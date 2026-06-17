import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../services/api'
import styles from './UserDashboard.module.css'
import ProfileModal from '../components/ProfileModal'

const SUGGESTIONS = [
  'Quel est le budget du projet ?',
  'Quels sont les livrables attendus ?',
  'Quelle est la durée de la mission ?',
  'Qui sont les bailleurs de fonds ?',
  'Quelles sont les qualifications requises ?',
]

export default function UserDashboard() {
  const { user, logout } = useAuth()
  const navigate         = useNavigate()

  const [query, setQuery]         = useState('')
  const [answer, setAnswer]       = useState('')
  const [sources, setSources]     = useState([])
  const [loading, setLoading]     = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [error, setError]         = useState('')
  const [profileOpen, setProfileOpen] = useState(false)

  const doSearch = useCallback(async (q = query) => {
    if (!q.trim()) return
    setLoading(true)
    setHasSearched(true)
    setError('')
    setAnswer('')
    setSources([])
    try {
      const data = await api.search(q)
      setAnswer(data.answer || '')
      setSources(data.sources || [])
    } catch (err) {
      setError(err.message || 'Erreur lors de la recherche.')
    } finally {
      setLoading(false)
    }
  }, [query])

  const handleSubmit    = e => { e.preventDefault(); doSearch() }
  const handleSuggestion = s => { setQuery(s); doSearch(s) }

  return (
    <>
    <div className={styles.root}>

      {/* ── HEADER ─────────────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <img src="/ey.jpg" alt="EY" className={styles.logo} />
          <div>
            <p className={styles.headerTitle}>TdR Intelligence</p>
            <p className={styles.headerSub}>Recherche & Analyse des Appels d'Offres</p>
          </div>
        </div>
        <div className={styles.headerRight}>
          <div className={styles.userChip} onClick={() => setProfileOpen(true)}
            style={{ cursor:'pointer' }} title="Modifier mon profil">
            <div className={styles.avatar}>
              {user?.avatar
                ? <img src={user.avatar} alt="avatar" style={{ width:'100%', height:'100%', objectFit:'cover', borderRadius:'50%' }} />
                : <>{user?.first_name?.[0]}{user?.last_name?.[0]}</>
              }
            </div>
            <div className={styles.userInfo}>
              <span className={styles.userName}>{user?.first_name} {user?.last_name}</span>
              <span className={styles.userRole}>{user?.role_title || 'Utilisateur'}</span>
            </div>
          </div>
          <button className={styles.profileIconBtn} onClick={() => setProfileOpen(true)}
            title="Modifier mon profil">
            <div className={styles.avatarSmall}>
              {user?.avatar
                ? <img src={user.avatar} alt="avatar" style={{ width:'100%', height:'100%', objectFit:'cover', borderRadius:'50%' }} />
                : <>{user?.first_name?.[0]}{user?.last_name?.[0]}</>
              }
            </div>
          </button>
          <button className={styles.logoutBtn} onClick={() => { logout(); navigate('/') }}>
            <LogoutIcon /> <span>Déconnexion</span>
          </button>
        </div>
      </header>

      {/* ── MAIN ───────────────────────────────────────────────── */}
      <main className={styles.main}>

        {/* Search bar */}
        <form className={styles.searchForm} onSubmit={handleSubmit}>
          <div className={styles.searchBox}>
            <SearchIcon />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Posez une question sur les TdR… ex : quels sont les livrables attendus ?"
              className={styles.searchInput}
              autoFocus
            />
            {query && (
              <button type="button" className={styles.clearBtn}
                onClick={() => { setQuery(''); setHasSearched(false); setAnswer(''); setSources([]); setError('') }}>
                ×
              </button>
            )}
          </div>
          <button type="submit" className={styles.searchBtn} disabled={loading || !query.trim()}>
            {loading ? <SmallSpinner /> : <>Rechercher <SearchArrow /></>}
          </button>
        </form>

        {/* ── Initial state ── */}
        {!hasSearched && !loading && (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}><BigSearchIcon /></div>
            <h3 className={styles.emptyTitle}>Interrogez les Documents TdR</h3>
            <p className={styles.emptyText}>
              Posez une question en langage naturel. Le système RAG retrouvera
              les passages pertinents et générera une réponse basée sur vos documents.
            </p>
            <div className={styles.suggestions}>
              <span className={styles.suggestLabel}>Exemples :</span>
              {SUGGESTIONS.map(s => (
                <button key={s} className={styles.suggestChip}
                  onClick={() => handleSuggestion(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {/* ── Loading ── */}
        {loading && (
          <div className={styles.loadingState}>
            <div className={styles.loadingSpinner} />
            <p>Analyse sémantique en cours…</p>
          </div>
        )}

        {/* ── Error ── */}
        {error && !loading && (
          <div className={styles.ragBanner}>
            <RagIcon />
            <div>
              <strong>Erreur</strong>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* ── Answer + Sources ── */}
        {hasSearched && !loading && !error && answer && (
          <>
            <div className={styles.answerBox}>
              <div className={styles.answerHeader}>
                <SparkleIcon /> Réponse générée par IA
              </div>
              <p className={styles.answerText}>{answer}</p>
            </div>

            {sources.length > 0 && (
              <div className={styles.sourcesSection}>
                <p className={styles.sourcesTitle}>
                  <DocIcon /> Sources utilisées ({sources.length})
                </p>
                <div className={styles.sourcesList}>
                  {sources.map((s, i) => (
                    <div key={i} className={styles.sourceCard}>
                      <div className={styles.sourceTop}>
                        <span className={styles.sourceFile}>{s.filename}</span>
                        <span className={styles.sourcePage}>Page {s.page}</span>
                        <span className={styles.sourceScore}>{Math.round(s.score * 100)}%</span>
                      </div>
                      <p className={styles.sourceExcerpt}>{s.excerpt}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>

    {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}
    </>
  )
}

/* ── Icons ──────────────────────────────────────────────────────── */
function SearchIcon()  { return <svg className={styles.searchIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> }
function SearchArrow() { return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg> }
function LogoutIcon()  { return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg> }
function BigSearchIcon() {
  return (
    <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg" style={{width:64,height:64,opacity:0.25}}>
      <circle cx="34" cy="34" r="22" stroke="#FFE600" strokeWidth="4"/>
      <line x1="50.5" y1="50.5" x2="70" y2="70" stroke="#FFE600" strokeWidth="4" strokeLinecap="round"/>
      <line x1="26" y1="34" x2="42" y2="34" stroke="#FFE600" strokeWidth="3" strokeLinecap="round"/>
      <line x1="34" y1="26" x2="34" y2="42" stroke="#FFE600" strokeWidth="3" strokeLinecap="round"/>
    </svg>
  )
}
function SmallSpinner() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
    style={{animation:'spin .75s linear infinite', display:'block'}}>
    <circle cx="12" cy="12" r="10" strokeOpacity="0.25"/>
    <path d="M12 2a10 10 0 0110 10"/>
  </svg>
}
function RagIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{flexShrink:0}}>
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>
}
function SparkleIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/>
  </svg>
}
function DocIcon() {
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
  </svg>
}
