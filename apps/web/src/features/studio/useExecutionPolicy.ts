import { useMemo } from 'react'
import { useArtifactIndex, useNetworks } from '../../api/hooks'
import type { ExecutionPolicy } from './flow'

/** Live-execution policy of the deployment from GET /networks and the precomputed simulation index. */
export function useExecutionPolicy() {
  const networks = useNetworks()
  const simArtifacts = useArtifactIndex({ kind: 'simulation' })
  const policy = useMemo<ExecutionPolicy>(
    () => ({
      live: new Map((networks.data ?? []).map((n) => [n.id, n.live_execution])),
      precomputed: simArtifacts.data
        ? new Set(
            simArtifacts.data
              .filter((a) => a.available !== false)
              .map((a) => a.scenario_hash)
              .filter((h): h is string => typeof h === 'string'),
          )
        : null,
    }),
    [networks.data, simArtifacts.data],
  )
  return { policy, simArtifacts }
}
