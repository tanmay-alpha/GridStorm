import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

/** Display-mode KaTeX rendering of a static, repository-authored TeX string (MathML included for AT). */
export function TeX({ tex, label }: { tex: string; label: string }) {
  const html = useMemo(() => katex.renderToString(tex, { displayMode: true, throwOnError: false, output: 'htmlAndMathml' }), [tex])
  return <div className="overflow-x-auto py-1 text-fg" aria-label={label} dangerouslySetInnerHTML={{ __html: html }} />
}
