import { useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, Play, Plus, RotateCcw, Save } from 'lucide-react'
import { ApiError, api } from '../../api/client'
import { qk, useNetwork, useNetworkAssets, useNetworks, useScenario, useScenarios } from '../../api/hooks'
import { LIMITS, type EventType, type StormEvent, type StormSpec } from '../../api/stormspec'
import type { NetworkSummary, ScenarioRecord, ValidationReport } from '../../api/types'
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
  type Tone,
} from '../../components/ui'
import { formatNumber, formatQuantity, formatTimestamp, shortHash } from '../../lib/format'
import { isRecord } from '../../lib/guards'
import { EventEditor } from './EventEditor'
import {
  AVAILABILITY_LABEL,
  STEPS,
  STEP_LABEL,
  availability,
  canEnter,
  effectiveStep,
  initialStep,
  recordNetwork,
  runBlockReason,
  runnableAlternatives,
  type Availability,
  type ExecutionPolicy,
  type Step,
} from './flow'
import { EVENT_LABEL, availableEventTypes, blankSpec, localIssues, newEvent, normaliseSpec } from './spec'
import { useDebounced } from './useDebounced'
import { useExecutionPolicy } from './useExecutionPolicy'
import { ValidationMessages } from './ValidationMessages'

/** Extract the ValidationReport from a 422 `scenario_invalid` error (services/api contract). */
function reportFromError(err: unknown): ValidationReport | null {
  if (!(err instanceof ApiError) || err.code !== 'scenario_invalid') return null
  const r = err.details.report
  if (isRecord(r) && typeof r.valid === 'boolean' && Array.isArray(r.errors) && Array.isArray(r.warnings)) {
    // Shape checked above; issue entries are rendered as plain strings.
    return r as unknown as ValidationReport
  }
  return null
}

const AVAILABILITY_TONE: Record<Availability, Tone> = {
  live: 'accent',
  precomputed: 'info',
  unavailable: 'warn',
  checking: 'neutral',
}

function AvailabilityBadge({ value, testId }: { value: Availability; testId?: string }) {
  return (
    <span data-testid={testId} data-availability={value}>
      <Badge tone={AVAILABILITY_TONE[value]}>{AVAILABILITY_LABEL[value]}</Badge>
    </span>
  )
}

function Stepper({ current, open, onGo }: { current: Step; open: (s: Step) => boolean; onGo: (s: Step) => void }) {
  return (
    <nav aria-label="Crisis Studio steps">
      <ol className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {STEPS.map((s, i) => {
          const active = s === current
          const done = STEPS.indexOf(current) > i
          return (
            <li key={s}>
              <button
                type="button"
                onClick={() => onGo(s)}
                disabled={!open(s)}
                aria-current={active ? 'step' : undefined}
                data-testid={`step-${s}`}
                className={cn(
                  'flex w-full items-center gap-2 rounded border px-2.5 py-2 text-left text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                  active ? 'border-accent bg-accent-soft text-fg' : 'border-line bg-surface text-fg-muted hover:bg-surface-2',
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full border text-2xs font-semibold',
                    active ? 'border-accent bg-accent text-accent-fg' : done ? 'border-ok text-ok' : 'border-line-strong',
                  )}
                >
                  {done ? <Check className="size-3" /> : i + 1}
                </span>
                <span>
                  <span className="sr-only">Step {i + 1}: </span>
                  {STEP_LABEL[s]}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function GridStep({
  networks,
  value,
  policy,
  onPick,
}: {
  networks: NetworkSummary[]
  value: string | null
  policy: ExecutionPolicy
  onPick: (id: string) => void
}) {
  return (
    <Panel title="1 · Choose grid" description="The power-system dataset the crisis is applied to.">
      <div role="radiogroup" aria-label="Grid" className="grid gap-2 sm:grid-cols-2">
        {networks.map((n) => {
          const live = policy.live.get(n.id)
          const checked = value === n.id
          return (
            <button
              key={n.id}
              type="button"
              role="radio"
              aria-checked={checked}
              onClick={() => onPick(n.id)}
              data-testid="grid-option"
              data-network-id={n.id}
              className={cn(
                'flex flex-col gap-1 rounded border p-3 text-left hover:bg-surface-2',
                checked ? 'border-accent bg-accent-soft' : 'border-line',
              )}
            >
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-semibold text-fg">{n.name}</span>
                <span data-testid="grid-execution">
                  {live === undefined ? <Badge>checking availability</Badge> : live ? (
                    <Badge tone="accent" title="This deployment solves scenarios on this grid live">
                      live solve
                    </Badge>
                  ) : (
                    <Badge tone="info" title="Only scenarios with a verified precomputed result can be opened">
                      precomputed only
                    </Badge>
                  )}
                </span>
                {n.coordinate_kind === 'schematic' && <Badge tone="warn">schematic</Badge>}
              </span>
              <span className="font-mono text-2xs text-fg-subtle">{n.id}</span>
              <span className="text-xs text-fg-muted">
                {formatNumber(n.counts.buses ?? null)} buses · {formatNumber(n.counts.lines ?? null)} lines ·{' '}
                {n.snapshots ? `${n.snapshots.count} snapshots × ${formatQuantity(n.snapshots.resolution_h, 'h')}` : 'snapshots n/a'}
                {n.peak_load_mw != null && <> · peak load {formatQuantity(n.peak_load_mw, 'MW', { scale: true })}</>}
              </span>
            </button>
          )
        })}
      </div>
    </Panel>
  )
}

function ScenarioList({
  records,
  activeId,
  onPick,
  policy,
  empty,
}: {
  records: ScenarioRecord[]
  activeId: string | null
  onPick: (r: ScenarioRecord) => void
  policy: ExecutionPolicy
  empty: string
}) {
  if (!records.length) return <p className="px-1 py-2 text-xs text-fg-muted">{empty}</p>
  return (
    <ul className="grid gap-1.5 sm:grid-cols-2">
      {records.map((r) => (
        <li key={r.id}>
          <button
            type="button"
            onClick={() => onPick(r)}
            aria-current={activeId === r.id ? 'true' : undefined}
            data-testid="preset-item"
            data-preset-id={r.id}
            className={cn(
              'flex h-full w-full flex-col gap-0.5 rounded border px-2.5 py-2 text-left hover:bg-surface-2',
              activeId === r.id ? 'border-accent bg-accent-soft' : 'border-line',
            )}
          >
            <span className="text-xs font-semibold text-fg">{r.name ?? r.spec.name}</span>
            {r.spec.description && <span className="line-clamp-2 text-2xs text-fg-muted">{r.spec.description}</span>}
            <span className="truncate font-mono text-2xs text-fg-subtle">
              {r.id} · {recordNetwork(r)} · {r.spec.events?.length ?? 0} events
            </span>
            <span className="mt-0.5">
              <AvailabilityBadge value={availability(policy, recordNetwork(r), r.hash)} testId="preset-execution" />
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function SummaryRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="gs-label">{label}</dt>
      <dd className="min-w-0 break-words text-xs text-fg">{children}</dd>
    </div>
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
  const [showAllPresets, setShowAllPresets] = useState(false)
  const [requestedStep, setRequestedStep] = useState<Step>(() => initialStep(params.get('network'), params.get('preset')))

  const presetId = params.get('preset')
  const records = useMemo(() => scenarios.data ?? [], [scenarios.data])
  const listedRecord = presetId ? (records.find((r) => r.id === presetId) ?? null) : null
  // Unlisted (anonymous) saves are not in the list but can be opened by id via ?preset=<id>.
  const unlisted = useScenario(presetId, scenarios.isSuccess && !listedRecord)
  const presetRecord = listedRecord ?? unlisted.data ?? null
  const netList = useMemo(() => networks.data ?? [], [networks.data])
  const requestedNet = params.get('network')

  // Current spec: user edits, else the selected preset/saved scenario. No crisis chosen yet: no spec.
  const spec: StormSpec | null = edited ?? (presetRecord ? normaliseSpec(presetRecord.spec) : null)
  const networkId =
    spec?.dataset.network_id ?? (requestedNet && netList.some((n) => n.id === requestedNet) ? requestedNet : null)
  const network = netList.find((n) => n.id === networkId) ?? null
  const crisisChosen = spec !== null
  const flowState = { networkId, crisisChosen }
  const step = effectiveStep(requestedStep, flowState)

  const { policy, simArtifacts } = useExecutionPolicy()
  // Picker assets are only needed while events are edited (step 2 with a chosen crisis).
  const assets = useNetworkAssets(step === 'crisis' && crisisChosen ? networkId : null)
  const networkDetail = useNetwork(networkId)

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
  const report = spec && specJson === debouncedJson ? (validation.data ?? null) : null

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

  const resetMutations = () => {
    run.reset()
    save.reset()
  }
  const update = (fn: (s: StormSpec) => StormSpec) => {
    if (!spec) return
    setEdited(fn(spec))
    resetMutations()
  }
  const pickNetwork = (id: string) => {
    if (id !== networkId) {
      setEdited(null)
      resetMutations()
      setParams((p) => {
        const q = new URLSearchParams(p)
        q.delete('preset')
        q.set('network', id)
        return q
      })
    }
    setRequestedStep('crisis')
  }
  const pickPreset = (r: ScenarioRecord) => {
    setEdited(null)
    resetMutations()
    setParams((p) => {
      const q = new URLSearchParams(p)
      q.set('preset', r.id)
      q.set('network', recordNetwork(r))
      return q
    })
  }
  const startCustom = () => {
    if (!network) return
    setEdited(blankSpec(network))
    resetMutations()
    setParams((p) => {
      const q = new URLSearchParams(p)
      q.delete('preset')
      q.set('network', network.id)
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
  if (netList.length === 0)
    return <EmptyState title="No networks available">Scenarios need a network dataset in the backend catalog.</EmptyState>

  const local = spec ? localIssues(spec) : []
  const runReport = reportFromError(run.error)
  const shownReport = runReport ?? report
  const blocked = local.length > 0 || report?.valid === false
  const presets = records.filter((r) => r.preset)
  const saved = records.filter((r) => !r.preset)
  const onNetwork = (r: ScenarioRecord) => recordNetwork(r) === networkId
  const netPresets = presets.filter(onNetwork)
  const visiblePresets = showAllPresets ? presets : netPresets
  const visibleSaved = showAllPresets ? saved : saved.filter(onNetwork)
  const liveExecution = networkDetail.data?.live_execution ?? network?.live_execution
  const liveNetworks = netList.filter((n) => n.live_execution).map((n) => n.id)
  const runnablePresets = netPresets.filter((r) => policy.precomputed?.has(r.hash))
  const currentHash = presetRecord && !edited ? presetRecord.hash : (report?.scenario_hash ?? null)
  const avail: Availability = networkId ? availability(policy, networkId, currentHash) : 'checking'
  const blockReason = runBlockReason({
    crisisChosen,
    localIssues: local.length,
    valid: report?.valid ?? null,
    validating,
    submitting: run.isPending,
    availability: avail,
  })
  const alternatives =
    avail === 'unavailable' && networkId
      ? runnableAlternatives(networkId, presetRecord, records, netList, policy)
      : []
  const liveUnavailable =
    run.error instanceof ApiError && run.error.code === 'live_execution_unavailable' ? run.error : null
  const liveNetworksFromError = Array.isArray(liveUnavailable?.details.live_networks)
    ? (liveUnavailable.details.live_networks as unknown[]).map(String)
    : []
  const stepIndex = STEPS.indexOf(step)
  const prevStep = stepIndex > 0 ? STEPS[stepIndex - 1]! : null
  const nextStep = stepIndex < STEPS.length - 1 ? STEPS[stepIndex + 1]! : null
  const crisisLabel = !spec
    ? 'Not chosen yet'
    : presetRecord && !edited
      ? (presetRecord.name ?? presetRecord.spec.name)
      : spec.name || spec.id
  const snaps = network?.snapshots ?? null
  const durationH = spec && snaps?.resolution_h != null ? spec.horizon.snapshots * snaps.resolution_h : null

  const setEvent = (i: number, e: StormEvent) =>
    update((s) => ({ ...s, events: s.events.map((x, j) => (j === i ? e : x)) }))

  let content: ReactNode
  if (step === 'grid') {
    content = <GridStep networks={netList} value={networkId} policy={policy} onPick={pickNetwork} />
  } else if (step === 'crisis') {
    const types = assets.data ? availableEventTypes(assets.data) : []
    const effectiveAddType = types.includes(addType) ? addType : (types[0] ?? 'demand_multiplier')
    content = (
      <div className="flex flex-col gap-3">
        <Panel
          title={`2 · Choose crisis on ${network?.name ?? networkId}`}
          description="Start from a curated preset for this grid, a saved scenario, or build custom events."
          actions={
            (presets.length > netPresets.length || saved.length > visibleSaved.length || showAllPresets) && (
              <button
                type="button"
                className="text-2xs font-semibold text-accent underline underline-offset-2"
                data-testid="show-all-presets"
                onClick={() => setShowAllPresets((v) => !v)}
              >
                {showAllPresets ? 'Current grid only' : 'All grids'}
              </button>
            )
          }
        >
          {scenarios.error ? (
            <ErrorState error={scenarios.error} title="Could not load scenarios" onRetry={() => void scenarios.refetch()} />
          ) : scenarios.isPending ? (
            <SkeletonBlock rows={4} label="Loading scenarios" />
          ) : (
            <div className="flex flex-col gap-3">
              <section aria-labelledby="presets-h" className="flex flex-col gap-1.5">
                <h3 id="presets-h" className="gs-label">
                  Presets ({visiblePresets.length})
                </h3>
                <ScenarioList
                  records={visiblePresets}
                  activeId={edited ? null : presetId}
                  onPick={pickPreset}
                  policy={policy}
                  empty="No presets for this grid."
                />
              </section>
              {visibleSaved.length > 0 && (
                <section aria-labelledby="saved-h" className="flex flex-col gap-1.5">
                  <h3 id="saved-h" className="gs-label">
                    Saved ({visibleSaved.length})
                  </h3>
                  <ScenarioList
                    records={visibleSaved}
                    activeId={edited ? null : presetId}
                    onPick={pickPreset}
                    policy={policy}
                    empty="None."
                  />
                </section>
              )}
              <section aria-labelledby="custom-h" className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
                <h3 id="custom-h" className="gs-label w-full">
                  Custom
                </h3>
                <Button size="sm" onClick={startCustom} data-testid="start-custom">
                  <Plus aria-hidden className="size-3.5" /> Start a custom scenario (no events)
                </Button>
                <span className="text-2xs text-fg-muted">
                  The grid as-is; add outages, demand or weather events below.
                  {liveExecution === false && ' Custom scenarios cannot run on this grid here.'}
                </span>
              </section>
            </div>
          )}
        </Panel>

        {spec && (
          <Panel
            title={`Custom events (${spec.events.length})`}
            description={
              presetRecord && !edited
                ? `Events of preset ${presetRecord.id}. Editing them creates a custom scenario.`
                : 'Events applied on top of the grid over the horizon.'
            }
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
        )}
      </div>
    )
  } else if (step === 'review' && spec) {
    content = (
      <div className="flex flex-col gap-3">
        <Panel title="3 · Review settings" description="Identity, horizon and mitigation options of this scenario.">
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField
              label="Scenario id"
              value={spec.id}
              testId="scenario-id"
              hint="Lowercase letters, digits, hyphens; 3–64 chars."
              onChange={(id) => update((s) => ({ ...s, id }))}
            />
            <TextField label="Name" value={spec.name} testId="scenario-name" onChange={(name) => update((s) => ({ ...s, name }))} />
            <TextField
              className="sm:col-span-2"
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
              ? `Grid has ${snaps.count} snapshots × ${formatQuantity(snaps.resolution_h, 'h')} (${formatTimestamp(snaps.start)} → ${formatTimestamp(snaps.end)}).`
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
        <Panel title="Mitigation">
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
          </div>
        </Panel>
        <details className="gs-panel p-4 text-xs" data-testid="advanced-settings">
          <summary className="cursor-pointer text-sm font-semibold">Advanced: solver & execution</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
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
                ['Deterministic', spec.execution.deterministic ? `yes · seed ${spec.execution.seed ?? 0}` : 'no'],
              ]}
            />
          </div>
        </details>
      </div>
    )
  } else if (spec) {
    content = (
      <div className="flex flex-col gap-3">
        <Panel title="4 · Run" description="Validated by the backend against the dataset on every change.">
          <div className="flex flex-col gap-3">
            {validation.error && !runReport ? (
              <ErrorState error={validation.error} title="Validation request failed" onRetry={() => void validation.refetch()} />
            ) : (
              <ValidationMessages report={shownReport} local={local} pending={validating && !runReport} />
            )}
            <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="execution-forecast" data-availability={avail}>
              <span className="font-semibold">Execution:</span>
              <AvailabilityBadge value={avail} />
              <span className="text-fg-muted">
                {avail === 'live'
                  ? 'The backend solves this scenario now (execution mode: live).'
                  : avail === 'precomputed'
                    ? 'This exact scenario matches a verified precomputed result; the server returns it (execution mode: precomputed).'
                    : avail === 'unavailable'
                      ? 'This scenario cannot run here: no live solve on this grid and no verified result for this exact scenario.'
                      : 'Checking for a matching verified precomputed result…'}
              </span>
            </div>
            {simArtifacts.error && avail === 'checking' && (
              <ErrorState error={simArtifacts.error} title="Could not load the precomputed result index" onRetry={() => void simArtifacts.refetch()} />
            )}
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                onClick={() => run.mutate(spec)}
                disabled={blockReason !== null}
                aria-describedby={blockReason ? 'run-block-reason' : undefined}
                data-testid="run-scenario"
              >
                <Play aria-hidden className="size-4" />
                {run.isPending ? 'Submitting…' : avail === 'precomputed' ? 'Open verified result' : 'Run simulation'}
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
                    resetMutations()
                  }}
                >
                  <RotateCcw aria-hidden className="size-4" /> Discard edits
                </Button>
              )}
            </div>
            {blockReason && !run.isPending && (
              <p id="run-block-reason" className="text-xs text-fg-muted" data-testid="run-block-reason">
                {blockReason}
              </p>
            )}
            {alternatives.length > 0 && (
              <div data-testid="unavailable-guidance" role="status" className="rounded-lg border border-warn/40 bg-warn-soft p-3 text-xs text-fg">
                <p className="font-semibold">This scenario is not available for execution on the hosted demo.</p>
                <p className="mt-1 text-fg-muted">Your edits are still valid to save. Runnable alternatives:</p>
                <ul className="mt-1 flex flex-col gap-1">
                  {alternatives.map((a) => (
                    <li key={a.to}>
                      <Link className="font-semibold text-accent underline underline-offset-2" to={a.to} reloadDocument>
                        {a.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {liveUnavailable ? (
              <div role="alert" className="rounded border border-warn/50 bg-warn-soft p-3 text-sm" data-testid="live-unavailable">
                <p className="font-semibold">Run refused: live execution unavailable</p>
                <p className="text-xs text-fg">{liveUnavailable.message}</p>
                {liveNetworksFromError.length > 0 && (
                  <p className="mt-1 text-xs text-fg-muted">
                    Networks solved live on this deployment:{' '}
                    <span className="font-mono">{liveNetworksFromError.join(', ')}</span>
                  </p>
                )}
                <p className="mt-1 font-mono text-2xs text-fg-muted">
                  HTTP {liveUnavailable.status} · {liveUnavailable.code}
                </p>
              </div>
            ) : (
              run.error && !runReport && <ErrorState error={run.error} title="Submission failed" />
            )}
            {save.error && <ErrorState error={save.error} title="Save failed" />}
            {save.data && (
              <p role="status" className="text-xs text-ok" data-testid="save-status">
                Saved as <code className="font-mono">{save.data.id}</code> (hash {shortHash(save.data.hash)}).
                {save.data.listed === false && (
                  <>
                    {' '}
                    Unlisted: it is not shown in the scenario list; reopen it via{' '}
                    <Link to={`/studio?preset=${encodeURIComponent(save.data.id)}`} className="underline" data-testid="saved-link">
                      this link
                    </Link>
                    .
                  </>
                )}
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
    )
  }

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-3 p-3 md:p-4">
      <PageHeader
        title="Crisis Studio"
        subtitle="Choose a grid, choose a crisis, review the settings and run it on the backend."
        badges={
          presetRecord && !edited ? (
            <Badge tone="info">preset {presetRecord.id}</Badge>
          ) : edited ? (
            <Badge tone="accent">custom scenario</Badge>
          ) : null
        }
      />
      <Stepper current={step} open={(s) => canEnter(s, flowState)} onGo={setRequestedStep} />
      {liveExecution === false && network && (
        <div role="status" className="gs-panel border-warn/50 p-3 text-sm" data-testid="live-execution-notice">
          <h2 className="font-semibold">Live solves disabled for {network.id} on this deployment</h2>
          <p className="text-xs">
            This backend runs live solves only for grids within its memory budget
            {liveNetworks.length > 0 && (
              <>
                {' '}
                (<span className="font-mono">{liveNetworks.join(', ')}</span>)
              </>
            )}
            . For this grid a run is served only when a verified precomputed result exists for the exact scenario,
            matched by its StormSpec hash; anything else is stopped here before submission.
          </p>
          {policy.precomputed && (
            <p className="mt-1 text-xs text-fg-muted">
              {runnablePresets.length} of {netPresets.length} presets for this grid have a precomputed result.
            </p>
          )}
        </div>
      )}
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex min-w-0 flex-col gap-3">{content}</div>
        <aside aria-label="Scenario summary" className="flex min-w-0 flex-col gap-3 lg:sticky lg:top-3 lg:self-start">
          <Panel title="Your scenario">
            <dl className="flex flex-col gap-2" data-testid="scenario-summary">
              <SummaryRow label="Grid">{network ? `${network.name} (${network.id})` : 'Not chosen yet'}</SummaryRow>
              <SummaryRow label="Crisis">
                {crisisLabel}
                {spec && <span className="text-fg-muted"> · {spec.events.length} events</span>}
              </SummaryRow>
              {spec && (
                <SummaryRow label="Horizon">
                  {spec.horizon.snapshots} snapshots from #{spec.horizon.start ?? 0} ({formatQuantity(durationH, 'h')})
                </SummaryRow>
              )}
              {spec && (
                <SummaryRow label="Validation">
                  <span data-testid="validation-summary">
                    {local.length > 0 || report?.valid === false
                      ? `${local.length + (report?.errors.length ?? 0)} error(s) — see step 4`
                      : validating || !report
                        ? 'checking…'
                        : `valid${report.warnings.length ? ` · ${report.warnings.length} warning(s)` : ''}`}
                  </span>
                </SummaryRow>
              )}
              {networkId && (
                <SummaryRow label="Execution">
                  <AvailabilityBadge value={crisisChosen ? avail : policy.live.get(networkId) === true ? 'live' : 'checking'} />
                </SummaryRow>
              )}
            </dl>
            <div className="mt-3 flex items-center justify-between gap-2">
              {prevStep ? (
                <Button size="sm" variant="ghost" onClick={() => setRequestedStep(prevStep)} data-testid="step-back">
                  <ArrowLeft aria-hidden className="size-3.5" /> Back
                </Button>
              ) : (
                <span />
              )}
              {nextStep && (
                <Button
                  size="sm"
                  variant="primary"
                  disabled={!canEnter(nextStep, flowState)}
                  onClick={() => setRequestedStep(nextStep)}
                  data-testid="step-next"
                >
                  {STEP_LABEL[nextStep]} <ArrowRight aria-hidden className="size-3.5" />
                </Button>
              )}
            </div>
            {nextStep && !canEnter(nextStep, flowState) && (
              <p className="mt-1 text-2xs text-fg-muted">
                {nextStep === 'crisis' ? 'Choose a grid to continue.' : 'Choose a crisis to continue.'}
              </p>
            )}
          </Panel>
        </aside>
      </div>
    </div>
  )
}
