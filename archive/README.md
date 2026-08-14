# Archive

The original Quera bootcamp submission, before this repository was rebuilt.

Nothing in the current pipeline reads anything in here. It is kept because the
rebuilt notebooks in `notebooks/` were derived from this work, and being able to
put the two side by side is useful — both for tracing where an analysis came from
and for showing what changed.

| Path | What it is |
| --- | --- |
| `data_analysis/` | Each team member's exploratory notebooks, one folder per person. |
| `presentation.ipynb` | The presentation notebook from the original submission. |
| `presentation_utils.py` | Its plotting and formatting helpers. |
| `assets/` | Player portraits used in the original deck. |

Two things in here are known to be wrong, and the rebuilt notebooks correct them:

- The H2 hypothesis test ran one-tailed with `alternative='greater'` and reported
  "cannot reject H0" at p ≈ 0.97, while its own t-statistic was −4.918. The effect
  was large and in the opposite direction. Its Yeo-Johnson transform was also fitted
  separately per group, which distorts a between-group comparison.
- Defensive box plus/minus was read with the sign backwards, which labelled the
  worst defenders as the best.
