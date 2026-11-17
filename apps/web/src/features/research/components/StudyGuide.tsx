import { useMemo } from 'react'
import { Link } from 'react-router'
import { ArrowRight } from 'lucide-react'
import { Badge } from '../../../components/ui'
import { buildWorkbenchIndex } from '../../workbench/catalog'
import { STUDIES, type StudyExecution } from '../../workbench/studies'
import { useArtifactCatalog } from '../hooks'

/** How a study's numbers are obtained (see `StudyExecution` in workbench/studies.ts). */
const EXECUTION: Record<StudyExecution, { label: string; tone: 'info' | 'accent'; text: string }> = {
  offline: { label: 'precomputed', tone: 'info', text: 'Published artifacts from an offline pipeline; not re-run by this app.' },
  'pypsa-preset': { label: 'live where allowed', tone: 'accent', text: 'Solved live by the API when the grid allows it; otherwise the published artifact is served.' },
}

/**
 * Top-of-page guide for a research page: one card per published study shown on it, with the
 * question it asks (study summary), the engine, how its numbers are obtained, a jump link to its
 * section and the Research Workbench entry (assumptions, limitations, references, reproduction
 * manifest). Copy comes from the study definitions; no result values are shown here.
 */
export function StudyGuide({ route }: { route: string }) {
  const catalog = useArtifactCatalog()
  const studies = STUDIES.filter((s) => s.detailRoute && s.detailRoute.path.split('#')[0] === route)
  const networkOf = useMemo(() => {
    const out = new Map<string, string>()
    for (const e of buildWorkbenchIndex(catalog.data ?? []).entries) if (!out.has(e.study.id)) out.set(e.study.id, e.network)
    return out
  }, [catalog.data])
  if (!studies.length) return null
  return (
    <section aria-labelledby="study-guide-h" className="flex flex-col gap-2" data-testid="study-guide">
      <h2 id="study-guide-h" className="gs-label">
        Studies on this page
      </h2>
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(15rem,1fr))] gap-2">
        {studies.map((s) => {
          const ex = EXECUTION[s.execution]
          const anchor = s.detailRoute!.path.includes('#') ? `#${s.detailRoute!.path.split('#')[1]}` : null
          const net = networkOf.get(s.id)
          const workbench = net ? `/workbench?network=${encodeURIComponent(net)}&study=${encodeURIComponent(s.id)}` : '/workbench'
          return (
            <li key={s.id} className="gs-panel flex min-w-0 flex-col gap-1 px-3 py-2" data-study={s.id}>
              <p className="text-xs font-semibold leading-snug text-fg">
                {anchor ? (
                  <a href={anchor} className="hover:underline">
                    {s.title}
                  </a>
                ) : (
                  s.title
                )}
              </p>
              <p className="line-clamp-2 text-2xs text-fg-muted" title={s.summary}>
                {s.summary}
              </p>
              <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-0.5">
                <Badge tone={ex.tone} title={ex.text}>
                  {ex.label}
                </Badge>
                <Badge title="Engine that produced the artifacts">{s.engine}</Badge>
                <Link
                  to={workbench}
                  className="ml-auto inline-flex min-h-6 items-center gap-1 text-2xs font-semibold text-accent underline underline-offset-2 pointer-coarse:min-h-11"
                >
                  Limits &amp; reproduce <ArrowRight aria-hidden className="size-3" />
                </Link>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
