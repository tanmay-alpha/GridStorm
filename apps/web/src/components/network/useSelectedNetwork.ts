import { useCallback } from 'react'
import { useSearchParams } from 'react-router'
import { useNetworks } from '../../api/hooks'

/**
 * Network selection stored in the `?network=` URL parameter (shareable, back-button friendly).
 * Defaults to the first network returned by the API — never a hard-coded id.
 */
export function useSelectedNetwork() {
  const [params, setParams] = useSearchParams()
  const networks = useNetworks()
  const requested = params.get('network')
  const list = networks.data ?? []
  const id = requested && list.some((n) => n.id === requested) ? requested : (list[0]?.id ?? null)
  const summary = list.find((n) => n.id === id) ?? null
  const setId = useCallback(
    (next: string) =>
      setParams(
        (p) => {
          const q = new URLSearchParams(p)
          q.set('network', next)
          return q
        },
        { replace: false },
      ),
    [setParams],
  )
  return { networks, list, id, summary, setId, unknownRequested: !!requested && list.length > 0 && id !== requested }
}
