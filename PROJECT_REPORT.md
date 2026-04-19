# PipeGuard Full Project Report

## 1. Project Overview

PipeGuard is now an integrated full-stack leak monitoring system with:

- React frontend (dashboard + analytics)
- Django backend (API + static frontend serving)
- Existing ML model integration (no retraining)
- Single-sensor live monitoring pipeline
- Production deployment via Gunicorn + systemd
- Public deployment via Cloudflare Tunnel

The project reads pressure data from a single HX710B-based sensor stream, converts pressure to KPa, runs prediction in backend, stores readings, and serves results to frontend in real time.

---

## 2. AI/ML Model Used

### 2.1 Active Model

Model metadata source: [models/best_model_meta.json](models/best_model_meta.json)

- model_name: isolation_forest_ensemble
- trained_at: 2026-04-07T15:01:05.120637+00:00
- trained_on_scenarios: [1, 2, 3]
- feature set: engineered differential + rolling statistical features (windowed)

### 2.2 Inference Wrapper

Inference service file: [src/predict.py](src/predict.py)

Key points:

- Loads existing serialized model from `models/best_model.pkl`
- Uses `PipeGuardPredictor.predict_proba(...)` for real-time inference
- Preserves compatibility for custom class unpickling (`IsolationForestLeakPipeline`)
- Uses rolling history to build features and outputs probability + leak decision

### 2.3 Model Metrics Source

Comparison report: [reports/model_comparison.csv](reports/model_comparison.csv)

Backend reads metrics for active model and exposes them via API.

---

## 3. Final Tech Stack

### Backend

- Python 3
- Django (API + app serving)
- Gunicorn (production WSGI server)
- SQLite (reading persistence)

### ML / Data

- scikit-learn, xgboost, lightgbm, joblib
- pandas, numpy, scipy

### Sensor / Hardware Integration

- HX710B reader: [src/hx710b.py](src/hx710b.py)
- GPIO backends:
  - RPi.GPIO (preferred when available)
  - gpiod fallback
  - synthetic mock fallback when GPIO unavailable/busy

### Frontend

- React + Vite
- React Router
- TanStack Query
- Tailwind-based styling + dashboard components
- Recharts for analytics/graphs

### Public Access

- Cloudflare Tunnel (quick tunnel)

---

## 4. Project Structure (Current)

### Core directories

- Backend: [backend](backend)
- Frontend: [Frontend](Frontend)
- ML and sensor integration: [src](src)
- Models and metadata: [models](models)
- Reports: [reports](reports)
- Deployment scripts: [scripts](scripts)
- Runtime logs: [logs](logs)
- Runtime PID/state: [run](run)

### Important backend files

- Settings: [backend/core/settings.py](backend/core/settings.py)
- URL root: [backend/core/urls.py](backend/core/urls.py)
- API routes: [backend/monitor/urls.py](backend/monitor/urls.py)
- API handlers: [backend/monitor/views.py](backend/monitor/views.py)
- Monitoring engine: [backend/monitor/services/engine.py](backend/monitor/services/engine.py)
- DB model: [backend/monitor/models.py](backend/monitor/models.py)

### Important frontend files

- App router: [Frontend/src/App.jsx](Frontend/src/App.jsx)
- Route config: [Frontend/src/pages.config.js](Frontend/src/pages.config.js)
- Dashboard page: [Frontend/src/pages/Dashboard.jsx](Frontend/src/pages/Dashboard.jsx)
- Analytics page: [Frontend/src/pages/Analytics.jsx](Frontend/src/pages/Analytics.jsx)

Dashboard components:

- [Frontend/src/components/dashboard/DashboardHeader.jsx](Frontend/src/components/dashboard/DashboardHeader.jsx)
- [Frontend/src/components/dashboard/LeakStatusCard.jsx](Frontend/src/components/dashboard/LeakStatusCard.jsx)
- [Frontend/src/components/dashboard/ModelMetricsCard.jsx](Frontend/src/components/dashboard/ModelMetricsCard.jsx)
- [Frontend/src/components/dashboard/SystemStatusPanel.jsx](Frontend/src/components/dashboard/SystemStatusPanel.jsx)
- [Frontend/src/components/dashboard/SignalChart.jsx](Frontend/src/components/dashboard/SignalChart.jsx)
- [Frontend/src/components/dashboard/AlertHistoryTable.jsx](Frontend/src/components/dashboard/AlertHistoryTable.jsx)

---

## 5. Architecture and Data Flow

1. Sensor sampled by `MonitoringEngine` in backend.
2. Raw pressure converted to:
   - pressure_pa
   - pressure_kpa (required display/storage unit)
3. Sensor health determined (`online` / `offline` / `unstable`).
4. Prediction computed with existing model (single sensor mirrored into model’s two expected inputs).
5. Reading persisted into DB as `Reading` row.
6. API publishes latest data through:
   - REST latest endpoint
   - SSE stream endpoint
7. React dashboard consumes stream + fallback polling.
8. Analytics page reads historical readings and summary endpoints.
9. CSV export endpoint outputs required columns:
   - pressure_kpa
   - label
   - confidence_score_percent

---

## 6. Frontend Routes and Pages

Routes are defined from [Frontend/src/pages.config.js](Frontend/src/pages.config.js) and wired in [Frontend/src/App.jsx](Frontend/src/App.jsx).

### Available routes

- `/` → Dashboard (main page)
- `/Dashboard` → Dashboard
- `/Analytics` → Analytics

### Dashboard features

- Turn On / Turn Off monitoring controls (API-backed)
- Real-time pressure display in KPa
- Real-time prediction label (`leak` / `no_leak`)
- Confidence percentage label
- Sensor health and power state indicators
- SSE streaming + polling fallback
- CSV export action

### Analytics features

- Historical pressure curve (KPa)
- Summary cards (counts, leak events, avg/min/max pressure)
- Sensor status snapshot
- Leak event markers on chart
- CSV export shortcut

---

## 7. Backend API Documentation

Base URL examples:

- Local: `http://127.0.0.1:8000`
- LAN: `http://<your-laptop-ip>:8000`
- Public tunnel: `https://<random>.trycloudflare.com`

### 7.1 System control

#### POST /api/system/power-on
Starts monitoring engine thread.

Response (example):

```json
{
  "ok": true,
  "power_state": "on",
  "sensor_status": "online",
  "latest": { "...": "latest payload" }
}
```

#### POST /api/system/power-off
Stops monitoring engine thread.

#### GET /api/system/status
Returns service status + latest payload.

### 7.2 Live data

#### GET /api/live/latest
Returns latest packet:

Core fields:

- seq
- timestamp
- is_running
- sensor_status
- sensor_mode
- sensor_error
- raw_pressure
- pressure_pa
- pressure_kpa
- label
- confidence_score_percent
- prediction_probability

#### GET /api/live/stream
Server-Sent Events stream (`text/event-stream`) of latest packets.

### 7.3 Model metrics

#### GET /api/model-metrics
Returns active model metrics + runtime counts.

Legacy alias also available:

- GET /api/model_metrics

### 7.4 Analytics

#### GET /api/analytics/summary
Returns summary stats:

- total_readings
- leak_events
- avg_pressure_kpa
- min_pressure_kpa
- max_pressure_kpa
- power_state
- sensor_status
- latest_timestamp

#### GET /api/analytics/history?limit=600
Returns historical reading list in chronological order.

### 7.5 Export

#### GET /api/export/csv
Downloads CSV with exact columns:

- pressure_kpa
- label
- confidence_score_percent

---

## 8. Database Model

Model: `Reading` in [backend/monitor/models.py](backend/monitor/models.py)

Fields:

- timestamp
- pressure_kpa
- label (`leak` / `no_leak`)
- confidence_score_percent
- prediction_probability
- sensor_status (`online` / `offline` / `unstable`)

Database:

- SQLite file: [backend/db.sqlite3](backend/db.sqlite3)

---

## 9. Run from Scratch (Local)

## 9.1 Prerequisites

- Python 3
- Node.js + npm
- Linux utilities: `lsof`, `curl`, `ss`

## 9.2 One-command local run (dev-style)

Script: [scripts/deploy_local.sh](scripts/deploy_local.sh)

```bash
cd /home/test/Downloads/pipeguard
./scripts/deploy_local.sh
```

What it does:

- creates/uses `.venv`
- installs python dependencies
- installs frontend dependencies
- builds frontend
- runs django migrations
- starts Django dev server

---

## 10. Real Production Deployment (Gunicorn)

Script: [scripts/deploy_production.sh](scripts/deploy_production.sh)

```bash
cd /home/test/Downloads/pipeguard
./scripts/deploy_production.sh
```

What it does:

- installs requirements (including gunicorn)
- builds frontend
- migrates DB
- starts Gunicorn daemon
- writes PID and logs

Related commands:

- status: [scripts/status_production.sh](scripts/status_production.sh)
- stop: [scripts/stop_production.sh](scripts/stop_production.sh)

Logs:

- [logs/gunicorn-access.log](logs/gunicorn-access.log)
- [logs/gunicorn-error.log](logs/gunicorn-error.log)

---

## 11. Real Service Deployment (systemd)

Installer script: [scripts/install_systemd_service.sh](scripts/install_systemd_service.sh)

```bash
cd /home/test/Downloads/pipeguard
./scripts/install_systemd_service.sh
```

Result:

- creates `/etc/systemd/system/pipeguard.service`
- enables service on boot
- starts service now
- restarts automatically on failure

Service operations:

- status helper: [scripts/status_systemd.sh](scripts/status_systemd.sh)
- remove service: [scripts/undeploy_systemd.sh](scripts/undeploy_systemd.sh)

---

## 12. Public Deployment via Cloudflare Tunnel

## 12.1 Start public tunnel

Script: [scripts/start_public_tunnel.sh](scripts/start_public_tunnel.sh)

```bash
cd /home/test/Downloads/pipeguard
./scripts/start_public_tunnel.sh
```

This returns a URL like:

- `https://<random>.trycloudflare.com`

## 12.2 Check tunnel URL and PID

Script: [scripts/status_public_tunnel.sh](scripts/status_public_tunnel.sh)

```bash
./scripts/status_public_tunnel.sh
```

## 12.3 Stop tunnel

Script: [scripts/stop_public_tunnel.sh](scripts/stop_public_tunnel.sh)

```bash
./scripts/stop_public_tunnel.sh
```

### Important tunnel notes

- Quick tunnel URL is temporary and changes on restart.
- For a permanent URL/domain, move to named Cloudflare Tunnel with Cloudflare account.

Cloudflare docs:

- https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/

---

## 13. Current Environment Notes

- Default sensor pin mapping now standardized to single sensor:
  - SCK: GPIO27
  - DOUT: GPIO17
- Backend converts pressure to KPa for storage/display.
- If GPIO access is unavailable or busy, engine can fall back to unstable/mock behavior and report health accordingly.

---

## 14. Quick Command Cheatsheet

## Install/build/deploy production

```bash
cd /home/test/Downloads/pipeguard
./scripts/deploy_production.sh
```

## Install as boot service

```bash
./scripts/install_systemd_service.sh
```

## Check service

```bash
./scripts/status_systemd.sh
```

## Start public URL

```bash
./scripts/start_public_tunnel.sh
./scripts/status_public_tunnel.sh
```

## Stop public URL

```bash
./scripts/stop_public_tunnel.sh
```

## Stop production daemon

```bash
./scripts/stop_production.sh
```

---

## 15. What Was Refactored (Summary)

- Replaced ad-hoc runtime wiring with clean Django backend APIs.
- Preserved and integrated existing trained ML model.
- Standardized app around one sensor.
- Added KPa conversion in backend pipeline.
- Added power control lifecycle (`on/off`) in backend + UI.
- Added persisted historical readings and exact CSV export format.
- Added dedicated analytics page and chart.
- Added production deployment scripts for Gunicorn, systemd, and public Cloudflare tunnel.

---

## 16. Main Internal and External References

Internal file links:

- [src/predict.py](src/predict.py)
- [src/hx710b.py](src/hx710b.py)
- [backend/monitor/services/engine.py](backend/monitor/services/engine.py)
- [backend/monitor/views.py](backend/monitor/views.py)
- [Frontend/src/pages/Dashboard.jsx](Frontend/src/pages/Dashboard.jsx)
- [Frontend/src/pages/Analytics.jsx](Frontend/src/pages/Analytics.jsx)

External references:

- Django deployment overview: https://docs.djangoproject.com/en/stable/howto/deployment/
- Gunicorn docs: https://docs.gunicorn.org/en/stable/
- Cloudflare Tunnel docs: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
