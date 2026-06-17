import { useState } from 'react'
import { Link } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import styles from './Auth.module.css'

const ROLES = [
  'Consultant',
  'Senior Consultant',
  'Manager',
  'Senior Manager',
  'Director',
  'Partner',
  'Other',
]

export default function SignUp() {
  const [form, setForm] = useState({
    firstName: '', lastName: '', email: '',
    role: '', password: '', confirm: '',
  })
  const [errors, setErrors]     = useState({})
  const [loading, setLoading]   = useState(false)
  const [showPw, setShowPw]     = useState(false)
  const [showCfm, setShowCfm]   = useState(false)
  const [agreed, setAgreed]     = useState(false)

  function validate() {
    const e = {}
    if (!form.firstName.trim()) e.firstName = 'Required.'
    if (!form.lastName.trim())  e.lastName  = 'Required.'
    if (!form.email.trim())     e.email     = 'Required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
      e.email = 'Invalid email.'
    if (!form.role)    e.role    = 'Select a role.'
    if (!form.password) e.password = 'Required.'
    else if (form.password.length < 8) e.password = 'Min. 8 characters.'
    if (!form.confirm)  e.confirm = 'Required.'
    else if (form.confirm !== form.password) e.confirm = "Doesn't match."
    if (!agreed) e.agreed = 'You must accept the terms.'
    return e
  }

  function handleChange(e) {
    const { name, value } = e.target
    setForm(p => ({ ...p, [name]: value }))
    if (errors[name]) setErrors(p => ({ ...p, [name]: null }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setLoading(true)
    await new Promise(r => setTimeout(r, 1400))
    setLoading(false)
  }

  const strength = passwordStrength(form.password)

  return (
    <AuthLayout>
      <div className={styles.header}>
        <h2 className={styles.title}>Create your account</h2>
        <p className={styles.subtitle}>Join EY TdR Intelligence — search smarter, faster</p>
      </div>

      <form className={styles.form} onSubmit={handleSubmit} noValidate>

        {/* Name */}
        <div className={styles.row}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="firstName">First name</label>
            <input id="firstName" name="firstName" type="text" autoComplete="given-name"
              placeholder="Jane" value={form.firstName} onChange={handleChange}
              className={`${styles.input} ${errors.firstName ? styles.inputError : ''}`} />
            {errors.firstName && <span className={styles.error}>{errors.firstName}</span>}
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="lastName">Last name</label>
            <input id="lastName" name="lastName" type="text" autoComplete="family-name"
              placeholder="Doe" value={form.lastName} onChange={handleChange}
              className={`${styles.input} ${errors.lastName ? styles.inputError : ''}`} />
            {errors.lastName && <span className={styles.error}>{errors.lastName}</span>}
          </div>
        </div>

        {/* Email */}
        <div className={styles.field}>
          <label className={styles.label} htmlFor="email">Email address</label>
          <input id="email" name="email" type="email" autoComplete="email"
            placeholder="you@ey.com" value={form.email} onChange={handleChange}
            className={`${styles.input} ${errors.email ? styles.inputError : ''}`} />
          {errors.email && <span className={styles.error}>{errors.email}</span>}
        </div>

        {/* Role */}
        <div className={styles.field}>
          <label className={styles.label} htmlFor="role">Role</label>
          <div className={styles.selectWrapper}>
            <select id="role" name="role" value={form.role} onChange={handleChange}
              className={`${styles.input} ${styles.select} ${errors.role ? styles.inputError : ''}`}>
              <option value="">Select your role…</option>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <ChevronIcon />
          </div>
          {errors.role && <span className={styles.error}>{errors.role}</span>}
        </div>

        {/* Passwords — side by side */}
        <div className={styles.row}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">Password</label>
            <div className={styles.passwordWrapper}>
              <input id="password" name="password" type={showPw ? 'text' : 'password'}
                autoComplete="new-password" placeholder="Min. 8 chars" value={form.password}
                onChange={handleChange}
                className={`${styles.input} ${errors.password ? styles.inputError : ''}`} />
              <button type="button" className={styles.eyeToggle}
                onClick={() => setShowPw(s => !s)}
                aria-label={showPw ? 'Hide' : 'Show'}>
                {showPw ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {errors.password && <span className={styles.error}>{errors.password}</span>}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="confirm">Confirm</label>
            <div className={styles.passwordWrapper}>
              <input id="confirm" name="confirm" type={showCfm ? 'text' : 'password'}
                autoComplete="new-password" placeholder="Re-enter" value={form.confirm}
                onChange={handleChange}
                className={`${styles.input} ${errors.confirm ? styles.inputError : ''}`} />
              <button type="button" className={styles.eyeToggle}
                onClick={() => setShowCfm(s => !s)}
                aria-label={showCfm ? 'Hide' : 'Show'}>
                {showCfm ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {errors.confirm && <span className={styles.error}>{errors.confirm}</span>}
          </div>
        </div>

        {/* Strength bar */}
        {form.password && (
          <div className={styles.strengthWrap}>
            <div className={styles.strengthTrack}>
              <div className={styles.strengthFill}
                style={{ width: `${(strength.score / 4) * 100}%`, background: strength.color }} />
            </div>
            <span className={styles.strengthLabel} style={{ color: strength.color }}>
              {strength.label}
            </span>
          </div>
        )}

        {/* Terms */}
        <label className={styles.checkboxLabel}>
          <input type="checkbox" checked={agreed} className={styles.checkbox}
            onChange={e => {
              setAgreed(e.target.checked)
              if (errors.agreed) setErrors(p => ({ ...p, agreed: null }))
            }} />
          <span>
            I agree to the{' '}
            <span className={styles.switchLink}>Terms of Service</span>
            {' '}and{' '}
            <span className={styles.switchLink}>Privacy Policy</span>
          </span>
        </label>
        {errors.agreed && <span className={styles.error}>{errors.agreed}</span>}

        <button type="submit" className={styles.submitBtn} disabled={loading}>
          {loading ? <Spinner /> : 'Create account'}
        </button>
      </form>

      <p className={styles.switchText}>
        Already have an account?{' '}
        <Link to="/signin" className={styles.switchLink}>Sign in</Link>
      </p>
    </AuthLayout>
  )
}

function passwordStrength(pw) {
  if (!pw) return { score: 0, label: '', color: '' }
  let score = 0
  if (pw.length >= 8)          score++
  if (/[A-Z]/.test(pw))        score++
  if (/[0-9]/.test(pw))        score++
  if (/[^A-Za-z0-9]/.test(pw)) score++
  const map = [
    { label: 'Too weak', color: '#C0392B' },
    { label: 'Weak',     color: '#E67E22' },
    { label: 'Fair',     color: '#D4AC00' },
    { label: 'Good',     color: '#27AE60' },
    { label: 'Strong',   color: '#1E8449' },
  ]
  return { score, ...map[score] }
}

function EyeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
}

function ChevronIcon() {
  return (
    <svg className={styles.chevron} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

function Spinner() {
  return (
    <svg className={styles.spinner} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
      <path d="M12 2a10 10 0 0110 10" />
    </svg>
  )
}
