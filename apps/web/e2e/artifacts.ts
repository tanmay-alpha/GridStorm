import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

/** Repository data/artifacts — the same files the local backend serves via /api/v1/artifacts. */
export const ARTIFACTS = path.resolve(import.meta.dirname, '../../../data/artifacts')
export const SCREENSHOTS = path.resolve(import.meta.dirname, '../../../docs/audit/screenshots')

export interface IndexItem {
  artifact_id: string
  kind: string
  network_id: string | null
  title?: string
  [k: string]: unknown
}

export interface ArtifactDoc {
  artifact: { artifact_id: string; payload_sha256: string; engine: string; engine_version: string }
  payload: Record<string, unknown>
}

export function readIndex(engine: string): IndexItem[] | null {
  const p = path.join(ARTIFACTS, engine, 'index.json')
  if (!existsSync(p)) return null
  const doc: { artifacts: IndexItem[] } = JSON.parse(readFileSync(p, 'utf8'))
  return doc.artifacts
}

export function readArtifact(engine: string, item: IndexItem): ArtifactDoc {
  const file = typeof item.path === 'string' ? item.path : `${item.artifact_id}.json`
  return JSON.parse(readFileSync(path.join(ARTIFACTS, engine, file), 'utf8'))
}
