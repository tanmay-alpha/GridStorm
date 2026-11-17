import { useMemo, type ReactNode } from 'react'
import { HVDC_COLOR } from '../../../lib/scales'
import { MAP_INK, deviceFill, deviceStroke, schematicVoltageColor } from './colors'
import type { MapFeatures } from '../features'
import type { BranchColorMode, LayerVisibility } from '../layers'
import { BranchLegend } from '../MapLegend'

function Row({ swatch, children }: { swatch: ReactNode; children: ReactNode }) {
  return (
    <li className="flex items-center gap-2 text-fg-muted">
      <svg aria-hidden width={24} height={16} viewBox="-12 -8 24 16" className="shrink-0 overflow-visible">
        {swatch}
      </svg>
      <span>{children}</span>
    </li>
  )
}

/**
 * Legend for SchematicView: the nominal voltages actually present (dataset `v_nom_kv`, as stored),
 * branch types and attached-unit symbols present in the drawing, and result overlays only when the
 * caller marked assets. Loading colours come from BranchLegend and appear only in loading/delta mode.
 */
export function SchematicLegend({
  features,
  layers,
  mode = 'voltage',
  deltaLabel,
}: {
  features: MapFeatures
  layers: LayerVisibility
  mode?: BranchColorMode
  /** Passed to the branch legend in delta mode. */
  deltaLabel?: string
}) {
  const facts = useMemo(() => {
    const kv = new Set<number>()
    const kinds = new Set<string>()
    let outaged = false
    let highlighted = false
    for (const f of features.buses.features) if (typeof f.properties.v_nom_kv === 'number') kv.add(f.properties.v_nom_kv)
    for (const f of features.branches.features) {
      kinds.add(String(f.properties.asset_type))
      outaged ||= f.properties.outaged === true
      highlighted ||= f.properties.highlighted === true
    }
    for (const fc of [features.generators, features.storage, features.loads])
      for (const f of fc.features) {
        outaged ||= f.properties.outaged === true
        highlighted ||= f.properties.highlighted === true
      }
    const unknownKv = features.buses.features.some((f) => typeof f.properties.v_nom_kv !== 'number')
    return {
      levels: [...kv].sort((a, b) => a - b),
      unknownKv,
      kinds,
      generators: features.generators.features.length > 0,
      storage: features.storage.features.length > 0,
      loads: features.loads.features.length > 0,
      outaged,
      highlighted,
    }
  }, [features])

  const line = (color: string, dash?: string, width = 2.6) => <path d="M-11 0H11" stroke={color} strokeWidth={width} strokeDasharray={dash} strokeLinecap="round" />
  return (
    <div className="flex flex-col gap-2 text-xs" data-testid="schematic-legend">
      {mode === 'voltage' ? (
        <figure>
          <figcaption className="gs-label mb-1">Nominal voltage (dataset v_nom)</figcaption>
          <ul className="flex flex-col gap-0.5">
            {facts.levels.map((kv) => (
              <Row key={kv} swatch={line(schematicVoltageColor(kv))}>
                {kv.toLocaleString('en-US')} kV
              </Row>
            ))}
            {facts.unknownKv && <Row swatch={line(schematicVoltageColor(null))}>voltage not reported</Row>}
          </ul>
          <p className="mt-1 text-2xs text-fg-subtle">Colours: Open Infrastructure Map voltage scale (below 10 kV and unknown in neutral ink); thicker = higher level.</p>
        </figure>
      ) : (
        <BranchLegend mode={mode} deltaLabel={deltaLabel} />
      )}
      <figure>
        <figcaption className="gs-label mb-1">Symbols</figcaption>
        <ul className="flex flex-col gap-0.5">
          {layers.buses && (
            <Row swatch={<circle r={5} fill="var(--gs-surface)" stroke={MAP_INK} strokeWidth={2.4} />}>Bus (ring colour = voltage)</Row>
          )}
          {layers.lines && facts.kinds.has('line') && <Row swatch={line(MAP_INK)}>Line</Row>}
          {layers.lines && facts.kinds.has('transformer') && (
            <Row
              swatch={
                <>
                  {line(MAP_INK)}
                  <circle cx={-3.4} r={5} fill="var(--gs-surface)" stroke={MAP_INK} strokeWidth={1.6} />
                  <circle cx={3.4} r={5} fill="none" stroke={MAP_INK} strokeWidth={1.6} />
                </>
              }
            >
              Transformer
            </Row>
          )}
          {layers.links && facts.kinds.has('link') && <Row swatch={line(HVDC_COLOR, '7 4')}>DC / controllable link</Row>}
          {layers.generators && facts.generators && (
            <Row
              swatch={
                <>
                  <circle r={6.5} fill="var(--gs-surface)" stroke={MAP_INK} strokeWidth={1.8} />
                  <path d="M-3.6 0C-2.6 -3 -1 -3 0 0S2.6 3 3.6 0" fill="none" stroke={MAP_INK} strokeWidth={1.4} />
                </>
              }
            >
              Generator (colour = carrier)
            </Row>
          )}
          {layers.storage && facts.storage && (
            <Row
              swatch={
                <>
                  <circle r={6.5} style={{ fill: deviceFill('#7d6ad6'), stroke: deviceStroke('#7d6ad6') }} strokeWidth={1.8} />
                  <path d="M-1.6 -3.8V3.8M1.6 -2V2" style={{ stroke: deviceStroke('#7d6ad6') }} strokeWidth={1.6} />
                </>
              }
            >
              Storage unit
            </Row>
          )}
          {layers.loads && facts.loads && <Row swatch={<path d="M-5 -5L6 0L-5 5Z" fill={MAP_INK} />}>Load</Row>}
          {facts.outaged && (
            <Row
              swatch={
                <>
                  {line('var(--gs-danger)', '6 4')}
                  <path d="M-4 -4L4 4M-4 4L4 -4" stroke="var(--gs-danger)" strokeWidth={2} />
                </>
              }
            >
              Out of service in scenario
            </Row>
          )}
          {facts.highlighted && <Row swatch={line('var(--gs-fg)', undefined, 8)}>Highlighted</Row>}
        </ul>
      </figure>
      {mode === 'loading' && (
        <p className="text-2xs text-fg-subtle">Red halo: loading ≥ 99.9 % (congested) at the selected snapshot.</p>
      )}
    </div>
  )
}
