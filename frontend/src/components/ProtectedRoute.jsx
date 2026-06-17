import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div style={{
        height: '100vh', display: 'flex', alignItems: 'center',
        justifyContent: 'center', background: '#0E0F1A', color: '#FFE600',
        fontSize: 14, fontFamily: 'Inter, sans-serif', gap: 10,
      }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
          stroke="#FFE600" strokeWidth="2.5"
          style={{ animation: 'spin 0.75s linear infinite' }}>
          <circle cx="12" cy="12" r="10" strokeOpacity="0.25"/>
          <path d="M12 2a10 10 0 0110 10"/>
        </svg>
        <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
        Loading…
      </div>
    )
  }

  if (!user) return <Navigate to="/" replace />
  if (adminOnly && user.role !== 'admin') return <Navigate to="/" replace />
  return children
}
