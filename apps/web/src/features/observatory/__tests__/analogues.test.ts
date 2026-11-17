import { describe, expect, it } from 'vitest'
import type { ArtifactIndexItem, DatasetEntry, ScenarioRecord } from '../../../api/types'
import { analogueFacts, indexUnservedMwh, stressLinks } from '../analogues'
import captured from './analogue-fixtures.json'
import { NASA } from './fixtures'

const ENTRY = captured.entry as unknown as DatasetEntry
const RECORDS = captured.scenarios.items as unknown as ScenarioRecord[]
const ARTIFACTS = captured.artifacts.items as unknown as ArtifactIndexItem[]
const record = (id: string) => RECORDS.find((r) => r.id === id)!

describe('stress windows → analogue presets', () => {
  it('pairs each stress-day window of the captured catalog entry with its preset', () => {
    const links = stressLinks(ENTRY)
    expect(links.map((l) => [l.day, l.scenarioId])).toEqual([
      ['2015-01-20', 'observed-dunkelflaute-2015-01-20'],
      ['2017-01-24', 'observed-high-load-low-res-2017-01-24'],
      ['2017-12-13', 'observed-peak-load-2017-12-13'],
    ])
    expect(links[0]!.dayStartMs).toBe(Date.UTC(2015, 0, 20))
    expect(links[0]!.dayEndMs).toBe(Date.UTC(2015, 0, 21))
  })

  it('links a ±3 d window only to the preset whose stress day it contains', () => {
    const d = { ...NASA, links: { ...NASA.links, scenario_ids: ENTRY.links.scenario_ids } }
    expect(stressLinks(d).map((l) => [l.window.label, l.scenarioId])).toEqual([
      ['Dunkelflaute, January 2015', 'observed-dunkelflaute-2015-01-20'],
      ['High load, low renewables, January 2017', 'observed-high-load-low-res-2017-01-24'],
      ['Peak load, December 2017', 'observed-peak-load-2017-12-13'],
    ])
    expect(stressLinks(NASA)).toEqual([])
  })

  it('states only what the preset states: events, reference day, criterion', () => {
    const dunkel = analogueFacts(record('observed-dunkelflaute-2015-01-20').spec)
    expect(dunkel.demand).toMatchObject({ hours: 24 })
    expect(dunkel.demand!.min).toBeGreaterThan(1)
    expect(dunkel.renewables).toEqual([
      { carrier: 'Wind Onshore', value: 0.05 },
      { carrier: 'Wind Offshore', value: 0.1 },
      { carrier: 'Solar', value: 0.25 },
    ])
    expect(dunkel.referenceDay).toBe('2015-01-01')
    expect(dunkel.criterion).toBe('lowest daily-mean wind+solar capacity factor over complete UTC days in months [12, 1, 2]')
    expect(dunkel.snapshots).toBe(24)
    // Peak-load day: onshore wind keeps the network's availability (no event).
    const peak = analogueFacts(record('observed-peak-load-2017-12-13').spec)
    expect(peak.renewables.map((r) => r.carrier)).toEqual(['Wind Offshore', 'Solar'])
    expect(peak.referenceDay).toBe('2018-01-01')
    expect(peak.criterion).toBe('maximum hourly load over all complete UTC days')
    expect(analogueFacts(record('observed-high-load-low-res-2017-01-24').spec).criterion).toContain('0.90 quantile of daily-mean load')
  })

  it('reads unserved energy from the artifact index, never inventing a value', () => {
    expect(indexUnservedMwh(ARTIFACTS, 'observed-dunkelflaute-2015-01-20')).toBeCloseTo(2721.006897, 6)
    expect(indexUnservedMwh(ARTIFACTS, 'observed-high-load-low-res-2017-01-24')).toBeCloseTo(4731.453896, 6)
    expect(indexUnservedMwh(ARTIFACTS, 'observed-peak-load-2017-12-13')).toBeCloseTo(4429.345555, 6)
    expect(indexUnservedMwh(ARTIFACTS, 'scigrid-de-baseline')).toBe(0)
    expect(indexUnservedMwh(ARTIFACTS, 'unknown')).toBeNull()
    expect(indexUnservedMwh(undefined, 'scigrid-de-baseline')).toBeNull()
  })
})
