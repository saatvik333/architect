import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { ErrorBoundary } from './components/ErrorBoundary'

const Tasks = lazy(() => import('./pages/Tasks'))
const TaskDetail = lazy(() => import('./pages/TaskDetail'))
const Health = lazy(() => import('./pages/Health'))
const Proposals = lazy(() => import('./pages/Proposals'))

function App() {
  return (
    <ErrorBoundary>
      <Layout>
        <Suspense fallback={<div className="text-gray-500 p-4">Loading...</div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/tasks" replace />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/tasks/:taskId" element={<TaskDetail />} />
            <Route path="/health" element={<Health />} />
            <Route path="/proposals" element={<Proposals />} />
          </Routes>
        </Suspense>
      </Layout>
    </ErrorBoundary>
  )
}

export default App
