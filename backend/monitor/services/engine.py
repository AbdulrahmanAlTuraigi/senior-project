from __future__ import annotations

import csv
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.db import close_old_connections

from monitor.models import Reading

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.hx710b import HX710B, HX710BConfig  # noqa: E402
from src.predict import PipeGuardPredictor  # noqa: E402

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    return default if v is None else int(v)


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    return default if v is None else float(v)


class MonitoringEngine:
    """Single-sensor monitoring engine with model inference."""

    def __init__(self) -> None:
        self.sample_hz = _env_float("MONITOR_SAMPLE_HZ", 10.0)

        self.sensor = HX710B(
            HX710BConfig(
                sck_pin=_env_int("SENSOR1_SCK", 17),
                dout_pin=_env_int("SENSOR1_DOUT", 27),
                offset=_env_float("SENSOR1_OFFSET", 0.0),
                scale=_env_float("SENSOR1_SCALE", 1.0),
                ready_timeout_s=_env_float("SENSOR_READY_TIMEOUT_S", 0.25),
            )
        )
        self.predictor = PipeGuardPredictor()

        self._history = deque(maxlen=160)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._is_running = False
        self._seq = 0
        self._last_raw: int | None = None
        self._zero_streak = 0
        self._same_streak = 0
        self._zero_fault_threshold = max(6, int(self.sample_hz * 1.5))
        self._same_fault_threshold = max(600, int(self.sample_hz * 120.0))

        self._latest: dict[str, Any] = {
            "seq": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_running": False,
            "sensor_status": "offline",
            "sensor_mode": "mock" if self.sensor.is_mock else "gpio",
            "sensor_error": self.sensor.init_error,
            "raw_pressure": None,
            "pressure_pa": None,
            "pressure_kpa": None,
            "label": "no_leak",
            "confidence_score_percent": 0.0,
            "prediction_probability": None,
        }

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def start(self) -> None:
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        thread: threading.Thread | None = None
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            self._stop_event.set()
            thread = self._thread

        if thread is not None:
            thread.join(timeout=2.0)

        with self._lock:
            self._history.clear()
            self._latest["is_running"] = False
            self._latest["sensor_status"] = "offline"

    def get_latest(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._latest)

    def _classify_sensor_health(self, raw: int | None) -> str:
        if raw is None:
            self._zero_streak = 0
            self._same_streak = 0
            self._last_raw = None
            return "offline"

        if self.sensor.is_mock:
            return "unstable"

        if raw == 0:
            self._zero_streak += 1
        else:
            self._zero_streak = 0

        if self._last_raw is not None and raw == self._last_raw:
            self._same_streak += 1
        else:
            self._same_streak = 0

        self._last_raw = raw

        if self._zero_streak >= self._zero_fault_threshold:
            return "unstable"
        if self._same_streak >= self._same_fault_threshold:
            return "unstable"
        return "online"

    def _build_prediction(self, pressure_pa: float | None, sensor_status: str) -> dict[str, Any]:
        if pressure_pa is None or sensor_status != "online":
            self._history.clear()
            return {
                "label": "no_leak",
                "confidence_score_percent": 0.0,
                "prediction_probability": None,
            }

        pred = self.predictor.predict_proba(
            sensor1_V=float(pressure_pa),
            sensor2_V=float(pressure_pa),
            history=self._history,
        )

        self._history.append(
            {
                "sensor1_V": float(pressure_pa),
                "sensor2_V": float(pressure_pa),
            }
        )

        prob = pred.get("leak_probability")
        if isinstance(prob, (int, float)):
            prob_value = float(prob)
            conf_percent = max(0.0, min(100.0, prob_value * 100.0))
        else:
            prob_value = None
            conf_percent = 0.0

        label = "leak" if bool(pred.get("leak_detected")) else "no_leak"
        return {
            "label": label,
            "confidence_score_percent": conf_percent,
            "prediction_probability": prob_value,
        }

    def _persist_reading(
        self,
        pressure_kpa: float | None,
        label: str,
        confidence_score_percent: float,
        prediction_probability: float | None,
        sensor_status: str,
    ) -> None:
        if pressure_kpa is None:
            return
        close_old_connections()
        Reading.objects.create(
            pressure_kpa=pressure_kpa,
            label=label,
            confidence_score_percent=confidence_score_percent,
            prediction_probability=prediction_probability,
            sensor_status=sensor_status,
        )

    def _loop(self) -> None:
        period = max(1e-3, 1.0 / self.sample_hz)
        logger.info("Monitoring loop started at %.2f Hz", self.sample_hz)

        while not self._stop_event.is_set():
            t0 = time.time()

            raw = self.sensor.read_raw()
            pressure_pa = None if raw is None else (raw - self.sensor.config.offset) * self.sensor.config.scale
            pressure_kpa = None if pressure_pa is None else float(pressure_pa) / 1000.0

            sensor_status = self._classify_sensor_health(raw)
            pred = self._build_prediction(pressure_pa=pressure_pa, sensor_status=sensor_status)

            now_iso = datetime.now(timezone.utc).isoformat()

            with self._lock:
                self._seq += 1
                payload = {
                    "seq": self._seq,
                    "timestamp": now_iso,
                    "is_running": self._is_running,
                    "sensor_status": sensor_status,
                    "sensor_mode": "mock" if self.sensor.is_mock else "gpio",
                    "sensor_error": self.sensor.init_error,
                    "raw_pressure": raw,
                    "pressure_pa": pressure_pa,
                    "pressure_kpa": pressure_kpa,
                    **pred,
                }
                self._latest = payload

            self._persist_reading(
                pressure_kpa=pressure_kpa,
                label=pred["label"],
                confidence_score_percent=pred["confidence_score_percent"],
                prediction_probability=pred["prediction_probability"],
                sensor_status=sensor_status,
            )

            elapsed = time.time() - t0
            delay = period - elapsed
            if delay > 0:
                time.sleep(delay)

        logger.info("Monitoring loop stopped")


engine = MonitoringEngine()


def load_model_metrics() -> dict[str, Any]:
    """Read model metrics from existing metadata/report artifacts."""
    model_name = engine.predictor.model_name
    result: dict[str, Any] = {
        "model": model_name,
        "model_version": None,
        "accuracy": None,
        "precision": None,
        "recall": None,
        "f1_score": None,
    }

    meta_path = PROJECT_ROOT / "models" / "best_model_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            result["model_version"] = meta.get("trained_at")
        except Exception:
            logger.exception("Failed to read model metadata")

    report_path = PROJECT_ROOT / "reports" / "model_comparison.csv"
    if report_path.exists():
        try:
            with report_path.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("model") == model_name:
                        result["accuracy"] = _safe_float(row.get("accuracy_mean"))
                        result["precision"] = _safe_float(row.get("precision_mean"))
                        result["recall"] = _safe_float(row.get("recall_mean"))
                        result["f1_score"] = _safe_float(row.get("f1_mean"))
                        break
        except Exception:
            logger.exception("Failed to read model comparison report")

    return result


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None
