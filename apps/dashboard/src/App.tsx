import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { ErrorBoundary } from './components/ErrorBoundary'

const Tasks = lazy(() => import('./pages/Tasks'))
const TaskDetail = lazy(() => import('./pages/TaskDetail'))
const Health = lazy(() => import('./pages/Health'))
const Proposals = lazy(() => import('./pages/Proposals'))
const Escalations = lazy(() => import('./pages/Escalations'))
const Progress = lazy(() => import('./pages/Progress'))
const Budget = lazy(() => import('./pages/Budget'))
const Activity = lazy(() => import('./pages/Activity'))

function App() {
  return (
    <ErrorBoundary>
      <Layout>
        <Suspense fallback={<div className="text-gray-500 p-4">Loading...</div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/progress" replace />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/tasks/:taskId" element={<TaskDetail />} />
            <Route path="/health" element={<Health />} />
            <Route path="/proposals" element={<Proposals />} />
            <Route path="/escalations" element={<Escalations />} />
            <Route path="/progress" element={<Progress />} />
            <Route path="/budget" element={<Budget />} />
            <Route path="/activity" element={<Activity />} />
          </Routes>
        </Suspense>
      </Layout>
    </ErrorBoundary>
  )
}

export default App
