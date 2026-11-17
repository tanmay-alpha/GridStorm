import type { ReactNode } from 'react'
import { FileText } from 'lucide-react'
import type { DatasetEntry } from '../../api/types'
import { Button, Drawer, KeyValue, ProvenanceLabel } from '../../components/ui'
import { formatTimestamp, NO_VALUE } from '../../lib/format'
import { docUrl } from '../research/content/methods'
import { REDISTRIBUTION_TEXT } from './vocabulary'

function External({ href, children }: { href: string | null; children: ReactNode }) {
  if (!href) return <>{children}</>
  return (
    <a href={href} target="_blank" rel="noreferrer" className="break-all text-accent underline underline-offset-2">
      {children}
    </a>
  )
}

function Hash({ value }: { value: string | null | undefined }) {
  return value ? <code className="break-all font-mono text-2xs">{value}</code> : <>{NO_VALUE}</>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t border-line pt-3">
      <h3 className="gs-label">{title}</h3>
      {children}
    </section>
  )
}

/**
 * Provenance drawer (shared `Drawer`: focus trap, Escape closes, focus returns to the trigger) with
 * the full record: original publication, licence, version, checksums, transformations and the
 * attribution text exactly as the source asks for it.
 */
export function ProvenanceDrawer({ d }: { d: DatasetEntry }) {
  const s = d.source
  return (
    <Drawer
      title="Provenance & licence"
      description={d.title}
      testId="provenance-drawer"
      className="md:w-[min(34rem,100vw)]"
      trigger={
        <Button size="sm" data-testid="open-provenance">
          <FileText aria-hidden className="size-3.5" />
          Provenance &amp; licence
        </Button>
      }
    >
          <div className="flex flex-col gap-4 text-xs">
            <div className="flex flex-col gap-1">
              <ProvenanceLabel value={d.provenance} label="Provenance" />
              <p className="text-fg-muted">{d.data_nature}</p>
            </div>

            <Section title="Original publication">
              <KeyValue
                rows={[
                  ['Source', <External href={s.url}>{s.name}</External>],
                  ['Publisher', s.publisher ?? NO_VALUE],
                  ['Version', s.version ?? NO_VALUE],
                  ['DOI', s.doi ? <External href={s.doi.startsWith('http') ? s.doi : `https://doi.org/${s.doi}`}>{s.doi}</External> : NO_VALUE],
                  ['Retrieved', s.retrieved_at ? formatTimestamp(s.retrieved_at) : NO_VALUE],
                  ['Source sha256', <Hash value={s.source_sha256} />],
                ]}
              />
            </Section>

            <Section title="Licence">
              <KeyValue
                rows={[
                  ['Licence', <External href={s.license.url}>{`${s.license.name} (${s.license.id})`}</External>],
                  ['Redistribution', <span data-testid="redistribution">{REDISTRIBUTION_TEXT[s.license.redistribution] ?? s.license.redistribution}</span>],
                  ['CSV export', d.exportable ? 'Offered' : 'Not offered'],
                ]}
              />
            </Section>

            <Section title="Attribution (verbatim)">
              <blockquote data-testid="attribution-text" className="whitespace-pre-wrap rounded border border-line bg-surface-2 p-2 font-mono text-2xs text-fg">
                {s.attribution}
              </blockquote>
            </Section>

            <Section title="Bundle file and checksums">
              {d.artifact ? (
                <KeyValue
                  rows={[
                    ['File', <code className="break-all font-mono text-2xs">{d.artifact.path}</code>],
                    ['sha256', <Hash value={d.artifact.sha256} />],
                    ['Size', `${d.artifact.bytes.toLocaleString('en-US')} bytes`],
                    ['Rows', d.artifact.rows.toLocaleString('en-US')],
                  ]}
                />
              ) : (
                <p className="text-fg-muted">No bundled data file: this entry describes data served elsewhere in GridStorm.</p>
              )}
            </Section>

            <Section title={`Transformations (version ${d.transformation_version || NO_VALUE})`}>
              {d.transformations.length ? (
                <ol className="flex list-decimal flex-col gap-1.5 pl-5">
                  {d.transformations.map((t, i) => (
                    <li key={`${t.step}-${i}`}>
                      <span className="font-medium text-fg">{t.step}</span>
                      <span className="text-fg-muted"> — {t.description}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-fg-muted">No transformations recorded.</p>
              )}
            </Section>

            {d.links.docs.length > 0 && (
              <Section title="Documentation">
                <ul className="flex flex-col gap-1">
                  {d.links.docs.map((doc) => (
                    <li key={doc.href}>
                      {/* Repository paths ("docs/…") open on GitHub; absolute URLs and app routes as given. */}
                      <External href={/^(https?:)?\/\//.test(doc.href) || doc.href.startsWith('/') ? doc.href : docUrl(doc.href)}>{doc.label}</External>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
          </div>
    </Drawer>
  )
}
