# Owl Assistant Backend (Unified)

Single service backend for Owl Assistant, based on FastAPI.

## Features

- Unified API prefix: `/api/v1`
- Sensor data from MySQL (`mitemperature` tables):
  - `lywsd03mmc_readings`
  - `daikin_readings`
- System info APIs
- USB thermal printer APIs (python-escpos + pyusb)
- No FM/ATIS backend

## API

- `GET /healthz`
- `GET /api/v1/sensors/latest`
- `POST /api/v1/sensors/history`
- `POST /api/v1/system/raw`
- `POST /api/v1/system/summary`
- `POST /api/v1/printer/online`
- `POST /api/v1/printer/system-ticket`
- `POST /api/v1/printer/print`

## Run with Docker Compose

1. Copy env:

```bash
cp .env.example .env
```

2. Start:

```bash
docker compose up --build -d
```

3. Logs:

```bash
docker compose logs -f
```

## USB Notes

`docker-compose.yml` maps `/dev/bus/usb` and includes:

- `device_cgroup_rules: "c 189:* rmw"`

This is needed for pyusb/libusb access to USB device nodes in containers.
