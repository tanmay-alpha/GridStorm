import { useMemo } from 'react'
import { Link } from 'react-router'
import { BookOpen, ExternalLink, FlaskConical, LineChart, PlayCircle } from 'lucide-react'
import { useNetworks, useScenarios } from '../../api/hooks'
import type { DatasetEntry, ScenarioRecord } from '../../api/types'
import { Badge, buttonClass, ExecutionBadge, Panel, Skeleton } from '../../components/ui'
import { formatNumber } from '../../lib/format'
import { availability, baselinePreset, recordNetwork } from '../studio/flow'
import { useExecutionPolicy } from '../studio/useExecutionPolicy'
import { analogueFacts, indexUnservedMwh, stressLinks, type StressLink } from './analogues'
import { utcDateTime } from './vocabulary'
import { windowRange, type WorkspaceState } from './workspace'

const mwh = (v: number | null) =>
  v === null ? 'not in the artifact index' : `${v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MWh`
const studioUrl = (network: string, preset: string) => `/studio?network=${encodeURIComponent(network)}&preset=${encodeURIComponent(preset)}`

function WindowCard({
  link,
  record,
  networkName,
  unserved,
  baseline,
  execution,
  methodHref,
  onShow,
}: {
  link: StressLink
  /** undefined while loading; null when the preset is not served (request failed or unknown id). */
  record: ScenarioRecord | null | undefined
  networkName: string | null
  unserved: number | null
  baseline: { record: ScenarioRecord; unserved: number | null } | null
  execution: Parameters<typeof ExecutionBadge>[0]['value']
  methodHref: string | null
  onShow: (() => void) | null
}) {
  const facts = record ? analogueFacts(record.spec) : null
  const network = record ? recordNetwork(record) : null
  const net = networkName ?? network
  const headingId = `stress-${link.scenarioId}`
  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-lg border border-line p-3" aria-labelledby={headingId} data-testid="stress-window" data-scenario={link.scenarioId}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id={headingId} className="text-sm font-semibold text-fg">
            Stress day {link.day} <span className="font-normal text-fg-muted">(UTC)</span>
          </h3>
          <p className="text-2xs text-fg-muted">
            Published window “{link.window.label}”: <span className="tabular">{utcDateTime(link.window.start_utc)} → {utcDateTime(link.window.end_utc)}</span>
          </p>
        </div>
        <span className="flex flex-wrap items-center gap-1">
          <Badge tone="info">modeled</Badge>
          <ExecutionBadge value={execution} testId="stress-execution" />
        </span>
      </div>
      <p className="text-xs text-fg">
        <span className="text-fg-muted">StormSpec preset </span>
        <code className="break-all rounded bg-surface-2 px-1 py-0.5 font-mono text-2xs">{link.scenarioId}</code>
        {net && <span className="text-fg-muted"> on {net}</span>}
        {record?.spec.name && <span className="block text-fg-muted">{record.spec.name}</span>}
      </p>
      {record === undefined ? (
        <Skeleton className="h-16" />
      ) : record === null ? (
        <p className="text-xs text-fg-muted" data-testid="stress-preset-unavailable">
          This deployment does not serve the preset, so its derivation and result cannot be shown here.
        </p>
      ) : (
        <div className="flex flex-col gap-1">
          <h4 className="gs-label">How the scenario was derived (as stated by the preset)</h4>
          <ul className="flex list-disc flex-col gap-1 pl-4 text-xs text-fg-muted" data-testid="stress-derivation">
            {facts?.criterion && (
              <li>
                <span className="text-fg">Day selection:</span> {facts.criterion}.
              </li>
            )}
            {facts?.demand && (
              <li>
                <span className="text-fg">Demand:</span> hour h of the stress day (UTC) becomes snapshot h of {net} ({facts.snapshots ?? facts.demand.hours} snapshots).
                Every load follows the ENTSO-E day-ahead load forecast's shape and its level relative to{' '}
                {facts.referenceDay ? `the reference day ${facts.referenceDay}` : 'a 1 January reference day'}: hourly multipliers{' '}
                <span className="tabular text-fg">
                  {formatNumber(facts.demand.min, 4)}–{formatNumber(facts.demand.max, 4)}
                </span>
                .
              </li>
            )}
            <li>
              <span className="text-fg">Renewables:</span> one daily availability multiplier per carrier on the network's own hourly profile
              {facts && facts.renewables.length > 0 ? (
                <>
                  :{' '}
                  <span className="tabular text-fg">{facts.renewables.map((x) => `${x.carrier} × ${formatNumber(x.value, 2)}`).join(' · ')}</span>; other carriers keep the network's availability.
                </>
              ) : (
                '; no carrier is reduced in this preset.'
              )}
            </li>
            <li>
              <span className="text-fg">Stored PyPSA result (modeled):</span> unserved energy <span className="tabular font-medium text-fg" data-testid="stress-unserved">{mwh(unserved)}</span>
              {baseline && (
                <>
                  {' '}
                  vs. <span className="tabular">{mwh(baseline.unserved)}</span> in the baseline preset <code className="font-mono text-2xs">{baseline.record.id}</code>
                </>
              )}
              .
            </li>
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {network && (
          <Link to={studioUrl(network, link.scenarioId)} className={buttonClass('primary', 'sm')} data-testid="open-analogue-studio">
            <PlayCircle aria-hidden className="size-3.5" />
            Open scenario in Crisis Studio
          </Link>
        )}
        {methodHref && (
          <a href={methodHref} target="_blank" rel="noreferrer" className={buttonClass('secondary', 'sm')} data-testid="analogue-method">
            <BookOpen aria-hidden className="size-3.5" />
            Read the method
            <ExternalLink aria-hidden className="size-3 text-fg-subtle" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        )}
        {network && unserved !== null && (
          <Link
            to={`/workbench?network=${encodeURIComponent(network)}&study=pypsa-presets&artifact=${encodeURIComponent(link.scenarioId)}`}
            className={buttonClass('ghost', 'sm')}
            data-testid="analogue-workbench"
          >
            <FlaskConical aria-hidden className="size-3.5" />
            Inspect the stored result
          </Link>
        )}
        {onShow && (
          <button type="button" onClick={onShow} className={buttonClass('ghost', 'sm')} data-testid="show-stress-window">
            <LineChart aria-hidden className="size-3.5" />
            Show this window in the chart
          </button>
        )}
      </div>
    </li>
  )
}

function StressScenarioList({ d, links, onWindow }: { d: DatasetEntry; links: StressLink[]; onWindow: ((patch: Partial<WorkspaceState>) => void) | null }) {
  const scenarios = useScenarios()
  const networks = useNetworks()
  const { policy, simArtifacts } = useExecutionPolicy()
  const byId = useMemo(() => new Map((scenarios.data ?? []).map((s) => [s.id, s])), [scenarios.data])
  const networkIds = [...new Set(links.map((l) => byId.get(l.scenarioId)).filter((r): r is ScenarioRecord => !!r).map(recordNetwork))]
  const baselines = networkIds
    .map((n) => (scenarios.data ? baselinePreset(n, scenarios.data) : null))
    .filter((r): r is ScenarioRecord => !!r)
  const methodHref = d.links.docs.find((x) => x.href.includes('observed-analogue-scenarios'))?.href ?? null
  const nameOf = (id: string) => networks.data?.find((n) => n.id === id)?.name ?? null
  const seriesHere = d.series.length > 0 && !!d.artifact
  return (
    <Panel
      title="Stress windows → crisis scenarios"
      id="obs-stress"
      description="Each published window contains an observed German stress day that GridStorm replays as a StormSpec scenario"
      bodyClassName="flex flex-col gap-3"
    >
      {!d.use_in_scenario.available && seriesHere && (
        <p className="text-xs text-fg-muted" data-testid="stress-not-direct">
          The series on this page is not fed into a network directly (see “Use this data”). The scenarios below were derived from
          the stress days as their presets state; their results are model outputs, not observations.
        </p>
      )}
      <ul className="grid grid-cols-1 gap-3 xl:grid-cols-2" data-testid="stress-windows">
        {links.map((l) => {
          const record = byId.get(l.scenarioId)
          const net = record ? recordNetwork(record) : null
          const base = net ? baselines.find((b) => recordNetwork(b) === net) : undefined
          return (
            <WindowCard
              key={`${l.window.start_utc}-${l.scenarioId}`}
              link={l}
              record={record ?? (scenarios.data || scenarios.error ? null : undefined)}
              networkName={net ? nameOf(net) : null}
              unserved={indexUnservedMwh(simArtifacts.data, l.scenarioId)}
              baseline={base ? { record: base, unserved: indexUnservedMwh(simArtifacts.data, base.id) } : null}
              execution={net && record ? availability(policy, net, record.hash) : 'checking'}
              methodHref={methodHref}
              onShow={onWindow && seriesHere ? () => onWindow(windowRange(d, l.window)) : null}
            />
          )
        })}
      </ul>
      {baselines.map((b) => (
        <div key={b.id} className="rounded-md border border-line bg-surface-2 p-3 text-xs" data-testid="compare-baseline-steps">
          <h3 className="mb-1 font-semibold text-fg">Compare with the {nameOf(recordNetwork(b)) ?? recordNetwork(b)} baseline</h3>
          <p className="mb-1.5 text-fg-muted">
            Compare pairs two completed runs, so it takes two steps (no run is started from this page):
          </p>
          <ol className="flex list-decimal flex-col gap-1 pl-4 text-fg-muted">
            <li>
              Run the baseline preset{' '}
              <Link to={studioUrl(recordNetwork(b), b.id)} className="font-medium text-accent underline" data-testid="baseline-studio">
                {b.id}
              </Link>{' '}
              in Crisis Studio.
            </li>
            <li>
              Run a stress-day scenario above, then choose <span className="font-medium text-fg">Compare with baseline</span> on its run page; it pairs the run with
              the completed baseline run.
            </li>
          </ol>
        </div>
      ))}
    </Panel>
  )
}

/**
 * Historical data → crisis workflow: every published window of this dataset that contains an
 * observed-analogue stress day, with the preset derived from it, how it was derived, its stored
 * result and the actions to open it. Rendered only when such a link exists.
 */
export function StressScenarios({ d, onWindow }: { d: DatasetEntry; onWindow: ((patch: Partial<WorkspaceState>) => void) | null }) {
  const links = useMemo(() => stressLinks(d), [d])
  if (links.length === 0) return null
  return <StressScenarioList d={d} links={links} onWindow={onWindow} />
}
