import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, History, Play, Plus, RotateCcw, Save, Sparkles } from 'lucide-react'
import { ApiError, api } from '../../api/client'
import { qk, useNetwork, useNetworkAssets, useNetworks, useScenario, useScenarios } from '../../api/hooks'
import { LIMITS, type EventType, type StormEvent, type StormSpec } from '../../api/stormspec'
import type { ScenarioRecord, ValidationIssue, ValidationReport } from '../../api/types'
import {
  Badge,
  Button,
  CheckboxField,
  CostBasisBadge,
  Disclosure,
  EmptyState,
  ErrorState,
  ExecutionBadge,
  KeyValue,
  LoadingState,
  Modal,
  NumberField,
  PageHeader,
  Panel,
  ScientificNotice,
  SkeletonBlock,
  TextField,
  type ExecutionAvailability,
} from '../../components/ui'
import { formatQuantity, formatTimestamp, shortHash } from '../../lib/format'
import { isRecord } from '../../lib/guards'
import { priceUnit, resolveCostBasis } from '../../lib/money'
import { clearDraft, draftMatches, loadDraft, storeDraft, type StudioDraft } from './draft'
import { EventEditor } from './EventEditor'
import {
  GUIDED_DEMO,
  STEPS,
  STEP_LABEL,
  availability,
  canEnter,
  effectiveStep,
  initialStep,
  recommendedNetwork,
  recommendedPreset,
  recordNetwork,
  runBlockReason,
  runnableAlternatives,
  type Step,
} from './flow'
import { GridStep } from './GridStep'
import { GuidePanel } from './GuidePanel'
import { PresetList } from './PresetList'
import { crisisLabel, plural } from './presentation'
import { EVENT_LABEL, availableEventTypes, blankSpec, localIssues, newEvent, normaliseSpec } from './spec'
import { Stepper } from './Stepper'
import { useDebounced } from './useDebounced'
import { useExecutionPolicy } from './useExecutionPolicy'
import { RunError } from './RunError'
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

/** Messages of the issues at `path` or below it (`path.x`, `path[0]`), for a field-level error. */
function issuesAt(issues: ValidationIssue[], ...paths: string[]): string | undefined {
  const hits = issues.filter((i) => paths.some((p) => i.path === p || i.path.startsWith(`${p}.`) || i.path.startsWith(`${p}[`)))
  return hits.length ? hits.map((i) => i.message).join(' ') : undefined
}

const FORECAST_TEXT: Record<ExecutionAvailability, string> = {
  live: 'The backend solves this scenario now (execution mode: live).',
  precomputed:
    'This exact scenario matches a verified precomputed result; the server returns it (execution mode: precomputed).',
  unavailable: 'This scenario cannot run here: no live solve on this grid and no verified result for this exact scenario.',
  checking: 'Checking for a matching verified precomputed result…',
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
  const guide = params.get('guide') === '1'
  const presetId = params.get('preset')
  const requestedNet = params.get('network')

  // Unsaved edits from an earlier visit: reopened automatically when the URL opens the same
  // scenario (not in the guided demo, which always shows the curated preset), otherwise offered.
  const [savedDraft, setSavedDraft] = useState<StudioDraft | null>(loadDraft)
  const [edited, setEdited] = useState<StormSpec | null>(() =>
    !guide && savedDraft && draftMatches(savedDraft, requestedNet, presetId) ? savedDraft.spec : null,
  )
  const [restoredAt, setRestoredAt] = useState<string | null>(() => (edited ? (savedDraft?.savedAt ?? null) : null))
  const [addType, setAddType] = useState<EventType>('line_outage')
  const [showAllPresets, setShowAllPresets] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [requestedStep, setRequestedStep] = useState<Step>(() => initialStep(requestedNet, presetId))
  const contentRef = useRef<HTMLDivElement>(null)
  const focusContent = useRef(false)

  const records = useMemo(() => scenarios.data ?? [], [scenarios.data])
  const listedRecord = presetId ? (records.find((r) => r.id === presetId) ?? null) : null
  // Unlisted (anonymous) saves are not in the list but can be opened by id via ?preset=<id>.
  const unlisted = useScenario(presetId, scenarios.isSuccess && !listedRecord)
  const presetRecord = listedRecord ?? unlisted.data ?? null
  const netList = useMemo(() => networks.data ?? [], [networks.data])

  // Current spec: user edits, else the selected preset/saved scenario. No crisis chosen yet: no spec.
  const spec: StormSpec | null = edited ?? (presetRecord ? normaliseSpec(presetRecord.spec) : null)
  const networkId =
    spec?.dataset.network_id ?? (requestedNet && netList.some((n) => n.id === requestedNet) ? requestedNet : null)
  const network = netList.find((n) => n.id === networkId) ?? null
  const crisisChosen = spec !== null
  const flowState = { networkId, crisisChosen }
  const step = effectiveStep(requestedStep, flowState)

  // Move focus to the new step's content after a step change made by the user (keyboard users
  // otherwise stay on the button they pressed, far from the new content).
  useEffect(() => {
    if (!focusContent.current) return
    focusContent.current = false
    contentRef.current?.focus()
  }, [step])
  const goTo = (s: Step) => {
    focusContent.current = true
    setRequestedStep(s)
  }

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
      void navigate(`/runs/${encodeURIComponent(job.id)}${guide ? '?guide=1' : ''}`)
    },
  })
  const save = useMutation({
    mutationFn: (s: StormSpec) => api.saveScenario(s),
    onSuccess: () => {
      clearDraft()
      setSavedDraft(null)
      void queryClient.invalidateQueries({ queryKey: qk.scenarios })
    },
  })

  const resetMutations = () => {
    run.reset()
    save.reset()
  }
  const setDraft = (next: StormSpec) => {
    const d: StudioDraft = { spec: next, basedOn: presetId, savedAt: new Date().toISOString() }
    storeDraft(d)
    setSavedDraft(d)
    setEdited(next)
    setRestoredAt(null)
    resetMutations()
  }
  const update = (fn: (s: StormSpec) => StormSpec) => {
    if (spec) setDraft(fn(spec))
  }
  const discardEdits = () => {
    clearDraft()
    setSavedDraft(null)
    setEdited(null)
    setRestoredAt(null)
    resetMutations()
  }
  const restoreDraft = (d: StudioDraft) => {
    setEdited(d.spec)
    setRestoredAt(d.savedAt)
    resetMutations()
    setParams((p) => {
      const q = new URLSearchParams(p)
      q.set('network', d.spec.dataset.network_id)
      if (d.basedOn) q.set('preset', d.basedOn)
      else q.delete('preset')
      return q
    })
    goTo('review')
  }
  const pickNetwork = (id: string, advance: boolean) => {
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
    if (advance) goTo('crisis')
  }
  /** `guided`: open the preset in the guided demo (guide=1), as the Home CTA does. */
  const pickPreset = (r: ScenarioRecord, next?: Step, guided = false) => {
    setEdited(null)
    setRestoredAt(null)
    resetMutations()
    setParams((p) => {
      const q = new URLSearchParams(p)
      q.set('preset', r.id)
      q.set('network', recordNetwork(r))
      if (guided) q.set('guide', '1')
      return q
    })
    if (next) goTo(next)
  }
  const startCustom = () => {
    if (!network) return
    setParams((p) => {
      const q = new URLSearchParams(p)
      q.delete('preset')
      q.set('network', network.id)
      return q
    })
    const d: StudioDraft = { spec: blankSpec(network), basedOn: null, savedAt: new Date().toISOString() }
    storeDraft(d)
    setSavedDraft(d)
    setEdited(d.spec)
    setRestoredAt(null)
    resetMutations()
  }

  if (networks.error)
    return (
      <div className="p-4">
        <ErrorState error={networks.error} title="Could not load networks" onRetry={() => void networks.refetch()} />
      </div>
    )
  if (networks.isPending)
    return (
      <div className="mx-auto max-w-[1500px] p-4">
        <LoadingState label="Loading Crisis Studio" rows={8} />
      </div>
    )
  if (netList.length === 0)
    return <EmptyState title="No networks available">Scenarios need a network dataset in the backend catalog.</EmptyState>

  const local = spec ? localIssues(spec) : []
  const runReport = reportFromError(run.error)
  const shownReport = runReport ?? report
  const allErrors = [...local, ...(shownReport?.errors ?? [])]
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
  const avail: ExecutionAvailability = networkId ? availability(policy, networkId, currentHash) : 'checking'
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
  const stepIndex = STEPS.indexOf(step)
  const prevStep = stepIndex > 0 ? STEPS[stepIndex - 1]! : null
  const nextStep = stepIndex < STEPS.length - 1 ? STEPS[stepIndex + 1]! : null
  const crisisName = crisisLabel(spec, presetRecord, edited !== null)
  const snaps = network?.snapshots ?? null
  const durationH = spec && snaps?.resolution_h != null ? spec.horizon.snapshots * snaps.resolution_h : null
  const costBasis = resolveCostBasis(networkDetail.data, network)
  const recNetwork = recommendedNetwork(netList, records)
  const recPreset = networkId ? recommendedPreset(networkId, records, policy) : null
  const quickStart = recNetwork ? recommendedPreset(recNetwork.id, records, policy) : null
  const otherDraft = !edited && savedDraft ? savedDraft : null
  const errorsIn = (s: Step) => allErrors.filter((i) => (i.path.startsWith('events') ? 'crisis' : 'review') === s)
  const exitGuide = (() => {
    const q = new URLSearchParams(params)
    q.delete('guide')
    return `/studio?${q.toString()}`
  })()

  const setEvent = (i: number, e: StormEvent) =>
    update((s) => ({ ...s, events: s.events.map((x, j) => (j === i ? e : x)) }))

  let content: ReactNode
  if (step === 'grid' && scenarios.isPending) {
    // The suggestion and the recommended grid both depend on the scenario list; rendering the grid
    // list before it arrives pushed it down by the suggestion panel (CLS 0.05 on every visit).
    content = <LoadingState label="Loading grids and example crises" rows={6} />
  } else if (step === 'grid') {
    content = (
      <div className="flex flex-col gap-3">
        {quickStart && recNetwork && (
          <div className="gs-panel flex flex-wrap items-center justify-between gap-3 p-4" data-testid="quick-start">
            <div className="min-w-0">
              <p className="gs-label">Not sure where to start?</p>
              <p className="text-sm text-fg">
                <span className="font-semibold">{quickStart.name ?? quickStart.spec.name}</span>{' '}
                <span className="text-fg-muted">on {recNetwork.name}, a small grid that is solved live here.</span>
              </p>
            </div>
            <Button
              variant="primary"
              onClick={() => pickPreset(quickStart, 'review', quickStart.id === GUIDED_DEMO.preset)}
              data-testid="quick-start-button"
            >
              <Sparkles aria-hidden className="size-4" /> Use this scenario
            </Button>
          </div>
        )}
        <GridStep
          networks={netList}
          value={networkId}
          recommendedId={recNetwork?.id ?? null}
          policy={policy}
          onPick={pickNetwork}
        />
      </div>
    )
  } else if (step === 'crisis') {
    const types = assets.data ? availableEventTypes(assets.data) : []
    const effectiveAddType = types.includes(addType) ? addType : (types[0] ?? 'demand_multiplier')
    const eventErrors = errorsIn('crisis')
    content = (
      <div className="flex flex-col gap-3">
        <Panel
          title={`2 · Choose crisis on ${network?.name ?? networkId}`}
          description="Start from a curated preset, a saved scenario, or build custom events. Open “Details & ids” for full traceability."
          actions={
            (presets.length > netPresets.length || saved.length > visibleSaved.length || showAllPresets) && (
              <Button size="sm" variant="ghost" data-testid="show-all-presets" onClick={() => setShowAllPresets((v) => !v)}>
                {showAllPresets ? 'Current grid only' : 'All grids'}
              </Button>
            )
          }
        >
          {scenarios.error ? (
            <ErrorState error={scenarios.error} title="Could not load scenarios" onRetry={() => void scenarios.refetch()} />
          ) : scenarios.isPending ? (
            <LoadingState label="Loading scenarios" rows={4} />
          ) : (
            <div className="flex flex-col gap-4">
              <section aria-labelledby="presets-h" className="flex flex-col gap-2">
                <h3 id="presets-h" className="gs-label">
                  Presets ({visiblePresets.length})
                </h3>
                <PresetList
                  records={visiblePresets}
                  activeId={edited ? null : presetId}
                  recommendedId={recPreset?.id ?? null}
                  onPick={(r) => pickPreset(r)}
                  policy={policy}
                  networks={netList}
                  empty="No presets for this grid."
                />
              </section>
              {visibleSaved.length > 0 && (
                <section aria-labelledby="saved-h" className="flex flex-col gap-2">
                  <h3 id="saved-h" className="gs-label">
                    Saved ({visibleSaved.length})
                  </h3>
                  <PresetList
                    records={visibleSaved}
                    activeId={edited ? null : presetId}
                    recommendedId={null}
                    onPick={(r) => pickPreset(r)}
                    policy={policy}
                    networks={netList}
                    empty="None."
                  />
                </section>
              )}
              <section aria-labelledby="custom-h" className="flex flex-col gap-2 border-t border-line pt-3">
                <h3 id="custom-h" className="gs-label">
                  Custom
                </h3>
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" onClick={startCustom} data-testid="start-custom">
                    <Plus aria-hidden className="size-3.5" /> Start a custom scenario (no events)
                  </Button>
                  <span className="text-2xs text-fg-muted">
                    The grid as-is; add outages, demand or weather events below.
                    {liveExecution === false && ' Custom scenarios cannot run on this grid here.'}
                  </span>
                </div>
              </section>
            </div>
          )}
        </Panel>

        {spec && (
          <Panel
            title={`Events (${spec.events.length})`}
            description={
              presetRecord && !edited
                ? `Events of “${presetRecord.name ?? presetRecord.spec.name}”. Editing them creates a custom scenario.`
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
                    className="gs-input h-8 min-h-0 max-w-[10rem] py-0 text-xs sm:max-w-none"
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
            {eventErrors.length > 0 && (
              <div className="mb-3">
                <ValidationMessages report={null} local={eventErrors} pending={false} />
              </div>
            )}
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
                    issues={eventErrors}
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
    const execError = issuesAt(allErrors, 'execution')
    content = (
      <div className="flex flex-col gap-3">
        <Panel title="3 · Review settings" description="Name, horizon and mitigation options of this scenario.">
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField
              label="Name"
              value={spec.name}
              testId="scenario-name"
              error={issuesAt(allErrors, 'name')}
              onChange={(name) => update((s) => ({ ...s, name }))}
            />
            <TextField
              label="Scenario id"
              value={spec.id}
              testId="scenario-id"
              hint="Lowercase letters, digits, hyphens; 3–64 characters. Identifies saved scenarios and results."
              error={issuesAt(allErrors, 'id')}
              onChange={(id) => update((s) => ({ ...s, id }))}
            />
            <TextField
              className="sm:col-span-2"
              label="Description"
              value={spec.description ?? ''}
              error={issuesAt(allErrors, 'description')}
              onChange={(description) => update((s) => ({ ...s, description }))}
            />
          </div>
        </Panel>
        <Panel
          title="Horizon"
          description={
            snaps
              ? `Grid has ${plural(snaps.count, 'snapshot')} × ${formatQuantity(snaps.resolution_h, 'h')} (${formatTimestamp(snaps.start)} → ${formatTimestamp(snaps.end)}).`
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
              error={issuesAt(allErrors, 'horizon.start')}
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
              error={issuesAt(
                allErrors.filter((i) => i.path !== 'horizon.start'),
                'horizon',
              )}
              onChange={(v) => update((s) => ({ ...s, horizon: { ...s.horizon, snapshots: v ?? 0 } }))}
            />
            <div className="flex flex-col justify-end text-xs text-fg-muted">
              Duration: <span className="tabular font-semibold text-fg">{formatQuantity(durationH, 'h')}</span>
            </div>
          </div>
        </Panel>
        <Panel title="Mitigation" actions={<CostBasisBadge basis={costBasis} testId="studio-cost-basis" />}>
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
                hint="Adds load-shedding generators at the value of lost load."
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
              unit={priceUnit(costBasis)}
              min={0}
              max={LIMITS.vollEurPerMwh.max}
              value={spec.mitigation.load_shedding.voll_eur_per_mwh}
              testId="voll"
              hint="Penalty per MWh of unserved energy, in the dataset's money unit. A modelling parameter, not an estimate of economic damage."
              error={issuesAt(allErrors, 'mitigation.load_shedding')}
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
        <Disclosure
          testId="advanced-settings"
          summary={
            <>
              Advanced: solver & execution
              {execError && <Badge tone="danger">error</Badge>}
            </>
          }
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <NumberField
              label="Solver time limit"
              unit="s"
              min={1}
              max={LIMITS.timeLimitS.max}
              value={spec.execution.solver_options?.time_limit_s ?? null}
              testId="time-limit"
              error={execError}
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
        </Disclosure>
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
              <ValidationMessages report={shownReport} local={local} pending={validating && !runReport} onGoToStep={goTo} />
            )}
            <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="execution-forecast" data-availability={avail}>
              <span className="font-semibold">Execution:</span>
              <ExecutionBadge value={avail} />
              <span className="text-fg-muted">{FORECAST_TEXT[avail]}</span>
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
                <Button variant="ghost" onClick={() => setConfirmDiscard(true)} data-testid="discard-edits">
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
            <RunError error={run.error} onRetry={() => run.mutate(spec)} />
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
        <Disclosure summary="StormSpec JSON (exact submitted scenario)">
          <pre className="max-h-80 overflow-auto font-mono text-2xs text-fg-muted" data-testid="spec-json">
            {JSON.stringify(spec, null, 2)}
          </pre>
        </Disclosure>
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
            <Badge tone="info">preset</Badge>
          ) : edited ? (
            <Badge tone="accent">custom scenario</Badge>
          ) : null
        }
      />
      <Stepper current={step} open={(s) => canEnter(s, flowState)} onGo={goTo} />
      {guide && spec && presetRecord && !edited && (
        <GuidePanel
          spec={spec}
          network={network}
          availability={avail}
          runDisabledReason={blockReason}
          submitting={run.isPending}
          onRun={() => run.mutate(spec)}
          exitTo={exitGuide}
        >
          {step !== 'run' && <RunError error={run.error} onRetry={() => run.mutate(spec)} />}
        </GuidePanel>
      )}
      {guide && edited && (
        <ScientificNotice kind="limitation" title="The guided demo explains the unchanged preset." testId="guide-edited">
          <p>
            You changed this scenario, so the guide is paused.{' '}
            <button type="button" className="font-semibold text-accent underline underline-offset-2" onClick={() => setConfirmDiscard(true)}>
              Discard edits
            </button>{' '}
            to return to it, or <Link className="font-semibold text-accent underline underline-offset-2" to={exitGuide}>exit the guide</Link>.
          </p>
        </ScientificNotice>
      )}
      {presetId && !presetRecord && unlisted.error && (
        <ErrorState error={unlisted.error} title={`Scenario “${presetId}” could not be opened`} onRetry={() => void unlisted.refetch()} />
      )}
      {restoredAt && edited && (
        <div role="status" className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs" data-testid="draft-restored">
          <History aria-hidden className="size-4 text-fg-muted" />
          <span>
            Restored your unsaved edits from {formatTimestamp(restoredAt)} (kept in this browser).
          </span>
          <Button size="sm" variant="ghost" onClick={() => setConfirmDiscard(true)}>
            Discard
          </Button>
        </div>
      )}
      {otherDraft && !guide && (
        <div role="status" className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs" data-testid="draft-available">
          <History aria-hidden className="size-4 text-fg-muted" />
          <span className="min-w-0 flex-1">
            Unsaved draft <span className="font-semibold">“{otherDraft.spec.name || otherDraft.spec.id}”</span> on{' '}
            <span className="font-mono">{otherDraft.spec.dataset.network_id}</span> from {formatTimestamp(otherDraft.savedAt)}.
          </span>
          <Button size="sm" onClick={() => restoreDraft(otherDraft)} data-testid="draft-restore">
            Restore
          </Button>
          <Button size="sm" variant="ghost" onClick={discardEdits} data-testid="draft-discard">
            Discard
          </Button>
        </div>
      )}
      {liveExecution === false && network && (
        <ScientificNotice kind="limitation" testId="live-execution-notice" title={`Live solves disabled for ${network.id} on this deployment`}>
          <p>
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
            <p>
              {runnablePresets.length} of {netPresets.length} presets for this grid have a precomputed result.
            </p>
          )}
        </ScientificNotice>
      )}
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex min-w-0 flex-col gap-3">
          <div
            ref={contentRef}
            tabIndex={-1}
            role="region"
            aria-label={`Step ${stepIndex + 1} of ${STEPS.length}: ${STEP_LABEL[step]}`}
            data-testid="step-content"
            className="flex min-w-0 flex-col gap-3 rounded-[10px] focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {content}
          </div>
          <div
            className="sticky bottom-0 z-10 -mx-3 flex items-center justify-between gap-2 border-t border-line bg-surface px-3 py-2 md:-mx-4 md:px-4 lg:static lg:mx-0 lg:rounded-[10px] lg:border lg:px-3"
            data-testid="step-nav"
          >
            {prevStep ? (
              <Button variant="ghost" onClick={() => goTo(prevStep)} data-testid="step-back">
                <ArrowLeft aria-hidden className="size-4" /> Back<span className="sr-only">: {STEP_LABEL[prevStep]}</span>
              </Button>
            ) : (
              <span />
            )}
            {nextStep && (
              <div className="flex min-w-0 items-center gap-2">
                {!canEnter(nextStep, flowState) && (
                  <span id="step-next-hint" className="min-w-0 text-right text-2xs text-fg-muted">
                    {nextStep === 'crisis' ? 'Choose a grid to continue.' : 'Choose a crisis to continue.'}
                  </span>
                )}
                <Button
                  variant="primary"
                  disabled={!canEnter(nextStep, flowState)}
                  aria-describedby={!canEnter(nextStep, flowState) ? 'step-next-hint' : undefined}
                  onClick={() => goTo(nextStep)}
                  data-testid="step-next"
                >
                  <span className="sr-only">Next: </span>
                  {STEP_LABEL[nextStep]} <ArrowRight aria-hidden className="size-4" />
                </Button>
              </div>
            )}
          </div>
        </div>
        <aside aria-label="Scenario summary" className="flex min-w-0 flex-col gap-3 lg:sticky lg:top-3 lg:self-start">
          <Panel title="Your scenario">
            <dl className="flex flex-col gap-2" data-testid="scenario-summary">
              <SummaryRow label="Grid">{network ? `${network.name} (${network.id})` : 'Not chosen yet'}</SummaryRow>
              <SummaryRow label="Crisis">
                {crisisName}
                {spec && <span className="text-fg-muted"> · {plural(spec.events.length, 'event')}</span>}
              </SummaryRow>
              {spec && (
                <SummaryRow label="Horizon">
                  {plural(spec.horizon.snapshots, 'snapshot')} from #{spec.horizon.start ?? 0} ({formatQuantity(durationH, 'h')})
                </SummaryRow>
              )}
              {spec && (
                <SummaryRow label="Validation">
                  <span data-testid="validation-summary">
                    {local.length > 0 || report?.valid === false
                      ? `${plural(local.length + (report?.errors.length ?? 0), 'error')} — see step 4`
                      : validating || !report
                        ? 'checking…'
                        : `valid${report.warnings.length ? ` · ${plural(report.warnings.length, 'warning')}` : ''}`}
                  </span>
                </SummaryRow>
              )}
              {networkId && (
                <SummaryRow label="Execution">
                  <ExecutionBadge value={crisisChosen ? avail : policy.live.get(networkId) === true ? 'live' : 'checking'} />
                </SummaryRow>
              )}
              {network && (
                <SummaryRow label="Cost basis">
                  <CostBasisBadge basis={costBasis} />
                </SummaryRow>
              )}
              {presetRecord && !edited && (
                <SummaryRow label="Scenario id · hash">
                  <span className="font-mono text-2xs text-fg-muted">
                    {presetRecord.id} · {shortHash(presetRecord.hash)}
                  </span>
                </SummaryRow>
              )}
            </dl>
          </Panel>
        </aside>
      </div>
      <Modal
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        title="Discard your edits?"
        description="The scenario returns to the selected preset (or to no crisis for a custom scenario). The unsaved draft in this browser is deleted."
        testId="discard-dialog"
        footer={
          <>
            <Button onClick={() => setConfirmDiscard(false)}>Keep editing</Button>
            <Button
              variant="danger"
              data-testid="confirm-discard"
              onClick={() => {
                discardEdits()
                setConfirmDiscard(false)
              }}
            >
              Discard edits
            </Button>
          </>
        }
      />
    </div>
  )
}
