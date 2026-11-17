import { useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Button, ErrorState, cn } from '../../components/ui'
import { formatNumber, shortHash } from '../../lib/format'
import { downloadBlob } from '../../lib/download'

export interface DownloadItem {
  /** `data-testid` of the button (kept stable for tests). */
  testId: string
  label: ReactNode
  /** What the file is, in one line. */
  description: string
  filename: string
  /** Size and sha256 the server declares for the file, when known before downloading. */
  bytes?: number | null
  sha256?: string | null
  disabled?: boolean
  /** Shown instead of size/hash when disabled. */
  unavailable?: string
  /** Returns the exact bytes to save (never re-serialised server bytes). */
  fetch: () => Promise<Blob>
}

interface Outcome {
  filename: string
  bytes: number
  sha256: string | null
  /** Expected sha256 compared with the saved bytes: true match, false mismatch, null no reference. */
  matches: boolean | null
}

function formatBytes(n: number): string {
  return n < 1024 ? `${formatNumber(n)} B` : n < 1024 * 1024 ? `${formatNumber(n / 1024, 1)} KiB` : `${formatNumber(n / 1024 / 1024, 2)} MiB`
}

async function sha256Hex(blob: Blob): Promise<string | null> {
  // crypto.subtle exists in secure contexts only (https, localhost); without it the hash is not shown.
  if (!globalThis.crypto?.subtle) return null
  const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Downloadable files with what each one is, the size and sha256 the server declares (when known),
 * and feedback after every click in a live region: saved file name, size and the sha256 of the
 * saved bytes (checked against the declared hash where one exists), or the failure.
 */
export function DownloadList({ items, testId = 'downloads-list' }: { items: DownloadItem[]; testId?: string }) {
  const [pending, setPending] = useState<string | null>(null)
  const [done, setDone] = useState<Outcome | null>(null)
  const [failed, setFailed] = useState<{ label: string; error: unknown } | null>(null)

  const save = async (item: DownloadItem) => {
    setPending(item.testId)
    setDone(null)
    setFailed(null)
    try {
      const blob = await item.fetch()
      const sha256 = await sha256Hex(blob).catch(() => null)
      downloadBlob(item.filename, blob)
      setDone({ filename: item.filename, bytes: blob.size, sha256, matches: item.sha256 && sha256 ? item.sha256 === sha256 : null })
    } catch (error) {
      setFailed({ label: item.filename, error })
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col divide-y divide-line/70" data-testid={testId}>
        {items.map((item) => (
          <li key={item.testId} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-1.5 first:pt-0" data-file={item.testId}>
            <Button
              size="sm"
              className="w-32 shrink-0 justify-start pointer-coarse:h-11"
              disabled={item.disabled || pending !== null}
              onClick={() => void save(item)}
              data-testid={item.testId}
              aria-describedby={`${item.testId}-desc`}
            >
              {item.label}
            </Button>
            <div id={`${item.testId}-desc`} className="flex min-w-0 flex-1 basis-48 flex-col gap-0.5 text-xs">
              <span className="text-fg">{item.description}</span>
              <span className="text-2xs text-fg-subtle">
                {item.disabled && item.unavailable ? (
                  item.unavailable
                ) : (
                  <>
                    <code className="font-mono">{item.filename}</code>
                    {item.bytes != null && <> · {formatBytes(item.bytes)}</>}
                    {item.sha256 && (
                      <>
                        {' '}
                        ·{' '}
                        <code className="font-mono" title={item.sha256}>
                          sha256 {shortHash(item.sha256, 16)}
                        </code>
                      </>
                    )}
                  </>
                )}
              </span>
            </div>
          </li>
        ))}
      </ul>
      <p role="status" aria-live="polite" className={cn('text-xs', !done && !pending && 'sr-only')} data-testid="download-status">
        {pending ? (
          'Preparing download…'
        ) : done ? (
          <span className={cn('inline-flex flex-wrap items-center gap-1', done.matches === false ? 'text-warn' : 'text-ok')}>
            {done.matches === false ? <AlertTriangle aria-hidden className="size-3.5 shrink-0" /> : <CheckCircle2 aria-hidden className="size-3.5 shrink-0" />}
            Saved <code className="font-mono">{done.filename}</code> · {formatBytes(done.bytes)}
            {done.sha256 && (
              <>
                {' '}
                · sha256 <code className="font-mono" title={done.sha256}>{shortHash(done.sha256, 16)}</code>
              </>
            )}
            {done.matches === true && ' — matches the stored checksum'}
            {done.matches === false && ' — differs from the stored checksum; do not rely on this file'}
          </span>
        ) : null}
      </p>
      {failed && <ErrorState error={failed.error} title={`Download failed: ${failed.label}`} />}
    </div>
  )
}
