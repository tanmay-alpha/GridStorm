import { lazy, Suspense } from 'react'
import { Link, Navigate, useLocation } from 'react-router'
import { ArrowRight, BookOpen, Compass, Database, FlaskConical, GitCompareArrows, Map, ShieldCheck, Zap } from 'lucide-react'
import { useNetworks } from '../../api/hooks'
import type { NetworkSummary } from '../../api/types'
import { Badge, DatasetCard, ProvenanceBadge, PROVENANCE_DESCRIPTION } from '../../components/ui'
import { NO_VALUE, formatQuantity } from '../../lib/format'
import { GUIDED_DEMO_URL } from '../studio/flow'

// The schematic renderer is shared with the Explorer chunk; loading it lazily keeps it out of the overview's initial JS.
const GridPreview = lazy(() => import('./GridPreview'))

const CAPABILITIES = [
  { icon: Map, title: 'Explore a grid', to: '/explore', link: 'Open Grid Explorer', text: 'Inspect buses, lines, transformers and generation in open research networks — geographic maps and schematic layouts are labelled as such.' },
  { icon: Zap, title: 'Build a crisis', to: '/studio', link: 'Design a scenario', text: 'Start from a reproducible preset, then change outages, demand or renewable availability. Scenarios are validated before anything runs.' },
  { icon: GitCompareArrows, title: 'Compare the impact', to: '/compare', link: 'Compare runs', text: 'Compare a scenario with its baseline: explicit units, time series, loading changes on the map and downloadable results.' },
  { icon: ShieldCheck, title: 'Trace every assumption', to: '/methods', link: 'Read the methods', text: 'Dataset provenance, model limitations and solver warnings travel with the numbers. Research outputs are not operational forecasts.' },
]

const EVIDENCE = [
  { icon: BookOpen, title: 'Methods', to: '/methods', text: 'Assumptions, equations, limitations and data provenance behind every GridStorm number, each linked to the repository document it comes from.' },
  { icon: FlaskConical, title: 'Benchmarks', to: '/benchmarks', text: 'Measured results from published artifacts: contingency-screening accuracy and speed, probabilistic stress estimates, cross-engine agreement and AC power-flow reference validation.' },
  { icon: Database, title: 'Research Workbench', to: '/workbench', text: 'Published studies with scenario, assumptions, results, limitations, solver and dataset versions and a downloadable reproduction manifest.' },
]

const GUIDE = ['Studio explains which generator fails and runs the scenario', 'The result page summarises the grid impact', 'Compare it with the no-crisis baseline and download the data']

const plural = (n: number | undefined, one: string, many: string) => (n === undefined ? NO_VALUE : `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`)

function NetworkCard({ n }: { n: NetworkSummary }) {
  const branches = n.counts.lines === undefined && n.counts.transformers === undefined && n.counts.links === undefined ? undefined : (n.counts.lines ?? 0) + (n.counts.transformers ?? 0) + (n.counts.links ?? 0)
  return (
    <DatasetCard
      title={n.name}
      id={n.id}
      to={`/explore?network=${n.id}`}
      testId="home-dataset-card"
      badges={
        <>
          <Badge tone={n.coordinate_kind === 'schematic' ? 'warn' : 'neutral'}>{n.coordinate_kind}</Badge>
          <ProvenanceBadge value={n.provenance_class} />
          {n.license?.spdx && (
            <Badge tone="info" caps={false}>
              {n.license.spdx}
            </Badge>
          )}
        </>
      }
      summary={n.description}
      facts={[
        { label: 'Buses', value: n.counts.buses?.toLocaleString('en-US') ?? NO_VALUE },
        { label: 'Branches', value: branches?.toLocaleString('en-US') ?? NO_VALUE },
        { label: 'Generators', value: n.counts.generators?.toLocaleString('en-US') ?? NO_VALUE },
        { label: 'Snapshots', value: n.snapshots ? `${n.snapshots.count.toLocaleString('en-US')} × ${formatQuantity(n.snapshots.resolution_h, 'h')}` : NO_VALUE },
      ]}
    />
  )
}

function Datasets() {
  const networks = useNetworks()
  const list = networks.data ?? []
  return (
    <section className="mt-14 sm:mt-20" aria-labelledby="datasets-title">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
          <p className="gs-label text-accent">Open data</p>
          <h2 id="datasets-title" className="mt-1 text-xl font-semibold tracking-tight">
            Network datasets
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-fg-muted" data-testid="home-dataset-count">
            {networks.data
              ? `${plural(list.length, 'network model', 'network models')} served by the GridStorm API, each with its source, licence and provenance class.`
              : networks.error
                ? 'The dataset list is unavailable right now — the API did not answer.'
                : 'Loading the dataset list from the GridStorm API…'}
          </p>
        </div>
        <Link to="/data" className="inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-accent hover:underline" data-testid="home-data-link">
          Browse the Data Observatory <ArrowRight aria-hidden className="size-4" />
        </Link>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {networks.data
          ? list.map((n) => <NetworkCard key={n.id} n={n} />)
          : !networks.error && [0, 1, 2].map((i) => <div key={i} className="gs-skeleton h-64 rounded-[10px]" aria-hidden />)}
      </div>
    </section>
  )
}

export default function HomePage() {
  const location = useLocation()
  if (new URLSearchParams(location.search).has('network')) return <Navigate replace to={`/explore${location.search}${location.hash}`} />
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8 sm:py-12 lg:py-14">
      <section className="grid items-start gap-8 lg:grid-cols-[1fr_1.05fr] lg:gap-12" aria-labelledby="overview-title">
        <div className="lg:pt-6">
          <p className="gs-label mb-4 text-accent">Open power-system resilience research</p>
          <h1 id="overview-title" className="max-w-2xl text-3xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            Understand a grid.
            <br />
            <span className="text-accent">Test its resilience.</span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-fg-muted">
            GridStorm connects open grid data, crisis scenarios and reproducible simulations — so you can see what changes, why it changes and where the model stops.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link data-testid="try-sample-crisis" to={GUIDED_DEMO_URL} className="inline-flex min-h-11 items-center gap-3 rounded-lg bg-accent px-5 py-3 font-semibold text-accent-fg hover:opacity-90">
              Start the guided demo <ArrowRight aria-hidden className="size-4" />
            </Link>
            <Link to="/explore" className="inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface px-5 py-3 font-medium hover:bg-surface-2">
              Explore a grid
            </Link>
          </div>
          <p className="mt-4 text-sm text-fg-muted">
            Prefer to build your own?{' '}
            <Link to="/studio" className="font-medium text-accent underline underline-offset-2" data-testid="open-studio">
              Open Crisis Studio
            </Link>
            .
          </p>
          <ul className="mt-8 flex flex-col gap-2 border-t border-line pt-5 text-sm text-fg-muted">
            <li className="flex gap-2.5"><ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-accent" />Every value carries a provenance class: observed, estimated, synthetic, modeled or calculated.</li>
            <li className="flex gap-2.5"><Database aria-hidden className="mt-0.5 size-4 shrink-0 text-accent" />Money stays in each dataset's declared cost basis; benchmark cost units are never shown as euros.</li>
          </ul>
        </div>
        <aside className="gs-panel flex flex-col overflow-hidden" aria-labelledby="guide-heading" data-testid="guided-demo-card">
          {/* Fixed-height slot: the lazily drawn preview never shifts the text below it. */}
          <div className="h-64 sm:h-80 lg:h-96">
            <Suspense fallback={<div className="h-full rounded-t-[9px] bg-map-bg" aria-hidden />}>
              <GridPreview />
            </Suspense>
          </div>
          <div className="border-t border-line p-5 sm:p-6">
            <p className="gs-label flex items-center gap-1.5">
              <Compass aria-hidden className="size-3.5 text-accent" /> Guided demo
            </p>
            <h2 id="guide-heading" className="mt-2 text-lg font-semibold leading-snug sm:text-xl">
              One generator goes offline.
              <br />
              Can the grid still serve demand?
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-fg-muted">
              A real benchmark case: the IEEE 14-bus test grid above loses one generating unit. Every number you will see comes from the dataset or the solver run.
            </p>
            <ol className="mt-4 flex flex-col gap-2 text-sm">
              {GUIDE.map((text, i) => (
                <li key={text} className="flex gap-2.5">
                  <span aria-hidden className="tabular flex size-5 shrink-0 items-center justify-center rounded-full border border-line-strong text-2xs font-semibold text-fg-muted">
                    {i + 1}
                  </span>
                  <span>{text}</span>
                </li>
              ))}
            </ol>
          </div>
        </aside>
      </section>

      <section className="mt-14 sm:mt-20" aria-labelledby="how-it-works">
        <p className="gs-label text-accent">Workflow</p>
        <h2 id="how-it-works" className="mb-5 mt-1 text-xl font-semibold tracking-tight">
          From an open dataset to an explainable result
        </h2>
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {CAPABILITIES.map(({ icon: Icon, title, text, to, link }, i) => (
            <li key={title} className="flex flex-col rounded-[10px] border border-line bg-surface p-5 shadow-panel">
              <div className="mb-4 flex items-center justify-between">
                <span className="flex size-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
                  <Icon aria-hidden className="size-4.5" />
                </span>
                <span className="font-mono text-xs text-fg-subtle">Step {i + 1}</span>
              </div>
              <h3 className="font-semibold">{title}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-fg-muted">{text}</p>
              <Link to={to} className="mt-4 inline-flex min-h-6 items-center gap-1 self-start text-sm font-medium text-accent hover:underline">
                {link} <ArrowRight aria-hidden className="size-3.5" />
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <Datasets />

      <section className="mt-14 sm:mt-20" aria-labelledby="evidence-title">
        <p className="gs-label text-accent">Scientific evidence</p>
        <h2 id="evidence-title" className="mt-1 text-xl font-semibold tracking-tight">
          How results are checked
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-fg-muted">
          GridStorm is a research tool, not a real-time control system. Its methods, benchmark artifacts and reproduction manifests are public.
        </p>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          {EVIDENCE.map(({ icon: Icon, title, to, text }) => (
            <Link key={to} to={to} className="group flex flex-col rounded-[10px] border border-line bg-surface p-5 shadow-panel transition-colors hover:border-accent">
              <span className="flex items-center gap-2 font-semibold text-fg group-hover:text-accent">
                <Icon aria-hidden className="size-4 text-accent" />
                {title}
                <ArrowRight aria-hidden className="ml-auto size-4 text-fg-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-accent" />
              </span>
              <span className="mt-2 text-sm leading-relaxed text-fg-muted">{text}</span>
            </Link>
          ))}
        </div>
        <div className="mt-6 rounded-[10px] border border-line bg-surface-2 p-5">
          <h3 className="text-sm font-semibold">Provenance vocabulary</h3>
          <dl className="mt-3 grid gap-x-6 gap-y-2.5 text-xs sm:grid-cols-2 lg:grid-cols-3">
            {(Object.keys(PROVENANCE_DESCRIPTION) as (keyof typeof PROVENANCE_DESCRIPTION)[]).map((p) => (
              <div key={p} className="flex items-start gap-2">
                <dt className="shrink-0">
                  <ProvenanceBadge value={p} />
                </dt>
                <dd className="text-fg-muted">{PROVENANCE_DESCRIPTION[p].split(' — ')[1]}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  )
}
