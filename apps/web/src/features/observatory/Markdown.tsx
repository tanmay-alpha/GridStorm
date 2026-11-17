import type { ReactNode } from 'react'

const INLINE = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)\s]+\))/g

function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 1)
      return (
        <code key={i} className="break-all rounded bg-surface-2 px-1 font-mono text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      )
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part)
    if (link) {
      const href = link[2]!
      // Only absolute http(s) links are followed; anything else stays plain text.
      return /^https?:\/\//.test(href) ? (
        <a key={i} href={href} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2">
          {link[1]}
        </a>
      ) : (
        <span key={i}>{link[1]}</span>
      )
    }
    return part
  })
}

const cells = (row: string) =>
  row
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((c) => c.trim())

/**
 * The small Markdown subset catalog descriptions use (paragraphs, bullet lists, pipe tables, bold,
 * inline code, http links), rendered as React elements — never as HTML, so catalog text cannot
 * inject markup.
 */
export function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks = text.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean)
  return (
    <div className={className}>
      {blocks.map((block, i) => {
        const lines = block.split('\n')
        if (lines.every((l) => l.trim().startsWith('|'))) {
          const separator = lines.find((l) => /^[\s|:-]+$/.test(l))
          const [head, ...body] = lines.filter((l) => l !== separator).map(cells)
          // `---:` in the separator row right-aligns that column (numbers).
          const right = separator ? cells(separator).map((c) => c.endsWith(':')) : []
          return (
            <div key={i} className="overflow-x-auto" role="region" aria-label="Description table" tabIndex={0}>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-fg-muted">
                    {head?.map((c, j) => (
                      <th key={j} scope="col" className={`px-2 py-1 font-semibold ${right[j] ? 'text-right' : ''}`}>
                        {inline(c)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((r, k) => (
                    <tr key={k} className="border-b border-line/60">
                      {r.map((c, j) => (
                        <td key={j} className={`tabular px-2 py-1 ${right[j] ? 'text-right' : ''}`}>
                          {inline(c)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
        if (lines.every((l) => /^\s*[-*] /.test(l)))
          return (
            <ul key={i} className="flex list-disc flex-col gap-1 pl-5">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*[-*] /, ''))}</li>
              ))}
            </ul>
          )
        return <p key={i}>{inline(lines.join(' '))}</p>
      })}
    </div>
  )
}
