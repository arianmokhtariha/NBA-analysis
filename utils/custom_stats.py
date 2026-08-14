"""
Reusable statistical-analysis helpers for exploratory data work.

Companion module to ``custom_plots.py``. That module turns a DataFrame into a
figure; this one turns a DataFrame into a **result table**. Nothing here knows
anything about a particular dataset or domain — drop the file into any project's
``utils/`` folder and import from it.

The contract
------------
Every *test / estimation* function returns a tidy ``pandas.DataFrame`` — one row
per test, per column, or per group. They render cleanly in a notebook, stack
with ``pd.concat``, and export straight into a report. The small *scalar
utilities* (``cohens_d``, ``cliffs_delta``, ``cramers_v``, ``p_adjust``) return
plain floats/arrays instead, because wrapping a single number in a frame helps
nobody.

Shared column vocabulary
------------------------
``test``            name of the test actually run
``n``               observations used (after dropping non-finite values)
``statistic``       the test statistic
``p_value``         two-sided p-value unless ``alternative`` says otherwise
``p_adj``           p-value after multiple-comparison correction
``decision``        ``'reject H₀'`` / ``'fail to reject H₀'`` at ``alpha``
``estimate``        the quantity being compared (e.g. a mean difference)
``ci_low/ci_high``  interval around ``estimate`` (or around ``r``)
``effect_size``     magnitude of the effect, on the scale named by…
``effect_type``     …this column (``hedges_g``, ``cliffs_delta``, …)
``magnitude``       conventional label for that effect size — a rule of thumb
``chosen_because``  why ``test='auto'`` landed on this test
``flags``           caveats that should be read before trusting the row

Conventions and deliberate defaults
-----------------------------------
* Non-finite values (``NaN``, ``±inf``) are dropped per column or per group; for
  paired and correlation functions the deletion is pairwise/listwise and the
  surviving ``n`` is always reported.
* Columns arriving from a database as ``Decimal`` objects (SQL ``numeric``)
  count as numeric even though pandas types them ``object`` — otherwise every
  SQL-computed metric would be silently skipped.
* Two independent groups default to **Welch's** t-test, not Student's. Welch
  costs almost nothing when variances happen to be equal and stays correct when
  they are not, so equal-variance Student is opt-in.
* Multiple comparisons default to **Holm**, not Bonferroni: Holm is uniformly
  more powerful and controls the same family-wise error rate.
* Bootstrap intervals default to **BCa**, which corrects for bias and skew.
* ``magnitude`` labels follow Cohen's conventions. They are folklore calibrated
  on psychology data, not laws of nature — report the number, use the label as
  shorthand only.
"""

from __future__ import annotations

import itertools
import math
import warnings
from typing import Callable, Dict, List, Literal, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import scipy.stats as st


__all__ = [
    # descriptives & assumption checks
    "summary_stats",
    "normality_test",
    "variance_test",
    "outlier_summary",
    "outlier_flags",
    # estimation
    "bootstrap_ci",
    "proportion_ci",
    # group comparison
    "compare_groups",
    "compare_paired",
    "pairwise_comparisons",
    "p_adjust",
    # categorical association
    "association_test",
    "contingency_residuals",
    # correlation
    "correlation_test",
    "partial_correlation",
    # effect sizes
    "cohens_d",
    "cliffs_delta",
    "cramers_v",
]


# ── Shared constants ─────────────────────────────────────────────────────────
_REJECT = "reject H₀"
_KEEP = "fail to reject H₀"

# Conventional effect-size cut-points. Each tuple is (upper bound, label); a
# value at or above the last bound is "large".
_D_LEVELS = ((0.20, "negligible"), (0.50, "small"), (0.80, "medium"))
_DELTA_LEVELS = ((0.147, "negligible"), (0.33, "small"), (0.474, "medium"))
_R_LEVELS = ((0.10, "negligible"), (0.30, "small"), (0.50, "medium"))
_ETA_LEVELS = ((0.01, "negligible"), (0.06, "small"), (0.14, "medium"))

# Shapiro-Wilk is only defined up to 5000 observations in most implementations,
# and its p-value is unreliable beyond that anyway.
_SHAPIRO_MAX_N = 5000

# Group sizes below these get flagged rather than silently trusted.
_TINY_N = 8
_SMALL_N = 20

# BCa needs the statistic to vary across jackknife samples. On heavily tied data
# — a median sitting on a repeated value, say — it cannot be computed, and scipy
# returns NaN with a warning rather than raising. That is surfaced as a flag.
_DEGENERATE_CI = (
    "interval undefined: the statistic barely varies across resamples "
    "(heavy ties) — try method='percentile'"
)

_STAT_FUNCS: Dict[str, Callable[..., np.ndarray]] = {
    "mean": np.mean,
    "median": np.median,
    "std": lambda a, axis=-1: np.std(a, axis=axis, ddof=1),
    "var": lambda a, axis=-1: np.var(a, axis=axis, ddof=1),
    "min": np.min,
    "max": np.max,
    "sum": np.sum,
}


# ══════════════════════════════════════════════════════════════════════════════
# Private helpers
# ══════════════════════════════════════════════════════════════════════════════
def _require_columns(df: pd.DataFrame, names: Sequence[str]) -> None:
    """Raise a clear ``KeyError`` naming every requested column that is absent."""
    missing = [n for n in names if n not in df.columns]
    if missing:
        raise KeyError(
            f"Column(s) not found in dataframe: {missing}. "
            f"Available: {list(df.columns)[:20]}"
        )


def _clean(values: Union[pd.Series, np.ndarray, Sequence[float]]) -> np.ndarray:
    """
    Coerce a 1-D input to ``float64`` and drop every non-finite entry.

    ``NaN``, ``inf`` and ``-inf`` all go: an infinity is never a legitimate
    observation in this kind of analysis, and leaving one in silently poisons
    every downstream mean, variance and rank.
    """
    s = values if isinstance(values, pd.Series) else pd.Series(np.asarray(values))
    arr = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    return arr[np.isfinite(arr)]


def _clean_pair(
    x: Union[pd.Series, np.ndarray],
    y: Union[pd.Series, np.ndarray],
) -> Tuple[np.ndarray, np.ndarray]:
    """Return the two inputs restricted to positions where **both** are finite."""
    xs = x if isinstance(x, pd.Series) else pd.Series(np.asarray(x))
    ys = y if isinstance(y, pd.Series) else pd.Series(np.asarray(y))
    xa = pd.to_numeric(xs, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    ya = pd.to_numeric(ys, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    if len(xa) != len(ya):
        raise ValueError(
            f"Paired inputs must be the same length (got {len(xa)} and {len(ya)})."
        )
    keep = np.isfinite(xa) & np.isfinite(ya)
    return xa[keep], ya[keep]


def _is_numeric_like(s: pd.Series) -> bool:
    """
    True for columns that hold numbers, including ones pandas calls ``object``.

    A database driver hands back SQL ``numeric``/``decimal`` columns as Python
    ``Decimal`` objects, so pandas types them ``object`` and
    ``is_numeric_dtype`` says no — which would silently drop every engineered
    metric in a SQL-backed project. An object column therefore qualifies when
    all of its non-null values convert cleanly to numbers. Booleans never
    qualify: a normality test or an IQR fence on a 0/1 column is meaningless
    (summarise those with ``proportion_ci``).
    """
    if pd.api.types.is_bool_dtype(s):
        return False
    if pd.api.types.is_numeric_dtype(s):
        return True
    if s.dtype != object:
        return False
    non_null = s.dropna()
    if non_null.empty:
        return False
    return bool(pd.to_numeric(non_null, errors="coerce").notna().all())


def _numeric_columns(
    df: pd.DataFrame,
    cols: Optional[List[str]],
    ignore_cols: Optional[List[str]],
) -> List[str]:
    """Resolve the numeric columns to work on (see ``_is_numeric_like``)."""
    ignore = set(ignore_cols or [])
    if cols is not None:
        _require_columns(df, cols)
        chosen = [c for c in cols if c not in ignore]
    else:
        chosen = [c for c in df.columns if c not in ignore]
    numeric = [c for c in chosen if _is_numeric_like(df[c])]
    if not numeric:
        raise ValueError(
            "No numeric (non-boolean) columns left to analyse after filtering."
        )
    return numeric


def _decision(p: float, alpha: float) -> str:
    """Map a p-value to the standard verdict string."""
    if p is None or not np.isfinite(p):
        return ""
    return _REJECT if p < alpha else _KEEP


def _magnitude(value: float, levels: Tuple[Tuple[float, str], ...]) -> str:
    """Label an effect size against ordered ``(upper_bound, label)`` cut-points."""
    if value is None or not np.isfinite(value):
        return ""
    v = abs(float(value))
    for cut, label in levels:
        if v < cut:
            return label
    return "large"


def _magnitude_v(v: float, min_dim: int) -> str:
    """
    Label a Cramér's V, rescaled for the table's degrees of freedom.

    Cohen's 0.1/0.3/0.5 cut-points are defined for a 2×2 table. In a larger
    table the same association produces a smaller V, so the thresholds are
    divided by ``sqrt(min(rows, cols) - 1)``. Comparing a 2×2 V against a 5×4 V
    without this adjustment reliably understates the bigger table.
    """
    if not np.isfinite(v):
        return ""
    scale = math.sqrt(max(min_dim - 1, 1))
    levels = ((0.10 / scale, "negligible"), (0.30 / scale, "small"),
              (0.50 / scale, "medium"))
    return _magnitude(v, levels)


def _join_flags(flags: Sequence[str]) -> str:
    """Collapse the flag list into one readable cell."""
    return "; ".join(f for f in flags if f)


def _size_flags(samples: Sequence[np.ndarray]) -> List[str]:
    """Flag group sizes that make any test result fragile."""
    if not samples:
        return []
    smallest = min(len(s) for s in samples)
    if smallest < _TINY_N:
        return [f"tiny group (n={smallest}): very low power, result is indicative"]
    if smallest < _SMALL_N:
        return [f"small group (n={smallest})"]
    return []


def _split_groups(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    min_group_n: int,
) -> Tuple[List[str], List[np.ndarray], List[str]]:
    """
    Split ``value_col`` into one clean array per level of ``group_col``.

    Group order follows the categorical order when ``group_col`` is an ordered
    ``Categorical`` and string-sorted order otherwise, so results are stable
    across runs. Groups left with fewer than ``min_group_n`` finite values are
    dropped and named in the returned flags rather than crashing the test.
    """
    _require_columns(df, [group_col, value_col])
    work = df[[group_col, value_col]].dropna(subset=[group_col])
    series = work[group_col]
    if isinstance(series.dtype, pd.CategoricalDtype):
        levels = [c for c in series.cat.categories if (series == c).any()]
    else:
        levels = sorted(series.unique(), key=str)

    labels: List[str] = []
    samples: List[np.ndarray] = []
    dropped: List[str] = []
    for level in levels:
        arr = _clean(work.loc[series == level, value_col])
        if len(arr) < min_group_n:
            dropped.append(f"{level}(n={len(arr)})")
            continue
        labels.append(str(level))
        samples.append(arr)

    flags: List[str] = []
    if dropped:
        flags.append(f"dropped below min_group_n: {', '.join(dropped)}")
    return labels, samples, flags


def _shapiro(
    arr: np.ndarray,
    max_n: int,
    random_state: int,
) -> Tuple[float, float, int, bool]:
    """
    Shapiro-Wilk, subsampling deterministically above ``max_n``.

    Returns ``(statistic, p_value, n_used, was_subsampled)``; both values are
    ``NaN`` below n = 3, where the test is undefined.
    """
    n = len(arr)
    if n < 3:
        return float("nan"), float("nan"), n, False
    subsampled = n > max_n
    if subsampled:
        rng = np.random.default_rng(random_state)
        arr = rng.choice(arr, size=max_n, replace=False)
    res = st.shapiro(arr)
    return float(res.statistic), float(res.pvalue), len(arr), subsampled


def _is_normal(arr: np.ndarray, alpha: float, random_state: int) -> bool:
    """
    Screen one sample for normality, conservatively.

    Below n = 3 nothing can be tested; the sample is reported as *not* normal so
    that automatic test selection falls back to a distribution-free test instead
    of assuming the shape it cannot check.
    """
    _, p, _, _ = _shapiro(arr, _SHAPIRO_MAX_N, random_state)
    if not np.isfinite(p):
        return False
    return p > alpha


def _fisher_ci(
    r: float,
    n: int,
    method: str,
    confidence: float,
    n_covar: int = 0,
) -> Tuple[float, float]:
    """
    Confidence interval for a correlation coefficient via the Fisher z transform.

    ``arctanh(r)`` is approximately normal with a coefficient-specific standard
    error, so the interval is built on the z scale and mapped back with ``tanh``.
    Using Pearson's ``1/sqrt(n-3)`` for all three coefficients — a common
    shortcut — produces intervals that are too narrow for Spearman and Kendall,
    so each gets its own variance (Bonett & Wright, 2000).
    """
    dof_used = n - n_covar
    if not np.isfinite(r) or abs(r) >= 1.0:
        return float("nan"), float("nan")
    if method == "pearson":
        if dof_used < 4:
            return float("nan"), float("nan")
        se = 1.0 / math.sqrt(dof_used - 3)
    elif method == "spearman":
        if dof_used < 4:
            return float("nan"), float("nan")
        se = math.sqrt(1.06 / (dof_used - 3))
    else:  # kendall
        if dof_used < 5:
            return float("nan"), float("nan")
        se = math.sqrt(0.437 / (dof_used - 4))
    z = math.atanh(r)
    crit = st.norm.ppf(0.5 + confidence / 2.0)
    return math.tanh(z - crit * se), math.tanh(z + crit * se)


def _mean_diff(x: np.ndarray, y: np.ndarray, axis: int = -1) -> np.ndarray:
    """Difference of means, written for scipy's vectorised resampling API."""
    return np.mean(x, axis=axis) - np.mean(y, axis=axis)


def _median_diff(x: np.ndarray, y: np.ndarray, axis: int = -1) -> np.ndarray:
    """Difference of medians, written for scipy's vectorised resampling API."""
    return np.median(x, axis=axis) - np.median(y, axis=axis)


def _boot_diff_ci(
    a: np.ndarray,
    b: np.ndarray,
    stat: Callable[..., np.ndarray],
    confidence: float,
    n_resamples: int,
    random_state: int,
) -> Tuple[float, float, List[str]]:
    """Bootstrap a two-sample difference; degenerate cases return NaN, flagged."""
    try:
        with warnings.catch_warnings():
            # scipy warns and returns NaN on degenerate input; that is reported
            # through the flags column instead, where it stays with the result.
            warnings.simplefilter("ignore")
            res = st.bootstrap(
                (a, b), stat, vectorized=True, paired=False,
                confidence_level=confidence, n_resamples=n_resamples,
                method="BCa", random_state=random_state,
            )
        low = float(res.confidence_interval.low)
        high = float(res.confidence_interval.high)
        if not (np.isfinite(low) and np.isfinite(high)):
            return low, high, [f"bootstrap {_DEGENERATE_CI}"]
        return low, high, []
    except Exception as exc:  # no interval is preferable to a wrong one
        return float("nan"), float("nan"), [f"bootstrap CI unavailable ({exc})"]


def _welch_anova(samples: Sequence[np.ndarray]) -> Tuple[float, float, float, float]:
    """
    Welch's heteroscedastic one-way ANOVA.

    Classic one-way ANOVA pools a single error variance across groups; when the
    groups have genuinely different spreads — especially with unequal n — its
    F test is badly calibrated. Welch weights each group by its own precision
    (``n_i / s_i²``) and adjusts the denominator degrees of freedom.

    Returns ``(F, p_value, df1, df2)``.
    """
    k = len(samples)
    n = np.array([len(s) for s in samples], dtype=float)
    means = np.array([s.mean() for s in samples], dtype=float)
    var = np.array([s.var(ddof=1) for s in samples], dtype=float)
    if np.any(var <= 0):
        return float("nan"), float("nan"), float("nan"), float("nan")

    w = n / var
    w_sum = w.sum()
    grand = float((w * means).sum() / w_sum)
    lam = ((1.0 - w / w_sum) ** 2 / (n - 1.0)).sum()

    numerator = (w * (means - grand) ** 2).sum() / (k - 1)
    denominator = 1.0 + (2.0 * (k - 2) / (k**2 - 1)) * lam
    f_stat = float(numerator / denominator)
    df1 = float(k - 1)
    df2 = float(1.0 / ((3.0 / (k**2 - 1)) * lam))
    return f_stat, float(st.f.sf(f_stat, df1, df2)), df1, df2


def _eta_squared(samples: Sequence[np.ndarray]) -> float:
    """Classic η² = between-group sum of squares / total sum of squares."""
    allv = np.concatenate(samples)
    grand = allv.mean()
    ss_between = sum(len(s) * (s.mean() - grand) ** 2 for s in samples)
    ss_total = float(((allv - grand) ** 2).sum())
    return float(ss_between / ss_total) if ss_total > 0 else float("nan")


def _eta_squared_h(h_stat: float, k: int, n: int) -> float:
    """
    Rank-based η² for Kruskal-Wallis: ``(H - k + 1) / (n - k)``.

    An alternative, ε² = ``H (n + 1) / (n² - 1)``, is equally defensible and
    usually lands within a hair of this; the two are not interchangeable in a
    write-up, so state which one a number came from.
    """
    if n <= k:
        return float("nan")
    return float((h_stat - k + 1) / (n - k))


def _rank_biserial_paired(diff: np.ndarray) -> float:
    """
    Matched-pairs rank-biserial correlation for the Wilcoxon signed-rank test.

    ``(T⁺ - T⁻) / (T⁺ + T⁻)`` — the share of signed-rank mass sitting on the
    positive side, on a -1…+1 scale. Zero differences are excluded, matching
    the test itself.
    """
    d = diff[diff != 0]
    if d.size == 0:
        return float("nan")
    ranks = st.rankdata(np.abs(d))
    t_plus = float(ranks[d > 0].sum())
    t_minus = float(ranks[d < 0].sum())
    total = t_plus + t_minus
    return float((t_plus - t_minus) / total) if total > 0 else float("nan")


_TWO_GROUP_TESTS = ("welch", "student", "mannwhitney", "brunnermunzel",
                    "ks", "permutation")
_K_GROUP_TESTS = ("anova", "welch_anova", "kruskal")


def _resolve_test(
    samples: Sequence[np.ndarray],
    test: str,
    alpha: float,
    random_state: int,
    pairwise: bool = False,
) -> Tuple[str, str, List[str]]:
    """
    Pick the test for ``compare_groups`` and explain the choice.

    Returns ``(test_name, chosen_because, flags)``. When ``test`` is anything
    other than ``'auto'`` this only validates the name against the group count.

    ``pairwise=True`` forces a two-sample test even though several groups were
    supplied: the assumption screen still looks at *all* the groups, so one
    consistent test is applied to every pair rather than a fresh choice per pair.
    """
    k = len(samples)
    allowed = _TWO_GROUP_TESTS if (pairwise or k == 2) else _K_GROUP_TESTS
    if test != "auto":
        if test not in allowed:
            scope = "pairwise comparison" if pairwise else f"{k} groups"
            raise ValueError(
                f"test='{test}' is not valid for {scope}. "
                f"Choose one of {allowed} or 'auto'."
            )
        return test, "user-specified", []

    normal = [_is_normal(s, alpha, random_state) for s in samples]
    n_normal = sum(normal)
    flags: List[str] = []

    equal_var = True
    if all(len(s) >= 2 for s in samples):
        try:
            equal_var = float(st.levene(*samples, center="median").pvalue) > alpha
        except ValueError:
            equal_var = True
            flags.append("variance test failed; assumed equal variances")

    biggest = max(len(s) for s in samples)
    if biggest > 300 and n_normal < k:
        flags.append(
            "normality rejected at large n — check a Q-Q plot before accepting "
            "the non-parametric route"
        )

    var_word = "equal" if equal_var else "unequal"
    reason = f"auto: normal {n_normal}/{k}, variances {var_word}"

    if pairwise or k == 2:
        if n_normal == k:
            return "welch", reason, flags
        return ("mannwhitney" if equal_var else "brunnermunzel"), reason, flags
    if n_normal == k:
        return ("anova" if equal_var else "welch_anova"), reason, flags
    return "kruskal", reason, flags


def _run_two_group(
    a: np.ndarray,
    b: np.ndarray,
    test: str,
    alpha: float,
    alternative: str,
    confidence: float,
    ci: str,
    n_resamples: int,
    random_state: int,
) -> Tuple[Dict[str, object], List[str]]:
    """
    Execute one two-sample test and package the shared result columns.

    ``a`` is always the reference: a positive ``estimate`` or effect size means
    group A sits above group B, and ``alternative='greater'`` reads as
    "A is greater than B".
    """
    flags: List[str] = []
    estimate = float("nan")
    ci_low = ci_high = float("nan")
    estimate_type = ""

    if test in ("welch", "student"):
        equal_var = test == "student"
        res = st.ttest_ind(a, b, equal_var=equal_var, alternative=alternative)
        statistic, p_value = float(res.statistic), float(res.pvalue)
        effect = cohens_d(a, b, hedges=True)
        effect_type, levels = "hedges_g", _D_LEVELS
        estimate_type = "mean difference"
        estimate = float(a.mean() - b.mean())
        if ci in ("auto", "t"):
            # Recomputed two-sided so the interval is a real interval even when
            # the test itself was one-sided (where scipy returns an open bound).
            two_sided = st.ttest_ind(a, b, equal_var=equal_var)
            interval = two_sided.confidence_interval(confidence_level=confidence)
            ci_low, ci_high = float(interval.low), float(interval.high)
        elif ci == "bootstrap":
            ci_low, ci_high, boot_flags = _boot_diff_ci(
                a, b, _mean_diff, confidence, n_resamples, random_state
            )
            flags += boot_flags
        if test == "student":
            flags.append("assumes equal variances (Welch is the safer default)")

    elif test == "mannwhitney":
        res = st.mannwhitneyu(a, b, alternative=alternative)
        statistic, p_value = float(res.statistic), float(res.pvalue)
        effect = cliffs_delta(a, b)
        effect_type, levels = "cliffs_delta", _DELTA_LEVELS
        estimate_type = "median difference"
        estimate = float(np.median(a) - np.median(b))
        if ci == "bootstrap":
            ci_low, ci_high, boot_flags = _boot_diff_ci(
                a, b, _median_diff, confidence, n_resamples, random_state
            )
            flags += boot_flags

    elif test == "brunnermunzel":
        res = st.brunnermunzel(a, b, alternative=alternative, distribution="t")
        statistic, p_value = float(res.statistic), float(res.pvalue)
        effect = cliffs_delta(a, b)
        effect_type, levels = "cliffs_delta", _DELTA_LEVELS
        estimate_type = "median difference"
        estimate = float(np.median(a) - np.median(b))
        if min(len(a), len(b)) < 10:
            flags.append("Brunner-Munzel t-approximation is unreliable below n=10")
        if ci == "bootstrap":
            ci_low, ci_high, boot_flags = _boot_diff_ci(
                a, b, _median_diff, confidence, n_resamples, random_state
            )
            flags += boot_flags

    elif test == "ks":
        res = st.ks_2samp(a, b, alternative=alternative)
        statistic, p_value = float(res.statistic), float(res.pvalue)
        effect = float(res.statistic)  # D is itself the effect size
        effect_type, levels = "ks_D", _R_LEVELS
        flags.append(
            "KS compares whole distributions, not locations — a significant "
            "result can come from a spread or shape difference alone"
        )

    else:  # permutation
        res = st.permutation_test(
            (a, b), _mean_diff, permutation_type="independent",
            n_resamples=n_resamples, alternative=alternative,
            vectorized=True, random_state=random_state,
        )
        statistic, p_value = float(res.statistic), float(res.pvalue)
        effect = cohens_d(a, b, hedges=True)
        effect_type, levels = "hedges_g", _D_LEVELS
        estimate_type = "mean difference"
        estimate = float(a.mean() - b.mean())
        if ci == "bootstrap":
            ci_low, ci_high, boot_flags = _boot_diff_ci(
                a, b, _mean_diff, confidence, n_resamples, random_state
            )
            flags += boot_flags

    row: Dict[str, object] = {
        "test": test,
        "n": int(len(a) + len(b)),
        "statistic": statistic,
        "p_value": p_value,
        "decision": _decision(p_value, alpha),
        "estimate_type": estimate_type,
        "estimate": estimate,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "effect_size": effect,
        "effect_type": effect_type,
        "magnitude": _magnitude(effect, levels),
    }
    return row, flags


# ══════════════════════════════════════════════════════════════════════════════
# 1 — Descriptive summaries and assumption checks
# ══════════════════════════════════════════════════════════════════════════════
def summary_stats(
    df: pd.DataFrame,
    cols: Optional[List[str]] = None,
    ignore_cols: Optional[List[str]] = None,
    confidence: float = 0.95,
    trim: float = 0.1,
) -> pd.DataFrame:
    """
    Descriptive profile of every numeric column, with robust companions.

    ``DataFrame.describe`` reports mean/std/quartiles and stops. This adds the
    three things that decide how the rest of an analysis should proceed: a
    confidence interval on the mean (is the centre even pinned down?), robust
    counterparts to mean and std (do outliers dominate?), and shape statistics
    (does a parametric test stand a chance?). Reading ``mean`` against
    ``trimmed_mean`` and ``std`` against ``mad`` is the fastest outlier
    diagnostic there is: a large gap means the summary is being driven by a
    handful of points.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    cols : list of str, optional
        Restrict to these columns; ``None`` profiles every numeric column.
    ignore_cols : list of str, optional
        Columns to exclude.
    confidence : float, default 0.95
        Confidence level for the interval around the mean (Student-t based).
    trim : float, default 0.1
        Proportion cut from *each* tail for ``trimmed_mean``.

    Returns
    -------
    pd.DataFrame
        One row per column: counts, mean and its CI, trimmed mean, median, std,
        MAD, IQR, coefficient of variation, skew, excess kurtosis, and the
        five-number summary.

    Notes
    -----
    ``mad`` is the median absolute deviation scaled by 1.4826 so it estimates
    the same quantity as ``std`` under normality — the two columns are directly
    comparable. ``cv`` (std/mean) is only meaningful for positive ratio-scale
    data and is returned as ``NaN`` when the mean is ~0. ``skew`` and
    ``excess_kurtosis`` are the bias-corrected sample versions, matching pandas;
    excess kurtosis is 0 for a normal distribution, not 3.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}.")
    if not 0.0 <= trim < 0.5:
        raise ValueError(f"trim must be in [0, 0.5), got {trim}.")

    columns = _numeric_columns(df, cols, ignore_cols)
    crit_half = 0.5 + confidence / 2.0
    rows: List[Dict[str, object]] = []

    for col in columns:
        raw = df[col]
        arr = _clean(raw)
        n = len(arr)
        n_missing = int(len(raw) - n)
        if n == 0:
            rows.append({"column": col, "n": 0, "n_missing": n_missing})
            continue

        mean = float(arr.mean())
        std = float(arr.std(ddof=1)) if n > 1 else float("nan")
        if n > 1 and np.isfinite(std):
            sem = std / math.sqrt(n)
            half = float(st.t.ppf(crit_half, n - 1) * sem)
            ci_low, ci_high = mean - half, mean + half
        else:
            ci_low = ci_high = float("nan")
        q1, q3 = np.percentile(arr, [25, 75])
        # Shape statistics are undefined on a constant column, and scipy warns
        # about catastrophic cancellation rather than returning NaN.
        varies = bool(np.ptp(arr) > 0)

        rows.append({
            "column": col,
            "n": n,
            "n_missing": n_missing,
            "pct_missing": round(100.0 * n_missing / max(len(raw), 1), 2),
            "n_unique": int(pd.Series(arr).nunique()),
            "mean": mean,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "trimmed_mean": float(st.trim_mean(arr, trim)),
            "median": float(np.median(arr)),
            "std": std,
            "mad": float(st.median_abs_deviation(arr, scale="normal")),
            "iqr": float(q3 - q1),
            "cv": (float(std / mean) if abs(mean) > 1e-12 and np.isfinite(std)
                   else float("nan")),
            "skew": (float(st.skew(arr, bias=False))
                     if n > 2 and varies else float("nan")),
            "excess_kurtosis": (float(st.kurtosis(arr, fisher=True, bias=False))
                                if n > 3 and varies else float("nan")),
            "min": float(arr.min()),
            "q1": float(q1),
            "q3": float(q3),
            "max": float(arr.max()),
        })

    return pd.DataFrame(rows)


def normality_test(
    df: pd.DataFrame,
    cols: Optional[List[str]] = None,
    ignore_cols: Optional[List[str]] = None,
    method: Literal["shapiro", "dagostino", "jarque_bera", "anderson"] = "shapiro",
    alpha: float = 0.05,
    max_n: int = _SHAPIRO_MAX_N,
    random_state: int = 0,
) -> pd.DataFrame:
    """
    Test whether each numeric column is consistent with a normal distribution.

    H₀: the sample comes from a normal distribution. A small p-value rejects
    normality and pushes the analysis toward non-parametric or robust methods.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    cols : list of str, optional
        Restrict to these columns; ``None`` tests every numeric column.
    ignore_cols : list of str, optional
        Columns to exclude.
    method : {'shapiro', 'dagostino', 'jarque_bera', 'anderson'}, default 'shapiro'
        - ``'shapiro'`` — best all-round power at small-to-moderate n; capped at
          ``max_n`` observations (see below).
        - ``'dagostino'`` — combines skew and kurtosis; needs n ≥ 8 and tells you
          *how* the shape departs, which the others do not.
        - ``'jarque_bera'`` — same idea, asymptotic; only trust it at large n.
        - ``'anderson'`` — Anderson-Darling, the most sensitive to the tails,
          which is usually where the damage is. On SciPy ≥ 1.17 it returns an
          interpolated p-value like the others; on older versions it yields only
          a critical value, so ``p_value`` is ``NaN`` and the decision compares
          ``statistic`` against ``critical_value`` instead.
    alpha : float, default 0.05
        Significance level.
    max_n : int, default 5000
        Shapiro-Wilk cap. Larger samples are subsampled without replacement
        using ``random_state`` (reproducible, and flagged in ``flags``).
    random_state : int, default 0
        Seed for that subsample.

    Returns
    -------
    pd.DataFrame
        One row per column with ``n``, ``n_used``, ``statistic``, ``p_value``,
        ``critical_value``, ``decision``, ``skew``, ``excess_kurtosis``, ``flags``.

    Notes
    -----
    **A normality test answers the wrong question at large n.** Its power grows
    with the sample, so past a few thousand rows it rejects deviations far too
    small to affect a t-test, while at n < 20 it fails to reject almost anything.
    Treat the p-value as one input: read ``skew`` and ``excess_kurtosis`` (both
    reported here for exactly this reason) and look at a Q-Q plot before
    concluding a distribution is unusable. Note too that t-tests and ANOVA
    assume normality of the *sampling distribution of the mean*, which the CLT
    delivers from skewed data once groups are reasonably large — so a rejection
    here is a prompt to think, not an automatic disqualification.
    """
    columns = _numeric_columns(df, cols, ignore_cols)
    rows: List[Dict[str, object]] = []

    for col in columns:
        arr = _clean(df[col])
        n = len(arr)
        flags: List[str] = []
        statistic = p_value = critical = float("nan")
        n_used = n

        if n < 3:
            flags.append("n < 3: normality is untestable")
        elif np.ptp(arr) == 0:
            flags.append("zero variance: constant column")
        elif method == "shapiro":
            statistic, p_value, n_used, subsampled = _shapiro(
                arr, max_n, random_state
            )
            if subsampled:
                flags.append(f"subsampled to n={max_n} (seed={random_state})")
        elif method == "dagostino":
            if n < 8:
                flags.append("D'Agostino needs n ≥ 8")
            else:
                res = st.normaltest(arr)
                statistic, p_value = float(res.statistic), float(res.pvalue)
                if n < 20:
                    flags.append("n < 20: D'Agostino p-value is approximate")
        elif method == "jarque_bera":
            res = st.jarque_bera(arr)
            statistic, p_value = float(res.statistic), float(res.pvalue)
            if n < 2000:
                flags.append("Jarque-Bera is asymptotic; unreliable below n≈2000")
        else:  # anderson
            try:
                # SciPy ≥ 1.17 interpolates a real p-value; older versions only
                # expose critical values, so both paths are kept.
                res = st.anderson(arr, dist="norm", method="interpolate")
                statistic, p_value = float(res.statistic), float(res.pvalue)
            except TypeError:
                res = st.anderson(arr, dist="norm")
                statistic = float(res.statistic)
                targets = np.asarray(res.significance_level, dtype=float) / 100.0
                idx = int(np.argmin(np.abs(targets - alpha)))
                critical = float(res.critical_values[idx])
                if not math.isclose(targets[idx], alpha, abs_tol=1e-9):
                    flags.append(
                        f"no critical value at α={alpha}; used α={targets[idx]:.3f}"
                    )

        if np.isfinite(p_value):
            decision = _decision(p_value, alpha)
        elif np.isfinite(critical) and np.isfinite(statistic):
            decision = _REJECT if statistic > critical else _KEEP
        else:
            decision = ""

        if n > 5000:
            flags.append("large n: trivial deviations become 'significant'")
        elif 0 < n < _SMALL_N:
            flags.append("small n: low power to detect non-normality")

        rows.append({
            "column": col,
            "method": method,
            "n": n,
            "n_used": n_used,
            "statistic": statistic,
            "p_value": p_value,
            "critical_value": critical,
            "decision": decision,
            "skew": (float(st.skew(arr, bias=False))
                     if n > 2 and np.ptp(arr) > 0 else float("nan")),
            "excess_kurtosis": (float(st.kurtosis(arr, fisher=True, bias=False))
                                if n > 3 and np.ptp(arr) > 0 else float("nan")),
            "flags": _join_flags(flags),
        })

    return pd.DataFrame(rows)


def variance_test(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    method: Literal["levene", "bartlett", "fligner"] = "levene",
    center: Literal["median", "mean", "trimmed"] = "median",
    alpha: float = 0.05,
    min_group_n: int = 2,
) -> pd.DataFrame:
    """
    Test whether groups share a common variance (homoscedasticity).

    H₀: all groups have the same variance. This is the assumption that decides
    between Student's and Welch's t-test, and between classic and Welch ANOVA.

    Parameters
    ----------
    df : pd.DataFrame
        Input data in long format.
    group_col : str
        Column holding the group labels.
    value_col : str
        Numeric column being compared.
    method : {'levene', 'bartlett', 'fligner'}, default 'levene'
        - ``'levene'`` with ``center='median'`` is the Brown-Forsythe test:
          robust to non-normality and the sensible default.
        - ``'bartlett'`` is more powerful **if** the data really are normal, and
          badly misleading if they are not — it confounds kurtosis with unequal
          variance.
        - ``'fligner'`` is a rank-based, fully non-parametric alternative.
    center : {'median', 'mean', 'trimmed'}, default 'median'
        Centring for Levene/Fligner. ``'median'`` is what makes them robust.
        Ignored by Bartlett.
    alpha : float, default 0.05
        Significance level.
    min_group_n : int, default 2
        Groups with fewer finite values are dropped and named in ``flags``.

    Returns
    -------
    pd.DataFrame
        A single row: ``test``, ``n_groups``, ``n``, ``group_sizes``,
        ``statistic``, ``p_value``, ``decision``, ``max_var_ratio``, ``flags``.

    Notes
    -----
    ``max_var_ratio`` (largest group variance ÷ smallest) is reported because
    the p-value alone is misleading in both directions: with large groups a
    ratio of 1.2 can be "significant" and matters not at all, while with small
    groups a ratio of 5 can slip past. A ratio under ~4 with roughly balanced
    group sizes is generally tolerable for ANOVA; unequal variance combined with
    unequal n is the case that actually breaks it — and the fix is Welch, not a
    transformation chosen to satisfy this test.
    """
    labels, samples, flags = _split_groups(df, group_col, value_col, min_group_n)
    if len(samples) < 2:
        raise ValueError(
            f"Need at least 2 groups with n ≥ {min_group_n}; got {len(samples)}."
        )

    if method == "bartlett":
        res = st.bartlett(*samples)
        flags.append("Bartlett assumes normality — verify it or use Levene")
    elif method == "fligner":
        res = st.fligner(*samples, center=center)
    else:
        res = st.levene(*samples, center=center)
        if center != "median":
            flags.append(f"center='{center}' trades robustness for power")

    variances = np.array([s.var(ddof=1) for s in samples], dtype=float)
    positive = variances[variances > 0]
    var_ratio = (float(positive.max() / positive.min())
                 if positive.size == variances.size else float("nan"))
    if np.isfinite(var_ratio) and var_ratio > 4:
        flags.append(f"variance ratio {var_ratio:.1f}× — prefer Welch-type tests")

    sizes = np.array([len(s) for s in samples], dtype=float)
    if sizes.max() / sizes.min() > 1.5 and np.isfinite(var_ratio) and var_ratio > 2:
        flags.append("unequal n with unequal variance: the case that breaks ANOVA")
    flags += _size_flags(samples)

    return pd.DataFrame([{
        "test": f"{method}({center})" if method != "bartlett" else "bartlett",
        "n_groups": len(samples),
        "n": int(sizes.sum()),
        "group_sizes": "; ".join(f"{l}={len(s)}" for l, s in zip(labels, samples)),
        "statistic": float(res.statistic),
        "p_value": float(res.pvalue),
        "decision": _decision(float(res.pvalue), alpha),
        "max_var_ratio": var_ratio,
        "flags": _join_flags(flags),
    }])


def outlier_summary(
    df: pd.DataFrame,
    cols: Optional[List[str]] = None,
    ignore_cols: Optional[List[str]] = None,
    method: Literal["iqr", "zscore", "modified_zscore"] = "iqr",
    threshold: Optional[float] = None,
) -> pd.DataFrame:
    """
    Count and bound the outliers in each numeric column.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    cols : list of str, optional
        Restrict to these columns; ``None`` scans every numeric column.
    ignore_cols : list of str, optional
        Columns to exclude.
    method : {'iqr', 'zscore', 'modified_zscore'}, default 'iqr'
        - ``'iqr'`` — Tukey fences at ``Q1 - k·IQR`` and ``Q3 + k·IQR``
          (``k = threshold``, default 1.5). Quartile-based, so the fence itself
          is not dragged around by the outliers.
        - ``'zscore'`` — ``|x - mean| / std > threshold`` (default 3.0). Listed
          for completeness but **self-defeating**: the mean and std it relies on
          are themselves inflated by the very points it is looking for, so a
          few extreme values mask each other.
        - ``'modified_zscore'`` — ``0.6745·|x - median| / MAD > threshold``
          (default 3.5, Iglewicz & Hoaglin). The robust version of z-score and
          the best choice when a column is contaminated.
    threshold : float, optional
        Cut-off for the chosen method; ``None`` uses the documented default.

    Returns
    -------
    pd.DataFrame
        One row per column: bounds, ``n_outliers``, ``pct_outliers``, and the
        most extreme flagged values on each side.

    Notes
    -----
    These are *distributional* flags, not errors. On a right-skewed column —
    counts, money, durations — the IQR rule will flag a long legitimate tail,
    and deleting it would destroy the very structure the analysis is about.
    Decide what an outlier means for the question at hand before removing
    anything; ``outlier_flags`` returns the mask if you do want to act on it.
    """
    defaults = {"iqr": 1.5, "zscore": 3.0, "modified_zscore": 3.5}
    if method not in defaults:
        raise ValueError(f"method must be one of {tuple(defaults)}, got '{method}'.")
    thr = defaults[method] if threshold is None else float(threshold)

    columns = _numeric_columns(df, cols, ignore_cols)
    rows: List[Dict[str, object]] = []

    for col in columns:
        arr = _clean(df[col])
        n = len(arr)
        low, high = _outlier_bounds(arr, method, thr)
        if n == 0 or not np.isfinite(low) or not np.isfinite(high):
            outliers = np.array([], dtype=float)
        else:
            outliers = arr[(arr < low) | (arr > high)]

        rows.append({
            "column": col,
            "method": method,
            "threshold": thr,
            "n": n,
            "lower_bound": low,
            "upper_bound": high,
            "n_outliers": int(outliers.size),
            "pct_outliers": (round(100.0 * outliers.size / n, 2) if n else
                             float("nan")),
            "n_below": int((arr < low).sum()) if n else 0,
            "n_above": int((arr > high).sum()) if n else 0,
            "min_outlier": float(outliers.min()) if outliers.size else float("nan"),
            "max_outlier": float(outliers.max()) if outliers.size else float("nan"),
        })

    return pd.DataFrame(rows)


def _outlier_bounds(
    arr: np.ndarray,
    method: str,
    threshold: float,
) -> Tuple[float, float]:
    """Lower/upper cut-offs for one column under the chosen rule."""
    if arr.size == 0:
        return float("nan"), float("nan")
    if method == "iqr":
        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1
        return float(q1 - threshold * iqr), float(q3 + threshold * iqr)
    if method == "zscore":
        if arr.size < 2:
            return float("nan"), float("nan")
        mean = float(arr.mean())
        std = float(arr.std(ddof=1))
        if not std:
            return float("nan"), float("nan")
        return mean - threshold * std, mean + threshold * std
    median = float(np.median(arr))
    mad = float(st.median_abs_deviation(arr, scale=1.0))
    if not mad:
        return float("nan"), float("nan")
    half = threshold * mad / 0.6745
    return median - half, median + half


def outlier_flags(
    df: pd.DataFrame,
    cols: Optional[List[str]] = None,
    ignore_cols: Optional[List[str]] = None,
    method: Literal["iqr", "zscore", "modified_zscore"] = "iqr",
    threshold: Optional[float] = None,
) -> pd.DataFrame:
    """
    Boolean mask of the outliers found by ``outlier_summary``.

    Same parameters and rules as ``outlier_summary`` — this is its actionable
    half, returning *which* rows were flagged rather than how many.

    Returns
    -------
    pd.DataFrame
        Boolean frame aligned to ``df.index``, one column per analysed column,
        plus ``any_outlier`` marking rows flagged in at least one column.
        ``NaN`` inputs are ``False`` (missing is not the same as extreme).

    Examples
    --------
    >>> mask = outlier_flags(df, cols=["price"], method="modified_zscore")
    >>> clean = df.loc[~mask["any_outlier"]]
    """
    defaults = {"iqr": 1.5, "zscore": 3.0, "modified_zscore": 3.5}
    if method not in defaults:
        raise ValueError(f"method must be one of {tuple(defaults)}, got '{method}'.")
    thr = defaults[method] if threshold is None else float(threshold)

    columns = _numeric_columns(df, cols, ignore_cols)
    out = pd.DataFrame(index=df.index)
    for col in columns:
        values = pd.to_numeric(df[col], errors="coerce").to_numpy(
            dtype=float, na_value=np.nan
        )
        low, high = _outlier_bounds(values[np.isfinite(values)], method, thr)
        if not np.isfinite(low) or not np.isfinite(high):
            out[col] = False
            continue
        flagged = (values < low) | (values > high)
        out[col] = np.where(np.isfinite(values), flagged, False)
    out["any_outlier"] = out.any(axis=1)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 2 — Estimation and confidence intervals
# ══════════════════════════════════════════════════════════════════════════════
def bootstrap_ci(
    df: pd.DataFrame,
    value_col: str,
    group_col: Optional[str] = None,
    statistic: Union[str, Callable[..., float]] = "mean",
    confidence: float = 0.95,
    n_resamples: int = 9999,
    method: Literal["BCa", "percentile", "basic"] = "BCa",
    min_group_n: int = 2,
    random_state: int = 0,
) -> pd.DataFrame:
    """
    Confidence interval for any statistic, by resampling the data itself.

    The bootstrap replaces "assume the sampling distribution is normal" with
    "simulate it": resample the observations with replacement thousands of
    times, recompute the statistic each time, and read the interval off the
    resulting spread. It is the only practical route to a CI for a median, an
    IQR, a trimmed mean, or any custom metric — none of which have a usable
    textbook formula.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    value_col : str
        Numeric column to resample.
    group_col : str, optional
        Compute a separate interval per level of this column. ``None`` returns
        one row for the whole column.
    statistic : str or callable, default 'mean'
        One of ``'mean'``, ``'median'``, ``'std'``, ``'var'``, ``'min'``,
        ``'max'``, ``'sum'``, or a callable. Named statistics are vectorised and
        fast; a callable is applied one resample at a time and is far slower —
        lower ``n_resamples`` to ~2000 when using one.
    confidence : float, default 0.95
        Confidence level.
    n_resamples : int, default 9999
        Bootstrap resamples. Odd numbers avoid ties at the percentile cut-points.
    method : {'BCa', 'percentile', 'basic'}, default 'BCa'
        - ``'BCa'`` — bias-corrected and accelerated. Adjusts for both bias and
          skew in the bootstrap distribution and is the most accurate here.
        - ``'percentile'`` — raw quantiles of the resamples; simple, and too
          narrow for skewed statistics.
        - ``'basic'`` — reflects the percentiles about the estimate; can produce
          impossible values (a negative bound on a strictly positive quantity).
    min_group_n : int, default 2
        Groups smaller than this are skipped.
    random_state : int, default 0
        Seed, so the interval is reproducible.

    Returns
    -------
    pd.DataFrame
        One row per group with ``estimate``, ``ci_low``, ``ci_high``,
        ``se`` (bootstrap standard error) and ``flags``.

    Notes
    -----
    The bootstrap assumes the sample represents the population and that
    observations are independent — it cannot repair a biased sample, and it is
    unreliable for statistics that depend on the extremes (min, max) or when n
    is very small, since the resamples can only ever contain values already
    observed. BCa additionally needs a non-degenerate jackknife; on constant or
    near-constant data it fails, and that failure is reported in ``flags``
    rather than papered over.
    """
    _require_columns(df, [value_col])
    if isinstance(statistic, str):
        if statistic not in _STAT_FUNCS:
            raise ValueError(
                f"statistic must be a callable or one of {tuple(_STAT_FUNCS)}, "
                f"got '{statistic}'."
            )
        func: Callable[..., np.ndarray] = _STAT_FUNCS[statistic]
        stat_name, vectorized = statistic, True
    else:
        func = statistic
        stat_name = getattr(statistic, "__name__", "custom")
        vectorized = False

    if group_col is None:
        labels, samples, flags = ["all"], [_clean(df[value_col])], []
    else:
        labels, samples, flags = _split_groups(
            df, group_col, value_col, min_group_n
        )

    rows: List[Dict[str, object]] = []
    for label, arr in zip(labels, samples):
        row_flags = list(flags)
        estimate = (float(func(arr)) if arr.size else float("nan"))
        ci_low = ci_high = se = float("nan")
        if arr.size < 2:
            row_flags.append("n < 2: no interval")
        else:
            try:
                with warnings.catch_warnings():
                    # Degenerate-data warnings become flags on the row, so the
                    # caveat travels with the number instead of the scrollback.
                    warnings.simplefilter("ignore")
                    res = st.bootstrap(
                        (arr,), func, vectorized=vectorized,
                        confidence_level=confidence, n_resamples=n_resamples,
                        method=method, random_state=random_state,
                    )
                ci_low = float(res.confidence_interval.low)
                ci_high = float(res.confidence_interval.high)
                se = float(res.standard_error)
                if not (np.isfinite(ci_low) and np.isfinite(ci_high)):
                    row_flags.append(f"{method} {_DEGENERATE_CI}")
            except Exception as exc:
                row_flags.append(f"bootstrap failed ({exc})")
            if arr.size < _SMALL_N:
                row_flags.append(f"small n ({arr.size}): interval is optimistic")

        rows.append({
            "group": label,
            "statistic": stat_name,
            "n": int(arr.size),
            "estimate": estimate,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "se": se,
            "method": method,
            "confidence": confidence,
            "flags": _join_flags(row_flags),
        })

    return pd.DataFrame(rows)


def proportion_ci(
    successes: Union[int, Sequence[int], np.ndarray, pd.Series],
    n: Union[int, Sequence[int], np.ndarray, pd.Series],
    confidence: float = 0.95,
    method: Literal["wilson", "agresti_coull", "clopper_pearson", "wald"] = "wilson",
    labels: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """
    Confidence interval for one or many binomial proportions.

    Rates — win rate, conversion rate, share of anything — are proportions, and
    the interval around them depends on how extreme the rate is and how many
    trials produced it. 7/10 and 700/1000 are the same point estimate carrying
    completely different uncertainty; this makes that visible.

    Parameters
    ----------
    successes : int or array-like of int
        Count of successes. Scalars and arrays are both accepted.
    n : int or array-like of int
        Number of trials, broadcast against ``successes``.
    confidence : float, default 0.95
        Confidence level.
    method : {'wilson', 'agresti_coull', 'clopper_pearson', 'wald'}, default 'wilson'
        - ``'wilson'`` — accurate down to small n and near 0 or 1; the default
          for good reason.
        - ``'agresti_coull'`` — "add 2 successes and 2 failures" then apply the
          normal formula; simpler to explain, slightly wider.
        - ``'clopper_pearson'`` — exact, guaranteed ≥ nominal coverage, and
          noticeably conservative (wide). Use when under-coverage is costly.
        - ``'wald'`` — the textbook ``p ± z·sqrt(p(1-p)/n)``. Included so it can
          be compared, not recommended: it collapses to zero width at p = 0 or 1
          and under-covers badly at small n.
    labels : sequence of str, optional
        Row labels; defaults to positional indices.

    Returns
    -------
    pd.DataFrame
        One row per proportion: ``label``, ``successes``, ``n``, ``proportion``,
        ``ci_low``, ``ci_high``, ``width``, ``method``.

    Examples
    --------
    Straight from a groupby::

        g = df.groupby("league")["won"].agg(["sum", "count"])
        proportion_ci(g["sum"], g["count"], labels=g.index)

    Notes
    -----
    To *compare* two proportions rather than describe them, put the counts in a
    2×2 table and use ``association_test`` — that is exactly the hypothesis a
    chi-square (or Fisher's exact) test answers.
    """
    methods = ("wilson", "agresti_coull", "clopper_pearson", "wald")
    if method not in methods:
        raise ValueError(f"method must be one of {methods}, got '{method}'.")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}.")

    k_arr = np.atleast_1d(np.asarray(successes, dtype=float))
    n_arr = np.atleast_1d(np.asarray(n, dtype=float))
    k_arr, n_arr = np.broadcast_arrays(k_arr, n_arr)
    if np.any(k_arr < 0) or np.any(k_arr > n_arr):
        raise ValueError("Every successes value must satisfy 0 ≤ successes ≤ n.")

    if labels is None:
        row_labels: List[str] = [str(i) for i in range(len(k_arr))]
    else:
        row_labels = [str(v) for v in labels]
        if len(row_labels) != len(k_arr):
            raise ValueError(
                f"labels has {len(row_labels)} entries but there are "
                f"{len(k_arr)} proportions."
            )

    alpha = 1.0 - confidence
    z = float(st.norm.ppf(0.5 + confidence / 2.0))
    rows: List[Dict[str, object]] = []

    for label, k, total in zip(row_labels, k_arr, n_arr):
        if total <= 0:
            rows.append({"label": label, "successes": int(k), "n": 0,
                         "proportion": float("nan"), "ci_low": float("nan"),
                         "ci_high": float("nan"), "width": float("nan"),
                         "method": method})
            continue
        p = k / total

        if method == "wald":
            half = z * math.sqrt(p * (1 - p) / total)
            low, high = p - half, p + half
        elif method == "wilson":
            denom = 1.0 + z**2 / total
            centre = (p + z**2 / (2 * total)) / denom
            half = (z * math.sqrt(p * (1 - p) / total
                                  + z**2 / (4 * total**2)) / denom)
            low, high = centre - half, centre + half
        elif method == "agresti_coull":
            n_tilde = total + z**2
            p_tilde = (k + z**2 / 2) / n_tilde
            half = z * math.sqrt(p_tilde * (1 - p_tilde) / n_tilde)
            low, high = p_tilde - half, p_tilde + half
        else:  # clopper_pearson
            low = 0.0 if k == 0 else float(st.beta.ppf(alpha / 2, k, total - k + 1))
            high = (1.0 if k == total
                    else float(st.beta.ppf(1 - alpha / 2, k + 1, total - k)))

        low, high = max(0.0, float(low)), min(1.0, float(high))
        rows.append({
            "label": label,
            "successes": int(k),
            "n": int(total),
            "proportion": float(p),
            "ci_low": low,
            "ci_high": high,
            "width": high - low,
            "method": method,
        })

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# 3 — Group comparison
# ══════════════════════════════════════════════════════════════════════════════
def compare_groups(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    test: Literal[
        "auto", "welch", "student", "mannwhitney", "brunnermunzel", "ks",
        "permutation", "anova", "welch_anova", "kruskal",
    ] = "auto",
    alpha: float = 0.05,
    alternative: Literal["two-sided", "less", "greater"] = "two-sided",
    ci: Literal["auto", "t", "bootstrap", "none"] = "auto",
    confidence: float = 0.95,
    min_group_n: int = 2,
    n_resamples: int = 4999,
    random_state: int = 0,
) -> pd.DataFrame:
    """
    Test whether a numeric variable differs across the levels of a grouping.

    Handles both the two-group case (H₀: the groups have the same location) and
    the k-group case (H₀: all groups have the same location). The right test
    depends on the group count, the distribution shape and whether the spreads
    match; ``test='auto'`` resolves all three and records its reasoning in
    ``chosen_because``.

    Parameters
    ----------
    df : pd.DataFrame
        Long-format data: one row per observation.
    group_col : str
        Column holding the group labels.
    value_col : str
        Numeric column being compared.
    test : str, default 'auto'
        ``'auto'``, or one of the following.

        **Two groups**

        - ``'welch'`` — Welch's t-test. Compares means without assuming equal
          variances. The default parametric choice.
        - ``'student'`` — pooled-variance t-test. Only when spreads genuinely
          match; Welch loses almost nothing when they do.
        - ``'mannwhitney'`` — rank test on stochastic dominance. Reads as a
          median difference **only when the two distributions have a similar
          shape**; otherwise it answers "does A tend to exceed B?".
        - ``'brunnermunzel'`` — the heteroscedastic counterpart of
          Mann-Whitney: valid when the shapes and spreads differ, which is
          exactly where Mann-Whitney's median interpretation breaks.
        - ``'ks'`` — two-sample Kolmogorov-Smirnov. Tests whether the whole
          distributions differ (location, spread or shape), not just location.
        - ``'permutation'`` — the difference in means compared against its own
          randomisation distribution. Assumption-free apart from exchangeability
          and ideal at small n; costs ``n_resamples`` recomputations.

        **Three or more groups**

        - ``'anova'`` — classic one-way F test; assumes normality and equal
          variances.
        - ``'welch_anova'`` — F test corrected for unequal variances.
        - ``'kruskal'`` — rank-based, distribution-free.
    alpha : float, default 0.05
        Significance level.
    alternative : {'two-sided', 'less', 'greater'}, default 'two-sided'
        Direction, phrased as *first group vs second*. Only valid for two
        groups; k-group tests are inherently two-sided.
    ci : {'auto', 't', 'bootstrap', 'none'}, default 'auto'
        Interval around ``estimate``. ``'auto'`` gives a t-interval for the
        mean-based tests and no interval for the rank-based ones (a bootstrap
        would be needed, and it is slow enough to be worth asking for
        explicitly). ``'bootstrap'`` forces a BCa interval on the mean or median
        difference.
    confidence : float, default 0.95
        Confidence level for that interval.
    min_group_n : int, default 2
        Groups with fewer finite values are dropped and named in ``flags``.
    n_resamples : int, default 4999
        Resamples for ``'permutation'`` and for bootstrap intervals.
    random_state : int, default 0
        Seed for every resampling step, including the normality subsample.

    Returns
    -------
    pd.DataFrame
        A single row using the shared vocabulary, plus ``comparison``,
        ``n_groups`` and ``group_sizes``.

    Notes
    -----
    **On ``test='auto'``.** Choosing a test by first testing its assumptions on
    the same data is a two-stage procedure, and the literature is clear that it
    distorts the nominal error rate — the second p-value is conditioned on the
    first having passed. It is convenient and it is what most exploratory work
    does, but for a headline result the defensible route is to pre-specify the
    test from what the variable *is* (bounded, count, heavily skewed → rank or
    permutation, decided before looking) rather than from a screening test.
    ``chosen_because`` is recorded so a reader can see which route was taken.

    A significant p-value says the difference is unlikely to be noise; it says
    nothing about whether the difference matters. Read ``effect_size`` and the
    interval around ``estimate`` first — with a few thousand rows, effects far
    too small to act on will clear α = 0.05 comfortably.
    """
    labels, samples, flags = _split_groups(df, group_col, value_col, min_group_n)
    k = len(samples)
    if k < 2:
        raise ValueError(
            f"Need at least 2 groups with n ≥ {min_group_n} in '{group_col}'; "
            f"found {k}."
        )
    if k > 2 and alternative != "two-sided":
        raise ValueError(
            f"alternative='{alternative}' is only defined for two groups; "
            f"'{group_col}' has {k}."
        )

    resolved, reason, sel_flags = _resolve_test(samples, test, alpha, random_state)
    flags += sel_flags + _size_flags(samples)

    if k == 2:
        row, run_flags = _run_two_group(
            samples[0], samples[1], resolved, alpha, alternative,
            confidence, ci, n_resamples, random_state,
        )
        flags += run_flags
        comparison = f"{labels[0]} vs {labels[1]}"
    else:
        n_total = int(sum(len(s) for s in samples))
        if resolved == "anova":
            res = st.f_oneway(*samples)
            statistic, p_value = float(res.statistic), float(res.pvalue)
            effect, effect_type = _eta_squared(samples), "eta_squared"
        elif resolved == "welch_anova":
            statistic, p_value, _, _ = _welch_anova(samples)
            effect, effect_type = _eta_squared(samples), "eta_squared"
            flags.append("η² is the ordinary decomposition; approximate under Welch")
        else:
            res = st.kruskal(*samples)
            statistic, p_value = float(res.statistic), float(res.pvalue)
            effect = _eta_squared_h(statistic, k, n_total)
            effect_type = "eta_squared_H"
        row = {
            "test": resolved,
            "n": n_total,
            "statistic": statistic,
            "p_value": p_value,
            "decision": _decision(p_value, alpha),
            "estimate_type": "",
            "estimate": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "effect_size": effect,
            "effect_type": effect_type,
            "magnitude": _magnitude(effect, _ETA_LEVELS),
        }
        flags.append("omnibus test: significance means 'at least one group "
                     "differs' — use pairwise_comparisons to locate it")
        comparison = " | ".join(labels)

    out: Dict[str, object] = {
        "comparison": comparison,
        "n_groups": k,
        "group_sizes": "; ".join(f"{l}={len(s)}" for l, s in zip(labels, samples)),
    }
    out.update(row)
    out["alternative"] = alternative
    out["chosen_because"] = reason
    out["flags"] = _join_flags(flags)
    return pd.DataFrame([out])


def compare_paired(
    df: pd.DataFrame,
    col_a: str,
    col_b: str,
    test: Literal["auto", "ttest", "wilcoxon", "sign", "permutation"] = "auto",
    alpha: float = 0.05,
    alternative: Literal["two-sided", "less", "greater"] = "two-sided",
    confidence: float = 0.95,
    n_resamples: int = 4999,
    random_state: int = 0,
) -> pd.DataFrame:
    """
    Test two *related* measurements taken on the same units.

    Use this — not ``compare_groups`` — whenever each row contributes both
    numbers: before vs after, home vs away for the same club, two metrics on the
    same player. Pairing removes between-unit variation from the comparison,
    which usually makes it far more sensitive; treating paired data as
    independent throws that away and understates the effect.

    H₀: the differences ``col_a - col_b`` are centred on zero.

    Parameters
    ----------
    df : pd.DataFrame
        Wide-format data: one row per unit, the two measurements side by side.
    col_a, col_b : str
        The paired numeric columns. Differences are ``col_a - col_b``, so a
        positive ``estimate`` means A is larger.
    test : {'auto', 'ttest', 'wilcoxon', 'sign', 'permutation'}, default 'auto'
        - ``'ttest'`` — paired t-test; assumes the *differences* are roughly
          normal (not the original columns — a common mix-up).
        - ``'wilcoxon'`` — signed-rank test; uses the size and direction of the
          differences without assuming normality. Assumes they are symmetric.
        - ``'sign'`` — counts only the direction of each difference. Assumes
          nothing at all about shape and is correspondingly low-powered; the
          right call when the differences are wildly skewed.
        - ``'permutation'`` — randomly flips the sign of each difference to
          build the null distribution. Exchangeable, assumption-light, exact
          enough at small n.
        - ``'auto'`` — Shapiro-Wilk on the differences picks ``'ttest'`` or
          ``'wilcoxon'``.
    alpha : float, default 0.05
        Significance level.
    alternative : {'two-sided', 'less', 'greater'}, default 'two-sided'
        Direction of the alternative, in terms of ``col_a - col_b``.
    confidence : float, default 0.95
        Confidence level for the interval around the mean difference.
    n_resamples : int, default 4999
        Resamples for ``'permutation'``.
    random_state : int, default 0
        Seed for resampling and for the normality screen.

    Returns
    -------
    pd.DataFrame
        A single row in the shared vocabulary, plus ``n_pairs`` and ``n_dropped``.

    Notes
    -----
    Rows where either column is missing are dropped listwise — a pair is only
    usable whole — and the count is reported in ``n_dropped``. The two-stage
    caveat under ``compare_groups`` applies to ``test='auto'`` here as well.
    """
    _require_columns(df, [col_a, col_b])
    a, b = _clean_pair(df[col_a], df[col_b])
    n = len(a)
    n_dropped = int(len(df) - n)
    if n < 3:
        raise ValueError(f"Need at least 3 complete pairs, found {n}.")

    diff = a - b
    flags: List[str] = []
    if n_dropped:
        flags.append(f"{n_dropped} incomplete pair(s) dropped listwise")
    if n < _SMALL_N:
        flags.append(f"small n ({n})")

    if test == "auto":
        _, p_norm, _, _ = _shapiro(diff, _SHAPIRO_MAX_N, random_state)
        normal = bool(np.isfinite(p_norm) and p_norm > alpha)
        resolved = "ttest" if normal else "wilcoxon"
        reason = f"auto: differences {'pass' if normal else 'fail'} Shapiro-Wilk"
    else:
        allowed = ("ttest", "wilcoxon", "sign", "permutation")
        if test not in allowed:
            raise ValueError(f"test must be 'auto' or one of {allowed}.")
        resolved, reason = test, "user-specified"

    estimate_type = "mean difference"
    estimate = float(diff.mean())
    ci_low = ci_high = float("nan")

    if resolved == "ttest":
        res = st.ttest_rel(a, b, alternative=alternative)
        statistic, p_value = float(res.statistic), float(res.pvalue)
        interval = st.ttest_rel(a, b).confidence_interval(
            confidence_level=confidence
        )
        ci_low, ci_high = float(interval.low), float(interval.high)
        effect, effect_type = cohens_d(a, b, paired=True, hedges=True), "hedges_g_z"

    elif resolved == "wilcoxon":
        if np.all(diff == 0):
            raise ValueError("All paired differences are zero; nothing to test.")
        res = st.wilcoxon(diff, alternative=alternative)
        statistic, p_value = float(res.statistic), float(res.pvalue)
        effect = _rank_biserial_paired(diff)
        effect_type = "rank_biserial"
        estimate_type = "median difference"
        estimate = float(np.median(diff))
        n_zero = int((diff == 0).sum())
        if n_zero:
            flags.append(f"{n_zero} zero difference(s) excluded by Wilcoxon")

    elif resolved == "sign":
        nonzero = diff[diff != 0]
        n_pos = int((nonzero > 0).sum())
        res = st.binomtest(n_pos, len(nonzero), p=0.5, alternative=alternative)
        statistic, p_value = float(n_pos), float(res.pvalue)
        effect = float(2 * n_pos / len(nonzero) - 1) if len(nonzero) else float("nan")
        effect_type = "direction_bias"
        estimate_type = "median difference"
        estimate = float(np.median(diff))
        flags.append("sign test ignores magnitude — low power by construction")

    else:  # permutation
        res = st.permutation_test(
            (diff,), lambda x, axis=-1: np.mean(x, axis=axis),
            permutation_type="samples", n_resamples=n_resamples,
            alternative=alternative, vectorized=True, random_state=random_state,
        )
        statistic, p_value = float(res.statistic), float(res.pvalue)
        effect, effect_type = cohens_d(a, b, paired=True, hedges=True), "hedges_g_z"

    levels = _D_LEVELS if effect_type.startswith("hedges") else _DELTA_LEVELS
    return pd.DataFrame([{
        "comparison": f"{col_a} vs {col_b}",
        "test": resolved,
        "n_pairs": n,
        "n_dropped": n_dropped,
        "n": n,
        "statistic": statistic,
        "p_value": p_value,
        "decision": _decision(p_value, alpha),
        "estimate_type": estimate_type,
        "estimate": estimate,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "effect_size": effect,
        "effect_type": effect_type,
        "magnitude": _magnitude(effect, levels),
        "alternative": alternative,
        "chosen_because": reason,
        "flags": _join_flags(flags),
    }])


def pairwise_comparisons(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    test: Literal[
        "auto", "welch", "student", "mannwhitney", "brunnermunzel", "ks",
        "permutation",
    ] = "auto",
    correction: Literal["holm", "bonferroni", "fdr_bh", "fdr_by", "none"] = "holm",
    alpha: float = 0.05,
    ref_group: Optional[str] = None,
    ci: Literal["auto", "t", "bootstrap", "none"] = "auto",
    confidence: float = 0.95,
    min_group_n: int = 2,
    n_resamples: int = 4999,
    random_state: int = 0,
) -> pd.DataFrame:
    """
    Post-hoc: which specific groups differ, with the p-values corrected.

    An omnibus test (ANOVA, Kruskal-Wallis) only says *somewhere* among the
    groups there is a difference. This locates it, running every pair — or every
    group against one reference — and then correcting for the fact that many
    tests were run.

    Parameters
    ----------
    df : pd.DataFrame
        Long-format data.
    group_col, value_col : str
        Grouping column and the numeric column being compared.
    test : str, default 'auto'
        Any two-group test accepted by ``compare_groups``. With ``'auto'`` the
        choice is made **once, from all groups together**, and that single test
        is then applied to every pair — a per-pair decision would mix t-tests
        and rank tests inside one comparison table, which cannot be read as a
        coherent set.
    correction : {'holm', 'bonferroni', 'fdr_bh', 'fdr_by', 'none'}, default 'holm'
        Multiple-comparison adjustment; see ``p_adjust``.
    alpha : float, default 0.05
        Significance level, applied to ``p_adj``.
    ref_group : str, optional
        Compare every other group against this one only (k-1 tests instead of
        k(k-1)/2). Fewer tests means a lighter correction and more power — worth
        it whenever one group really is the baseline.
    ci : {'auto', 't', 'bootstrap', 'none'}, default 'auto'
        Passed through to each pairwise test.
    confidence : float, default 0.95
        Confidence level for those intervals.
    min_group_n : int, default 2
        Groups with fewer finite values are dropped.
    n_resamples : int, default 4999
        Resamples for permutation tests and bootstrap intervals.
    random_state : int, default 0
        Seed.

    Returns
    -------
    pd.DataFrame
        One row per pair — group labels, per-group n/mean/median, the test
        result, ``p_value``, ``p_adj``, ``decision`` (based on ``p_adj``) and the
        effect size — sorted by ``p_adj``.

    Notes
    -----
    ``decision`` is taken from ``p_adj``, never from the raw ``p_value``: with
    six groups there are fifteen pairs, and at α = 0.05 roughly one "significant"
    result is expected from noise alone. Both columns are kept so the cost of the
    correction is visible. Confidence intervals here are **not** simultaneously
    corrected — they are the pairwise intervals, so an interval can exclude zero
    while ``p_adj`` says the pair is not significant. Read ``p_adj`` for the
    decision and the interval for the plausible size of the difference.
    """
    labels, samples, flags = _split_groups(df, group_col, value_col, min_group_n)
    if len(samples) < 2:
        raise ValueError(f"Need at least 2 usable groups, found {len(samples)}.")

    resolved, reason, sel_flags = _resolve_test(
        samples, test, alpha, random_state, pairwise=True
    )
    flags += sel_flags

    index = {lab: i for i, lab in enumerate(labels)}
    if ref_group is not None:
        if str(ref_group) not in index:
            raise ValueError(
                f"ref_group='{ref_group}' is not a usable level of "
                f"'{group_col}'. Available: {labels}"
            )
        pairs = [(str(ref_group), lab) for lab in labels if lab != str(ref_group)]
    else:
        pairs = list(itertools.combinations(labels, 2))

    rows: List[Dict[str, object]] = []
    for lab_a, lab_b in pairs:
        a, b = samples[index[lab_a]], samples[index[lab_b]]
        row, run_flags = _run_two_group(
            a, b, resolved, alpha, "two-sided", confidence, ci,
            n_resamples, random_state,
        )
        entry: Dict[str, object] = {
            "group_a": lab_a,
            "group_b": lab_b,
            "n_a": int(len(a)),
            "n_b": int(len(b)),
            "mean_a": float(a.mean()),
            "mean_b": float(b.mean()),
            "median_a": float(np.median(a)),
            "median_b": float(np.median(b)),
        }
        entry.update(row)
        entry["flags"] = _join_flags(flags + run_flags + _size_flags([a, b]))
        rows.append(entry)

    out = pd.DataFrame(rows)
    out["p_adj"] = p_adjust(out["p_value"].to_numpy(dtype=float), method=correction)
    out["decision"] = [_decision(p, alpha) for p in out["p_adj"]]
    out["correction"] = correction
    out["n_comparisons"] = len(pairs)
    out["chosen_because"] = reason

    order = ["group_a", "group_b", "n_a", "n_b", "mean_a", "mean_b",
             "median_a", "median_b", "test", "statistic", "p_value", "p_adj",
             "decision", "estimate_type", "estimate", "ci_low", "ci_high",
             "effect_size", "effect_type", "magnitude", "correction",
             "n_comparisons", "chosen_because", "flags"]
    out = out[[c for c in order if c in out.columns]]
    return out.sort_values("p_adj", kind="stable").reset_index(drop=True)


def p_adjust(
    p_values: Union[Sequence[float], np.ndarray, pd.Series],
    method: Literal["holm", "bonferroni", "fdr_bh", "fdr_by", "none"] = "holm",
) -> np.ndarray:
    """
    Adjust a family of p-values for multiple comparisons.

    Run twenty independent tests at α = 0.05 and one "significant" result is
    expected from pure noise. These corrections make the reported p-values
    comparable against the original α despite that.

    Parameters
    ----------
    p_values : array-like of float
        Raw p-values. ``NaN`` entries are passed through untouched and excluded
        from the family size.
    method : {'holm', 'bonferroni', 'fdr_bh', 'fdr_by', 'none'}, default 'holm'
        - ``'holm'`` — step-down Bonferroni. Controls the probability of *any*
          false positive (FWER) and is uniformly more powerful than Bonferroni,
          under no extra assumptions. There is never a reason to prefer plain
          Bonferroni for its error control.
        - ``'bonferroni'`` — multiply by the number of tests. Simple, familiar,
          conservative.
        - ``'fdr_bh'`` — Benjamini-Hochberg. Controls the *proportion* of false
          positives among the rejections rather than forbidding them outright:
          far more powerful with many tests, and the standard choice for
          exploratory screening where a few false leads are acceptable.
        - ``'fdr_by'`` — Benjamini-Yekutieli, the version valid under arbitrary
          dependence between tests. More conservative than BH.
        - ``'none'`` — pass through unchanged.

    Returns
    -------
    np.ndarray
        Adjusted p-values, aligned to the input order and clipped to [0, 1].

    Notes
    -----
    FWER (Holm, Bonferroni) and FDR (BH, BY) answer different questions. Use
    FWER when a single false positive is costly — a headline claim, a decision
    that gets acted on. Use FDR when the output is a ranked shortlist to
    investigate further, which is what most correlation screens are. Deciding
    *after* seeing the p-values is how error control gets lost, so pick the
    family and the method before looking.
    """
    arr = np.asarray(p_values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("p_values must be one-dimensional.")
    out = np.full(arr.shape, np.nan, dtype=float)
    valid = np.isfinite(arr)
    p = arr[valid]
    n = p.size
    if n == 0:
        return out
    if method == "none":
        out[valid] = p
        return out
    if method == "bonferroni":
        out[valid] = np.minimum(p * n, 1.0)
        return out

    order = np.argsort(p, kind="stable")
    ranked = p[order]
    adjusted = np.empty(n, dtype=float)

    if method == "holm":
        # Step down: multiply by the number of tests still in play, then take a
        # running maximum so the sequence can never decrease.
        scaled = ranked * (n - np.arange(n))
        adjusted = np.maximum.accumulate(scaled)
    elif method in ("fdr_bh", "fdr_by"):
        # Step up: scale by n/rank, then a running minimum from the largest p
        # down, so the sequence stays monotone.
        factor = n / (np.arange(n) + 1.0)
        if method == "fdr_by":
            factor *= np.sum(1.0 / (np.arange(n) + 1.0))
        scaled = ranked * factor
        adjusted = np.minimum.accumulate(scaled[::-1])[::-1]
    else:
        raise ValueError(
            "method must be one of 'holm', 'bonferroni', 'fdr_bh', 'fdr_by', "
            f"'none'; got '{method}'."
        )

    restored = np.empty(n, dtype=float)
    restored[order] = np.minimum(adjusted, 1.0)
    out[valid] = restored
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 4 — Categorical association
# ══════════════════════════════════════════════════════════════════════════════
def association_test(
    df: pd.DataFrame,
    col_a: str,
    col_b: str,
    alpha: float = 0.05,
    yates: bool = True,
    bias_correction: bool = True,
    min_expected: float = 5.0,
) -> pd.DataFrame:
    """
    Test whether two categorical variables are associated (chi-square).

    H₀: the two variables are independent — knowing one tells you nothing about
    the other. The test compares the observed cell counts against the counts
    expected under independence.

    Parameters
    ----------
    df : pd.DataFrame
        Input data; rows missing either column are dropped.
    col_a, col_b : str
        The two categorical columns (rows and columns of the contingency table).
    alpha : float, default 0.05
        Significance level.
    yates : bool, default True
        Apply Yates' continuity correction on 2×2 tables. It makes the test more
        conservative; some argue it over-corrects. Ignored for larger tables.
    bias_correction : bool, default True
        Report Bergsma's bias-corrected Cramér's V. Plain V is biased upward,
        badly so when the table is large relative to n — a 5×4 table on 200 rows
        shows a sizeable V even under perfect independence.
    min_expected : float, default 5.0
        Expected-count floor for the assumption check. Cells below it are
        counted and flagged.

    Returns
    -------
    pd.DataFrame
        A single row: ``test``, table shape, ``n``, ``dof``, ``statistic``,
        ``p_value``, ``decision``, Cramér's V as ``effect_size`` with its
        ``magnitude``, ``chi2_uncorrected`` (the quantity V is derived from,
        reported separately because ``statistic`` may carry Yates' correction or
        be an odds ratio), ``min_expected``, ``pct_cells_below_min``,
        ``odds_ratio`` (2×2 only) and ``flags``.

    Notes
    -----
    Chi-square is an *asymptotic* test: its p-value is only trustworthy when the
    expected counts are big enough (the usual rule: all ≥ 1 and at most 20% of
    cells below 5). When a 2×2 table breaks that rule this function switches to
    Fisher's exact test automatically and says so in ``test`` and ``flags``;
    larger sparse tables are flagged but not switched, since an exact test there
    can be prohibitively expensive — collapsing rare categories is usually the
    better answer.

    A significant result means the variables are associated, not that one causes
    the other, and a large table can reach significance on a pattern confined to
    one or two cells. Use ``contingency_residuals`` to see *which* cells drive
    it before writing the finding up.
    """
    _require_columns(df, [col_a, col_b])
    work = df[[col_a, col_b]].dropna()
    if work.empty:
        raise ValueError(f"No complete rows for '{col_a}' and '{col_b}'.")
    table = pd.crosstab(work[col_a], work[col_b])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise ValueError(
            f"Need at least 2 levels in each variable; got "
            f"{table.shape[0]}×{table.shape[1]}."
        )

    n = int(table.to_numpy().sum())
    is_2x2 = table.shape == (2, 2)
    flags: List[str] = []

    res = st.chi2_contingency(table, correction=yates and is_2x2)
    expected = np.asarray(res.expected_freq, dtype=float)
    below = int((expected < min_expected).sum())
    pct_below = 100.0 * below / expected.size
    sparse = pct_below > 20.0 or expected.min() < 1.0

    test_name = "chi_square"
    statistic = float(res.statistic)
    p_value = float(res.pvalue)
    dof = int(res.dof)
    odds_ratio = float("nan")

    if is_2x2:
        fisher = st.fisher_exact(table.to_numpy())
        odds_ratio = float(fisher.statistic)
        if sparse:
            test_name = "fisher_exact"
            statistic, p_value = odds_ratio, float(fisher.pvalue)
            dof = 1
            flags.append(
                "expected counts too low for chi-square; used Fisher's exact"
            )
    elif sparse:
        flags.append(
            f"{pct_below:.0f}% of cells have expected < {min_expected:g} — "
            "chi-square p-value is unreliable; collapse rare categories"
        )

    # Reported uncorrected, because this is the quantity Cramér's V is built
    # from and the one contingency_residuals decomposes; ``statistic`` above
    # may carry Yates' correction or be an odds ratio from Fisher's exact.
    chi2_uncorrected = float(
        st.chi2_contingency(table, correction=False).statistic
    )
    v = cramers_v(table, bias_correction=bias_correction)
    if yates and is_2x2 and not sparse:
        flags.append("Yates' correction applied (2×2)")
    if n < 5 * expected.size:
        flags.append(f"only {n} rows across {expected.size} cells")

    return pd.DataFrame([{
        "variables": f"{col_a} × {col_b}",
        "test": test_name,
        "shape": f"{table.shape[0]}×{table.shape[1]}",
        "n": n,
        "dof": dof,
        "statistic": statistic,
        "p_value": p_value,
        "decision": _decision(p_value, alpha),
        "effect_size": v,
        "effect_type": "cramers_v_corrected" if bias_correction else "cramers_v",
        "magnitude": _magnitude_v(v, min(table.shape)),
        "chi2_uncorrected": chi2_uncorrected,
        "min_expected": float(expected.min()),
        "pct_cells_below_min": round(pct_below, 1),
        "odds_ratio": odds_ratio,
        "flags": _join_flags(flags),
    }])


def contingency_residuals(
    df: pd.DataFrame,
    col_a: str,
    col_b: str,
    kind: Literal["adjusted", "standardized", "contribution"] = "adjusted",
    long: bool = False,
) -> pd.DataFrame:
    """
    Locate *which* cells drive an association between two categorical variables.

    A significant chi-square is a table-level verdict; it never says where the
    dependence lives. Residuals decompose it cell by cell, turning "position and
    footedness are associated" into "left-footed defenders are the cell carrying
    the association".

    Parameters
    ----------
    df : pd.DataFrame
        Input data; rows missing either column are dropped.
    col_a, col_b : str
        Categorical columns forming the rows and columns of the table.
    kind : {'adjusted', 'standardized', 'contribution'}, default 'adjusted'
        - ``'adjusted'`` — ``(O-E) / sqrt(E(1-row%)(1-col%))``. Approximately
          standard normal, so ``|z| > 1.96`` marks a cell that deviates more
          than chance would explain at the 5% level. The only variant with a
          fixed interpretable threshold, hence the default.
        - ``'standardized'`` — Pearson residual ``(O-E)/sqrt(E)``. Its variance
          is below 1 and depends on the margins, so a fixed cut-off is
          misleading; useful for ranking, not for thresholding.
        - ``'contribution'`` — each cell's share of the total chi-square, in
          percent. Sums to 100 and answers "how much of the statistic came from
          here?".
    long : bool, default False
        Return tidy long format (``row``, ``col``, ``observed``, ``expected``,
        ``residual``) instead of the matrix. Convenient for sorting by residual
        or feeding a plotting function.

    Returns
    -------
    pd.DataFrame
        The residual matrix indexed like the contingency table, or its long form.

    Notes
    -----
    These are descriptive, not a corrected multiple-comparison procedure: an r×c
    table produces r·c residuals, so scanning them all for ``|z| > 1.96`` will
    turn up some false positives. Treat large residuals as the explanation of a
    significant omnibus test, not as independent findings, and apply ``p_adjust``
    to the two-sided normal p-values if cell-level claims are needed.
    """
    _require_columns(df, [col_a, col_b])
    work = df[[col_a, col_b]].dropna()
    if work.empty:
        raise ValueError(f"No complete rows for '{col_a}' and '{col_b}'.")
    table = pd.crosstab(work[col_a], work[col_b])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise ValueError("Need at least 2 levels in each variable.")

    observed = table.to_numpy(dtype=float)
    n = observed.sum()
    row_p = observed.sum(axis=1, keepdims=True) / n
    col_p = observed.sum(axis=0, keepdims=True) / n
    expected = row_p * col_p * n

    with np.errstate(divide="ignore", invalid="ignore"):
        pearson = (observed - expected) / np.sqrt(expected)
        if kind == "adjusted":
            residual = pearson / np.sqrt((1 - row_p) * (1 - col_p))
        elif kind == "standardized":
            residual = pearson
        elif kind == "contribution":
            chi2 = np.nansum(pearson**2)
            residual = 100.0 * pearson**2 / chi2 if chi2 > 0 else pearson * np.nan
        else:
            raise ValueError(
                "kind must be 'adjusted', 'standardized' or 'contribution'; "
                f"got '{kind}'."
            )

    matrix = pd.DataFrame(residual, index=table.index, columns=table.columns)
    if not long:
        return matrix

    tidy = (
        matrix.stack().rename("residual").reset_index()
        .rename(columns={col_a: "row", col_b: "col",
                         "level_0": "row", "level_1": "col"})
    )
    tidy["observed"] = observed.ravel()
    tidy["expected"] = expected.ravel()
    tidy["kind"] = kind
    return tidy[["row", "col", "observed", "expected", "residual", "kind"]]


# ══════════════════════════════════════════════════════════════════════════════
# 5 — Correlation
# ══════════════════════════════════════════════════════════════════════════════
def correlation_test(
    df: pd.DataFrame,
    cols: Optional[List[str]] = None,
    ignore_cols: Optional[List[str]] = None,
    pairs: Optional[Sequence[Tuple[str, str]]] = None,
    method: Literal["pearson", "spearman", "kendall"] = "pearson",
    alpha: float = 0.05,
    correction: Literal["holm", "bonferroni", "fdr_bh", "fdr_by", "none"] = "holm",
    confidence: float = 0.95,
    min_n: int = 4,
) -> pd.DataFrame:
    """
    Significance-tested correlations for every pair, ranked by strength.

    ``DataFrame.corr`` gives coefficients with no sample size, no p-value and no
    interval — a 0.6 from 12 rows looks identical to a 0.6 from 12 000. This
    returns the same coefficients with the evidence attached, sorted so the
    strongest relationships surface first. It is the natural companion to a
    correlation heatmap: the heatmap shows the shape, this table says which
    cells survive scrutiny.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    cols : list of str, optional
        Restrict to these numeric columns; ``None`` uses all of them.
    ignore_cols : list of str, optional
        Columns to exclude.
    pairs : sequence of (str, str), optional
        Test only these specific pairs. Pre-specifying a handful of pairs is
        statistically far stronger than screening every combination and
        reporting the winners — with 15 columns there are 105 pairs, and roughly
        five will clear p < 0.05 on noise alone.
    method : {'pearson', 'spearman', 'kendall'}, default 'pearson'
        - ``'pearson'`` — linear association; sensitive to outliers and assumes
          an approximately linear relationship.
        - ``'spearman'`` — Pearson on ranks. Captures any monotone relationship
          and shrugs off outliers and skew. The safer default for messy data.
        - ``'kendall'`` — concordance-based; more robust still and better
          behaved on small samples with ties, but slower and usually smaller in
          magnitude than Spearman (they are not interchangeable numbers).
    alpha : float, default 0.05
        Significance level, applied to ``p_adj``.
    correction : {'holm', 'bonferroni', 'fdr_bh', 'fdr_by', 'none'}, default 'holm'
        Multiple-comparison adjustment across all pairs tested. ``'fdr_bh'`` is
        often the better fit for a wide exploratory screen.
    confidence : float, default 0.95
        Confidence level for the interval around ``r``.
    min_n : int, default 4
        Pairs with fewer complete observations are skipped.

    Returns
    -------
    pd.DataFrame
        One row per pair: ``x``, ``y``, ``n``, ``r``, ``ci_low``, ``ci_high``,
        ``r_squared``, ``p_value``, ``p_adj``, ``decision``, ``magnitude``,
        ``flags`` — sorted by ``|r|`` descending.

    Notes
    -----
    Observations are dropped **pairwise**: each pair uses every row where both
    of its columns are present, so ``n`` can differ from row to row. That keeps
    the maximum information per pair, at the cost that the coefficients are not
    all computed on the same subset — worth checking when the ``n`` column
    varies a lot.

    ``r_squared`` is the shared variance, and it is the honest way to read a
    coefficient: r = 0.3 sounds substantial but accounts for 9% of the variation.
    None of this speaks to causation, and a near-zero r rules out only a
    *monotone* relationship — a clean U-shape gives r ≈ 0. Plot the pairs that
    matter.
    """
    if pairs is None:
        columns = _numeric_columns(df, cols, ignore_cols)
        if len(columns) < 2:
            raise ValueError("Need at least two numeric columns to correlate.")
        pair_list = list(itertools.combinations(columns, 2))
    else:
        pair_list = [(str(a), str(b)) for a, b in pairs]
        _require_columns(df, sorted({c for pair in pair_list for c in pair}))

    rows: List[Dict[str, object]] = []
    for x_col, y_col in pair_list:
        x, y = _clean_pair(df[x_col], df[y_col])
        n = len(x)
        flags: List[str] = []
        r = p_value = float("nan")
        ci_low = ci_high = float("nan")

        if n < min_n:
            flags.append(f"n={n} below min_n={min_n}: not tested")
        elif np.ptp(x) == 0 or np.ptp(y) == 0:
            flags.append("zero variance in one column")
        else:
            if method == "pearson":
                res = st.pearsonr(x, y)
            elif method == "spearman":
                res = st.spearmanr(x, y)
            else:
                res = st.kendalltau(x, y)
            r, p_value = float(res.statistic), float(res.pvalue)
            ci_low, ci_high = _fisher_ci(r, n, method, confidence)
            if n < _SMALL_N:
                flags.append(f"small n ({n}): interval is wide and unstable")

        rows.append({
            "x": x_col,
            "y": y_col,
            "method": method,
            "n": n,
            "r": r,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "r_squared": r**2 if np.isfinite(r) else float("nan"),
            "p_value": p_value,
            "magnitude": _magnitude(r, _R_LEVELS),
            "flags": _join_flags(flags),
        })

    out = pd.DataFrame(rows)
    out["p_adj"] = p_adjust(out["p_value"].to_numpy(dtype=float), method=correction)
    out["decision"] = [_decision(p, alpha) for p in out["p_adj"]]
    out["correction"] = correction
    out["n_comparisons"] = int(np.isfinite(out["p_value"]).sum())
    if correction == "none" and len(out) > 1:
        out["flags"] = out["flags"].where(
            out["flags"].astype(str) != "",
            f"{len(out)} uncorrected tests: expect false positives",
        )

    order = ["x", "y", "method", "n", "r", "ci_low", "ci_high", "r_squared",
             "p_value", "p_adj", "decision", "magnitude", "correction",
             "n_comparisons", "flags"]
    out = out[[c for c in order if c in out.columns]]
    return (
        out.assign(_abs=out["r"].abs())
        .sort_values("_abs", ascending=False, kind="stable", na_position="last")
        .drop(columns="_abs")
        .reset_index(drop=True)
    )


def partial_correlation(
    df: pd.DataFrame,
    x: str,
    y: str,
    covar: Union[str, Sequence[str]],
    method: Literal["pearson", "spearman"] = "pearson",
    alpha: float = 0.05,
    confidence: float = 0.95,
) -> pd.DataFrame:
    """
    Correlation between two variables with the influence of others removed.

    The standard answer to "is this relationship real, or is something else
    driving both?". Both variables are regressed on the control variables and
    the correlation is recomputed on what is left over, so the result describes
    the association that survives once the controls are accounted for.

    The zero-order (uncontrolled) coefficient is returned alongside so the two
    can be read together: a partial r far below the zero-order r means the
    controls explained most of the apparent relationship.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    x, y : str
        The two numeric columns of interest.
    covar : str or sequence of str
        Control variable(s). Numeric columns enter directly; categorical
        columns are dummy-coded automatically (first level dropped), so
        controlling for something like a league or position works out of the box.
    method : {'pearson', 'spearman'}, default 'pearson'
        ``'spearman'`` rank-transforms every variable before residualising —
        robust to outliers and monotone non-linearity, and the standard
        approximation rather than an exact rank statistic.
    alpha : float, default 0.05
        Significance level.
    confidence : float, default 0.95
        Confidence level for the interval around the partial r.

    Returns
    -------
    pd.DataFrame
        A single row: ``x``, ``y``, ``covar``, ``n``, ``r`` (partial),
        ``r_zero_order``, ``ci_low``, ``ci_high``, ``r_squared``, ``p_value``,
        ``decision``, ``magnitude``, ``flags``.

    Notes
    -----
    Rows missing *any* of the variables are dropped listwise, so adding controls
    shrinks n — that alone can move the coefficient, which is why ``n`` is
    reported. The residualising is linear: a control with a curved effect is
    only partly removed, and controlling for a variable that sits on the causal
    path between x and y removes the very effect being measured. This is
    statistical adjustment, not experimental control — it handles the
    confounders present in the data, never the ones absent from it, so the
    result is still an association.
    """
    covars = [covar] if isinstance(covar, str) else list(covar)
    if not covars:
        raise ValueError("At least one control variable is required.")
    _require_columns(df, [x, y, *covars])
    if x in covars or y in covars:
        raise ValueError("x and y cannot also appear in covar.")

    work = df[[x, y, *covars]].dropna()
    flags: List[str] = []
    n_dropped = int(len(df) - len(work))
    if n_dropped:
        flags.append(f"{n_dropped} row(s) dropped listwise")

    numeric_cov = [c for c in covars if _is_numeric_like(work[c])]
    categorical_cov = [c for c in covars if c not in numeric_cov]
    design = work[numeric_cov].astype(float) if numeric_cov else pd.DataFrame(
        index=work.index
    )
    if categorical_cov:
        dummies = pd.get_dummies(
            work[categorical_cov], drop_first=True, dtype=float
        )
        design = pd.concat([design, dummies], axis=1)
        flags.append(f"dummy-coded: {', '.join(categorical_cov)}")

    xv = pd.to_numeric(work[x], errors="coerce").to_numpy(dtype=float)
    yv = pd.to_numeric(work[y], errors="coerce").to_numpy(dtype=float)
    cv = design.to_numpy(dtype=float)
    keep = np.isfinite(xv) & np.isfinite(yv) & np.isfinite(cv).all(axis=1)
    xv, yv, cv = xv[keep], yv[keep], cv[keep]

    n = len(xv)
    k = cv.shape[1]
    if n < k + 4:
        raise ValueError(
            f"Need at least {k + 4} complete rows for {k} control term(s); "
            f"found {n}."
        )

    if method == "spearman":
        xv, yv = st.rankdata(xv), st.rankdata(yv)
        cv = np.column_stack([st.rankdata(cv[:, j]) for j in range(k)])
    elif method != "pearson":
        raise ValueError("method must be 'pearson' or 'spearman'.")

    zero_order = float(st.pearsonr(xv, yv).statistic)

    design_matrix = np.column_stack([np.ones(n), cv])
    coef_x, *_ = np.linalg.lstsq(design_matrix, xv, rcond=None)
    coef_y, *_ = np.linalg.lstsq(design_matrix, yv, rcond=None)
    res_x = xv - design_matrix @ coef_x
    res_y = yv - design_matrix @ coef_y

    if np.ptp(res_x) == 0 or np.ptp(res_y) == 0:
        raise ValueError(
            "The control variables explain one of the columns completely; "
            "no residual variation is left to correlate."
        )

    r = float(st.pearsonr(res_x, res_y).statistic)
    dof = n - 2 - k
    t_stat = r * math.sqrt(dof / max(1e-12, 1 - r**2))
    p_value = float(2 * st.t.sf(abs(t_stat), dof))
    ci_low, ci_high = _fisher_ci(r, n, "pearson", confidence, n_covar=k)

    if abs(zero_order) > 1e-9 and abs(r) < 0.5 * abs(zero_order):
        flags.append("controls absorb most of the raw association")
    if n < _SMALL_N + k:
        flags.append(f"small n ({n}) relative to {k} control term(s)")

    return pd.DataFrame([{
        "x": x,
        "y": y,
        "covar": ", ".join(covars),
        "method": method,
        "n": n,
        "n_covar_terms": k,
        "r": r,
        "r_zero_order": zero_order,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "r_squared": r**2,
        "p_value": p_value,
        "decision": _decision(p_value, alpha),
        "magnitude": _magnitude(r, _R_LEVELS),
        "flags": _join_flags(flags),
    }])


# ══════════════════════════════════════════════════════════════════════════════
# 6 — Effect sizes
# ══════════════════════════════════════════════════════════════════════════════
def cohens_d(
    a: Union[pd.Series, np.ndarray, Sequence[float]],
    b: Union[pd.Series, np.ndarray, Sequence[float]],
    paired: bool = False,
    hedges: bool = True,
) -> float:
    """
    Standardised mean difference between two samples.

    Expresses the gap between the means in standard deviations, which makes it
    comparable across variables measured on different scales — and, unlike a
    p-value, independent of sample size.

    Parameters
    ----------
    a, b : array-like
        The two samples. Sign follows ``a - b``.
    paired : bool, default False
        Treat the inputs as matched pairs and standardise by the standard
        deviation of the *differences* (Cohen's dz). Requires equal lengths;
        non-finite pairs are dropped together.
    hedges : bool, default True
        Apply Hedges' small-sample correction. Cohen's d overestimates the
        effect at small n by roughly ``3/(4·df-1)``; the correction is
        negligible past n ≈ 50 and there is no reason to switch it off.

    Returns
    -------
    float
        The effect size — 0.2 small, 0.5 medium, 0.8 large by convention.
        ``NaN`` when there is no usable variation.

    Notes
    -----
    The unpaired version pools the two standard deviations, which assumes they
    are comparable. When the spreads differ sharply the pooled value describes
    neither group and a rank-based measure such as ``cliffs_delta`` is the more
    honest summary.
    """
    if paired:
        xa, xb = _clean_pair(a, b)
        diff = xa - xb
        n = len(diff)
        if n < 2:
            return float("nan")
        sd = float(diff.std(ddof=1))
        if sd == 0:
            return float("nan")
        d = float(diff.mean() / sd)
        dof = n - 1
    else:
        xa, xb = _clean(a), _clean(b)
        n1, n2 = len(xa), len(xb)
        if n1 < 2 or n2 < 2:
            return float("nan")
        v1, v2 = xa.var(ddof=1), xb.var(ddof=1)
        dof = n1 + n2 - 2
        pooled = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / dof)
        if pooled == 0:
            return float("nan")
        d = float((xa.mean() - xb.mean()) / pooled)

    if hedges and dof > 1:
        d *= 1.0 - 3.0 / (4.0 * dof - 1.0)
    return d


def cliffs_delta(
    a: Union[pd.Series, np.ndarray, Sequence[float]],
    b: Union[pd.Series, np.ndarray, Sequence[float]],
) -> float:
    """
    Non-parametric effect size: how often one sample exceeds the other.

    ``δ = P(a > b) - P(a < b)``, on a -1…+1 scale. δ = 0.5 means a value drawn
    from ``a`` exceeds one drawn from ``b`` 75% of the time; δ = 1 means the two
    samples do not overlap at all. Unlike Cohen's d it assumes nothing about
    shape or equal spread, which makes it the natural partner to Mann-Whitney
    or Brunner-Munzel.

    Parameters
    ----------
    a, b : array-like
        The two samples; non-finite values are dropped independently.

    Returns
    -------
    float
        Cliff's delta. Conventional cut-points: 0.147 negligible, 0.33 small,
        0.474 medium, above that large. ``NaN`` if either sample is empty.

    Notes
    -----
    Computed from the Mann-Whitney U statistic (``δ = 2U/(n₁n₂) - 1``), which is
    identical to counting every pairwise comparison but runs in ``O(n log n)``
    instead of ``O(n₁n₂)`` and handles ties correctly. For two independent
    samples this is numerically the same quantity as the rank-biserial
    correlation.
    """
    xa, xb = _clean(a), _clean(b)
    if xa.size == 0 or xb.size == 0:
        return float("nan")
    u = float(st.mannwhitneyu(xa, xb, alternative="two-sided").statistic)
    return 2.0 * u / (xa.size * xb.size) - 1.0


def cramers_v(
    table: Union[pd.DataFrame, np.ndarray],
    bias_correction: bool = True,
) -> float:
    """
    Strength of association between two categorical variables, on a 0…1 scale.

    Chi-square grows with sample size and cannot be compared across tables;
    Cramér's V normalises it into an interpretable measure of association
    strength. 0 means independence, 1 means one variable determines the other.

    Parameters
    ----------
    table : pd.DataFrame or np.ndarray
        A contingency table of counts (e.g. from ``pd.crosstab``).
    bias_correction : bool, default True
        Apply Bergsma's (2013) correction. Uncorrected V is biased upward, and
        the bias grows with the number of cells relative to n — a large sparse
        table can post a respectable V under exact independence.

    Returns
    -------
    float
        Cramér's V. The conventional 0.1/0.3/0.5 cut-points assume a 2×2 table;
        for larger tables divide them by ``sqrt(min(rows, cols) - 1)``, which is
        what ``association_test`` reports in its ``magnitude`` column.
    """
    counts = (table.to_numpy(dtype=float) if isinstance(table, pd.DataFrame)
              else np.asarray(table, dtype=float))
    if counts.ndim != 2 or min(counts.shape) < 2:
        raise ValueError("table must be a 2-D contingency table with ≥2 rows/cols.")
    n = float(counts.sum())
    if n <= 0:
        return float("nan")

    chi2 = float(st.chi2_contingency(counts, correction=False).statistic)
    phi2 = chi2 / n
    r, c = counts.shape

    if not bias_correction:
        return float(math.sqrt(phi2 / (min(r, c) - 1)))

    phi2_corrected = max(0.0, phi2 - (r - 1) * (c - 1) / (n - 1))
    r_corrected = r - (r - 1) ** 2 / (n - 1)
    c_corrected = c - (c - 1) ** 2 / (n - 1)
    denominator = min(r_corrected, c_corrected) - 1
    if denominator <= 0:
        return float("nan")
    return float(math.sqrt(phi2_corrected / denominator))
