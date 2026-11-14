import { Link } from 'react-router'
import { useMutation } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { api } from '../../api/client'
import { useArtifactIndex, useJobs, useNetworks, useScenarios } from '../../api/hooks'
import type { ArtifactIndexItem, Job, NetworkSummary, ScenarioRecord } from '../../api/types'
import {
  Badge,
  Button,
  DataTable,
  ErrorState,
  ExecutionModeBadge,
  JobStatusBadge,
  OutcomeBadge,
  PageHeader,
  Panel,
  ProvenanceBadge,
  QueryView,
  SkeletonBlock,
  type Column,
} from '../../components/ui'
import { NO_VALUE, formatDuration, formatTimestamp, shortHash } from '../../lib/format'
import { downloadJson } from '../../lib/download'

function DownloadButton({ label, fetcher, filename }: { label: string; fetcher: () => Promise<unknown>; filename: string }) {
  const m = useMutation({ mutationFn: async () => downloadJson(filename, await fetcher()) })
  return (
    <span className="inline-flex items-center gap-1">
      <Button size="sm" variant="ghost" onClick={() => m.mutate()} disabled={m.isPending} aria-label={`${label} (${filename})`}>
        <Download aria-hidden className="size-3.5" /> {label}
      </Button>
      {m.error && (
        <span role="alert" className="text-2xs text-danger">
          {m.error.message}
        </span>
      )}
    </span>
  )
}

const jobColumns: Column<Job>[] = [
  {
    key: 'id',
    header: 'Job',
    sortValue: (j) => j.id,
    render: (j) => (
      <Link to={`/runs/${encodeURIComponent(j.id)}`} className="font-mono text-accent underline">
        {shortHash(j.id, 8)}
      </Link>
    ),
  },
  { key: 'scenario', header: 'Scenario', sortValue: (j) => j.scenario_id, render: (j) => j.scenario_id ?? NO_VALUE },
  { key: 'network', header: 'Network', sortValue: (j) => j.network_id, render: (j) => j.network_id ?? NO_VALUE },
  { key: 'status', header: 'Status', sortValue: (j) => j.status, render: (j) => <JobStatusBadge status={j.status} /> },
  { key: 'outcome', header: 'Outcome', sortValue: (j) => j.outcome, render: (j) => <OutcomeBadge outcome={j.outcome} /> },
  { key: 'mode', header: 'Mode', sortValue: (j) => j.execution_mode, render: (j) => <ExecutionModeBadge mode={j.execution_mode} /> },
  {
    key: 'wall',
    header: 'Wall time',
    align: 'right',
    sortValue: (j) => j.solver?.wall_time_s,
    render: (j) => formatDuration(j.solver?.wall_time_s),
  },
  { key: 'created', header: 'Created (UTC)', sortValue: (j) => j.created_at, render: (j) => formatTimestamp(j.created_at) },
]

const scenarioColumns: Column<ScenarioRecord>[] = [
  {
    key: 'name',
    header: 'Scenario',
    sortValue: (s) => s.name ?? s.spec.name,
    render: (s) => (
      <Link to={`/studio?preset=${encodeURIComponent(s.id)}`} className="text-accent underline">
        {s.name ?? s.spec.name}
      </Link>
    ),
  },
  { key: 'id', header: 'Id', sortValue: (s) => s.id, render: (s) => <span className="font-mono">{s.id}</span> },
  { key: 'kind', header: 'Kind', sortValue: (s) => (s.preset ? 0 : 1), render: (s) => (s.preset ? <Badge tone="info">preset</Badge> : <Badge>saved</Badge>) },
  { key: 'network', header: 'Network', sortValue: (s) => s.spec.dataset.network_id, render: (s) => s.spec.dataset.network_id },
  { key: 'events', header: 'Events', align: 'right', sortValue: (s) => s.spec.events.length, render: (s) => s.spec.events.length },
  { key: 'hash', header: 'Hash', render: (s) => <code className="font-mono">{shortHash(s.hash)}</code> },
  { key: 'created', header: 'Created (UTC)', sortValue: (s) => s.created_at, render: (s) => formatTimestamp(s.created_at) },
  {
    key: 'dl',
    header: <span className="sr-only">Download</span>,
    render: (s) => <DownloadButton label="Spec" filename={`stormspec-${s.id}.json`} fetcher={async () => s.spec} />,
  },
]

const networkColumns: Column<NetworkSummary>[] = [
  {
    key: 'name',
    header: 'Dataset',
    sortValue: (n) => n.name,
    render: (n) => (
      <Link to={`/?network=${encodeURIComponent(n.id)}`} className="text-accent underline">
        {n.name}
      </Link>
    ),
  },
  { key: 'id', header: 'Id', sortValue: (n) => n.id, render: (n) => <span className="font-mono">{n.id}</span> },
  {
    key: 'kind',
    header: 'Coordinates',
    sortValue: (n) => n.coordinate_kind,
    render: (n) => <Badge tone={n.coordinate_kind === 'schematic' ? 'warn' : 'neutral'}>{n.coordinate_kind}</Badge>,
  },
  { key: 'prov', header: 'Provenance', render: (n) => <ProvenanceBadge value={n.provenance_class} /> },
  {
    key: 'lic',
    header: 'License',
    sortValue: (n) => n.license?.spdx,
    render: (n) =>
      n.license?.url ? (
        <a href={n.license.url} target="_blank" rel="noreferrer" className="text-accent underline">
          {n.license.spdx ?? 'license'}
        </a>
      ) : (
        (n.license?.spdx ?? NO_VALUE)
      ),
  },
  { key: 'buses', header: 'Buses', align: 'right', sortValue: (n) => n.counts.buses, render: (n) => n.counts.buses ?? NO_VALUE },
  { key: 'snap', header: 'Snapshots', align: 'right', sortValue: (n) => n.snapshots?.count, render: (n) => n.snapshots?.count ?? NO_VALUE },
  { key: 'sha', header: 'network.nc sha256', render: (n) => <code className="font-mono">{shortHash(n.network_sha256)}</code> },
  {
    key: 'dl',
    header: <span className="sr-only">Download</span>,
    render: (n) => (
      <DownloadButton
        label="Manifest"
        filename={`dataset-manifest-${n.id}.json`}
        fetcher={async () => (await api.network(n.id)).manifest ?? null}
      />
    ),
  },
]

const artifactColumns: Column<ArtifactIndexItem>[] = [
  { key: 'title', header: 'Artifact', sortValue: (a) => a.title, render: (a) => a.title || a.artifact_id },
  { key: 'engine', header: 'Engine', sortValue: (a) => a.engine, render: (a) => a.engine },
  { key: 'kind', header: 'Kind', sortValue: (a) => a.kind, render: (a) => <Badge>{a.kind ?? NO_VALUE}</Badge> },
  { key: 'network', header: 'Network', sortValue: (a) => a.network_id, render: (a) => a.network_id ?? NO_VALUE },
  {
    key: 'dl',
    header: <span className="sr-only">Download</span>,
    render: (a) => (
      <DownloadButton
        label="JSON"
        filename={`${a.engine}-${a.artifact_id}.json`}
        fetcher={() => api.artifact(a.engine, a.artifact_id)}
      />
    ),
  },
]

export default function LibraryPage() {
  const networks = useNetworks()
  const scenarios = useScenarios()
  const jobs = useJobs()
  const artifacts = useArtifactIndex()
  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-3 p-3 md:p-4">
      <PageHeader
        title="Research Library"
        subtitle="Scenarios, run history, dataset catalog with licenses and manifests, and precomputed engine artifacts — all served by the API."
      />
      <Panel title="Simulation runs" id="runs">
        <QueryView query={jobs} loading={<SkeletonBlock rows={4} label="Loading runs" />} errorTitle="Could not load runs">
          {(rows) => (
            <DataTable
              columns={jobColumns}
              rows={rows}
              rowKey={(j) => j.id}
              caption="Simulation job history"
              initialSort={{ key: 'created', dir: 'desc' }}
              emptyText="No runs yet — start one in Crisis Studio."
            />
          )}
        </QueryView>
      </Panel>
      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="Scenarios" id="scenarios">
          <QueryView query={scenarios} errorTitle="Could not load scenarios">
            {(rows) => (
              <DataTable columns={scenarioColumns} rows={rows} rowKey={(s) => s.id} caption="Preset and saved scenarios" emptyText="No scenarios." />
            )}
          </QueryView>
        </Panel>
        <Panel title="Datasets" id="datasets">
          <QueryView query={networks} errorTitle="Could not load dataset catalog">
            {(rows) => <DataTable columns={networkColumns} rows={rows} rowKey={(n) => n.id} caption="Dataset catalog" emptyText="No datasets." />}
          </QueryView>
        </Panel>
      </div>
      <Panel title="Precomputed artifacts" id="artifacts" description="Engine outputs computed offline (execution mode: precomputed).">
        {artifacts.error ? (
          <ErrorState error={artifacts.error} title="Could not load artifact index" onRetry={() => void artifacts.refetch()} />
        ) : !artifacts.data ? (
          <SkeletonBlock rows={3} label="Loading artifacts" />
        ) : (
          <DataTable
            columns={artifactColumns}
            rows={artifacts.data}
            rowKey={(a) => `${a.engine}/${a.artifact_id}`}
            caption="Precomputed artifacts"
            emptyText="No precomputed artifacts."
          />
        )}
      </Panel>
    </div>
  )
}
