# Research papers — summaries, equations and GridStorm mapping

Status: research notes (2026-11-14). Every paper was read from the arXiv PDF (full text extracted
locally, not only the abstract). Equations are transcribed from the papers or from the cited upstream
source code / documentation; where we reformulate for GridStorm we say so explicitly.

"Implementation target" names the GridStorm component that the idea is **intended** for, as defined in
[`docs/architecture/contracts.md`](../architecture/contracts.md). It is not a claim that the feature exists
or has been validated; implementation status is tracked in `TODO.md`.

GridStorm components referenced: `stormspec` (scenario spec, validation, capabilities),
`gridstorm_pypsa` (LOPF runner, `gridstorm-result/1.0`), `gridstorm_pandapower` (AC power flow, N-1),
`gridstorm_advisor` (deterministic Crisis Response Advisor), `stormbench` (PTDF/LODF contingency
screening benchmark), `gridstorm_grid2op` (sequential episodes), plus `pipelines/network-import`.

## 1. Matrix

| Paper | Scientific contribution | Assumptions | Equations | Reusable ideas | Implementation target | Validation method | Limitations |
|---|---|---|---|---|---|---|---|
| **PyPSA** — Brown, Hörsch, Schlachtberger 2018, [arXiv:1707.09913](https://arxiv.org/abs/1707.09913) ([J. Open Res. Softw. 6(1):4, doi:10.5334/jors.188](https://doi.org/10.5334/jors.188)) | Open Python toolbox bridging steady-state power flow and multi-period linear optimisation of operation + investment (LOPF), with storage, unit commitment, sector coupling, SCLOPF via BODF. | Linearised AC flow: lossless passive branches, $\lvert V\rvert\approx 1$, small angle differences ($\sin\theta\approx\theta$), $r\ll x$, P/Q decoupling; inelastic demand; perfect foresight over the optimisation horizon. | LOPF objective (5), dispatch bounds (6), storage SOC (10), KCL (12), branch limits (13), **KVL cycle constraint (15)**, BODF (21–22) — §2. | Cycle-based KVL; load shedding as a high-cost generator; SOC recursion with efficiencies; BODF-based N-1 constraints; snapshot weightings $w_t$ for energy. | `gridstorm_pypsa` (LOPF, metrics), `stormspec` (rejecting partial-window line outages because KVL still binds), `stormbench` (BODF/LODF reference). | Test suite comparing power-flow results with PYPOWER and pandapower; MATPOWER timing comparison on standard cases (paper §IV–V); demonstrations on SciGRID-DE and GridKit-EU. | Linear model ignores reactive power, voltage limits and losses; no non-linear OPF (at paper time); results only as good as input data; perfect-foresight optimisation is not an operational forecast. |
| **PyPSA-Eur** — Hörsch, Hofmann, Schlachtberger, Brown 2018, [arXiv:1806.01613](https://arxiv.org/abs/1806.01613) ([Energy Strategy Reviews 22:207–215, doi:10.1016/j.esr.2018.08.012](https://doi.org/10.1016/j.esr.2018.08.012)) | First open, fully reproducible transmission-level model of the whole ENTSO-E area (6001 HVAC lines, 3657 substations), powerplantmatching database, demand regionalisation, wind/solar availability and potentials, automated pipeline. | Line impedances from standard line types by voltage and length; transformers placeholder 2 GW / 0.1 pu; Voronoi-cell assignment of load/generation; demand split 60 % GDP / 40 % population; same load shape at every node in a country; renewables from reanalysis. Simplification maps all voltages to 380 kV; clustering is k-means on geography weighted by load + conventional capacity ([arXiv:1705.07617](https://arxiv.org/abs/1705.07617)). | Load regionalisation, wind hub-height extrapolation (3), capacity factor (4), kernel k-means validation (9–10), clustering objective (from 1705.07617) — §3. | Pipeline provenance (every transformation is a rule); explicit list of approximations to propagate into `canonical-grid/1.0` `assumptions` and `field_provenance`; clustered network as a computationally tractable input. | `pipelines/network-import` (`pypsa-eur-be`, only if the reduced build succeeds per contract), `canonical_grid` assumptions/provenance. | Circuit lengths vs ENTSO-E statistics; renewable potentials vs literature; LOPF at the 2013 European peak hour (20.4 GW load shedding attributed to model bottlenecks; ≈1 % at 1500-bus clustering); kernel-k-means topology comparison with osmTGmod and ELMOD-DE. | Map distortions; unknown impedances, busbar/switch/transformer data; Voronoi misassignment; uniform national load shape; small RES excluded; hydro storage from country totals; no borders to RU/BY/UA/TR/MA. Authors call it "partially validated". |
| **L2RPN NeurIPS 2020 retrospective** — Marot et al. 2021, [arXiv:2103.03104](https://arxiv.org/abs/2103.03104) (PMLR, NeurIPS 2020 Competition and Demonstration Track) | Grid2Op framework + benchmark casting grid operation as an MDP over AC power flow; competition design (robustness track with adversarial line attacks, adaptability track with 10–30 % renewables); analysis of winning agents. | IEEE-118-derived synthetic grid; 5-min steps, weekly episodes (2016 steps); game over when any load is lost; overloaded lines trip after a delay; cooldowns on actions; opponent disconnects heavily loaded lines at random times. | Operational cost per step and the piecewise-linear normalised score (as implemented in Grid2Op) — §4. | Separation between agent reward and evaluation score; do-nothing baseline as the zero point; survival time as a primary KPI; hidden test scenarios to avoid overfitting. | `gridstorm_grid2op` (episode KPIs: survival steps, operational cost, comparison against do-nothing). | 24 hidden weekly test scenarios (2 per month), feedback vs test phase from the same distribution; leaderboard average. | Score normalisation acknowledged as too harsh near 0; no agent earned the loss-optimisation points; synthetic grid and chronics; "super-human" is anecdotal (one scenario). |
| **DemandCast** — Steijn, Goli, Antonini 2025, [arXiv:2510.08000](https://arxiv.org/abs/2510.08000) (NeurIPS 2025 CCAI workshop); code [open-energy-transition/demandcast](https://github.com/open-energy-transition/demandcast) | XGBoost model forecasting **normalised** hourly demand profiles for many countries/subdivisions from weather (ERA5), population, GDP and annual demand per capita; strict temporal split. | Demand shape is learnable from temperature at the most populous grid cells + socio-economic covariates; absolute level supplied externally (annual demand per capita × population). | Normalised target (1), MAPE, WAPE; temporal split rules — §5. | Separate shape from level; temporal (not random) splits; per-artifact manifests with checksums + code commit + `uv.lock` hash; never redistribute restricted inputs. | Data only, deferred: candidate source of **modeled** demand profiles for `pipelines/network-import`; manifest practice mirrors `dataset-manifest/1.0`. Code is AGPL-3.0 → not copied. | Paper: last available year per region = test (8.91 %), second-to-last = validation (9.84 %), rest = train; average test MAPE 9.2 %. Repo docs add LOGO cross-validation and WAPE. | No predictive uncertainty (authors); uneven data coverage across regions; MAPE sensitive to near-zero hours (repo docs); forecasts are model outputs, not observations. |
| **X-GridAgent** — Wen, Chen 2025, [arXiv:2512.20789](https://arxiv.org/abs/2512.20789) | LLM agent (planning / coordination / action layers) that answers power-system questions by calling pandapower tools through MCP servers; prompt refinement with an LLM judge + human feedback; schema-adaptive hybrid RAG over large result tables. | LLM (GPT-5 API, temperature 0) plans correctly given a calibrated prompt; correctness is delegated to deterministic tools (pandapower); retrieval over structured tables works better after schema selection + sorting by the key column. | Plan (1), tool step (2), reflection (3), judge (5), prompt edit (6), cosine (7), BM25 (8), schema selection (9), hybrid score (11) — §6. | **Grounding rule**: every number in an answer must come from an engine output, never from the language layer; select table+column by schema, sort by the extreme-value column, return top-k with ids. | `gridstorm_advisor` — **concepts only**: deterministic, tool-grounded advice built from engine outputs; no LLM (GridStorm forbids LLM APIs). | 11 representative queries (IEEE 39/118/300, Texas 2k), each run 30 times, 100 % success against manually computed answers. | Small author-designed test set; success judged against the authors' own references; dependence on a proprietary LLM; steady-state only; the paper links a demo video, no source repository is cited. |

Supporting method references (used by `stormbench`, `gridstorm_pandapower`, metrics):

| Reference | Used for | Link |
|---|---|---|
| A. J. Wood, B. F. Wollenberg, G. B. Sheblé, *Power Generation, Operation, and Control*, 3rd ed., Wiley 2013 (ISBN 978-0-471-79055-6) | DC power flow, PTDF ("generation shift") and LODF derivation, contingency screening | [Wiley](https://www.wiley.com/en-us/Power+Generation,+Operation,+and+Control,+3rd+Edition-p-9780471790556) |
| T. Güler, G. Gross, M. Liu, "Generalized Line Outage Distribution Factors", IEEE Trans. Power Syst. 22(2):879–881, 2007, doi:10.1109/TPWRS.2006.888950 | LODF from PTDF, multiple outages | [IEEE Xplore](https://ieeexplore.ieee.org/document/4162596), [DOI](https://doi.org/10.1109/TPWRS.2006.888950) |
| J. Guo, Y. Fu, Z. Li, M. Shahidehpour, "Direct Calculation of Line Outage Distribution Factors", IEEE Trans. Power Syst. 24(3):1633–1634, 2009 | LODF directly from the network matrices | [DOI](https://doi.org/10.1109/TPWRS.2009.2023273) |
| H. Ronellenfitsch, D. Manik, J. Hörsch, T. Brown, D. Witthaut, "Dual Theory of Transmission Line Outages", IEEE Trans. Power Syst. 32(5), 2017 | PyPSA SCLOPF implementation basis | [DOI](https://doi.org/10.1109/TPWRS.2017.2658022) |
| J. Hörsch, H. Ronellenfitsch, D. Witthaut, T. Brown, "Linear Optimal Power Flow Using Cycle Flows", Electric Power Systems Research 158:126–135, 2018, doi:10.1016/j.epsr.2017.12.034 | KVL cycle formulation, speed vs angle formulation | [arXiv:1704.01881](https://arxiv.org/abs/1704.01881), [DOI](https://doi.org/10.1016/j.epsr.2017.12.034) |
| PyPSA documentation, "Contingencies" (BPTDF/BODF definitions) | BODF formulas exactly as implemented in PyPSA | [docs.pypsa.org](https://docs.pypsa.org/latest/user-guide/optimization/contingencies/) |
| R. Billinton, R. N. Allan, *Reliability Evaluation of Power Systems*, 2nd ed., Springer 1996, doi:10.1007/978-1-4899-1860-4 | Definition of EENS / expected energy not supplied and related adequacy indices | [Springer](https://link.springer.com/book/10.1007/978-1-4899-1860-4) |

## 2. PyPSA (arXiv:1707.09913)

**Contribution.** A free toolbox that stores network components in pandas tables and supports
(i) full non-linear AC/DC power flow by Newton–Raphson, (ii) linearised power flow, and (iii) multi-period
linear optimal power flow (LOPF) with investment, storage, unit commitment and sector coupling.

**Linearised power flow (paper eq. 4).** With incidence matrix $K$, branch susceptances
$b_\ell = 1/(x_\ell \tau_\ell)$ in diagonal $B$:

$$P_n = \sum_m (K B K^\top)_{nm}\,\theta_m - \sum_\ell K_{n\ell}\, b_\ell\, \theta^{\text{shift}}_\ell$$

**LOPF objective (paper eq. 5).** Branch capacities $F_\ell$, generator capacities $G_{n,r}$, storage
power/energy capacities $H_{n,s}$/$E_{n,s}$, dispatch $g_{n,r,t}$, storage dispatch $h_{n,s,t}$,
snapshot weights $w_t$:

$$
\min \; \sum_\ell c_\ell F_\ell + \sum_{n,r} c_{n,r} G_{n,r}
+ \sum_{n,r,t} \big(w_t\, o_{n,r}\, g_{n,r,t} + suc_{n,r,t} + sdc_{n,r,t}\big)
+ \sum_{n,s} c_{n,s} H_{n,s} + \sum_{n,s} \hat c_{n,s} E_{n,s}
+ \sum_{n,s,t} w_t\, o_{n,s}\, [h_{n,s,t}]^+
$$

**Dispatch bounds (6):** $\tilde g_{n,r,t} G_{n,r} \le g_{n,r,t} \le \bar g_{n,r,t} G_{n,r}$ — for wind/solar
$\bar g_{n,r,t}$ is the weather-dependent availability; curtailment is $\bar g G - g$.

**Storage state of charge (10):**

$$
e_{n,s,t} = \eta_{n,s,0}^{\,w_t}\, e_{n,s,t-1}
+ \eta_{n,s,+}\, w_t\, [h_{n,s,t}]^- - \eta_{n,s,-}^{-1}\, w_t\, [h_{n,s,t}]^+
+ w_t\, h^{\text{inflow}}_{n,s,t} - w_t\, h^{\text{spillage}}_{n,s,t},
\qquad \tilde e_{n,s,t} E_{n,s} \le e_{n,s,t} \le \bar e_{n,s,t} E_{n,s}
$$

(Paper eq. 10 as printed attaches $\eta_{+}$ to $[h]^+$ and $\eta_{-}^{-1}$ to $[h]^-$, while the same paper
defines $h>0$ as discharging into the grid. Under that convention discharging must *reduce* the level, so
we write the sign-consistent form above, which matches PyPSA's storage documentation
(`efficiency_store` on charging, `1/efficiency_dispatch` on dispatch). The initial level is user-set or
cyclic, $e_{n,s,0}=e_{n,s,T}$.)

**KCL / nodal balance (12)** with dual $w_t\lambda_{n,t}$ (marginal price):
$\sum_r g_{n,r,t} + \sum_s h_{n,s,t} + \sum_\ell \alpha_{\ell,n,t} f_{\ell,t} = d_{n,t}$, where
$\alpha = K$ for lines/transformers and $\alpha=\eta_{\ell,t}$ at the receiving end of a link.

**Branch limits (13–14):** $|f_{\ell,t}| \le F_\ell$ for passive branches;
$\tilde f_{\ell,t}F_\ell \le f_{\ell,t} \le \bar f_{\ell,t}F_\ell$ for controllable links.

**KVL cycle constraint (15).** With cycle matrix $C_{\ell c}$ (one column per independent cycle) and series
reactance $x_\ell$:

$$\sum_\ell C_{\ell c}\, x_\ell\, f_{\ell,t} = 0 \qquad \forall c, t$$

The paper reports the cycle formulation solving up to 20× faster than the angle formulation
([arXiv:1704.01881](https://arxiv.org/abs/1704.01881)); angle and PTDF formulations give identical results.

**SCLOPF (21–22).** $f^{(k)}_\ell = f_\ell + \mathrm{BODF}_{\ell k} f_k$ and
$|f_{\ell,t} + \mathrm{BODF}_{\ell k} f_{k,t}| \le |F_\ell|$ for each considered outage $k$.

**GridStorm mapping.**
- `gridstorm_pypsa` (contract §4): operational LOPF on fixed capacities; load shedding is a generator per
  load bus with marginal cost = VOLL, so the objective reduces to
  $\min \sum_t w_t \big(\sum_{n,r} o_{n,r} g_{n,r,t} + \mathrm{VOLL}\sum_n p^{\text{shed}}_{n,t}\big)$
  and $E_{\text{unserved}} = \sum_t p^{\text{shed}}_t\, w_t$ (contract definition).
- `stormspec` (contract §3): a line outage limited to a partial time window cannot be emulated with
  `s_max_pu = 0`, because the branch would remain in the cycle basis and (15) would still constrain the
  flows of the rest of the network; such scenarios are rejected unless the window covers the horizon.
- `stormbench`: BODF/LODF definitions (§7) are shared with PyPSA's implementation, which gives an independent
  reference implementation to compare against.

**Limitations to state in GridStorm outputs.** No reactive power, voltage magnitudes or losses in LOPF
(already the contract's default assumption string); perfect foresight over the horizon.

## 3. PyPSA-Eur (arXiv:1806.01613)

**Contribution.** An open, automated pipeline that assembles a load-flow-ready European transmission
model from open sources (GridKit extract of the ENTSO-E map, powerplantmatching, ENTSO-E load,
reanalysis-based renewable availability, CORINE/Natura2000 land-use limits).

**Key approximations (paper §2 and §4).**
- AC line parameters from three standard line types (220/300/380 kV) × length × circuits.
- No transformer data: one 2 GW, 0.1 pu transformer between co-located buses of different voltage (2018
  paper version; later PyPSA-Eur releases changed the base network — check the version used).
- Voronoi cells assign load and generation to substations.
- Load regionalisation: national load split 60 % by GDP and 40 % by population (NUTS3 → Voronoi overlap),
  identical normalised shape at all nodes of a country:
  $d_{n,t} = d_{c,t}\,\big(0.6\,\tfrac{\mathrm{GDP}_n}{\mathrm{GDP}_c} + 0.4\,\tfrac{\mathrm{POP}_n}{\mathrm{POP}_c}\big)$
  (our compact restatement of the prose in §2.6).
- Wind (3–4): $u_h = u_{100}\,\ln(h/z_0)/\ln(100\,\mathrm{m}/z_0)$, capacity factor
  $c_{x,w} = \langle P_w(u_h(t))\rangle_t / P^{\max}_w$; potential $G^{\max}_{x,w}=0.3\cdot 10\,\mathrm{MW/km^2}\cdot A_{x,w}$.

**Simplification & clustering** (PyPSA-Eur docs, [simplification](https://pypsa-eur.readthedocs.io/en/v0.13.0-docs-fix/simplification.html);
method from Hörsch & Brown, [arXiv:1705.07617](https://arxiv.org/abs/1705.07617)):
1. Map all voltage levels to a 380 kV equivalent; collapse multi-hop HVDC to one link; iteratively remove
   stubs (dead ends) and move their components to the neighbour.
2. Weight buses by load + conventional capacity and solve weighted k-means on coordinates:
   $$\min_{\{x_c\}} \sum_{c=1}^{k} \sum_{n\in N_c} w_n \lVert x_c - x_n\rVert^2$$
   with clusters allocated per country/synchronous zone proportional to mean load (best of 10 starts).
3. Aggregate generators/storage/loads per technology at each cluster bus; average renewable availability
   with weights; replace inter-cluster lines by one equivalent line of length $1.25\times$ the crow-flies
   distance, capacity = sum of capacities, impedance = parallel equivalent.

The paper's network-comparison validation uses kernel k-means (9–10) with
$K_{a,b}=e^{-\lVert a-b\rVert_2^2/N} + \nu B^\dagger_{a,b}$ (geographic RBF + reactance distance).

**Validation (paper §3).** Circuit lengths vs ENTSO-E statistics (e.g. EU 380 kV: 146.82 vs 154.31 thousand
km); German offshore/solar potentials vs literature; LOPF of the 17-01-2013 17:00 European peak (0.51 TW)
with lines capped at 70 % to approximate N-1 gives 20.4 GW load shedding attributed to modelling bottlenecks;
~1 % at 1500 clusters; nearly none at 362 clusters.

**GridStorm mapping.** `pipelines/network-import` for `pypsa-eur-be` (contract: only if the reduced build
succeeds). Every approximation above that survives in the built network must appear in
`canonical-grid/1.0` `assumptions`, and parameters such as line impedances must be labelled
`modeled` in `field_provenance`, not `observed`. The paper's own peak-hour result is a warning for
GridStorm: load shedding in a clustered/synthetic network can be a modelling artefact, so shed energy
must never be presented as a predicted blackout.

**Limitations.** As listed in the matrix; the authors explicitly invite further validation.

## 4. L2RPN NeurIPS 2020 retrospective (arXiv:2103.03104)

**Contribution.** Grid2Op wraps an AC power-flow backend in an MDP: observation = full grid state,
actions = discrete bus-splitting topology changes (>70 000) + continuous redispatch (40-dim),
transitions = AC power flow + protection logic (overloaded lines trip after a delay, cooldowns, an
adversarial opponent in the robustness track).

**Score.** The paper states that per-scenario score is based on cumulative operational cost and normalised to
$[-100, 0, 80, 100]$ = [initial blackout, do-nothing, scenario completed, +20 % cost optimisation], averaged
over 24 hidden scenarios. The exact formula is in Grid2Op (MPL-2.0;
[`grid2op/Reward/l2RPNSandBoxScore.py`](https://github.com/Grid2op/grid2op/blob/07012c4f19cac81662df1df54122568c64d8fe09/grid2op/Reward/l2RPNSandBoxScore.py),
[`grid2op/utils/l2rpn_2020_scores.py`](https://github.com/Grid2op/grid2op/blob/07012c4f19cac81662df1df54122568c64d8fe09/grid2op/utils/l2rpn_2020_scores.py),
commit `07012c4f19cac81662df1df54122568c64d8fe09`). Per step $t$ with duration $\Delta t$ and price
$p_t = \max$ marginal cost of the generators currently producing:

$$
c_t = p_t \,\frac{\Delta t}{3600\,\mathrm{s}} \Big(\alpha_{\text{loss}}\big(\textstyle\sum_g P_g - \sum_l P_l\big)
+ \alpha_{\text{redisp}} \sum_g |\Delta P^{\text{redisp}}_g| + \alpha_{\text{sto}} \sum_s |P_s|
+ \alpha_{\text{curt}} \sum_g P^{\text{curt}}_g\Big)
$$

Episode cost $C = \sum_{t<T_{\text{played}}} c_t + \bar p \sum_{t \ge T_{\text{played}}} L_t$ (remaining load
after game over priced at the maximum marginal cost $\bar p$). The score is a piecewise-linear interpolation

$$
S = \mathrm{interp}\big(C;\ [C_{\text{best}}, C_{\text{no-overflow}}, C_{\text{do-nothing}}, C_{\text{worst}}],\ [100, 80, 0, -100]\big)
$$

with $C_{\text{worst}} = \bar p \sum_t L_t$ and, as implemented at this commit,
$C_{\text{best}} = 0.8 \sum_t \text{losses}_t$ (`min_losses_ratio`; note the code does not multiply this term
by a price — we record the implementation as-is). If the do-nothing agent survives the whole episode, the
80-point anchor is dropped.

**GridStorm mapping.** `gridstorm_grid2op` episode artifacts (`kind: episode`): report survival steps,
cumulative operational cost and the do-nothing baseline separately and in physical units. A normalised
L2RPN score may be added only if computed by Grid2Op's own scorer and labelled as such; GridStorm must not
re-implement or re-tune it.

**Limitations.** Synthetic grid/chronics; score saturation near the do-nothing anchor (authors); no agent
optimised losses; results are not transferable to real system operation.

## 5. DemandCast (arXiv:2510.08000; repo `open-energy-transition/demandcast`)

**Contribution.** A reproducible pipeline (retrieval → cleaning → assembly → XGBoost) that forecasts hourly
demand **profiles** for many regions; absolute demand comes from annual demand per capita × population.

**Normalised target (paper eq. 1).** For year $Y$, with $D_Y$ the observed annual energy and coverage
correction:

$$D_n(t) = \frac{D(t)}{D_Y}\cdot\frac{\sum_Y H_{\text{avail}}}{\sum_Y H}$$

The repository documentation (`webpage/docs/ML.md`, commit `c7d9f1dd32394b0a84001cc1dcc3410a73086e1d`) now multiplies
this fraction by the hours of the local year, i.e. load relative to the annual mean (1.0 = average hour).

**Metrics.** $\mathrm{MAPE} = \frac{1}{N}\sum_t \frac{|y_t-\hat y_t|}{|y_t|}$ (paper);
the repo adds $\mathrm{WAPE} = \frac{\sum_t |y_t-\hat y_t|}{\sum_t |y_t|}$, because MAPE is dominated by
near-zero hours.

**Splits.** Paper: per region, last available year = test (8.91 % of rows), second-to-last = validation
(9.84 %), remainder = training (81.25 %); 6 041 222 / 731 538 / 662 369 hourly observations; average test MAPE
9.2 % (per-region test MAPE 2.3 %–19.4 %). Repo: missing years are skipped; Leave-One-Group-Out
cross-validation with `holdout: entity` or `holdout: country`.

**Licensing (verified in the repo at the commit above).** Code: AGPL-3.0 (`LICENSE`). Published model and
forecasts: CC BY 4.0 on Zenodo (record v2.0.0, [doi:10.5281/zenodo.23924756](https://doi.org/10.5281/zenodo.23924756),
published 2026-11-03; README link [doi:10.5281/zenodo.18374351](https://doi.org/10.5281/zenodo.18374351)). The
retrieved hourly demand is **not redistributed** "since the licences of many data sources do not allow it"
(repo `README.md`). Input licences listed in `demandcast/publishing/release/README.md` include IMF WEO data
whose commercial reuse needs IMF permission. That README still cites the "Licence to use Copernicus
Products" for ERA5; the CDS replaced it with CC BY 4.0 on 2025-07-02 ([ECMWF announcement](https://forum.ecmwf.int/t/cc-by-licence-to-replace-licence-to-use-copernicus-products-on-02-july-2025/13464)).

**GridStorm mapping.** No code reuse (AGPL). Possible later use of the CC BY 4.0 forecasts as **modeled**
demand profiles (provenance class `modeled`, never `observed`) in `pipelines/network-import`, with the
Zenodo DOI in `dataset-manifest/1.0.source`. Process ideas adopted conceptually: temporal splits for any
learned component, per-artifact manifests with checksums and code commit.

## 6. X-GridAgent (arXiv:2512.20789)

**Contribution.** Three-layer agent: planning $\mathcal P$, coordination, action $\mathcal A$, with eight MCP
tool servers on top of pandapower (retrieval, power flow, OPF, contingency, short circuit, …).

**Equations (paper numbering).**
- Plan: $\Gamma := \{T_1 \to \dots \to T_N\} = \mathcal P(q;\pi^*_P)$ (1)
- Tool step: $p^i_k = \mathcal A(T_i, M_i, p^i_{k-1}; \pi^*_A)$ (2); reflection $r_k = \mathrm{Reflect}(p^i_k, T_i)$ (3)
- Prompt refinement: $y=\text{X-GridAgent}(q;\pi)$ (4), judge $d_k=\mathcal J(q_k,y_k,\hat y_k)$ (5),
  edit $\pi_{k+1}=\mathcal E(\pi_k,d_k)$ (6)
- Retrieval: $\mathrm{sim}(q,c_i)=\frac{v_q\cdot v_{c_i}}{\lVert v_q\rVert\lVert v_{c_i}\rVert}$ (7);
  $\mathrm{BM25}(q,c_i)=\sum_j \mathrm{IDF}(t_j)\frac{f(t_j,c_i)(k_1+1)}{f(t_j,c_i)+k_1(1-b+b\,N/\mathrm{avgdl})}$ (8)
- Schema selection $X_q=\mathcal S(D_{\text{ori}},q)$ (9), then rows sorted by the keyword column;
  hybrid score $s_{\text{hyb}}=\lambda\,\mathrm{BM25}+(1-\lambda)\,\mathrm{sim}$ (11)

**Grounding.** Correctness comes from the engine (pandapower), not from the LLM; retrieval failures on large
result tables (e.g. 3 992-row line table) are fixed by selecting the relevant table/columns and sorting by
the extreme-value column before retrieval.

**GridStorm mapping — concepts only.** `gridstorm_advisor` is defined as deterministic (architecture
overview) and GridStorm forbids LLM APIs. Ideas kept: (a) every number shown is copied from an engine
artifact with its asset id and provenance; (b) "schema-adaptive selection" becomes a typed query
(table, column, sort direction, k) over result tables — no embeddings, BM25 or LLM needed; (c) a
plan→execute→check loop maps to a fixed pipeline whose check step verifies that required outputs
(e.g. which contingency causes which violation) are present.

**Limitations.** See matrix. The 100 % success rate is over 11 author-chosen queries × 30 repetitions and is
not evidence of general reliability.

## 7. Distribution factors and EENS (method references)

**PTDF (DC power flow; Wood & Wollenberg).** With reduced susceptance matrix $B_{\text{bus}}$ (slack removed)
and branch matrix $B_f = \mathrm{diag}(b)K^\top$:

$$\mathrm{PTDF} = B_f\, B_{\text{bus}}^{-1}, \qquad f = \mathrm{PTDF}\cdot P_{\text{inj}}$$

**LODF / BODF (Güler et al. 2007; PyPSA docs).** $\mathrm{BPTDF} = \mathrm{PTDF}\cdot K$ (flow change on $b$
for a unit transfer across branch $c$), then

$$\mathrm{LODF}_{bc} = \frac{\mathrm{BPTDF}_{bc}}{1-\mathrm{BPTDF}_{cc}}\ (b\ne c),\qquad \mathrm{LODF}_{bb}=-1,\qquad f^{(c)}_b = f_b + \mathrm{LODF}_{bc} f_c$$

$\mathrm{BPTDF}_{cc}=1$ means the outage islands the network; the factor is undefined and the case must be
handled separately (flagged, not approximated).

**EENS (Billinton & Allan 1996).** Expected energy not supplied over outage states $s$ with probability
$p_s$ (or frequency/duration) and curtailed energy $E_s$: $\mathrm{EENS}=\sum_s p_s E_s$ (MWh per period).
GridStorm's contract metric `unserved_energy_mwh` $=\sum_t p^{\text{shed}}_t\,w_t$ is the unserved energy of
**one deterministic scenario**; it is not EENS and must not be labelled as such unless a probability-weighted
ensemble of scenarios is actually computed.

## 8. Local copies used

PDFs/text were downloaded to `D:/New folder (4)/upstream/_papers/` (outside the repo) on 2026-11-14 from
`https://arxiv.org/pdf/<id>`; Grid2Op and DemandCast sources were read from local clones at the commits named
above. Nothing from these sources was copied into the repository.
