import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { createBrowserRouter } from 'react-router'
import { AppLayout } from './components/layout/AppLayout'
import { RouteError } from './components/layout/RouteError'
import { SkeletonBlock } from './components/ui'

function page(load: () => Promise<{ default: ComponentType }>): ReactNode {
  const C = lazy(load)
  return (
    <Suspense
      fallback={
        <div className="p-4">
          <SkeletonBlock rows={6} label="Loading page" />
        </div>
      }
    >
      <C />
    </Suspense>
  )
}

const research = () => import('./features/research')

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: page(() => import('./features/home/HomePage')) },
      { path: 'explore', element: page(() => import('./features/explorer/ExplorerPage')) },
      { path: 'data', element: page(() => import('./features/observatory/ObservatoryPage')) },
      { path: 'data/:datasetId', element: page(() => import('./features/observatory/DatasetPage')) },
      { path: 'studio', element: page(() => import('./features/studio/StudioPage')) },
      { path: 'runs/:id', element: page(() => import('./features/runs/RunPage')) },
      { path: 'compare', element: page(() => import('./features/compare/ComparePage')) },
      { path: 'mitigation', element: page(() => import('./features/mitigation/MitigationPage')) },
      { path: 'mitigation/:studyId', element: page(() => import('./features/mitigation/MitigationPage')) },
      { path: 'library', element: page(() => import('./features/library/LibraryPage')) },
      { path: 'contingency', element: page(() => research().then((m) => ({ default: m.ContingencyPage }))) },
      { path: 'operations', element: page(() => research().then((m) => ({ default: m.OperationsPage }))) },
      { path: 'benchmarks', element: page(() => research().then((m) => ({ default: m.BenchmarksPage }))) },
      { path: 'methods', element: page(() => research().then((m) => ({ default: m.MethodsPage }))) },
      { path: 'workbench', element: page(() => import('./features/workbench').then((m) => ({ default: m.WorkbenchPage }))) },
      { path: '*', element: page(() => import('./components/layout/NotFound')) },
    ],
  },
])
