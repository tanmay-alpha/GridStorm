import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Plus, RotateCcw, Save } from 'lucide-react'
import { ApiError, api } from '../../api/client'
import { qk, useNetwork, useNetworkAssets, useNetworks, useScenarios } from '../../api/hooks'
import { LIMITS, type EventType, type StormEvent, type StormSpec } from '../../api/stormspec'
import type { ScenarioRecord, ValidationReport } from '../../api/types'
import { NetworkSelect } from '../../components/network/NetworkSelect'
import {
  Badge,
  Button,
  CheckboxField,
  EmptyState,
  ErrorState,
  KeyValue,
  NumberField,
  PageHeader,
  Panel,
  SkeletonBlock,
  TextField,
  cn,
} from '../../components/ui'
import { formatQuantity, formatTimestamp, shortHash } from '../../lib/format'
import { isRecord } from '../../lib/guards'
import { EventEditor } from './EventEditor'
import { EVENT_LABEL, availableEventTypes, blankSpec, localIssues, newEvent, normaliseSpec } from './spec'
import { useDebounced } from './useDebounced'
import { ValidationMessages } from './ValidationMessages'

/** Extract the ValidationReport from a 422 `scenario_invalid` error (services/api contract). */
function reportFromError(err: unknown): ValidationReport | null {
  if (!(err instanceof ApiError) || err.code !== 'scenario_invalid') return null
  const r = err.details.report
  if (isRecord(r) && typeof r.valid === 'boolean' && Array.isArray(r.errors) && Array.isArray(r.warnings)) {
    // Shape checked above; issue entries are rendered as plain strings.
    const report = r as unknown as ValidationReport
    return report
  }
  return null
}

function PresetList({
  records,
  activeId,
  onPick,
}: {
  records: ScenarioRecord[]
  activeId: string | null
  onPick: (r: ScenarioRecord) => void
}) {
  if (!records.length) return <p className="px-1 py-2 text-xs text-fg-muted">None.</p>
  return (
    <ul className="flex flex-col gap-0.5">
      {records.map((r) => (
        <li key={r.id}>
          <button
            type="button"
            onClick={() => onPick(r)}
            aria-current={activeId === r.id ? 'true' : undefined}
            data-testid="preset-item"
            data-preset-id={r.id}
            className={cn(
              'flex w-full flex-col rounded px-2 py-1.5 text-left hover:bg-surface-2',
              activeId === r.id && 'bg-accent-soft',
            )}
          >
            <span className="truncate text-xs font-medium text-fg">{r.name ?? r.spec.name}</span>
            <span className="truncate font-mono text-2xs text-fg-subtle">
              {r.id} · {r.network_id ?? r.spec.dataset.network_id} · {r.spec.events?.length ?? 0} events
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

export default function StudioPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const networks = useNetworks()
  const scenarios = useScenarios()
  const [edited, setEdited] = useState<StormSpec | null>(null)
  const [addType, setAddType] = useState<EventType>('line_outage')

  const presetId = params.get('preset')
  const records = useMemo(() => scenarios.data ?? [], [scenarios.data])
  const presetRecord = presetId ? (records.find((r) => r.id === presetId) ?? null) : null
  const netList = networks.data ?? []
  const requestedNet = params.get('network')
  const network = netList.find((n) => n.id === requestedNet) ?? netList[0] ?? null

  // Current spec: user edits, else the selected preset, else a blank scenario for the network.
  const spec: StormSpec | null =
    edited ?? (presetRecord ? normaliseSpec(presetRecord.spec) : network ? blankSpec(network) : null)
  const specNetwork = spec ? (netList.find((n) => n.id === spec.dataset.network_id) ?? null) : null
  const assets = useNetworkAssets(spec?.dataset.network_id)
  const networkDetail = useNetwork(spec?.dataset.network_id)

  const specJson = spec ? JSON.stringify(spec) : ''
  const debouncedJson = useDebounced(specJson, 400)
  const validation = useQuery({
    queryKey: ['validate', debouncedJson],
    queryFn: ({ signal }) => api.validateScenario(JSON.parse(debouncedJson) as StormSpec, signal),
    enabled: debouncedJson !== '',
    staleTime: Infinity,
    retry: false,
  })
  const validating = specJson !== debouncedJson || validation.isFetching
  const report = specJson === debouncedJson ? (validation.data ?? null) : null

  const run = useMutation({
    mutationFn: (s: StormSpec) =>
      presetRecord && !edited ? api.submitSimulation({ scenario_id: presetRecord.id }) : api.submitSimulation({ scenario: s }),
    onSuccess: (job) => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs })
      void navigate(`/runs/${encodeURIComponent(job.id)}`)
    },
  })
  const save = useMutation({
    mutationFn: (s: StormSpec) => api.saveScenario(s),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: qk.scenarios }),
  })

  const update = (fn: (s: StormSpec) => StormSpec) => {
    if (!spec) return
    setEdited(fn(spec))
    run.reset()
    save.reset()
  }
  const pickPreset = (r: ScenarioRecord) => {
    setEdited(null)
    run.reset()
    save.reset()
    setParams((p) => {
      const q = new URLSearchParams(p)
      q.set('preset', r.id)
      q.delete('network')
      return q
    })
  }
  const newBlank = (networkId: string) => {
    setEdited(null)
    run.reset()
    save.reset()
    setParams((p) => {
      const q = new URLSearchParams(p)
      q.delete('preset')
      q.set('network', networkId)
      return q
    })
  }

  if (networks.error)
    return (
      <div className="p-4">
        <ErrorState error={networks.error} title="Could not load networks" onRetry={() => void networks.refetch()} />
      </div>
    )
  if (networks.isPending)
    return (
      <div className="p-4">
        <SkeletonBlock rows={8} label="Loading Crisis Studio" />
      </div>
    )
  if (!spec || netList.length === 0)
    return <EmptyState title="No networks available">Scenarios need a network dataset in the backend catalog.</EmptyState>

  const local = localIssues(spec)
  const runReport = reportFromError(run.error)
  const shownReport = runReport ?? report
  const blocked = local.length > 0 || report?.valid === false
  const types = assets.data ? availableEventTypes(assets.data) : []
  const effectiveAddType = types.includes(addType) ? addType : (types[0] ?? 'demand_multiplier')
  const presets = records.filter((r) => r.preset)
  const saved = records.filter((r) => !r.preset)
  const snaps = specNetwork?.snapshots ?? null
  const durationH = snaps?.resolution_h != null ? spec.horizon.snapshots * snaps.resolution_h : null

  const setEvent = (i: number, e: StormEvent) =>
    update((s) => ({ ...s, events: s.events.map((x, j) => (j === i ? e : x)) }))

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-3 p-3 md:p-4">
      <PageHeader
        title="Crisis Studio"
        subtitle="Compose a StormSpec scenario from real network assets, validate it against the dataset, and run it on the backend."
        badges={
          presetRecord && !edited ? (
            <Badge tone="info">preset {presetRecord.id}</Badge>
          ) : edited ? (
            <Badge tone="accent">edited</Badge>
          ) : (
            <Badge>new scenario</Badge>
          )
        }
      />
      {networkDetail.data?.live_execution === false && (
        <div role="status" className="gs-panel border-warn/50 p-3 text-sm">
          <h2 className="font-semibold">Precomputed preset results only</h2>
          <p>
            Live execution is unavailable for this network: measured solver memory exceeds the deployment memory limit.
            Select an unchanged preset below to access its available precomputed result. Edited scenarios cannot run live here.
          </p>
        </div>
      )}
      <div className="grid gap-3 lg:grid-cols-[16rem_minmax(0,1fr)_20rem]">
        <Panel title="Scenarios" bodyClassName="p-1.5" className="lg:max-h-[calc(100vh-9rem)] lg:overflow-y-auto">
          {scenarios.error ? (
            <ErrorState error={scenarios.error} title="Could not load scenarios" onRetry={() => void scenarios.refetch()} />
          ) : scenarios.isPending ? (
            <SkeletonBlock rows={4} label="Loading scenarios" />
          ) : (
            <div className="flex flex-col gap-2">
              <section aria-labelledby="presets-h">
                <h3 id="presets-h" className="gs-label px-1">
                  Presets
                </h3>
                <PresetList records={presets} activeId={edited ? null : presetId} onPick={pickPreset} />
              </section>
              <section aria-labelledby="saved-h">
                <h3 id="saved-h" className="gs-label px-1">
                  Saved
                </h3>
                <PresetList records={saved} activeId={edited ? null : presetId} onPick={pickPreset} />
              </section>
            </div>
          )}
        </Panel>

        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="Scenario">
            <div className="grid gap-3 sm:grid-cols-2">
              <NetworkSelect networks={netList} value={spec.dataset.network_id} onChange={newBlank} />
              <TextField
                label="Scenario id"
                value={spec.id}
                testId="scenario-id"
                hint="Lowercase letters, digits, hyphens; 3–64 chars."
                onChange={(id) => update((s) => ({ ...s, id }))}
              />
              <TextField label="Name" value={spec.name} testId="scenario-name" onChange={(name) => update((s) => ({ ...s, name }))} />
              <TextField
                label="Description"
                value={spec.description ?? ''}
                onChange={(description) => update((s) => ({ ...s, description }))}
              />
            </div>
          </Panel>

          <Panel
            title="Horizon"
            description={
              snaps
                ? `Network has ${snaps.count} snapshots × ${formatQuantity(snaps.resolution_h, 'h')} (${formatTimestamp(snaps.start)} → ${formatTimestamp(snaps.end)}).`
                : 'Snapshot metadata unavailable.'
            }
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <NumberField
                label="Start snapshot"
                unit="index"
                step={1}
                min={0}
                value={spec.horizon.start ?? 0}
                testId="horizon-start"
                onChange={(v) => update((s) => ({ ...s, horizon: { ...s.horizon, start: v ?? 0 } }))}
              />
              <NumberField
                label="Snapshots"
                unit="count"
                step={1}
                min={LIMITS.horizonSnapshots.min}
                max={LIMITS.horizonSnapshots.max}
                value={spec.horizon.snapshots}
                testId="horizon-snapshots"
                onChange={(v) => update((s) => ({ ...s, horizon: { ...s.horizon, snapshots: v ?? 0 } }))}
              />
              <div className="flex flex-col justify-end text-xs text-fg-muted">
                Duration: <span className="tabular font-semibold text-fg">{formatQuantity(durationH, 'h')}</span>
              </div>
            </div>
          </Panel>

          <Panel
            title={`Events (${spec.events.length})`}
            actions={
              assets.data && types.length > 0 ? (
                <div className="flex items-center gap-1.5">
                  <label htmlFor="add-event-type" className="sr-only">
                    Event type to add
                  </label>
                  <select
                    id="add-event-type"
                    className="gs-input h-7 min-h-0 py-0 text-xs"
                    value={effectiveAddType}
                    onChange={(e) => setAddType(e.target.value as EventType)}
                    data-testid="add-event-type"
                  >
                    {types.map((t) => (
                      <option key={t} value={t}>
                        {EVENT_LABEL[t]}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="sm"
                    onClick={() => update((s) => ({ ...s, events: [...s.events, newEvent(effectiveAddType, assets.data!)] }))}
                    data-testid="add-event"
                  >
                    <Plus aria-hidden className="size-3.5" /> Add
                  </Button>
                </div>
              ) : null
            }
          >
            {assets.error ? (
              <ErrorState error={assets.error} title="Could not load network assets for pickers" onRetry={assets.refetch} />
            ) : !assets.data ? (
              <SkeletonBlock rows={3} label="Loading network assets" />
            ) : spec.events.length === 0 ? (
              <p className="text-xs text-fg-muted">
                No events: the scenario runs the network as-is (useful as a baseline for comparisons).
              </p>
            ) : (
              <ol className="flex flex-col gap-2">
                {spec.events.map((e, i) => (
                  <EventEditor
                    key={i}
                    index={i}
                    event={e}
                    assets={assets.data!}
                    horizon={spec.horizon}
                    onChange={(ne) => setEvent(i, ne)}
                    onRemove={() => update((s) => ({ ...s, events: s.events.filter((_, j) => j !== i) }))}
                  />
                ))}
              </ol>
            )}
          </Panel>

          <Panel title="Mitigation & execution">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <CheckboxField
                  label="Storage dispatch"
                  hint="Off: storage units held at zero dispatch."
                  checked={spec.mitigation.storage_dispatch}
                  onChange={(v) => update((s) => ({ ...s, mitigation: { ...s.mitigation, storage_dispatch: v } }))}
                />
                <CheckboxField
                  label="Allow renewable curtailment"
                  hint="Off: variable renewables must produce all available power."
                  checked={spec.mitigation.curtailment}
                  onChange={(v) => update((s) => ({ ...s, mitigation: { ...s.mitigation, curtailment: v } }))}
                />
                <CheckboxField
                  label="Load shedding"
                  hint="Adds load-shedding generators at value of lost load."
                  checked={spec.mitigation.load_shedding.enabled}
                  onChange={(v) =>
                    update((s) => ({
                      ...s,
                      mitigation: { ...s.mitigation, load_shedding: { ...s.mitigation.load_shedding, enabled: v } },
                    }))
                  }
                />
              </div>
              <div className="grid gap-2">
                <NumberField
                  label="Value of lost load (VOLL)"
                  unit="EUR/MWh"
                  min={0}
                  max={LIMITS.vollEurPerMwh.max}
                  value={spec.mitigation.load_shedding.voll_eur_per_mwh}
                  testId="voll"
                  onChange={(v) =>
                    update((s) => ({
                      ...s,
                      mitigation: {
                        ...s.mitigation,
                        load_shedding: { ...s.mitigation.load_shedding, voll_eur_per_mwh: v ?? Number.NaN },
                      },
                    }))
                  }
                />
                <NumberField
                  label="Solver time limit"
                  unit="s"
                  min={1}
                  max={LIMITS.timeLimitS.max}
                  value={spec.execution.solver_options?.time_limit_s ?? null}
                  testId="time-limit"
                  onChange={(v) =>
                    update((s) => ({
                      ...s,
                      execution: { ...s.execution, solver_options: { ...s.execution.solver_options, time_limit_s: v ?? Number.NaN } },
                    }))
                  }
                />
                <KeyValue
                  rows={[
                    ['Engine', `${spec.execution.engine} · ${spec.execution.formulation}`],
                    ['Solver', `${spec.execution.solver ?? 'engine default'} · ${spec.execution.solver_options?.threads ?? 1} thread(s)`],
                  ]}
                />
              </div>
            </div>
          </Panel>
        </div>

        <div className="flex min-w-0 flex-col gap-3 lg:sticky lg:top-3 lg:self-start">
          <Panel title="Validation" description="Checked by the backend against the dataset on every change.">
            {validation.error && !runReport ? (
              <ErrorState error={validation.error} title="Validation request failed" onRetry={() => void validation.refetch()} />
            ) : (
              <ValidationMessages report={shownReport} local={local} pending={validating && !runReport} />
            )}
          </Panel>
          <Panel title="Run">
            <div className="flex flex-col gap-2">
              <Button
                variant="primary"
                onClick={() => run.mutate(spec)}
                disabled={blocked || run.isPending}
                data-testid="run-scenario"
              >
                <Play aria-hidden className="size-4" />
                {run.isPending ? 'Submitting…' : 'Run simulation'}
              </Button>
              <Button onClick={() => save.mutate(spec)} disabled={blocked || save.isPending} data-testid="save-scenario">
                <Save aria-hidden className="size-4" />
                {save.isPending ? 'Saving…' : 'Save scenario'}
              </Button>
              {edited && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setEdited(null)
                    run.reset()
                    save.reset()
                  }}
                >
                  <RotateCcw aria-hidden className="size-4" /> Discard edits
                </Button>
              )}
              {blocked && <p className="text-2xs text-fg-muted">Fix the validation errors to enable running.</p>}
              {run.error && !runReport && <ErrorState error={run.error} title="Submission failed" />}
              {save.error && <ErrorState error={save.error} title="Save failed" />}
              {save.data && (
                <p role="status" className="text-xs text-ok" data-testid="save-status">
                  Saved as <code className="font-mono">{save.data.id}</code> (hash {shortHash(save.data.hash)}).
                </p>
              )}
            </div>
          </Panel>
          <details className="gs-panel p-3 text-xs">
            <summary className="cursor-pointer font-semibold">StormSpec JSON</summary>
            <pre className="mt-2 max-h-80 overflow-auto font-mono text-2xs text-fg-muted" data-testid="spec-json">
              {JSON.stringify(spec, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    </div>
  )
}
