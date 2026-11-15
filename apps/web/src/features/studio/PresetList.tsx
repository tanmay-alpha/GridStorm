import type { NetworkSummary, ScenarioRecord } from '../../api/types'
import { Badge, ExecutionBadge, KeyValue, ScenarioCard } from '../../components/ui'
import { formatTimestamp } from '../../lib/format'
import { availability, recordNetwork, type ExecutionPolicy } from './flow'
import { investigationQuestion, scenarioCategory, shortDescription } from './presentation'

/** Preset / saved scenario cards: compact summary, long text and technical ids behind "Details". */
export function PresetList({
  records,
  activeId,
  recommendedId,
  onPick,
  policy,
  networks,
  empty,
}: {
  records: ScenarioRecord[]
  activeId: string | null
  recommendedId: string | null
  onPick: (r: ScenarioRecord) => void
  policy: ExecutionPolicy
  networks: NetworkSummary[]
  empty: string
}) {
  if (!records.length) return <p className="px-1 py-2 text-xs text-fg-muted">{empty}</p>
  return (
    <ul className="grid gap-2 md:grid-cols-2">
      {records.map((r) => {
        const net = recordNetwork(r)
        const netName = networks.find((n) => n.id === net)?.name ?? net
        const title = r.name ?? r.spec.name
        const events = r.spec.events ?? []
        return (
          <li key={r.id} className="min-w-0">
            <ScenarioCard
              testId="preset-card"
              title={title}
              network={netName}
              category={scenarioCategory(r.spec)}
              summary={shortDescription(r.spec.description)}
              question={investigationQuestion(r.spec)}
              selected={activeId === r.id}
              onSelect={() => onPick(r)}
              badges={r.id === recommendedId ? <Badge tone="ok">recommended</Badge> : undefined}
              execution={<ExecutionBadge value={availability(policy, net, r.hash)} testId="preset-execution" />}
              selectAttributes={{ 'data-testid': 'preset-item', 'data-preset-id': r.id }}
              details={
                <div className="flex flex-col gap-2">
                  {r.spec.description && <p className="leading-relaxed text-fg-muted">{r.spec.description}</p>}
                  <KeyValue
                    rows={[
                      ['Scenario id', <code className="font-mono break-all">{r.id}</code>],
                      ['StormSpec hash', <code className="font-mono break-all" title={r.hash}>{r.hash}</code>],
                      ['Network id', <code className="font-mono">{net}</code>],
                      [
                        'Events',
                        events.length ? (
                          <ul className="flex flex-col gap-0.5">
                            {events.map((e, i) => (
                              <li key={i} className="font-mono text-2xs">
                                {e.type}
                                {'asset_id' in e ? ` · ${e.asset_id}` : ''}
                                {'carrier' in e ? ` · ${e.carrier}` : ''}
                                {'value' in e ? ` · ×${e.value}` : ''}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          'none'
                        ),
                      ],
                      ['Horizon', `${r.spec.horizon.snapshots} snapshot(s) from #${r.spec.horizon.start ?? 0}`],
                      ['Kind', r.preset ? 'curated preset' : `saved scenario${r.created_at ? ` · ${formatTimestamp(r.created_at)}` : ''}`],
                    ]}
                  />
                </div>
              }
            />
          </li>
        )
      })}
    </ul>
  )
}
