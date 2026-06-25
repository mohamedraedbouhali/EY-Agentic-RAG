import { useRef, useEffect } from 'react'
import styles from './AuthLayout.module.css'

export default function AuthLayout({ children, panelAnim }) {
  const brandRef = useRef(null)

  /* Animate left panel whenever mode switches */
  useEffect(() => {
    if (!panelAnim || !brandRef.current) return
    const el = brandRef.current
    const dx = panelAnim === 'fwd' ? -14 : 14

    el.style.transition = 'transform 0.30s cubic-bezier(0.4,0,1,1), filter 0.30s ease'
    el.style.transform  = `translateX(${dx}px)`
    el.style.filter     = 'brightness(0.75)'

    const tid = setTimeout(() => {
      el.style.transition = 'transform 0.55s cubic-bezier(0.22,1,0.36,1), filter 0.45s ease'
      el.style.transform  = 'translateX(0px)'
      el.style.filter     = 'brightness(1)'
    }, 310)

    return () => clearTimeout(tid)
  }, [panelAnim])

  return (
    <div className={styles.root}>

      {/* ── LEFT SHOWCASE PANEL ─────────────────── */}
      <div ref={brandRef} className={styles.brand}>
        <div className={styles.grid} />
        <div className={styles.orb1} />
        <div className={styles.orb2} />
        <div className={styles.orb3} />
        <div className={styles.beam1} />
        <div className={styles.beam2} />

        <div className={styles.brandContent}>
          <div className={styles.logoBlock}>
            <div className={styles.logoHalo} />
            <img src="/ey.jpg" alt="EY" className={styles.logo} />
          </div>

          <div className={styles.hero}>
            <p className={styles.overline}>
              <span className={styles.overlineDot} />
              Ernst &amp; Young · Agentic Intelligence
            </p>
            <h1 className={styles.tagline}>
              Shape the future<br />with&nbsp;
              <span className={styles.shimmer}>confidence</span>
            </h1>
            <p className={styles.sub}>
              AI-powered intelligence platform for Tender Reference Documents —
              search, analyse and match expert profiles at scale.
            </p>
          </div>
        </div>

        <footer className={styles.brandFooter}>
          <div className={styles.footerRule} />
          <span>© {new Date().getFullYear()} Ernst &amp; Young — All rights reserved.</span>
        </footer>
      </div>

      {/* ── RIGHT FORM PANEL ────────────────────── */}
      <div className={styles.formSide}>
        <div className={styles.formBg} />
        <div className={styles.formCard}>
          {children}
        </div>
      </div>

    </div>
  )
}
