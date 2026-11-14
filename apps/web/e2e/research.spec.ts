import { test, expect, type Page } from '@playwright/test'
import { formatNumber } from '../src/lib/format'
import { readArtifact, readIndex, type IndexItem } from './artifacts'

/**
 * Research pages against the real local backend. Every expected value is read from the same
 * data/artifacts files the backend serves, so a mismatch means the UI misrendered an artifact.
 */

function collectErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  return errors
}

const available = (items: IndexItem[] | null) => (items ?? []).filter((i) => i.available !== false)

test('/benchmarks renders StormBench, StormRisk, cross-engine and PyPSA artifacts', async ({ page }) => {
  const errors = collectErrors(page)
  await page.goto('/benchmarks')
  await expect(page.getByRole('heading', { level: 1, name: 'Benchmarks' })).toBeVisible()

  // StormBench: every per-case row of the published summary.
  const sbIndex = available(readIndex('stormbench'))
  const summary = sbIndex.find((i) => i.artifact_id === 'stormbench-summary')
  expect(summary, 'stormbench-summary in data/artifacts/stormbench/index.json').toBeTruthy()
  const sbDoc = readArtifact('stormbench', summary!)
  const cases = sbDoc.payload.cases as { case: string }[]
  const sb = page.locator('#stormbench')
  await expect(sb.getByTestId('artifact-meta').first()).toContainText(`sha256 ${sbDoc.artifact.payload_sha256.slice(0, 12)}`)
  const sbTable = sb.getByRole('table', { name: 'StormBench results per case' })
  await expect(sbTable.locator('tbody tr')).toHaveCount(cases.length)
  for (const c of cases) await expect(sbTable).toContainText(c.case)

  // StormRisk: EENS, CI and LOLP exactly as published.
  const riskItem = available(readIndex('stormrisk'))[0]
  expect(riskItem, 'a StormRisk study in data/artifacts/stormrisk/index.json').toBeTruthy()
  const risk = readArtifact('stormrisk', riskItem)
  const est = risk.payload.estimates as Record<string, number | string>
  const rs = page.locator('#stormrisk')
  await expect(rs.getByTestId('artifact-meta')).toContainText(`sha256 ${risk.artifact.payload_sha256.slice(0, 12)}`)
  await expect(rs.getByTestId('artifact-meta')).toContainText('precomputed')
  await expect(rs).toContainText(
    `95 % CI ${formatNumber(est.ci95_low_mwh as number)} – ${formatNumber(est.ci95_high_mwh as number)} MWh`,
  )
  await expect(rs).toContainText(`Estimator ${est.estimator}`)
  await expect(rs).toContainText(`${formatNumber(est.n_samples as number)} samples`)
  await expect(rs.getByRole('img', { name: /Running EENS estimate/ })).toBeVisible()

  // Cross-engine: one table row per published check, verdicts as published.
  const ceItems = available(readIndex('cross-engine'))
  const checks = ceItems.flatMap((i) => readArtifact('cross-engine', i).payload.checks as { verdict: string }[])
  const ce = page.locator('#cross-engine').getByRole('table', { name: 'Cross-engine agreement checks' })
  await expect(ce.locator('tbody tr')).toHaveCount(checks.length)
  for (const verdict of new Set(checks.map((c) => c.verdict))) {
    // The table shows verdict codes with underscores as spaces (e.g. EXPECTED DIFFERENCE).
    const shown = ce.getByText(verdict.replaceAll('_', ' '), { exact: true })
    await expect(shown).toHaveCount(checks.filter((c) => c.verdict === verdict).length)
  }

  // PyPSA preset artifacts: one row per published simulation, titled from the index.
  const pypsa = available(readIndex('pypsa'))
  const pt = page.locator('#pypsa').getByRole('table', { name: 'Precomputed PyPSA preset runs' })
  await expect(pt.locator('tbody tr')).toHaveCount(pypsa.length)
  for (const p of pypsa) await expect(pt).toContainText(p.network_id ?? '')

  // pandapower AC reference validation: one row per comparison, all within tolerance as published.
  const acItem = available(readIndex('pandapower')).find((i) => i.kind === 'benchmark')
  expect(acItem, 'a pandapower benchmark artifact in data/artifacts/pandapower/index.json').toBeTruthy()
  const ac = readArtifact('pandapower', acItem!).payload as {
    matpower_cases: unknown[]
    matpower_testsuite: unknown
    pandapower_builtin: unknown[]
    summary: { all_pass: boolean }
  }
  const acRows = ac.matpower_cases.length + (Array.isArray(ac.matpower_testsuite) ? ac.matpower_testsuite.length : 1) + ac.pandapower_builtin.length
  const acPanel = page.locator('#ac-reference')
  await expect(acPanel.getByRole('table', { name: 'AC power-flow comparisons against reference solvers' }).locator('tbody tr')).toHaveCount(acRows)
  await expect(acPanel.getByTestId('ac-reference-summary')).toContainText(
    `of ${acRows} comparisons within tolerance · artifact verdict: ${ac.summary.all_pass ? 'all pass' : 'not all pass'}`,
  )
  expect(errors).toEqual([])
})

test('/contingency renders pandapower N-1 (when published) and Crisis Advisor artifacts', async ({ page }) => {
  const errors = collectErrors(page)
  const n1 = available(readIndex('pandapower')).filter((i) => i.kind === 'n_minus_1')
  const adv = available(readIndex('advisor'))
  const network = [...new Set([...n1, ...adv].map((i) => i.network_id).filter((n): n is string => !!n))].sort()[0]
  await page.goto('/contingency')
  await expect(page.getByRole('heading', { level: 1, name: 'Contingency analysis' })).toBeVisible()

  const n1Item = n1.find((i) => i.network_id === network)
  if (n1Item) {
    const doc = readArtifact('pandapower', n1Item)
    const counts = (doc.payload.summary as { class_counts: Record<string, number> }).class_counts
    for (const [cls, n] of Object.entries(counts)) await expect(page.getByTestId(`count-${cls}`)).toHaveText(String(n))
    await expect(page.locator('#n1').getByTestId('artifact-meta')).toContainText(doc.artifact.payload_sha256.slice(0, 12))
  } else {
    test.info().annotations.push({ type: 'note', description: `no pandapower N-1 index entry for ${network}` })
    await expect(page.locator('#n1')).toContainText(`No pandapower N-1 artifact for ${network}.`)
  }

  const advItem = adv.find((i) => i.network_id === network)
  expect(advItem, `an advisor artifact for the default network ${network}`).toBeTruthy()
  const advDoc = readArtifact('advisor', advItem!)
  await expect(page.getByTestId('security-statement')).toHaveText(advDoc.payload.security_statement as string)
  await expect(page.locator('#advisor').getByTestId('artifact-meta')).toContainText(advDoc.artifact.payload_sha256.slice(0, 12))
  expect(errors).toEqual([])
})

test('/operations replays a Grid2Op episode with per-agent KPIs from the index', async ({ page }) => {
  const errors = collectErrors(page)
  const items = available(readIndex('grid2op'))
  const first = items[0]
  const group = items.filter((i) => i.chronics_id === first.chronics_id && i.variant === first.variant)
  await page.goto('/operations')
  await expect(page.getByRole('heading', { level: 1, name: 'Operations replay' })).toBeVisible()
  const kpis = page.locator('#kpis').getByRole('table')
  await expect(kpis.locator('tbody tr')).toHaveCount(group.length)
  for (const [i, it] of group.entries()) {
    const k = it.kpis as { survival_steps: number; max_steps: number }
    const row = kpis.locator('tbody tr').nth(i)
    await expect(row).toContainText(String(it.agent))
    await expect(row).toContainText(`${formatNumber(k.survival_steps, 0)} / ${formatNumber(k.max_steps, 0)}`)
  }
  const replay = page.locator('#replay')
  await expect(replay.getByTestId('artifact-meta')).toContainText(String(first.artifact_id))
  const slider = replay.getByRole('slider')
  await slider.focus()
  await page.keyboard.press('ArrowRight')
  await expect(replay).toContainText('Step 1 of', { ignoreCase: true })
  expect(errors).toEqual([])
})

test('/methods states the disclaimer, equations and provenance', async ({ page }) => {
  const errors = collectErrors(page)
  await page.goto('/methods')
  await expect(page.getByRole('heading', { level: 1, name: 'Methods' })).toBeVisible()
  await expect(page.getByText('Not a real-time control system.')).toBeVisible()
  await expect(page.locator('#equations .katex').first()).toBeVisible()
  await expect(page.locator('#data')).toContainText('scigrid-de')
  expect(errors).toEqual([])
})
