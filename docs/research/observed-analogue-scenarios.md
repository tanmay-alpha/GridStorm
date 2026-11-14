# Observed-analogue scenarios (scigrid-de)

Status: implemented 2026-11-14; provenance and numerical checks completed 2026-11-15. Code: `pipelines/observed/` (one uv project, package
`gridstorm_observed`, for both the electricity-demand/renewables pipeline and the weather pipeline;
there are no separate `pipelines/electricity-demand/` or `pipelines/weather/` projects).
Outputs: `data/scenarios/observed/*.yaml`, `data/observed/opsd-de/`, `data/observed/nasa-power-de/`,
`data/observed/analogue-results.json`.

A *historical-analogue scenario* takes a stress day that was **observed** in Germany (high load,
little wind and sun) and replays its hourly shape on the `scigrid-de` network (PyPSA SciGRID
example, 24 hourly snapshots of 2011-01-01; `network.nc` sha256 `284850c8…5236500`). The inputs
are observed; the mapping and every result are **modeled**.

## 1. Data sources and licences

| Source | What we use | Licence / terms (checked 2026-11-14–15) | What is committed |
|---|---|---|---|
| Open Power System Data, *Time series*, version **2020-10-06** ([package page](https://data.open-power-system-data.org/time_series/), [datapackage metadata](https://data.open-power-system-data.org/time_series/2020-10-06/datapackage.json)), DOI [10.25832/time_series/2020-10-06](https://doi.org/10.25832/time_series/2020-10-06) | `time_series_60min_singleindex.csv` (130 339 665 bytes, sha256 `6a7f2bc5…c704c8`), German load and wind/solar generation and capacity columns (MW, UTC hour start) | No `licenses` field in the datapackage; the page's CC-BY notice covers text. **Per-column** metadata attributes load/generation to ENTSO-E Transparency, but capacities to **OPSD calculations based on BNetzA and netztransparenz.de**. Permission to redistribute the ENTSO-E-derived series is not established; see the [ENTSO-E terms](https://transparencyplatform.zendesk.com/hc/en-us/articles/40921911218961-Legal-Terms-and-Conditions) and [reuse list](https://transparencyplatform.zendesk.com/hc/en-us/article_attachments/40921869379729). | Only derived multipliers, detection summaries, source URLs and sha256 checksums. **No hourly OPSD series**, including capacity columns. Manifest records each column's source and the full CSV/datapackage checksums. Raw data stay outside the repository. |
| NASA POWER Hourly API (v2.10.4; MERRA-2/POWER), no key | `T2M` (°C), `WS10M` (m/s), Berlin/Hamburg/Cologne/Munich; stress day ±3 days, UTC | [NASA Earthdata use guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance) permits factual use and redistribution of unrestricted NASA material with acknowledgement and without implied endorsement. The [POWER referencing guide](https://power.larc.nasa.gov/docs/referencing/) requires service/version/access-date attribution and requests redistribution notification. No POWER-specific SPDX licence is asserted. | 2016 rows, no missing values, plus request URLs and response/extract hashes. **Reanalysis-derived** MERRA-2 grid-cell values (about 0.5° × 0.625°), not station measurements. |
| scigrid-de network | `loads_t.p_set`, `generators_t.p_max_pu`, `p_nom`, `carrier` | See the network's `data/networks/scigrid-de/manifest.json` | none (read only) |

Attribution: *Open Power System Data. 2020. Data Package Time series. Version 2020-10-06.
https://doi.org/10.25832/time_series/2020-10-06. (Primary data from various sources, for a complete
list see URL). German load/generation: ENTSO-E Transparency Platform. German capacities: OPSD
calculations based on BNetzA and netztransparenz.de.* NASA POWER: see its manifest's `attribution`.

Redistribution permission for the OPSD load/generation columns has not been verified. The
conservative policy is therefore to commit only derived parameters and summaries, not hourly
OPSD inputs of any kind. Reproduction requires the user's own sha256-verified download.

### Missing values and quality flags

- No interpolation and no filling, anywhere. `opsd.read_de` reindexes the source onto a gap-free
  hourly UTC grid, so a missing hour becomes NaN. Any UTC day or window that contains a NaN hour is
  excluded from detection, and a day can only be mapped if all of its hours are present.
- Coverage of the cached source: 2014-12-31T23:00Z to 2020-09-30T23:00Z (50 401 hours). Load is
  missing for 1 hour. Capacities stop on 2019-12-30, so capacity-factor (CF) criteria use only
  complete days up to then. Generation is missing for 73 hours (onshore wind), 75 (offshore wind)
  and 104 (solar).
- Flag on the peak-load day: observed offshore wind generation is **above** the OPSD offshore
  capacity (CF > 1) at 7 hours (UTC 16 and 18–23). Lagging capacity data are one possible
  explanation, not a verified cause. Values are retained and flagged; the mapping clips ratios to 1.

## 2. Detecting stress days (`gridstorm_observed.detect`)

A day is a **UTC calendar day** (00:00–23:00 UTC). Hourly CF is computed as

$$CF_{ws}(t)=\frac{G_{on}+G_{off}+G_{pv}}{C_{on}+C_{off}+C_{pv}}(t), \qquad CF_c(t)=G_c(t)/C_c(t).$$

| Criterion | Definition | Result |
|---|---|---|
| (a) highest-load day | UTC day containing the highest hourly load, over all complete days (2100 days) | **2017-12-13**: peak 77 549 MW at 16:00 UTC, daily mean 67 242 MW. The highest daily *mean* falls on another day: 2019-01-23, 68 184 MW. |
| (b) winter *Dunkelflaute* | Complete UTC day in Dec–Feb (445 days) with the lowest daily-mean wind+solar CF | **2015-01-20**: mean CF_ws = 0.0176. The lowest rolling 24 h window starting at any hour is 2015-01-20 04:00 → 2015-01-21 04:00 UTC, mean 0.0170. |
| (c) combined | Among complete days whose daily-mean load is at or above the 0.90 quantile of daily-mean load (threshold 63 578 MW, 182 of 1815 days), the day with the lowest daily-mean CF_ws | **2017-01-24**: mean load 67 232 MW, peak 75 845 MW, mean CF_ws = 0.0224 |

Ties go to the earliest timestamp. Weather on these days (NASA POWER, four-city mean, UTC day):
2017-12-13 T2M 0.06 °C, WS10M 6.38 m/s (windy); 2015-01-20 −1.11 °C, 1.70 m/s; 2017-01-24
−4.09 °C, 1.95 m/s (Munich −9.96 °C mean, −12.54 °C min). Both low-renewable days are cold and calm.

## 3. Mapping to the network (MODELED, `gridstorm_observed.mapping`)

Hour $h$ of the observed UTC day maps to network snapshot $h$ (2011-01-01 $h$:00).

**Why UTC.** `alignment_evidence` in `derived-multipliers.json` compares observed 1 January
profiles (2015–2020) with the network's profiles under two alignments:

| Alignment | Mean r, solar CF (4 years) | Mean r, load (years) | Load min/max hour matches network |
|---|---|---|---|
| UTC | 0.984 | 0.896 (6) | 5/6, 6/6 |
| Europe/Berlin | 0.814 | 0.921 (5) | 0/5, 0/5 |

Solar is the physically decisive test, and it points to UTC. For load the evidence is weaker: the
correlation is slightly higher in local time, but the daily minimum and maximum hours line up in UTC.

**Demand.** Let $L_{net}(h)$ be the total network load and $L_{obs}(d,h)$ the observed national load
on stress day $d$. Let $r$ be the **observed 1 January nearest to $d$ with complete data**, which is
the observed analogue of the network's own day (same calendar day, same holiday, same season). Then

$$m_h=\frac{L_{obs}(d,h)/\overline{L_{obs}(r,\cdot)}}{L_{net}(h)/\overline{L_{net}}}
\;\Rightarrow\; m_h L_{net}(h)=\overline{L_{net}}\,\frac{L_{obs}(d,h)}{\overline{L_{obs}(r,\cdot)}} .$$

Under this mapping, the scaled network load has exactly the observed shape. Its level relative to
the network's 1 January mean equals the observed day's level relative to the observed 1 January
mean. This choice also absorbs the level offset between the network's load (ENTSO-E 2011 data
scaled by 1.12 in the PyPSA example) and the observed year. Scaling to the peak would instead
remove the stress level we are trying to reproduce. Values are rounded to 4 decimals and clipped
to the StormSpec range $(0, 5]$; no clipping happened in any of the three scenarios. Each
multiplier applies to **all loads**: `buses: null`, `window: {start: h, end: h+1}` (half-open,
absolute snapshot index; the pypsa capability allows any window for `demand_multiplier`).

**Renewables**, per carrier $c$ ∈ {Wind Onshore, Wind Offshore, Solar}, applied to every generator
of $c$:

$$CF_{net,c}(h)=\frac{\sum_g p_{max,pu,g}(h)\,p_{nom,g}}{\sum_g p_{nom,g}},\qquad
w_{c,h}=\operatorname{clip}\!\left(\frac{CF_{obs,c}(h)}{CF_{net,c}(h)},0,1\right).$$

When $w$ is not clipped, the network's capacity-weighted CF becomes exactly $CF_{obs}$. StormSpec
requires $w\le 1$, so hours where the observed CF exceeds the network CF keep the network's own
availability. No event is emitted for those hours, and they are reported as *clipped*. Hours with
$CF_{net}=0$ (solar at night) are *undefined*: the multiplier has no effect there, so no event is
emitted.

| Scenario | Demand m (min–max) | Scaled network peak / energy | Onshore CF net → obs → modeled (clipped h) | Offshore CF (clipped h) | Solar CF (clipped / undefined h) | Events |
|---|---|---|---|---|---|---|
| `observed-peak-load-2017-12-13` (ref 2018-01-01) | 1.160–1.996 | 88 241 MW / 1 836 261 MWh | 0.528 → 0.694 → 0.488 (16 h, max raw ratio 2.71) | 0.974 → 0.891 → 0.827 (7 h) | 0.053 → 0.037 → 0.036 (1 / 16) | 56 |
| `observed-dunkelflaute-2015-01-20` (ref 2015-01-01) | 1.031–1.813 | 78 681 MW / 1 655 703 MWh | 0.528 → 0.024 → 0.024 (0) | 0.974 → 0.081 → 0.081 (0) | 0.053 → 0.012 → 0.012 (1 / 16) | 79 |
| `observed-high-load-low-res-2017-01-24` (ref 2017-01-01) | 1.253–2.073 | 90 074 MW / 1 916 278 MWh | 0.528 → 0.025 → 0.025 (0) | 0.974 → 0.163 → 0.163 (0) | 0.053 → 0.011 → 0.010 (1 / 16) | 79 |

The unscaled network day has mean load 50 415 MW and peak 58 425 MW. Its variable capacity is
37 340 MW onshore wind (488 generators), 2 974 MW offshore wind (5) and 37 042 MW solar (489).
Observed solar hours that the network does not have (UTC 7 and 15) cannot be represented. Multipliers
above 2 trigger the StormSpec warning `large_multiplier` (2017-01-24, hours 6–7). They stay valid.

## 4. Results (MODELED, PyPSA LOPF, HiGHS, threads = 1)

These are real runs of `gridstorm_pypsa.run_scenario` on `data/networks/scigrid-de` (`network.nc`
sha256 `284850c8…`), executed one at a time in the `workers/pypsa` environment with pypsa 1.4.0,
linopy 0.10.1 and highspy 1.16.0. Settings: 24 snapshots, load shedding at VOLL 10 000 €/MWh,
curtailment allowed, storage dispatch on. Every scenario validated (`valid: true`) against both
`canonical.json` and the index of the loaded network. The only validation warning was
`large_multiplier`, for 2017-01-24. The baseline is the same scenario with no events, so it is the
network's own 2011-01-01 day. Source: `data/observed/analogue-results.json`.

| Scenario | Outcome | Load (MWh) | Unserved energy (MWh) | Peak shed (MW) | Shed hours | Total cost (€) | of which generation (€) | Wind+solar curtailment (MWh) | Max / mean line loading (%) | Congested lines | Storage discharge (MWh) | HiGHS time (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (2011-01-01, no events) | feasible | 1 209 952 | 0 | 0 | 0 | 6 684 817 | 6 684 817 | 69 591 | 100.0 / 22.9 | 42 | 32 434 | 4.7 |
| `observed-dunkelflaute-2015-01-20` | feasible | 1 655 703 | 3 237 | 261 | 17 | 66 230 005 | 33 859 013 | 0 | 100.0 / 22.2 | 32 | 31 980 | 5.6 |
| `observed-high-load-low-res-2017-01-24` | feasible | 1 916 278 | 20 500 | 1 662 | 24 | 253 032 523 | 48 035 798 | 458 | 100.0 / 24.8 | 44 | 45 186 | 6.2 |
| `observed-peak-load-2017-12-13` | feasible | 1 836 261 | 5 648 | 437 | 20 | 82 186 648 | 25 709 394 | 19 199 | 100.0 / 26.1 | 51 | 43 781 | 4.5 |

The four refreshed runs terminated optimally. Their largest nodal balance residual was
**3.24 × 10⁻⁷ MW**. The summary also records independently integrated serialized load, shedding,
generation and net-storage series; tests check these against the physical energy balance and
reported metrics with an explicit bound for four-decimal MW serialization. Maximum line loading
was 100 % in all four cases. PyPSA logged zero-resistance transformer warnings in this source
network; these solves do not provide an AC feasibility certificate.

How to read the table (modeled findings, not predictions):

- On the network's own day, all load is served; 42 branches reach their limit and 69.6 GWh of
  wind and solar is curtailed. These outputs alone do not identify why each MWh was curtailed.
- All three observed analogues require load shedding. The combined high-load / low-renewable
  case has the largest unserved energy among these three cases: 20.5 GWh, shedding in every hour,
  with 81 % of total cost attributable to load shedding.
- The peak-load case has more unserved energy than the Dunkelflaute case, alongside 11 % higher
  demand energy and 19.2 GWh of wind+solar curtailment. A controlled counterfactual would be needed
  to separate the effects of transmission, dispatchable availability, demand and renewable shape;
  national nameplate capacity alone cannot establish the cause of shedding.
- Results carry the adapter's warning that the dataset has no CO2 intensities (`co2_emissions_t`
  is null).

## 5. Limitations

- **Different systems.** The network has 2011 topology, a 2011 demand profile and renewable
  capacities from the end of 2014. The observed days are 2015–2017. Installed capacities are not
  rescaled, so this is an analogue stress test, not a reconstruction of the observed day.
- **National aggregates applied uniformly.** One multiplier per hour is applied to every load and to
  every generator of a carrier. The spatial pattern stays the network's own 2011-01-01 pattern, so
  real regional differences (for example, wind calm in the north while it is windy in the south)
  are lost.
- **Clipping (StormSpec w ≤ 1).** Wind on the peak-load day was stronger than on the network's day
  for 16 h onshore and 7 h offshore. Those hours keep the network's lower availability, which
  understates renewable supply on that day. The modeled onshore CF is 0.488 against 0.694 observed.
- **The reference day sets the demand level.** Every level is relative to an observed 1 January, a
  public holiday with low load. Multipliers of 1.5–2.1 on morning hours reflect "winter working day
  vs holiday", not demand growth.
- **DC LOPF with perfect foresight.** No losses, reactive power or voltage limits, no unit
  commitment, and short-run marginal costs only. Load shedding is priced at VOLL 10 000 €/MWh, so
  unserved energy measures network and capacity limits under this model, not a blackout prediction.
- **Data provenance.** OPSD has inconsistent offshore generation/capacity values (CF > 1).
  Weather values are reanalysis grid-cell values, not station measurements; 10 m wind is not
  turbine hub-height wind or an independent validation of generation.
  values are reanalysis grid-cell values, not station measurements.
- **Licensing.** Without the user's own OPSD download (sha256-pinned), the committed multipliers
  cannot be regenerated, and the observed hourly series are deliberately not in the repository.


```bash
cd pipelines/observed
uv sync
uv run python -m gridstorm_observed.build          # downloads ~130 MB to the cache once, verifies sha256
cd ../../workers/pypsa
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 uv run python ../../pipelines/observed/scripts/run_analogues.py
cd ../../pipelines/observed
uvx ruff@0.14.0 check --fix . && uvx ruff@0.14.0 format .
uv run pytest -q                                   # 25 passed; numerical properties and provenance
```

`--network-dir` (on both commands) overrides `data/networks/scigrid-de`. Full
`gridstorm-result/1.0` documents go to `<cache>/observed-runs/`. The summary is written to
`data/observed/analogue-results.json`.

Verification run: the builder above, followed by four serial single-threaded adapter solves,
then Ruff 0.14.0 check/format and `uv run pytest -q` (**25 passed**). These tests require the real
canonical SciGRID network, not a synthetic substitute. Re-run the solve command after regenerating
scenarios so scenario hashes and recorded results remain synchronized.
