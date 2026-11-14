/**
 * Methods-page content. Every entry paraphrases or quotes a repository document and carries its
 * path in `source`; nothing here is a claim that is not made in those documents.
 * Update together with the cited docs.
 */

export const REPO_URL = 'https://github.com/tanmay-alpha/GridStorm'
export const docUrl = (path: string) => `${REPO_URL}/blob/main/${path}`
export const treeUrl = (path: string) => `${REPO_URL}/tree/main/${path}`

export interface Equation {
  id: string
  title: string
  tex: string
  explanation: string
  source: string
}

export const EQUATIONS: Equation[] = [
  {
    id: 'dc-flow',
    title: 'DC power flow',
    tex: 'P_{ij} = \\frac{\\theta_i - \\theta_j}{x_{ij}}',
    explanation:
      'Linear approximation of AC power flow: flat voltage magnitudes (1 p.u.), small angle differences, lossless lines, no reactive power. Basis of LOPF, PTDF and LODF.',
    source: 'docs/glossary.md',
  },
  {
    id: 'unserved',
    title: 'Unserved energy',
    tex: 'E_{\\text{unserved}} = \\sum_t P_{\\text{shed},t}\\,\\Delta t',
    explanation:
      'Load shedding is modelled as a dispatchable generator per load bus (carrier load_shedding, marginal cost = VOLL); Δt comes from the snapshot weightings.',
    source: 'docs/architecture/contracts.md',
  },
  {
    id: 'curtailment',
    title: 'Curtailment',
    tex: 'E_{\\text{curt}} = \\sum_t \\left(P_{\\text{available},t} - P_{\\text{dispatched},t}\\right)\\Delta t',
    explanation: 'Available variable-renewable energy that is not used, summed over variable generators [MWh].',
    source: 'docs/glossary.md',
  },
  {
    id: 'loading',
    title: 'Line loading',
    tex: '\\text{loading} = 100\\cdot\\frac{|P_{\\text{flow}}|}{s_{\\text{nom}}}\\ \\text{(LOPF)}\\qquad \\text{loading} = 100\\cdot\\frac{|I|}{I_{\\max}}\\ \\text{(AC PF)}',
    explanation: 'A line at ≥ 99.9 % at any snapshot counts as congested in congested_line_count.',
    source: 'docs/glossary.md',
  },
  {
    id: 'ptdf',
    title: 'Power Transfer Distribution Factors',
    tex: '\\mathrm{PTDF} = B_f\\, B_{\\text{bus}}^{-1}\\quad\\text{(reduced, slack removed)}',
    explanation:
      'PTDF_{l,n} is the change of flow on line l for 1 MW injected at bus n and withdrawn at the slack bus, in DC flow.',
    source: 'docs/glossary.md',
  },
  {
    id: 'lodf',
    title: 'Line Outage Distribution Factors',
    tex: '\\Delta P_l = \\mathrm{LODF}_{l,k}\\, P_k^0,\\qquad \\mathrm{LODF}_{l,k} = \\frac{\\mathrm{PTDF}_{l,k}}{1 - \\mathrm{PTDF}_{k,k}}',
    explanation:
      'Branch-to-branch form. Undefined (PTDF_kk = 1) when k is a bridge whose loss islands the grid.',
    source: 'docs/glossary.md',
  },
  {
    id: 'eens',
    title: 'Expected Energy Not Served',
    tex: '\\mathrm{EENS} = \\sum_s p_s\\, E_{\\text{unserved},s},\\qquad \\sum_s p_s = 1',
    explanation:
      'Over a complete, mutually exclusive scenario set. Only as meaningful as the supplied probabilities; infeasible scenarios are excluded rather than counted as zero.',
    source: 'docs/glossary.md',
  },
  {
    id: 'lolp',
    title: 'Loss Of Load Probability',
    tex: '\\mathrm{LOLP} = \\sum_s p_s\\, \\mathbf{1}\\!\\left[E_{\\text{unserved},s} > 0\\right]',
    explanation: 'Probability that some load is not served over a probability-weighted scenario set. Dimensionless.',
    source: 'docs/glossary.md',
  },
  {
    id: 'rho',
    title: 'Grid2Op line usage ratio',
    tex: '\\rho = \\frac{|I|}{I_{\\text{thermal}}},\\qquad \\text{overload} \\iff \\rho > 1',
    explanation:
      'Grid2Op disconnects lines that stay overloaded too long (OVERLOAD_RHO = 1.0 in workers/grid2op/src/gridstorm_grid2op/kpis.py).',
    source: 'docs/glossary.md',
  },
]

export interface Statement {
  text: string
  source: string
}

export const ASSUMPTIONS: Statement[] = [
  {
    text: 'PyPSA results use a DC linearised power flow (LOPF): no reactive power, voltage magnitudes or losses.',
    source: 'docs/architecture/contracts.md',
  },
  {
    text: 'Load shedding is modelled as a dispatchable generator per load bus with marginal cost equal to VOLL (e.g. 10 000 EUR/MWh). VOLL is a modelling assumption, not an observed value.',
    source: 'docs/glossary.md',
  },
  {
    text: 'Infeasible scenarios return outcome "infeasible" with empty series — never fabricated numbers.',
    source: 'docs/architecture/contracts.md',
  },
  {
    text: 'Unsupported scenario operations are rejected, never silently approximated (e.g. a PyPSA line outage with a partial time window is rejected because KVL would still bind the angles).',
    source: 'docs/architecture/contracts.md',
  },
  {
    text: 'Engines run in isolated, separately locked Python environments and exchange data only through versioned JSON / NetCDF artifacts.',
    source: 'docs/decisions/0001-architecture-and-environment-isolation.md',
  },
  {
    text: 'Only the PyPSA engine runs live in the API; pandapower, Crisis Advisor, Grid2Op and StormBench studies run offline and are published as labelled precomputed artifacts.',
    source: 'docs/decisions/0001-architecture-and-environment-isolation.md',
  },
]

export const LIMITATIONS: Statement[] = [
  {
    text: 'GridStorm is a research and teaching tool — not a live utility control system and not a validated real-world blackout predictor.',
    source: 'docs/architecture/overview.md',
  },
  {
    text: 'Screening (PTDF/LODF post-outage DC flows) can miss violations that an AC check would find; it is not a substitute for AC N-1.',
    source: 'docs/glossary.md',
  },
  {
    text: 'EENS and LOLP are only as meaningful as the supplied scenario probabilities.',
    source: 'docs/glossary.md',
  },
  {
    text: 'Islands without a slack/generation cannot be solved by power flow; their load is reported as disconnected/unsupplied, not silently balanced.',
    source: 'docs/glossary.md',
  },
  {
    text: 'Cross-engine claims (e.g. PyPSA DC flows ≈ pandapower DC flows on the same case) require explicit numerical tests across environments.',
    source: 'docs/decisions/0001-architecture-and-environment-isolation.md',
  },
]

export const PROVENANCE_ROWS: { cls: string; meaning: string }[] = [
  { cls: 'observed', meaning: 'Measured or published data used as-is (e.g. bus coordinates from a dataset).' },
  { cls: 'estimated', meaning: 'Derived from observed data by a documented estimation method.' },
  { cls: 'synthetic', meaning: 'Constructed for testing/teaching; not a real system state.' },
  { cls: 'modeled', meaning: 'Assumed model parameters (e.g. marginal costs) or engine outputs of a model.' },
  { cls: 'calculated', meaning: 'Deterministic arithmetic on other values (e.g. KPI aggregations).' },
]

/** Engine pins as declared in contracts §1 and verified on PyPI in ADR 0001. */
export const ENGINE_PINS: { env: string; contents: string; pins: string; source: string }[] = [
  { env: 'core', contents: 'FastAPI API, stormspec, canonical_grid, gridstorm_pypsa, gridstorm_analytics', pins: 'Python 3.11, PyPSA 1.4.x, linopy, highspy, pandas 3', source: 'docs/architecture/contracts.md' },
  { env: 'pandapower', contents: 'gridstorm_pandapower', pins: 'pandapower 3.5.x (pandas 2.x)', source: 'docs/architecture/contracts.md' },
  { env: 'advisor', contents: 'gridstorm_advisor (Crisis Response Advisor)', pins: 'pandapower 3.5.x', source: 'docs/architecture/contracts.md' },
  { env: 'grid2op', contents: 'gridstorm_grid2op', pins: 'grid2op 1.12.x (pandas < 3)', source: 'docs/architecture/contracts.md' },
  { env: 'stormbench', contents: 'stormbench', pins: 'numpy, scipy, pandapower', source: 'docs/architecture/contracts.md' },
]

export const DOC_LINKS: { label: string; path: string }[] = [
  { label: 'Architecture overview', path: 'docs/architecture/overview.md' },
  { label: 'Interface contracts (v1)', path: 'docs/architecture/contracts.md' },
  { label: 'ADR 0001 — architecture and environment isolation', path: 'docs/decisions/0001-architecture-and-environment-isolation.md' },
  { label: 'Glossary', path: 'docs/glossary.md' },
  { label: 'Grid2viz audit', path: 'docs/audit/grid2viz-audit.md' },
]

export const REFERENCES: { text: string; url: string }[] = [
  { text: 'T. Brown, J. Hörsch, D. Schlachtberger, "PyPSA: Python for Power System Analysis", J. Open Research Software 6(1), 2018.', url: 'https://doi.org/10.5334/jors.188' },
  { text: 'L. Thurner et al., "pandapower — an open-source Python tool for convenient modeling, analysis, and optimization of electric power systems", IEEE Trans. Power Systems 33(6), 2018.', url: 'https://doi.org/10.1109/TPWRS.2018.2829021' },
  { text: 'A. Marot et al., "Learning to run a power network challenge for training topology controllers", Electric Power Systems Research 189, 2020.', url: 'https://doi.org/10.1016/j.epsr.2020.106635' },
]
