import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { useAuth } from '../context/AuthContext'
import { api } from '../services/api'
import styles from './Auth.module.css'

const ROLES = ['Consultant','Senior Consultant','Manager','Senior Manager','Director','Partner','Other']

/* ─────────────────────────────────────────────
   SIGN-IN FORM
───────────────────────────────────────────── */
function SignInForm({ onSwitch }) {
  const { login }            = useAuth()
  const navigate             = useNavigate()
  const [form, setForm]      = useState({ email: '', password: '' })
  const [errors, setErrors]  = useState({})
  const [loading, setLoading] = useState(false)
  const [showPw, setShowPw]  = useState(false)

  function validate() {
    const e = {}
    if (!form.email.trim()) e.email = 'Required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) e.email = 'Invalid email.'
    if (!form.password) e.password = 'Required.'
    return e
  }

  function handleChange(e) {
    const { name, value } = e.target
    setForm(p => ({ ...p, [name]: value }))
    if (errors[name] || errors.submit) setErrors(p => ({ ...p, [name]: null, submit: null }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setLoading(true)
    try {
      const user = await login(form.email, form.password)
      if (user.role === 'admin') navigate('/admin')
      else navigate('/dashboard')
    } catch (err) {
      setErrors({ submit: err.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className={styles.header}>
        <h2 className={styles.title}>Welcome back</h2>
        <p className={styles.subtitle}>Sign in to EY TdR Intelligence</p>
      </div>

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="si-email">Email address</label>
          <input id="si-email" name="email" type="email" autoComplete="email"
            placeholder="you@ey.com" value={form.email} onChange={handleChange}
            className={`${styles.input} ${errors.email ? styles.inputError : ''}`} />
          {errors.email && <span className={styles.error}>{errors.email}</span>}
        </div>

        <div className={styles.field}>
          <div className={styles.labelRow}>
            <label className={styles.label} htmlFor="si-pw">Password</label>
            <button type="button" className={styles.forgotLink}>Forgot password?</button>
          </div>
          <div className={styles.passwordWrapper}>
            <input id="si-pw" name="password" type={showPw ? 'text' : 'password'}
              autoComplete="current-password" placeholder="••••••••"
              value={form.password} onChange={handleChange}
              className={`${styles.input} ${errors.password ? styles.inputError : ''}`} />
            <button type="button" className={styles.eyeToggle}
              onClick={() => setShowPw(s => !s)} aria-label="Toggle password">
              {showPw ? <EyeOff /> : <Eye />}
            </button>
          </div>
          {errors.password && <span className={styles.error}>{errors.password}</span>}
        </div>

        {/* Global API error */}
        {errors.submit && (
          <div className={styles.alertError}>
            <AlertIcon /> {errors.submit}
          </div>
        )}

        <button type="submit" className={styles.submitBtn} disabled={loading}>
          {loading ? <Spinner /> : 'Sign in'}
        </button>
      </form>

      <p className={styles.switchText}>
        Don't have an account?{' '}
        <button type="button" className={styles.switchLink} onClick={onSwitch}>
          Create one
        </button>
      </p>
    </>
  )
}

/* ─────────────────────────────────────────────
   SIGN-UP FORM
───────────────────────────────────────────── */
function SignUpForm({ onSwitch }) {
  const [form, setForm]       = useState({
    firstName:'', lastName:'', email:'', role:'', password:'', confirm:''
  })
  const [errors, setErrors]   = useState({})
  const [loading, setLoading] = useState(false)
  const [showPw, setShowPw]   = useState(false)
  const [showCfm, setShowCfm] = useState(false)
  const [agreed, setAgreed]   = useState(false)
  const [success, setSuccess] = useState(false)

  function validate() {
    const e = {}
    if (!form.firstName.trim()) e.firstName = 'Required.'
    if (!form.lastName.trim())  e.lastName  = 'Required.'
    if (!form.email.trim())     e.email     = 'Required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) e.email = 'Invalid email.'
    if (!form.role)              e.role     = 'Select a role.'
    if (!form.password)          e.password = 'Required.'
    else if (form.password.length < 8)       e.password = 'Min. 8 characters.'
    if (!form.confirm)           e.confirm  = 'Required.'
    else if (form.confirm !== form.password) e.confirm  = "Doesn't match."
    if (!agreed)                 e.agreed   = 'Please accept the terms.'
    return e
  }

  function handleChange(e) {
    const { name, value } = e.target
    setForm(p => ({ ...p, [name]: value }))
    if (errors[name] || errors.submit) setErrors(p => ({ ...p, [name]: null, submit: null }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setLoading(true)
    try {
      await api.register({
        email:      form.email,
        password:   form.password,
        first_name: form.firstName,
        last_name:  form.lastName,
        role_title: form.role,
      })
      setSuccess(true)
    } catch (err) {
      setErrors({ submit: err.message })
    } finally {
      setLoading(false)
    }
  }

  const strength = pwStrength(form.password)

  /* Success screen */
  if (success) {
    return (
      <div className={styles.successWrap}>
        <div className={styles.successIcon}>
          <svg viewBox="0 0 24 24" fill="none" stroke="#00C47D" strokeWidth="2.5"
            strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <h2 className={styles.successTitle}>Account created!</h2>
        <p className={styles.successMsg}>
          Your request has been sent to the administrator.
          You'll be able to sign in once your account is approved.
        </p>
        <button className={styles.submitBtn} style={{ marginTop: 8 }}
          onClick={onSwitch}>
          Back to Sign in
        </button>
      </div>
    )
  }

  return (
    <>
      <div className={styles.header}>
        <h2 className={styles.title}>Create account</h2>
        <p className={styles.subtitle}>Join EY TdR Intelligence</p>
      </div>

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <div className={styles.row}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="su-fn">First name</label>
            <input id="su-fn" name="firstName" type="text" autoComplete="given-name"
              placeholder="Jane" value={form.firstName} onChange={handleChange}
              className={`${styles.input} ${errors.firstName ? styles.inputError : ''}`} />
            {errors.firstName && <span className={styles.error}>{errors.firstName}</span>}
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="su-ln">Last name</label>
            <input id="su-ln" name="lastName" type="text" autoComplete="family-name"
              placeholder="Doe" value={form.lastName} onChange={handleChange}
              className={`${styles.input} ${errors.lastName ? styles.inputError : ''}`} />
            {errors.lastName && <span className={styles.error}>{errors.lastName}</span>}
          </div>
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="su-email">Email address</label>
          <input id="su-email" name="email" type="email" autoComplete="email"
            placeholder="you@ey.com" value={form.email} onChange={handleChange}
            className={`${styles.input} ${errors.email ? styles.inputError : ''}`} />
          {errors.email && <span className={styles.error}>{errors.email}</span>}
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="su-role">Role</label>
          <div className={styles.selectWrapper}>
            <select id="su-role" name="role" value={form.role} onChange={handleChange}
              className={`${styles.input} ${styles.select} ${errors.role ? styles.inputError : ''}`}>
              <option value="">Select your role…</option>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <Chevron />
          </div>
          {errors.role && <span className={styles.error}>{errors.role}</span>}
        </div>

        <div className={styles.row}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="su-pw">Password</label>
            <div className={styles.passwordWrapper}>
              <input id="su-pw" name="password" type={showPw ? 'text' : 'password'}
                autoComplete="new-password" placeholder="Min. 8 chars"
                value={form.password} onChange={handleChange}
                className={`${styles.input} ${errors.password ? styles.inputError : ''}`} />
              <button type="button" className={styles.eyeToggle}
                onClick={() => setShowPw(s => !s)} aria-label="Toggle">
                {showPw ? <EyeOff /> : <Eye />}
              </button>
            </div>
            {errors.password && <span className={styles.error}>{errors.password}</span>}
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="su-cfm">Confirm</label>
            <div className={styles.passwordWrapper}>
              <input id="su-cfm" name="confirm" type={showCfm ? 'text' : 'password'}
                autoComplete="new-password" placeholder="Re-enter"
                value={form.confirm} onChange={handleChange}
                className={`${styles.input} ${errors.confirm ? styles.inputError : ''}`} />
              <button type="button" className={styles.eyeToggle}
                onClick={() => setShowCfm(s => !s)} aria-label="Toggle">
                {showCfm ? <EyeOff /> : <Eye />}
              </button>
            </div>
            {errors.confirm && <span className={styles.error}>{errors.confirm}</span>}
          </div>
        </div>

        {form.password && (
          <div className={styles.strengthWrap}>
            <div className={styles.strengthTrack}>
              <div className={styles.strengthFill}
                style={{ width:`${(strength.score/4)*100}%`, background: strength.color }} />
            </div>
            <span className={styles.strengthLabel} style={{ color: strength.color }}>
              {strength.label}
            </span>
          </div>
        )}

        <label className={styles.checkboxLabel}>
          <input type="checkbox" checked={agreed} className={styles.checkbox}
            onChange={e => {
              setAgreed(e.target.checked)
              if (errors.agreed) setErrors(p => ({ ...p, agreed: null }))
            }} />
          <span>
            I agree to the <span className={styles.termLink}>Terms of Service</span>
            {' '}and <span className={styles.termLink}>Privacy Policy</span>
          </span>
        </label>
        {errors.agreed && <span className={styles.error}>{errors.agreed}</span>}

        {errors.submit && (
          <div className={styles.alertError}>
            <AlertIcon /> {errors.submit}
          </div>
        )}

        <button type="submit" className={styles.submitBtn} disabled={loading}>
          {loading ? <Spinner /> : 'Create account'}
        </button>
      </form>

      <p className={styles.switchText}>
        Already have an account?{' '}
        <button type="button" className={styles.switchLink} onClick={onSwitch}>
          Sign in
        </button>
      </p>
    </>
  )
}

/* ─────────────────────────────────────────────
   MAIN PAGE — animated mode switch
───────────────────────────────────────────── */
export default function Auth() {
  const { user, loading } = useAuth()
  const navigate          = useNavigate()
  const [mode, setMode]   = useState('signin')
  const [panelAnim, setPanelAnim] = useState(null)
  const slideRef = useRef(null)
  const busy     = useRef(false)

  /* Already logged in → redirect immediately */
  useEffect(() => {
    if (!loading && user) {
      if (user.role === 'admin') navigate('/admin', { replace: true })
      else navigate('/dashboard', { replace: true })
    }
  }, [user, loading, navigate])

  const goTo = useCallback((newMode) => {
    if (busy.current || newMode === mode || !slideRef.current) return
    busy.current = true

    const isFwd = newMode === 'signup'
    const exitX = isFwd ? -56 : 56
    const fromX = isFwd ?  56 : -56

    setPanelAnim(isFwd ? 'fwd' : 'bwd')

    const node = slideRef.current
    node.style.transition = 'transform 0.30s cubic-bezier(0.4,0,1,1), opacity 0.28s ease'
    node.style.transform  = `translateX(${exitX}px)`
    node.style.opacity    = '0'

    setTimeout(() => {
      node.style.transition = 'none'
      node.style.transform  = `translateX(${fromX}px)`
      node.style.opacity    = '0'
      setMode(newMode)

      requestAnimationFrame(() => requestAnimationFrame(() => {
        node.style.transition = 'transform 0.42s cubic-bezier(0.22,1,0.36,1), opacity 0.35s ease'
        node.style.transform  = 'translateX(0px)'
        node.style.opacity    = '1'
        setTimeout(() => { busy.current = false; setPanelAnim(null) }, 430)
      }))
    }, 310)
  }, [mode])

  if (loading) return null   // wait for session restore

  return (
    <AuthLayout panelAnim={panelAnim}>
      <div ref={slideRef} className={styles.slide}>
        {mode === 'signin'
          ? <SignInForm  onSwitch={() => goTo('signup')} />
          : <SignUpForm  onSwitch={() => goTo('signin')} />
        }
      </div>
    </AuthLayout>
  )
}

/* ─────────────────────────────────────────────
   HELPERS
───────────────────────────────────────────── */
function pwStrength(pw) {
  if (!pw) return { score: 0, label: '', color: '' }
  let s = 0
  if (pw.length >= 8)          s++
  if (/[A-Z]/.test(pw))        s++
  if (/[0-9]/.test(pw))        s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  return [
    { label:'Too weak', color:'#FF4D4D' },
    { label:'Weak',     color:'#FF8C00' },
    { label:'Fair',     color:'#FFD000' },
    { label:'Good',     color:'#00C47D' },
    { label:'Strong',   color:'#00C47D' },
  ][s]
}

function Eye() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
}
function EyeOff() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
}
function Chevron() {
  return <svg style={{position:'absolute',right:10,top:'50%',transform:'translateY(-50%)',width:14,height:14,color:'rgba(255,255,255,0.3)',pointerEvents:'none'}} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
}
function Spinner() {
  return <svg className={styles.spinner} viewBox="0 0 24 24" fill="none" stroke="#12131F" strokeWidth="2.5"><circle cx="12" cy="12" r="10" strokeOpacity="0.25"/><path d="M12 2a10 10 0 0110 10"/></svg>
}
function AlertIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
}
