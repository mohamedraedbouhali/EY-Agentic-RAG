const BASE = 'http://localhost:8000'

function headers() {
  const token = localStorage.getItem('ey_token')
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function req(method, path, body, timeoutMs = 10000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${BASE}${path}`, {
      method,
      headers: headers(),
      signal: controller.signal,
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || 'Request failed')
    return data
  } catch (err) {
    if (err.name === 'AbortError') throw new Error('Request timed out — backend unreachable')
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  // ── Auth ──────────────────────────────────
  login:    (email, password)   => req('POST', '/auth/login',    { email, password }),
  register: (payload)           => req('POST', '/auth/register', payload),
  me:       ()                  => req('GET',  '/auth/me'),
  updateMe: (data)             => req('PUT',  '/auth/me', data),

  // ── Search ────────────────────────────────
  search:     (query, history = [], filters = {}) => req('POST', '/search/tdr', { query, history, filters }, 60000),
  getFilters: ()                                   => req('GET',  '/search/filters'),

  // ── Admin ─────────────────────────────────
  getUsers:    ()               => req('GET',    '/admin/users'),
  createUser:  (data)           => req('POST',   '/admin/users',              data),
  updateUser:  (id, data)       => req('PUT',    `/admin/users/${id}`,        data),
  approveUser: (id)             => req('PUT',    `/admin/users/${id}/approve`),
  revokeUser:  (id)             => req('PUT',    `/admin/users/${id}/revoke`),
  deleteUser:  (id)             => req('DELETE', `/admin/users/${id}`),
}
