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

## Public (FRP) auth

Backend includes `owl-auth-token` validation middleware.

- It only validates token when request is considered "public via FRP".
- Default public detector: header `x-owl-via-frp: 1`.
- Token algorithm matches Avalonia client:
  - `sha256("<unix_time//120>:<OWL_AUTH_SALT>").lower()`
  - Backend accepts current window and neighbor windows (clock skew).

Recommended FRP config (`frpc.toml`, `type = "http"`):

```toml
[[proxies]]
name = "owl-api"
type = "http"
localPort = 8080
customDomains = ["api.example.com"]
requestHeaders.set.x-owl-via-frp = "1"
```

`X-Forwarded-For` may exist in FRP HTTP mode, but default backend does not rely on it for public detection.
