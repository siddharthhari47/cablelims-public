import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './state/authStore'
import { ProtectedRoute } from './components/ProtectedRoute'
import DesktopShell from './components/DesktopShell'
import MobileShell from './components/MobileShell'

import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/scientist/DashboardPage'
import CreateSamplePage from './pages/scientist/CreateSamplePage'
import SampleDetailPage from './pages/scientist/SampleDetailPage'
import AssistantHomePage from './pages/assistant/AssistantHomePage'
import AssistantSamplePage from './pages/assistant/AssistantSamplePage'
import AdminPage from './pages/admin/AdminPage'

function HomeRedirect() {
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={user.role === 'SCIENTIFIC_ASSISTANT' ? '/assistant' : '/dashboard'} replace />
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<HomeRedirect />} />

      <Route
        element={
          <ProtectedRoute roles={['SCIENTIST', 'ADMINISTRATOR']}>
            <DesktopShell />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/samples/new" element={<CreateSamplePage />} />
        <Route path="/samples/:sampleId" element={<SampleDetailPage />} />
      </Route>

      <Route
        element={
          <ProtectedRoute roles={['ADMINISTRATOR']}>
            <DesktopShell />
          </ProtectedRoute>
        }
      >
        <Route path="/admin" element={<AdminPage />} />
      </Route>

      <Route
        element={
          <ProtectedRoute roles={['SCIENTIFIC_ASSISTANT']}>
            <MobileShell />
          </ProtectedRoute>
        }
      >
        <Route path="/assistant" element={<AssistantHomePage />} />
        <Route path="/assistant/samples/:sampleId" element={<AssistantSamplePage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
