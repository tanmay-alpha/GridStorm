import { useJobs, useScenarios } from '../../api/hooks'
import type { Job } from '../../api/types'
import { useExecutionPolicy } from '../studio/useExecutionPolicy'
import { baselinePlan, type BaselinePlan } from './baseline'

/** The baseline plan of `job` once presets and jobs are loaded (null while loading). */
export function useBaselinePlan(job: Job): { plan: BaselinePlan | null; error: unknown } {
  const scenarios = useScenarios()
  const jobs = useJobs()
  const { policy } = useExecutionPolicy()
  const error = scenarios.error ?? jobs.error
  if (error || !scenarios.data || !jobs.data) return { plan: null, error }
  return { plan: baselinePlan(job, scenarios.data, jobs.data, policy), error: null }
}
