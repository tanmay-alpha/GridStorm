import type { DatasetSummary } from '../../api/types'
import { Badge, DatasetCard, ProvenanceBadge } from '../../components/ui'
import { NO_VALUE } from '../../lib/format'
import { availabilityLabel, REDISTRIBUTION_TEXT, resolutionLabel, utcDate } from './vocabulary'

/** One catalog entry as a shared `DatasetCard`: provenance badge, honest data-nature line, key facts. */
export function CatalogCard({ d }: { d: DatasetSummary }) {
  const licence = d.source.license
  const range = d.temporal ? `${utcDate(d.temporal.start_utc)} → ${utcDate(d.temporal.end_utc)}` : null
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
        { label: 'Source', value: <span title={d.source.publisher ?? d.source.name}>{d.source.name}</span> },
        { label: 'Region', value: d.region?.name ?? NO_VALUE },
        { label: 'Time range (UTC)', value: range ? <span title={range}>{range}</span> : 'Not time-indexed' },
        { label: 'Resolution', value: d.temporal ? resolutionLabel(d.temporal.resolution) : NO_VALUE },
        { label: 'Availability', value: availabilityLabel(d) },
        {
          label: 'Licence',
          value: <span title={REDISTRIBUTION_TEXT[licence.redistribution]}>{`${licence.id} · ${licence.redistribution}`}</span>,
        },
      ]}
      footer={<span className="text-2xs italic text-fg-subtle">{d.data_nature}</span>}
    />
  )
}
