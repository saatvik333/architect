import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Tasks from './pages/Tasks'
import TaskDetail from './pages/TaskDetail'
import Health from './pages/Health'
import Proposals from './pages/Proposals'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/tasks" replace />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/tasks/:taskId" element={<TaskDetail />} />
        <Route path="/health" element={<Health />} />
        <Route path="/proposals" element={<Proposals />} />
      </Routes>
    </Layout>
  )
}

export default App
