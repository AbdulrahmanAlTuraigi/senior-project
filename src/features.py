"""
Feature engineering for PipeGuard leak detection.

All rolling statistics use only past observations (shift before rolling),
computed per scenario_id to avoid cross-scenario leakage.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ROLLING_WINDOWS = (16, 32, 80, 160)


def _engineer_features_for_group(
    group: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute features for a single scenario (one pipeline run).

    Args:
        group: Sub-dataframe with columns sensor1_V, sensor2_V (and index aligned).

    Returns:
        DataFrame of engineered features with same index as group.
    """
    s1 = group["sensor1_V"].astype(float)
    s2 = group["sensor2_V"].astype(float)
    dP = s1 - s2
    abs_dP = dP.abs()
    dP_squared = dP**2

    out: dict[str, pd.Series] = {
        "dP": dP,
        "abs_dP": abs_dP,
        "dP_squared": dP_squared,
    }

    for w in ROLLING_WINDOWS:
        shifted_dp = dP.shift(1)
        shifted_abs = abs_dP.shift(1)
        shifted_sq = dP_squared.shift(1)
        out[f"dP_mean_{w}"] = shifted_dp.rolling(window=w, min_periods=w).mean()
        out[f"dP_std_{w}"] = shifted_dp.rolling(window=w, min_periods=w).std()
        out[f"dP_max_{w}"] = shifted_abs.rolling(window=w, min_periods=w).max()
        out[f"dP_energy_{w}"] = shifted_sq.rolling(window=w, min_periods=w).sum()
        out[f"s1_std_{w}"] = (
            s1.shift(1).rolling(window=w, min_periods=w).std()
        )
        out[f"s2_std_{w}"] = (
            s2.shift(1).rolling(window=w, min_periods=w).std()
        )

    out["dP_diff1"] = dP.diff(1)
    out["dP_diff8"] = dP.diff(8)
    out["dP_diff16"] = dP.diff(16)
    out["s1_diff1"] = s1.diff(1)
    out["s2_diff1"] = s2.diff(1)

    baseline_mean = dP.shift(1).rolling(window=160, min_periods=160).mean()
    baseline_std = dP.shift(1).rolling(window=160, min_periods=160).std()
    out["dP_zscore"] = (dP - baseline_mean) / (baseline_std + 1e-8)
    out["abs_zscore"] = out["dP_zscore"].abs()

    ratio_s1_s2 = s1 / (s2 + 1e-8)
    out["ratio_s1_s2"] = ratio_s1_s2
    out["log_ratio"] = np.log(ratio_s1_s2 + 1e-8)

    return pd.DataFrame(out, index=group.index)


def engineer_features(
    df: pd.DataFrame,
    drop_invalid: bool = True,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Build feature matrix from raw sensor data.

    Args:
        df: Raw data with columns scenario_id, sensor1_V, sensor2_V,
            and optionally time_s, leak_present, leak_id.
        drop_invalid: If True, drop rows with any feature NaN (training).
            If False, keep all rows (NaN for warmup) for batch inference alignment.

    Returns:
        Tuple of (X, y, groups) where X is features, y is leak_present,
        and groups is scenario_id for GroupKFold.
    """
    required = {"scenario_id", "sensor1_V", "sensor2_V", "leak_present"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    logger.info("Engineering features per scenario_id (no cross-scenario leakage).")
    work = df.copy()
    work["_row_id"] = np.arange(len(work), dtype=int)

    parts: list[pd.DataFrame] = []

    for sid, grp in work.groupby("scenario_id", sort=False):
        row_ids = grp["_row_id"].values
        sub = grp.drop(columns=["_row_id"])
        feat = _engineer_features_for_group(sub)
        feat.insert(0, "scenario_id", sid)
        feat["_row_id"] = row_ids
        parts.append(feat)

    X_full = pd.concat(parts, axis=0).sort_values("_row_id")
    y = work.loc[X_full.index, "leak_present"].astype(int)
    groups = work.loc[X_full.index, "scenario_id"].astype(int)
    X_full = X_full.drop(columns=["_row_id"])

    feature_cols = [c for c in X_full.columns if c != "scenario_id"]
    X = X_full[feature_cols].copy()

    if not drop_invalid:
        return X, y, groups

    before = len(X)
    mask = X.notna().all(axis=1) & y.notna()
    X = X.loc[mask]
    y = y.loc[mask]
    groups = groups.loc[mask]
    dropped = before - len(X)
    logger.info("Dropped %d rows with NaN after rolling windows (kept %d).", dropped, len(X))

    return X, y, groups


def get_feature_column_names() -> list[str]:
    """
    Return ordered list of feature column names (without scenario_id).

    Returns:
        List of feature names matching engineer_features output order.
    """
    base = ["dP", "abs_dP", "dP_squared"]
    for w in ROLLING_WINDOWS:
        base.extend(
            [
                f"dP_mean_{w}",
                f"dP_std_{w}",
                f"dP_max_{w}",
                f"dP_energy_{w}",
                f"s1_std_{w}",
                f"s2_std_{w}",
            ]
        )
    base.extend(
        [
            "dP_diff1",
            "dP_diff8",
            "dP_diff16",
            "s1_diff1",
            "s2_diff1",
            "dP_zscore",
            "abs_zscore",
            "ratio_s1_s2",
            "log_ratio",
        ]
    )
    return base
