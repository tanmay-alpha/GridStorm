import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Compass, Play, X } from 'lucide-react'
import { useAssetTable } from '../../api/hooks'
import type { StormSpec } from '../../api/stormspec'
import type { CanonicalGenerator, NetworkSummary } from '../../api/types'
import { Button, ErrorState, SkeletonBlock, type ExecutionAvailability } from '../../components/ui'
import { formatNumber, formatQuantity } from '../../lib/format'
import { formatPrice, resolveCostBasis } from '../../lib/money'
import { investigationQuestion } from './presentation'

const GUIDE_STEPS = ['Run the crisis in Studio', 'Read the impact brief', 'Compare with the baseline'] as const

/** Plain-language description of generator outages, from the network's generator table. */
function GeneratorOutages({ ids, generators, peakLoadMw }: { ids: string[]; generators: CanonicalGenerator[]; peakLoadMw: number | null }) {
  const out = new Set(ids)
  const failing = generators.filter((g) => out.has(g.id))
  const others = generators.filter((g) => !out.has(g.id))
  const remaining = others.reduce((sum, g) => sum + (g.p_nom_mw ?? 0), 0)
  const unknownCapacity = others.some((g) => g.p_nom_mw === null)
  const byCapacity = [...generators].sort((a, b) => (b.p_nom_mw ?? -1) - (a.p_nom_mw ?? -1))
  return (
    <>
      {failing.map((g) => (
        <p key={g.id} data-testid="guide-failing-asset" data-asset-id={g.id}>
          <span className="font-semibold">What fails:</span> generator <code className="font-mono">{g.id}</code> at bus{' '}
          <code className="font-mono">{g.bus}</code>
          {g.carrier && <> (carrier {g.carrier})</>} with an installed capacity of{' '}
          <span className="tabular font-semibold">{formatQuantity(g.p_nom_mw, 'MW')}</span>
          {byCapacity[0]?.id === g.id && generators.length > 1 && <> — the largest of the {generators.length} generators on this grid</>}
          . It is switched off for the whole simulated horizon.
        </p>
      ))}
      {failing.length < ids.length && (
        <p className="text-warn">
          Not found in the generator table: {ids.filter((id) => !failing.some((g) => g.id === id)).join(', ')}.
        </p>
      )}
      <p data-testid="guide-remaining">
        <span className="font-semibold">What remains:</span> the other {others.length} generator{others.length === 1 ? '' : 's'} have{' '}
        <span className="tabular font-semibold">{formatQuantity(remaining, 'MW')}</span> of installed capacity combined
        {unknownCapacity && ' (some capacities are not reported)'}
        {peakLoadMw != null && (
          <>
            , against a peak load of <span className="tabular font-semibold">{formatQuantity(peakLoadMw, 'MW')}</span>
          </>
        )}
        . Values are read from the dataset.
      </p>
    </>
  )
}

/**
 * Guided demo, stage 1 (Studio): explains which asset fails and which question the run answers,
 * then runs it (or opens its verified result). Later stages are rendered on the run/compare pages.
 */
export function GuidePanel({
  spec,
  network,
  availability,
  runDisabledReason,
  submitting,
  onRun,
  exitTo,
  children,
}: {
  spec: StormSpec
  network: NetworkSummary | null
  availability: ExecutionAvailability
  runDisabledReason: string | null
  submitting: boolean
  onRun: () => void
  exitTo: string
  /** Submission feedback (errors) shown under the Run button. */
  children?: ReactNode
}) {
  const outageIds = spec.events.filter((e) => e.type === 'generator_outage').map((e) => e.asset_id)
  const generators = useAssetTable(spec.dataset.network_id, 'generators', outageIds.length > 0)
  const basis = resolveCostBasis(network)
  const voll = spec.mitigation.load_shedding
  return (
    <section
      aria-labelledby="guide-title"
      data-testid="guide-panel"
      className="gs-panel flex flex-col gap-3 border-accent/50 p-4"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="gs-label flex items-center gap-1.5 text-accent">
            <Compass aria-hidden className="size-3.5" /> Guided demo · step 1 of {GUIDE_STEPS.length}
          </p>
          <h2 id="guide-title" className="mt-1 text-base font-semibold text-fg">
            {spec.name}
          </h2>
        </div>
        <Link
          to={exitTo}
          className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded px-2 text-xs text-fg-muted hover:bg-surface-2 hover:text-fg"
          data-testid="guide-exit"
        >
          <X aria-hidden className="size-3.5" /> Exit guide
        </Link>
      </div>
      <ol className="flex flex-wrap gap-x-4 gap-y-1 text-2xs text-fg-muted" aria-label="Guided demo steps">
        {GUIDE_STEPS.map((s, i) => (
          <li key={s} className={i === 0 ? 'font-semibold text-fg' : undefined} aria-current={i === 0 ? 'step' : undefined}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>
      <div className="flex flex-col gap-2 text-sm leading-relaxed text-fg">
        {outageIds.length > 0 &&
          (generators.error ? (
            <ErrorState error={generators.error} title="Could not load the generator table" onRetry={() => void generators.refetch()} />
          ) : !generators.data ? (
            <SkeletonBlock rows={2} label="Loading generator data" />
          ) : (
            <GeneratorOutages ids={outageIds} generators={generators.data} peakLoadMw={network?.peak_load_mw ?? null} />
          ))}
        <p data-testid="guide-question">
          <span className="font-semibold">Question:</span> {investigationQuestion(spec)}
        </p>
        {voll.enabled && (
          <p className="text-xs text-fg-muted">
            If supply falls short, the optimisation sheds load at the value-of-lost-load penalty (
            <span className="tabular">{formatPrice(voll.voll_eur_per_mwh, basis)}</span>) and reports the unserved energy.
            The penalty is a modelling parameter, not an estimate of economic damage.
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <Button
          variant="primary"
          onClick={onRun}
          disabled={runDisabledReason !== null}
          aria-describedby={runDisabledReason ? 'guide-run-reason' : undefined}
          data-testid="guide-run"
        >
          <Play aria-hidden className="size-4" />
          {submitting ? 'Submitting…' : availability === 'precomputed' ? 'Open the verified result' : 'Run this crisis'}
        </Button>
        <span id="guide-run-reason" className="text-xs text-fg-muted">
          {runDisabledReason ??
            (availability === 'precomputed'
              ? 'Returns the stored, verified result for this exact scenario.'
              : `Solved live by the backend for ${network?.name ?? spec.dataset.network_id}; you will land on the result page.`)}
        </span>
      </div>
      {children}
      {network && (
        <p className="text-2xs text-fg-subtle">
          {network.name}: {formatNumber(network.counts.buses ?? null)} buses, {formatNumber(network.counts.generators ?? null)} generators
          {network.coordinate_kind === 'schematic' ? ' · schematic layout, not geographic' : ''} · research use only.
        </p>
      )}
    </section>
  )
}
