import { Link } from 'react-router'
import { FlaskConical, Map as MapIcon, PlayCircle } from 'lucide-react'
import type { DatasetSummary } from '../../api/types'
import { Badge, DatasetCard, ProvenanceBadge } from '../../components/ui'
import { NO_VALUE } from '../../lib/format'
import { availabilityLabel, REDISTRIBUTION_TEXT, resolutionLabel, utcDate } from './vocabulary'

/** Where a catalog entry is used in the app: the Explorer for networks, the study's own page for studies. */
function entryPageLink(d: Pick<DatasetSummary, 'category' | 'links'>): { to: string; label: string; icon: typeof MapIcon } | null {
  if (d.category === 'network_model' && d.links.network_id)
    return { to: `/explore?network=${encodeURIComponent(d.links.network_id)}`, label: 'Open in Grid Explorer', icon: MapIcon }
  const route = d.links.study_route
  if (d.category !== 'precomputed_experiment' || !route) return null
  if (route.startsWith('/studio')) return { to: route, label: 'Open in Crisis Studio', icon: PlayCircle }
  if (route.startsWith('/workbench')) return { to: route, label: 'Open in Research Workbench', icon: FlaskConical }
  return { to: route, label: 'Open study results', icon: FlaskConical }
}

/**
 * One catalog entry as a shared `DatasetCard`: provenance badge, the same facts for every entry
 * (source, region, coverage, resolution, availability, licence), honest data-nature line and, for
 * networks and studies, a link to the page that uses them.
 */
export function CatalogCard({ d }: { d: DatasetSummary }) {
  const licence = d.source.license
  const range = d.temporal ? `${utcDate(d.temporal.start_utc)} → ${utcDate(d.temporal.end_utc)}` : null
  // Network entries are named after their source; their version line names the upstream instead.
  const source = d.source.publisher ?? (d.source.name === d.title && d.source.version ? d.source.version : d.source.name)
  const page = entryPageLink(d)
  return (
    <DatasetCard
      title={d.title}
      to={`/data/${encodeURIComponent(d.id)}`}
      id={d.id}
      testId="dataset-card"
      className="w-full"
      badges={
        <>
          <ProvenanceBadge value={d.provenance} />
          {!d.exportable && d.series.length > 0 && (
            <Badge tone="warn" title={REDISTRIBUTION_TEXT[licence.redistribution]}>
              view only
            </Badge>
          )}
        </>
      }
      summary={d.summary}
      facts={[
        { label: 'Source', value: <span title={[d.source.name, d.source.publisher, d.source.version].filter(Boolean).join(' · ')}>{source}</span> },
        { label: 'Region', value: d.region ? <span title={d.region.name}>{d.region.name}</span> : NO_VALUE },
        { label: 'Coverage (UTC)', value: range ? <span title={range}>{range}</span> : 'Not time-indexed' },
        { label: 'Resolution', value: d.temporal ? resolutionLabel(d.temporal.resolution) : NO_VALUE },
        { label: 'Availability', value: availabilityLabel(d) },
        {
          label: 'Licence',
          value: <span title={REDISTRIBUTION_TEXT[licence.redistribution]}>{`${licence.id} · ${licence.redistribution}`}</span>,
        },
      ]}
      footer={
        <span className="flex min-w-0 flex-col items-start gap-1">
          {page && (
            <Link
              to={page.to}
              className="inline-flex min-h-6 items-center gap-1 font-medium text-accent underline-offset-2 hover:underline"
              data-testid="dataset-card-page"
            >
              <page.icon aria-hidden className="size-3.5" />
              {page.label}
              <span className="sr-only"> — {d.title}</span>
            </Link>
          )}
          <span className="text-2xs italic text-fg-subtle">{d.data_nature}</span>
        </span>
      }
    />
  )
}
