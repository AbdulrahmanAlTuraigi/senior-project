# PipeGuard Live Raspberry Pi Setup (HX710B)

## 1) Wiring (your current setup)

- HX710B `SCK` -> Raspberry Pi GPIO17
- HX710B `DOUT`/`OUT` -> Raspberry Pi GPIO27
- Sensor `VCC` -> 3.3V
- Sensor `GND` -> GND

## 2) Install dependencies on the Pi

```bash
cd /home/test/Downloads/pipeguard
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If `RPi.GPIO` is missing:

```bash
pip install RPi.GPIO
```

## 3) Run live server + dashboard

```bash
cd /home/test/Downloads/pipeguard
source .venv/bin/activate
python -m src.live_server
```

Open in browser:

- `http://<your-rpi-ip>:8000`

API endpoints:

- `GET /api/latest` -> latest packet JSON
- `GET /api/stream` -> Server-Sent Events live stream
- `GET /api/health` -> health/model status

## 4) Model connection behavior

The server uses `models/best_model.pkl` and `models/best_model_meta.json` via `PipeGuardPredictor` in `src/predict.py`.

Because this model expects two channels (`sensor1_V`, `sensor2_V`):

- If only one HX710B is configured (your current wiring), the server mirrors sensor1 into sensor2.
- This runs, but best accuracy requires two real pressure sensors.

## 5) Optional second sensor (recommended)

Example:

- Sensor2 SCK -> GPIO22
- Sensor2 DOUT -> GPIO23

Run with environment variables:

```bash
SENSOR1_SCK=17 SENSOR1_DOUT=27 SENSOR2_SCK=22 SENSOR2_DOUT=23 python -m src.live_server
```

## 6) Calibration (important)

Raw ADC values should be scaled into the same unit range used during model training (voltage-like values in this project).

Use env vars:

```bash
SENSOR1_OFFSET=<raw_zero> SENSOR1_SCALE=<scale_factor> \
SENSOR2_OFFSET=<raw_zero> SENSOR2_SCALE=<scale_factor> \
python -m src.live_server
```

The live payload includes both raw and calibrated values for tuning.

## 7) Connect your existing HTML/CSS/JS app

If your app is separate, consume the stream like this:

```javascript
const stream = new EventSource("http://<your-rpi-ip>:8000/api/stream");
stream.onmessage = (event) => {
  const packet = JSON.parse(event.data);
  // packet.sensor1_V, packet.sensor2_V, packet.leak_probability, packet.alert_level
};
```

Or poll every second:

```javascript
setInterval(async () => {
  const res = await fetch("http://<your-rpi-ip>:8000/api/latest");
  const packet = await res.json();
  console.log(packet);
}, 1000);
```
