import { useState, type MouseEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ArrowLeft, Download, Map as MapIcon, FlaskConical, PlayCircle } from 'lucide-react'
import { api, ApiError } from '../../api/client'
import { useDataCatalog, useDataset, useScenarios } from '../../api/hooks'
import type { DatasetEntry, QualityStatus } from '../../api/types'
import {
  Badge,
  Button,
  buttonClass,
  EmptyState,
  ErrorState,
  KeyValue,
  LinkButton,
  LoadingState,
  PageHeader,
  Panel,
  ProvenanceLabel,
  ScientificNotice,
  type Tone,
} from '../../components/ui'
import { cn } from '../../components/ui/cn'
import { downloadBlob } from '../../lib/download'
import { formatNumber, NO_VALUE } from '../../lib/format'
import { describeWarning } from '../../lib/qualityFlags'
import { useDocumentTitle } from '../../lib/title'
import { QualityFlagLine } from '../explorer/DatasetInfo'
import { useExecutionPolicy } from '../studio/useExecutionPolicy'
import { Markdown } from './Markdown'
import { PeriodComparison } from './PeriodComparison'
import { ProvenanceDrawer } from './ProvenanceDrawer'
import { SeriesWorkspace } from './SeriesWorkspace'
import { StressScenarios } from './StressScenarios'
import { categoryLabel, coverageLabel, exportBlockedReason, resolutionLabel, utcDate, utcDateTime } from './vocabulary'
import { readWorkspace, writeWorkspace, type WorkspaceState } from './workspace'

const CHECK_TONE: Record<QualityStatus, Tone> = { pass: 'ok', warn: 'warn', fail: 'danger' }

/** Message of an API error body (`{error: {message}}`), else the HTTP status. */
async function exportError(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json()
    const err = body && typeof body === 'object' && 'error' in body ? body.error : null
    if (err && typeof err === 'object' && 'message' in err && typeof err.message === 'string') return err.message
  } catch {
    // Not JSON: fall through to the status line.
  }
  return `HTTP ${res.status}`
}

type ExportStatus = { href: string; kind: 'busy' | 'ok' | 'error'; text: string }

function ExportControl({ d, state }: { d: DatasetEntry; state: WorkspaceState }) {
  const [status, setStatus] = useState<ExportStatus | null>(null)
  const blocked = exportBlockedReason(d)
  if (blocked)
    return (
      <span className="inline-flex max-w-md flex-col items-start gap-0.5 md:items-end">
        <Button size="sm" disabled aria-describedby="export-blocked" data-testid="export-csv">
          <Download aria-hidden className="size-3.5" />
          Export CSV
        </Button>
        <span id="export-blocked" className="text-2xs text-fg-muted md:text-right" data-testid="export-blocked">
          {blocked}
        </span>
      </span>
    )
  const href = api.dataExportUrl(d.id, { series: state.series, start: state.start, end: state.end })
  const shown = status?.href === href ? status : null
  // Fetch the file to report what was saved (name, rows, licence) or why it failed; modified clicks
  // (new tab, save as) keep the plain link behaviour.
  const onClick = async (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    setStatus({ href, kind: 'busy', text: 'Preparing CSV…' })
    try {
      const res = await fetch(href)
      if (!res.ok) return setStatus({ href, kind: 'error', text: `Export failed: ${await exportError(res)}` })
      const blob = await res.blob()
      const filename = /filename="?([^";]+)"?/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? `${d.id}.csv`
      // Data rows: everything except the "#" licence/provenance header and the column header line.
      const rows = Math.max(0, (await blob.text()).split(/\r?\n/).filter((l) => l && !l.startsWith('#')).length - 1)
      downloadBlob(filename, blob)
      setStatus({ href, kind: 'ok', text: `Saved ${filename} · ${rows.toLocaleString('en-US')} rows · licence ${d.source.license.id}` })
    } catch {
      setStatus({ href, kind: 'error', text: 'Export failed: the API could not be reached.' })
    }
  }
  return (
    <span className="inline-flex max-w-md flex-col items-start gap-0.5 md:items-end">
      {/* Fallback name only: the API's Content-Disposition filename (dataset + UTC window) takes precedence. */}
      <LinkButton
        size="sm"
        variant="primary"
        href={href}
        download={`${d.id}.csv`}
        onClick={(e) => void onClick(e)}
        aria-describedby="export-status"
        data-testid="export-csv"
        title="Raw values for the selected series and window, with a licence/attribution/sha256 header"
      >
        <Download aria-hidden className="size-3.5" />
        Export CSV
      </LinkButton>
      {/* One reserved line, so the result message never moves the page. */}
      <span
        id="export-status"
        role="status"
        className={cn('block min-h-4 max-w-full truncate text-2xs md:text-right', shown?.kind === 'error' ? 'font-medium text-danger' : 'text-fg-muted')}
        title={shown?.text}
        data-testid="export-status"
      >
        {shown?.text ?? ''}
      </span>
    </span>
  )
}

function CoveragePanel({ d }: { d: DatasetEntry }) {
  const t = d.temporal
  const q = d.quality
  const missing = d.series.map((s) => [s.label, q.missing_values[s.id]] as const)
  return (
    <Panel title="Coverage" id="obs-coverage" bodyClassName="flex flex-col gap-3">
      <KeyValue
        rows={[
          ['Time range', coverageLabel(t)],
          ['Resolution', t ? resolutionLabel(t.resolution) : NO_VALUE],
          ['Timezone', t ? 'UTC' : NO_VALUE],
          ['Region', d.region ? `${d.region.name} (${d.region.kind})` : NO_VALUE],
          ['Rows', q.rows === null ? NO_VALUE : `${q.rows.toLocaleString('en-US')}${q.expected_rows !== null ? ` of ${q.expected_rows.toLocaleString('en-US')} expected` : ''}`],
          ['Completeness', q.completeness_pct === null ? NO_VALUE : `${formatNumber(q.completeness_pct, 2)} %`],
          ['Missing values', 'kept as missing (drawn as gaps, never 0)'],
        ]}
      />
      {t?.windows && t.windows.length > 0 && (
        <div>
          <h3 className="gs-label mb-1">Published windows</h3>
          <ul className="flex flex-col gap-1 text-xs">
            {t.windows.map((w) => (
              <li key={`${w.start_utc}-${w.label}`}>
                <span className="font-medium text-fg">{w.label}</span>
                <span className="tabular block text-2xs text-fg-muted">
                  {utcDateTime(w.start_utc)} → {utcDateTime(w.end_utc)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {missing.length > 0 && (
        <div>
          <h3 className="gs-label mb-1">Missing values per series</h3>
          <ul className="flex flex-col gap-0.5 text-xs" data-testid="missing-counts">
            {missing.map(([label, n]) => (
              <li key={label} className="flex justify-between gap-2">
                <span className="min-w-0 truncate text-fg-muted">{label}</span>
                <span className="tabular text-fg">{n ?? NO_VALUE}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}

function QualityPanel({ d }: { d: DatasetEntry }) {
  const checks = d.quality.checks
  return (
    <Panel title="Quality" id="obs-quality" bodyClassName="flex flex-col gap-3">
      {d.quality.warnings.length > 0 && (
        <p className="text-xs text-fg-muted">
          {d.quality.warnings.length === 1 ? 'One warning is' : `${d.quality.warnings.length} warnings are`} shown at the top
          of this page.
        </p>
      )}
      {checks.some((c) => c.status === 'fail') && (
        <ScientificNotice kind="warning" title="A quality check failed">
          Values that fail integrity checks are not served by the API.
        </ScientificNotice>
      )}
      {checks.length ? (
        <ul className="flex flex-col gap-2 text-xs" data-testid="quality-checks">
          {checks.map((c) => (
            <li key={c.name} className="flex flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-1.5">
                <Badge tone={CHECK_TONE[c.status] ?? 'neutral'}>{c.status}</Badge>
                <span className="font-medium text-fg">{c.name}</span>
              </span>
              <span className="break-words text-fg-muted">{c.detail}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-fg-muted">No automated checks recorded for this entry.</p>
      )}
    </Panel>
  )
}

function ActionsPanel({ d }: { d: DatasetEntry }) {
  const use = d.use_in_scenario
  const link = buttonClass('secondary', 'md', 'w-full justify-start')
  return (
    <Panel title="Use this data" id="obs-actions" bodyClassName="flex flex-col gap-3 text-xs">
      {d.links.network_id && (
        <Link to={`/explore?network=${encodeURIComponent(d.links.network_id)}`} className={link} data-testid="open-explorer">
          <MapIcon aria-hidden className="size-4" />
          Open in Grid Explorer
        </Link>
      )}
      {use.available && use.route ? (
        <div className="flex flex-col gap-1">
          <Link to={use.route} className={buttonClass('primary', 'md', 'w-full justify-start')} data-testid="use-in-scenario">
            <PlayCircle aria-hidden className="size-4" />
            Use in a scenario
          </Link>
          <p className="text-fg-muted">{use.rationale}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-0.5 rounded border border-line bg-surface-2 p-2" data-testid="scenario-unavailable">
          <p className="font-medium text-fg">Not available as a scenario input</p>
          <p className="text-fg-muted">{use.rationale}</p>
        </div>
      )}
      {d.links.study_route && (
        <Link to={d.links.study_route} className={link} data-testid="open-study">
          <FlaskConical aria-hidden className="size-4" />
          Open the research study
        </Link>
      )}
      {d.links.scenario_ids.length > 0 && (
        <div>
          <h3 className="gs-label mb-1">Related scenarios</h3>
          <ul className="flex flex-wrap gap-1">
            {d.links.scenario_ids.map((s) => (
              <li key={s}>
                <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-2xs">{s}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}

/**
 * Other series of the same region whose UTC coverage overlaps this one (e.g. daily weather next to
 * the load forecast), for context only: listing them implies no causal relation. Last in the sidebar,
 * so its late arrival (one catalog request) moves nothing below it.
 */
function RelatedSeries({ d }: { d: DatasetEntry }) {
  const catalog = useDataCatalog({})
  const t = d.temporal
  if (!t || !d.region || d.series.length === 0) return null
  const lo = Date.parse(t.start_utc)
  const hi = Date.parse(t.end_utc)
  const overlap = (x: { start_utc: string; end_utc: string }) => Math.min(hi, Date.parse(x.end_utc)) - Math.max(lo, Date.parse(x.start_utc))
  const related = (catalog.data?.items ?? [])
    .filter((x) => x.id !== d.id && x.series.length > 0 && x.region?.code === d.region!.code && x.category !== d.category && x.temporal && overlap(x.temporal) > 0)
    .sort((a, b) => overlap(b.temporal!) - overlap(a.temporal!) || a.title.localeCompare(b.title))
    .slice(0, 3)
  if (related.length === 0) return null
  return (
    <Panel title="Context datasets" id="obs-related" description="Same region, overlapping UTC coverage" bodyClassName="flex flex-col gap-2 text-xs">
      <ul className="flex flex-col gap-1.5" data-testid="related-series">
        {related.map((x) => (
          <li key={x.id}>
            <Link to={`/data/${encodeURIComponent(x.id)}`} className="font-medium text-accent underline underline-offset-2">
              {x.title}
            </Link>
            <span className="tabular block text-2xs text-fg-muted">
              {categoryLabel(x.category)} · {utcDate(x.temporal!.start_utc)} → {utcDate(x.temporal!.end_utc)} · {resolutionLabel(x.temporal!.resolution)}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-2xs text-fg-subtle">Listed for context (e.g. seasonal weather); no causal link between the series is implied.</p>
    </Panel>
  )
}

/** Accessible list of source request points; only for `spatial.kind === 'points'` with real coordinates. */
function PointsPanel({ d }: { d: DatasetEntry }) {
  const points = (d.spatial.points ?? []).filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon))
  if (d.spatial.kind !== 'points' || points.length === 0) return null
  return (
    <Panel title="Locations" id="obs-points" description="Coordinates as requested from the source (WGS 84)">
      <div className="overflow-x-auto" role="region" aria-label="Locations (table)" tabIndex={0}>
        <table className="w-full border-collapse text-xs" data-testid="points-table">
          <caption className="sr-only">Source request points</caption>
          <thead>
            <tr className="border-b border-line text-left text-fg-muted">
              <th scope="col" className="px-2 py-1 font-semibold">Name</th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">Lat [°N]</th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">Lon [°E]</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.id} className="border-b border-line/60 align-top">
                <th scope="row" className="px-2 py-1 text-left font-normal text-fg">
                  {p.name}
                  {p.grid_note && <span className="block text-2xs text-fg-subtle">{p.grid_note}</span>}
                </th>
                <td className="tabular px-2 py-1 text-right">{p.lat.toFixed(3)}</td>
                <td className="tabular px-2 py-1 text-right">{p.lon.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function DatasetView({ d }: { d: DatasetEntry }) {
  const [params, setParams] = useSearchParams()
  const state = readWorkspace(params, d)
  const hasSeries = d.series.length > 0 && !!d.artifact && !!d.temporal
  const onChange = (patch: Partial<WorkspaceState>) => setParams((p) => writeWorkspace(p, patch), { replace: true })
  const showWindow = (patch: Partial<WorkspaceState>) => {
    onChange(patch)
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    document.getElementById('obs-series')?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
  }
  const warnings = d.quality.warnings.map(describeWarning)
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 p-4 md:p-6" data-testid="dataset-page" data-dataset={d.id}>
      <Link to="/data" className="inline-flex min-h-6 w-fit items-center gap-1 text-xs text-fg-muted hover:text-fg">
        <ArrowLeft aria-hidden className="size-3.5" />
        Data Observatory
      </Link>
      <PageHeader
        title={d.title}
        subtitle={d.summary}
        badges={<Badge>{categoryLabel(d.category)}</Badge>}
        actions={
          <>
            <ProvenanceDrawer d={d} />
            <ExportControl d={d} state={state} />
          </>
        }
      />
      {warnings.length === 1 ? (
        <ScientificNotice kind="warning" title={warnings[0]!.sentence ?? warnings[0]!.code ?? ''} testId="dataset-warnings">
          {warnings[0]!.sentence && warnings[0]!.code && <code className="font-mono text-2xs text-fg-muted">{warnings[0]!.code}</code>}
        </ScientificNotice>
      ) : warnings.length > 1 ? (
        <ScientificNotice kind="warning" title={`${warnings.length} quality warnings for this dataset`} testId="dataset-warnings">
          <ul className="flex list-disc flex-col gap-1 pl-4">
            {warnings.map((w, i) => (
              <li key={d.quality.warnings[i]} className="break-words">
                <QualityFlagLine text={w} />
              </li>
            ))}
          </ul>
        </ScientificNotice>
      ) : null}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <Panel title="Overview" id="obs-overview" bodyClassName="flex flex-col gap-3 text-sm">
            <ProvenanceLabel value={d.provenance} label="Provenance" testId="dataset-provenance" />
            <p className="text-xs text-fg-muted">
              <span className="font-medium text-fg">Nature of the data: </span>
              {d.data_nature}
            </p>
            <Markdown text={d.description} className="flex max-w-3xl flex-col gap-2 text-fg" />
            <p className="text-xs text-fg-muted">
              Source: {d.source.name}
              {d.source.version ? ` · version ${d.source.version}` : ''} · licence {d.source.license.id}
            </p>
          </Panel>
          {hasSeries ? (
            <>
              <SeriesWorkspace d={d} state={state} onChange={onChange} />
              <StressScenarios d={d} onWindow={showWindow} />
              <PeriodComparison d={d} />
            </>
          ) : (
            <>
              <StressScenarios d={d} onWindow={null} />
              <Panel title="Time series" id="obs-series">
                <EmptyState title="No time series in this entry">
                  {d.category === 'network_model'
                    ? 'Network models are topologies and parameters; open them in the Grid Explorer.'
                    : 'This entry is described here; its data are served by the linked GridStorm view.'}
                </EmptyState>
              </Panel>
            </>
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <ActionsPanel d={d} />
          <CoveragePanel d={d} />
          <QualityPanel d={d} />
          <PointsPanel d={d} />
          <RelatedSeries d={d} />
        </div>
      </div>
    </div>
  )
}

export default function DatasetPage() {
  const { datasetId } = useParams()
  const q = useDataset(datasetId)
  // Requested in parallel with the dataset (small, shared with Crisis Studio), so the stress-window
  // scenarios render together with the page instead of growing it afterwards.
  useScenarios()
  useExecutionPolicy()
  useDocumentTitle(q.data ? `${q.data.title} · Data Observatory` : null)
  if (q.isPending)
    return (
      <div className="mx-auto w-full max-w-7xl p-4 md:p-6">
        <LoadingState label="Loading dataset" rows={8} />
      </div>
    )
  if (q.error || !q.data)
    return (
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 p-4 md:p-6">
        <ErrorState
          error={q.error ?? 'No data'}
          title={q.error instanceof ApiError && q.error.status === 404 ? `Dataset “${datasetId}” not found` : undefined}
          onRetry={() => void q.refetch()}
        />
        <Link to="/data" className="text-sm text-accent underline">
          Back to the Data Observatory
        </Link>
      </div>
    )
  return <DatasetView key={q.data.id} d={q.data} />
}
