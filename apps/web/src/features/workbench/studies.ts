import type { ArtifactKind } from '../../api/types'

/**
 * Published research studies shown by the Research Workbench.
 *
 * Every quoted statement (assumptions, limitations, solver, dataset, execution notes, references)
 * is copied verbatim from the repository file named in `doc`; `studies.test.ts` checks each one
 * against the file (markdown emphasis, code ticks and link targets ignored, whitespace collapsed)
 * and checks every reproduction command, doc anchor and artifact selector. Numbers shown by the
 * workbench never come from here: they are read from the artifacts at run time.
 */

/** A sentence quoted verbatim from a repository file (path relative to the repo root). */
export interface DocQuote {
  text: string
  doc: string
  /** UI label shown before a bare value (e.g. a hash); not part of the quote. */
  label?: string
}

export interface StudyReference {
  /** Citation text as written in `doc`. */
  text: string
  /** Link given next to the citation in `doc`, or null. */
  url: string | null
  doc: string
  /** Why the study cites it (UI copy, not part of the citation). */
  role: string
}

export interface StudyDoc {
  path: string
  /** GitHub heading anchor (without `#`), checked against the file's headings. */
  anchor?: string
  label: string
}

/**
 * How results of a study can be obtained in a deployment of this app:
 * - `offline`: the engine never runs in the API (`LIVE_ENGINES = ("pypsa",)`); results come only
 *   from published artifacts produced by an offline pipeline;
 * - `pypsa-preset`: a PyPSA preset; the API solves it live when the network allows live
 *   execution (`live_execution` on GET /networks), otherwise it serves the published artifact.
 */
export type StudyExecution = 'offline' | 'pypsa-preset'

export type StudyMetrics =
  | 'stormbench'
  | 'stormrisk'
  | 'advisor'
  | 'grid2op'
  | 'n1'
  | 'ac-reference'
  | 'distribution'
  | 'cross-engine'
  | 'stormml'
  | 'pypsa'

export interface StudyDefinition {
  id: string
  title: string
  /** One-line description (UI copy; no numbers). */
  summary: string
  /** Catalog rows belonging to the study. */
  engine: string
  kind?: ArtifactKind
  /** Artifact shown first when the study has several on one network (e.g. a summary). */
  preferredArtifact?: string
  /** Artifacts that are inputs of the study rather than result views (listed in the manifest only). */
  inputArtifacts?: string[]
  metrics: StudyMetrics
  execution: StudyExecution
  executionNotes: DocQuote[]
  docs: StudyDoc[]
  /** Existing app page with the full interactive view, if any. */
  detailRoute: { path: string; label: string } | null
  references: StudyReference[]
  assumptions: DocQuote[]
  limitations: DocQuote[]
  solver: DocQuote[]
  dataset: DocQuote[]
  reproduction: { cwd: string; commands: string[]; doc: string }
}

const quotes = (doc: string, ...texts: string[]): DocQuote[] => texts.map((text) => ({ text, doc }))

const PAPERS = 'docs/research/research-papers.md'
const STORMBENCH = 'docs/benchmarks/stormbench.md'
const STRESS = 'docs/research/probabilistic-stress.md'
const ADVISOR = 'docs/research/crisis-advisor.md'
const GRID2OP = 'docs/research/grid2op-integration.md'
const AC = 'docs/research/ac-validation.md'
const SIMBENCH = 'docs/research/simbench-distribution.md'
const CROSS = 'docs/benchmarks/cross-engine.md'
const STORMML = 'docs/research/ml-contingency-screening.md'
const CATALOG = 'docs/research/data-catalog.md'
const USER_GUIDE = 'docs/user-guide.md'
const LOCAL_DEV = 'docs/deployment/local-development.md'
const VALIDATION = 'services/api/src/gridstorm_api/validation.py'

const OFFLINE_NOTES: DocQuote[] = [
  ...quotes(VALIDATION, "Engines this API can execute live. Other engines' results are served as precomputed artifacts."),
  ...quotes(LOCAL_DEV, 'They are not automatically recomputed when a browser opens a research page.'),
]

const PGLIB_DATASET = quotes(
  CATALOG,
  'Both cases use PGLib-OPF v23.07, publication date recorded as 2023-07-23, pinned commit dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3.',
)

const REF = {
  wood: {
    text: 'A. J. Wood, B. F. Wollenberg and G. B. Sheblé, Power Generation, Operation, and Control, 3rd ed., Wiley, 2014, chapter 7',
    url: 'https://www.wiley.com/en-us/Power+Generation%2C+Operation%2C+and+Control%2C+3rd+Edition-p-9780471790556',
    doc: STORMBENCH,
  },
  guler: {
    text: 'T. Güler, G. Gross and M. Liu, “Generalized line outage distribution factors,” IEEE Transactions on Power Systems, 22(2), 879–881, 2007',
    url: 'https://doi.org/10.1109/TPWRS.2006.888950',
    doc: STORMBENCH,
  },
  matpower: { text: 'MATPOWER manual, DC modeling and sensitivity factors.', url: 'https://matpower.org/docs/MATPOWER-manual.pdf', doc: STORMBENCH },
  pandapowerPf: { text: 'pandapower power-flow documentation', url: 'https://pandapower.readthedocs.io/en/stable/powerflow.html', doc: STORMBENCH },
  pglib: {
    text: 'PGLib-OPF source and license',
    url: 'https://github.com/power-grid-lib/pglib-opf/tree/dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3',
    doc: STORMBENCH,
  },
  pypsa: {
    text: 'PyPSA — Brown, Hörsch, Schlachtberger 2018, arXiv:1707.09913 (J. Open Res. Softw. 6(1):4, doi:10.5334/jors.188)',
    url: 'https://arxiv.org/abs/1707.09913',
    doc: PAPERS,
  },
  pypsaEur: {
    text: 'PyPSA-Eur — Hörsch, Hofmann, Schlachtberger, Brown 2018, arXiv:1806.01613 (Energy Strategy Reviews 22:207–215, doi:10.1016/j.esr.2018.08.012)',
    url: 'https://arxiv.org/abs/1806.01613',
    doc: PAPERS,
  },
  cycleFlows: {
    text: 'J. Hörsch, H. Ronellenfitsch, D. Witthaut, T. Brown, "Linear Optimal Power Flow Using Cycle Flows", Electric Power Systems Research 158:126–135, 2018, doi:10.1016/j.epsr.2017.12.034',
    url: 'https://arxiv.org/abs/1704.01881',
    doc: PAPERS,
  },
  billinton: {
    text: 'R. Billinton, R. N. Allan, Reliability Evaluation of Power Systems, 2nd ed., Springer 1996, doi:10.1007/978-1-4899-1860-4',
    url: 'https://link.springer.com/book/10.1007/978-1-4899-1860-4',
    doc: PAPERS,
  },
} as const

export const STUDIES: readonly StudyDefinition[] = [
  {
    id: 'stormbench',
    title: 'StormBench — DC PTDF/LODF screening vs exact N-1',
    summary: 'How well and how fast linear DC sensitivity screening finds the single-branch outages that exact DC and AC N-1 power flows flag.',
    engine: 'stormbench',
    kind: 'benchmark',
    preferredArtifact: 'stormbench-summary',
    metrics: 'stormbench',
    execution: 'offline',
    executionNotes: OFFLINE_NOTES,
    docs: [
      { path: STORMBENCH, anchor: 'scope-and-reproducibility', label: 'StormBench benchmark report' },
      { path: STORMBENCH, anchor: 'interpretation-and-limitations', label: 'Interpretation and limitations' },
    ],
    detailRoute: { path: '/benchmarks#stormbench', label: 'Full StormBench tables and charts' },
    references: [
      { ...REF.wood, role: 'DC power flow, PTDF and LODF derivation' },
      { ...REF.guler, role: 'Line outage distribution factors' },
      { ...REF.matpower, role: 'DC modelling and sensitivity factors' },
      { ...REF.pandapowerPf, role: 'Exact AC reference solver' },
      { ...REF.pglib, role: 'Benchmark cases' },
    ],
    assumptions: quotes(
      STORMBENCH,
      'StormBench independently implements sparse DC matrices, PTDF and LODF with NumPy/SciPy.',
      'Operating points are DC-OPF dispatches using PGLib costs approximated with ten linear segments and SciPy HiGHS.',
      'These benchmarks use fixed dispatch (with slack balance), not post-contingency corrective OPF.',
      'Generator reactive limits are not enforced (runpp defaults); convergence therefore does not certify operational feasibility.',
      'The IEEE-named cases use PGLib ratings, not the often-unlimited ratings of other IEEE distributions.',
    ),
    limitations: quotes(
      STORMBENCH,
      'DC screening exactly reproduces the chosen linear DC reference to numerical precision. It does not reproduce nonlinear AC physics.',
      'High recall elsewhere is not a universal safety guarantee.',
      'The results describe one operating point per case, without stochastic outage probabilities, multi-outage events, corrective dispatch or dynamic stability.',
      'They do not establish superiority over other tools, production readiness, or expected energy not served.',
    ),
    solver: quotes(
      STORMBENCH,
      'Measured platform: Intel Core i7-14650HX, 24 logical CPUs, 15.7 GiB RAM, Windows 10 build 26300, Python 3.11.15; NumPy 2.4.6, SciPy 1.17.1, pandapower 3.5.6, Numba 0.68.1, psutil 7.2.2.',
    ),
    dataset: [
      ...quotes(STORMBENCH, 'Source: PGLib-OPF, commit dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3.'),
      ...quotes(STORMBENCH, 'The committed measurements cover six PGLib-OPF networks, including the 1,354-bus PEGASE case.'),
    ],
    reproduction: {
      cwd: 'repository root',
      commands: [
        'cd packages/stormbench',
        'uv sync --locked',
        'uv run --locked python ../../benchmarks/stormbench/run_benchmark.py',
        'uv run --locked python ../../benchmarks/stormbench/make_tables.py',
      ],
      doc: STORMBENCH,
    },
  },
  {
    id: 'stormrisk',
    title: 'StormRisk — Monte Carlo expected energy not served',
    summary: 'Probability-weighted unserved energy (EENS) over sampled component-outage states, each solved as a DC linear OPF.',
    engine: 'stormrisk',
    kind: 'risk',
    metrics: 'stormrisk',
    execution: 'offline',
    executionNotes: [
      ...OFFLINE_NOTES,
      ...quotes(STRESS, "it exceeds the hosted API's 330 MB job budget, so this study is offline-only and is not runnable as a hosted job."),
    ],
    docs: [
      { path: STRESS, anchor: 'method', label: 'Probabilistic stress studies' },
      { path: STRESS, anchor: 'assumptions', label: 'Assumptions' },
      { path: STRESS, anchor: 'scigrid-de-reduced-horizon-study-measured', label: 'SciGRID-DE reduced-horizon study' },
    ],
    detailRoute: { path: '/benchmarks#stormrisk', label: 'Full StormRisk view (convergence, importance)' },
    references: [
      {
        text: 'Grigg et al., "The IEEE Reliability Test System-1996", IEEE Trans. Power Syst. 14(3):1010–1020, 1999',
        url: 'https://doi.org/10.1109/59.780914',
        doc: STRESS,
        role: 'Context for generator and line outage rates (RTS-96)',
      },
      { ...REF.billinton, role: 'Definition of EENS' },
    ],
    assumptions: [
      ...quotes(
        STRESS,
        'packages/stormrisk turns one deterministic StormSpec scenario into a probability-weighted scenario set by Monte Carlo sampling of component outages (and optionally demand)',
        'Neither a storm multiplier nor a whole-horizon outage probability is inferred from these stationary RTS data.',
        'Wind-farm and HVDC-link probabilities are illustrative proxies, not technology-specific reliability statistics.',
        'Components fail independently of each other and of demand (no common-mode or spatially correlated storm damage).',
        'Outages last the whole horizon (the PyPSA adapter supports whole-horizon topology changes only); no repair or restoration.',
        'Each state is a DC linear OPF (PyPSA, HiGHS, threads = 1, capacities fixed at p_nom/s_nom)',
      ),
    ],
    limitations: quotes(
      STRESS,
      'The outage probabilities are modelled assumptions, using generic IEEE RTS-96 values as context and author-selected stress probabilities; the networks are research/example datasets. Numbers below describe the model, not any real power system.',
      'no AC feasibility, voltage, stability or protection behaviour.',
      'Crude Monte Carlo: the CI covers sampling error only, not parameter or model uncertainty.',
      'These overlapping shares are not causal attribution.',
    ),
    solver: quotes(STRESS, 'PyPSA 1.4.0 and HiGHS 1.16.0 solved all states.'),
    dataset: quotes(CATALOG, 'Version/date: PyPSA v1.4.0 example', 'Version/date: PyPSA v1.4.0 packaging of SciGRID v0.2'),
    reproduction: {
      cwd: 'repository root',
      commands: [
        'cd packages/stormrisk',
        'uv sync',
        'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 uv run python scripts/run_study.py studies/ac-dc-meshed-storm-stress.json --workers 1',
        'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 uv run python scripts/run_study.py studies/scigrid-de-storm-stress-6h.json --workers 1',
      ],
      doc: STRESS,
    },
  },
  {
    id: 'crisis-advisor',
    title: 'Crisis Response Advisor — AC-verified remedial actions',
    summary: 'Deterministic candidate search (redispatch, switching, load shedding) for a crisis state; every candidate is accepted or rejected by full AC power flow.',
    engine: 'advisor',
    kind: 'advisor',
    metrics: 'advisor',
    execution: 'offline',
    executionNotes: [
      ...OFFLINE_NOTES,
      ...quotes(USER_GUIDE, 'pandapower N-1, the advisor, Grid2Op, StormBench and StormRisk run offline in their own environments'),
    ],
    docs: [
      { path: ADVISOR, anchor: 'method-and-objective', label: 'Method and objective' },
      { path: ADVISOR, anchor: 'security-scope-and-limitations', label: 'Security scope and limitations' },
    ],
    detailRoute: { path: '/contingency#advisor', label: 'Full advisor view (candidates, baselines)' },
    references: [
      { ...REF.wood, role: 'DC PTDF/LODF sensitivities used to shortlist candidates' },
      {
        text: 'X-GridAgent — Wen, Chen 2025, arXiv:2512.20789',
        url: 'https://arxiv.org/abs/2512.20789',
        doc: PAPERS,
        role: 'Concept mapping only: tool-grounded checks; GridStorm uses no LLM',
      },
    ],
    assumptions: quotes(
      ADVISOR,
      "PGLib's stored Pg values are not assumed feasible: each preset first obtains an intact-network AC-OPF operating point, with current limits conservatively tightened using VMAX to respect published MVA ratings.",
      'Bisection assumes a monotone response; it is not a global minimum-shedding optimization.',
      'VOLL and switching penalties are modeling choices.',
      'The objective ranks the generated candidates, not all feasible interventions.',
    ),
    limitations: quotes(
      ADVISOR,
      'It does not imply N-1 security.',
      'No dynamics, transient/frequency stability, protection coordination, ramp rates, time coupling or restoration sequence is checked.',
      'DC sensitivities are heuristics for candidate selection, not acceptance.',
      'Active-power cost and deterministic one-hour unserved energy are not probability-weighted EENS.',
      '“No accepted candidate” is therefore deliberately weaker than “no solution exists”.',
    ),
    solver: quotes(ADVISOR, 'solve Newton–Raphson AC PF (DC initialization, one flat-start retry, tolerance 1e-8 MVA, generator Q limits enforced).'),
    dataset: [...quotes(ADVISOR, 'PGLib inputs come from data/networks/<network_id>/source/*.m'), ...PGLIB_DATASET],
    reproduction: {
      cwd: 'workers/advisor',
      commands: ['uv sync', 'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 uv run python scripts/build_artifacts.py'],
      doc: ADVISOR,
    },
  },
  {
    id: 'grid2op-agents',
    title: 'Grid2Op — baseline agents over week-long episodes',
    summary: 'Three deterministic agents operate the l2rpn_case14_sandbox grid for up to one week, with and without a forced line outage.',
    engine: 'grid2op',
    kind: 'episode',
    metrics: 'grid2op',
    execution: 'offline',
    executionNotes: [
      ...OFFLINE_NOTES,
      ...quotes(USER_GUIDE, 'pandapower N-1, the advisor, Grid2Op, StormBench and StormRisk run offline in their own environments'),
    ],
    docs: [
      { path: GRID2OP, anchor: 'environment-and-versions', label: 'Environment and versions' },
      { path: GRID2OP, anchor: 'limitations', label: 'Limitations' },
    ],
    detailRoute: { path: '/operations', label: 'Episode replay' },
    references: [
      {
        text: 'L2RPN NeurIPS 2020 retrospective — Marot et al. 2021, arXiv:2103.03104 (PMLR, NeurIPS 2020 Competition and Demonstration Track)',
        url: 'https://arxiv.org/abs/2103.03104',
        doc: PAPERS,
        role: 'Grid2Op framework and L2RPN benchmark',
      },
    ],
    assumptions: quotes(
      GRID2OP,
      'Crisis variant: line 1_3_3 forcibly disconnected at trace row 12 (set_line_status=-1 overriding the agent action of that step)',
      'Seeds: env.reset(seed=seed, options={"time serie id": chronic}) and agent.seed(seed); all agents are deterministic.',
      'obs.simulate uses forecasts, so the greedy agent\'s choices are model-based estimates.',
      'Survival 2016 means "reached the step cap", not that the agent would survive indefinitely.',
    ),
    limitations: quotes(
      GRID2OP,
      'Simulation success ≠ operational safety. Grid2Op is a research environment: a DC/AC power-flow per 5-min step, simplified protection (overload counters), no dynamics, voltage stability or real operator procedures.',
      'Small synthetic 14-bus grid; 2 chronics × 1 seed — illustrative, not statistically significant.',
      'No opponent; the crisis is one scripted outage.',
      'cross-backend or cross-version bit equality is not claimed.',
    ),
    solver: quotes(GRID2OP, 'lightsim2grid 1.3.1 (LightSimBackend)'),
    dataset: [
      ...quotes(
        GRID2OP,
        'l2rpn_case14_sandbox (IEEE-14-derived, 20 lines incl. transformers, 14 substations, 5-min steps, 2016 steps/chronic = 1 week)',
      ),
      { label: 'Archive sha256 (published, verified locally)', text: '1c3b2d73bcfda03c2fc0e977e16e695f303e856752d8b280443accb7248b5827', doc: GRID2OP },
    ],
    reproduction: { cwd: 'workers/grid2op', commands: ['uv run python scripts/run_experiments.py --max-steps 2016'], doc: GRID2OP },
  },
  {
    id: 'pandapower-n1',
    title: 'pandapower AC N-1 contingency screening',
    summary: 'Every in-service branch taken out of an AC-OPF base point and re-solved by Newton–Raphson; outages classified as secure, overload, voltage, islanding or non-convergent.',
    engine: 'pandapower',
    kind: 'n_minus_1',
    metrics: 'n1',
    execution: 'offline',
    executionNotes: [
      ...OFFLINE_NOTES,
      ...quotes(USER_GUIDE, 'pandapower N-1, the advisor, Grid2Op, StormBench and StormRisk run offline in their own environments'),
    ],
    docs: [
      { path: AC, anchor: '3-n-1--n-2-contingency-screening', label: 'N-1 / N-2 contingency screening' },
      { path: AC, anchor: '6-limitations', label: 'Limitations' },
    ],
    detailRoute: { path: '/contingency#n1', label: 'Ranked contingencies and network schematic' },
    references: [
      { ...REF.pandapowerPf, role: 'AC power-flow solver' },
      { ...REF.pglib, role: 'Test cases' },
    ],
    assumptions: quotes(
      AC,
      "Each study therefore starts from pandapower's AC-OPF (runopp, PIPS interior point; polynomial costs, RATE_A, bus voltage and generator P/Q limits).",
      "pandapower's OPF ignores MATPOWER branch angle-difference limits (ANGMIN/ANGMAX).",
      'Generators keep their P and V set points (no re-dispatch); one slack absorbs any imbalance.',
      'N-2: all pairs among the 5 highest-ranked N-1 contingencies (case14 only, 10 pairs).',
    ),
    limitations: quotes(
      AC,
      'Steady-state, balanced, single-snapshot AC power flow only. No protection, dynamics, transient or frequency stability, and no remedial actions or re-dispatch after an outage.',
      'Single-slack balancing. Generator reactive limits are not enforced, so post-contingency voltages at PV buses are optimistic. Loads are constant power.',
      'Islanding treats every island without a slack as de-energised.',
      'The case118 and case300 base points sit on branch limits because the OPF is not security-constrained.',
      'non_convergent comes from one fixed solver configuration and does not establish voltage collapse.',
    ),
    solver: quotes(
      AC,
      'pandapower.runpp: Newton-Raphson, mismatch tolerance 1e-8 MVA, at most 30 iterations, voltage angles on, π transformer model (the same model MATPOWER uses), generator reactive limits not enforced, numba on.',
      'produced with pandapower 3.5.4, SciPy 1.13.1, NumPy 2.2.6, PYPOWER 5.1.21 and Python 3.11.15 on Windows 10 x64.',
    ),
    dataset: [...quotes(AC, 'The OPF objectives agree with the PGLib BASELINE.md AC values (commit dc6be4b)'), ...PGLIB_DATASET],
    reproduction: { cwd: 'workers/pandapower', commands: ['uv run --locked python scripts/run_studies.py'], doc: AC },
  },
  {
    id: 'ac-reference',
    title: 'pandapower AC power-flow reference validation',
    summary: 'pandapower Newton–Raphson results compared with MATPOWER/PYPOWER reference solutions on the same cases.',
    engine: 'pandapower',
    kind: 'benchmark',
    metrics: 'ac-reference',
    execution: 'offline',
    executionNotes: OFFLINE_NOTES,
    docs: [{ path: AC, anchor: '2-reference-validation-ac-reference-validationjson', label: 'Reference validation' }],
    detailRoute: { path: '/benchmarks#ac-reference', label: 'All comparisons' },
    references: [
      { ...REF.matpower, role: 'Reference model and solutions' },
      { ...REF.pandapowerPf, role: 'Solver under test' },
    ],
    assumptions: quotes(
      AC,
      'Pass tolerances: |ΔVm| ≤ 1e-6 pu, |ΔVa| ≤ 1e-4° (wrapped to [−180, 180)), branch/generator |ΔP| ≤ 1e-3 MW, |ΔQ| ≤ 1e-3 Mvar, |balance residual| ≤ 1e-3 MW.',
      'Every case starts from a flat start.',
      'Generator Q is compared per bus, because MATPOWER splits Q between several generators at one PV bus in an arbitrary way.',
    ),
    limitations: quotes(
      AC,
      'These rows therefore validate the conversion and id map (branch orientation, transformer model, shunts, negative loads), not an independent NR algorithm.',
      "The PYPOWER comparison shares algorithmic ancestry with pandapower. The only fully independent reference is MATPOWER's stored soln9_pf.mat (9 buses).",
    ),
    solver: quotes(
      AC,
      'pandapower.runpp: Newton-Raphson, mismatch tolerance 1e-8 MVA, at most 30 iterations, voltage angles on, π transformer model (the same model MATPOWER uses), generator reactive limits not enforced, numba on.',
      'produced with pandapower 3.5.4, SciPy 1.13.1, NumPy 2.2.6, PYPOWER 5.1.21 and Python 3.11.15 on Windows 10 x64.',
    ),
    dataset: quotes(AC, 'Files: MATPOWER data/case*.m at commit 952ebcb, vendored in workers/pandapower/reference_data/matpower/.'),
    reproduction: { cwd: 'workers/pandapower', commands: ['uv run --locked python scripts/run_studies.py'], doc: AC },
  },
  {
    id: 'simbench-distribution',
    title: 'SimBench LV feeder — AC time-series studies',
    summary: 'Week-long quasi-static AC power flows of one rural low-voltage feeder under load, PV and voltage-boundary stress, with two PV mitigations.',
    engine: 'distribution',
    kind: 'timeseries',
    metrics: 'distribution',
    execution: 'offline',
    executionNotes: OFFLINE_NOTES,
    docs: [
      { path: SIMBENCH, anchor: 'scope-and-reproducibility', label: 'SimBench distribution studies' },
      { path: SIMBENCH, anchor: 'numerical-interpretation-and-limitations', label: 'Interpretation and limitations' },
    ],
    detailRoute: null,
    references: [
      {
        text: 'SimBench v1.6.3 license: BSD-3-Clause for code, ODbL-1.0 for the database, DbCL-1.0 for individual contents.',
        url: 'https://github.com/e2nIEE/simbench/blob/v1.6.3/LICENSE',
        doc: SIMBENCH,
        role: 'Benchmark dataset terms',
      },
      {
        text: 'Attribution: University of Kassel, TU Dortmund, RWTH Aachen University, Fraunhofer Institute for Energy Economics and Energy System Technology (IEE), and individual contributors.',
        url: null,
        doc: SIMBENCH,
        role: 'Dataset authors',
      },
      { text: 'Pinned release', url: 'https://pypi.org/project/simbench/1.6.3/', doc: SIMBENCH, role: 'Dataset and converter release' },
      { text: 'time-series documentation', url: 'https://pandapower.readthedocs.io/en/latest/timeseries.html', doc: SIMBENCH, role: 'pandapower time-series engine' },
    ],
    assumptions: quotes(
      SIMBENCH,
      'Heat-wave is only a load ×1.3 proxy: no measured weather, temperature-dependent conductor rating, or causal temperature-to-demand model is used.',
      'This is an explicit assumed upstream voltage rise, not an observed value.',
      'These are selected illustrative windows, not an annual worst-case guarantee or probability sample.',
      'Idling storage is an explicit study assumption, not a simulated storage mitigation.',
    ),
    limitations: quotes(
      SIMBENCH,
      'Results are balanced, positive-sequence, quasi-static three-phase AC power flows: no phase imbalance, dynamics, fault current, protection trips, transformer heating, tap control or corrective load shedding.',
      'convergence does not mean operational feasibility or security.',
      'These are instantaneous study limits, not an EN 50160 compliance calculation',
      'There are no outage probabilities, so these are deterministic energy/violation studies, not EENS or risk estimates.',
      'This is a synthetic benchmark, not a model of a named distribution utility or a national sample.',
    ),
    solver: quotes(
      SIMBENCH,
      'Newton–Raphson uses tolerance 1e-8 MVA, at most 30 iterations, with numba disabled.',
      'using SimBench 1.6.3, pandapower 3.5.6, pandas 2.3.3 and numpy 2.4.6 in its committed uv.lock.',
    ),
    dataset: quotes(
      SIMBENCH,
      '1-LV-rural1--0-sw (scenario 0) and 1-LV-rural1--2-sw (scenario 2)',
      "The grid code's leading 1 denotes data generation version 1, not package version 1.6.3",
    ),
    reproduction: {
      cwd: 'workers/distribution',
      commands: ['uv sync --locked', 'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run python scripts/run_studies.py'],
      doc: SIMBENCH,
    },
  },
  {
    id: 'cross-engine',
    title: 'Cross-engine agreement — pandapower vs PyPSA vs MATPOWER formulas',
    summary: 'The same PGLib cases solved by pandapower, PyPSA and an independent implementation of the MATPOWER DC equations, compared within fixed tolerances.',
    engine: 'cross-engine',
    kind: 'benchmark',
    metrics: 'cross-engine',
    execution: 'offline',
    executionNotes: OFFLINE_NOTES,
    docs: [
      { path: CROSS, anchor: 'verdict-and-scope', label: 'Verdict and scope' },
      { path: CROSS, anchor: 'reproduction-and-evidence', label: 'Reproduction and evidence' },
    ],
    detailRoute: { path: '/benchmarks#cross-engine', label: 'All agreement checks' },
    references: [
      { ...REF.pypsa, role: 'PyPSA linear power flow and LOPF' },
      { ...REF.cycleFlows, role: 'PyPSA KVL cycle formulation' },
      { ...REF.matpower, role: 'MATPOWER DC equations' },
    ],
    assumptions: quotes(
      CROSS,
      'The absolute tolerance is 1e-6 MW (1 W) for every branch flow and bus injection, and 1e-6 degrees for every bus angle.',
      'uses HiGHS with threads=1, random_seed=0.',
      'The importer replaces c2*P²+c1*P+c0 with marginal cost c1+c2*Pmax and drops c0.',
    ),
    limitations: quotes(
      CROSS,
      'These quantify the approximation at the specified operating points, not cross-engine numerical disagreement or a universal DC error bound.',
      'The AC runs ignore generator reactive limits and are not AC-feasibility certificates.',
      'every quadratic coefficient in these particular source files is zero; this is not evidence of quadratic-OPF equivalence.',
      'last-bit floating-point differences are not promised to be bitwise reproducible.',
    ),
    solver: quotes(
      CROSS,
      'Observed environment: Windows 10 build 26300, Python 3.11.15; pandapower 3.5.6, matpowercaseframes 2.1.1, PyPSA 1.4.0, NumPy 2.4.6, SciPy 1.17.1, linopy 0.10.1, highspy/HiGHS 1.16.0.',
    ),
    dataset: PGLIB_DATASET,
    reproduction: { cwd: 'repository root', commands: ['python tests/cross_engine/run_all.py'], doc: CROSS },
  },
  {
    id: 'stormml',
    title: 'StormML — ML contingency screening vs DC-LODF baselines',
    summary: 'Whether models trained on simulator-generated AC N-1 labels rank outages better than transparent DC-LODF and pre-loading screening, on unseen operating points and unseen networks.',
    engine: 'stormml',
    kind: 'benchmark',
    preferredArtifact: 'ml-screening-results',
    inputArtifacts: ['ml-screening-dataset'],
    metrics: 'stormml',
    execution: 'offline',
    executionNotes: OFFLINE_NOTES,
    docs: [
      { path: STORMML, anchor: 'method', label: 'Method' },
      { path: STORMML, anchor: 'limitations', label: 'Limitations' },
    ],
    detailRoute: null,
    references: [{ text: 'T. Güler, G. Gross, M. Liu, "Generalized Line Outage Distribution Factors", IEEE Trans. Power Syst. 22(2):879–881, 2007, doi:10.1109/TPWRS.2006.888950', url: 'https://doi.org/10.1109/TPWRS.2006.888950', doc: PAPERS, role: 'DC-LODF baseline' }],
    assumptions: quotes(
      STORMML,
      'All labels are simulator-generated.',
      "The .m matrices are parsed by stormml.cases and converted with pandapower's own from_ppc; no power-flow code is re-implemented.",
      'Generator Q limits are relaxed in the dispatch and not enforced in any power flow',
    ),
    limitations: quotes(
      STORMML,
      'Labels are simulator outputs (pandapower AC power flow), not historical outages; no dynamics, protection, remedial action schemes, corrective re-dispatch or tap/shunt switching after the outage.',
      'the LONO results are four single-network case studies, not an estimate of generalisation to "networks in general".',
      'Runtime is single-threaded Python on one workstation; the AC N-1 loop is not an optimised production contingency analysis.',
      'These conclusions hold for this simulator, these four test systems and this operating-point generator only.',
    ),
    solver: quotes(STORMML, 'Dataset (real run, 2026-11-15, single thread, Windows x64, pandapower 3.5.4, SciPy 1.13.1)'),
    dataset: quotes(STORMML, 'PGLib-OPF v23.07 pglib_opf_case{30,57,118,300}_ieee.m'),
    reproduction: {
      cwd: 'packages/stormml',
      commands: [
        'export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1',
        'uv run python -m stormml generate --network case30  --n-train 40 --n-test 20',
        'uv run python -m stormml generate --network case57  --n-train 40 --n-test 20',
        'uv run python -m stormml generate --network case118 --n-train 40 --n-test 20',
        'uv run python -m stormml generate --network case300 --n-train 30 --n-test 15',
        'uv run python -m stormml assemble',
        'uv run python -m stormml evaluate --n-boot 1000 --boot-seed 20261114',
      ],
      doc: STORMML,
    },
  },
  {
    id: 'pypsa-presets',
    title: 'PyPSA preset scenarios — operational LOPF',
    summary: 'Published StormSpec presets (baselines, outages, demand and renewable stress) solved as linear optimal power flow on fixed capacities with load shedding.',
    engine: 'pypsa',
    kind: 'simulation',
    metrics: 'pypsa',
    execution: 'pypsa-preset',
    executionNotes: [
      ...quotes(VALIDATION, 'Engines this API can execute live.'),
      ...quotes(USER_GUIDE, 'Other networks complete as precomputed when a stored artifact matches the scenario hash; otherwise HTTP 422 (live_execution_unavailable).'),
    ],
    docs: [
      { path: USER_GUIDE, anchor: '4-execution-modes-live-vs-precomputed', label: 'Execution modes: live vs precomputed' },
      { path: CATALOG, anchor: 'inventory', label: 'Network data catalog' },
    ],
    detailRoute: { path: '/benchmarks#pypsa', label: 'All preset runs' },
    references: [
      { ...REF.pypsa, role: 'Modelling framework (LOPF)' },
      { ...REF.cycleFlows, role: 'KVL cycle formulation' },
      { ...REF.pypsaEur, role: 'Source model of pypsa-eur-be' },
    ],
    assumptions: [
      ...quotes(
        PAPERS,
        'gridstorm_pypsa (contract §4): operational LOPF on fixed capacities; load shedding is a generator per load bus with marginal cost = VOLL',
      ),
      ...quotes(CATALOG, 'Values remain source nominal currency/MWh, not EUR, despite the fixed canonical field name marginal_cost_eur_per_mwh', 'marginal costs illustrative.'),
    ],
    limitations: [
      ...quotes(PAPERS, "No reactive power, voltage magnitudes or losses in LOPF (already the contract's default assumption string); perfect foresight over the horizon."),
      ...quotes(
        CATALOG,
        'These are research/example systems, not validated present-day operational grids.',
        'Any energy-not-served derived from a single deterministic dataset/scenario is unserved energy; reserve “EENS” for probability-weighted results.',
      ),
    ],
    // The solver name and version of each run are read from the artifact payload (`solver`).
    solver: [],
    dataset: [...PGLIB_DATASET, ...quotes(CATALOG, 'Version/date: PyPSA v1.4.0 example')],
    reproduction: {
      cwd: 'workers/pypsa',
      commands: ['uv run python scripts/precompute_presets.py --out-dir ../../data/artifacts/pypsa --benchmark-md ../../docs/benchmarks/pypsa-presets.md'],
      doc: 'workers/pypsa/scripts/precompute_presets.py',
    },
  },
]

export const STUDY_BY_ID: ReadonlyMap<string, StudyDefinition> = new Map(STUDIES.map((s) => [s.id, s]))
