import type { Page } from '@playwright/test'
import type { Map as MapLibreMap } from 'maplibre-gl'

declare global {
  interface Window {
    __gridstormMap?: MapLibreMap
  }
}

/**
 * Wait until the network drawing for `networkId` is on screen, whichever view renders it:
 * - schematic networks (coordinate_kind "schematic", e.g. IEEE 14/118): the SVG schematic
 *   `[data-testid=network-schematic][data-network=<id>][data-ready=true]` with all its buses drawn;
 * - geographic networks: the MapLibre map (`window.__gridstormMap`) has its style and network layers
 *   loaded and renders at least one bus.
 * Pass `null` to accept any network (pages whose network id the test does not know).
 * Resolves with the view kind that rendered.
 */
export async function waitForNetworkView(page: Page, networkId: string | null, timeout = 90_000): Promise<'schematic' | 'map'> {
  const handle = await page.waitForFunction(
    (id) => {
      const sel = id ? `[data-testid="network-schematic"][data-network="${id}"][data-ready="true"]` : '[data-testid="network-schematic"][data-ready="true"]'
      const schematic = document.querySelector(sel)
      if (schematic && schematic.querySelectorAll('[data-bus-id]').length > 0) return 'schematic'
      const map = window.__gridstormMap
      // A kept-alive map stays mounted but undisplayed while a schematic network is shown.
      const el = document.querySelector('[data-testid="network-map"][data-map-ready="true"]')
      if (map && el && el.getClientRects().length > 0 && map.getLayer('gs-buses') && map.queryRenderedFeatures({ layers: ['gs-buses'] }).length > 0)
        return 'map'
      return false
    },
    networkId,
    { timeout },
  )
  return (await handle.jsonValue()) as 'schematic' | 'map'
}
