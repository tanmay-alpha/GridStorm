import { lazy } from 'react'

/**
 * MapLibre map loaded on demand: MapLibre GL is the largest dependency (~290 kB gzip plus its worker),
 * and schematic networks never need it. Render inside <Suspense>.
 */
export const LazyNetworkMap = lazy(() => import('./NetworkMap').then((m) => ({ default: m.NetworkMap })))
