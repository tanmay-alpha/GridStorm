import { useAssetTable } from '../../api/hooks'
import type { StormEvent, StormSpec } from '../../api/stormspec'
import type { NetworkSummary } from '../../api/types'
import { Badge, Panel, SkeletonBlock } from '../../components/ui'
import { formatNumber, formatQuantity } from '../../lib/format'
import { eventPhrase, investigationQuestion, plural, shortDescription } from './presentation'

type Outage = Extract<StormEvent, { type: 'generator_outage' | 'line_outage' | 'link_outage' }>

const isOutage = (e: StormEvent): e is Outage => e.type === 'generator_outage' || e.type === 'line_outage' || e.type === 'link_outage'

interface AssetFact {
  key: string
  kind: string
  id: string
  /** Where the asset sits: its bus, or "busA – busB" for a branch. */
  where: string | null
  /** Rating read from the asset table (installed MW, MVA rating); null when not reported. */
  rating: string | null
  detail: string | null
  /** The id is not in the network's asset table (validation reports it too). */
  missing: boolean
}

function outageFacts(
  outages: Outage[],
  tables: {
    generators: { id: string; bus: string; carrier: string | null; p_nom_mw: number | null }[] | undefined
    lines: { id: string; bus0: string; bus1: string; s_nom_mva: number | null; v_nom_kv: number | null; length_km: number | null }[] | undefined
    transformers: { id: string; bus0: string; bus1: string; s_nom_mva: number | null }[] | undefined
    links: { id: string; bus0: string; bus1: string; p_nom_mw: number | null; carrier: string | null }[] | undefined
  },
): AssetFact[] {
  return outages.map((e, i) => {
    const key = `${i}-${e.type}-${e.asset_id}`
    if (e.type === 'generator_outage') {
      const g = tables.generators?.find((x) => x.id === e.asset_id)
      const total = tables.generators?.reduce((s, x) => s + (x.p_nom_mw ?? 0), 0) ?? null
      const share = g?.p_nom_mw != null && total ? (g.p_nom_mw / total) * 100 : null
      return {
        key,
        kind: 'Generator',
        id: e.asset_id,
        where: g ? `bus ${g.bus}` : null,
        rating: g ? formatQuantity(g.p_nom_mw, 'MW') : null,
        detail: g ? [g.carrier, share !== null ? `${formatNumber(share, 1)} % of installed generation` : null].filter(Boolean).join(' · ') || null : null,
        missing: !!tables.generators && !g,
      }
    }
    if (e.type === 'link_outage') {
      const l = tables.links?.find((x) => x.id === e.asset_id)
      return {
        key,
        kind: 'Link',
        id: e.asset_id,
        where: l ? `${l.bus0} – ${l.bus1}` : null,
        rating: l ? formatQuantity(l.p_nom_mw, 'MW') : null,
        detail: l?.carrier ?? null,
        missing: !!tables.links && !l,
      }
    }
    if (e.component === 'transformer') {
      const t = tables.transformers?.find((x) => x.id === e.asset_id)
      return {
        key,
        kind: 'Transformer',
        id: e.asset_id,
        where: t ? `${t.bus0} – ${t.bus1}` : null,
        rating: t ? formatQuantity(t.s_nom_mva, 'MVA') : null,
        detail: null,
        missing: !!tables.transformers && !t,
      }
    }
    const l = tables.lines?.find((x) => x.id === e.asset_id)
    return {
      key,
      kind: 'Line',
      id: e.asset_id,
      where: l ? `${l.bus0} – ${l.bus1}` : null,
      rating: l ? formatQuantity(l.s_nom_mva, 'MVA') : null,
      detail: l ? [l.v_nom_kv != null ? formatQuantity(l.v_nom_kv, 'kV') : null, l.length_km != null ? formatQuantity(l.length_km, 'km') : null].filter(Boolean).join(' · ') || null : null,
      missing: !!tables.lines && !l,
    }
  })
}

/**
 * Studio aside: the question the scenario asks, its description, and a preview of the assets its
 * events touch, read from the network's asset tables (ratings, buses). Nothing here is a result.
 */
export function ScenarioContext({ spec, network }: { spec: StormSpec; network: NetworkSummary | null }) {
  const net = spec.dataset.network_id
  const outages = spec.events.filter(isOutage)
  const has = (t: Outage['type'], component?: 'line' | 'transformer') =>
    outages.some((e) => e.type === t && (!component || (e.type === 'line_outage' && e.component === component)))
  const generators = useAssetTable(net, 'generators', has('generator_outage'))
  const lines = useAssetTable(net, 'lines', has('line_outage', 'line'))
  const transformers = useAssetTable(net, 'transformers', has('line_outage', 'transformer'))
  const links = useAssetTable(net, 'links', has('link_outage'))
  const pending = [
    has('generator_outage') && generators.isPending,
    has('line_outage', 'line') && lines.isPending,
    has('line_outage', 'transformer') && transformers.isPending,
    has('link_outage') && links.isPending,
  ].some(Boolean)
  const facts = outageFacts(outages, { generators: generators.data, lines: lines.data, transformers: transformers.data, links: links.data })
  const others = spec.events.filter((e) => !isOutage(e))
  const description = shortDescription(spec.description, 220)
  return (
    <Panel title="Scenario context" id="scenario-context" bodyClassName="flex flex-col gap-3">
      <p className="text-sm leading-snug text-fg" data-testid="scenario-question">
        <span className="gs-label mb-0.5 block">Question</span>
        {investigationQuestion(spec)}
      </p>
      {description && <p className="text-xs leading-relaxed text-fg-muted">{description}</p>}
      {outages.length > 0 && (
        <section aria-labelledby="ctx-assets" className="flex flex-col gap-1.5">
          <h3 id="ctx-assets" className="gs-label">
            Affected {outages.length === 1 ? 'asset' : 'assets'}
          </h3>
          {pending ? (
            <SkeletonBlock rows={2} label="Loading asset data" />
          ) : (
            <ul className="flex flex-col gap-1.5" data-testid="affected-assets">
              {facts.map((f) => (
                <li key={f.key} className="rounded-lg border border-line bg-surface-2 px-2.5 py-2 text-xs" data-asset-id={f.id}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone="danger">out of service</Badge>
                    <span className="font-semibold text-fg">{f.kind}</span>
                    <code className="font-mono text-fg">{f.id}</code>
                  </div>
                  {f.missing ? (
                    <p className="mt-1 text-warn">Not found in the network’s asset table.</p>
                  ) : (
                    <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-fg-muted">
                      {f.where && (
                        <>
                          <dt>Location</dt>
                          <dd className="min-w-0 break-words font-mono text-fg">{f.where}</dd>
                        </>
                      )}
                      {f.rating && (
                        <>
                          <dt>Rating</dt>
                          <dd className="tabular text-fg">{f.rating}</dd>
                        </>
                      )}
                      {f.detail && (
                        <>
                          <dt>Detail</dt>
                          <dd className="min-w-0 break-words text-fg">{f.detail}</dd>
                        </>
                      )}
                    </dl>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="text-2xs text-fg-subtle">Ratings and locations are read from the dataset’s asset tables.</p>
        </section>
      )}
      {others.length > 0 && (
        <section aria-labelledby="ctx-events" className="flex flex-col gap-1">
          <h3 id="ctx-events" className="gs-label">
            Other events
          </h3>
          <ul className="flex list-disc flex-col gap-0.5 pl-4 text-xs text-fg">
            {others.map((e, i) => (
              <li key={`${e.type}-${i}`}>{eventPhrase(e)}</li>
            ))}
          </ul>
        </section>
      )}
      {spec.events.length === 0 && <p className="text-xs text-fg-muted">No events: the grid runs as-is, the reference for comparisons.</p>}
      {network && (
        <p className="border-t border-line pt-2 text-2xs text-fg-subtle">
          {network.name}: {plural(network.counts.buses ?? 0, 'bus', 'buses')}, {plural(network.counts.generators ?? 0, 'generator')}
          {network.peak_load_mw != null && <>, peak load {formatQuantity(network.peak_load_mw, 'MW', { scale: true })}</>}
          {network.coordinate_kind === 'schematic' ? ' · schematic layout' : ''}.
        </p>
      )}
    </Panel>
  )
}
