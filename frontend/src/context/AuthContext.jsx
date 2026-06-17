import { createContext, useContext, useState, useEffect } from 'react'
import { api } from '../services/api'

const Ctx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)
  const [loading, setLoading] = useState(true)

  /* Restore session from localStorage on page load */
  useEffect(() => {
    const token = localStorage.getItem('ey_token')
    if (!token) { setLoading(false); return }
    api.me()
      .then(setUser)
      .catch(() => localStorage.removeItem('ey_token'))
      .finally(() => setLoading(false))
  }, [])

  async function login(email, password) {
    const data = await api.login(email, password)
    localStorage.setItem('ey_token', data.access_token)
    setUser(data.user)
    return data.user
  }

  function logout() {
    localStorage.removeItem('ey_token')
    setUser(null)
  }

  function updateUser(updated) {
    setUser(updated)
  }

  return (
    <Ctx.Provider value={{ user, loading, login, logout, updateUser }}>
      {children}
    </Ctx.Provider>
  )
}

export const useAuth = () => useContext(Ctx)
