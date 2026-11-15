/** Layer toggles shared by the MapLibre map and the schematic view (no MapLibre import, so cheap to load). */
export interface LayerVisibility {
  buses: boolean
  lines: boolean
  links: boolean
  generators: boolean
  storage: boolean
  /** Load symbols; drawn by the schematic view only (the geographic map has no load layer). */
  loads: boolean
}

export const DEFAULT_LAYERS: LayerVisibility = {
  buses: true,
  lines: true,
  links: true,
  generators: true,
  storage: true,
  loads: true,
}

/** voltage = colour branches by kV; loading = by `value` (%); delta = by `value` (percentage points). */
export type BranchColorMode = 'voltage' | 'loading' | 'delta'
