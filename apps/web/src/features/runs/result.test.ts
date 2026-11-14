import { describe, expect, it } from 'vitest'
import { snapshotLabels } from './result'
import type { GridstormResult } from '../../api/types'

const withSnapshots = (snapshots: string[]) => ({ snapshots }) as unknown as GridstormResult

describe('snapshotLabels', () => {
  it('keeps the model clock of timezone-naive snapshots regardless of the browser offset', () => {
    // vite.config.ts pins TZ=Asia/Kolkata for tests, so a local-time parse would shift by +05:30.
    expect(snapshotLabels(withSnapshots(['2015-01-01T00:00:00', '2015-01-01T09:00:00']))).toEqual([
      '01-01 00:00',
      '01-01 09:00',
    ])
  })

  it('converts explicitly zoned timestamps to UTC', () => {
    expect(snapshotLabels(withSnapshots(['2015-01-01T05:30:00+05:30']))).toEqual(['01-01 00:00'])
  })
})
