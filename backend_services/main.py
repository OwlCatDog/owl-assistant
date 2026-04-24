import io
import os
import platform
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import filetype
import psutil
import pymysql
import usb.core
from escpos.printer import Usb as EscposUsb
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image


BLE_TABLE = "lywsd03mmc_readings"
DAIKIN_TABLE = "daikin_readings"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    return int(raw)


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


@dataclass
class Settings:
    api_host: str
    api_port: int
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    inside_sensor_mac: str
    outside_sensor_mac: str
    darkin_sensor_name: str
    thermal_printer_vid: int
    thermal_printer_pid: int
    thermal_print_width: int

    @staticmethod
    def load() -> "Settings":
        return Settings(
            api_host=_env_str("API_HOST", "0.0.0.0"),
            api_port=_env_int("API_PORT", 8080),
            mysql_host=_env_str("MYSQL_HOST", "127.0.0.1"),
            mysql_port=_env_int("MYSQL_PORT", 3306),
            mysql_user=_env_str("MYSQL_USER", "root"),
            mysql_password=_env_str("MYSQL_PASSWORD", ""),
            mysql_database=_env_str("MYSQL_DATABASE", "mitemperature"),
            inside_sensor_mac=_env_str("INSIDE_SENSOR_MAC", "A4:C1:38:CF:B0:D6").upper(),
            outside_sensor_mac=_env_str("OUTSIDE_SENSOR_MAC", "A4:C1:38:D5:05:79").upper(),
            darkin_sensor_name=_env_str("DARKIN_SENSOR_NAME", "darkin"),
            thermal_printer_vid=int(_env_str("THERMAL_PRINTER_VID", "0x0416"), 0),
            thermal_printer_pid=int(_env_str("THERMAL_PRINTER_PID", "0x5011"), 0),
            thermal_print_width=_env_int("THERMAL_PRINT_WIDTH", 400),
        )


settings = Settings.load()


class SensorHistoryRequest(BaseModel):
    sensor: str | None = None
    db: str | None = None
    start: str
    end: str


class RawInfoRequest(BaseModel):
    req: str


class MySqlClient:
    def __init__(self, cfg: Settings):
        self._cfg = cfg

    def _connect(self):
        return pymysql.connect(
            host=self._cfg.mysql_host,
            port=self._cfg.mysql_port,
            user=self._cfg.mysql_user,
            password=self._cfg.mysql_password,
            database=self._cfg.mysql_database,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone()
        finally:
            conn.close()

    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        finally:
            conn.close()


class PrinterClient:
    def __init__(self, cfg: Settings):
        self._cfg = cfg
        self._lock = threading.Lock()

    def is_online(self) -> bool:
        dev = usb.core.find(idVendor=self._cfg.thermal_printer_vid, idProduct=self._cfg.thermal_printer_pid)
        return dev is not None

    def print_text(self, text: str):
        with self._lock:
            printer = EscposUsb(self._cfg.thermal_printer_vid, self._cfg.thermal_printer_pid)
            try:
                printer.text(text)
                printer.text("\n\n")
            finally:
                printer.close()

    def print_image(self, image_bytes: bytes):
        with self._lock:
            printer = EscposUsb(self._cfg.thermal_printer_vid, self._cfg.thermal_printer_pid)
            try:
                image = Image.open(io.BytesIO(image_bytes))
                width, height = image.size
                if width > height:
                    image = image.transpose(Image.ROTATE_90)
                    width, height = image.size
                factor = self._cfg.thermal_print_width / float(width)
                new_height = max(1, int(height * factor))
                image = image.resize((self._cfg.thermal_print_width, new_height))
                printer.image(image)
                printer.text("\n\n")
            finally:
                printer.close()


mysql_client = MySqlClient(settings)
printer_client = PrinterClient(settings)
app = FastAPI(title="owl-assistant-api", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_unix_seconds(ts: datetime | None) -> int:
    if ts is None:
        return 0
    if ts.tzinfo is None:
        return int(ts.replace(tzinfo=timezone.utc).timestamp())
    return int(ts.timestamp())


def _to_iso_time(ts: datetime | None) -> str:
    if ts is None:
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _to_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    return int(v)


def _default_ble_payload(name: str) -> dict[str, Any]:
    return {
        "temp": 0.0,
        "humi": 0.0,
        "volt": 0.0,
        "name": name,
        "rssi": 0,
        "batt": 0,
        "time": "-",
        "stamp": 0,
    }


def _default_darkin_payload() -> dict[str, Any]:
    return {
        "temp": 0.0,
        "humi": 0.0,
        "co2": 0,
        "eco2": 0,
        "pm1": 0.0,
        "pm10": 0.0,
        "pm25": 0.0,
        "tvoc": 0,
        "name": settings.darkin_sensor_name,
        "time": "-",
        "stamp": 0,
    }


def _latest_ble_by_mac(mac: str) -> dict[str, Any]:
    sql = f"""
    SELECT mac, temperature, humidity, voltage, battery, rssi, timestamp
    FROM {BLE_TABLE}
    WHERE mac = %s
    ORDER BY timestamp DESC
    LIMIT 1
    """
    row = mysql_client.fetch_one(sql, (mac,))
    if row is None:
        return _default_ble_payload(mac)
    ts = row["timestamp"]
    return {
        "temp": round(_to_float(row["temperature"]), 2),
        "humi": round(_to_float(row["humidity"]), 2),
        "volt": round(_to_float(row["voltage"]), 3),
        "name": row["mac"],
        "rssi": _to_int(row["rssi"]),
        "batt": _to_int(row["battery"]),
        "time": _to_iso_time(ts),
        "stamp": _to_unix_seconds(ts),
    }


def _latest_darkin() -> dict[str, Any]:
    sql = f"""
    SELECT co2, eco2, pm1, pm25, pm10, tvoc, temperature, humidity, timestamp
    FROM {DAIKIN_TABLE}
    ORDER BY timestamp DESC
    LIMIT 1
    """
    row = mysql_client.fetch_one(sql, ())
    if row is None:
        return _default_darkin_payload()
    ts = row["timestamp"]
    return {
        "temp": round(_to_float(row["temperature"]), 2),
        "humi": round(_to_float(row["humidity"]), 2),
        "co2": _to_int(row["co2"]),
        "eco2": _to_int(row["eco2"]),
        "pm1": round(_to_float(row["pm1"]), 2),
        "pm10": round(_to_float(row["pm10"]), 2),
        "pm25": round(_to_float(row["pm25"]), 2),
        "tvoc": _to_int(row["tvoc"]),
        "name": settings.darkin_sensor_name,
        "time": _to_iso_time(ts),
        "stamp": _to_unix_seconds(ts),
    }


def _sensor_history(sensor: str, start: str, end: str) -> list[dict[str, Any]]:
    normalized = sensor.strip().lower()
    if normalized in {"inside", "inner_sensor"}:
        sql = f"""
        SELECT
          temperature AS temp,
          humidity AS humi,
          voltage AS volt,
          battery AS batt,
          rssi,
          mac AS name,
          timestamp AS time
        FROM {BLE_TABLE}
        WHERE mac = %s AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """
        rows = mysql_client.fetch_all(sql, (settings.inside_sensor_mac, start, end))
    elif normalized in {"outside", "out_sensor"}:
        sql = f"""
        SELECT
          temperature AS temp,
          humidity AS humi,
          voltage AS volt,
          battery AS batt,
          rssi,
          mac AS name,
          timestamp AS time
        FROM {BLE_TABLE}
        WHERE mac = %s AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """
        rows = mysql_client.fetch_all(sql, (settings.outside_sensor_mac, start, end))
    elif normalized in {"darkin", "darkin_sensor"}:
        sql = f"""
        SELECT
          temperature AS temp,
          humidity AS humi,
          pm1,
          pm25,
          pm10,
          tvoc,
          co2,
          eco2,
          timestamp AS time
        FROM {DAIKIN_TABLE}
        WHERE timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
        """
        rows = mysql_client.fetch_all(sql, (start, end))
    else:
        raise HTTPException(status_code=400, detail=f"Unknown sensor: {sensor}")

    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            if key == "time":
                item[key] = _to_iso_time(value)
            elif isinstance(value, Decimal):
                item[key] = float(value)
            else:
                item[key] = value
        out.append(item)
    return out


def _cpu_temp() -> str:
    temp_path = "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open(temp_path, "r", encoding="utf-8") as f:
            return f"{float(f.read().strip()) / 1000:.1f}"
    except Exception:
        return "0.0"


def _load_avg() -> dict[str, str]:
    if hasattr(os, "getloadavg"):
        one, five, fifteen = os.getloadavg()
        return {
            "1_min_avg": f"{one:.2f}",
            "5_min_avg": f"{five:.2f}",
            "15_min_avg": f"{fifteen:.2f}",
        }
    return {"1_min_avg": "0.00", "5_min_avg": "0.00", "15_min_avg": "0.00"}


def _current_ram() -> dict[str, str]:
    ram = psutil.virtual_memory()
    used = ram.total - ram.available
    return {
        "total": f"{ram.total / 1024 / 1024 / 1024:.2f}G",
        "used": f"{used / 1024 / 1024 / 1024:.2f}G",
        "available": f"{ram.available / 1024 / 1024 / 1024:.2f}G",
    }


def _system_general() -> dict[str, str]:
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    return {
        "OS": f"{platform.system()} {platform.release()}",
        "Uptime": str(uptime).split(".")[0],
        "Hostname": platform.node(),
    }


def _cpu_info() -> dict[str, str]:
    return {
        "Architecture": platform.machine(),
        "CPU(s)": str(psutil.cpu_count(logical=True) or 0),
        "Model name": platform.processor() or "Unknown",
    }


def _disk_partitions() -> list[dict[str, str]]:
    partitions: list[dict[str, str]] = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype == "":
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except Exception:
            continue
        partitions.append(
            {
                "file_system": part.device,
                "size": f"{usage.total / 1024 / 1024 / 1024:.2f}G",
                "used": f"{usage.used / 1024 / 1024 / 1024:.2f}G",
                "used%": f"{usage.percent:.1f}%",
                "mounted": part.mountpoint,
            }
        )
    return partitions


def _build_system_text(sensor_data: list[dict[str, Any]]) -> str:
    general = _system_general()
    load = _load_avg()
    temp = _cpu_temp()
    ram = _current_ram()
    cpu = _cpu_info()
    disks = _disk_partitions()

    lines: list[str] = []
    lines.append("Status Report Ticket")
    lines.append("Reporter v2")
    lines.append("")
    lines.append("----System info-----")
    lines.append(f"Operation System: {general['OS']}")
    lines.append(f"Uptime: {general['Uptime']}")
    lines.append(f"LoadAvg: {load['1_min_avg']}, {load['5_min_avg']}, {load['15_min_avg']}")
    lines.append("")
    lines.append("-----CPU info-----")
    lines.append(f"CPUArch: {cpu['Architecture']}")
    lines.append(f"Core: {cpu['CPU(s)']}")
    lines.append(f"Model: {cpu['Model name']}")
    lines.append(f"Temperature: {temp}C")
    lines.append("")
    lines.append("-----RAM Info-----")
    lines.append(f"Total: {ram['total']}")
    lines.append(f"Used: {ram['used']}")
    lines.append(f"Available: {ram['available']}")
    lines.append("")
    lines.append("-----Disk Info-----")
    for i in disks:
        lines.append(f"{i['file_system']}: {i['used']}/{i['size']}, used {i['used%']}, mount@{i['mounted']}")
    lines.append("")
    lines.append("-----Sensor Info-----")
    for item in sensor_data:
        lines.append(f"==={item['name']}===")
        lines.append(f"Temperature: {item.get('temp', 0)}C")
        lines.append(f"Humidity: {item.get('humi', 0)}%")
        if "batt" in item:
            lines.append(f"Batt: {item.get('batt', 0)}%")
            lines.append(f"Volt: {item.get('volt', 0)}v")
            lines.append(f"Rssi: {item.get('rssi', 0)}dBm")
        if "co2" in item:
            lines.append(f"CO2: {item.get('co2', 0)}ppm")
            lines.append(f"PM2.5: {item.get('pm25', 0)}ug/m3")
            lines.append(f"TVOC: {item.get('tvoc', 0)}")
        lines.append(f"Report@: {item.get('time', '-')}")
    lines.append("<<<<<<<<<<<<<<<<<<<<<")
    lines.append(f"PrintTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    return "\n".join(lines)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/v1/sensors/latest")
def get_sensors_latest():
    return [
        _latest_ble_by_mac(settings.inside_sensor_mac),
        _latest_ble_by_mac(settings.outside_sensor_mac),
        _latest_darkin(),
    ]


@app.post("/api/v1/sensors/history")
def get_sensors_history(payload: SensorHistoryRequest):
    sensor = payload.sensor or payload.db
    if not sensor:
        raise HTTPException(status_code=400, detail="sensor is required")
    result = _sensor_history(sensor, payload.start, payload.end)
    return {"result": result}


@app.post("/api/v1/system/raw")
def get_system_raw(payload: RawInfoRequest):
    req = payload.req.strip().lower()
    if req == "cpu_utilization":
        return {"code": 200, "data": f"{psutil.cpu_percent(interval=0.2):.1f}"}
    if req == "cpu_temp":
        return {"code": 200, "data": _cpu_temp()}
    if req == "current_ram":
        return {"code": 200, "data": _current_ram()}
    if req == "load_avg":
        return {"code": 200, "data": _load_avg()}
    if req == "general_info":
        return {"code": 200, "data": _system_general()}
    if req == "cpu_info":
        return {"code": 200, "data": _cpu_info()}
    if req == "disk_partitions":
        return {"code": 200, "data": _disk_partitions()}
    raise HTTPException(status_code=400, detail=f"Unknown raw req: {req}")


@app.post("/api/v1/system/summary")
def get_system_summary():
    payload = [
        _latest_ble_by_mac(settings.inside_sensor_mac),
        _latest_ble_by_mac(settings.outside_sensor_mac),
        _latest_darkin(),
    ]
    return {"code": 200, "data": _build_system_text(payload)}


@app.post("/api/v1/printer/online")
def printer_online():
    if printer_client.is_online():
        return {"code": 200}
    return {"code": 201}


@app.post("/api/v1/printer/system-ticket")
def printer_system_ticket():
    if not printer_client.is_online():
        return {"code": 201}
    payload = [
        _latest_ble_by_mac(settings.inside_sensor_mac),
        _latest_ble_by_mac(settings.outside_sensor_mac),
        _latest_darkin(),
    ]
    printer_client.print_text(_build_system_text(payload))
    return {"code": 200}


@app.post("/api/v1/printer/print")
async def printer_print(
    request: Request,
    file: UploadFile | None = File(default=None),
    text_payload: str | None = Form(default=None, alias="file"),
):
    if not printer_client.is_online():
        return {"code": 500, "msg": "设备离线！"}

    content_type = request.headers.get("content-type", "").lower()

    if "multipart/form-data" in content_type:
        if file is None:
            return {"code": 500, "msg": "未提供文件"}
        data = await file.read()
        if len(data) > 15 * 1024 * 1024:
            return {"code": 500, "msg": "图片大于15M!"}
        if filetype.guess(data) is None:
            return {"code": 500, "msg": "文件类型未知"}
        printer_client.print_image(data)
        return {"code": 200}

    if "application/x-www-form-urlencoded" in content_type:
        text = text_payload or ""
        if len(text) == 0 or len(text) > 1000:
            return {"code": 500, "msg": "长度超过1000字符！"}
        printer_client.print_text(text)
        return {"code": 200}

    return {"code": 500, "msg": "文件类型未知"}

