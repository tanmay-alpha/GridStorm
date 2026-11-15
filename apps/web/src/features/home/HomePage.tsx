import { Link, Navigate, useLocation } from 'react-router'
import { ArrowRight, Compass, GitCompareArrows, Map, ShieldCheck, Zap } from 'lucide-react'
import { GUIDED_DEMO_URL } from '../studio/flow'

const STEPS = [
  { icon: Map, title: 'Explore a grid', text: 'Inspect buses, transmission lines and generation in open research networks. Distinguish geographic maps from schematic layouts.' },
  { icon: Zap, title: 'Build a crisis', text: 'Start with a reproducible preset, then change outages, demand or renewable availability in Crisis Studio.' },
  { icon: GitCompareArrows, title: 'Compare the impact', text: 'Run a supported simulation and compare it with a baseline using explicit units, time series and downloadable results.' },
  { icon: ShieldCheck, title: 'Trace every assumption', text: 'Review dataset provenance, model limitations and solver warnings. Research outputs are not operational forecasts.' },
]

const GUIDE = ['Studio explains which generator fails and runs the scenario', 'The result page summarises the grid impact', 'Compare it with the no-crisis baseline and download the data']

export default function HomePage() {
  const location = useLocation()
  if (new URLSearchParams(location.search).has('network')) return <Navigate replace to={`/explore${location.search}${location.hash}`} />
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-10 sm:py-14">
      <p className="gs-label mb-4 text-accent">Open power-system research workspace</p>
      <section className="grid items-start gap-8 lg:grid-cols-[1.4fr_1fr] lg:gap-10" aria-labelledby="overview-title">
        <div>
          <h1 id="overview-title" className="max-w-2xl text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">Understand a grid.<br /><span className="text-accent">Test its resilience.</span></h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-fg-muted">GridStorm connects open grid data, crisis scenarios and reproducible simulations — so you can see what changes, why it changes and where the model stops.</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link data-testid="try-sample-crisis" to={GUIDED_DEMO_URL} className="inline-flex min-h-11 items-center gap-3 rounded-lg bg-accent px-5 py-3 font-semibold text-accent-fg hover:opacity-90">Start the guided demo <ArrowRight aria-hidden className="size-4" /></Link>
            <Link to="/explore" className="inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface px-5 py-3 font-medium hover:bg-surface-2">Explore a grid</Link>
          </div>
          <p className="mt-4 text-sm text-fg-muted">
            Prefer to build your own? <Link to="/studio" className="font-medium text-accent underline underline-offset-2" data-testid="open-studio">Open Crisis Studio</Link>.
          </p>
        </div>
        <aside className="gs-panel p-5 sm:p-7" aria-labelledby="guide-heading" data-testid="guided-demo-card">
          <p className="gs-label flex items-center gap-1.5"><Compass aria-hidden className="size-3.5 text-accent" /> Guided demo</p>
          <h2 id="guide-heading" className="mt-2 text-xl font-semibold">One generator goes offline.<br />Can the grid still serve demand?</h2>
          <p className="mt-3 leading-relaxed text-fg-muted">A real benchmark case: the IEEE 14-bus test grid loses one generating unit. Every number you will see comes from the dataset or the solver run.</p>
          <ol className="mt-4 flex flex-col gap-2 text-sm">
            {GUIDE.map((text, i) => (
              <li key={text} className="flex gap-2.5">
                <span aria-hidden className="flex size-5 shrink-0 items-center justify-center rounded-full border border-line-strong text-2xs font-semibold text-fg-muted">{i + 1}</span>
                <span>{text}</span>
              </li>
            ))}
          </ol>
          <p className="mt-5 border-t border-line pt-4 text-xs text-fg-subtle">Small benchmark network · schematic, not geographic · research use only</p>
        </aside>
      </section>
      <section className="mt-12 border-t border-line pt-8 sm:mt-16" aria-labelledby="how-it-works">
        <h2 id="how-it-works" className="mb-6 text-xl font-semibold tracking-tight">From an open dataset to an explainable result</h2>
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{STEPS.map(({ icon: Icon, title, text }, i) => <li key={title} className="rounded-xl border border-line bg-surface p-5"><div className="mb-4 flex items-center justify-between text-accent"><Icon aria-hidden className="size-5" /><span className="font-mono text-xs text-fg-subtle">0{i + 1}</span></div><h3 className="font-semibold">{title}</h3><p className="mt-2 text-sm leading-relaxed text-fg-muted">{text}</p></li>)}</ol>
      </section>
    </div>
  )
}
