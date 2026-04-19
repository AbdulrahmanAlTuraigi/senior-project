"""
Train and select the best PipeGuard leak-detection model using GroupKFold CV.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from scipy.special import expit
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    fbeta_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from tqdm import tqdm
from xgboost import XGBClassifier

# Ensure package root on path for imports when run as script
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.features import engineer_features  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Parallelism for tree / boosting libs (major speedup on multi-core CPUs)
_N_JOBS = int(os.environ.get("PIPEGUARD_N_JOBS", "-1"))
# RBF SVC is O(n²)–O(n³); subsample large train folds to cap fit time (stratified).
_SVC_MAX_TRAIN = int(os.environ.get("PIPEGUARD_SVC_MAX_TRAIN", "2800"))


class IsolationForestLeakPipeline(BaseEstimator, ClassifierMixin):
    """
    Scaler + IsolationForest with probability-like scores for leak (positive class).

    Uses decision_function: lower values indicate stronger outliers (leaks).
    """

    def __init__(self, contamination: float = 0.09, random_state: int = 42) -> None:
        self.contamination = contamination
        self.random_state = random_state

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> IsolationForestLeakPipeline:
        self.pipeline_ = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    IsolationForest(
                        contamination=self.contamination,
                        random_state=self.random_state,
                        n_jobs=_N_JOBS,
                    ),
                ),
            ]
        )
        self.pipeline_.fit(X)
        self.classes_ = np.array([0, 1], dtype=int)
        self.n_features_in_ = X.shape[1]
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        Xs = self.pipeline_.named_steps["scaler"].transform(X)
        raw = self.pipeline_.named_steps["clf"].predict(Xs)
        return (raw == -1).astype(int)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        Xs = self.pipeline_.named_steps["scaler"].transform(X)
        clf = self.pipeline_.named_steps["clf"]
        decision = clf.decision_function(Xs)
        leak_proba = expit(-decision)
        return np.column_stack([1.0 - leak_proba, leak_proba])


def _hist_gradient_boosting() -> HistGradientBoostingClassifier:
    """
    Build HistGradientBoostingClassifier with params compatible with older sklearn.

    ``max_samples`` exists only in newer scikit-learn; omit it when unsupported.
    """
    kwargs: Dict[str, Any] = dict(
        max_iter=200,
        max_depth=4,
        learning_rate=0.05,
        random_state=42,
        class_weight="balanced",
    )
    if "max_samples" in inspect.signature(HistGradientBoostingClassifier.__init__).parameters:
        kwargs["max_samples"] = 0.8
    return HistGradientBoostingClassifier(**kwargs)


def _build_models() -> Dict[str, Any]:
    """
    Return model name -> unfitted estimator (exact keys required).

    Note: ``gradient_boosting`` uses ``HistGradientBoostingClassifier`` (sklearn's
    fast histogram implementation) with the same depth/learning-rate intent as
    classic ``GradientBoostingClassifier`` — classic GB is single-threaded and
    often dominates wall time on this dataset size.
    """
    xgb_kwargs: Dict[str, Any] = dict(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=10,
        random_state=42,
        n_jobs=_N_JOBS,
        tree_method="hist",
    )
    try:
        xgb = XGBClassifier(**xgb_kwargs, eval_metric="logloss")
    except TypeError:
        xgb = XGBClassifier(**xgb_kwargs, eval_metric="logloss", use_label_encoder=False)

    return {
        "logistic_regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=1000,
                        C=0.1,
                        solver="saga",
                        n_jobs=_N_JOBS,
                    ),
                ),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            max_depth=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=_N_JOBS,
        ),
        "gradient_boosting": _hist_gradient_boosting(),
        "xgboost": xgb,
        "lightgbm": LGBMClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            class_weight="balanced",
            random_state=42,
            verbose=-1,
            n_jobs=_N_JOBS,
        ),
        "svm": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "svm",
                    SVC(
                        kernel="rbf",
                        class_weight="balanced",
                        probability=False,
                        C=1.0,
                        gamma="scale",
                        cache_size=2000,
                    ),
                ),
            ]
        ),
        "isolation_forest_ensemble": IsolationForestLeakPipeline(
            contamination=0.09,
            random_state=42,
        ),
    }


def _positive_proba(model: Any, X: np.ndarray) -> np.ndarray:
    """
    Return a score in (0, 1) for the positive (leak) class.

    Uses predict_proba when available; otherwise maps decision_function through
    a sigmoid (avoids SVC's slow internal Platt CV from probability=True).
    """
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        return np.asarray(proba[:, 1], dtype=np.float64)
    if hasattr(model, "decision_function"):
        df = model.decision_function(X)
        return expit(np.asarray(df, dtype=np.float64).ravel())
    raise AttributeError("Model has neither predict_proba nor decision_function")


def _fit_model(model: Any, X: np.ndarray, y: np.ndarray) -> Any:
    """
    Fit model; IsolationForest ignores labels (unsupervised).

    RBF SVM subsamples large training folds (see PIPEGUARD_SVC_MAX_TRAIN) so CV
    does not spend minutes per fold on kernel matrix work.
    """
    m = clone(model)
    if isinstance(m, IsolationForestLeakPipeline):
        m.fit(X)
        return m

    X_fit, y_fit = X, y
    if isinstance(m, Pipeline) and "svm" in m.named_steps and _SVC_MAX_TRAIN > 0:
        n = X_fit.shape[0]
        if n > _SVC_MAX_TRAIN:
            idx = np.arange(n)
            try:
                idx_sub, _ = train_test_split(
                    idx,
                    train_size=_SVC_MAX_TRAIN,
                    stratify=y_fit,
                    random_state=42,
                )
            except ValueError:
                rng = np.random.RandomState(42)
                idx_sub = rng.choice(idx, size=_SVC_MAX_TRAIN, replace=False)
            X_fit, y_fit = X_fit[idx_sub], y_fit[idx_sub]
            logger.info(
                "SVM: stratified subsample for fit %d → %d rows (PIPEGUARD_SVC_MAX_TRAIN=%d)",
                n,
                len(X_fit),
                _SVC_MAX_TRAIN,
            )

    m.fit(X_fit, y_fit)
    return m


@dataclass
class FoldMetrics:
    accuracy: float
    roc_auc: float
    precision: float
    recall: float
    f1: float
    f2: float
    pr_auc: float
    confusion: np.ndarray
    infer_ms_per_sample: float


@dataclass
class ModelCvResult:
    name: str
    fold_metrics: List[FoldMetrics] = field(default_factory=list)

    def mean_roc_auc(self) -> float:
        return float(np.mean([f.roc_auc for f in self.fold_metrics]))

    def mean_pr_auc(self) -> float:
        return float(np.mean([f.pr_auc for f in self.fold_metrics]))

    def mean_f2(self) -> float:
        return float(np.mean([f.f2 for f in self.fold_metrics]))

    def mean_precision(self) -> float:
        return float(np.mean([f.precision for f in self.fold_metrics]))

    def mean_recall(self) -> float:
        return float(np.mean([f.recall for f in self.fold_metrics]))

    def mean_f1(self) -> float:
        return float(np.mean([f.f1 for f in self.fold_metrics]))

    def mean_accuracy(self) -> float:
        return float(np.mean([f.accuracy for f in self.fold_metrics]))

    def mean_infer_ms(self) -> float:
        return float(np.mean([f.infer_ms_per_sample for f in self.fold_metrics]))


def _evaluate_fold(
    model: Any,
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_te: np.ndarray,
    y_te: np.ndarray,
) -> Tuple[Any, FoldMetrics]:
    """Fit on train, score on test, measure inference time."""
    fitted = _fit_model(model, X_tr, y_tr)
    y_score = _positive_proba(fitted, X_te)

    roc = roc_auc_score(y_te, y_score)
    pr_auc = average_precision_score(y_te, y_score)
    y_pred = (y_score >= 0.5).astype(int)
    acc = accuracy_score(y_te, y_pred)
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_te, y_pred, average="binary", pos_label=1, zero_division=0
    )
    f2 = fbeta_score(y_te, y_pred, beta=2, pos_label=1, zero_division=0)
    cm = confusion_matrix(y_te, y_pred, labels=[0, 1])

    n_te = X_te.shape[0]
    t0 = time.perf_counter()
    _ = _positive_proba(fitted, X_te)
    t1 = time.perf_counter()
    infer_ms = (t1 - t0) * 1000.0 / max(n_te, 1)

    metrics = FoldMetrics(
        accuracy=float(acc),
        roc_auc=float(roc),
        precision=float(prec),
        recall=float(rec),
        f1=float(f1),
        f2=float(f2),
        pr_auc=float(pr_auc),
        confusion=cm,
        infer_ms_per_sample=float(infer_ms),
    )
    return fitted, metrics


def run_group_cv(
    X: pd.DataFrame,
    y: pd.Series,
    groups: pd.Series,
    models: Mapping[str, Any],
    n_splits: int = 3,
) -> Dict[str, ModelCvResult]:
    """
    Run GroupKFold cross-validation for each model.

    Args:
        X: Feature matrix.
        y: Binary labels.
        groups: Group id per row (scenario_id).
        models: Mapping of model name to estimator.
        n_splits: Number of CV folds (must be <= number of groups).

    Returns:
        Dict mapping model name to ModelCvResult with per-fold metrics.
    """
    gkf = GroupKFold(n_splits=n_splits)
    results: Dict[str, ModelCvResult] = {name: ModelCvResult(name=name) for name in models}

    X_np = X.values.astype(np.float64)
    y_np = y.values.astype(int)
    g_np = groups.values

    for name, est in tqdm(models.items(), desc="Models", unit="model"):
        t_model = time.perf_counter()
        logger.info("Cross-validating model: %s", name)
        for tr_idx, te_idx in gkf.split(X_np, y_np, g_np):
            X_tr, X_te = X_np[tr_idx], X_np[te_idx]
            y_tr, y_te = y_np[tr_idx], y_np[te_idx]
            _, fold_metrics = _evaluate_fold(est, X_tr, y_tr, X_te, y_te)
            results[name].fold_metrics.append(fold_metrics)
        elapsed = time.perf_counter() - t_model
        logger.info("Model %s completed in %.1f s (3 folds)", name, elapsed)

    return results


def select_winner(
    cv_results: Mapping[str, ModelCvResult],
) -> Tuple[str, ModelCvResult]:
    """
    Select best model: maximize mean F2, then PR-AUC, then minimize inference time.

    Args:
        cv_results: Output of run_group_cv.

    Returns:
        Tuple of (winner_name, winner_result).
    """
    ranked = sorted(
        cv_results.items(),
        key=lambda kv: (
            -kv[1].mean_f2(),
            -kv[1].mean_pr_auc(),
            kv[1].mean_infer_ms(),
        ),
    )
    best_name, best_res = ranked[0]
    return best_name, best_res


def _print_leaderboard(cv_results: Mapping[str, ModelCvResult]) -> None:
    """Print formatted leaderboard to console."""
    rows = sorted(
        cv_results.items(),
        key=lambda kv: (
            -kv[1].mean_f2(),
            -kv[1].mean_pr_auc(),
            kv[1].mean_infer_ms(),
        ),
    )
    lines = [
        "╔══════════════════════════════════════════════════════╗",
        "║           PipeGuard Model Selection Report           ║",
        "╠══════════════════════════════════════════════════════╣",
        "║ Model               F2     PR-AUC  ROC-AUC  Time(ms) ║",
        "║ ─────────────────── ────── ─────── ──────── ──────── ║",
    ]
    for name, res in rows:
        f2 = res.mean_f2()
        pr = res.mean_pr_auc()
        roc = res.mean_roc_auc()
        tms = res.mean_infer_ms()
        lines.append(
            f"║ {name:<19} {f2:.3f}  {pr:.3f}   {roc:.3f}    {tms:<8.1f} ║"
        )
    win_name, win_res = rows[0]
    lines.extend(
        [
            "╠══════════════════════════════════════════════════════╣",
            f"║ WINNER: {win_name}  (F2={win_res.mean_f2():.3f}, PR-AUC={win_res.mean_pr_auc():.3f}){' ' * max(0, 15 - len(win_name))}║",
            "║ Saved to: models/best_model.pkl                      ║",
            "╚══════════════════════════════════════════════════════╝",
        ]
    )
    print("\n" + "\n".join(lines) + "\n")


def main() -> None:
    """Load data, engineer features, CV all models, save best model and metadata."""
    logger.info(
        "Perf: gradient_boosting uses fast HistGradientBoostingClassifier; "
        "SVM train rows capped at %d (set PIPEGUARD_SVC_MAX_TRAIN=0 to disable). "
        "Parallel jobs: PIPEGUARD_N_JOBS=%s",
        _SVC_MAX_TRAIN,
        os.environ.get("PIPEGUARD_N_JOBS", "-1"),
    )
    data_path = _ROOT / "data" / "pipeguard_synthetic_sensor_data_160Hz.csv"
    logger.info("Loading data from %s", data_path)
    raw = pd.read_csv(data_path)

    X, y, groups = engineer_features(raw)
    feature_names = list(X.columns)
    logger.info("Features: %d, samples: %d", len(feature_names), len(X))

    models = _build_models()
    cv_results = run_group_cv(X, y, groups, models, n_splits=3)

    _print_leaderboard(cv_results)

    winner_name, winner_res = select_winner(cv_results)
    logger.info(
        "Winner: %s — mean F2=%.4f, mean PR-AUC=%.4f, mean ROC-AUC=%.4f",
        winner_name,
        winner_res.mean_f2(),
        winner_res.mean_pr_auc(),
        winner_res.mean_roc_auc(),
    )

    reports_dir = _ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    comparison_rows: List[Dict[str, Any]] = []
    for name, res in cv_results.items():
        comparison_rows.append(
            {
                "model": name,
                "accuracy_mean": res.mean_accuracy(),
                "f2_mean": res.mean_f2(),
                "pr_auc_mean": res.mean_pr_auc(),
                "roc_auc_mean": res.mean_roc_auc(),
                "precision_mean": res.mean_precision(),
                "recall_mean": res.mean_recall(),
                "f1_mean": res.mean_f1(),
                "infer_ms_per_sample_mean": res.mean_infer_ms(),
            }
        )
    pd.DataFrame(comparison_rows).to_csv(reports_dir / "model_comparison.csv", index=False)
    logger.info("Wrote %s", reports_dir / "model_comparison.csv")

    models_dir = _ROOT / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    best_estimator = _build_models()[winner_name]
    final_model = _fit_model(best_estimator, X.values.astype(np.float64), y.values.astype(int))

    best_path = models_dir / "best_model.pkl"
    joblib.dump(
        {
            "model": final_model,
            "feature_names": feature_names,
            "model_name": winner_name,
        },
        best_path,
    )
    logger.info("Saved model to %s", best_path)

    meta = {
        "model_name": winner_name,
        "f2_score": winner_res.mean_f2(),
        "pr_auc": winner_res.mean_pr_auc(),
        "roc_auc": winner_res.mean_roc_auc(),
        "feature_names": feature_names,
        "trained_on_scenarios": sorted(int(x) for x in groups.unique()),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = models_dir / "best_model_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    logger.info("Saved metadata to %s", meta_path)

    print("\n--- Summary ---")
    print(f"Winner: {winner_name}")
    print(f"F2 score (mean CV): {winner_res.mean_f2():.4f}")
    print(f"PR-AUC (mean CV): {winner_res.mean_pr_auc():.4f}")
    print(f"ROC-AUC (mean CV): {winner_res.mean_roc_auc():.4f}")
    print(f"Model file: {best_path}")
    print(f"Metadata: {meta_path}\n")


if __name__ == "__main__":
    main()
