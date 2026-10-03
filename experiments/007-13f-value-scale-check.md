# 007: Flag 13F filings that still report values in thousands

**Status:** VALIDATED
**Date:** 2026-10-03
**Targets:** 13F value scale. Filings made on or after 3 Jan 2023 must report
whole dollars, and `er.datasources.sec_13f` trusts that (`value_unit = 'USD'`).
An outside review claimed 334 Q2 2026 holdings reports (3.8%) still look like
thousands. That was third-party analysis, so it had to be reproduced on our own
data before it became a rule.

## Hypothesis

A filer that reports in thousands is wrong on every row by the same factor, so
its rows' implied prices (value / shares) should sit near 1/1000 of what every
other filer implies for the same CUSIP and period. No external price feed is
needed: the 13F population is its own consensus. If the per-filing median
ratio is bimodal with a clean gap near 10^-3, a fixed band is a safe flag.

OpenFIGI was proposed as the price source. It doesn't return prices, so it
can't be used for this.

## Method

`check_value_scale()` in `src/er/datasources/sec_13f/ingest.py`, run over
`sec_13f_effective_holdings.parquet` from `01mar2026-31may2026_form13f.zip`:

- rows: `value_unit = 'USD'`, `put_call IS NULL`, `SH` (not `PRN`), shares and
  value > 0
- consensus: median implied price per (period, CUSIP) when at least 5 distinct
  filers report it
- per filing: median of row price / consensus over the compared rows; flagged
  when at least 5 rows compare and the median falls in [0.0005, 0.002]
  (`sec_13f.scale_check` in config)

```bash
uv run python -c "from er.config import load_config; \
from er.datasources.sec_13f.ingest import check_value_scale; print(check_value_scale(load_config()))"
```

The flag is written to `sec_13f_scale_checks.parquet`. Values are never
rescaled. `get_position_history` adds a warning to its evidence when a row it
uses comes from a flagged filing.

## Result

Distribution of the per-filing median ratio (8,477 filings with at least 5
comparable rows):

| log10(ratio) bucket | filings |
|---|---|
| -3.5 | 156 |
| -3.0 | 143 |
| -2.5 | 1 |
| -1.5 | 3 |
| -0.5 | 1,991 |
| 0.0 | 6,181 |
| 1.0 / 1.5 | 1 / 1 |

- **299 of 8,477 flagged (3.5%)**. For the 31-MAR-2026 period alone: 288 of
  7,868 (3.7%), close to the claimed 3.8% for a different quarter.
- Widening the band 2.5x either side ([0.0002, 0.005]) flags the same 299, so
  the threshold isn't doing fragile work. Only 4 filings fall between 0.002 and
  0.5.
- Spot check, `0000080255-26-000381` (T. Rowe Price Associates, 4,518 compared
  rows): Apple at 179,340,662 shares with value 45,514,867 implies $0.25 a
  share. The real price was about $254, so the filing is in thousands.

## Verdict

Kept as a flag, not a correction. A filing in the band is almost certainly in
thousands, but rescaling it silently would hide a source defect behind a
number that looks authoritative. The answer path shows the value as filed with
the warning attached. Not covered: filers with fewer than 5 comparable rows,
and CUSIPs reported by fewer than 5 filers.
