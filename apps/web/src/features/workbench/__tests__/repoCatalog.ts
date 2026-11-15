/// <reference types="node" />
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import type { ArtifactIndexItem } from '../../../api/types'

/** Repository root relative to vitest's cwd (apps/web). */
export const REPO = '../..'

/** The committed artifact documents, keyed `engine/artifact_id`. */
export function readDoc(engine: string, artifactId: string): { artifact: Record<string, unknown>; payload: Record<string, unknown> } {
  return JSON.parse(readFileSync(`${REPO}/data/artifacts/${engine}/${artifactId}.json`, 'utf8'))
}

/**
 * The catalog GET /api/v1/artifacts?include=header would serve for the committed data
 * (services/api precomputed.py: index rows + engine/available + the file's `artifact` header).
 */
export function repoCatalog(): ArtifactIndexItem[] {
  const root = `${REPO}/data/artifacts`
  const out: ArtifactIndexItem[] = []
  for (const d of readdirSync(root, { withFileTypes: true }).filter((x) => x.isDirectory()).sort((a, b) => a.name.localeCompare(b.name))) {
    const indexPath = `${root}/${d.name}/index.json`
    if (!existsSync(indexPath)) continue
    const raw = JSON.parse(readFileSync(indexPath, 'utf8')) as { artifacts?: Record<string, unknown>[] } | Record<string, unknown>[]
    for (const e of Array.isArray(raw) ? raw : (raw.artifacts ?? [])) {
      const id = String(e.artifact_id)
      const available = existsSync(`${root}/${d.name}/${id}.json`)
      out.push({
        ...e,
        engine: d.name,
        artifact_id: id,
        kind: e.kind as ArtifactIndexItem['kind'],
        network_id: (e.network_id as string | null) ?? null,
        title: (e.title as string) ?? null,
        available,
        header: available ? readDoc(d.name, id).artifact : null,
      })
    }
  }
  return out
}
