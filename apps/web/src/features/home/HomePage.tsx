import { Link, Navigate, useLocation } from 'react-router'
import { ArrowRight, GitCompareArrows, Map, ShieldCheck, Zap } from 'lucide-react'

export const SAMPLE_CRISIS_URL = '/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage'

const STEPS = [
  { icon: Map, title: 'Explore a grid', text: 'Inspect buses, transmission lines and generation in open research networks. Distinguish geographic maps from schematic layouts.' },
  { icon: Zap, title: 'Build a crisis', text: 'Start with a reproducible preset, then change outages, demand or renewable availability in Crisis Studio.' },
  { icon: GitCompareArrows, title: 'Compare the impact', text: 'Run a supported simulation and compare it with a baseline using explicit units, time series and downloadable results.' },
  { icon: ShieldCheck, title: 'Trace every assumption', text: 'Review dataset provenance, model limitations and solver warnings. Research outputs are not operational forecasts.' },
]

export default function HomePage() {
  const location = useLocation()
  if (new URLSearchParams(location.search).has('network')) return <Navigate replace to={`/explore${location.search}${location.hash}`} />
  return (
    <div className="mx-auto max-w-6xl px-5 py-10 sm:px-10 sm:py-16">
      <p className="gs-label mb-4 text-accent">Open power-system research workspace</p>
      <section className="grid items-center gap-10 lg:grid-cols-[1.4fr_1fr]" aria-labelledby="overview-title">
        <div>
          <h1 id="overview-title" className="max-w-2xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">Understand a grid.<br /><span className="text-accent">Test its resilience.</span></h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-fg-muted">GridStorm connects open grid data, crisis scenarios and reproducible simulations — so you can see what changes, why it changes and where the model stops.</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link data-testid="try-sample-crisis" to={SAMPLE_CRISIS_URL} className="inline-flex min-h-11 items-center gap-3 rounded-lg bg-accent px-5 py-3 font-semibold text-accent-fg hover:opacity-90">Try a sample crisis <ArrowRight aria-hidden className="size-4" /></Link>
            <Link to="/explore" className="inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface px-5 py-3 font-medium hover:bg-surface-2">Explore a grid</Link>
          </div>
        </div>
        <aside className="gs-panel border-accent/25 p-6 sm:p-8" aria-label="Sample crisis">
          <div className="mb-5 flex size-12 items-center justify-center rounded-xl bg-accent-soft text-accent"><Zap aria-hidden className="size-6" /></div>
          <p className="gs-label">Your first experiment</p>
          <h2 className="mt-2 text-xl font-semibold">One generator goes offline.<br />What happens next?</h2>
          <p className="mt-4 leading-relaxed text-fg-muted">Open the IEEE 14-bus generator-outage preset in Studio. Review the scenario, run it and inspect the change against its baseline.</p>
          <p className="mt-5 border-t border-line pt-4 text-xs text-fg-subtle">Small benchmark network · schematic, not geographic · research use only</p>
        </aside>
      </section>
      <section className="mt-12 border-t border-line pt-8 sm:mt-16" aria-labelledby="how-it-works">
        <h2 id="how-it-works" className="mb-6 text-xl font-semibold tracking-tight">From an open dataset to an explainable result</h2>
        <ol className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{STEPS.map(({ icon: Icon, title, text }, i) => <li key={title} className="rounded-xl border border-line bg-surface p-5"><div className="mb-4 flex items-center justify-between text-accent"><Icon aria-hidden className="size-5" /><span className="font-mono text-xs text-fg-subtle">0{i + 1}</span></div><h3 className="font-semibold">{title}</h3><p className="mt-2 text-sm leading-relaxed text-fg-muted">{text}</p></li>)}</ol>
      </section>
    </div>
  )
}
