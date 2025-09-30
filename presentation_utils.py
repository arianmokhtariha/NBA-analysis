import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from pandas.api import types as ptypes
import seaborn as sns
import matplotlib.pyplot as plt
import warnings
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from matplotlib.ticker import PercentFormatter
import numpy as np
from PIL import Image
import pathlib

from scipy.stats import pearsonr


### Mona


def snake_to_camel(s: str):
    parts = s.split("_")
    return parts[0].lower() + "".join(word.capitalize() for word in parts[1:])


def format_column_name(col: str) -> str:
    parts = col.split("_")
    if len(parts) > 1 and len(parts[-1]) <= 5:
        name = " ".join(parts[:-1])
        unit = parts[-1]
        return f"{name} ({unit})"
    else:
        return snake_to_camel(col)


def hist_plot(columns_list: list[str], dataframe: pd.DataFrame, x, y) -> None:
    N = len(columns_list)
    rows = int(np.floor(np.sqrt(N)))
    cols = int(np.ceil(N / rows))
    fig, axes = plt.subplots(rows, cols, figsize=(x, y))

    if N == 1:
        axes = [axes]
    else:
        axes = axes.flatten()

    palette = ["#2A9D8F", "#E76F51"]

    for i, col in enumerate(columns_list):
        sns.histplot(
            ax=axes[i],
            x=col,
            data=dataframe,
            hue="group_label",
            palette=palette,
            alpha=0.65,
            edgecolor="none",
        )

        axes[i].set_title(f"{format_column_name(col)}")
        axes[i].set_ylabel("")
        axes[i].set_xlabel("")
        axes[i].tick_params(axis="y")
        axes[i].grid(axis="x", linestyle="--", linewidth=0.4, alpha=0.3)
        axes[i].tick_params(axis="both")
        sns.despine(ax=axes[i], top=True, right=True)

    for j in range(N, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.show()


def kde_plot(columns_list: list[str], dataframe: pd.DataFrame, x: int, y: int) -> None:
    N = len(columns_list)
    rows = int(np.floor(np.sqrt(N)))
    cols = int(np.ceil(N / rows))
    fig, axes = plt.subplots(rows, cols, figsize=(x, y))

    if N == 1:
        axes = [axes]
    else:
        axes = axes.flatten()

    palette = ["#1D3557", "#E63946"]

    for i, col in enumerate(columns_list):
        sns.kdeplot(
            ax=axes[i],
            data=dataframe,
            x=col,
            hue="group_label",
            fill=True,
            common_norm=True,
            palette=palette,
            alpha=0.35,
            linewidth=1.0,
        )

        axes[i].set_title(f"{format_column_name(col)}")
        axes[i].set_ylabel("")
        axes[i].set_xlabel("")
        axes[i].tick_params(axis="y")
        axes[i].grid(axis="x", linestyle="--", linewidth=0.5, alpha=0.3)
        axes[i].tick_params(axis="both")
        sns.despine(ax=axes[i], top=True, right=True)

    fig.suptitle(
        f"Distribution of: {', '.join(format_column_name(cl) for cl in columns_list)} by group",
        fontweight="bold",
    )

    for j in range(N, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.show()


def box_plot(
    columns_list: list[str], dataframe: pd.DataFrame, fig_x: float, fig_y: float
) -> None:
    N = len(columns_list)
    rows = int(np.floor(np.sqrt(N)))
    cols = int(np.ceil(N / rows))
    fig, axes = plt.subplots(rows, cols, figsize=(fig_x, fig_y))

    if N == 1:
        axes = [axes]
    else:
        axes = axes.flatten()

    palette = ["#2A9D8F", "#E76F51"]

    for i, col in enumerate(columns_list):
        sns.boxplot(
            ax=axes[i],
            data=dataframe,
            x="group_label",
            y=col,
            palette=palette,
            linewidth=1.2,
            boxprops={"alpha": 0.8},
            medianprops={"color": "#1D3557", "linewidth": 1.4},
        )
        axes[i].set_title("")
        axes[i].set_ylabel("")
        axes[i].set_xlabel(f"{format_column_name(col)}")
        axes[i].grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.3)
        axes[i].tick_params(axis="both")
        sns.despine(ax=axes[i], top=True, right=True)

    for j in range(N, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.show()


def Yeo_johnson(df, column_name, label):
    transformed_data, lambda_val = stats.yeojohnson(df[column_name])
    stat, p_value = stats.shapiro(transformed_data)
    print(f"Yeo-Johnson transformation for {label}:")
    print(f"λ = {lambda_val:.3f}, shapiro p-value = {p_value:.3f}")

    fig, ax = plt.subplots(figsize=(8, 6))
    stats.probplot(transformed_data, dist="norm", plot=ax)
    ax.set_title(f'QQ Plot for "{label}" after Yeo-Johnson\nshapiro p = {p_value:.3f}')
    plt.tight_layout()
    plt.show()

    return transformed_data


### Alireza


def custom_barplot(
    data: pd.DataFrame,
    title_text,
    subtitle,
    footnote="",
    x_field="season",
    y_field="availability",
):
    fig_w, fig_h = 14, 6
    bg_color = "#0b1f23"
    bar_color = "#e74f6b"
    highlight_color = "#ffce54"
    text_color = "white"
    percent_fmt = "{:.0f}%"
    highlight_index = data[data[y_field] == data[y_field].max()].index

    df_clean = None
    df_clean = data.dropna(subset=[y_field]).copy()
    seasons = sorted(df_clean[x_field].unique())

    if ptypes.is_numeric_dtype(data[x_field].dtype):
        seasons_x = [
            f"{season}-{int(str(season)[2:]) + 1}"
            for season in sorted(df_clean[x_field].unique())
        ]
    else:
        seasons_x = seasons

    values = [
        df_clean[df_clean[x_field] == s][y_field].values[0] * 100 for s in seasons
    ]

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=bg_color)
    ax = fig.add_subplot(111)
    ax.set_facecolor(bg_color)

    x = np.arange(len(seasons_x))
    width = 0.60

    colors = [
        highlight_color if i == highlight_index else bar_color
        for i in range(len(values))
    ]

    bars = ax.bar(
        x,
        values,
        width=width,
        color=colors,
        edgecolor="#2a2a2a",
        linewidth=0.8,
        zorder=3,
    )

    for i, (b, v) in enumerate(zip(bars, values)):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v + 3,  # vertical offset
            percent_fmt.format(v),
            ha="center",
            va="bottom",
            fontsize=20,
            fontweight="bold",
            color=text_color if i != highlight_index else "#e74f6b",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(seasons_x, fontsize=14, color="#d6e3e3")
    ax.tick_params(axis="x", which="both", pad=10)

    ax.text(
        -0.02,
        1.08,
        title_text,
        transform=ax.transAxes,
        fontsize=20,
        fontweight="bold",
        color="#ff9fb3",
        ha="left",
    )
    ax.text(
        -0.02,
        1.02,
        subtitle,
        transform=ax.transAxes,
        fontsize=12,
        color="#d6e3e3",
        ha="left",
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#2f4f4f")
    ax.set_yticks([])

    ymax = 120
    # int(max(data)) + 60
    ax.set_ylim(0, ymax)
    ax.set_yticks([0, 25, 50, 75, 100, 120])
    ax.set_yticklabels([])
    ax.grid(axis="y", color="#154040", linestyle="--", linewidth=0.6, zorder=0)

    hx = x[highlight_index]
    ax.hlines(
        -2.5,
        hx - 0.3,
        hx + 0.3,
        transform=ax.get_xaxis_transform(),
        colors="#ff9fb3",
        linewidth=6,
        zorder=4,
    )

    ax.text(
        0.02,
        -0.12,
        footnote,
        transform=ax.transAxes,
        fontsize=12,
        color="#ffd1d9",
        bbox=dict(facecolor="#1a2b2b", alpha=0.6, boxstyle="round,pad=0.4"),
    )

    for b in bars:
        b.set_linewidth(0)
        b.set_alpha(0.95)

    plt.show()


#### Anoosha

for path in pathlib.Path("data_analysis/Anoosha/assets").glob("*.png"):
    img = Image.open(path)
    img = img.resize((300, 300))
    img.save(path)


def annotate_corr(ax, x, y, xpos=0.05, ypos=0.9):
    r, p = pearsonr(x, y)
    ax.text(
        xpos,
        ypos,
        f"r = {r:.2f}\np = {p:.3f}",
        transform=ax.transAxes,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7),
    )


def plot_superstar_tax_top10(usage_effic_df):
    plot_df = usage_effic_df.copy()
    plot_df["ts_pct"] = plot_df["true_shooting_percentage"] * 100
    g = sns.relplot(
        data=plot_df,
        x="usage_percentage",
        y="ts_pct",
        hue="season",
        col="player_name",
        col_wrap=6,
        height=4.8,
        aspect=1.0,
        palette="viridis",
        facet_kws=dict(sharex=True, sharey=True),
        s=140,
    )

    g.set_axis_labels("Usage Percentage %", "True Shooting Percentage %")
    g.set(xlim=(0, 70), ylim=(0, 70))
    g.set_titles("{col_name}", fontweight="bold", fontsize="14")
    g.set_axis_labels("", "")
    g.figure.supxlabel("Usage Percentage %", y=0.00, fontweight="bold", fontsize="14")
    g.figure.supylabel(
        "True Shooting Percentage %", x=0.003, fontweight="bold", fontsize="14"
    )
    g.fig.suptitle(
        "Superstar Tax for Top 10 Players ( 2019 - 2025 )",
        fontsize=15,
        fontweight="bold",
        y=1.02,
    )
    legend = g._legend
    legend.set_title("Season")
    legend.get_title().set_fontsize(16)

    for text in legend.get_texts():
        text.set_fontsize(14)

    g.tight_layout()
    plt.show()


def plot_superstar_tax(usage_effic_df):
    # plt.style.use("seaborn-v0_8-white")
    fig, ax = plt.subplots(2, 3, figsize=(18, 12), sharex=True, sharey=True)

    giannis = usage_effic_df[
        usage_effic_df["player_name"] == "giannis antetokounmpo"
    ].copy()
    giannis["ts_pct"] = giannis["true_shooting_percentage"] * 100
    sns.scatterplot(
        ax=ax[0, 0],
        data=giannis,
        x="usage_percentage",
        y="ts_pct",
        hue="season",
        palette="viridis",
        s=120,
    )
    ax[0, 0].set_xlim(0, 100)
    ax[0, 0].set_ylim(0, 100)
    ax[0, 0].set_xlabel("Usage Percentage %", fontweight="bold")
    ax[0, 0].set_ylabel("True Shooting Percentage %", fontweight="bold")
    ax[0, 0].set_title("Giannis Antetokounmpo", fontweight="bold")
    sns.despine(ax=ax[0, 0])
    logo = plt.imread("data_analysis/Anoosha/assets/gianni.png")
    ax[0, 0].add_artist(
        AnnotationBbox(
            OffsetImage(logo, zoom=0.7),
            (0.97, 0.05),
            frameon=False,
            xycoords="axes fraction",
            box_alignment=(1, 0),
        )
    )

    Harden = usage_effic_df[usage_effic_df["player_name"] == "james harden"].copy()
    Harden["ts_pct"] = Harden["true_shooting_percentage"] * 100
    sns.scatterplot(
        ax=ax[0, 1],
        data=Harden,
        x="usage_percentage",
        y="ts_pct",
        hue="season",
        palette="viridis",
        s=120,
    )
    ax[0, 1].set_xlim(0, 100)
    ax[0, 1].set_ylim(0, 100)
    ax[0, 1].set_xlabel("Usage Percentage %", fontweight="bold")
    ax[0, 1].set_ylabel("True Shooting Percentage %", fontweight="bold")
    ax[0, 1].set_title("James Harden", fontweight="bold")
    sns.despine(ax=ax[0, 1])
    logo = plt.imread("data_analysis/Anoosha/assets/harden.png")
    ax[0, 1].add_artist(
        AnnotationBbox(
            OffsetImage(logo, zoom=0.7),
            (0.97, 0.05),
            frameon=False,
            xycoords="axes fraction",
            box_alignment=(1, 0),
        )
    )

    tatum = usage_effic_df[usage_effic_df["player_name"] == "jayson tatum"].copy()
    tatum["ts_pct"] = tatum["true_shooting_percentage"] * 100
    sns.scatterplot(
        ax=ax[0, 2],
        data=tatum,
        x="usage_percentage",
        y="ts_pct",
        hue="season",
        palette="viridis",
        s=120,
    )
    ax[0, 2].set_xlim(0, 100)
    ax[0, 2].set_ylim(0, 100)
    ax[0, 2].set_xlabel("Usage Percentage %", fontweight="bold")
    ax[0, 2].set_ylabel("True Shooting Percentage %", fontweight="bold")
    ax[0, 2].set_title("Jayson Tatum", fontweight="bold")
    sns.despine(ax=ax[0, 2])
    logo = plt.imread("data_analysis/Anoosha/assets/tatum.png")
    ax[0, 2].add_artist(
        AnnotationBbox(
            OffsetImage(logo, zoom=0.6),
            (0.97, 0.05),
            frameon=False,
            xycoords="axes fraction",
            box_alignment=(1, 0),
        )
    )

    young = usage_effic_df[usage_effic_df["player_name"] == "trae young"].copy()
    young["ts_pct"] = young["true_shooting_percentage"] * 100
    sns.scatterplot(
        ax=ax[1, 0],
        data=young,
        x="usage_percentage",
        y="ts_pct",
        hue="season",
        palette="viridis",
        s=120,
    )
    ax[1, 0].set_xlim(0, 100)
    ax[1, 0].set_ylim(0, 100)
    ax[1, 0].set_xlabel("Usage Percentage %", fontweight="bold")
    ax[1, 0].set_ylabel("True Shooting Percentage %", fontweight="bold")
    ax[1, 0].set_title("Trae Young", fontweight="bold")
    sns.despine(ax=ax[1, 0])
    logo = plt.imread("data_analysis/Anoosha/assets/young.png")
    ax[1, 0].add_artist(
        AnnotationBbox(
            OffsetImage(logo, zoom=0.7),
            (0.97, 0.05),
            frameon=False,
            xycoords="axes fraction",
            box_alignment=(1, 0),
        )
    )

    edwards = usage_effic_df[usage_effic_df["player_name"] == "anthony edwards"].copy()
    edwards["ts_pct"] = edwards["true_shooting_percentage"] * 100
    sns.scatterplot(
        ax=ax[1, 1],
        data=edwards,
        x="usage_percentage",
        y="ts_pct",
        hue="season",
        palette="viridis",
        s=120,
    )
    ax[1, 1].set_xlim(0, 100)
    ax[1, 1].set_ylim(0, 100)
    ax[1, 1].set_xlabel("Usage Percentage %", fontweight="bold")
    ax[1, 1].set_ylabel("True Shooting Percentage %", fontweight="bold")
    ax[1, 1].set_title("Anthony Edwards", fontweight="bold")
    sns.despine(ax=ax[1, 1])

    logo = plt.imread("data_analysis/Anoosha/assets/edwards.png")
    ax[1, 1].add_artist(
        AnnotationBbox(
            OffsetImage(logo, zoom=0.7),
            (0.97, 0.05),
            frameon=False,
            xycoords="axes fraction",
            box_alignment=(1, 0),
        )
    )

    ax[1, 2].axis("off")
    fig.tight_layout()
    fig.suptitle(
        "True Shooting vs Usage (2019 - 2025)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )
    plt.show()


def fitline(ax, x, y):
    """
    draws a best-fit line for x,y on given matplotlib ax
    """
    m, b = np.polyfit(x, y, 1)
    x2 = [np.min(x), np.max(x)]
    ax.plot(x2, m * np.array(x2) + b, lw=1)


def team_performance_metrics(team_df: pd.DataFrame, season):
    """
    plots four team metrics against their rank in the provided season.
    metrics : effective field goal percentage, offensive rebound percentage, free throw rate and turnover percentage. uses fitline() helper function to draw a best fit line for each subplot.
    """
    fig, ax = plt.subplots(2, 2, sharex=True)

    x = team_df["rank"]
    ax[0, 0].scatter(x, team_df["effective_fg_percentage"])
    ax[0, 0].set_title("Effective Field Goal (%) vs Rank", fontweight="bold")
    ax[0, 0].set_ylim(top=80)
    fitline(ax[0, 0], x, team_df["effective_fg_percentage"])
    annotate_corr(ax[0, 0], x, team_df["effective_fg_percentage"])

    ax[0, 1].scatter(x, team_df["offensive_rebound_pct"])
    ax[0, 1].set_title("Offensive Rebound (%) vs Rank", fontweight="bold")
    ax[0, 1].set_ylim(top=50)
    fitline(ax[0, 1], x, team_df["offensive_rebound_pct"])
    annotate_corr(ax[0, 1], x, team_df["offensive_rebound_pct"])

    ax[1, 0].scatter(x, team_df["free_throw_rate"])
    ax[1, 0].set_title("Free-Throw Rate (%) vs Rank", fontweight="bold")
    ax[1, 0].set_ylim(top=50)
    fitline(ax[1, 0], x, team_df["free_throw_rate"])
    annotate_corr(ax[1, 0], x, team_df["free_throw_rate"])

    ax[1, 1].scatter(x, team_df["turnover_pct"])
    ax[1, 1].set_title("Turnover (%) vs Rank", fontweight="bold")
    ax[1, 1].set_ylim(top=50)
    fitline(ax[1, 1], x, team_df["turnover_pct"])
    annotate_corr(ax[1, 1], x, team_df["turnover_pct"])

    for axes in ax.flat:
        axes.set_ylim(bottom=0)
        axes.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))

    sns.despine(fig=fig)
    fig.tight_layout(rect=(0, 0.05, 1, 0.98))
    fig.tight_layout()

    fig.suptitle(
        (f"NBA {season} Teams Performance"),
        ha="center",
        y=1.05,
        fontsize=15,
        fontweight="bold",
        backgroundcolor="lightgrey",
    )

    fig.supxlabel(
        "Rank",
        x=0.51,
        y=-0.01,
        fontsize=13,
        fontweight="bold",
        backgroundcolor="lightgrey",
    )

    fig.supylabel(
        "Percentage (%)",
        x=-0.03,
        fontsize=13,
        fontweight="bold",
        backgroundcolor="lightgrey",
    )

    plt.show()


def compare_metric_correlations(team_2024, team_2025):
    metrics = [
        "effective_fg_percentage",
        "offensive_rebound_pct",
        "free_throw_rate",
        "turnover_pct",
    ]

    corr_2024 = team_2024[metrics].corrwith(team_2024["rank"]).reindex(metrics)
    corr_2025 = team_2025[metrics].corrwith(team_2025["rank"]).reindex(metrics)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True, sharex=True)

    axes[0].barh(metrics, corr_2024, height=0.6, alpha=0.6, color="darkblue")
    axes[0].set_title("2024 Team Performance Metrics", fontweight="bold")
    axes[0].set_xlabel("Correlation")

    axes[1].barh(metrics, corr_2025, height=0.6, alpha=0.6, color="darkblue")
    axes[1].set_title("2025 Team Performance Metrics", fontweight="bold")
    axes[1].set_xlabel("Correlation")

    axes[0].set_yticklabels(
        [
            "Effective Field Goal (%)",
            "Offensive Rebound (%)",
            "Free Throw Rate (%)",
            "Turnover (%)",
        ],
        fontweight="bold",
    )

    for ax in axes.flatten():
        ax.set_xlim(-1, 1)
        ax.set_xticks([-1, -0.5, 0, 0.5, 1])
        ax.axvline(0, color="black", linewidth=1)
        ax.set_xlabel("")

    sns.despine(fig=fig)
    fig.tight_layout()
    plt.show()


#### Mohsen


def Get_BestPicks_df_Ready(BestPicks_df: pd.DataFrame):
    # Replacing player_name with unusual characters with their correct name
    BestPicks_df.loc[1, "player_name"] = "luka doncic"
    BestPicks_df.loc[27, "player_name"] = "jonas valančiūnas"
    BestPicks_df.loc[38, "player_name"] = "kristaps porziņģis"
    # making new columns
    BestPicks_df.loc[BestPicks_df["draft_overall_pick_rank"] <= 5, "Top5_picks"] = 1
    BestPicks_df.loc[BestPicks_df["draft_overall_pick_rank"] > 5, "Top5_picks"] = 0

    BestPicks_df.loc[
        BestPicks_df["total_value_over_replacement_player"] >= 20, "vorp_tier"
    ] = "high_vorp"
    BestPicks_df.loc[
        BestPicks_df["total_value_over_replacement_player"] < 20, "vorp_tier"
    ] = "low_vorp"

    BestPicks_df.loc[BestPicks_df["age"] <= 30, "age_group"] = "20-30"
    BestPicks_df.loc[BestPicks_df["age"] >= 30, "age_group"] = "30-40"

    y = np.asarray(BestPicks_df["total_defensive_box_plus_minus"])
    choices = ["great", "decent", "bad"]
    def_conditions = [(y < 0), (y == 0), (y > 0)]

    BestPicks_df["defense_tier"] = np.select(def_conditions, choices, default="other")

    x = np.asarray(BestPicks_df["average_efficiency_rate"])
    choices = ["not_a_starter", "all-star_candidate", "mvp_candidate"]
    per_conditions = [(x <= 20), (x >= 20) & (x <= 25), (x >= 25)]

    BestPicks_df["per_reference_guide"] = np.select(
        per_conditions, choices, default="other"
    )
    # Changing format of numbers
    continuous_stats = [
        "average_efficiency_rate",
        "total_win_shares",
        "average_rebound_percentage",
        "average_assist_percentage",
        "average_steal_percentage",
        "average_block_percentage",
        "total_offensive_box_plus_minus",
        "total_defensive_box_plus_minus",
        "total_value_over_replacement_player",
    ]
    counts_stats = [
        "triple_doubles",
        "draft_overall_pick_rank",
        "age",
        "experience",
        "Top5_picks",
    ]
    for stat in continuous_stats:
        BestPicks_df[stat] = BestPicks_df[stat].apply(lambda x: np.round(x, 2))
    BestPicks_df = BestPicks_df.dropna(subset=["experience"])
    for stat in counts_stats:
        BestPicks_df[stat] = BestPicks_df[stat].apply(lambda x: int(x))
    BestPicks_df.reset_index(inplace=True)
    BestPicks_df = BestPicks_df.drop("index", axis=1)


#################################################### Data Visualization ##############################################################


def hist_plot_numerics(columns_list: list[str], dataframe: pd.DataFrame, x, y) -> None:
    N = len(columns_list)
    rows = int(np.floor(np.sqrt(N)))
    cols = int(np.ceil(N / rows))
    fig, axes = plt.subplots(rows, cols, figsize=(x, y))

    if N == 1:
        axes = [axes]
    else:
        axes = axes.flatten()

    for i, col in enumerate(columns_list):
        sns.histplot(ax=axes[i], x=col, data=dataframe, kde=True)
        axes[i].set_title(f"{col}")
        axes[i].set_ylabel("")
        axes[i].set_xlabel("")
        axes[i].tick_params(axis="y")
        axes[i].grid(axis="x", linestyle="--", linewidth=0.5, alpha=0.3)
        axes[i].tick_params(axis="both")
        sns.despine(ax=axes[i], top=True, right=True)

    fig.suptitle("histograms of Selected Columns", fontweight="bold")

    for j in range(N, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.show()


def ct_2var(col1_name: str, col2_name: str, df: pd.DataFrame):
    fig, ax = plt.subplots(2, 2, figsize=(15, 15))
    ax = ax.flatten()

    table = pd.crosstab(df[col1_name], df[col2_name])
    sns.heatmap(
        table,
        ax=ax[0],
        annot=True,
        fmt=".2f",
        cbar=False,
        linewidths=0.5,
        square=True,
        cmap="Greys",
    )
    sns.heatmap(
        table.div(table.sum(axis=1), axis=0),
        ax=ax[1],
        annot=True,
        fmt=".2f",
        cbar=False,
        linewidths=0.5,
        square=True,
        cmap="Greys",
    )

    d = df.copy()
    d[col1_name] = d[col1_name].astype("string")
    d[col2_name] = d[col2_name].astype("string")

    sns.histplot(
        data=d,
        x=col1_name,
        hue=col2_name,
        multiple="dodge",
        discrete=True,
        shrink=0.5,
        stat="percent",
        ax=ax[2],
    )
    sns.histplot(
        data=d,
        x=col2_name,
        hue=col1_name,
        multiple="fill",
        discrete=True,
        shrink=0.5,
        ax=ax[3],
    )

    sns.despine(right=True, top=True, ax=ax[2])
    sns.despine(right=True, top=True, ax=ax[3])

    ax[3].set_ylabel("proportion- normalized")

    plt.tick_params(axis="both", which="both", length=0)
    plt.tight_layout()
    plt.show()


#################################### Mohsen's code ##################################################################################


def continuous_vs_binary(
    Dataframe: pd.DataFrame, continuous_Column: str, Binary_Column: str, log_scale=False
):
    fig, ax = plt.subplots(2, 3, figsize=(20, 15))
    ax = ax.flatten()

    sns.boxplot(
        data=Dataframe, x=continuous_Column, color="Grey", palette="Greys", ax=ax[0]
    )
    sns.histplot(
        data=Dataframe[continuous_Column],
        kde=True,
        multiple="dodge",
        shrink=0.5,
        ax=ax[1],
        log_scale=log_scale,
    )
    stats.probplot(Dataframe[continuous_Column], dist="norm", fit=True, plot=ax[2])
    stat, p_norm = stats.shapiro(Dataframe[continuous_Column])

    line_markers = ax[1].get_lines()[0]

    line_markers.set_marker("o")
    line_markers.set_markerfacecolor("#005f73")
    line_markers.set_markeredgecolor("#22333b")
    line_markers.set_markersize(4)
    line_markers.set_alpha(0.7)

    ax[2].set_title(
        f"QQplot\n Shapiro p={np.format_float_positional(p_norm, precision=4)}"
    )

    sns.histplot(
        data=Dataframe,
        x=continuous_Column,
        hue=Binary_Column,
        multiple="stack",
        shrink=0.3,
        ax=ax[3],
        log_scale=log_scale,
    )

    sns.histplot(
        data=Dataframe,
        x=continuous_Column,
        hue=Binary_Column,
        log_scale=log_scale,
        stat="proportion",
        multiple="fill",
        shrink=0.3,
        ax=ax[5],
    )
    sns.despine(right=True, top=True, ax=ax[3])
    sns.despine(right=True, top=True, ax=ax[5])

    sns.kdeplot(
        data=Dataframe,
        x=continuous_Column,
        hue=Binary_Column,
        fill=True,
        common_norm=False,
        palette="crest",
        alpha=0.5,
        linewidth=0,
        ax=ax[4],
        log_scale=log_scale,
    )

    plt.tick_params(axis="both", which="both", length=0)
    plt.tight_layout()
    plt.show()

    # statistical tests
    # mann-whitney
    # group1= Dataframe[Dataframe[Binary_Column]==1][continuous_Column]
    # group2= Dataframe[Dataframe[Binary_Column]==0][continuous_Column]
    # U_statistics , mw_pvalue = stats.mannwhitneyu(group1 , group2)
    # if mw_pvalue<0.05:
    # print(f'for mann-whitney test p value {mw_pvalue} is smaller than 0.05; So there is strog evidance for rejecting the null hypothesis which is "there is no diffrence in median {continuous_Column} of sold users with conversion 1 or 0"')
    # elif mw_pvalue>=0.05:
    # print(f'for mann-whitney test p value {mw_pvalue} is larger than 0.05; So there is no evidance for rejecting the null hypothesis which is "there is no diffrence in median {continuous_Column} of sold users with conversion 1 or 0"')


def var_vs_binary_in_categorie(
    Dataframe: pd.DataFrame,
    Categorie_Column: str,
    Categories_list: list,
    var_column: str,
    target: str,
):
    groups_list = [
        Dataframe[Dataframe[Categorie_Column] == item] for item in Categories_list
    ]
    for group in groups_list:
        from scipy.stats import mannwhitneyu

        con_1 = group[group["conversion"] == 1]
        con_0 = group[group["conversion"] == 0]
        group_U, group_pvalue = mannwhitneyu(con_1[var_column], con_0[var_column])
        if group_pvalue < 0.05:
            print(
                f"pvalue:{group_pvalue}\nthere's a significant diffrence in {var_column} median for conversion in {list(group[Categorie_Column].unique())} categorie"
            )
        else:
            print(
                f"there's no evidence for significant diffrence in {var_column} median for conversion in {list(group[Categorie_Column].unique())} categorie"
            )


def vorp_vs_eff(col1_name: str, col2_name: str, df: pd.DataFrame):
    fig, ax = plt.subplots(2, 2, figsize=(15, 15))
    ax = ax.flatten()

    table = pd.crosstab(df[col1_name], df[col2_name])
    sns.heatmap(
        table,
        ax=ax[0],
        annot=True,
        fmt=".2f",
        cbar=False,
        linewidths=0.5,
        square=True,
        cmap="Greys",
    )
    sns.heatmap(
        table.div(table.sum(axis=1), axis=0),
        ax=ax[1],
        annot=True,
        fmt=".2f",
        cbar=False,
        linewidths=0.5,
        square=True,
        cmap="Greys",
    )

    d = df.copy()
    d[col1_name] = d[col1_name].astype("string")
    d[col2_name] = d[col2_name].astype("string")

    sns.histplot(
        data=d,
        x=col1_name,
        hue=col2_name,
        multiple="dodge",
        discrete=True,
        shrink=0.5,
        stat="percent",
        ax=ax[2],
    )
    sns.histplot(
        data=d[d[col1_name] == "all-star_candidate"],
        x=col2_name,
        hue=col1_name,
        discrete=True,
        shrink=0.5,
        ax=ax[3],
    )

    sns.despine(right=True, top=True, ax=ax[2])
    sns.despine(right=True, top=True, ax=ax[3])

    ax[3].set_ylabel("proportion- normalized")

    plt.tick_params(axis="both", which="both", length=0)
    plt.tight_layout()
    plt.show()
