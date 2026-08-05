import { Navigate } from 'react-router-dom'
import { useAuthStore, type Role } from '../state/authStore'

export function ProtectedRoute({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  if (!roles.includes(user.role)) {
    return <Navigate to={user.role === 'SCIENTIFIC_ASSISTANT' ? '/assistant' : '/dashboard'} replace />
  }
  return <>{children}</>
}
