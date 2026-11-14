import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

/**
 * Display-mode KaTeX rendering of a static, repository-authored TeX string. The rendered equation
 * is exposed as one image named by `label` (aria-label is prohibited on a role-less div); the
 * horizontal scroller around it stays a plain container.
 */
export function TeX({ tex, label }: { tex: string; label: string }) {
  const html = useMemo(() => katex.renderToString(tex, { displayMode: true, throwOnError: false, output: 'htmlAndMathml' }), [tex])
  return (
    <div className="overflow-x-auto py-1 text-fg">
      <div role="img" aria-label={label} dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  )
}
