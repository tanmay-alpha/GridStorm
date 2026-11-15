import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'
import { readArtifact, readIndex } from './artifacts'

/**
 * Research Workbench against the real local backend (services/api serving data/artifacts):
 * pick a network and a study, check provenance against the committed artifact, download the
 * reproduction manifest and compare it with the artifact headers on disk.
 */
test('/workbench walks network → study and downloads a reproduction manifest', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))

  const n1 = (readIndex('pandapower') ?? []).find((i) => i.kind === 'n_minus_1' && i.network_id === 'pglib-case14-ieee')
  expect(n1, 'n1-pglib-case14-ieee in data/artifacts/pandapower/index.json').toBeTruthy()
  const doc = readArtifact('pandapower', n1!) as unknown as { artifact: Record<string, unknown>; payload: { summary: { contingency_count: number } } }

  await page.goto('/workbench')
  await expect(page.getByRole('heading', { level: 1, name: 'Research workbench' })).toBeVisible()
  const nav = page.getByRole('navigation', { name: 'Choose a network and a study' })
  // Radios are controlled by the URL (?network=&study=): click, then assert the routed state.
  await nav.getByRole('radio', { name: /^IEEE 14-bus|^pglib-case14-ieee/ }).click()
  await expect(page).toHaveURL(/network=pglib-case14-ieee/)
  await nav.getByRole('radio', { name: /pandapower AC N-1 contingency screening/ }).click()
  await expect(page).toHaveURL(/network=pglib-case14-ieee&study=pandapower-n1/)

  const detail = page.getByTestId('study-detail')
  await expect(detail.getByTestId('execution-mode')).toHaveAttribute('data-mode', 'offline-only')
  await expect(detail.getByTestId('artifact-meta').first()).toContainText(String(doc.artifact.payload_sha256).slice(0, 12))
  await expect(detail.getByTestId('study-metrics')).toContainText(String(doc.payload.summary.contingency_count))
  await expect(detail.getByTestId('study-references')).not.toBeEmpty()
  await expect(detail.getByTestId('reproduction-commands')).toContainText('scripts/run_studies.py')

  const [download] = await Promise.all([page.waitForEvent('download'), detail.getByTestId('download-manifest').click()])
  expect(download.suggestedFilename()).toBe('gridstorm-manifest-pandapower-n1-pglib-case14-ieee.json')
  const manifest = JSON.parse(readFileSync(await download.path(), 'utf8'))
  expect(manifest.schema_version).toBe('gridstorm-reproduction-manifest/1.0')
  expect(manifest.execution_mode.value).toBe('offline-only')
  const art = manifest.artifacts.find((a: { artifact_id: string }) => a.artifact_id === n1!.artifact_id)
  expect(art.header.payload_sha256).toBe(doc.artifact.payload_sha256)
  expect(art.header.command).toBe(doc.artifact.command)
  expect(art.header.inputs).toEqual(doc.artifact.inputs)

  // A PyPSA preset on the same network is labelled by the deployment's live-execution flag.
  await nav.getByRole('radio', { name: /PyPSA preset scenarios/ }).click()
  await expect(nav.getByRole('radio', { name: /PyPSA preset scenarios/ })).toBeChecked()
  await expect(detail.getByTestId('execution-mode')).toHaveAttribute('data-mode', /^(live|precomputed)$/)
  await expect(detail.getByTestId('study-metrics')).toContainText('Outcome')
  await expect(detail.getByTestId('study-metrics')).not.toContainText(/\bEUR\b/)
  expect(errors).toEqual([])
})
