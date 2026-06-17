import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../services/api'
import styles from './AdminDashboard.module.css'
import ProfileModal from '../components/ProfileModal'

const ROLES = ['Consultant','Senior Consultant','Manager','Senior Manager','Director','Partner','Other']

/* ── MODAL (Add / Edit user) ─────────────────────── */
function UserModal({ user, onClose, onSave }) {
  const isEdit = Boolean(user)
  const [form, setForm] = useState({
    first_name: user?.first_name || '',
    last_name:  user?.last_name  || '',
    email:      user?.email      || '',
    role_title: user?.role_title || '',
    password:   '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  function handleChange(e) {
    setForm(p => ({ ...p, [e.target.name]: e.target.value }))
    setError('')
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (isEdit) {
        const payload = { ...form }
        if (!payload.password) delete payload.password   // don't send empty password
        await onSave(user.id, payload)
      } else {
        if (!form.password) { setError('Password is required.'); setLoading(false); return }
        await onSave(null, form)
      }
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h3>{isEdit ? 'Edit User' : 'Add New User'}</h3>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} className={styles.modalForm}>
          <div className={styles.modalRow}>
            <Field label="First name" name="first_name" value={form.first_name}
              onChange={handleChange} placeholder="Jane" required />
            <Field label="Last name" name="last_name" value={form.last_name}
              onChange={handleChange} placeholder="Doe" required />
          </div>
          <Field label="Email" name="email" type="email" value={form.email}
            onChange={handleChange} placeholder="user@ey.com" required />
          <div className={styles.fieldWrap}>
            <label className={styles.fieldLabel}>Role / Title</label>
            <div className={styles.selectWrap}>
              <select name="role_title" value={form.role_title} onChange={handleChange}
                className={styles.fieldInput}>
                <option value="">Select role…</option>
                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              <Chevron />
            </div>
          </div>
          <Field
            label={isEdit ? 'New password (leave blank to keep)' : 'Password'}
            name="password" type="password" value={form.password}
            onChange={handleChange} placeholder="••••••••"
            required={!isEdit} />

          {error && <p className={styles.modalError}>{error}</p>}

          <div className={styles.modalActions}>
            <button type="button" className={styles.cancelBtn} onClick={onClose}>Cancel</button>
            <button type="submit" className={styles.saveBtn} disabled={loading}>
              {loading ? <SmallSpinner /> : (isEdit ? 'Save changes' : 'Create user')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, name, type = 'text', value, onChange, placeholder, required }) {
  return (
    <div className={styles.fieldWrap}>
      <label className={styles.fieldLabel}>{label}</label>
      <input name={name} type={type} value={value} onChange={onChange}
        placeholder={placeholder} required={required}
        className={styles.fieldInput} />
    </div>
  )
}

/* ── MAIN DASHBOARD ──────────────────────────────── */
export default function AdminDashboard() {
  const { user, logout }     = useAuth()
  const navigate             = useNavigate()
  const [users, setUsers]    = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter]  = useState('all')
  const [modal, setModal]    = useState(null)
  const [busy, setBusy]      = useState({})
  const [profileOpen, setProfileOpen] = useState(false)

  const fetchUsers = useCallback(async () => {
    try {
      setUsers(await api.getUsers())
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  function handleLogout() {
    logout()
    navigate('/')
  }

  /* Row-level action wrapper */
  async function rowAction(id, fn) {
    setBusy(p => ({ ...p, [id]: true }))
    try {
      await fn()
      await fetchUsers()
    } catch (err) {
      alert(err.message)
    } finally {
      setBusy(p => ({ ...p, [id]: false }))
    }
  }

  /* Modal save handler */
  async function handleSave(id, data) {
    if (id) {
      await api.updateUser(id, data)
    } else {
      await api.createUser(data)
    }
    await fetchUsers()
  }

  /* Derived */
  const filtered = users.filter(u => {
    if (filter === 'pending')  return !u.is_approved
    if (filter === 'approved') return  u.is_approved
    return true
  })
  const totalUsers   = users.filter(u => u.role !== 'admin').length
  const pendingCount = users.filter(u => !u.is_approved && u.role !== 'admin').length
  const approvedCount = users.filter(u =>  u.is_approved && u.role !== 'admin').length

  return (
    <div className={styles.root}>

      {/* ── HEADER ──────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <img src="/ey.jpg" alt="EY" className={styles.headerLogo} />
          <div>
            <p className={styles.headerTitle}>Admin Dashboard</p>
            <p className={styles.headerSub}>User management &amp; approval</p>
          </div>
        </div>
        <div className={styles.headerRight}>
          <button className={styles.adminBadge} onClick={() => setProfileOpen(true)}
            style={{ cursor:'pointer', background: 'rgba(255,255,255,0.07)', border:'1px solid rgba(255,255,255,0.12)' }}
            title="Modifier mon profil">
            <div className={styles.avatar} style={{ width:26, height:26, fontSize:10, flexShrink:0 }}>
              {user?.avatar
                ? <img src={user.avatar} alt="avatar" style={{ width:'100%', height:'100%', objectFit:'cover', borderRadius:'50%' }} />
                : <>{user?.first_name?.[0]}{user?.last_name?.[0]}</>
              }
            </div>
            <span className={styles.adminDot} />
            {user?.email}
          </button>
          <button className={styles.logoutBtn} onClick={handleLogout}>
            <LogoutIcon /> <span>Sign out</span>
          </button>
        </div>
      </header>

      <main className={styles.main}>

        {/* ── STAT CARDS ──────────────────────── */}
        <div className={styles.stats}>
          {[
            { label: 'Total users',      value: totalUsers,    color: '#FFE600' },
            { label: 'Pending approval', value: pendingCount,  color: '#FF8C00' },
            { label: 'Approved',         value: approvedCount, color: '#00C47D' },
          ].map(({ label, value, color }) => (
            <div key={label} className={styles.statCard}>
              <span className={styles.statValue} style={{ color }}>{value}</span>
              <span className={styles.statLabel}>{label}</span>
              <div className={styles.statBar} style={{ background: color }} />
            </div>
          ))}
        </div>

        {/* ── TOOLBAR ─────────────────────────── */}
        <div className={styles.toolbar}>
          <div className={styles.filters}>
            {['all','pending','approved'].map(f => (
              <button key={f}
                className={`${styles.filterBtn} ${filter === f ? styles.filterActive : ''}`}
                onClick={() => setFilter(f)}>
                {f.charAt(0).toUpperCase() + f.slice(1)}
                {f === 'pending' && pendingCount > 0 && (
                  <span className={styles.badge}>{pendingCount}</span>
                )}
              </button>
            ))}
          </div>
          <button className={styles.addBtn} onClick={() => setModal({ mode:'add' })}>
            <PlusIcon /> Add user
          </button>
        </div>

        {/* ── TABLE ───────────────────────────── */}
        <div className={styles.tableWrap}>
          {loading ? (
            <div className={styles.tableLoading}>
              <SmallSpinner /> Loading users…
            </div>
          ) : filtered.length === 0 ? (
            <div className={styles.tableEmpty}>No users found.</div>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Joined</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(u => (
                  <tr key={u.id} className={u.role === 'admin' ? styles.adminRow : ''}>
                    <td>
                      <div className={styles.nameCell}>
                        <div className={styles.avatar}>
                          {u.first_name[0]}{u.last_name[0]}
                        </div>
                        <div>
                          <p className={styles.fullName}>{u.first_name} {u.last_name}</p>
                          {u.role === 'admin' && <span className={styles.adminTag}>Admin</span>}
                        </div>
                      </div>
                    </td>
                    <td className={styles.emailCell}>{u.email}</td>
                    <td className={styles.dimCell}>{u.role_title || '—'}</td>
                    <td>
                      <span className={`${styles.statusBadge} ${u.is_approved ? styles.statusApproved : styles.statusPending}`}>
                        {u.is_approved ? '● Approved' : '● Pending'}
                      </span>
                    </td>
                    <td className={styles.dimCell}>
                      {new Date(u.created_at).toLocaleDateString('fr-FR')}
                    </td>
                    <td>
                      <div className={styles.actions}>
                        {/* Approve / Revoke */}
                        {u.role !== 'admin' && (
                          u.is_approved ? (
                            <ActionBtn
                              title="Revoke access"
                              color="#FF4D4D"
                              loading={busy[u.id]}
                              onClick={() => rowAction(u.id, () => api.revokeUser(u.id))}>
                              <RevokeIcon />
                            </ActionBtn>
                          ) : (
                            <ActionBtn
                              title="Approve"
                              color="#00C47D"
                              loading={busy[u.id]}
                              onClick={() => rowAction(u.id, () => api.approveUser(u.id))}>
                              <CheckIcon />
                            </ActionBtn>
                          )
                        )}

                        {/* Edit */}
                        <ActionBtn title="Edit" color="#FFE600"
                          onClick={() => setModal({ mode:'edit', user: u })}>
                          <EditIcon />
                        </ActionBtn>

                        {/* Delete */}
                        {u.role !== 'admin' && (
                          <ActionBtn title="Delete" color="#FF4D4D"
                            loading={busy[`del_${u.id}`]}
                            onClick={() => {
                              if (!confirm(`Delete ${u.email}?`)) return
                              rowAction(`del_${u.id}`, () => api.deleteUser(u.id))
                            }}>
                            <DeleteIcon />
                          </ActionBtn>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>

      {/* ── MODAL ───────────────────────────────── */}
      {modal && (
        <UserModal
          user={modal.user}
          onClose={() => setModal(null)}
          onSave={handleSave}
        />
      )}

      {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}
    </div>
  )
}

/* ── Small reusable components ───────────────────── */
function ActionBtn({ title, color, loading, onClick, children }) {
  return (
    <button className={styles.actionBtn} title={title} onClick={onClick}
      disabled={loading} style={{ '--btn-color': color }}>
      {loading ? <SmallSpinner size={13} /> : children}
    </button>
  )
}

function SmallSpinner({ size = 15 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5"
      style={{ animation: 'spin 0.75s linear infinite', display:'block' }}>
      <circle cx="12" cy="12" r="10" strokeOpacity="0.25"/>
      <path d="M12 2a10 10 0 0110 10"/>
    </svg>
  )
}

function Chevron() {
  return (
    <svg style={{ position:'absolute', right:10, top:'50%', transform:'translateY(-50%)',
      width:13, height:13, color:'rgba(255,255,255,0.3)', pointerEvents:'none' }}
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  )
}
function PlusIcon()   { return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> }
function CheckIcon()  { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg> }
function EditIcon()   { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> }
function DeleteIcon() { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg> }
function RevokeIcon() { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg> }
function LogoutIcon() { return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg> }
