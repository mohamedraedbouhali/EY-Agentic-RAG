import { useState, useRef } from 'react'
import { api } from '../services/api'
import { useAuth } from '../context/AuthContext'
import styles from './ProfileModal.module.css'

function compressImage(file) {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const img = new Image()
      img.onload = () => {
        const SIZE = 200
        const canvas = document.createElement('canvas')
        canvas.width = SIZE
        canvas.height = SIZE
        const ctx = canvas.getContext('2d')
        const minDim = Math.min(img.width, img.height)
        const sx = (img.width - minDim) / 2
        const sy = (img.height - minDim) / 2
        ctx.drawImage(img, sx, sy, minDim, minDim, 0, 0, SIZE, SIZE)
        resolve(canvas.toDataURL('image/jpeg', 0.75))
      }
      img.src = e.target.result
    }
    reader.readAsDataURL(file)
  })
}

export default function ProfileModal({ onClose }) {
  const { user, updateUser } = useAuth()
  const fileRef = useRef(null)

  const [form, setForm] = useState({
    first_name: user?.first_name || '',
    last_name:  user?.last_name  || '',
  })
  const [preview, setPreview] = useState(user?.avatar || null)
  const [avatarData, setAvatarData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const initials = `${user?.first_name?.[0] || ''}${user?.last_name?.[0] || ''}`

  async function handleFile(e) {
    const file = e.target.files[0]
    if (!file) return
    if (!file.type.startsWith('image/')) { setError('Please select an image file.'); return }
    const compressed = await compressImage(file)
    setPreview(compressed)
    setAvatarData(compressed)
    setError('')
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const payload = {
        first_name: form.first_name.trim(),
        last_name:  form.last_name.trim(),
        ...(avatarData ? { avatar: avatarData } : {}),
      }
      const updated = await api.updateMe(payload)
      updateUser(updated)
      setSuccess(true)
      setTimeout(onClose, 900)
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
          <h3>Mon profil</h3>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} className={styles.body}>

          {/* Avatar section */}
          <div className={styles.avatarSection}>
            <div className={styles.avatarWrap} onClick={() => fileRef.current?.click()}>
              {preview
                ? <img src={preview} alt="avatar" className={styles.avatarImg} />
                : <span className={styles.avatarInitials}>{initials}</span>
              }
              <div className={styles.avatarOverlay}>
                <CameraIcon />
              </div>
            </div>
            <p className={styles.avatarHint}>Cliquer pour changer la photo</p>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={handleFile}
            />
          </div>

          {/* Name fields */}
          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label}>Prénom</label>
              <input
                className={styles.input}
                value={form.first_name}
                onChange={e => setForm(p => ({ ...p, first_name: e.target.value }))}
                placeholder="Prénom"
                required
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Nom</label>
              <input
                className={styles.input}
                value={form.last_name}
                onChange={e => setForm(p => ({ ...p, last_name: e.target.value }))}
                placeholder="Nom"
                required
              />
            </div>
          </div>

          {error   && <p className={styles.error}>{error}</p>}
          {success && <p className={styles.successMsg}>Profil mis à jour !</p>}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelBtn} onClick={onClose}>
              Annuler
            </button>
            <button type="submit" className={styles.saveBtn} disabled={loading || success}>
              {loading ? <Spinner /> : 'Enregistrer'}
            </button>
          </div>

        </form>
      </div>
    </div>
  )
}

function CameraIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/>
      <circle cx="12" cy="13" r="4"/>
    </svg>
  )
}

function Spinner() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5"
      style={{ animation: 'spin .75s linear infinite', display: 'block' }}>
      <circle cx="12" cy="12" r="10" strokeOpacity="0.25"/>
      <path d="M12 2a10 10 0 0110 10"/>
    </svg>
  )
}
