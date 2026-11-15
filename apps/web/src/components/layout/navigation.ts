export const WORKSPACE_NAV = [
  { to: '/explore', label: 'Explore', title: 'Grid Explorer' },
  { to: '/studio', label: 'Simulate', title: 'Crisis Studio' },
  { to: '/compare', label: 'Compare', title: 'Compare & Replay' },
  { to: '/mitigation', label: 'Mitigation', title: 'Mitigation comparison' },
  { to: '/library', label: 'Library', title: 'Library' },
] as const
export const RESEARCH_NAV = [
  { to: '/workbench', label: 'Workbench', title: 'Research Workbench' },
  { to: '/contingency', label: 'Contingency', title: 'Contingency' },
  { to: '/operations', label: 'Operations', title: 'Operations' },
  { to: '/benchmarks', label: 'Benchmarks', title: 'Benchmarks' },
  { to: '/methods', label: 'Methods', title: 'Methods' },
] as const
export const NAV = [...WORKSPACE_NAV, ...RESEARCH_NAV]
