"""
Live sensor + model inference server for Raspberry Pi.

Reads HX710B values from GPIO, runs PipeGuard model inference, and streams
live data to a browser dashboard (SSE + JSON endpoints).
"""

from __future__ import annotations

import csv
import json
import logging
import os
import signal
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Deque, Dict

from flask import Flask, Response, jsonify, send_from_directory

from src.hx710b import HX710B, HX710BConfig
from src.predict import PipeGuardPredictor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("src.features").setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
FRONTEND_DIST_DIR = ROOT / "Frontend" / "dist"
STATIC_DIR = FRONTEND_DIST_DIR if (FRONTEND_DIST_DIR / "index.html").exists() else WEB_DIR


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    return int(val)


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None:
        return default
    return float(val)


class LiveEngine:
    """Owns sensors, model, rolling history, and latest packet state."""

    def __init__(self) -> None:
        self.sample_hz = _env_float("PIPEGUARD_SAMPLE_HZ", 10.0)
        self.sensor1 = HX710B(
            HX710BConfig(
                sck_pin=_env_int("SENSOR1_SCK", 17),
                dout_pin=_env_int("SENSOR1_DOUT", 27),
                offset=_env_float("SENSOR1_OFFSET", 0.0),
                scale=_env_float("SENSOR1_SCALE", 1.0),
            )
        )

        # Optional second pressure channel. If not configured, mirror sensor1.
        sensor2_dout = os.getenv("SENSOR2_DOUT")
        sensor2_sck = os.getenv("SENSOR2_SCK")
        self.sensor2 = None
        if sensor2_dout and sensor2_sck:
            self.sensor2 = HX710B(
                HX710BConfig(
                    sck_pin=int(sensor2_sck),
                    dout_pin=int(sensor2_dout),
                    offset=_env_float("SENSOR2_OFFSET", 0.0),
                    scale=_env_float("SENSOR2_SCALE", 1.0),
                )
            )

        self.predictor = PipeGuardPredictor()
        self.history: Deque[Dict[str, float]] = deque(maxlen=160)
        self.seq = 0
        self.total_predictions = 0
        self.alert_predictions = 0
        self._last_raw1: int | None = None
        self._zero_streak = 0
        self._same_streak = 0
        self._zero_fault_threshold = max(6, int(self.sample_hz * 1.5))
        self._same_fault_threshold = max(12, int(self.sample_hz * 3.0))
        self.latest: Dict[str, Any] = {
            "seq": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sensor1_V": None,
            "sensor2_V": None,
            "raw1": None,
            "raw2": None,
            "mode": "mock" if self.sensor1.is_mock else "gpio",
            "gpio_error": self.sensor1.init_error,
            "sensor_health": "unknown",
            "sensor_fault": None,
            "leak_probability": None,
            "leak_detected": False,
            "confidence": "low",
            "alert_level": "WARNING",
            "status": "starting",
        }
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2.0)
        self.sensor1.close()
        if self.sensor2:
            self.sensor2.close()

    def _run_loop(self) -> None:
        period = max(1e-3, 1.0 / self.sample_hz)
        logger.info("Live loop starting at %.2f Hz", self.sample_hz)

        while not self.stop_event.is_set():
            t0 = time.time()
            raw1 = self.sensor1.read_raw()
            val1 = None if raw1 is None else (raw1 - self.sensor1.config.offset) * self.sensor1.config.scale

            raw2 = None
            val2 = None
            if self.sensor2:
                raw2 = self.sensor2.read_raw()
                val2 = None if raw2 is None else (raw2 - self.sensor2.config.offset) * self.sensor2.config.scale
            elif val1 is not None:
                val2 = val1

            status = "ok"
            sensor_health = "ok"
            sensor_fault = None
            pred = {
                "leak_probability": None,
                "leak_detected": False,
                "confidence": "low",
                "alert_level": "WARNING",
            }

            if raw1 is None:
                sensor_health = "fault"
                sensor_fault = "sensor_timeout"
            else:
                if raw1 == 0 and not self.sensor1.is_mock:
                    self._zero_streak += 1
                else:
                    self._zero_streak = 0

                if self._last_raw1 is not None and raw1 == self._last_raw1 and not self.sensor1.is_mock:
                    self._same_streak += 1
                else:
                    self._same_streak = 0
                self._last_raw1 = raw1

                if self._zero_streak >= self._zero_fault_threshold:
                    sensor_health = "fault"
                    sensor_fault = "sensor_stuck_zero"
                elif self._same_streak >= self._same_fault_threshold:
                    sensor_health = "fault"
                    sensor_fault = "sensor_stuck_value"

            if sensor_health == "ok" and val1 is not None and val2 is not None:
                pred = self.predictor.predict_proba(
                    sensor1_V=float(val1),
                    sensor2_V=float(val2),
                    history=self.history,
                )
                self.history.append({"sensor1_V": float(val1), "sensor2_V": float(val2)})

                self.total_predictions += 1
                if bool(pred.get("leak_detected")):
                    self.alert_predictions += 1
            else:
                status = sensor_fault or "sensor_fault"
                if sensor_fault:
                    # Prevent stale history from driving predictions during a hardware fault.
                    self.history.clear()

            with self.lock:
                self.seq += 1
                self.latest = {
                    "seq": self.seq,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sensor1_V": val1,
                    "sensor2_V": val2,
                    "raw1": raw1,
                    "raw2": raw2,
                    "mode": "mock" if self.sensor1.is_mock else "gpio",
                    "gpio_error": self.sensor1.init_error,
                    "sensor_health": sensor_health,
                    "sensor_fault": sensor_fault,
                    "status": status,
                    **pred,
                }

            elapsed = time.time() - t0
            to_sleep = period - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)


engine = LiveEngine()
# We serve the frontend ourselves to support SPA fallback routing.
app = Flask(__name__, static_folder=None)


@app.get("/api/health")
def health() -> Response:
    return jsonify({"ok": True, "model": engine.predictor.model_name, "seq": engine.seq})


def _safe_float(val: object) -> float | None:
    try:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


@app.get("/api/model_metrics")
def model_metrics() -> Response:
    model_name = engine.predictor.model_name

    payload: Dict[str, Any] = {
        "model": model_name,
        "model_version": None,
        "accuracy": None,
        "precision": None,
        "recall": None,
        "f1_score": None,
        "total_predictions": engine.total_predictions,
        "alert_rate": (engine.alert_predictions / engine.total_predictions) if engine.total_predictions else None,
    }

    meta_path = ROOT / "models" / "best_model_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            payload["model_version"] = meta.get("trained_at") or meta.get("model_name")
        except Exception:
            pass

    report_path = ROOT / "reports" / "model_comparison.csv"
    if report_path.exists():
        try:
            with report_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("model") == model_name:
                        payload["accuracy"] = _safe_float(row.get("accuracy_mean"))
                        payload["precision"] = _safe_float(row.get("precision_mean"))
                        payload["recall"] = _safe_float(row.get("recall_mean"))
                        payload["f1_score"] = _safe_float(row.get("f1_mean"))
                        break
        except Exception:
            pass

    return jsonify(payload)


@app.get("/api/latest")
def latest() -> Response:
    with engine.lock:
        payload = dict(engine.latest)
    return jsonify(payload)


@app.get("/api/stream")
def stream() -> Response:
    def event_gen() -> Any:
        last_seq = -1
        while True:
            with engine.lock:
                payload = dict(engine.latest)
            if payload["seq"] != last_seq:
                last_seq = payload["seq"]
                yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(0.1)

    return Response(event_gen(), mimetype="text/event-stream")


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def index(path: str) -> Response:
    # Let the explicit /api/* routes win. This is just a safety net.
    if path.startswith("api/"):
        return Response("Not Found", status=404)

    # Avoid any path traversal tricks.
    if path and ".." in PurePosixPath(path).parts:
        return Response("Not Found", status=404)

    requested = STATIC_DIR / path
    if path and requested.is_file():
        return send_from_directory(STATIC_DIR, path)

    # SPA fallback
    return send_from_directory(STATIC_DIR, "index.html")


def _shutdown_handler(signum: int, frame: Any) -> None:
    logger.info("Signal %s received, shutting down live engine.", signum)
    engine.stop()
    raise SystemExit(0)


def main() -> None:
    engine.start()
    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    host = os.getenv("PIPEGUARD_HOST", "0.0.0.0")
    port = _env_int("PIPEGUARD_PORT", 8000)
    logger.info("Serving dashboard on http://%s:%d", host, port)
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
