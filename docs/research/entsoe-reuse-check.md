# ENTSO-E Transparency re-use check for the OPSD columns behind `data/observed/opsd-de` (P0-10)

Checked 2026-11-15, by hand, against the documents ENTSO-E currently publishes. Scope: the seven OPSD
`time_series` 2020-10-06 columns in `data/observed/opsd-de/manifest.json` → `source.columns_used`. Claims
marked **[INFERENCE]** are reasoning, not text from a source. This is not legal advice.

## 1. Sources read today

| # | Document | Where | What I checked |
|---|---|---|---|
| S1 | ENTSO-E Transparency Platform "Legal Terms and Conditions" page, marked "Updated November 14, 2025" | <https://transparencyplatform.zendesk.com/hc/en-us/articles/40921911218961-Legal-Terms-and-Conditions> | The current Terms of Use are the **29/03/2023** version, "applicable as of 01 November 2023". The current list of data for free re-use is **18/10/2023**. The page says the list is published "pursuant to clause 2.5 of the Terms of Use". |
| S2 | General Terms and Conditions for the use of the ENTSO-E Transparency Platform (approved 29 March 2023), `230329_ENTSOE_Transparency_Terms_Conditions_MC_APPROVED.pdf`, sha256 `665d08621f711e3c0971581b15b2572e69054d4a017f693e32c20924d476352b` | <https://transparencyplatform.zendesk.com/hc/en-us/article_attachments/40921869376401> | Clauses 2.5, 3.1, 5.1 and 5.3, all 15 pages. |
| S3 | "List of data available for free re-use", last modified 18 October 2023, `231018_List_of_Data_available_for_reuse.pdf`, sha256 `b21717e8a5a41b9b8544db730d11c2a717abc9b07f89704437a89332b708ff9a` (the same hash as in the manifest) | <https://transparencyplatform.zendesk.com/hc/en-us/article_attachments/40921869379729> | The preamble, the exclusions and all items #1–#35 with their Transparency Regulation articles, on all 5 pages. Page 1 was checked against a rendered image, not only extracted text. |
| S4 | Commission Regulation (EU) No 543/2013 (OJ L 163, 15.6.2013), Articles 6, 14 and 16 | Publications Office Cellar <http://publications.europa.eu/resource/celex/32013R0543>. EUR-Lex <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32013R0543> returned a bot challenge. | The wording of each data item |
| S5 | OPSD `time_series` 2020-10-06 `datapackage.json` and README | <https://data.open-power-system-data.org/time_series/2020-10-06/datapackage.json> (cached copy hash = manifest `datapackage_sha256`) | `licenses: null`. The only package-level source is `ENTSO-E Transparency`. The README "License and attribution" section contains only an attribution string. |
| S6 | OPSD home page | <https://open-power-system-data.org/> | "several data owners do not allow us to do so. Beware that some data published here might be subject to copyright." |
| S7 | OPSD `renewable_power_plants` 2020-08-25 `datapackage.json` (the source of OPSD's DE capacity calculations) | <https://data.open-power-system-data.org/renewable_power_plants/latest/datapackage.json> (redirects to `/2020-08-25/`) | `licenses: null`. The sources include Bundesnetzagentur register spreadsheets and netztransparenz.de. |

## 2. What the ENTSO-E terms say

- **Only listed items are open data (CC BY 4.0).** ToU clause 2.5 (S2) says ENTSO-E "currently publishes a
  *subset* of the Transparency Platform data available under an open source license (CC-BY 4.0)". The list
  preamble (S3) says the listed data may be freely copied, redistributed and adapted "by giving appropriate
  credit (attribution) to its source and indicating if they have made any changes, with no need to seek for
  the prior agreement of the respective Primary Owner of Data".
- **Unlisted data stay subject to the Primary Owner's rights.** ToU 3.1 (S2) says the Data User shall:
  - "mention the ENTSO-E Transparency Platform as the source of publication of the data";
  - not imply sponsorship or endorsement by ENTSO-E;
  - "not cause prejudice to the copyright or related right on a Transparency Platform Data, which may be owned
    by the concerned Primary Owner of Data. In case of a risk to cause prejudice to said right, the Data User
    shall seek the prior agreement of the holder";
  - "check this list before each re-use".

  ToU 5.1 says "Transparency Platform Data may be subject to copyright owned by the Primary Owner of Data". The
  rights of use are "not sub-licensable or transferrable".
- **The ToU set no derived-data or anonymisation exception.** Neither S2 nor S3 mentions derived values,
  aggregates or ratios. The only test is "prejudice to the copyright or related right".
- **List contents (S3).** For the Transparency Regulation, the list covers:
  - load *forecasts* only (#1–#4 = Art. 6.1.b–e);
  - transmission and congestion items (Arts. 9.1, 10.1, 11.1, 11.4, 12.1, 13.1);
  - balancing items (Art. 17).

  It contains **no item for Art. 6.1.a (actual total load), Art. 14.1 (installed capacity / generation
  forecasts) or Art. 16.1 (actual generation)**. The country exclusions (MD, TR, some UA/interconnector items)
  do not concern Germany, but they are moot because the items are not listed at all.

## 3. Per-column result

The OPSD column metadata (manifest `column_sources`) links each OPSD column to a TP data view. The Art. 543/2013
wording is from S4. "Raw" means redistributing the hourly OPSD/TP values themselves. "Derived" means
committing GridStorm's hourly multipliers and statistics in their current form.

| OPSD column | Primary origin (manifest `column_sources`) | Reg. 543/2013 item | On free re-use list (S3)? | Re-use status | Attribution required | Raw redistribution | Derived multipliers as committed |
|---|---|---|---|---|---|---|---|
| `DE_load_actual_entsoe_transparency` | "own calculation based on ENTSO-E Transparency", TP view `totalLoadR2` | Art. 6.1.a "the total load per market time unit" | **No.** #1–#4 are only 6.1.b–e forecasts. | Not CC BY. Governed by ToU 3.1 and 5.1: the Primary Owner's rights apply, and prior agreement is needed if there is a risk of prejudice. | Name the "ENTSO-E Transparency Platform" as the source of publication (ToU 3.1), plus the OPSD citation | **NOT PERMITTED** (no grant; permission not obtained) | **UNCLEAR** (see §4: the committed values reconstruct the observed hourly load) |
| `DE_wind_onshore_generation_actual` | same, TP view `actualGenerationPerProductionType` | Art. 16.1.b "aggregated generation output per market time unit and per production type" and/or 16.1.c "actual or estimated wind and solar power generation". [INFERENCE: mapped from the TP view name; the TP site is a JS app and its labels could not be read.] | **No.** No Art. 16 item is listed. | as above | as above | **NOT PERMITTED** | **UNCLEAR** |
| `DE_wind_offshore_generation_actual` | as above | Art. 16.1.b / 16.1.c | **No** | as above | as above | **NOT PERMITTED** | **UNCLEAR** |
| `DE_solar_generation_actual` | as above | Art. 16.1.b / 16.1.c | **No** | as above | as above | **NOT PERMITTED** | **UNCLEAR** |
| `DE_wind_onshore_capacity` | "own calculation based on BNetzA and netztransparenz.de". Not ENTSO-E. | None: not taken from the TP. (The TP item that would correspond, Art. 14.1.a, is not on the list either.) | n/a | ENTSO-E terms do not apply. The OPSD packages (S5, S7) declare no data licence, and BNetzA/netztransparenz.de terms were not checked. | OPSD citation; name BNetzA and netztransparenz.de as the primary sources | **UNCLEAR** | **UNCLEAR**, low exposure: no capacity value is committed, only the observed CF (generation ÷ capacity) is recoverable (§4) |
| `DE_wind_offshore_capacity` | as above | as above | n/a | as above | as above | **UNCLEAR** | **UNCLEAR**, low exposure |
| `DE_solar_capacity` | as above | as above | n/a | as above | as above | **UNCLEAR** | **UNCLEAR**, low exposure |

Why "UNCLEAR" and not "NOT PERMITTED" for the derived values: the ToU do not forbid re-use of unlisted data. They
only require the Primary Owner's prior agreement when there is "a risk to cause prejudice" to the copyright or
related right. Whether a few days of hourly values, published as ratios, carry that risk is a legal judgement.
**[INFERENCE]** Individual metered MW values are facts, and three days of a multi-year series is probably not a
substantial extraction under EU database right. Still, neither ENTSO-E nor the German TSOs (the Primary Owners)
grant this anywhere in the documents read.

## 4. Repo practice: derived multipliers plus checksums only

What the repo actually commits (`data/observed/opsd-de/derived-multipliers.json`, sha256
`cd153dd6…51c1`, matches the manifest), as observed today:

- Per stress day, 24 demand multipliers and 24 multipliers per renewable carrier. The formulas are in
  `pipelines/observed/src/gridstorm_observed/mapping.py` L15–27.
- The network's own hourly `load_mw` and `capacity_factor` (from SciGRID-DE, not OPSD).
- Point values taken straight from the observed series:
  - `detection.detail.peak_load_mw` (the observed peak in MW; value redacted here, see §6), and the matching `peak_hour_utc`;
  - `daily_mean_load_mw`, `max_daily_mean_load_mw`;
  - `reference_day_mean_load_mw`;
  - `observed_daily_mean_cf`;
  - the dunkelflaute daily and rolling CF means.

**The observed hourly series can be recovered from these committed values.**
- **Load.** `L_obs(d,h) = m_h · L_net(h) / mean(L_net) · reference_day_mean_load_mw`. I ran this today against
  the cached OPSD CSV (sha256 `6a7f2bc5…04c8`, matches the manifest). It reproduces
  `DE_load_actual_entsoe_transparency` for all 24 hours of all three stress days (2017-12-13, 2015-01-20,
  2017-01-24) to within **2.4 MW** (relative error ≤ 4·10⁻⁵). No demand hour was clipped.
- **Renewables.** `CF_obs = w_h · CF_net(h)` for hours that are not clipped. It reproduces observed generation ÷
  capacity to within 5·10⁻⁵ for 7–24 hours per carrier per day. Generation and capacity cannot be recovered
  separately because no capacity value is committed.

Verdict on consistency:
- **Consistent:** no raw OPSD file and no `target_load_mw` or `observed_cf` field is committed. Inputs are
  pinned by URL and sha256. The manifest says `redistribution: "restricted"`. The ENTSO-E TP is attributed as
  the source of the load and generation data, which meets ToU 3.1 for attribution.
- **Not accurate as described:**
  - `committed_content: "… no observed hourly series"` and the `test_no_observed_opsd_series_committed`
    check (field-name test) cover storage, not information. In effect the repo publishes 72 observed hourly
    DE actual-load values (Art. 6.1.a, unlisted). It also publishes observed hourly CFs that derive from
    unlisted Art. 16.1 data.
  - "Derived multipliers only" therefore does **not** by itself keep the repo inside the CC BY list. The
    practice is defensible only on the **[INFERENCE]** that a few days of values does not prejudice the TSOs'
    rights. That is the UNCLEAR point above.
- **Ways to remove the uncertainty** (decision for the owner):
  1. Get written confirmation from ENTSO-E (via the TP Zendesk / transparency@entsoe.eu) or the German TSOs.
  2. Or make the committed values non-invertible. Examples: drop `reference_day_mean_load_mw` and the other
     observed absolute statistics, or round the multipliers coarsely.
  3. Or switch these scenarios to listed items. The day-ahead load forecast, Art. 6.1.b (#1), is CC BY 4.0
     with attribution and change notes. Listed items need the CC BY attribution and indicate-changes
     wording (S3 preamble) in the manifest.

## 5. Manifest licence block

The evidence makes the old wording more precise: the load and generation items are *not on* the free re-use list
(it was not "not established"), and the "no observed hourly series" claim is wrong in effect. The `assessment`
and `committed_content` strings in `data/observed/opsd-de/manifest.json` were updated to match.
`redistribution: "restricted"` is unchanged. The generator writes the same strings
(`pipelines/observed/src/gridstorm_observed/build.py` L420–434 and module docstring L13–17), so it must be
changed to match, or the next build will revert the manifest.

## 6. Outcome: rebuild of 2026-11-15 (option 3 for load; non-invertible values for renewables)

The owner chose to remove the uncertainty rather than ask for permission. Details:
`docs/research/observed-analogue-scenarios.md` §1.1, §3 and §4.

- **Load → listed item.** Demand multipliers now come from `DE_load_forecast_entsoe_transparency`.
  The OPSD datapackage describes it as "Day-ahead load forecast in Germany in MW as published on
  ENTSO-E Transparency Platform", TP view `totalLoadR2`. It is Reg. 543/2013 Art. 6.1.b = S3 item #1
  ("Day-ahead forecast of the total load per market time unit", confirmed in the cached
  `231018_List_of_Data_available_for_reuse.pdf`).
  - It is used under CC BY 4.0. The manifest (`license.load_forecast_attribution`) and every
    scenario carry the attribution and the list of changes.
  - The actual load (Art. 6.1.a) now only selects the stress dates.
- **Renewables → MODELED daily shortfall.**
  - A per-hour ratio rounded to 0.05 and clipped to ≤ 1 was tested first. It still returned the
    observed hourly CF to within 0.004–0.025 CF in unclipped hours (offshore 2017-12-13: within
    0.022 at a CF of about 0.9), so it was rejected.
  - Each carrier now gets one daily multiplier: the ratio of the daily-mean observed CF to the
    daily-mean network CF, rounded to 0.05 and clipped to ≤ 1, applied to the whole day.
- **Absolutes removed.** The committed files no longer contain:
  - `reference_day_mean_load_mw`, peak/daily-mean loads, peak hour, combined-day threshold and
    observed CF means;
  - per-hour renewable multipliers and clipped-hour lists;
  - the observed-peak value in §4 above (redacted).
- **Reconstruction test.** `pipelines/observed/tests/test_reuse.py` runs against the cached OPSD
  CSV, with an oracle least-squares scale.
  - Actual hourly load now misses by at least 1 054 / 2 059 / 2 608 MW (2017-01-24 / 2015-01-20 /
    2017-12-13), against a required > 500 MW. Before: 2.2–2.5 MW.
  - Hourly CF misses by at least 0.15 of the day's peak CF, against a required > 0.10. Before:
    0.000–0.076 in several carrier-days.
  - The test also checks that no non-open column name appears in the scenarios,
    `derived-multipliers.json` or `analogue-results.json`.
- **Manifest.**
  - `redistribution` is now `"derived-only"`.
  - `source.column_reuse` gives, per column: origin, free re-use status, raw redistribution
    (forecast: permitted with attribution; actual load and generation: not permitted;
    capacities: unclear), use and committed derivative.
  - The generator (`build.py`, `sources.py`) writes the same strings, so rebuilding keeps them.
- **Residual [INFERENCE].** The daily renewable multiplier still derives from unlisted Art. 16.1
  data. It gives the daily-mean observed CF only to ±0.025 · mean network CF (one rounded number
  per carrier and day, not a series). I judge this not to prejudice the Primary Owners' rights,
  but no permission was obtained. A licence-pure alternative would replace it with a fully
  assumed shortfall.
