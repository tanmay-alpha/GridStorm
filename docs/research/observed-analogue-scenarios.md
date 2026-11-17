# Observed-analogue scenarios (scigrid-de)

Status: implemented 2026-11-14; provenance and numerical checks completed 2026-11-15; rebuilt
2026-11-15 for ENTSO-E re-use compliance (§1.1, `docs/research/entsoe-reuse-check.md`). Code:
`pipelines/observed/` (one uv project, package `gridstorm_observed`, for both the
electricity-demand/renewables pipeline and the weather pipeline; there are no separate
`pipelines/electricity-demand/` or `pipelines/weather/` projects). Outputs:
`data/scenarios/observed/*.yaml`, `data/observed/opsd-de/`, `data/observed/nasa-power-de/`,
`data/observed/analogue-results.json`.

A *historical-analogue scenario* takes a stress day that was observed in Germany (high load,
little wind and sun) and replays its demand shape and its renewable shortfall on the `scigrid-de`
network (PyPSA SciGRID example, 24 hourly snapshots of 2011-01-01; `network.nc` sha256
`284850c8…5236500`). The mapping and every result are **modeled**.

## 1. Data sources and licences

| Source | What we use | Licence / terms (checked 2026-11-14–15) | What is committed |
|---|---|---|---|
| Open Power System Data, *Time series*, version **2020-10-06** ([package page](https://data.open-power-system-data.org/time_series/), [datapackage metadata](https://data.open-power-system-data.org/time_series/2020-10-06/datapackage.json)), DOI [10.25832/time_series/2020-10-06](https://doi.org/10.25832/time_series/2020-10-06) | `time_series_60min_singleindex.csv` (130 339 665 bytes, sha256 `6a7f2bc5…c704c8`): `DE_load_forecast_entsoe_transparency` ("Day-ahead load forecast in Germany", ENTSO-E), and, for detection only, the German actual load and wind/solar generation and capacity columns (MW, UTC hour start) | No `licenses` field in the datapackage; the page's CC-BY notice covers text. Per column (manifest `source.column_reuse`): the **day-ahead load forecast** is ENTSO-E Reg. 543/2013 Art. 6.1.b = item #1 of the ENTSO-E free re-use list (2023-10-18) → **CC BY 4.0**. Actual load (Art. 6.1.a) and actual generation (Art. 16.1) are **not** on the list. Capacities are OPSD calculations based on BNetzA and netztransparenz.de, with no declared licence. | Per stress day: 24 demand multipliers (CC BY 4.0, derived from the forecast), one daily multiplier per renewable carrier (rounded to 0.05), dates and criteria. No OPSD series, no observed MW value or statistic. |
| NASA POWER Hourly API (v2.10.4; MERRA-2/POWER), no key | `T2M` (°C), `WS10M` (m/s), Berlin/Hamburg/Cologne/Munich; stress day ±3 days, UTC | [NASA Earthdata use guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance) permits factual use and redistribution of unrestricted NASA material with acknowledgement and without implied endorsement. The [POWER referencing guide](https://power.larc.nasa.gov/docs/referencing/) requires service/version/access-date attribution and requests redistribution notification. No POWER-specific SPDX licence is asserted. | 2016 rows, no missing values, plus request URLs and response/extract hashes. **Reanalysis-derived** MERRA-2 grid-cell values (about 0.5° × 0.625°), not station measurements. |
| scigrid-de network | `loads_t.p_set`, `generators_t.p_max_pu`, `p_nom`, `carrier` | See the network's `data/networks/scigrid-de/manifest.json` | none (read only) |

Attribution (CC BY 4.0, also in every scenario's first assumption and in the manifest's
`license.load_forecast_attribution`): *Day-ahead forecast of the total load per market time unit,
Germany (Reg. (EU) 543/2013 Art. 6.1.b), ENTSO-E Transparency Platform
(https://transparency.entsoe.eu/), obtained via Open Power System Data, Time series 2020-10-06
(https://doi.org/10.25832/time_series/2020-10-06), column DE_load_forecast_entsoe_transparency.
Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/) per the ENTSO-E list of
data available for free re-use (2023-10-18), item #1. Changes made by GridStorm: the stress day's 24
hourly values are divided by the mean of the nearest 1 January (UTC), then by the scigrid-de
network's normalized hourly load, and rounded to 4 decimals; only these ratios are published.*
OPSD citation: *Open Power System Data. 2020. Data Package Time series. Version 2020-10-06.
https://doi.org/10.25832/time_series/2020-10-06.* NASA POWER: see its manifest's `attribution`.

### 1.1 Re-use rule and how it is enforced

`docs/research/entsoe-reuse-check.md` found that the first version of these files let anyone rebuild
the observed hourly actual load to within 2.4 MW (from the demand multipliers plus the committed
`reference_day_mean_load_mw`) and the observed hourly capacity factors (CF) to within 5·10⁻⁵ in
unclipped hours. Those series are not openly licensed. The rebuild therefore follows one rule:
**nothing committed may allow a non-open ENTSO-E series to be reconstructed.**

- **Demand** uses the day-ahead total load forecast, which is CC BY 4.0. The actual load only
  selects the stress dates.
- **Renewables.** A coarse per-hour ratio was checked first: the ratio to the network profile,
  rounded to 0.05 and clipped to ≤ 1. It still returns the observed hourly CF to within
  0.025 · CF_net. Measured on the three stress days in unclipped hours, the maximum error was
  0.004–0.025 CF. On the peak-load day, offshore wind came back within 0.022 at a CF of about 0.9.
  That is a meaningful reconstruction, so it was rejected. Each carrier now gets **one MODELED
  daily multiplier** (§3). Only the renewable shortfall of the day enters the scenario, not its
  hourly profile.
- **Observed absolutes removed.** The following are no longer written anywhere:
  - `reference_day_mean_load_mw`, the peak load and its hour, daily-mean loads, and the
    combined-day load threshold;
  - observed daily/rolling CF means, the per-hour renewable multipliers, and hours of
    clipping/CF > 1. The CF > 1 flag is kept as a count only.
- **Test.** `pipelines/observed/tests/test_reuse.py` has two parts.
  - Always-run checks: no non-open column name appears in the scenarios,
    `derived-multipliers.json` or `analogue-results.json`; none of the removed keys appears; and
    every renewable event is a single full-day event on the 0.05 grid.
  - Reconstruction attempt against the cached, sha256-verified OPSD CSV (skipped when the cache is
    absent). Even with an *oracle* least-squares scale fitted to the secret values, the actual
    hourly load must miss by **> 500 MW** in some hour. The observed hourly CF, rebuilt with the
    committed w or the oracle scale, must miss by **> 10 % of the day's peak CF** for every carrier
    and day. A positive control checks that the committed multipliers do return the (open)
    forecast to within 10 MW.
  - Measured margins: actual load misses by at least **1 054 / 2 059 / 2 608 MW** on 2017-01-24 /
    2015-01-20 / 2017-12-13. The CF error is at least **0.15** of the peak CF (solar, 2017-12-13).
  - The same test fails on the previous files: load error 2.2–2.5 MW; CF errors 0.000–0.076 of
    peak in several carrier-days.
- **What remains derivable.** With the network's daily-mean CF, the committed w gives the
  observed daily-mean CF only to within ±0.025 · mean CF_net per carrier and day. That is one
  rounded number, not a series. It still derives from unlisted Art. 16.1 data. **[INFERENCE]**
  This is not a reproduction of the series, but no ENTSO-E/TSO permission has been obtained for it
  either.

Reproduction requires the user's own sha256-verified OPSD download.

### Missing values and quality flags

- No interpolation and no filling, anywhere. `opsd.read_de` reindexes the source onto a gap-free
  hourly UTC grid, so a missing hour becomes NaN. Any UTC day or window that contains a NaN hour is
  excluded from detection, and a day can only be mapped if all of its hours are present.
- Coverage of the cached source: 2014-12-31T23:00Z to 2020-09-30T23:00Z (50 401 hours). Actual
  load is missing for 1 hour and the load forecast for 25. Capacities stop on 2019-12-30, so CF
  criteria use only complete days up to then. Generation is missing for 73 hours (onshore wind),
  75 (offshore wind) and 104 (solar). The stress days and their reference days are complete in
  every column used.
- Flag on the peak-load day: observed offshore wind generation is **above** the OPSD offshore
  capacity (CF > 1) in 7 UTC hours. Lagging capacity data are one possible explanation, not a
  verified cause. Values are retained and flagged. They enter only the daily ratio, which is
  clipped to 0.9 (< 1) for offshore that day.

## 2. Detecting stress days (`gridstorm_observed.detect`)

A day is a **UTC calendar day** (00:00–23:00 UTC). Detection runs on the actual load and on the
hourly CF

$$CF_{ws}(t)=\frac{G_{on}+G_{off}+G_{pv}}{C_{on}+C_{off}+C_{pv}}(t), \qquad CF_c(t)=G_c(t)/C_c(t).$$

Only the resulting dates, criteria and day counts are committed.

| Criterion | Definition | Result |
|---|---|---|
| (a) highest-load day | UTC day containing the highest hourly actual load, over all complete days (2100 days) | **2017-12-13** |
| (b) winter *Dunkelflaute* | Complete UTC day in Dec–Feb (445 days) with the lowest daily-mean wind+solar CF | **2015-01-20**. The lowest rolling 24 h window starting at any hour is 2015-01-20 04:00 → 2015-01-21 04:00 UTC. |
| (c) combined | Among complete days whose daily-mean actual load is at or above the 0.90 quantile of daily-mean load (182 of 1815 days), the day with the lowest daily-mean CF_ws | **2017-01-24** |

Ties go to the earliest timestamp. Weather on these days (NASA POWER, four-city mean, UTC day):
2017-12-13 T2M 0.06 °C, WS10M 6.38 m/s (windy); 2015-01-20 −1.11 °C, 1.70 m/s; 2017-01-24
−4.09 °C, 1.95 m/s (Munich −9.96 °C mean, −12.54 °C min). Both low-renewable days are cold and calm.

## 3. Mapping to the network (MODELED, `gridstorm_observed.mapping`)

Hour $h$ of the UTC stress day maps to network snapshot $h$ (2011-01-01 $h$:00).

**Why UTC.** `alignment_evidence` in `derived-multipliers.json` compares 1 January profiles
(2015–2020) with the network's profiles under two alignments. Load here is the day-ahead forecast;
solar is the observed CF, reported only as a multi-year mean correlation.

| Alignment | Mean r, solar CF (4 years) | Mean r, load forecast (years) | Load min/max hour matches network |
|---|---|---|---|
| UTC | 0.984 | 0.759 (6) | 4/6, 6/6 |
| Europe/Berlin | 0.814 | 0.847 (5) | 0/5, 0/5 |

Solar is the physically decisive test, and it points to UTC. For load the evidence is weaker: the
correlation is higher in local time, but the daily minimum and maximum hours line up in UTC.

**Demand.** Let $L_{net}(h)$ be the total network load and $F(d,h)$ the ENTSO-E day-ahead total
load forecast on stress day $d$. Let $r$ be the **1 January nearest to $d$ with complete data**,
the analogue of the network's own day (same calendar day, same holiday, same season). Then

$$m_h=\frac{F(d,h)/\overline{F(r,\cdot)}}{L_{net}(h)/\overline{L_{net}}}
\;\Rightarrow\; m_h L_{net}(h)=\overline{L_{net}}\,\frac{F(d,h)}{\overline{F(r,\cdot)}} .$$

The scaled network load follows the forecast shape exactly. Its level relative to the network's
1 January mean equals the forecast stress-day level relative to the forecast 1 January mean. The
actual load differs from the forecast by the forecast error. On these days, an oracle-scaled
forecast shape misses the actual load by 1.1–2.6 GW in the worst hour. Values are rounded to 4
decimals and clipped to the StormSpec range $(0, 5]$; nothing was clipped. Each multiplier applies
to **all loads**: `buses: null`, `window: {start: h, end: h+1}`.

**Renewables (MODELED shortfall)**, per carrier $c$ ∈ {Wind Onshore, Wind Offshore, Solar}, one
multiplier for the whole day, applied to every generator of $c$:

$$CF_{net,c}(h)=\frac{\sum_g p_{max,pu,g}(h)\,p_{nom,g}}{\sum_g p_{nom,g}},\qquad
w_c=\min\!\left(\operatorname{round}_{0.05}\!\left(\frac{\overline{CF_{obs,c}}}{\overline{CF_{net,c}}}\right),1\right).$$

The network's own hourly shape is kept; only its level is scaled. StormSpec requires $w\le 1$, so
a day with more output than the network's day keeps $w=1$ (*clipped*) and gets no event. Each
$w<1$ is one event with `window: {start: 0, end: 24}`.

| Scenario | Demand m (min–max) | Scaled network peak / energy | w onshore → modeled mean CF | w offshore → CF | w solar → CF | Events |
|---|---|---|---|---|---|---|
| `observed-peak-load-2017-12-13` (ref 2018-01-01) | 1.130–1.899 | 82 715 MW / 1 760 101 MWh | 1.00 (clipped) → 0.528 | 0.90 → 0.876 | 0.70 → 0.037 | 26 |
| `observed-dunkelflaute-2015-01-20` (ref 2015-01-01) | 1.038–1.775 | 76 905 MW / 1 623 499 MWh | 0.05 → 0.026 | 0.10 → 0.097 | 0.25 → 0.013 | 27 |
| `observed-high-load-low-res-2017-01-24` (ref 2017-01-01) | 1.158–1.944 | 83 325 MW / 1 779 121 MWh | 0.05 → 0.026 | 0.15 → 0.146 | 0.20 → 0.011 | 27 |

The unscaled network day has mean load 50 415 MW and peak 58 425 MW. Its network-day mean CFs are
0.528 onshore, 0.974 offshore and 0.053 solar. Its variable capacity is 37 340 MW onshore wind (488
generators), 2 974 MW offshore wind (5) and 37 042 MW solar (489). No multiplier exceeds 2, so the
StormSpec warning `large_multiplier` no longer occurs.

## 4. Results (MODELED, PyPSA LOPF, HiGHS, threads = 1)

These are real runs of `gridstorm_pypsa.run_scenario` on `data/networks/scigrid-de`
(`network.nc` sha256 `284850c8…`), executed one at a time in the `workers/pypsa` environment with
pypsa 1.4.0, linopy 0.10.1 and highspy 1.16.0 (2026-11-15). Settings: 24 snapshots, load shedding at
VOLL 10 000 €/MWh, curtailment allowed, storage dispatch on. Every scenario validated
(`valid: true`) against both `canonical.json` and the index of the loaded network, with no
validation warnings. The baseline is the same scenario with no events, so it is the network's own
2011-01-01 day. Source: `data/observed/analogue-results.json`.

| Scenario | Outcome | Load (MWh) | Unserved energy (MWh) | Peak shed (MW) | Shed hours | Total cost (€) | of which generation (€) | Wind+solar curtailment (MWh) | Max / mean line loading (%) | Congested lines | Storage discharge (MWh) | HiGHS time (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (2011-01-01, no events) | feasible | 1 209 952 | 0 | 0 | 0 | 6 684 817 | 6 684 817 | 69 591 | 100.0 / 22.9 | 42 | 32 434 | 2.5 |
| `observed-dunkelflaute-2015-01-20` | feasible | 1 623 499 | 2 721 | 230 | 17 | 59 147 318 | 31 937 249 | 0 | 100.0 / 22.0 | 26 | 20 159 | 2.4 |
| `observed-high-load-low-res-2017-01-24` | feasible | 1 779 121 | 4 731 | 346 | 20 | 87 280 269 | 39 965 730 | 0 | 100.0 / 23.4 | 36 | 39 632 | 2.8 |
| `observed-peak-load-2017-12-13` | feasible | 1 760 101 | 4 429 | 335 | 19 | 66 189 364 | 21 895 909 | 38 621 | 100.0 / 25.7 | 50 | 33 981 | 2.7 |

All four runs terminated optimally. Their largest nodal balance residual was **3.24 × 10⁻⁷ MW**
(baseline). The summary also records independently integrated serialized load, shedding,
generation and net-storage series. Tests check these against the physical energy balance and the
reported metrics, with an explicit bound for four-decimal MW serialization. Maximum line loading
was 100 % in all four cases. PyPSA logged zero-resistance transformer warnings in this source
network; these solves do not provide an AC feasibility certificate.

**Change against the first (non-compliant) version** (actual-load demand, hourly renewable
multipliers). The baseline is unchanged.

| Scenario | Load | Unserved energy | Peak shed | Shed hours | Total cost | Wind+solar curtailment | Congested lines |
|---|---|---|---|---|---|---|---|
| Dunkelflaute 2015-01-20 | 1 655 703 → 1 623 499 MWh (−1.9 %) | 3 237 → 2 721 MWh (−15.9 %) | 261 → 230 MW | 17 → 17 | 66.23 → 59.15 M€ (−10.7 %) | 0 → 0 MWh | 32 → 26 |
| Combined 2017-01-24 | 1 916 278 → 1 779 121 MWh (−7.2 %) | 20 500 → 4 731 MWh (−76.9 %) | 1 662 → 346 MW | 24 → 20 | 253.03 → 87.28 M€ (−65.5 %) | 458 → 0 MWh | 44 → 36 |
| Peak load 2017-12-13 | 1 836 261 → 1 760 101 MWh (−4.1 %) | 5 648 → 4 429 MWh (−21.6 %) | 437 → 335 MW | 20 → 19 | 82.19 → 66.19 M€ (−19.5 %) | 19 199 → 38 621 MWh | 51 → 50 |

There are two drivers. First, the forecast-based demand is 1.9–7.2 % lower in energy: the
forecast's stress-day/1 January level ratio is smaller than the one computed from actual load.
Unserved energy responds strongly because demand sits at the edge of the network's dispatchable and
transfer limits. Second, on the peak-load day, onshore wind now keeps the network's full
availability all day (w = 1). Before, it was clipped hour by hour to the lower of the two profiles.
Onshore output rises from 425 092 to 447 285 MWh, and curtailment doubles.

How to read the table (modeled findings, not predictions):

- On the network's own day, all load is served; 42 branches reach their limit and 69.6 GWh of
  wind and solar is curtailed. These outputs alone do not identify why each MWh was curtailed.
- All three observed analogues require load shedding. The combined high-load / low-renewable case
  still has the largest unserved energy (4.7 GWh over 20 hours; 54 % of total cost is load
  shedding). The peak-load case is now close behind at 4.4 GWh: its demand energy is 8.4 % above
  the Dunkelflaute case, and it has 38.6 GWh of wind+solar curtailment. A controlled
  counterfactual would be needed to separate the effects of transmission, dispatchable
  availability, demand and renewable level. National nameplate capacity alone cannot establish the
  cause of shedding.
- Results carry the adapter's warning that the dataset has no CO2 intensities (`co2_emissions_t`
  is null).

## 5. Limitations

- **Different systems.** The network has 2011 topology, a 2011 demand profile and renewable
  capacities from the end of 2014. The observed days are 2015–2017. Installed capacities are not
  rescaled, so this is an analogue stress test, not a reconstruction of the observed day.
- **Forecast, not actual demand.** Demand follows the day-ahead forecast. In the worst hour it
  misses the actual load by 1.1–2.6 GW, even after an oracle rescaling. This is the price of
  publishing only openly licensed data.
- **Renewable shape is the network's.** One daily multiplier per carrier scales the network's
  2011-01-01 hourly profile. The observed hourly timing of wind and sun (for example, a calm
  evening after a windy morning) is not represented. Rounding to 0.05 moves the modeled daily mean
  CF by up to ±0.025 · CF_net (about ±0.013 onshore, ±0.024 offshore, ±0.0013 solar).
- **Clipping (StormSpec w ≤ 1).** On the peak-load day, onshore wind was stronger than on the
  network's day. It keeps the network's own availability (w = 1), which understates renewable
  supply on that day.
- **National aggregates applied uniformly.** One multiplier applies to every load, and one to every
  generator of a carrier. The spatial pattern stays the network's own 2011-01-01 pattern, so real
  regional differences are lost.
- **The reference day sets the demand level.** Every level is relative to a 1 January forecast, a
  public holiday with low load. Multipliers of 1.5–1.9 on morning hours reflect "winter working
  day vs holiday", not demand growth.
- **DC LOPF with perfect foresight.** No losses, reactive power or voltage limits, no unit
  commitment, and short-run marginal costs only. Load shedding is priced at VOLL 10 000 €/MWh, so
  unserved energy measures network and capacity limits under this model, not a blackout prediction.
- **Data provenance.** OPSD has inconsistent offshore generation/capacity values (CF > 1). Weather
  values are reanalysis grid-cell values, not station measurements, and 10 m wind is not turbine
  hub-height wind or an independent validation of generation.
- **Licensing.** Without the user's own OPSD download (sha256-pinned), the committed multipliers
  cannot be regenerated. The reconstruction test then runs only its always-run part.

```bash
cd pipelines/observed
uv sync
uv run python -m gridstorm_observed.build          # downloads ~130 MB to the cache once, verifies sha256
cd ../../workers/pypsa
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 uv run python ../../pipelines/observed/scripts/run_analogues.py
cd ../../pipelines/observed
uvx ruff@0.14.0 check --fix . && uvx ruff@0.14.0 format .
uv run pytest -q                                   # 92 passed (2026-11-17), incl. the reconstruction attempt and observatory bundle tests
```

`--network-dir` (on both commands) overrides `data/networks/scigrid-de`. Full
`gridstorm-result/1.0` documents go to `<cache>/observed-runs/`. The summary is written to
`data/observed/analogue-results.json`.

Verification run (2026-11-15): the builder above (`--skip-weather`; the NASA POWER extract is
unchanged because the stress days are unchanged), four serial single-threaded adapter solves, Ruff
0.14.0 check/format, and `uv run pytest -q` (**38 passed**, with the OPSD cache present so the
reconstruction tests ran). These tests require the real canonical SciGRID network, not a synthetic
substitute. Re-run the solve command after regenerating scenarios so that scenario hashes and
recorded results stay synchronized.

Since GridStorm 3.2 (2026-11-17) the three scenarios are also published as **precomputed** Crisis
Studio presets (`packages/stormspec/presets/observed-*.yaml`, byte-identical copies guarded by
`publish_observatory.py --verify`) with full PyPSA result artifacts in `data/artifacts/pypsa/`
(unserved energy 2 721.006897 / 4 731.453896 / 4 429.345555 MWh, scenario hashes identical to
`analogue-results.json`), and the Data Observatory (`/data`) links to them. See
[observatory pipeline](../data/observatory-pipeline.md).
