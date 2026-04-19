"""
Generate evaluation plots, model comparison artifacts, and HTML report.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from jinja2 import Template
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GroupKFold

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.features import engineer_features  # noqa: E402
from src.train import _build_models, _fit_model, _positive_proba  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _oof_predictions(
    X: pd.DataFrame,
    y: pd.Series,
    groups: pd.Series,
    models: Dict[str, Any],
    n_splits: int = 3,
) -> Tuple[Dict[str, np.ndarray], np.ndarray]:
    """
    Out-of-fold positive-class probabilities for each model.

    Args:
        X: Feature matrix.
        y: Labels.
        groups: Group labels for GroupKFold.
        models: Model name to unfitted estimator.
        n_splits: CV folds.

    Returns:
        Tuple of (oof_proba_dict, y_true aligned to rows).
    """
    gkf = GroupKFold(n_splits=n_splits)
    X_np = X.values.astype(np.float64)
    y_np = y.values.astype(int)
    g_np = groups.values
    n = len(y_np)
    oof: Dict[str, np.ndarray] = {name: np.full(n, np.nan) for name in models}

    for tr_idx, te_idx in gkf.split(X_np, y_np, g_np):
        X_tr, X_te = X_np[tr_idx], X_np[te_idx]
        y_tr = y_np[tr_idx]
        for name, est in models.items():
            fitted = _fit_model(est, X_tr, y_tr)
            oof[name][te_idx] = _positive_proba(fitted, X_te)

    return oof, y_np


def _fig_to_base64(fig: plt.Figure) -> str:
    """Encode matplotlib figure as PNG base64 string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _plot_roc_curves(
    oof: Dict[str, np.ndarray],
    y_true: np.ndarray,
    out_path: Path,
) -> str:
    """
    Plot ROC curves for all models.

    Args:
        oof: Model name to OOF probabilities.
        y_true: Ground truth labels.
        out_path: Path to save PNG.

    Returns:
        Base64-encoded PNG.
    """
    fig, ax = plt.subplots(figsize=(9, 7))
    for name, scores in sorted(oof.items()):
        auc = roc_auc_score(y_true, scores)
        fpr, tpr, _ = roc_curve(y_true, scores)
        ax.plot(fpr, tpr, label=f"{name} (AUC={auc:.3f})")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.4)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC curves — all models (OOF)")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    b64 = _fig_to_base64(fig)
    return b64


def _plot_pr_curves(
    oof: Dict[str, np.ndarray],
    y_true: np.ndarray,
    out_path: Path,
) -> str:
    """
    Plot Precision-Recall curves for all models.

    Args:
        oof: Model name to OOF probabilities.
        y_true: Ground truth labels.
        out_path: Path to save PNG.

    Returns:
        Base64-encoded PNG.
    """
    fig, ax = plt.subplots(figsize=(9, 7))
    for name, scores in sorted(oof.items()):
        auc = average_precision_score(y_true, scores)
        prec, rec, _ = precision_recall_curve(y_true, scores)
        ax.plot(rec, prec, label=f"{name} (PR-AUC={auc:.3f})")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall curves — all models (OOF)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    b64 = _fig_to_base64(fig)
    return b64


def _plot_confusion_matrices(
    oof: Dict[str, np.ndarray],
    y_true: np.ndarray,
    out_path: Path,
) -> str:
    """
    Plot confusion matrix heatmaps (one subplot per model).

    Args:
        oof: Model name to OOF probabilities.
        y_true: Ground truth labels.
        out_path: Path to save PNG.

    Returns:
        Base64-encoded PNG.
    """
    names = sorted(oof.keys())
    n = len(names)
    ncols = 3
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.5 * nrows))
    axes_flat = np.atleast_1d(axes).ravel()
    for i, name in enumerate(names):
        y_pred = (oof[name] >= 0.5).astype(int)
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=[0, 1])
        disp.plot(ax=axes_flat[i], colorbar=False)
        axes_flat[i].set_title(name, fontsize=9)
    for j in range(len(names), len(axes_flat)):
        axes_flat[j].axis("off")
    fig.suptitle("Confusion matrices (OOF, threshold=0.5)", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    b64 = _fig_to_base64(fig)
    return b64


def _extract_importances(est: Any) -> np.ndarray | None:
    """
    Return feature importances from a tree estimator or pipeline containing one.

    Args:
        est: Fitted estimator.

    Returns:
        Importance vector or None if not available.
    """
    if hasattr(est, "feature_importances_"):
        return np.asarray(est.feature_importances_)
    if hasattr(est, "named_steps"):
        for step in reversed(list(est.named_steps.values())):
            if hasattr(step, "feature_importances_"):
                return np.asarray(step.feature_importances_)
    return None


def _plot_feature_importance(
    est: Any,
    feature_names: List[str],
    out_path: Path,
    title: str = "Feature importance (top 20)",
) -> str:
    """
    Plot horizontal bar chart of top 20 feature importances.

    Args:
        est: Fitted tree-based model.
        feature_names: Names aligned with importances.
        out_path: PNG path.
        title: Plot title.

    Returns:
        Base64-encoded PNG.
    """
    imp = _extract_importances(est)
    if imp is None:
        return ""
    order = np.argsort(imp)[::-1][:20]
    top_names = [feature_names[i] for i in order]
    top_vals = imp[order]

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(range(len(top_names)), top_vals, color="steelblue")
    ax.set_yticks(range(len(top_names)))
    ax.set_yticklabels(top_names)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.set_xlabel("Importance")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    return _fig_to_base64(fig)


def _plot_timeseries_overlay(
    raw: pd.DataFrame,
    proba_by_scenario: Dict[int, np.ndarray],
    out_path: Path,
) -> str:
    """
    Plot sensor1, sensor2, and predicted leak probability per scenario.

    Args:
        raw: Raw dataframe with scenario_id, time_s, sensor1_V, sensor2_V, leak_present.
        proba_by_scenario: scenario_id -> predicted leak probability per row (aligned).
        out_path: PNG path.

    Returns:
        Base64-encoded PNG.
    """
    scenarios = sorted(raw["scenario_id"].unique())
    fig, axes = plt.subplots(len(scenarios), 1, figsize=(12, 4 * len(scenarios)), sharex=False)
    if len(scenarios) == 1:
        axes = [axes]
    for ax, sid in zip(axes, scenarios):
        g = raw.loc[raw["scenario_id"] == sid].sort_values("time_s")
        y = g["leak_present"].values
        t = g["time_s"].values
        p = proba_by_scenario[sid]
        ax.plot(t, g["sensor1_V"], label="sensor1_V", alpha=0.85)
        ax.plot(t, g["sensor2_V"], label="sensor2_V", alpha=0.85)
        ax2 = ax.twinx()
        ax2.plot(t, p, color="crimson", label="P(leak)", linewidth=1.5)
        if y.any():
            leak_mask = y.astype(bool)
            t0, t1 = t[leak_mask][0], t[leak_mask][-1]
            ax.axvspan(t0, t1, color="orange", alpha=0.2, label="true leak window")
        ax.set_ylabel("Voltage (V)")
        ax2.set_ylabel("P(leak)")
        ax.set_title(f"Scenario {sid}")
        lines1, lab1 = ax.get_legend_handles_labels()
        lines2, lab2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, lab1 + lab2, loc="upper right", fontsize=8)
    axes[-1].set_xlabel("time_s")
    fig.suptitle("Sensors and predicted leak probability (best model)", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    return _fig_to_base64(fig)


def _load_leaderboard_html(csv_path: Path) -> str:
    """Render model_comparison.csv as HTML table."""
    df = pd.read_csv(csv_path)
    return df.to_html(index=False, classes="leaderboard", border=0)


def main() -> None:
    """Load data, compute OOF predictions, save plots and HTML report."""
    data_path = _ROOT / "data" / "pipeguard_synthetic_sensor_data_160Hz.csv"
    meta_path = _ROOT / "models" / "best_model_meta.json"
    model_path = _ROOT / "models" / "best_model.pkl"
    reports_dir = _ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(data_path)
    X, y, groups = engineer_features(raw)
    feature_names = list(X.columns)

    models = _build_models()
    logger.info("Computing OOF predictions for all models...")
    oof, y_true = _oof_predictions(X, y, groups, models, n_splits=3)

    def file_b64(p: Path) -> str:
        """Encode existing PNG file as base64."""
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    _plot_roc_curves(oof, y_true, reports_dir / "roc_curves.png")
    _plot_pr_curves(oof, y_true, reports_dir / "pr_curves.png")
    _plot_confusion_matrices(oof, y_true, reports_dir / "confusion_matrices.png")

    b64_roc = file_b64(reports_dir / "roc_curves.png")
    b64_pr = file_b64(reports_dir / "pr_curves.png")
    b64_cm = file_b64(reports_dir / "confusion_matrices.png")

    # Best model from metadata (trained on full data)
    bundle = joblib.load(model_path)
    best_name = bundle["model_name"]
    best_est = bundle["model"]

    # Tree-based: importances from winner if available; else RF on full data
    imp_b64 = ""
    if _extract_importances(best_est) is not None:
        imp_b64 = _plot_feature_importance(
            best_est,
            bundle["feature_names"],
            reports_dir / "feature_importance.png",
            title=f"Feature importance — {best_name} (top 20)",
        )
    else:
        rf = _build_models()["random_forest"]
        rf_fitted = _fit_model(rf, X.values.astype(np.float64), y.values.astype(int))
        imp_b64 = _plot_feature_importance(
            rf_fitted,
            feature_names,
            reports_dir / "feature_importance.png",
            title="Feature importance — RandomForest (top 20, proxy for non-tree winner)",
        )

    # Full-data predictions on full raw frame with drop_invalid=False for alignment
    X_full, _, _ = engineer_features(raw, drop_invalid=False)
    X_full_np = X_full.values.astype(np.float64)
    mask = np.isfinite(X_full_np).all(axis=1)
    proba_series = pd.Series(np.nan, index=raw.index, dtype=float)
    if mask.any():
        proba_series.loc[X_full.index[mask]] = _positive_proba(
            best_est, X_full_np[mask]
        )

    proba_by_scenario: Dict[int, np.ndarray] = {}
    for sid in sorted(raw["scenario_id"].unique()):
        g_idx = raw.index[raw["scenario_id"] == sid]
        proba_by_scenario[sid] = proba_series.loc[g_idx].values

    _plot_timeseries_overlay(raw, proba_by_scenario, reports_dir / "timeseries_overlay.png")
    b64_ts = file_b64(reports_dir / "timeseries_overlay.png")

    csv_path = reports_dir / "model_comparison.csv"
    if not csv_path.exists():
        logger.warning("model_comparison.csv missing — run train.py first")
    leaderboard_html = _load_leaderboard_html(csv_path) if csv_path.exists() else "<p>Run train.py first.</p>"

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    explanation = (
        f"The selected model is <strong>{meta.get('model_name', best_name)}</strong>. "
        "It was chosen by 3-fold GroupKFold cross-validation (grouped by scenario_id) "
        "to maximize mean F2 on the leak class (recall-weighted), then mean PR-AUC, "
        "then inference speed. "
        "Features use only past samples within each scenario (causal rolling windows) "
        "and emphasize differential pressure (sensor1 − sensor2), its dynamics, "
        "and baseline z-scores. "
        "Deploy by streaming new readings through the PipeGuardPredictor "
        "with a rolling history buffer."
    )

    html = Template(
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>PipeGuard Evaluation Report</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 1100px; }
    h1, h2 { color: #1a2b3c; }
    img { max-width: 100%; height: auto; border: 1px solid #ddd; margin: 0.5rem 0; }
    table.leaderboard { border-collapse: collapse; width: 100%; }
    table.leaderboard th, table.leaderboard td { border: 1px solid #ccc; padding: 6px 8px; text-align: right; }
    table.leaderboard th, table.leaderboard td:first-child { text-align: left; }
    .section { margin-bottom: 2rem; }
  </style>
</head>
<body>
  <h1>PipeGuard — Evaluation Report</h1>
  <p>Generated from out-of-fold predictions and saved artifacts.</p>

  <div class="section">
    <h2>Leaderboard (CV means)</h2>
    {{ leaderboard | safe }}
  </div>

  <div class="section">
    <h2>Winning model</h2>
    <p>{{ explanation }}</p>
    <pre>{{ meta_json }}</pre>
  </div>

  <div class="section">
    <h2>ROC curves</h2>
    <img src="data:image/png;base64,{{ b64_roc }}" alt="ROC"/>
  </div>

  <div class="section">
    <h2>Precision–Recall curves</h2>
    <img src="data:image/png;base64,{{ b64_pr }}" alt="PR"/>
  </div>

  <div class="section">
    <h2>Confusion matrices (OOF)</h2>
    <img src="data:image/png;base64,{{ b64_cm }}" alt="Confusion matrices"/>
  </div>

  <div class="section">
    <h2>Feature importance (top 20)</h2>
    <img src="data:image/png;base64,{{ imp_b64 }}" alt="Feature importance"/>
  </div>

  <div class="section">
    <h2>Time series — sensors × P(leak)</h2>
    <img src="data:image/png;base64,{{ b64_ts }}" alt="Time series"/>
  </div>
</body>
</html>
"""
    ).render(
        leaderboard=leaderboard_html,
        explanation=explanation,
        meta_json=json.dumps(meta, indent=2),
        b64_roc=b64_roc,
        b64_pr=b64_pr,
        b64_cm=b64_cm,
        imp_b64=imp_b64,
        b64_ts=b64_ts,
    )

    out_html = reports_dir / "evaluation_report.html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Wrote %s", out_html)


if __name__ == "__main__":
    main()
