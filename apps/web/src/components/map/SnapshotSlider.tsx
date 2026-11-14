import { useEffect, useId, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { Button } from '../ui'

/**
 * Snapshot selector with optional replay. Replay steps one snapshot per `intervalMs` through
 * the real result series; it stops at the last snapshot.
 */
export function SnapshotSlider({
  labels,
  value,
  onChange,
  intervalMs = 600,
}: {
  labels: string[]
  value: number
  onChange: (t: number) => void
  intervalMs?: number
}) {
  const id = useId()
  const [playing, setPlaying] = useState(false)
  const last = Math.max(0, labels.length - 1)
  const atEnd = value >= last
  const isPlaying = playing && !atEnd

  useEffect(() => {
    if (!isPlaying) return
    const t = setTimeout(() => onChange(value + 1), intervalMs)
    return () => clearTimeout(t)
  }, [isPlaying, value, onChange, intervalMs])

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Button
        size="sm"
        onClick={() => {
          if (isPlaying) return setPlaying(false)
          if (atEnd) onChange(0)
          setPlaying(true)
        }}
        aria-label={isPlaying ? 'Pause replay' : 'Replay snapshots'}
        disabled={labels.length < 2}
        data-testid="replay-toggle"
      >
        {isPlaying ? <Pause aria-hidden className="size-3.5" /> : <Play aria-hidden className="size-3.5" />}
        {isPlaying ? 'Pause' : 'Replay'}
      </Button>
      <label htmlFor={id} className="gs-label">
        Snapshot
      </label>
      <input
        id={id}
        type="range"
        min={0}
        max={last}
        step={1}
        value={value}
        onChange={(e) => {
          setPlaying(false)
          onChange(Number(e.target.value))
        }}
        className="min-w-40 flex-1 accent-[var(--gs-accent)]"
        aria-valuetext={`${value + 1} of ${labels.length}: ${labels[value] ?? ''}`}
        data-testid="snapshot-slider"
      />
      <span className="tabular w-48 shrink-0 text-fg" data-testid="snapshot-label">
        {value + 1}/{labels.length} · {labels[value] ?? '—'}
      </span>
    </div>
  )
}
