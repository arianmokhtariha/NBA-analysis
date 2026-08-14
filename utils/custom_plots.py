from __future__ import annotations

import math
from typing import Callable, List, Literal, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import scipy.cluster.hierarchy as sch
import scipy.stats as stats
from plotly.subplots import make_subplots
from scipy.spatial.distance import squareform


# ── Shared aesthetic constants ───────────────────────────────────────────────
PALETTE = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA",
    "#FFA15A", "#19D3F3", "#FF6692",
]
# 10-colour qualitative palette shared by distribution_plot and box_plot
_NUMERICAL_COLORS = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
]
_CATEGORICAL_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
]
_OTHER_COLOR = "#4a4a4a"

_DARK_BG = "#0e1117"
_PLOT_BG = "#1a1a1a"
_GRID_CLR = "rgba(128,128,128,0.2)"
_FONT_CLR = "white"

# Subplot-grid layout budget, in px. Every grid dimension derives from these
# three tokens, so grids stay uniform at any size. See _grid_geometry.
_ROW_GAP_PX = 90     # between rows: lower row's title + upper row's tick labels
_COL_GAP_PX = 110    # between columns: tick labels + breathing room
_ROW_PLOT_PX = 260   # drawing area reserved for one subplot row

# Diverging RdBu (blue = positive, red = negative) for bubble_plot's colour axis.
# Markers carry no text, so its light midpoint costs nothing there.
_RDBU = [
    [0.0,  "#B2182B"],
    [0.1,  "#D6604D"],
    [0.2,  "#F4A582"],
    [0.35, "#FDDBC7"],
    [0.5,  "#F7F7F7"],
    [0.65, "#D1E5F0"],
    [0.8,  "#92C5DE"],
    [0.9,  "#4393C3"],
    [1.0,  "#2166AC"],
]

# Dark-surface diverging ramp for correlation_heatmap, where every cell carries
# a white r-value label. Classic RdBu peaks near-white at r ≈ 0 (1.1:1 against
# white text — illegible), so this ramp is anchored on a neutral dark slate at
# the midpoint and interpolated outward in OKLab to the same red/blue poles.
# Every stop clears WCAG 4.5:1 against white (worst case 4.6:1 at the poles) and
# lightness is monotone along each arm, so salience now scales with |r| — weak
# correlations recede instead of glaring. Plotly's heatmap ``textfont.color`` is
# scalar-only, so per-cell adaptive text colour is not an option; the ramp has to
# carry the legibility.
_CORR_DIVERGING = [
    [0.0, "#E3223A"],
    [0.1, "#C90430"],
    [0.2, "#A61A30"],
    [0.3, "#7C2B35"],
    [0.4, "#503038"],
    [0.5, "#272C35"],
    [0.6, "#273B55"],
    [0.7, "#204978"],
    [0.8, "#16579A"],
    [0.9, "#1566B6"],
    [1.0, "#2877C8"],
]

# Severity ramp for the missing-values plot: healthy green → amber → alarm red.
_SEVERITY_STOPS: List[Tuple[float, str]] = [
    (0.0, "#00CC96"),
    (0.5, "#FFA15A"),
    (1.0, "#EF553B"),
]


# ── Private helpers ──────────────────────────────────────────────────────────
def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert a ``#rrggbb`` string to an ``(r, g, b)`` int tuple."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Return an ``rgba(...)`` string from a hex colour and an alpha in [0, 1]."""
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha})"


def _interp_hex(frac: float, stops: List[Tuple[float, str]]) -> str:
    """
    Linearly interpolate a hex colour along ordered ``(position, hex)`` stops.

    Parameters
    ----------
    frac : float
        Position in [0, 1]; clamped to that range.
    stops : list of (float, str)
        Ordered control points (ascending positions) as ``(pos, '#rrggbb')``.

    Returns
    -------
    str
        The interpolated ``#rrggbb`` colour.
    """
    frac = min(1.0, max(0.0, frac))
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= frac <= p1:
            t = 0.0 if p1 == p0 else (frac - p0) / (p1 - p0)
            r0, g0, b0 = _hex_to_rgb(c0)
            r1, g1, b1 = _hex_to_rgb(c1)
            r = round(r0 + (r1 - r0) * t)
            g = round(g0 + (g1 - g0) * t)
            b = round(b0 + (b1 - b0) * t)
            return f"#{r:02x}{g:02x}{b:02x}"
    return stops[-1][1]


def _grid_geometry(
    n_plots: int,
    n_cols: int,
    width: int,
    height: Optional[int] = None,
) -> Tuple[int, float, float, int]:
    """
    Compute subplot-grid geometry shared by the grid-based plots.

    Plotly expresses ``horizontal_spacing``/``vertical_spacing`` as a fraction of
    the *whole figure*, not as a gap between neighbouring panels. A fixed
    fraction therefore silently starves large grids: the gaps scale with the
    panel count while the figure does not, so at ``v_spacing=0.12`` with nine
    rows the eight gaps consume 96% of the figure and every subplot collapses to
    ~11px of drawing area.

    Both gaps are consequently declared as **pixel budgets** and converted
    against the dimension they are measured along, which holds the whitespace
    between panels visually constant however many panels there are. Row height
    is a flat per-row budget for the same reason: every subplot gets the same
    drawing area whether the grid holds two panels or twenty. Each spacing is
    capped at half its axis so gaps can never out-consume the panels even when
    the caller forces a small ``height``.

    Parameters
    ----------
    n_plots : int
        Number of subplots to lay out.
    n_cols : int
        Requested number of grid columns.
    width : int
        Figure width in px, used to convert the column gap to a fraction.
    height : int, optional
        Caller's explicit figure height in px. ``None`` derives it from the row
        count. Passed in so the pixel→fraction conversion uses the height the
        figure is actually rendered at.

    Returns
    -------
    tuple of (int, float, float, int)
        ``(n_rows, h_spacing, v_spacing, final_height)`` — the resolved figure
        height is returned so callers do not each re-derive it.
    """
    n_rows = math.ceil(n_plots / n_cols)
    final_height = (
        height if height is not None
        else n_rows * (_ROW_PLOT_PX + _ROW_GAP_PX)
    )
    v_spacing = (
        min(_ROW_GAP_PX / final_height, 0.5 / (n_rows - 1)) if n_rows > 1 else 0.0
    )
    h_spacing = (
        min(_COL_GAP_PX / width, 0.5 / (n_cols - 1)) if n_cols > 1 else 0.0
    )
    return n_rows, h_spacing, v_spacing, final_height


def _apply_base_layout(
    fig: go.Figure,
    *,
    title: str,
    subtitle: str = "",
    width: Optional[int],
    height: Optional[int],
) -> None:
    """
    Apply the house dark aesthetic and a centred bold title to a figure.

    Sets the ``plotly_dark`` template, the project background colours, the white
    Arial font and a centred size-18 bold title with an optional ``<sup>``
    subtitle line (used to carry a methodological note). Width and height are
    only written when not ``None`` so callers can defer to auto-sizing.

    Parameters
    ----------
    fig : go.Figure
        Figure mutated in place.
    title : str
        Main title text (already resolved — never empty in practice).
    subtitle : str, default ""
        Optional smaller subtitle rendered under the title.
    width : int, optional
        Figure width in px; skipped when ``None``.
    height : int, optional
        Figure height in px; skipped when ``None``.

    Returns
    -------
    None
    """
    title_html = f"<b>{title}</b>"
    if subtitle:
        title_html += f"<br><sup>{subtitle}</sup>"
    layout: dict = dict(
        template="plotly_dark",
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_PLOT_BG,
        font=dict(color=_FONT_CLR, family="Arial"),
        title=dict(
            text=title_html,
            font=dict(size=18, color=_FONT_CLR, family="Arial"),
            x=0.5, xanchor="center",
        ),
    )
    if width is not None:
        layout["width"] = width
    if height is not None:
        layout["height"] = height
    fig.update_layout(**layout)


def _p_stars(p: float) -> str:
    """Return significance stars for an (uncorrected) p-value."""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def _fmt_p(p: float) -> str:
    """Format a p-value as ``p<0.001`` below the floor, else ``p=0.043``."""
    return "p<0.001" if p < 0.001 else f"p={p:.3f}"


def _corr_similarity(
    corr: pd.DataFrame,
    order_on: Literal["signed", "abs"],
) -> np.ndarray:
    """
    Coerce a correlation matrix into a clean symmetric similarity matrix.

    Zero-variance columns produce all-NaN correlations; those pairs are treated
    as unrelated (r = 0) **for seriation only** — the displayed matrix keeps its
    NaNs. The result is re-symmetrised because floating-point noise makes
    ``corr`` very slightly asymmetric, which ``squareform`` rejects.

    Parameters
    ----------
    corr : pd.DataFrame
        Square correlation matrix.
    order_on : {'signed', 'abs'}
        ``'abs'`` folds sign away so that a strong negative pair counts as
        closely related; ``'signed'`` keeps direction.

    Returns
    -------
    np.ndarray
        Symmetric similarity matrix with a unit diagonal.
    """
    sim = np.nan_to_num(corr.to_numpy(dtype=float), nan=0.0)
    if order_on == "abs":
        sim = np.abs(sim)
    sim = (sim + sim.T) / 2.0
    np.fill_diagonal(sim, 1.0)
    return sim


def _corr_order(
    corr: pd.DataFrame,
    order: Literal["original", "cluster", "angle", "pc1", "alphabet"],
    order_on: Literal["signed", "abs"],
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Compute a seriation permutation for a correlation matrix.

    Seriation applies one permutation to **both** axes so related variables sit
    next to each other and the matrix collapses into blocks along the diagonal.
    Three data-driven strategies are offered because they answer different
    questions: ``'cluster'`` finds hard groups, ``'angle'`` and ``'pc1'`` lay the
    variables out along a smooth gradient with no group boundaries implied.

    ``'cluster'`` uses **average linkage** — the only common linkage family that
    stays valid on a *precomputed*, non-Euclidean distance. Ward and centroid
    linkage assume Euclidean raw coordinates and are silently wrong here. The
    leaf order is then refined by ``optimal_leaf_ordering``, which rotates each
    dendrogram branch to minimise the distance between adjacent leaves (the tree
    itself is unchanged — only the drawing order is).

    Parameters
    ----------
    corr : pd.DataFrame
        Square correlation matrix.
    order : {'original', 'cluster', 'angle', 'pc1', 'alphabet'}
        Seriation strategy; see ``correlation_heatmap`` for the descriptions.
    order_on : {'signed', 'abs'}
        Whether the underlying similarity keeps the sign of ``r``.

    Returns
    -------
    tuple of (np.ndarray, np.ndarray or None)
        The permutation of column indices, and the linkage matrix when
        ``order='cluster'`` (needed to cut flat clusters) else ``None``.
    """
    labels = corr.columns.tolist()
    n = len(labels)
    if order == "original" or n < 3:
        return np.arange(n), None
    if order == "alphabet":
        return np.array(sorted(range(n), key=lambda i: str(labels[i]))), None

    sim = _corr_similarity(corr, order_on)

    if order in ("angle", "pc1"):
        # Friendly (2002): project each variable onto the plane of the two
        # leading eigenvectors of the correlation matrix, then read the
        # variables off in angular order around that plane.
        _, eigvecs = np.linalg.eigh(sim)          # eigh returns ascending
        e1, e2 = eigvecs[:, -1], eigvecs[:, -2]
        if e1.sum() < 0:                          # eigenvector sign is arbitrary
            e1, e2 = -e1, -e2                     # pin it for reproducibility
        if order == "pc1":
            return np.argsort(e1, kind="stable"), None
        # arctan2 is the numerically safe form of Friendly's atan(e2/e1) branch
        # rule — it differs only in where the circle is cut open into a line.
        return np.argsort(np.arctan2(e2, e1), kind="stable"), None

    # order == 'cluster'. Both distances are bounded in [0, 1]: signed maps
    # r=+1 → 0 and r=-1 → 1, absolute maps |r|=1 → 0 and r=0 → 1.
    dist = (1.0 - sim) if order_on == "abs" else (1.0 - sim) / 2.0
    np.fill_diagonal(dist, 0.0)
    condensed = squareform(np.clip(dist, 0.0, None), checks=False)
    linkage = sch.linkage(condensed, method="average")
    # Optimal leaf ordering is O(n^3); trivial at EDA-sized matrices but worth
    # skipping if someone throws a few hundred columns at it.
    if n <= 150:
        linkage = sch.optimal_leaf_ordering(linkage, condensed)
    return sch.leaves_list(linkage), linkage


def _cluster_block_sizes(
    linkage: np.ndarray,
    perm: np.ndarray,
    n_clusters: int,
) -> List[int]:
    """
    Cut a dendrogram into ``n_clusters`` groups and measure the diagonal blocks.

    Because any leaf order of a dendrogram keeps each subtree contiguous, the
    flat clusters are guaranteed to form unbroken runs once reordered by
    ``perm`` — so the run lengths are exactly the block sizes to outline.

    Parameters
    ----------
    linkage : np.ndarray
        Linkage matrix from ``_corr_order``.
    perm : np.ndarray
        The leaf-order permutation applied to the matrix.
    n_clusters : int
        Number of flat clusters to cut.

    Returns
    -------
    list of int
        Consecutive block sizes along the reordered diagonal.
    """
    flat = sch.fcluster(linkage, t=n_clusters, criterion="maxclust")[perm]
    sizes: List[int] = []
    run = 1
    for i in range(1, len(flat)):
        if flat[i] == flat[i - 1]:
            run += 1
        else:
            sizes.append(run)
            run = 1
    sizes.append(run)
    return sizes


def _is_categorical_col(s: pd.Series) -> bool:
    """True for string/object/category dtypes, including PyArrow-backed variants."""
    if isinstance(s.dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(s):
        return True
    # catches ArrowDtype('large_string'), ArrowDtype('string'), etc.
    dtype_str = str(s.dtype).lower()
    return "string" in dtype_str or "object" in dtype_str


def _normalize_size(s: pd.Series, lo: float = 5.0, hi: float = 50.0) -> np.ndarray:
    """Min-max scale a numeric Series to [lo, hi]. Raises clearly if non-numeric."""
    if _is_categorical_col(s):
        raise TypeError(
            f"Column '{s.name}' is not numeric and cannot be used as bubble size. "
            "The `size` parameter must be a numerical column."
        )
    vals = s.to_numpy(dtype=float, na_value=np.nan)
    mn, mx = np.nanmin(vals), np.nanmax(vals)
    if mx == mn:
        return np.full(len(vals), (lo + hi) / 2)
    return lo + (vals - mn) / (mx - mn) * (hi - lo)


# ══════════════════════════════════════════════════════════════════════════════
# Single-variable & data-quality profiling
# ══════════════════════════════════════════════════════════════════════════════
def distribution_plot(
    df: pd.DataFrame,
    title: str = "",
    ignore_cols: Optional[List[str]] = None,
    top_n_categories: int = 10,
    n_cols: int = 2,
    show_mean_line: bool = True,
    show_median_line: bool = True,
    show_kde: bool = False,
    categorical_threshold: int = 10,
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    One-glance distribution overview for every column in a DataFrame.

    Each column becomes its own subplot: numeric columns (≥ ``categorical_threshold``
    distinct values) render as histograms with optional mean/median reference
    lines and a stats chip; everything else renders as a sorted count bar chart
    with an "Other" bucket capping the long tail at ``top_n_categories``. Reach
    for this first when meeting a new table — it surfaces skew, multimodality,
    dominant categories and rare levels in a single figure.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe to profile.
    title : str, default ""
        Main title; empty string auto-generates ``"Distribution Overview"``.
    ignore_cols : list of str, optional
        Column names to exclude from the grid.
    top_n_categories : int, default 10
        Maximum categories shown individually before the rest fold into "Other".
    n_cols : int, default 2
        Number of columns in the subplot grid.
    show_mean_line : bool, default True
        Overlay the mean as a dashed gold line on numeric subplots.
    show_median_line : bool, default True
        Overlay the median as a dotted red line on numeric subplots.
    show_kde : bool, default False
        Switch numeric subplots to a probability-density histogram and overlay a
        Gaussian KDE curve. The curve is silently skipped for a subplot with
        fewer than 5 distinct non-null values or zero variance (the histogram is
        still drawn). Mean/median lines still render (they are drawn on domain
        references, independent of the y-scale).
    categorical_threshold : int, default 10
        Numeric columns with fewer distinct values than this are treated as
        categorical (rendered as bars).
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` auto-computes it from the row count.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    ignore_cols = ignore_cols or []
    cols_to_plot = [
        col for col in df.columns
        if col not in ignore_cols and df[col].notna().any()
    ]
    if not cols_to_plot:
        raise ValueError("No valid columns to plot after filtering.")

    def _classify(col: str) -> str:
        s = df[col].dropna()
        if pd.api.types.is_numeric_dtype(s) and s.nunique() >= categorical_threshold:
            return "numerical"
        return "categorical"

    column_types = {col: _classify(col) for col in cols_to_plot}

    n_plots = len(cols_to_plot)
    n_rows, h_spacing, v_spacing, final_height = _grid_geometry(
        n_plots, n_cols, width=width, height=height
    )

    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=cols_to_plot,
        vertical_spacing=v_spacing,
        horizontal_spacing=h_spacing,
    )

    categorical_ymax: dict[tuple[int, int], float] = {}
    stats_annotations: list[dict] = []

    for idx, col in enumerate(cols_to_plot):
        row = idx // n_cols + 1
        col_pos = idx % n_cols + 1
        col_data = df[col].dropna()

        axis_suffix = "" if idx == 0 else str(idx + 1)
        xref = f"x{axis_suffix}"
        yref_domain = f"y{axis_suffix} domain"
        xref_domain = f"x{axis_suffix} domain"

        if column_types[col] == "numerical":
            bar_color = _NUMERICAL_COLORS[idx % len(_NUMERICAL_COLORS)]
            hist_kwargs: dict = dict(
                x=col_data,
                name=col,
                marker_color=bar_color,
                showlegend=False,
                autobinx=True,
            )
            if show_kde:
                hist_kwargs["histnorm"] = "probability density"
            fig.add_trace(go.Histogram(**hist_kwargs), row=row, col=col_pos)

            if show_kde and col_data.nunique() >= 5 and col_data.var() > 0:
                arr = col_data.to_numpy(dtype=float)
                kde = stats.gaussian_kde(arr)
                xs = np.linspace(arr.min(), arr.max(), 200)
                fig.add_trace(
                    go.Scatter(
                        x=xs,
                        y=kde(xs),
                        mode="lines",
                        line=dict(color="rgba(255,255,255,0.85)", width=2),
                        showlegend=False,
                        hoverinfo="skip",
                    ),
                    row=row, col=col_pos,
                )

            mean_val = col_data.mean()
            median_val = col_data.median()

            if show_mean_line:
                fig.add_shape(
                    type="line",
                    x0=mean_val, x1=mean_val, y0=0, y1=1,
                    xref=xref, yref=yref_domain,
                    line=dict(color="#FFD700", width=2.5, dash="dash"),
                )
            if show_median_line:
                fig.add_shape(
                    type="line",
                    x0=median_val, x1=median_val, y0=0, y1=1,
                    xref=xref, yref=yref_domain,
                    line=dict(color="#FF6B6B", width=2.5, dash="dot"),
                )

            annotation_lines = []
            if show_mean_line:
                annotation_lines.append(
                    f'<span style="color:#FFD700;">━━</span> Mean: {mean_val:.2f}'
                )
            if show_median_line:
                annotation_lines.append(
                    f'<span style="color:#FF6B6B;">⋯⋯</span> Median: {median_val:.2f}'
                )
            if annotation_lines:
                stats_annotations.append(dict(
                    text="<br>".join(annotation_lines),
                    xref=xref_domain, yref=yref_domain,
                    x=0.98, y=0.98,
                    xanchor="right", yanchor="top",
                    showarrow=False,
                    font=dict(size=10, color="#fafafa"),
                    bgcolor="rgba(0,0,0,0.6)",
                    bordercolor="#2d2d2d",
                    borderwidth=1,
                    borderpad=4,
                ))

        else:  # categorical
            value_counts = col_data.value_counts()
            total = len(col_data)

            if len(value_counts) > top_n_categories:
                top = value_counts.head(top_n_categories)
                rest = value_counts.iloc[top_n_categories:].sum()
                categories = [*top.index, "Other"]
                counts = [*top.values, rest]
                colors = [
                    _CATEGORICAL_COLORS[i % len(_CATEGORICAL_COLORS)]
                    for i in range(top_n_categories)
                ] + [_OTHER_COLOR]
            else:
                categories = list(value_counts.index)
                counts = list(value_counts.values)
                colors = [
                    _CATEGORICAL_COLORS[i % len(_CATEGORICAL_COLORS)]
                    for i in range(len(categories))
                ]

            pcts = [round(c / total * 100, 2) for c in counts]

            order = sorted(range(len(counts)), key=lambda i: counts[i], reverse=True)
            categories = [categories[i] for i in order]
            counts = [counts[i] for i in order]
            pcts = [pcts[i] for i in order]
            colors = [colors[i] for i in order]

            # 1.25x headroom so the tallest bar's outside % label never clips
            categorical_ymax[(row, col_pos)] = max(counts) * 1.25

            fig.add_trace(
                go.Bar(
                    x=categories,
                    y=counts,
                    name=col,
                    marker_color=colors,
                    showlegend=False,
                    text=[f"{p}%" for p in pcts],
                    textposition="outside",
                    textfont=dict(size=10),
                    hovertext=[
                        f"{cat}<br>Count: {n}<br>Percentage: {p}%"
                        for cat, n, p in zip(categories, counts, pcts)
                    ],
                    hoverinfo="text",
                    cliponaxis=False,
                ),
                row=row, col=col_pos,
            )

    fig.update_layout(
        height=final_height,
        width=width,
        autosize=False,
        showlegend=False,
        # 'show' (not 'hide') forces every bar label to render
        uniformtext_minsize=8,
        uniformtext_mode="show",
        annotations=list(fig.layout.annotations) + stats_annotations,
    )
    fig.update_xaxes(
        showgrid=True, gridwidth=0.5, gridcolor="#2d2d2d",
        tickangle=-45, tickfont=dict(size=10),
    )
    fig.update_yaxes(showgrid=True, gridwidth=0.5, gridcolor="#2d2d2d")
    for (r, c), ymax in categorical_ymax.items():
        fig.update_yaxes(range=[0, ymax], row=r, col=c)

    _apply_base_layout(
        fig, title=title or "Distribution Overview",
        width=width, height=final_height,
    )
    return fig


def box_plot(
    df: pd.DataFrame,
    ignore_cols: Optional[List[str]] = None,
    kind: Literal["box", "violin"] = "box",
    whis: float = 1.5,
    show_points: Literal["outliers", "all", False] = "outliers",
    orientation: Literal["horizontal", "vertical"] = "horizontal",
    n_cols: int = 2,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Per-column box or violin grid with an honest, tunable whisker fence.

    Every numeric column gets its own subplot on an independent scale. Unlike a
    naive ``go.Box`` (which always draws Plotly's fixed 1.5×IQR whiskers), the
    box statistics here are precomputed and passed explicitly, so ``whis``
    genuinely moves both the whiskers and the outlier markers. Outlier points are
    overlaid as a lightly jittered scatter (precomputed boxes cannot auto-draw
    them), keeping the "Outliers: N (%)" annotation consistent with the drawing
    by construction.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    ignore_cols : list of str, optional
        Numeric columns to exclude. Entirely-null columns are dropped too.
    kind : {'box', 'violin'}, default 'box'
        ``'violin'`` draws a kernel-density violin per column with the box and
        mean line overlaid. For violins the ``whis`` fence drives the outlier
        *count annotation only* (the violin already renders the full density).
    whis : float, default 1.5
        IQR multiplier for the whisker / outlier fence. Whiskers extend to the
        last actual data point inside ``q1/q3 ± whis*IQR``.
    show_points : {'outliers', 'all', False}, default 'outliers'
        ``'outliers'`` overlays only points beyond the whiskers (violin:
        ``points='outliers'``); ``'all'`` overlays a jittered strip of every
        point (violin: ``points='all'``); ``False`` draws no point markers.
    orientation : {'horizontal', 'vertical'}, default 'horizontal'
        'horizontal' puts the value on the x-axis; 'vertical' on the y-axis.
    n_cols : int, default 2
        Number of columns in the subplot grid.
    title : str, default ""
        Main title; empty auto-generates ``"Box/Violin Plot Overview"``.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` auto-computes from the row count.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    ignore_cols = ignore_cols or []
    numerical_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    numerical_cols = [
        c for c in numerical_cols
        if c not in ignore_cols and df[c].notna().any()
    ]
    if not numerical_cols:
        raise ValueError(
            "No numerical columns with data remain after applying ignore_cols."
        )

    n = len(numerical_cols)
    n_rows, h_spacing, v_spacing, final_height = _grid_geometry(
        n, n_cols, width=width, height=height
    )
    is_h = orientation == "horizontal"
    orient = "h" if is_h else "v"
    rng = np.random.default_rng(0)

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=numerical_cols,
        horizontal_spacing=h_spacing,
        vertical_spacing=v_spacing,
    )

    outlier_stats: list[tuple[int, float]] = []
    for idx, col in enumerate(numerical_cols):
        data = df[col].dropna()
        q1, q3 = data.quantile(0.25), data.quantile(0.75)
        med, mean_val = data.median(), data.mean()
        iqr = q3 - q1
        lo_whisker = data[data >= q1 - whis * iqr].min()
        hi_whisker = data[data <= q3 + whis * iqr].max()
        outliers = data[(data < lo_whisker) | (data > hi_whisker)]
        outlier_stats.append((len(outliers), len(outliers) / len(data) * 100))

        r = idx // n_cols + 1
        c = idx % n_cols + 1
        color = _NUMERICAL_COLORS[idx % len(_NUMERICAL_COLORS)]

        if kind == "violin":
            v_kwargs: dict = dict(
                name="", marker_color=color, box_visible=True,
                meanline_visible=True, line=dict(width=2),
                showlegend=False, orientation=orient,
                # hard span: never draw KDE beyond observed data (e.g. below 0
                # for a non-negative metric)
                spanmode="hard",
                hovertemplate=f"<b>{col}</b>: %{{{'x' if is_h else 'y'}}}<extra></extra>",
            )
            v_kwargs["x" if is_h else "y"] = data
            if show_points == "all":
                v_kwargs.update(points="all", jitter=0.35, pointpos=0)
            elif show_points == "outliers":
                v_kwargs["points"] = "outliers"
            else:
                v_kwargs["points"] = False
            fig.add_trace(go.Violin(**v_kwargs), row=r, col=c)
        else:
            pos_axis = "y" if is_h else "x"
            box_kwargs: dict = {
                pos_axis: [0],
                "q1": [q1], "median": [med], "q3": [q3],
                "lowerfence": [lo_whisker], "upperfence": [hi_whisker],
                "mean": [mean_val],
                "orientation": orient, "name": "", "width": 0.5,
                "marker_color": color, "boxmean": True,
                "line": dict(width=2), "showlegend": False,
            }
            fig.add_trace(go.Box(**box_kwargs), row=r, col=c)

            pts: Optional[pd.Series] = None
            if show_points == "outliers":
                pts = outliers
            elif show_points == "all":
                pts = data
            if pts is not None and len(pts) > 0:
                jitter = np.clip(rng.normal(0, 0.08, len(pts)), -0.22, 0.22)
                vals = pts.to_numpy(dtype=float)
                sx, sy = (vals, jitter) if is_h else (jitter, vals)
                fig.add_trace(
                    go.Scatter(
                        x=sx, y=sy, mode="markers",
                        marker=dict(size=4, color="rgba(220,220,220,0.55)"),
                        showlegend=False,
                        hovertemplate=(
                            f"<b>{col}</b>: %{{{'x' if is_h else 'y'}}}<extra></extra>"
                        ),
                    ),
                    row=r, col=c,
                )

    annotations = list(fig.layout.annotations)
    for idx in range(n):
        n_out, pct = outlier_stats[idx]
        axis_idx = "" if idx == 0 else str(idx + 1)
        x_domain = fig.layout[f"xaxis{axis_idx}"].domain
        y_domain = fig.layout[f"yaxis{axis_idx}"].domain
        if is_h:
            # boxes horizontal → annotate INSIDE the subplot, top-right corner
            annotations.append(dict(
                text=f"Outliers: {n_out} ({pct:.1f}%)",
                xref="paper", yref="paper",
                x=x_domain[1] - 0.005, y=y_domain[1],
                xanchor="right", yanchor="top",
                showarrow=False,
                font=dict(size=11, color="#FFD700"),
                bgcolor="rgba(0,0,0,0.5)",
                bordercolor="#FFD700", borderwidth=1, borderpad=4,
            ))
        else:
            # boxes vertical → annotate below each subplot
            annotations.append(dict(
                text=f"Outliers: {n_out} ({pct:.1f}%)",
                xref="paper", yref="paper",
                x=(x_domain[0] + x_domain[1]) / 2, y=y_domain[0] - 0.02,
                xanchor="center", yanchor="top",
                showarrow=False,
                font=dict(size=11, color="#FFD700"),
                bgcolor="rgba(0,0,0,0.5)",
                bordercolor="#FFD700", borderwidth=1, borderpad=4,
            ))

    fig.update_layout(width=width, height=final_height, showlegend=False,
                      annotations=annotations)

    grid = dict(showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR)
    if is_h:
        # value on x → hide the (numeric position) category axis ticks on y
        fig.update_xaxes(showticklabels=True, **grid)
        fig.update_yaxes(showticklabels=False, range=[-0.6, 0.6], **grid)
    else:
        fig.update_xaxes(showticklabels=False, range=[-0.6, 0.6], **grid)
        fig.update_yaxes(showticklabels=True, **grid)

    default_title = f"{'Violin' if kind == 'violin' else 'Box'} Plot Overview"
    _apply_base_layout(
        fig, title=title or default_title,
        subtitle=f"Whisker fence: {whis}×IQR",
        width=width, height=final_height,
    )
    return fig


def ecdf_plot(
    df: pd.DataFrame,
    cols: Union[str, List[str]],
    group_col: Optional[str] = None,
    mark_percentiles: Optional[List[float]] = None,
    log_x: bool = False,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Empirical cumulative distribution (ECDF) — the assumption-free distribution view.

    An ECDF steps from 0 to 1 as x increases, reading directly as "what share of
    observations are ≤ x". Unlike a histogram it needs no bin-width choice and
    makes percentiles, ceilings/floors and stochastic dominance between groups
    easy to compare. Two modes: overlay several numeric columns, or split a
    single column by a categorical ``group_col``.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    cols : str or list of str
        Numeric column(s). With ``group_col`` set this must be a single column.
    group_col : str, optional
        Categorical column; draws one ECDF per level (capped at the 10 most
        frequent levels — the subtitle notes when capping happened).
    mark_percentiles : list of float, optional
        Percentiles in (0, 1) (e.g. ``[0.25, 0.5, 0.9]``): each curve gets a
        marker at its quantile value and faint dotted horizontal guides span the
        plot at each level.
    log_x : bool, default False
        Log-scale the x-axis. Nonpositive values are simply not displayable on a
        log axis (no data is mutated).
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` defaults to 620.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    cols_list = [cols] if isinstance(cols, str) else list(cols)
    for c in cols_list:
        if c not in df.columns:
            raise ValueError(f"Column '{c}' not found in the DataFrame.")
        if not pd.api.types.is_numeric_dtype(df[c]):
            raise ValueError(f"Column '{c}' must be numeric for an ECDF.")

    if mark_percentiles is not None:
        for p in mark_percentiles:
            if not 0.0 < p < 1.0:
                raise ValueError(
                    f"mark_percentiles values must be in (0, 1); got {p}."
                )

    if group_col is not None and len(cols_list) != 1:
        raise ValueError(
            "When group_col is set, `cols` must be a single column name."
        )

    fig = go.Figure()
    capped_note = ""

    def _add_curve(data: pd.Series, name: str, color: str) -> None:
        vals = np.sort(data.dropna().to_numpy(dtype=float))
        n = len(vals)
        if n == 0:
            return
        y = np.arange(1, n + 1) / n
        fig.add_trace(go.Scatter(
            x=vals, y=y, mode="lines", line_shape="hv",
            line=dict(color=color, width=2), name=f"{name} (n={n:,})",
            hovertemplate="x = %{x:.3g}<br>F(x) = %{y:.3f}<extra></extra>",
        ))
        if mark_percentiles:
            qs = np.quantile(vals, mark_percentiles)
            fig.add_trace(go.Scatter(
                x=qs, y=list(mark_percentiles), mode="markers",
                marker=dict(size=8, color=color,
                            line=dict(width=1, color="white")),
                showlegend=False,
                customdata=[int(p * 100) for p in mark_percentiles],
                hovertemplate="P%{customdata} = %{x:.3g}<extra></extra>",
            ))

    if group_col is None:
        for i, col in enumerate(cols_list):
            _add_curve(df[col], col, PALETTE[i % len(PALETTE)])
    else:
        if group_col not in df.columns:
            raise ValueError(f"Column '{group_col}' not found in the DataFrame.")
        col = cols_list[0]
        counts = df[group_col].value_counts()
        levels = counts.index.tolist()
        if len(levels) > 10:
            capped_note = f"top 10 of {len(levels)} groups shown"
            levels = levels[:10]
        for i, level in enumerate(levels):
            sub = df.loc[df[group_col] == level, col]
            _add_curve(sub, str(level), PALETTE[i % len(PALETTE)])

    if not fig.data:
        raise ValueError("No non-null observations to plot.")

    if mark_percentiles:
        for p in mark_percentiles:
            fig.add_hline(
                y=p, line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dot"),
            )

    if title:
        plot_title = title
    elif group_col is not None:
        plot_title = f"ECDF of {cols_list[0]} by {group_col}"
    elif len(cols_list) == 1:
        plot_title = f"ECDF of {cols_list[0]}"
    else:
        plot_title = "Empirical Cumulative Distribution"

    fig.update_layout(
        width=width, height=height if height is not None else 620,
        xaxis=dict(
            title=dict(text="value" if len(cols_list) > 1 else cols_list[0],
                       font=dict(size=13)),
            type="log" if log_x else "linear",
            showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR, zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="F(x) — share of observations ≤ x",
                       font=dict(size=13)),
            range=[0, 1.02], showgrid=True, gridwidth=0.5,
            gridcolor=_GRID_CLR, zeroline=False,
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0.4)", bordercolor="rgba(255,255,255,0.15)",
            borderwidth=1, font=dict(size=11, color=_FONT_CLR),
        ),
        margin=dict(l=80, r=60, t=100, b=80),
    )
    _apply_base_layout(
        fig, title=plot_title, subtitle=capped_note,
        width=width, height=height if height is not None else 620,
    )
    return fig


def qq_plot(
    df: pd.DataFrame,
    cols: Union[str, List[str]],
    dist: str = "norm",
    n_cols: int = 2,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Quantile-quantile grid — the eyeball check behind formal normality tests.

    For each column, sample quantiles are plotted against the theoretical
    quantiles of ``dist``; points hugging the gold reference line indicate a good
    fit, while systematic curvature reveals skew and fat/thin tails. This is the
    visual companion to Shapiro-Wilk-style tests: it motivates a normality test
    and explains *how* a distribution departs when the test rejects. A per-panel
    chip reports n, skewness and excess kurtosis.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    cols : str or list of str
        Numeric column(s); each must have ≥ 10 non-null values.
    dist : str, default 'norm'
        Any ``scipy.stats`` continuous distribution name (e.g. 'norm', 'expon',
        'logistic'). Validated via ``getattr(scipy.stats, dist)``.
    n_cols : int, default 2
        Number of columns in the subplot grid.
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` auto-computes from the row count.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    cols_list = [cols] if isinstance(cols, str) else list(cols)

    dist_obj = getattr(stats, dist, None)
    if not isinstance(dist_obj, stats.rv_continuous):
        raise ValueError(
            f"'{dist}' is not a scipy.stats continuous distribution. Try a name "
            "like 'norm', 'expon', 'logistic', or 'lognorm'."
        )

    offenders = []
    for c in cols_list:
        if c not in df.columns:
            offenders.append(f"{c} (missing)")
        elif not pd.api.types.is_numeric_dtype(df[c]):
            offenders.append(f"{c} (non-numeric)")
        elif df[c].dropna().shape[0] < 10:
            offenders.append(f"{c} (<10 non-null)")
    if offenders:
        raise ValueError(
            "Columns unusable for a QQ plot: " + ", ".join(offenders)
        )

    n = len(cols_list)
    n_rows, h_spacing, v_spacing, final_height = _grid_geometry(
        n, n_cols, width=width, height=height
    )

    fig = make_subplots(
        rows=n_rows, cols=n_cols, subplot_titles=cols_list,
        horizontal_spacing=h_spacing, vertical_spacing=v_spacing,
    )

    annotations = list(fig.layout.annotations)
    for idx, col in enumerate(cols_list):
        vals = df[col].dropna().to_numpy(dtype=float)
        (osm, osr), (slope, intercept, _) = stats.probplot(vals, dist=dist)
        r = idx // n_cols + 1
        c = idx % n_cols + 1
        color = _NUMERICAL_COLORS[idx % len(_NUMERICAL_COLORS)]

        fig.add_trace(go.Scatter(
            x=osm, y=osr, mode="markers",
            marker=dict(size=5, color=color, opacity=0.7,
                        line=dict(width=0.4, color="rgba(255,255,255,0.3)")),
            showlegend=False,
            hovertemplate=("theoretical = %{x:.3g}<br>"
                           "sample = %{y:.3g}<extra></extra>"),
        ), row=r, col=c)
        fig.add_trace(go.Scatter(
            x=osm, y=slope * osm + intercept, mode="lines",
            line=dict(color="#FFD700", width=2, dash="dash"),
            showlegend=False, hoverinfo="skip",
        ), row=r, col=c)

        axis_idx = "" if idx == 0 else str(idx + 1)
        annotations.append(dict(
            text=(f"n = {len(vals):,}<br>skew = {stats.skew(vals):.2f}"
                  f"<br>ex. kurt = {stats.kurtosis(vals):.2f}"),
            xref=f"x{axis_idx} domain", yref=f"y{axis_idx} domain",
            x=0.03, y=0.97, xanchor="left", yanchor="top", showarrow=False,
            font=dict(size=10, color="#fafafa"),
            bgcolor="rgba(0,0,0,0.6)", bordercolor="#2d2d2d",
            borderwidth=1, borderpad=4, align="left",
        ))

    fig.update_layout(width=width, height=final_height, showlegend=False,
                      annotations=annotations)
    fig.update_xaxes(showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR,
                     zeroline=False, tickfont=dict(size=10),
                     title=dict(text="theoretical quantiles",
                                font=dict(size=11)))
    fig.update_yaxes(showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR,
                     zeroline=False, tickfont=dict(size=10),
                     title=dict(text="sample quantiles", font=dict(size=11)))
    _apply_base_layout(
        fig, title=title or f"Q-Q Plots vs {dist}",
        width=width, height=final_height,
    )
    return fig


def missing_values_plot(
    df: pd.DataFrame,
    mode: Literal["bar", "matrix"] = "bar",
    ignore_cols: Optional[List[str]] = None,
    include_complete: bool = True,
    sample_n: int = 1000,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Missingness overview — the mandatory data-quality first look.

    ``'bar'`` ranks columns by percent missing with a severity colour ramp
    (green → amber → red); ``'matrix'`` renders the raw missingness grid over a
    row sample to expose *co-missingness* and temporal/insertion bands (columns
    that go missing together, or gaps in a time-ordered load).

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    mode : {'bar', 'matrix'}, default 'bar'
        Chart style (see summary).
    ignore_cols : list of str, optional
        Columns to exclude from the analysis.
    include_complete : bool, default True
        In ``'bar'`` mode, whether to also show fully-complete columns (dimmed
        grey). Raising is triggered only when everything is complete *and* this
        is ``False`` — nothing would remain to plot.
    sample_n : int, default 1000
        ``'matrix'`` mode: when the frame has more rows than this, take
        ``sample_n`` *evenly spaced* rows in original order (via ``np.linspace``
        indices). Even spacing is deliberate — random sampling would scramble
        row order and hide temporal/insertion missingness bands.
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` auto-computes from the layout.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    ignore_cols = ignore_cols or []
    cols = [c for c in df.columns if c not in ignore_cols]
    if not cols:
        raise ValueError("No columns remain after applying ignore_cols.")

    total_rows = len(df)
    miss_counts = df[cols].isna().sum()
    miss_pct = (miss_counts / total_rows * 100) if total_rows else miss_counts * 0.0
    overall = (
        df[cols].isna().to_numpy().sum() / (total_rows * len(cols)) * 100
        if total_rows else 0.0
    )
    subtitle = (
        f"{total_rows:,} rows · {len(cols)} columns · "
        f"{overall:.1f}% of cells missing"
    )

    if mode == "bar":
        ordered = miss_pct.sort_values(ascending=False)
        if not include_complete:
            ordered = ordered[ordered > 0]
        if ordered.empty:
            raise ValueError("Nothing to plot — no missing values.")

        cats = ordered.index.tolist()
        pcts = ordered.to_numpy(dtype=float)
        colors = [
            "#3a3a3a" if p == 0 else _interp_hex(p / 100.0, _SEVERITY_STOPS)
            for p in pcts
        ]
        texts = [
            f"{p:.1f}% ({int(miss_counts[c]):,} / {total_rows:,})"
            for c, p in zip(cats, pcts)
        ]
        fig = go.Figure(go.Bar(
            x=pcts, y=cats, orientation="h",
            marker=dict(color=colors),
            text=texts, textposition="outside", textfont=dict(size=10),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:.2f}% missing<extra></extra>",
        ))
        fig.update_layout(
            width=width,
            height=height if height is not None
            else max(360, 30 * len(cats) + 180),
            showlegend=False,
            xaxis=dict(title=dict(text="% missing", font=dict(size=13)),
                       range=[0, max(100.0, float(pcts.max()) * 1.15)],
                       showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
            margin=dict(l=160, r=90, t=110, b=70),
        )
        _apply_base_layout(
            fig, title=title or "Missing Values by Column", subtitle=subtitle,
            width=width,
            height=height if height is not None
            else max(360, 30 * len(cats) + 180),
        )
        return fig

    # ── matrix mode ───────────────────────────────────────────────────────────
    if include_complete is False and (miss_counts == 0).all():
        raise ValueError("Nothing to plot — no missing values.")

    cols_ordered = miss_pct.sort_values(ascending=False).index.tolist()
    if total_rows > sample_n:
        idx = np.unique(np.linspace(0, total_rows - 1, sample_n).astype(int))
    else:
        idx = np.arange(total_rows)
    sample = df.iloc[idx]
    mask = sample[cols_ordered].isna()
    z = mask.to_numpy(dtype=int)
    y_labels = sample.index.to_numpy()
    custom = np.where(mask.to_numpy(), "Missing", "Present")

    fig = go.Figure(go.Heatmap(
        z=z, x=cols_ordered, y=y_labels, customdata=custom,
        colorscale=[[0.0, _PLOT_BG], [1.0, "#EF553B"]],
        zmin=0, zmax=1, showscale=False, xgap=0, ygap=0,
        hovertemplate=("Row %{y}<br>Column: %{x}<br>"
                       "%{customdata}<extra></extra>"),
    ))
    fig.update_layout(
        width=width,
        height=height if height is not None else 620,
        xaxis=dict(tickfont=dict(size=11), tickangle=-40, side="bottom"),
        yaxis=dict(autorange="reversed", showticklabels=False,
                   title=dict(text="rows (sampled, original order)",
                              font=dict(size=12))),
        annotations=[dict(
            text=('<span style="color:#EF553B;">■</span> Missing   '
                  '<span style="color:#888888;">■</span> Present'),
            xref="paper", yref="paper", x=1.0, y=1.03,
            xanchor="right", yanchor="bottom", showarrow=False,
            font=dict(size=12, color=_FONT_CLR),
        )],
        margin=dict(l=90, r=60, t=110, b=120),
    )
    _apply_base_layout(
        fig, title=title or "Missing Values Matrix", subtitle=subtitle,
        width=width, height=height if height is not None else 620,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Relationships
# ══════════════════════════════════════════════════════════════════════════════
def scatter_plot(
    df: pd.DataFrame,
    x: str,
    y: str,
    color_by: Optional[str] = None,
    trendline: bool = True,
    marginals: bool = False,
    density: bool = False,
    log_x: bool = False,
    log_y: bool = False,
    point_size: int = 6,
    opacity: float = 0.65,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Scatter of two numeric columns with optional trendline, marginals and density.

    With ``color_by`` the points split by category and each group gets its own
    colour and its own OLS line — making it obvious whether an x–y relationship
    holds across groups or is an artefact of pooling. For heavy overplotting,
    ``density=True`` swaps the markers for a 2-D histogram.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    x, y : str
        Numeric columns for the axes.
    color_by : str, optional
        Categorical column to colour-split the scatter (one trendline each).
    trendline : bool, default True
        Overlay an OLS fit; the label reports r² and the p-value, e.g.
        ``"OLS (r²=0.79, p<0.001)"``.
    marginals : bool, default False
        Add a marginal histogram of x (top) and of y (right). With ``color_by``
        these become per-group overlaid histograms tied to the group legend.
    density : bool, default False
        Replace markers with a Viridis 2-D histogram for large-n overplotting.
        Not compatible with ``color_by`` (raises); compatible with ``marginals``.
    log_x, log_y : bool, default False
        Log-scale the axes. Nonpositive values are simply not displayable on a
        log axis (no data is mutated).
    point_size : int, default 6
        Marker size in px (ignored in density mode).
    opacity : float, default 0.65
        Marker opacity (ignored in density mode).
    title : str, default ""
        Main title; empty auto-generates ``"y vs x"``.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` uses 620 (700 with marginals).

    Returns
    -------
    plotly.graph_objects.Figure
    """
    needed = [x, y] + ([color_by] if color_by else [])
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {missing}")
    if density and color_by is not None:
        raise ValueError("density mode does not support color_by — pick one.")

    work = df[needed].dropna()
    if work.empty:
        raise ValueError("No rows remain after dropping nulls.")

    plot_title = title or f"{y}  vs  {x}"
    final_h = height if height is not None else (700 if marginals else 620)

    if marginals:
        fig = make_subplots(
            rows=2, cols=2,
            column_widths=[0.85, 0.15], row_heights=[0.15, 0.85],
            horizontal_spacing=0.02, vertical_spacing=0.02,
            shared_xaxes=True, shared_yaxes=True,
        )
        main_rc: dict = dict(row=2, col=1)
    else:
        fig = go.Figure()
        main_rc = {}

    def _add_trend(xd: np.ndarray, yd: np.ndarray, color: str,
                   prefix: str = "") -> None:
        if len(xd) < 3:
            return
        slope, intercept, r_val, p_val, _ = stats.linregress(xd, yd)
        xs = np.linspace(np.min(xd), np.max(xd), 200)
        lbl = f"OLS (r²={r_val**2:.2f}, {_fmt_p(p_val)})"
        if prefix:
            lbl = f"{prefix} · {lbl}"
        fig.add_trace(go.Scatter(
            x=xs, y=slope * xs + intercept, mode="lines", name=lbl,
            line=dict(color=color, width=2, dash="dash"), opacity=0.85,
            legendgroup=prefix or "trend", showlegend=True, hoverinfo="skip",
        ), **main_rc)

    cats: List = []
    if density:
        fig.add_trace(go.Histogram2d(
            x=work[x], y=work[y], colorscale="Viridis", nbinsx=80,
            colorbar=dict(
                title=dict(text="Count",
                           font=dict(size=12, color=_FONT_CLR, family="Arial")),
                tickfont=dict(color=_FONT_CLR), thickness=14, outlinewidth=0,
            ),
            hovertemplate=(f"<b>{x}</b>: %{{x}}<br><b>{y}</b>: %{{y}}"
                           "<br>count: %{z}<extra></extra>"),
        ), **main_rc)
        if trendline:
            _add_trend(work[x].to_numpy(float), work[y].to_numpy(float),
                       PALETTE[2])
    elif color_by is None:
        fig.add_trace(go.Scatter(
            x=work[x], y=work[y], mode="markers", name="",
            marker=dict(color=PALETTE[0], size=point_size, opacity=opacity,
                        line=dict(width=0.4, color="rgba(255,255,255,0.3)")),
            showlegend=False,
            hovertemplate=f"<b>{x}</b>: %{{x}}<br><b>{y}</b>: %{{y}}<extra></extra>",
        ), **main_rc)
        if trendline:
            _add_trend(work[x].to_numpy(float), work[y].to_numpy(float),
                       PALETTE[2])
    else:
        cats = sorted(work[color_by].unique(), key=str)
        for i, cat in enumerate(cats):
            sub = work[work[color_by] == cat]
            col = PALETTE[i % len(PALETTE)]
            fig.add_trace(go.Scatter(
                x=sub[x], y=sub[y], mode="markers", name=str(cat),
                marker=dict(color=col, size=point_size, opacity=opacity,
                            line=dict(width=0.4, color="rgba(255,255,255,0.3)")),
                legendgroup=str(cat),
                hovertemplate=(f"<b>{color_by}</b>: {cat}<br><b>{x}</b>: %{{x}}"
                               f"<br><b>{y}</b>: %{{y}}<extra></extra>"),
            ), **main_rc)
            if trendline:
                _add_trend(sub[x].to_numpy(float), sub[y].to_numpy(float),
                           col, prefix=str(cat))

    if marginals:
        if color_by is None:
            fig.add_trace(go.Histogram(
                x=work[x], marker_color=PALETTE[0], opacity=0.75,
                showlegend=False, hoverinfo="skip"), row=1, col=1)
            fig.add_trace(go.Histogram(
                y=work[y], marker_color=PALETTE[0], opacity=0.75,
                showlegend=False, hoverinfo="skip"), row=2, col=2)
        else:
            for i, cat in enumerate(cats):
                sub = work[work[color_by] == cat]
                col = PALETTE[i % len(PALETTE)]
                fig.add_trace(go.Histogram(
                    x=sub[x], marker_color=col, opacity=0.55, showlegend=False,
                    legendgroup=str(cat), hoverinfo="skip"), row=1, col=1)
                fig.add_trace(go.Histogram(
                    y=sub[y], marker_color=col, opacity=0.55, showlegend=False,
                    legendgroup=str(cat), hoverinfo="skip"), row=2, col=2)
            fig.update_layout(barmode="overlay")
        for rr, cc in ((1, 1), (2, 2)):
            fig.update_xaxes(showticklabels=False, showgrid=False, row=rr, col=cc)
            fig.update_yaxes(showticklabels=False, showgrid=False, row=rr, col=cc)
        fig.update_xaxes(type="log" if log_x else "linear", row=1, col=1)
        fig.update_yaxes(type="log" if log_y else "linear", row=2, col=2)

    x_type = "log" if log_x else "linear"
    y_type = "log" if log_y else "linear"
    axis_kw = dict(showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR,
                   zeroline=False)
    if marginals:
        fig.update_xaxes(title=dict(text=x, font=dict(size=13)), type=x_type,
                         row=2, col=1, **axis_kw)
        fig.update_yaxes(title=dict(text=y, font=dict(size=13)), type=y_type,
                         row=2, col=1, **axis_kw)
    else:
        fig.update_layout(
            xaxis=dict(title=dict(text=x, font=dict(size=13, family="Arial")),
                       tickfont=dict(size=11), type=x_type, **axis_kw),
            yaxis=dict(title=dict(text=y, font=dict(size=13, family="Arial")),
                       tickfont=dict(size=11), type=y_type, **axis_kw),
        )

    fig.update_layout(
        width=width, height=final_h,
        legend=dict(bgcolor="rgba(0,0,0,0.4)",
                    bordercolor="rgba(255,255,255,0.15)", borderwidth=1,
                    font=dict(size=11, color=_FONT_CLR)),
        margin=dict(l=80, r=60, t=90, b=80),
    )
    _apply_base_layout(fig, title=plot_title, width=width, height=final_h)
    return fig


def bubble_plot(
    df: pd.DataFrame,
    x: str,
    y: str,
    size: str,
    color_by: Optional[str] = None,
    label_col: Optional[str] = None,
    label_top_n: int = 10,
    size_range: Tuple[float, float] = (5.0, 50.0),
    log_x: bool = False,
    log_y: bool = False,
    opacity: float = 0.7,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Four-variable bubble chart: x × y × bubble area × colour, with named points.

    Bubble area encodes ``size`` (scaled into ``size_range`` px so extremes don't
    swamp the chart). ``color_by`` accepts a categorical column (discrete palette
    + legend) or a numeric column (RdBu colorbar). ``label_col`` names the most
    prominent bubbles — the storytelling touch for "which entities are these?".

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    x, y : str
        Numeric columns for the axes.
    size : str
        Numeric column controlling bubble area.
    color_by : str, optional
        Categorical (≤ 12 distinct → discrete legend) or numeric (RdBu colorbar).
    label_col : str, optional
        Column whose text labels the ``label_top_n`` largest bubbles by ``size``.
    label_top_n : int, default 10
        Number of largest bubbles to annotate when ``label_col`` is set.
    size_range : tuple of (float, float), default (5.0, 50.0)
        Min/max marker size in px; must satisfy ``0 < lo < hi``.
    log_x, log_y : bool, default False
        Log-scale the axes (nonpositive values not displayable; no mutation).
    opacity : float, default 0.7
        Marker opacity.
    title : str, default ""
        Main title; empty auto-generates ``"y vs x (size = size)"``.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` defaults to 640.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    lo, hi = size_range
    if not (0 < lo < hi):
        raise ValueError(f"size_range must satisfy 0 < lo < hi; got {size_range}.")

    required = [c for c in [x, y, size, color_by, label_col] if c]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {missing}")

    working = df[required].dropna()
    if working.empty:
        raise ValueError("No rows remain after dropping nulls for the columns.")

    bubble_sizes = _normalize_size(working[size], lo, hi)
    plot_title = title or f"{y}  vs  {x}  (size = {size})"

    raw = working[size].to_numpy(dtype=float, na_value=np.nan)
    refs = [float(np.nanquantile(raw, p)) for p in (0.25, 0.75, 1.0)]
    is_categorical = color_by is not None and (
        _is_categorical_col(working[color_by])
        or working[color_by].nunique() <= 12
    )
    is_numerical = color_by is not None and not is_categorical

    fig = go.Figure()

    if is_categorical:
        for i, cat in enumerate(sorted(working[color_by].unique(), key=str)):
            mask = working[color_by] == cat
            sub = working[mask]
            fig.add_trace(go.Scatter(
                x=sub[x], y=sub[y], mode="markers", name=str(cat),
                customdata=sub[size].values,
                marker=dict(size=bubble_sizes[mask.values],
                            color=PALETTE[i % len(PALETTE)], opacity=opacity,
                            line=dict(width=0.8, color="rgba(255,255,255,0.25)")),
                legendgroup=str(cat),
                hovertemplate=(f"<b>{color_by}</b>: {cat}<br><b>{x}</b>: %{{x}}"
                               f"<br><b>{y}</b>: %{{y}}<br><b>{size}</b>: "
                               "%{customdata:.3g}<extra></extra>"),
            ))
    elif is_numerical:
        fig.add_trace(go.Scatter(
            x=working[x], y=working[y], mode="markers", name="",
            customdata=np.stack(
                [working[size].values, working[color_by].values], axis=1),
            marker=dict(
                size=bubble_sizes, color=working[color_by].values,
                colorscale=_RDBU,
                colorbar=dict(
                    title=dict(text=color_by,
                               font=dict(size=12, color=_FONT_CLR, family="Arial")),
                    tickfont=dict(color=_FONT_CLR, family="Arial"),
                    thickness=14, outlinewidth=0),
                opacity=opacity, showscale=True,
                line=dict(width=0.8, color="rgba(255,255,255,0.25)")),
            showlegend=False,
            hovertemplate=(f"<b>{x}</b>: %{{x}}<br><b>{y}</b>: %{{y}}"
                           f"<br><b>{size}</b>: %{{customdata[0]:.3g}}"
                           f"<br><b>{color_by}</b>: %{{customdata[1]:.3g}}"
                           "<extra></extra>"),
        ))
    else:
        fig.add_trace(go.Scatter(
            x=working[x], y=working[y], mode="markers", name="",
            customdata=working[size].values,
            marker=dict(size=bubble_sizes, color="#00CC96", opacity=opacity,
                        line=dict(width=0.8, color="rgba(255,255,255,0.25)")),
            showlegend=False,
            hovertemplate=(f"<b>{x}</b>: %{{x}}<br><b>{y}</b>: %{{y}}"
                           f"<br><b>{size}</b>: %{{customdata:.3g}}<extra></extra>"),
        ))

    if label_col is not None:
        top = working.nlargest(label_top_n, size)
        fig.add_trace(go.Scatter(
            x=top[x], y=top[y], mode="text",
            text=top[label_col].astype(str),
            textposition="top center", textfont=dict(size=10, color="#DDDDDD"),
            showlegend=False, hoverinfo="skip",
        ))

    size_note_lines = [
        f"● {label}  {ref:.3g}"
        for label, ref in zip(("Q25", "Q75", "Max"), refs)
    ]
    size_block = f"<b>Bubble size → {size}</b><br>" + "<br>".join(size_note_lines)

    x_type = "log" if log_x else "linear"
    y_type = "log" if log_y else "linear"
    fig.update_layout(
        width=width, height=height if height is not None else 640,
        xaxis=dict(title=dict(text=x, font=dict(size=13, family="Arial")),
                   tickfont=dict(size=11), type=x_type, showgrid=True,
                   gridwidth=0.5, gridcolor=_GRID_CLR, zeroline=False),
        yaxis=dict(title=dict(text=y, font=dict(size=13, family="Arial")),
                   tickfont=dict(size=11), type=y_type, showgrid=True,
                   gridwidth=0.5, gridcolor=_GRID_CLR, zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0.4)",
                    bordercolor="rgba(255,255,255,0.12)", borderwidth=1,
                    font=dict(size=11, color=_FONT_CLR),
                    title=dict(text=color_by if is_categorical else "",
                               font=dict(size=12, color=_FONT_CLR))),
        annotations=[dict(
            text=size_block, xref="paper", yref="paper", x=0.99, y=0.99,
            xanchor="right", yanchor="top", showarrow=False,
            font=dict(size=11, color="#AAAAAA", family="Arial"),
            bgcolor="rgba(0,0,0,0.45)", bordercolor="rgba(255,255,255,0.12)",
            borderwidth=1, borderpad=6, align="left")],
        margin=dict(l=80, r=80, t=90, b=80),
    )
    _apply_base_layout(
        fig, title=plot_title, width=width,
        height=height if height is not None else 640,
    )
    return fig


def correlation_heatmap(
    df: pd.DataFrame,
    ignore_cols: Optional[List[str]] = None,
    cols: Optional[List[str]] = None,
    method: Literal["pearson", "spearman", "kendall"] = "pearson",
    threshold: float = 0.0,
    triangle: Literal["full", "lower"] = "full",
    show_significance: bool = False,
    order: Literal["original", "cluster", "angle", "pc1", "alphabet"] = "original",
    order_on: Literal["signed", "abs"] = "signed",
    n_clusters: Optional[int] = None,
    title: str = "",
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Annotated correlation matrix with optional seriation and significance stars.

    Colour diverges around zero on a dark-anchored ramp (blue positive, red
    negative, near-black ≈ 0) so salience scales with ``|r|`` and the white
    in-cell labels stay legible at every value. The diagonal and any
    ``|r| < threshold`` cells are masked for readability; ``triangle='lower'``
    additionally hides the redundant upper triangle.

    ``order`` **seriates** the matrix — one permutation applied to both axes so
    related variables become adjacent and the structure collapses into blocks
    along the diagonal. Alphabetical or load order usually scatters that
    structure; seriation is what makes it visible. This is a reordering of an
    existing matrix, not a model: it changes nothing about the correlations
    themselves, and the blocks it reveals are descriptive groupings, not
    evidence of a latent factor.

    With ``show_significance`` each cell gains stars from a p-value computed on
    **pairwise-complete** observations (matching how ``DataFrame.corr`` forms r).
    Note the multiple-comparison caveat: an n×n matrix runs many tests, so some
    stars will appear by chance and these p-values are uncorrected and
    descriptive — formal inference belongs in a dedicated, pre-registered test.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    ignore_cols : list of str, optional
        Columns to exclude before selecting numerics.
    cols : list of str, optional
        Restrict to these columns; ``None`` uses all numerics minus ignore_cols.
    method : {'pearson', 'spearman', 'kendall'}, default 'pearson'
        Correlation coefficient.
    threshold : float, default 0.0
        Cells with ``|r|`` below this are blanked out.
    triangle : {'full', 'lower'}, default 'full'
        ``'lower'`` masks the upper triangle and diagonal (de-duplicated view).
    show_significance : bool, default False
        Append significance stars and show n(pairwise)/p in the hover.
    order : {'original', 'cluster', 'angle', 'pc1', 'alphabet'}, default 'original'
        Row/column ordering:

        - ``'original'`` — keep the dataframe's column order (no seriation).
        - ``'cluster'`` — hierarchical clustering (average linkage) on the
          correlation distance, refined by optimal leaf ordering. Produces hard
          blocks; the right choice when the question is *which variables group
          together*. Required for ``n_clusters``.
        - ``'angle'`` — angular order of the two leading eigenvectors
          (Friendly, 2002). Lays variables on a smooth gradient and implies no
          group boundaries — safer when the block structure is weak and
          clustering would invent groups that are not really there.
        - ``'pc1'`` — sort by loading on the first principal component; a
          one-dimensional version of ``'angle'``.
        - ``'alphabet'`` — alphabetical; for looking a variable up, not for
          seeing structure.
    order_on : {'signed', 'abs'}, default 'signed'
        Which similarity the seriation runs on — a genuine choice with different
        answers, not an implementation detail. ``'signed'`` uses distance
        ``(1 - r) / 2``, grouping variables that move in the *same direction* and
        pushing strongly anti-correlated pairs far apart. ``'abs'`` uses
        ``1 - |r|``, grouping variables that share information regardless of
        sign, so an anti-correlated pair sits adjacent and its block reads red.
        Use ``'signed'`` to find variables that behave alike, ``'abs'`` to find
        redundancy. Ignored when ``order`` is ``'original'`` or ``'alphabet'``.
    n_clusters : int, optional
        Cut the dendrogram into this many flat clusters and outline the
        resulting diagonal blocks. Requires ``order='cluster'``. The count is a
        **visual aid you choose**, not a result the data supports — nothing here
        estimates an optimal k.
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, optional
        Figure width in px. ``None`` auto-sizes a square from the column count
        (this plot self-sizes — a deviation from the ``width=1400`` default used
        elsewhere).
    height : int, optional
        Figure height in px; ``None`` auto-sizes to match.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    ignore_cols = ignore_cols or []
    working = df.drop(columns=[c for c in ignore_cols if c in df.columns])
    if cols is not None:
        working = working[cols]

    num = working.select_dtypes(include=[np.number])
    if num.shape[1] < 2:
        raise ValueError(
            "Need at least two numerical columns for a correlation heatmap."
        )

    corr = num.corr(method=method)
    n = corr.shape[1]

    if n_clusters is not None:
        if order != "cluster":
            raise ValueError(
                "n_clusters requires order='cluster' — the other orderings "
                "build no dendrogram to cut."
            )
        if not 2 <= n_clusters <= n:
            raise ValueError(
                f"n_clusters must be between 2 and {n} (got {n_clusters})."
            )

    perm, linkage = _corr_order(corr, order, order_on)
    if not np.array_equal(perm, np.arange(n)):
        corr = corr.iloc[perm, perm]
        num = num.iloc[:, perm]      # keep the pairwise p-value loop aligned

    labels = corr.columns.tolist()
    z = corr.values

    test_fn = {
        "pearson": stats.pearsonr,
        "spearman": stats.spearmanr,
        "kendall": stats.kendalltau,
    }[method]
    pmat = np.full((n, n), np.nan)
    nmat = np.zeros((n, n), dtype=int)
    if show_significance:
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                pair = num.iloc[:, [i, j]].dropna()
                nmat[i, j] = len(pair)
                if len(pair) >= 3:
                    try:
                        _, p_val = test_fn(pair.iloc[:, 0], pair.iloc[:, 1])
                        pmat[i, j] = p_val
                    except ValueError:
                        pmat[i, j] = np.nan

    z_display = z.copy().astype(float)
    text_matrix: list[list[str]] = []
    for r in range(n):
        row_text = []
        for c in range(n):
            masked = (
                r == c
                or (triangle == "lower" and c > r)
                or abs(z[r, c]) < threshold
            )
            if masked:
                z_display[r, c] = np.nan
                row_text.append("")
            else:
                cell = f"{z[r, c]:.2f}"
                if show_significance and not np.isnan(pmat[r, c]):
                    cell += _p_stars(pmat[r, c])
                row_text.append(cell)
        text_matrix.append(row_text)

    if show_significance:
        hovertemplate = (
            "<b>%{y}</b> × <b>%{x}</b><br>r = %{z:.3f}"
            "<br>n = %{customdata[0]}<br>p = %{customdata[1]:.3g}<extra></extra>"
        )
        customdata = np.dstack([nmat, pmat])
    else:
        hovertemplate = "<b>%{y}</b> × <b>%{x}</b><br>r = %{z:.3f}<extra></extra>"
        customdata = None

    fig = go.Figure(go.Heatmap(
        z=z_display, x=labels, y=labels, text=text_matrix,
        texttemplate="%{text}", textfont=dict(size=10, color="white",
                                              family="Arial"),
        colorscale=_CORR_DIVERGING, zmid=0, zmin=-1, zmax=1,
        customdata=customdata,
        colorbar=dict(
            title=dict(text=method.capitalize(),
                       font=dict(size=12, color=_FONT_CLR, family="Arial")),
            tickfont=dict(color=_FONT_CLR, family="Arial"),
            tickvals=[-1, -0.5, 0, 0.5, 1],
            ticktext=["-1", "-0.5", "0", "0.5", "1"],
            thickness=14, outlinewidth=0),
        hovertemplate=hovertemplate,
    ))

    if n_clusters is not None and linkage is not None:
        # Outline each diagonal block. Cell k spans [k-0.5, k+0.5] in data
        # coords, so a block of rows s..e is bounded by s-0.5 and e+0.5.
        start = 0
        for size in _cluster_block_sizes(linkage, perm, n_clusters):
            lo, hi = start - 0.5, start + size - 0.5
            fig.add_shape(
                type="rect", xref="x", yref="y",
                x0=lo, x1=hi, y0=lo, y1=hi,
                line=dict(color="rgba(255,255,255,0.55)", width=2),
                fillcolor="rgba(0,0,0,0)", layer="above",
            )
            start += size

    thr_note = f"  ·  |r| < {threshold} masked" if threshold > 0 else ""
    tri_note = "  ·  lower triangle" if triangle == "lower" else ""
    sig_note = ("  ·  * p<.05 ** p<.01 *** p<.001 — uncorrected, descriptive only"
                if show_significance else "")
    dist_note = "1−|r|" if order_on == "abs" else "(1−r)/2"
    order_note = {
        "original": "",
        "alphabet": "  ·  alphabetical order",
        "cluster": f"  ·  seriated: average-linkage clustering on {dist_note}",
        "angle": f"  ·  seriated: angular eigenvector order on {dist_note}",
        "pc1": f"  ·  seriated: first-PC loading on {dist_note}",
    }[order]
    blk_note = (f"  ·  {n_clusters} blocks outlined"
                if n_clusters is not None else "")
    subtitle = (f"{method.capitalize()} correlation{thr_note}{tri_note}"
                f"{order_note}{blk_note}{sig_note}")

    cell_px = max(38, min(70, 900 // n))
    size = n * cell_px + 200
    final_w = width if width is not None else max(700, size)
    final_h = height if height is not None else max(600, size)

    fig.update_layout(
        xaxis=dict(tickfont=dict(size=11), tickangle=-40, side="bottom"),
        yaxis=dict(tickfont=dict(size=11), autorange="reversed"),
        margin=dict(l=150, r=80, t=110, b=150),
    )
    _apply_base_layout(fig, title=title or "Feature Correlation Matrix",
                       subtitle=subtitle, width=final_w, height=final_h)
    return fig


def cross_tab_heatmap(
    df: pd.DataFrame,
    col1: str,
    col2: str,
    normalize: Optional[Literal["row", "col", "all"]] = "row",
    show_counts: bool = False,
    colorscale: str = "Viridis",
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Cross-tabulation heatmap — does the mix of ``col2`` shift across ``col1``?

    Each row is one category of ``col1``. Normalisation controls what the colour
    encodes so unequal category sizes don't mislead: row/column percentages, a
    share of the grand total, or raw counts.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    col1 : str
        Row dimension (y-axis).
    col2 : str
        Column dimension (x-axis).
    normalize : {'row', 'col', 'all', None}, default 'row'
        ``'row'`` = each row sums to 100 %; ``'col'`` = each column sums to
        100 %; ``'all'`` = % of the grand total; ``None`` = raw counts.
    show_counts : bool, default False
        When normalising, append ``(n=45)`` under each percentage. No-op when
        ``normalize=None`` (counts are already shown).
    colorscale : str, default 'Viridis'
        Any named Plotly colorscale.
    title : str, default ""
        Main title; empty auto-generates ``"col1 × col2"``.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` auto-computes from the row count.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    if col1 not in df.columns or col2 not in df.columns:
        missing = [c for c in (col1, col2) if c not in df.columns]
        raise ValueError(f"Column(s) not found: {missing}")

    ct = pd.crosstab(df[col1], df[col2])
    if ct.empty or ct.to_numpy().sum() == 0:
        raise ValueError(
            "Crosstab is empty after dropping nulls — nothing to plot."
        )

    counts = ct.to_numpy(dtype=float)
    if normalize == "row":
        z = ct.div(ct.sum(axis=1), axis=0).to_numpy() * 100
        cbar_title, subtitle = "Row %", "Row-normalised (each row sums to 100 %)"
    elif normalize == "col":
        z = ct.div(ct.sum(axis=0), axis=1).to_numpy() * 100
        cbar_title = "Column %"
        subtitle = "Column-normalised (each column sums to 100 %)"
    elif normalize == "all":
        z = counts / counts.sum() * 100
        cbar_title, subtitle = "% of total", "% of grand total"
    else:
        z = counts
        cbar_title, subtitle = "Count", "Raw counts"

    y_labels = [str(v) for v in ct.index.tolist()]
    x_labels = [str(v) for v in ct.columns.tolist()]

    text_matrix: list[list[str]] = []
    for r in range(len(y_labels)):
        row_text = []
        for c in range(len(x_labels)):
            if normalize is None:
                row_text.append(f"{int(counts[r, c]):,}")
            elif show_counts:
                row_text.append(f"{z[r, c]:.1f}%<br>(n={int(counts[r, c]):,})")
            else:
                row_text.append(f"{z[r, c]:.1f}%")
        text_matrix.append(row_text)

    if normalize is None:
        hover = (f"<b>{col1}</b>: %{{y}}<br><b>{col2}</b>: %{{x}}"
                 "<br>Count: %{z:,.0f}<extra></extra>")
    else:
        hover = (f"<b>{col1}</b>: %{{y}}<br><b>{col2}</b>: %{{x}}"
                 f"<br>{cbar_title}: %{{z:.1f}}%"
                 "<br>n = %{customdata:,}<extra></extra>")

    fig = go.Figure(go.Heatmap(
        z=z, x=x_labels, y=y_labels, text=text_matrix, texttemplate="%{text}",
        textfont=dict(size=10 if show_counts else 11, color="white",
                      family="Arial"),
        customdata=counts if normalize is not None else None,
        colorscale=colorscale,
        colorbar=dict(
            title=dict(text=cbar_title,
                       font=dict(size=12, color=_FONT_CLR, family="Arial")),
            tickfont=dict(color=_FONT_CLR, family="Arial"),
            thickness=14, outlinewidth=0),
        hovertemplate=hover,
    ))
    fig.update_layout(
        width=width, height=height if height is not None
        else max(420, len(y_labels) * 52 + 160),
        xaxis=dict(title=dict(text=col2, font=dict(size=13)),
                   tickfont=dict(size=11), side="bottom"),
        yaxis=dict(title=dict(text=col1, font=dict(size=13)),
                   tickfont=dict(size=11), autorange="reversed"),
        margin=dict(l=140, r=80, t=100, b=100),
    )
    _apply_base_layout(
        fig, title=title or f"{col1}  ×  {col2}", subtitle=subtitle,
        width=width,
        height=height if height is not None else max(420, len(y_labels) * 52 + 160),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Group comparison
# ══════════════════════════════════════════════════════════════════════════════
def _agg_ci(
    vals: np.ndarray,
    agg_func: Callable[..., float],
    ci_method: Optional[str],
    confidence: float,
    n_boot: int,
) -> Tuple[float, float, float, int]:
    """
    Aggregate a value array and return ``(point, ci_lo, ci_hi, n)``.

    Bootstrap CIs use the basic percentile method with ``random_state=0`` for
    reproducibility; ``'sem'`` uses the normal-approx mean ± z·SEM. CIs need
    n ≥ 2 (else the interval is NaN).
    """
    vals = np.asarray(vals, dtype=float)
    vals = vals[~np.isnan(vals)]
    n = len(vals)
    if n == 0:
        return np.nan, np.nan, np.nan, 0
    point = float(agg_func(vals))
    lo = hi = np.nan
    if ci_method and n >= 2:
        if ci_method == "bootstrap":
            res = stats.bootstrap(
                (vals,), agg_func, confidence_level=confidence,
                n_resamples=n_boot, method="basic", random_state=0)
            lo, hi = res.confidence_interval.low, res.confidence_interval.high
        else:  # sem
            sem = np.std(vals, ddof=1) / np.sqrt(n)
            zc = stats.norm.ppf(0.5 + confidence / 2)
            lo, hi = point - zc * sem, point + zc * sem
    return point, lo, hi, n


def grouped_bar_plot(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    split_col: Optional[str] = None,
    agg: Literal["mean", "median"] = "mean",
    ci_method: Optional[Literal["bootstrap", "sem"]] = "bootstrap",
    n_boot: int = 2000,
    confidence: float = 0.95,
    min_n_flag: int = 30,
    top_n: Optional[int] = None,
    ascending: bool = False,
    orientation: Literal["vertical", "horizontal"] = "vertical",
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Ranked bar chart of an aggregate across groups, with confidence intervals.

    Each bar is one ``group_col`` category; error bars show a CI around the
    aggregate so groups' *distinguishability* — not just their bar heights — is
    visible. Groups with fewer than ``min_n_flag`` observations are flagged
    (gold outline + "⚠") rather than dropped; this is descriptive only, formal
    group tests belong in the dedicated notebook. ``split_col`` turns the chart
    into clustered bars for a second categorical dimension.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    group_col : str
        Categorical column defining the primary groups.
    value_col : str
        Numeric column being aggregated.
    split_col : str, optional
        Second categorical column → clustered bars (one bar per level within each
        group). Capped at 8 levels — more raises (pre-filter first). Group order
        is decided by the aggregate over all rows (ignoring the split) so cluster
        order stays stable. In split mode the low-n flag is carried by the "⚠"
        text only (outlining every cluster bar gets noisy).
    agg : {'mean', 'median'}, default 'mean'
        Aggregate statistic.
    ci_method : {'bootstrap', 'sem', None}, default 'bootstrap'
        'bootstrap' works for mean or median; 'sem' is mean-only, so
        ``agg='median'`` silently falls back to bootstrap. ``None`` hides CIs.
    n_boot : int, default 2000
        Bootstrap resamples per cell (bootstrap only).
    confidence : float, default 0.95
        Confidence level.
    min_n_flag : int, default 30
        Low-n flag threshold.
    top_n : int, optional
        Keep only the top N groups after sorting.
    ascending : bool, default False
        Sort direction by the aggregated value.
    orientation : {'vertical', 'horizontal'}, default 'vertical'
        'horizontal' swaps the axes (good for long category names); rank 1 sits
        at the top.
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` defaults to 560.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    keep = [group_col, value_col] + ([split_col] if split_col else [])
    working = df[keep].dropna()
    if working.empty:
        raise ValueError("No rows remain after dropping nulls for the columns.")

    agg_func = np.mean if agg == "mean" else np.median
    eff_ci = "bootstrap" if (agg == "median" and ci_method == "sem") else ci_method
    is_v = orientation == "vertical"

    def _err(ep: List[float], em: List[float]) -> Optional[dict]:
        if not eff_ci:
            return None
        return dict(type="data", symmetric=False, array=ep, arrayminus=em,
                    color="rgba(255,255,255,0.6)", thickness=1.5, width=4)

    # ── Ordering key (over all rows, ignoring any split) ──────────────────────
    overall = working.groupby(group_col)[value_col].agg(agg)
    overall = overall.sort_values(ascending=ascending)
    if top_n is not None:
        overall = overall.head(top_n)
    ordered_groups = [str(g) for g in overall.index.tolist()]
    group_index = overall.index.tolist()

    trace_specs: list[dict] = []
    if split_col is None:
        vals, eps, ems, ns = [], [], [], []
        for grp in group_index:
            arr = working.loc[working[group_col] == grp, value_col].to_numpy(float)
            point, lo, hi, n = _agg_ci(arr, agg_func, eff_ci, confidence, n_boot)
            vals.append(point)
            eps.append(0.0 if np.isnan(hi) else hi - point)
            ems.append(0.0 if np.isnan(lo) else point - lo)
            ns.append(n)
        colors = [
            _CATEGORICAL_COLORS[i % len(_CATEGORICAL_COLORS)]
            if n >= min_n_flag else _OTHER_COLOR
            for i, n in enumerate(ns)
        ]
        line_widths = [2 if n < min_n_flag else 0 for n in ns]
        texts = [f"n={n}" + (" ⚠" if n < min_n_flag else "") for n in ns]
        trace_specs.append(dict(
            vals=vals, eps=eps, ems=ems, ns=ns, texts=texts, name="",
            marker=dict(color=colors, line=dict(width=line_widths,
                                                color="#FFD700")),
            showlegend=False))
    else:
        level_counts = working[split_col].value_counts()
        if len(level_counts) > 8:
            raise ValueError(
                f"split_col '{split_col}' has {len(level_counts)} levels (max 8). "
                "Pre-filter to the levels you want to compare."
            )
        split_levels = level_counts.index.tolist()
        for si, level in enumerate(split_levels):
            sub = working[working[split_col] == level]
            vals, eps, ems, ns = [], [], [], []
            for grp in group_index:
                arr = sub.loc[sub[group_col] == grp, value_col].to_numpy(float)
                point, lo, hi, n = _agg_ci(arr, agg_func, eff_ci, confidence,
                                           n_boot)
                vals.append(point)
                eps.append(0.0 if np.isnan(hi) else hi - point)
                ems.append(0.0 if np.isnan(lo) else point - lo)
                ns.append(n)
            texts = [
                ("" if n == 0 else f"n={n}" + (" ⚠" if n < min_n_flag else ""))
                for n in ns
            ]
            trace_specs.append(dict(
                vals=vals, eps=eps, ems=ems, ns=ns, texts=texts,
                name=str(level),
                marker=dict(color=PALETTE[si % len(PALETTE)]), showlegend=True))

    fig = go.Figure()
    for spec in trace_specs:
        common = dict(
            text=spec["texts"], textposition="outside", textfont=dict(size=10),
            cliponaxis=False, marker=spec["marker"], name=spec["name"],
            showlegend=spec["showlegend"], customdata=spec["ns"])
        val_hover = f"{agg.capitalize()} {value_col}"
        extra = "%{fullData.name}" if split_col else ""
        if is_v:
            fig.add_trace(go.Bar(
                x=ordered_groups, y=spec["vals"],
                error_y=_err(spec["eps"], spec["ems"]),
                hovertemplate=(f"<b>%{{x}}</b><br>{val_hover}: %{{y:.3g}}"
                               f"<br>n=%{{customdata}}<extra>{extra}</extra>"),
                **common))
        else:
            fig.add_trace(go.Bar(
                y=ordered_groups, x=spec["vals"], orientation="h",
                error_x=_err(spec["eps"], spec["ems"]),
                hovertemplate=(f"<b>%{{y}}</b><br>{val_hover}: %{{x:.3g}}"
                               f"<br>n=%{{customdata}}<extra>{extra}</extra>"),
                **common))

    hi_all = np.concatenate([
        np.asarray(s["vals"], float) + np.nan_to_num(np.asarray(s["eps"], float))
        for s in trace_specs])
    lo_all = np.concatenate([
        np.asarray(s["vals"], float) - np.nan_to_num(np.asarray(s["ems"], float))
        for s in trace_specs])
    v_top = float(np.nanmax(hi_all))
    v_bot = float(np.nanmin(lo_all))
    span = (v_top - v_bot) * 0.15 or abs(v_top) * 0.15 or 1.0
    val_range = [min(0, v_bot - span * 0.3), v_top + span]

    plot_title = title or f"{agg.capitalize()} {value_col} by {group_col}"
    all_ns = [n for s in trace_specs for n in s["ns"]]
    ci_note = (f"Error bars: {int(confidence * 100)}% {eff_ci} CI"
               if eff_ci else "No confidence interval shown")
    if split_col is not None:
        low_n_note = (f" · ⚠ = n < {min_n_flag}"
                      if any(0 < n < min_n_flag for n in all_ns) else "")
    else:
        low_n_note = (f" · gold outline = n < {min_n_flag}"
                      if any(n < min_n_flag for n in all_ns) else "")

    val_title = f"{agg.capitalize()} {value_col}"
    if is_v:
        fig.update_layout(
            xaxis=dict(title=dict(text=group_col, font=dict(size=13)),
                       tickfont=dict(size=11), tickangle=-35),
            yaxis=dict(title=dict(text=val_title, font=dict(size=13)),
                       showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR,
                       range=val_range))
    else:
        fig.update_layout(
            yaxis=dict(title=dict(text=group_col, font=dict(size=13)),
                       tickfont=dict(size=11), autorange="reversed"),
            xaxis=dict(title=dict(text=val_title, font=dict(size=13)),
                       showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR,
                       range=val_range))

    fig.update_layout(
        width=width, height=height if height is not None else 560,
        barmode="group" if split_col else "relative",
        showlegend=split_col is not None,
        legend=dict(title=dict(text=split_col or ""),
                    bgcolor="rgba(0,0,0,0.4)",
                    bordercolor="rgba(255,255,255,0.15)", borderwidth=1,
                    font=dict(size=11, color=_FONT_CLR)),
        margin=dict(l=90, r=70, t=110, b=90),
    )
    _apply_base_layout(
        fig, title=plot_title, subtitle=f"{ci_note}{low_n_note}",
        width=width, height=height if height is not None else 560,
    )
    return fig


def grouped_box_plot(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    kind: Literal["box", "violin"] = "box",
    show_points: Literal["outliers", "all", False] = "outliers",
    sort_by: Literal["median", "mean", "n"] = "median",
    ascending: bool = False,
    top_n: Optional[int] = None,
    min_n_flag: int = 30,
    orientation: Literal["vertical", "horizontal"] = "vertical",
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Distribution comparison across groups — box or violin, one per group.

    Shows shape and spread, not just a point estimate, so it complements
    ``grouped_bar_plot`` (aggregate ± CI). ``kind='violin'`` is the library's
    violin: an integrated mode with the box and mean line overlaid. Groups with
    fewer than ``min_n_flag`` observations get a gold outline and a flagged n=
    annotation.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    group_col : str
        Categorical column defining the groups.
    value_col : str
        Numeric column being compared.
    kind : {'box', 'violin'}, default 'box'
        Box (whiskers at Plotly's 1.5×IQR, ``boxmean=True``) or kernel-density
        violin with box + mean line overlaid.
    show_points : {'outliers', 'all', False}, default 'outliers'
        Point overlay: outliers only, a jittered strip of all points, or none.
    sort_by : {'median', 'mean', 'n'}, default 'median'
        Statistic used to order groups.
    ascending : bool, default False
        Sort direction.
    top_n : int, optional
        Keep only the top N groups after sorting.
    min_n_flag : int, default 30
        Low-n flag threshold.
    orientation : {'vertical', 'horizontal'}, default 'vertical'
        'horizontal' puts groups on the y-axis (value on x), n= labels move to
        the right margin.
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` defaults to 600.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    working = df[[group_col, value_col]].dropna()
    if working.empty:
        raise ValueError("No rows remain after dropping nulls for the columns.")

    grouped = working.groupby(group_col)[value_col]
    summary = grouped.agg(median="median", mean="mean", n="count")
    summary = summary.sort_values(sort_by, ascending=ascending)
    if top_n is not None:
        summary = summary.head(top_n)
    ordered_groups = summary.index.tolist()
    is_v = orientation == "vertical"

    bp_map = {"outliers": "outliers", "all": "all", False: False}
    points = bp_map[show_points]

    fig = go.Figure()
    for i, grp in enumerate(ordered_groups):
        vals = grouped.get_group(grp).to_numpy(dtype=float)
        n = int(summary.loc[grp, "n"])
        low_n = n < min_n_flag
        color = _CATEGORICAL_COLORS[i % len(_CATEGORICAL_COLORS)]
        line_color = "#FFD700" if low_n else color
        value_axis = "y" if is_v else "x"

        if kind == "violin":
            v_kwargs: dict = dict(
                name=str(grp), marker_color=color, box_visible=True,
                meanline_visible=True, line=dict(width=2, color=line_color),
                points=points, showlegend=False, orientation="v" if is_v else "h",
                # hard span: never draw KDE beyond observed data (e.g. below 0
                # for a non-negative metric)
                spanmode="hard",
                hovertemplate=(f"<b>{group_col}</b>: {grp}<br><b>{value_col}</b>: "
                               f"%{{{value_axis}}}<extra></extra>"))
            if show_points == "all":
                v_kwargs.update(jitter=0.35, pointpos=0)
            v_kwargs[value_axis] = vals
            fig.add_trace(go.Violin(**v_kwargs))
        else:
            b_kwargs: dict = dict(
                name=str(grp), marker_color=color, boxmean=True,
                boxpoints=points, line=dict(width=2, color=line_color),
                marker=dict(size=4, outliercolor="rgba(220,220,220,0.6)",
                            line=dict(outliercolor="rgba(220,220,220,0.6)",
                                      outlierwidth=1)),
                showlegend=False,
                hovertemplate=(f"<b>{group_col}</b>: {grp}<br><b>{value_col}</b>: "
                               f"%{{{value_axis}}}<extra></extra>"))
            if show_points == "all":
                b_kwargs.update(jitter=0.35, pointpos=-1.8)
            b_kwargs[value_axis] = vals
            fig.add_trace(go.Box(**b_kwargs))

    annotations = []
    for grp in ordered_groups:
        n = int(summary.loc[grp, "n"])
        flagged = n < min_n_flag
        text = f"n={n}" + (" ⚠" if flagged else "")
        color = "#FFD700" if flagged else "#AAAAAA"
        if is_v:
            annotations.append(dict(
                x=str(grp), y=1.02, xref="x", yref="paper", text=text,
                showarrow=False, yanchor="bottom",
                font=dict(size=10, color=color)))
        else:
            annotations.append(dict(
                x=1.01, y=str(grp), xref="paper", yref="y", text=text,
                showarrow=False, xanchor="left",
                font=dict(size=10, color=color)))

    plot_title = title or f"{value_col} distribution by {group_col}"
    low_n_note = (f"gold outline / ⚠ = n < {min_n_flag}"
                  if (summary["n"] < min_n_flag).any() else "")

    grid = dict(showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR)
    if is_v:
        fig.update_layout(
            xaxis=dict(title=dict(text=group_col, font=dict(size=13)),
                       tickfont=dict(size=11), tickangle=-35),
            yaxis=dict(title=dict(text=value_col, font=dict(size=13)), **grid))
    else:
        fig.update_layout(
            yaxis=dict(title=dict(text=group_col, font=dict(size=13)),
                       tickfont=dict(size=11)),
            xaxis=dict(title=dict(text=value_col, font=dict(size=13)), **grid))

    fig.update_layout(
        width=width, height=height if height is not None else 600,
        showlegend=False, annotations=annotations,
        margin=dict(l=90, r=90, t=120, b=90),
    )
    _apply_base_layout(fig, title=plot_title, subtitle=low_n_note,
                       width=width, height=height if height is not None else 600)
    return fig


def dumbbell_plot(
    df: pd.DataFrame,
    category_col: str,
    value_col_start: str,
    value_col_end: str,
    sort_by: Literal["start", "end", "diff", "abs_diff"] = "diff",
    ascending: bool = False,
    top_n: Optional[int] = None,
    start_label: str = "",
    end_label: str = "",
    show_diff_labels: bool = True,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Dumbbell chart — read change *and* level per entity in one row.

    For each category, a connector links a start dot to an end dot, so both the
    two values and the gap between them are legible at a glance. Reach for this
    on before/after or A-vs-B comparisons (two time points, two conditions,
    two metrics) across many entities.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    category_col : str
        One row per category. Duplicate categories are mean-aggregated first.
    value_col_start, value_col_end : str
        Numeric columns for the two endpoints.
    sort_by : {'start', 'end', 'diff', 'abs_diff'}, default 'diff'
        Ordering key; ``'diff'`` = end − start, ``'abs_diff'`` = |end − start|.
    ascending : bool, default False
        Sort direction (rank 1 is drawn at the top).
    top_n : int, optional
        Keep only the top N rows after sorting.
    start_label, end_label : str, default ""
        Legend names for the endpoints; empty defaults to the column names.
    show_diff_labels : bool, default True
        Annotate each row's signed difference at the right margin, coloured
        green/red by sign.
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` auto-computes from the row count.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    for c in (category_col, value_col_start, value_col_end):
        if c not in df.columns:
            raise ValueError(f"Column '{c}' not found in the DataFrame.")

    work = df[[category_col, value_col_start, value_col_end]].dropna()
    if work.empty:
        raise ValueError("No rows remain after dropping nulls for the columns.")

    agg = work.groupby(category_col).mean(numeric_only=True)
    agg["diff"] = agg[value_col_end] - agg[value_col_start]
    agg["abs_diff"] = agg["diff"].abs()
    key = {"start": value_col_start, "end": value_col_end,
           "diff": "diff", "abs_diff": "abs_diff"}[sort_by]
    agg = agg.sort_values(key, ascending=ascending)
    if top_n is not None:
        agg = agg.head(top_n)

    cats = [str(c) for c in agg.index.tolist()]
    starts = agg[value_col_start].to_numpy(dtype=float)
    ends = agg[value_col_end].to_numpy(dtype=float)
    diffs = agg["diff"].to_numpy(dtype=float)
    s_name = start_label or value_col_start
    e_name = end_label or value_col_end

    conn_x: list = []
    conn_y: list = []
    for cat, s, e in zip(cats, starts, ends):
        conn_x += [s, e, None]
        conn_y += [cat, cat, None]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=conn_x, y=conn_y, mode="lines",
        line=dict(color="rgba(255,255,255,0.35)", width=2),
        showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=starts, y=cats, mode="markers", name=s_name,
        marker=dict(color=PALETTE[0], size=10,
                    line=dict(width=0.6, color="rgba(255,255,255,0.4)")),
        hovertemplate=(f"<b>%{{y}}</b><br>{s_name}: %{{x:.3g}}<extra></extra>")))
    fig.add_trace(go.Scatter(
        x=ends, y=cats, mode="markers", name=e_name,
        marker=dict(color=PALETTE[1], size=10,
                    line=dict(width=0.6, color="rgba(255,255,255,0.4)")),
        hovertemplate=(f"<b>%{{y}}</b><br>{e_name}: %{{x:.3g}}<extra></extra>")))

    annotations = []
    if show_diff_labels:
        for cat, d in zip(cats, diffs):
            annotations.append(dict(
                x=1.01, y=cat, xref="paper", yref="y",
                text=f"{d:+.2g}".replace("-", "−"),
                showarrow=False, xanchor="left",
                font=dict(size=11,
                          color="#00CC96" if d >= 0 else "#EF553B")))

    n_rows = len(cats)
    final_h = height if height is not None else max(400, 34 * n_rows + 180)
    fig.update_layout(
        width=width, height=final_h,
        xaxis=dict(title=dict(text="value", font=dict(size=13)),
                   showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR,
                   zeroline=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
        legend=dict(bgcolor="rgba(0,0,0,0.4)",
                    bordercolor="rgba(255,255,255,0.15)", borderwidth=1,
                    font=dict(size=11, color=_FONT_CLR),
                    orientation="h", yanchor="bottom", y=1.01,
                    xanchor="left", x=0),
        annotations=annotations,
        margin=dict(l=160, r=90, t=100, b=70),
    )
    _apply_base_layout(
        fig, title=title or f"{value_col_start} → {value_col_end} by {category_col}",
        width=width, height=final_h,
    )
    return fig


def radar_plot(
    df: pd.DataFrame,
    category_col: str,
    value_cols: List[str],
    entities: Optional[List[str]] = None,
    top_n: Optional[int] = None,
    rank_by: Optional[str] = None,
    scale: Literal["minmax", "none"] = "minmax",
    fill: bool = True,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Radar (spider) chart — compare a few entities across many metrics at once.

    Each selected entity becomes a polygon over the ``value_cols`` axes, making
    multi-metric profiles and trade-offs easy to compare side by side. With the
    default min–max scaling, an entity's position on each axis reflects its
    standing across the *whole* dataset (not just the selected few); hover still
    reports the raw value.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    category_col : str
        Entity identifier. Duplicate categories are mean-aggregated first.
    value_cols : list of str
        Metrics forming the radial axes (≥ 3 required).
    entities : list of str, optional
        Exact ``category_col`` values to plot (unknown values raise). Mutually
        used instead of ``top_n``.
    top_n : int, optional
        Plot the top N entities ranked by ``rank_by`` when ``entities`` is None.
    rank_by : str, optional
        Metric to rank by (defaults to the first of ``value_cols``).
    scale : {'minmax', 'none'}, default 'minmax'
        'minmax' scales each axis to [0, 1] across all rows; 'none' plots raw
        values (only meaningful when all metrics share units).
    fill : bool, default True
        Fill each polygon at low opacity; otherwise draw lines only.
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` defaults to 640.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    if len(value_cols) < 3:
        raise ValueError("radar_plot needs at least 3 value_cols.")
    for c in [category_col, *value_cols]:
        if c not in df.columns:
            raise ValueError(f"Column '{c}' not found in the DataFrame.")

    agg = df.groupby(category_col)[value_cols].mean(numeric_only=True)
    n_total = len(agg)

    if entities is not None:
        missing = [e for e in entities if e not in agg.index]
        if missing:
            raise ValueError(f"Entities not found in {category_col}: {missing}")
        selected = list(entities)
    else:
        rank_col = rank_by or value_cols[0]
        if rank_col not in agg.columns:
            raise ValueError(
                f"rank_by '{rank_col}' must be one of value_cols {value_cols}."
            )
        n_take = top_n if top_n is not None else min(6, n_total)
        selected = agg.sort_values(rank_col, ascending=False).head(n_take).index
        selected = [str(s) for s in selected.tolist()]

    if len(selected) > 6:
        raise ValueError(
            f"radar_plot caps at 6 entities for readability; got {len(selected)}. "
            "Select fewer entities or lower top_n."
        )

    if scale == "minmax":
        mn = agg.min()
        mx = agg.max()
        rng = (mx - mn).replace(0, np.nan)
        scaled = (agg - mn) / rng
        scaled = scaled.fillna(0.5)  # constant metric → neutral mid-position
        subtitle = f"axes min–max scaled across all {n_total} rows"
    else:
        scaled = agg
        subtitle = "raw values (metrics should share units)"

    theta = list(value_cols) + [value_cols[0]]
    fig = go.Figure()
    for i, ent in enumerate(selected):
        key = ent if ent in agg.index else type(agg.index[0])(ent)
        r_vals = scaled.loc[key, value_cols].to_numpy(dtype=float)
        raw_vals = agg.loc[key, value_cols].to_numpy(dtype=float)
        r_closed = np.append(r_vals, r_vals[0])
        raw_closed = np.append(raw_vals, raw_vals[0])
        color = PALETTE[i % len(PALETTE)]
        fig.add_trace(go.Scatterpolar(
            r=r_closed, theta=theta, name=str(ent),
            mode="lines+markers", customdata=raw_closed,
            line=dict(color=color, width=2),
            marker=dict(size=6, color=color),
            fill="toself" if fill else "none",
            fillcolor=_hex_to_rgba(color, 0.25) if fill else None,
            hovertemplate=("%{theta}: %{customdata:.3g}"
                           "<extra>%{fullData.name}</extra>"),
        ))

    radial = dict(showline=False, gridcolor=_GRID_CLR,
                  tickfont=dict(size=10, color=_FONT_CLR))
    if scale == "minmax":
        radial["range"] = [0, 1]
    fig.update_layout(
        width=width, height=height if height is not None else 640,
        polar=dict(bgcolor=_PLOT_BG, radialaxis=radial,
                   angularaxis=dict(gridcolor=_GRID_CLR,
                                    tickfont=dict(size=11, color=_FONT_CLR))),
        legend=dict(bgcolor="rgba(0,0,0,0.4)",
                    bordercolor="rgba(255,255,255,0.15)", borderwidth=1,
                    font=dict(size=11, color=_FONT_CLR)),
        margin=dict(l=80, r=80, t=110, b=80),
    )
    _apply_base_layout(
        fig, title=title or f"Metric profiles by {category_col}",
        subtitle=subtitle, width=width,
        height=height if height is not None else 640,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Trends & composition
# ══════════════════════════════════════════════════════════════════════════════
def time_series_plot(
    df: pd.DataFrame,
    date_col: str,
    value_col: Optional[str] = None,
    group_col: Optional[str] = None,
    agg: Literal["mean", "median", "sum", "count"] = "mean",
    freq: str = "MS",
    rolling: Optional[int] = None,
    top_n_groups: int = 8,
    show_points: bool = False,
    log_y: bool = False,
    rangeslider: bool = False,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Temporal aggregation line chart with optional grouping and rolling means.

    Resamples ``date_col`` to a regular ``freq`` grid and aggregates ``value_col``
    per period, so trends, seasonality and level shifts are visible. Periods with
    no underlying rows are left as *gaps* (not zero) — a gap means "no data".

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    date_col : str
        Datetime-like column (coerced via ``to_datetime``; unparseable rows are
        dropped).
    value_col : str, optional
        Numeric column to aggregate. When ``None``, ``agg`` must be ``'count'``
        (rows per period), else a ValueError explains the mismatch.
    group_col : str, optional
        Categorical column → one line per level, capped at ``top_n_groups`` most
        frequent levels (subtitle notes when capped).
    agg : {'mean', 'median', 'sum', 'count'}, default 'mean'
        Aggregate per period. ``'count'`` with a ``value_col`` counts non-null
        rows of it.
    freq : str, default 'MS'
        Pandas resample alias ('D', 'W', 'MS', 'QS', 'YS', …).
    rolling : int, optional
        Overlay a trailing rolling mean over this many periods (``min_periods=1``);
        the raw line fades and the legend labels only the rolling trace.
    top_n_groups : int, default 8
        Max group lines to draw.
    show_points : bool, default False
        Add markers on the raw lines.
    log_y : bool, default False
        Log-scale the y-axis.
    rangeslider : bool, default False
        Show the x-axis range slider (off by default — it fights fixed heights).
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` defaults to 600.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    if date_col not in df.columns:
        raise ValueError(f"Column '{date_col}' not found in the DataFrame.")
    if value_col is None and agg != "count":
        raise ValueError(
            "value_col=None only supports agg='count' (rows per period). "
            f"Pass a value_col to use agg='{agg}'."
        )
    if value_col is not None and value_col not in df.columns:
        raise ValueError(f"Column '{value_col}' not found in the DataFrame.")
    if group_col is not None and group_col not in df.columns:
        raise ValueError(f"Column '{group_col}' not found in the DataFrame.")

    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col])
    if value_col is not None:
        work = work.dropna(subset=[value_col])
    if work.empty:
        raise ValueError("No rows remain after coercing dates / dropping nulls.")

    def _resample(sub: pd.DataFrame) -> pd.Series:
        idx = sub.set_index(date_col).sort_index()
        row_counts = idx.resample(freq).size()
        if agg == "count":
            series = (row_counts if value_col is None
                      else idx[value_col].resample(freq).count())
        else:
            series = getattr(idx[value_col].resample(freq), agg)()
        series = series.astype(float)
        # Empty periods → gaps (NaN), not zero.
        series[row_counts == 0] = np.nan
        return series

    value_label = "row count" if value_col is None else f"{agg} {value_col}"
    fig = go.Figure()
    subtitle = ""

    def _add_series(series: pd.Series, name: str, color: str) -> None:
        if rolling is not None:
            roll = series.rolling(rolling, min_periods=1).mean()
            fig.add_trace(go.Scatter(
                x=series.index, y=series.to_numpy(dtype=float), mode="lines",
                line=dict(color=color, width=1), opacity=0.35,
                connectgaps=False, showlegend=False, name=name,
                hovertemplate="%{y:.3g}<extra></extra>"))
            fig.add_trace(go.Scatter(
                x=roll.index, y=roll.to_numpy(dtype=float),
                mode="lines+markers" if show_points else "lines",
                line=dict(color=color, width=3), connectgaps=False,
                name=f"{name} ({rolling}-period roll)",
                hovertemplate="%{y:.3g}<extra></extra>"))
        else:
            fig.add_trace(go.Scatter(
                x=series.index, y=series.to_numpy(dtype=float),
                mode="lines+markers" if show_points else "lines",
                line=dict(color=color, width=2), connectgaps=False, name=name,
                hovertemplate="%{y:.3g}<extra></extra>"))

    if group_col is None:
        _add_series(_resample(work), value_label, PALETTE[0])
    else:
        counts = work[group_col].value_counts()
        levels = counts.index.tolist()
        if len(levels) > top_n_groups:
            subtitle = f"top {top_n_groups} of {len(levels)} groups"
            levels = levels[:top_n_groups]
        for i, level in enumerate(levels):
            sub = work[work[group_col] == level]
            _add_series(_resample(sub), str(level), PALETTE[i % len(PALETTE)])

    fig.update_layout(
        width=width, height=height if height is not None else 600,
        hovermode="x unified",
        xaxis=dict(title=dict(text=date_col, font=dict(size=13)),
                   showgrid=True, gridwidth=0.5, gridcolor=_GRID_CLR,
                   rangeslider=dict(visible=rangeslider)),
        yaxis=dict(title=dict(text=value_label, font=dict(size=13)),
                   type="log" if log_y else "linear", showgrid=True,
                   gridwidth=0.5, gridcolor=_GRID_CLR),
        legend=dict(bgcolor="rgba(0,0,0,0.4)",
                    bordercolor="rgba(255,255,255,0.15)", borderwidth=1,
                    font=dict(size=11, color=_FONT_CLR)),
        margin=dict(l=80, r=60, t=100, b=70),
    )
    _apply_base_layout(
        fig, title=title or f"{value_label} over time", subtitle=subtitle,
        width=width, height=height if height is not None else 600,
    )
    return fig


def pareto_plot(
    df: pd.DataFrame,
    category_col: str,
    value_col: Optional[str] = None,
    agg: Literal["sum", "count"] = "sum",
    top_n: Optional[int] = None,
    cutoff: Optional[float] = 0.8,
    title: str = "",
    width: int = 1400,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Pareto chart — bars by contribution + a cumulative-share line (the 80/20 view).

    Categories are ranked by their aggregated value with a cumulative-share line
    on a secondary axis, so "the few that matter" are obvious. The ``cutoff``
    guide marks how many categories cover a target share of the total.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    category_col : str
        Categorical column defining the bars.
    value_col : str, optional
        Numeric column to aggregate. ``None`` forces ``agg='count'`` (row counts
        per category); ``agg='count'`` with a value_col counts its non-null rows.
    agg : {'sum', 'count'}, default 'sum'
        Aggregate per category.
    top_n : int, optional
        Cap the number of bars *displayed* — cumulative shares are still computed
        on the full data so the line stays honest (subtitle notes the cap).
    cutoff : float, optional
        Target cumulative share in (0, 1] (default 0.8). Draws a dashed guide and
        highlights the covering categories; ``None`` disables the guide/split.
    title : str, default ""
        Main title; empty auto-generates a sensible title.
    width : int, default 1400
        Figure width in px.
    height : int, optional
        Figure height in px; ``None`` defaults to 600.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    if category_col not in df.columns:
        raise ValueError(f"Column '{category_col}' not found in the DataFrame.")
    if value_col is not None and value_col not in df.columns:
        raise ValueError(f"Column '{value_col}' not found in the DataFrame.")
    if cutoff is not None and not 0.0 < cutoff <= 1.0:
        raise ValueError(f"cutoff must be in (0, 1]; got {cutoff}.")

    if value_col is None:
        series = df.groupby(category_col).size()
        agg = "count"
    elif agg == "count":
        series = df.groupby(category_col)[value_col].count()
    else:
        series = df.groupby(category_col)[value_col].sum()

    series = series[series > 0].sort_values(ascending=False)
    if series.empty:
        raise ValueError("No positive aggregated values to plot.")

    total = float(series.sum())
    m = len(series)
    share = series.to_numpy(dtype=float) / total
    cum_share = np.cumsum(share)

    n_cover = None
    if cutoff is not None:
        n_cover = int(np.searchsorted(cum_share, cutoff, side="left")) + 1
        n_cover = min(max(n_cover, 1), m)

    disp = m if top_n is None else min(top_n, m)
    cats = [str(c) for c in series.index[:disp].tolist()]
    vals = series.to_numpy(dtype=float)[:disp]
    share_d = share[:disp]
    cum_d = cum_share[:disp]

    if cutoff is not None:
        colors = [PALETTE[0] if i < n_cover else _OTHER_COLOR
                  for i in range(disp)]
    else:
        colors = [PALETTE[0]] * disp

    bar_name = "row count" if value_col is None else f"{agg} {value_col}"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=cats, y=vals, marker=dict(color=colors), name=bar_name,
        customdata=np.stack([share_d * 100, cum_d * 100], axis=1),
        hovertemplate=("<b>%{x}</b><br>value: %{y:.3g}"
                       "<br>share: %{customdata[0]:.1f}%"
                       "<br>cumulative: %{customdata[1]:.1f}%<extra></extra>"),
        showlegend=False,
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=cats, y=cum_d * 100, mode="lines+markers", name="cumulative %",
        line=dict(color="#19D3F3", width=2), marker=dict(size=6),
        hovertemplate="cumulative: %{y:.1f}%<extra></extra>", showlegend=False,
    ), secondary_y=True)

    if cutoff is not None:
        fig.add_hline(
            y=cutoff * 100, line=dict(color="#FFD700", width=1.5, dash="dash"),
            secondary_y=True)

    annotations = []
    if cutoff is not None:
        annotations.append(dict(
            text=(f"<b>{n_cover} of {m}</b> categories cover "
                  f"≥{cutoff:.0%} of total"),
            xref="paper", yref="paper", x=0.99, y=0.99,
            xanchor="right", yanchor="top", showarrow=False,
            font=dict(size=12, color="#fafafa"),
            bgcolor="rgba(0,0,0,0.55)", bordercolor="#FFD700",
            borderwidth=1, borderpad=6))

    subtitle = f"showing top {disp} of {m}" if disp < m else ""
    value_axis_title = "row count" if value_col is None else f"{agg} {value_col}"

    fig.update_layout(
        width=width, height=height if height is not None else 600,
        annotations=annotations,
        xaxis=dict(title=dict(text=category_col, font=dict(size=13)),
                   tickfont=dict(size=11), tickangle=-40),
        margin=dict(l=80, r=80, t=110, b=110),
    )
    fig.update_yaxes(title_text=value_axis_title, showgrid=True, gridwidth=0.5,
                     gridcolor=_GRID_CLR, secondary_y=False)
    fig.update_yaxes(title_text="cumulative %", range=[0, 105], showgrid=False,
                     secondary_y=True)
    _apply_base_layout(
        fig, title=title or f"Pareto of {category_col}", subtitle=subtitle,
        width=width, height=height if height is not None else 600,
    )
    return fig
