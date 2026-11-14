import { useEffect, useId, useMemo, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { Badge, Button, Chart, DataTable, EmptyState, ErrorState, Legend, PageHeader, Panel, SkeletonBlock, type ChartOption, type Column } from '../../../components/ui'
import { formatNumber, formatQuantity, NO_VALUE } from '../../../lib/format'
import { loadingColor, LOADING_SCALE, OUTAGED_COLOR } from '../../../lib/scales'
import { ArtifactLoader } from '../components/ArtifactPanel'
import { Disclaimer } from '../components/Disclaimer'
import { GridSchematic, type SchematicEdge, type SchematicNode } from '../components/GridSchematic'
import { useArtifactIndex, useArtifacts } from '../hooks'
import { parseEpisode, rhoStats, type Episode, type EpisodeKpis } from '../lib/episode'
import { groupEpisodes, itemAgent } from '../lib/indexing'

const PLAY_INTERVAL_MS = 300

interface KpiRow {
  agent: string
  artifactId: string
  kpis: EpisodeKpis | null
  failed: boolean
}

const kpiColumns: Column<KpiRow>[] = [
  { key: 'agent', header: 'Agent', sortValue: (r) => r.agent, render: (r) => <span className="font-mono">{r.agent}</span> },
  {
    key: 'survival',
    header: 'Survival',
    align: 'right',
    sortValue: (r) => r.kpis?.survival_steps,
    render: (r) =>
      r.failed ? 'failed to load' : r.kpis ? `${formatNumber(r.kpis.survival_steps)} / ${formatNumber(r.kpis.max_steps)}${r.kpis.survived ? '' : ' (game over)'}` : '…',
  },
  { key: 'overload', header: 'Overloaded line-steps', align: 'right', sortValue: (r) => r.kpis?.overload_line_steps, render: (r) => formatNumber(r.kpis?.overload_line_steps) },
  { key: 'disc', header: 'Disconnections', align: 'right', sortValue: (r) => r.kpis?.disconnection_events, render: (r) => formatNumber(r.kpis?.disconnection_events) },
  { key: 'actions', header: 'Actions', align: 'right', sortValue: (r) => r.kpis?.actions_count, render: (r) => formatNumber(r.kpis?.actions_count) },
  { key: 'illegal', header: 'Illegal', align: 'right', sortValue: (r) => r.kpis?.illegal_actions, render: (r) => formatNumber(r.kpis?.illegal_actions) },
  { key: 'maxrho', header: 'Max ρ', align: 'right', sortValue: (r) => r.kpis?.max_rho, render: (r) => formatNumber(r.kpis?.max_rho, 3) },
  { key: 'reward', header: 'Cumulative reward', align: 'right', sortValue: (r) => r.kpis?.cumulative_reward, render: (r) => formatNumber(r.kpis?.cumulative_reward) },
]

function KpiTable({ items }: { items: { agent: string; artifactId: string }[] }) {
  const results = useArtifacts(
    'grid2op',
    items.map((i) => i.artifactId),
  )
  const rows: KpiRow[] = items.map((it, i) => {
    const r = results[i]
    return { ...it, kpis: r?.data ? parseEpisode(r.data.payload).kpis : null, failed: Boolean(r?.isError) }
  })
  return <DataTable columns={kpiColumns} rows={rows} rowKey={(r) => r.artifactId} caption="Episode KPIs per agent for the selected chronic" />
}

function rhoChart(e: Episode, row: number): ChartOption {
  const { max, mean } = rhoStats(e)
  const x = e.t.map((t, i) => t ?? i)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['max ρ', 'mean ρ'] },
    xAxis: { type: 'value', name: 'step', min: x[0] ?? 0, max: x[x.length - 1] ?? 0 },
    yAxis: { type: 'value', name: 'ρ (I / Imax)' },
    series: [
      {
        name: 'max ρ',
        type: 'line',
        showSymbol: false,
        data: x.map((t, i) => [t, max[i]]),
        markLine: {
          symbol: 'none',
          silent: true,
          data: [{ yAxis: 1, name: 'thermal limit' }, { xAxis: x[row] ?? 0, name: 'selected step' }],
          lineStyle: { type: 'dashed' },
        },
      },
      { name: 'mean ρ', type: 'line', showSymbol: false, data: x.map((t, i) => [t, mean[i]]) },
    ],
  }
}

export function EpisodeReplay({ episode }: { episode: Episode }) {
  const rows = episode.t.length
  const [row, setRow] = useState(0)
  const [playing, setPlaying] = useState(false)
  const sliderId = useId()

  useEffect(() => {
    if (!playing) return
    const h = window.setInterval(() => {
      setRow((r) => {
        if (r >= rows - 1) {
          setPlaying(false)
          return r
        }
        return r + 1
      })
    }, PLAY_INTERVAL_MS)
    return () => window.clearInterval(h)
  }, [playing, rows])

  const layout = episode.layout
  const nodes: SchematicNode[] = useMemo(
    () => (layout?.substations ?? []).flatMap((s) => (s.x !== null && s.y !== null ? [{ id: s.id, x: s.x, y: s.y, label: s.id }] : [])),
    [layout],
  )
  const rho = episode.rho[row] ?? null
  const status = episode.lineStatus[row] ?? null
  const edges: SchematicEdge[] = (layout?.lines ?? []).map((l) => {
    const r = rho?.[l.index] ?? null
    const connected = status ? status[l.index] : null
    const outaged = connected === false
    return {
      id: l.id,
      from: l.subOr,
      to: l.subEx,
      color: outaged ? OUTAGED_COLOR : loadingColor(r === null ? null : r * 100),
      width: 3,
      dashed: outaged,
      title: `${l.id}: ${outaged ? 'disconnected' : r === null ? 'no value' : `ρ = ${r.toFixed(3)}`}`,
    }
  })
  const chart = useMemo(() => rhoChart(episode, row), [episode, row])
  const timeline = episode.actions.flatMap((a, i) =>
    a && (a.type !== 'do_nothing' || a.illegal || a.blocked) ? [{ row: i, t: episode.t[i], action: a }] : [],
  )
  const t = episode.t[row]
  const dt = episode.datetime[row]

  if (rows === 0) return <EmptyState title="Empty episode">The artifact contains no recorded steps.</EmptyState>

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <Button
          variant="secondary"
          onClick={() => {
            if (row >= rows - 1) setRow(0)
            setPlaying((p) => !p)
          }}
          aria-pressed={playing}
          aria-label={playing ? 'Pause replay' : 'Play replay'}
        >
          {playing ? <Pause aria-hidden className="size-4" /> : <Play aria-hidden className="size-4" />}
          {playing ? 'Pause' : 'Play'}
        </Button>
        <label htmlFor={sliderId} className="flex min-w-[14rem] flex-1 flex-col gap-1">
          <span className="gs-label">
            Step {formatNumber(t ?? row)} of {formatNumber(episode.t[rows - 1] ?? rows - 1)}
            {dt && <span className="ml-2 font-mono text-fg-muted">{dt}</span>}
          </span>
          <input
            id={sliderId}
            type="range"
            min={0}
            max={rows - 1}
            step={1}
            value={row}
            onChange={(e) => {
              setPlaying(false)
              setRow(Number(e.target.value))
            }}
            aria-valuetext={`step ${t ?? row}${dt ? `, ${dt}` : ''}`}
            className="w-full accent-[var(--gs-accent)]"
          />
        </label>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          {nodes.length === 0 ? (
            <EmptyState title="No layout">This episode artifact has no substation layout coordinates.</EmptyState>
          ) : (
            <GridSchematic
              nodes={nodes}
              edges={edges}
              showLabels
              ariaLabel={`Grid schematic at step ${t ?? row}, lines coloured by loading ratio rho`}
              caption={layout?.coordinateNote ?? undefined}
            />
          )}
          {!rho && <p className="text-xs text-warn">No grid state at this row (game over).</p>}
          <Legend
            title="Line loading ρ"
            items={[...LOADING_SCALE.map(([, color, label]) => ({ label, color, shape: 'line' as const })), { label: 'disconnected', color: OUTAGED_COLOR, shape: 'line' as const }]}
          />
        </div>
        <Chart option={chart} ariaLabel="Maximum and mean line loading ratio rho over the episode, with the selected step marked" height={300} />
      </div>

      {episode.gameOver ? (
        <div role="status" className="rounded border border-danger/50 bg-danger-soft p-2 text-xs">
          <strong>Game over at step {formatNumber(episode.gameOver.step)}.</strong>
          <ul className="mt-1 list-disc pl-5 font-mono">
            {episode.gameOver.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-xs text-fg-muted">Episode ended: {episode.episodeEnd ?? NO_VALUE}.</p>
      )}

      <section aria-label="Actions timeline">
        <h3 className="text-sm font-semibold">Actions timeline ({timeline.length})</h3>
        {timeline.length === 0 ? (
          <p className="text-xs text-fg-muted">No actions other than do-nothing were applied.</p>
        ) : (
          <ol className="max-h-64 overflow-y-auto text-xs">
            {timeline.map(({ row: r, t: ts, action: a }) => (
              <li key={r}>
                <button
                  type="button"
                  className="flex w-full flex-wrap items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-surface-2 aria-[current=true]:bg-accent-soft"
                  aria-current={r === row}
                  onClick={() => {
                    setPlaying(false)
                    setRow(r)
                  }}
                >
                  <span className="font-mono tabular-nums">t={ts ?? r}</span>
                  <Badge tone={a.source === 'scenario' ? 'warn' : 'accent'}>{a.source ?? 'agent'}</Badge>
                  <span>{a.type}</span>
                  {a.targets.length > 0 && <span className="font-mono text-fg-muted">{a.targets.join(', ')}</span>}
                  {Object.keys(a.redispatchMw).length > 0 && (
                    <span className="font-mono text-fg-muted">
                      {Object.entries(a.redispatchMw)
                        .map(([g, mw]) => `${g} ${formatQuantity(mw, 'MW')}`)
                        .join(', ')}
                    </span>
                  )}
                  {a.illegal && <Badge tone="danger">illegal</Badge>}
                  {a.ambiguous && <Badge tone="danger">ambiguous</Badge>}
                  {a.blocked && <Badge tone="warn">blocked by scenario{a.proposedType ? ` (proposed ${a.proposedType})` : ''}</Badge>}
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>

      {episode.warnings.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-warn">
          {episode.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {Object.keys(episode.kpiDefinitions).length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold">KPI definitions</summary>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            {Object.entries(episode.kpiDefinitions).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="font-mono">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  )
}

export function OperationsPage() {
  const index = useArtifactIndex({ engine: 'grid2op', kind: 'episode' })
  const groups = useMemo(() => groupEpisodes(index.data ?? []), [index.data])
  const [groupKey, setGroupKey] = useState<string | null>(null)
  const [artifactId, setArtifactId] = useState<string | null>(null)
  const groupSelect = useId()
  const agentSelect = useId()
  const group = groups.find((g) => g.key === groupKey) ?? groups[0] ?? null
  const items = group?.items ?? []
  const current = items.find((i) => i.artifact_id === artifactId) ?? items[0] ?? null
  const agents = items.map((i) => ({ agent: itemAgent(i) ?? i.artifact_id, artifactId: i.artifact_id }))

  let body
  if (index.isError) body = <ErrorState error={index.error} onRetry={() => void index.refetch()} />
  else if (index.isPending) body = <SkeletonBlock rows={6} label="Loading episode index" />
  else if (!group || !current)
    body = <EmptyState title="No Grid2Op episodes published">The backend lists no grid2op episode artifacts (data/artifacts/grid2op).</EmptyState>
  else
    body = (
      <>
        <div className="flex flex-wrap gap-3">
          <label htmlFor={groupSelect} className="flex min-w-0 flex-col gap-1">
            <span className="gs-label">Chronic / scenario</span>
            <select
              id={groupSelect}
              className="gs-input"
              value={group.key}
              onChange={(e) => {
                setGroupKey(e.target.value)
                setArtifactId(null)
              }}
            >
              {groups.map((g) => (
                <option key={g.key} value={g.key}>
                  {g.label}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={agentSelect} className="flex min-w-0 flex-col gap-1">
            <span className="gs-label">Agent</span>
            <select id={agentSelect} className="gs-input" value={current.artifact_id} onChange={(e) => setArtifactId(e.target.value)}>
              {agents.map((a) => (
                <option key={a.artifactId} value={a.artifactId}>
                  {a.agent}
                </option>
              ))}
            </select>
          </label>
        </div>
        <Panel title="KPIs per agent" id="kpis">
          <KpiTable items={agents} />
        </Panel>
        <Panel title="Episode replay" id="replay">
          <ArtifactLoader key={current.artifact_id} engine="grid2op" artifactId={current.artifact_id}>
            {(a) => <EpisodeReplay episode={parseEpisode(a.payload)} />}
          </ArtifactLoader>
        </Panel>
      </>
    )

  return (
    <div className="flex flex-col gap-4 p-4">
      <PageHeader title="Operations replay" subtitle="Precomputed Grid2Op episodes: baseline agents operating a sandbox grid over time." />
      <Disclaimer>
        <strong>Simulation success ≠ operational safety.</strong> Surviving a Grid2Op episode means the simulator did not reach game over under its
        own rules on this sandbox environment; it says nothing about the safety of any real grid or control policy.
      </Disclaimer>
      {body}
    </div>
  )
}
