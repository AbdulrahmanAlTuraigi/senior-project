"""
Deployment-oriented inference for PipeGuard leak detection.
"""

from __future__ import annotations

import logging
import __main__
import sys
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, MutableMapping, Optional

import joblib
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.features import engineer_features  # noqa: E402
from src.train import IsolationForestLeakPipeline, _positive_proba  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# Backward compatibility for joblib models trained when train.py was executed
# as a script and custom estimators were serialized under __main__.
if not hasattr(__main__, "IsolationForestLeakPipeline"):
    __main__.IsolationForestLeakPipeline = IsolationForestLeakPipeline


def _confidence_label(p: float) -> str:
    """
    Map probability to qualitative confidence.

    Args:
        p: Predicted leak probability in [0, 1].

    Returns:
        One of 'high', 'medium', 'low'.
    """
    if p >= 0.7 or p <= 0.3:
        return "high"
    if 0.4 <= p <= 0.6:
        return "low"
    return "medium"


def _alert_level(p: float) -> str:
    """
    Map probability to alert level per PipeGuard rules.

    Args:
        p: Leak probability.

    Returns:
        'NONE', 'WARNING', or 'CRITICAL'.
    """
    if p < 0.3:
        return "NONE"
    if p < 0.6:
        return "WARNING"
    return "CRITICAL"


class PipeGuardPredictor:
    """
    Load trained model and run real-time or batch inference.
    """

    def __init__(
        self,
        model_path: str | Path = "models/best_model.pkl",
        meta_path: str | Path = "models/best_model_meta.json",
    ) -> None:
        """
        Load serialized model and metadata.

        Args:
            model_path: Path to joblib bundle from training.
            meta_path: Path to JSON metadata (feature names, etc.).
        """
        root = _ROOT
        mp = Path(model_path)
        if not mp.is_absolute():
            mp = root / mp
        jp = Path(meta_path)
        if not jp.is_absolute():
            jp = root / jp

        bundle: Dict[str, Any] = joblib.load(mp)
        self._model = bundle["model"]
        self.feature_names: List[str] = list(bundle["feature_names"])
        self.model_name: str = str(bundle["model_name"])
        self._meta_path = jp
        logger.info("Loaded model '%s' from %s", self.model_name, mp)

    def predict_proba(
        self,
        sensor1_V: float,
        sensor2_V: float,
        history: Deque[MutableMapping[str, float]],
    ) -> Dict[str, Any]:
        """
        Real-time inference for one new reading using prior samples in history.

        Args:
            sensor1_V: Upstream sensor voltage.
            sensor2_V: Downstream sensor voltage.
            history: Deque of the last ~160 dicts with keys 'sensor1_V', 'sensor2_V'
                (oldest at left, newest at right before the current sample).

        Returns:
            Dict with leak_probability, leak_detected (threshold 0.5), confidence,
            and alert_level. If features are not yet valid (warmup), returns
            conservative defaults and low confidence.
        """
        rows: List[Dict[str, Any]] = []
        for h in history:
            rows.append(
                {
                    "sensor1_V": float(h["sensor1_V"]),
                    "sensor2_V": float(h["sensor2_V"]),
                }
            )
        rows.append({"sensor1_V": float(sensor1_V), "sensor2_V": float(sensor2_V)})

        n = len(rows)
        df = pd.DataFrame(rows)
        df["scenario_id"] = 1
        df["time_s"] = np.arange(n, dtype=float) / 160.0
        df["leak_present"] = 0
        df["leak_id"] = 0

        X, _, _ = engineer_features(df, drop_invalid=False)
        last = X.iloc[-1]
        if last.isna().any():
            return {
                "leak_probability": 0.5,
                "leak_detected": False,
                "confidence": "low",
                "alert_level": "WARNING",
            }

        vec = last[self.feature_names].values.astype(np.float64).reshape(1, -1)
        p = float(_positive_proba(self._model, vec)[0])
        detected = p >= 0.5
        return {
            "leak_probability": p,
            "leak_detected": bool(detected),
            "confidence": _confidence_label(p),
            "alert_level": _alert_level(p),
        }

    def predict_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Batch inference on a dataframe with sensor columns and scenario_id.

        Args:
            df: Columns must include sensor1_V, sensor2_V, time_s, scenario_id.

        Returns:
            Copy of df with columns leak_probability, leak_detected, confidence,
            alert_level.
        """
        required = {"sensor1_V", "sensor2_V", "time_s", "scenario_id"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"predict_batch missing columns: {missing}")

        work = df.copy()
        if "leak_present" not in work.columns:
            work["leak_present"] = 0
        if "leak_id" not in work.columns:
            work["leak_id"] = 0

        X, _, _ = engineer_features(work, drop_invalid=False)
        probs = pd.Series(np.nan, index=df.index, dtype=float)
        mask = np.isfinite(X.values).all(axis=1)
        if mask.any():
            probs.loc[X.index[mask]] = _positive_proba(
                self._model, X.loc[mask].values.astype(np.float64)
            )

        out = df.copy()
        out["leak_probability"] = probs.values
        out["leak_detected"] = (out["leak_probability"] >= 0.5) & out[
            "leak_probability"
        ].notna()
        out["confidence"] = out["leak_probability"].apply(
            lambda x: _confidence_label(float(x)) if np.isfinite(x) else "low"
        )
        out["alert_level"] = out["leak_probability"].apply(
            lambda x: _alert_level(float(x)) if np.isfinite(x) else "WARNING"
        )
        return out


if __name__ == "__main__":
    data_path = _ROOT / "data" / "pipeguard_synthetic_sensor_data_160Hz.csv"
    raw = pd.read_csv(data_path)
    pred = PipeGuardPredictor()
    batch = pred.predict_batch(raw)
    sample = batch[
        ["scenario_id", "time_s", "leak_probability", "leak_detected", "alert_level"]
    ].iloc[:: max(1, len(batch) // 20)]
    print("PipeGuard batch demo (stratified sample of rows):")
    print(sample.to_string(index=False))
    if "leak_present" in raw.columns:
        m = batch.loc[batch["leak_probability"].notna()]
        y = raw.loc[m.index, "leak_present"]
        acc = float((m["leak_detected"].astype(int) == y.astype(int)).mean())
        print(f"\nAccuracy on valid feature rows (batch): {acc:.4f}")
