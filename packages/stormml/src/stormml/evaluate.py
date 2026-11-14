"""Screening models (baselines + ML) and split evaluation with paired cluster-bootstrap CIs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import metrics as M
from .datagen import LABEL_NAMES, Dataset
from .splits import Split

MIN_PRECISIONS = (0.8, 0.9)
TOP_K = (5, 10)
TOP_FRAC = 0.10
OOF_FOLDS = 3


@dataclass
class FeatureScore:
    """Transparent baseline: rank contingencies by one pre-contingency feature."""

    name: str
    feature: str
    description: str
    fixed_threshold: float | None = None
    kind: str = "baseline"
    probabilistic: bool = False
    threshold: float = float("nan")

    def fit(self, X, y, groups, names):
        self._col = names.index(self.feature)
        self.threshold = (
            self.fixed_threshold
            if self.fixed_threshold is not None
            else M.best_f1_threshold(y, X[:, self._col])
        )
        return self

    def score(self, X):
        return X[:, self._col]


@dataclass
class SkModel:
    name: str
    description: str
    factory: object  # () -> sklearn estimator
    kind: str = "ml"
    probabilistic: bool = True
    threshold: float = float("nan")
    est: object = field(default=None, repr=False)

    def fit(self, X, y, groups, names):
        # Threshold from out-of-fold predictions (grouped by operating point) to avoid tuning on
        # in-sample scores.
        oof = np.zeros(y.size)
        for tr, va in GroupKFold(n_splits=OOF_FOLDS).split(X, y, groups):
            oof[va] = self.factory().fit(X[tr], y[tr]).predict_proba(X[va])[:, 1]
        self.threshold = M.best_f1_threshold(y, oof)
        self.est = self.factory().fit(X, y)
        return self

    def score(self, X):
        return self.est.predict_proba(X)[:, 1]


def make_models() -> list:
    return [
        FeatureScore(
            "dc_lodf_rule",
            "dc_score",
            "DC-LODF screening on base AC P-flows: flag if attributable estimated loading > 100 %",
            fixed_threshold=100.0,
        ),
        FeatureScore(
            "dc_lodf_tuned",
            "dc_score",
            "Same DC-LODF score, flag threshold tuned for F1 on the training split",
        ),
        FeatureScore(
            "pre_loading",
            "pre_load",
            "Pre-contingency AC loading of the outaged branch; threshold tuned for F1 on train",
        ),
        SkModel(
            "logreg",
            "StandardScaler + LogisticRegression(C=1, lbfgs)",
            lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=5000)),
        ),
        SkModel(
            "gboost",
            "HistGradientBoostingClassifier(max_iter=300, lr=0.05, max_leaf_nodes=31, seed 0)",
            lambda: HistGradientBoostingClassifier(
                max_iter=300, learning_rate=0.05, max_leaf_nodes=31, early_stopping=False,
                random_state=0,
            ),
        ),
    ]


def _topk_flags(s: np.ndarray, groups: np.ndarray) -> dict[str, np.ndarray]:
    r = M.ranks_within_groups(s, groups)
    _, inv, counts = np.unique(groups, return_inverse=True, return_counts=True)
    kfrac = np.ceil(TOP_FRAC * counts[inv]).astype(int)
    out = {f"recall_at_{k}": r < k for k in TOP_K}
    out[f"recall_at_{int(TOP_FRAC * 100)}pct"] = r < kfrac
    return out


def _point_metrics(y, s, pred, flags) -> dict:
    d = {"pr_auc": M.pr_auc(y, s), "roc_auc": M.roc_auc(y, s)}
    for p in MIN_PRECISIONS:
        d[f"recall_at_precision_{p}"] = M.recall_at_precision(y, s, p)
    for k, fl in flags.items():
        d[k] = float(y[fl].sum() / y.sum()) if y.sum() else float("nan")
    d["at_threshold"] = M.precision_recall_at(y, pred)
    return d


BOOT_METRICS = ("pr_auc", "roc_auc", "recall_at_precision_0.9", "recall_at_10", "f1")


def _boot_values(y, s, pred, flag10, idx) -> dict[str, float]:
    yy, ss, pp = y[idx], s[idx], pred[idx]
    pos = yy.sum()
    tp = float((pp & (yy == 1)).sum())
    fp = float((pp & (yy == 0)).sum())
    return {
        "pr_auc": M.pr_auc(yy, ss),
        "roc_auc": M.roc_auc(yy, ss),
        "recall_at_precision_0.9": M.recall_at_precision(yy, ss, 0.9),
        "recall_at_10": float(yy[flag10[idx]].sum() / pos) if pos else float("nan"),
        "f1": 2 * tp / (2 * tp + fp + (pos - tp)) if pos + fp else float("nan"),
    }


def evaluate_split(
    ds: Dataset,
    split: Split,
    target: str,
    ac_seconds_per_op: dict[str, float],
    feature_seconds_per_op: dict[str, float],
    n_boot: int,
    boot_seed: int,
) -> dict:
    names = list(ds.feature_names)
    ycol = LABEL_NAMES.index(target)
    nonconv = ds.y[:, LABEL_NAMES.index("nonconv")].astype(bool)
    train, test = split.train, split.test
    excluded = 0
    if target == "thermal":
        # Non-converged contingencies carry no thermal information: excluded from this target.
        excluded = int(nonconv[test].sum() + nonconv[train].sum())
        train, test = train[~nonconv[train]], test[~nonconv[test]]
    Xtr, ytr, gtr = ds.X[train], ds.y[train, ycol].astype(int), ds.op_id[train]
    Xte, yte, gte = ds.X[test], ds.y[test, ycol].astype(int), ds.op_id[test]
    n_ops_te = np.unique(gte).size
    boots = M.cluster_bootstrap_indices(gte, n_boot, boot_seed)

    out_models = {}
    boot_vals: dict[str, dict[str, np.ndarray]] = {}
    for model in make_models():
        t0 = time.perf_counter()
        model.fit(Xtr, ytr, gtr, names)
        fit_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        s = model.score(Xte)
        pred_s = time.perf_counter() - t0
        strict = getattr(model, "fixed_threshold", None) is not None  # DC rule: "> 100 %"
        pred = s > model.threshold if strict else s >= model.threshold
        flags = _topk_flags(s, gte)
        pm = _point_metrics(yte, s, pred, flags)
        bv = [_boot_values(yte, s, pred, flags["recall_at_10"], idx) for idx in boots]
        boot_vals[model.name] = {k: np.array([b[k] for b in bv]) for k in BOOT_METRICS}
        pm["ci95"] = {k: M.percentile_ci(boot_vals[model.name][k]) for k in BOOT_METRICS}
        by_type = {}
        for t in ("thermal", "voltage", "nonconv"):
            sel = ds.y[test, LABEL_NAMES.index(t)].astype(bool)
            by_type[t] = {
                "positives": int(sel.sum()),
                "recall_at_threshold": float(pred[sel].mean()) if sel.any() else float("nan"),
            }
        pm["recall_by_violation_type"] = by_type
        nets = {}
        for net in np.unique(ds.network[test]):
            sel = ds.network[test] == net
            nets[str(net)] = {
                "rows": int(sel.sum()),
                "positives": int(yte[sel].sum()),
                "pr_auc": M.pr_auc(yte[sel], s[sel]),
                "recall_at_10": float(yte[sel][flags["recall_at_10"][sel]].sum() / yte[sel].sum())
                if yte[sel].sum()
                else float("nan"),
            }
        pm["by_network"] = nets
        if model.probabilistic:
            pm["calibration"] = {"brier": M.brier(yte, s), **M.calibration_bins(yte, s)}
        pm["threshold"] = float(model.threshold)
        pm["threshold_source"] = (
            "fixed" if getattr(model, "fixed_threshold", None) is not None
            else ("train out-of-fold F1" if model.kind == "ml" else "train F1")
        )
        pm["fit_seconds"] = fit_s
        pm["score_seconds_per_operating_point"] = pred_s / n_ops_te
        pm["kind"] = model.kind
        pm["description"] = model.description
        if model.name == "logreg":
            lr = model.est[-1]
            pm["standardized_coefficients"] = dict(
                sorted(zip(names, lr.coef_[0].tolist(), strict=True), key=lambda kv: -abs(kv[1]))
            )
        out_models[model.name] = pm

    # Paired ML-minus-baseline differences on the same operating-point resamples, against the DC
    # score (tuned threshold; the ranking metrics are identical for both DC variants) and against
    # the pre-loading heuristic.
    diffs = {}
    for ml in ("logreg", "gboost"):
        for base in ("dc_lodf_tuned", "pre_loading"):
            d = {}
            for k in BOOT_METRICS:
                delta = boot_vals[ml][k] - boot_vals[base][k]
                point = (
                    out_models[ml]["at_threshold"]["f1"] - out_models[base]["at_threshold"]["f1"]
                    if k == "f1" else out_models[ml][k] - out_models[base][k]
                )
                lo, hi = M.percentile_ci(delta)
                d[k] = {"diff": point, "ci95": [lo, hi]}
            diffs[f"{ml}-minus-{base}"] = d

    nets_te = sorted(set(ds.network[test].tolist()))
    ac = float(np.mean([ac_seconds_per_op[n] for n in nets_te]))
    feat = float(np.mean([feature_seconds_per_op[n] for n in nets_te]))
    return {
        "split": split.name,
        "target": target,
        "train": {"rows": int(train.size), "operating_points": int(np.unique(gtr).size),
                  "positives": int(ytr.sum()), "networks": sorted(set(ds.network[train].tolist()))},
        "test": {"rows": int(test.size), "operating_points": int(n_ops_te),
                 "positives": int(yte.sum()), "networks": nets_te},
        "excluded_nonconverged_rows": excluded,
        "bootstrap": {"unit": "operating point", "n_boot": n_boot, "seed": boot_seed,
                      "ci": "percentile 95 %"},
        "models": out_models,
        "paired_differences": diffs,
        "runtime": {
            "ac_n1_seconds_per_operating_point_mean": ac,
            "feature_seconds_per_operating_point_mean": feat,
            "note": "AC N-1 = sequential pandapower runpp per contingency (numba, 1 thread); "
                    "screening = feature extraction from the solved base case + model scoring.",
        },
    }
