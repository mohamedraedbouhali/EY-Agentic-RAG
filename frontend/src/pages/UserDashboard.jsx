import { useState, useCallback, useRef, useEffect } from 'react'
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
  const navigate = useNavigate()

  const [query, setQuery]           = useState('')
  const [messages, setMessages]     = useState([])   // [{role, content, sources?}]
  const [loading, setLoading]       = useState(false)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [error, setError]           = useState('')
  const [profileOpen, setProfileOpen] = useState(false)
  const [expandedSources, setExpandedSources] = useState({})
  const [availableFilters, setAvailableFilters] = useState({})
  const [selectedFilters, setSelectedFilters] = useState({ domain: [], country: [], donor: [], year: [] })
  const [filterPanelOpen, setFilterPanelOpen] = useState(false)

  const bottomRef  = useRef(null)
  const inputRef   = useRef(null)
  const textareaRef = useRef(null)

  // Load persistent history and available filters on mount
  useEffect(() => {
    api.getHistory()
      .then(msgs => setMessages(msgs))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
    api.getFilters()
      .then(f => setAvailableFilters(f))
      .catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const autoResize = () => {
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
    }
  }

  const doSearch = useCallback(async (q = query) => {
    const trimmed = q.trim()
    if (!trimmed || loading) return

    const prevMessages = messages
    setMessages(prev => [...prev, { role: 'user', content: trimmed }])
    setQuery('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    setLoading(true)
    setError('')

    const history = prevMessages.map(m => ({ role: m.role, content: m.content }))

    try {
      const data = await api.search(trimmed, history, selectedFilters)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.answer || '',
        sources: data.sources || [],
        similar_missions: data.similar_missions || [],
      }])
    } catch (err) {
      setError(err.message || 'Erreur lors de la recherche.')
      // Keep the user message visible on error instead of reverting
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }, [query, messages, loading])

  const handleSubmit    = e => { e.preventDefault(); doSearch() }
  const handleSuggestion = s => doSearch(s)
  const handleKeyDown   = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSearch() }
  }
  const handleNewConversation = async () => {
    setMessages([])
    setError('')
    setQuery('')
    setExpandedSources({})
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    inputRef.current?.focus()
    try { await api.clearHistory() } catch {}
  }
  const toggleSources = idx =>
    setExpandedSources(prev => ({ ...prev, [idx]: !prev[idx] }))

  const toggleFilter = (key, value) =>
    setSelectedFilters(prev => ({
      ...prev,
      [key]: prev[key].includes(value)
        ? prev[key].filter(v => v !== value)
        : [...prev[key], value],
    }))

  const clearFilters = () =>
    setSelectedFilters({ domain: [], country: [], donor: [], year: [] })

  const activeFilterCount = Object.values(selectedFilters).flat().length

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
          {messages.length > 0 && (
            <button className={styles.newChatBtn} onClick={handleNewConversation}>
              <PlusIcon /> <span>Nouvelle conversation</span>
            </button>
          )}
          <div className={styles.userChip} onClick={() => setProfileOpen(true)}
            style={{ cursor: 'pointer' }} title="Modifier mon profil">
            <div className={styles.avatar}>
              {user?.avatar
                ? <img src={user.avatar} alt="avatar" style={{ width:'100%', height:'100%', objectFit:'cover', borderRadius:'50%' }} />
                : <>{user?.first_name?.[0]}{user?.last_name?.[0]}</>}
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
                : <>{user?.first_name?.[0]}{user?.last_name?.[0]}</>}
            </div>
          </button>
          <button className={styles.logoutBtn} onClick={() => { logout(); navigate('/') }}>
            <LogoutIcon /> <span>Déconnexion</span>
          </button>
        </div>
      </header>

      {/* ── CHAT AREA ──────────────────────────────────────────── */}
      <div className={styles.chatArea}>
        <div className={styles.chatInner}>

          {/* Empty state */}
          {messages.length === 0 && !loading && !error && !historyLoading && (
            <div className={styles.emptyState}>
              <div className={styles.emptyLogoWrap}>
                <div className={styles.emptyLogoHalo} />
                <div className={styles.emptyLogoRing} />
                <EYLogo />
              </div>
              <div className={styles.emptyHeadingGroup}>
                <p className={styles.emptyOverline}>EY · Agentic Intelligence</p>
                <h3 className={styles.emptyTitle}>Interrogez les Documents TdR</h3>
                <div className={styles.emptyDivider}><span /></div>
                <p className={styles.emptyText}>
                  Posez une question en langage naturel. Le système retrouvera
                  les passages pertinents et générera une réponse basée sur vos documents.
                </p>
              </div>
            </div>
          )}

          {/* Message list */}
          {messages.map((msg, idx) => (
            msg.role === 'user' ? (
              <div key={idx} className={styles.userTurn}>
                <div className={styles.userBubble}>{msg.content}</div>
              </div>
            ) : (
              <div key={idx} className={styles.assistantTurn}>
                <div className={styles.assistantIcon}><SparkleIcon /></div>
                <div className={styles.assistantContent}>
                  <p className={styles.answerText}>{msg.content}</p>
                  {msg.sources?.length > 0 && (
                    <div className={styles.sourcesBlock}>
                      <button className={styles.sourcesToggle} onClick={() => toggleSources(idx)}>
                        <DocIcon />
                        {expandedSources[idx]
                          ? 'Masquer les sources'
                          : `${msg.sources.length} source${msg.sources.length > 1 ? 's' : ''}`}
                        <ChevronIcon open={expandedSources[idx]} />
                      </button>
                      {expandedSources[idx] && (
                        <div className={styles.sourcesList}>
                          {msg.sources.map((s, i) => (
                            <div key={i} className={styles.sourceCard}>
                              <div className={styles.sourceTop}>
                                <span className={styles.sourceFile}>{s.filename}</span>
                                <div className={styles.sourceTopRight}>
                                  <span className={styles.sourceScore}>{(s.score * 100).toFixed(0)}%</span>
                                  <span className={styles.sourcePage}>Page {s.page}</span>
                                </div>
                              </div>
                              {/* Metadata tags */}
                              <div className={styles.sourceTags}>
                                {s.domain  && s.domain  !== 'Inconnu' && <span className={`${styles.sourceTag} ${styles.tagDomain}`}>{s.domain}</span>}
                                {s.country && s.country !== 'Inconnu' && <span className={`${styles.sourceTag} ${styles.tagCountry}`}>{s.country}</span>}
                                {s.donor   && s.donor   !== 'Inconnu' && <span className={`${styles.sourceTag} ${styles.tagDonor}`}>{s.donor}</span>}
                                {s.year    && s.year    !== 'Inconnu' && <span className={`${styles.sourceTag} ${styles.tagYear}`}>{s.year}</span>}
                              </div>
                              <p className={styles.sourceExcerpt}>{s.excerpt}</p>
                              {/* Required profiles */}
                              {s.profiles?.length > 0 && (
                                <div className={styles.sourceSection}>
                                  <span className={styles.sourceSectionLabel}><ProfileIcon /> Profils exigés</span>
                                  <ul className={styles.sourceSectionList}>
                                    {s.profiles.map((p, pi) => <li key={pi}>{p}</li>)}
                                  </ul>
                                </div>
                              )}
                              {/* Required competencies */}
                              {s.competencies?.length > 0 && (
                                <div className={styles.sourceSection}>
                                  <span className={styles.sourceSectionLabel}><SkillIcon /> Compétences exigées</span>
                                  <ul className={styles.sourceSectionList}>
                                    {s.competencies.map((c, ci) => <li key={ci}>{c}</li>)}
                                  </ul>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {/* Similar missions */}
                  {msg.similar_missions?.length > 0 && (
                    <div className={styles.similarBlock}>
                      <span className={styles.similarLabel}><SimilarIcon /> Missions similaires</span>
                      <div className={styles.similarList}>
                        {msg.similar_missions.map((m, i) => (
                          <div key={i} className={styles.similarCard}>
                            <div className={styles.similarTop}>
                              <span className={styles.similarFile}>{m.filename}</span>
                            </div>
                            <div className={styles.sourceTags}>
                              {m.domain  && m.domain  !== 'Inconnu' && <span className={`${styles.sourceTag} ${styles.tagDomain}`}>{m.domain}</span>}
                              {m.country && m.country !== 'Inconnu' && <span className={`${styles.sourceTag} ${styles.tagCountry}`}>{m.country}</span>}
                              {m.donor   && m.donor   !== 'Inconnu' && <span className={`${styles.sourceTag} ${styles.tagDonor}`}>{m.donor}</span>}
                              {m.year    && m.year    !== 'Inconnu' && <span className={`${styles.sourceTag} ${styles.tagYear}`}>{m.year}</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )
          ))}

          {/* Typing indicator */}
          {loading && (
            <div className={styles.assistantTurn}>
              <div className={styles.assistantIcon}><SparkleIcon /></div>
              <div className={styles.typingIndicator}>
                <span /><span /><span />
              </div>
            </div>
          )}

          {/* Error */}
          {error && !loading && (
            <div className={styles.ragBanner}>
              <RagIcon />
              <div>
                <strong>Erreur</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── INPUT BAR ──────────────────────────────────────────── */}
      <div className={styles.inputBar}>
        <div className={styles.inputInner}>

          {/* Filter panel */}
          {filterPanelOpen && (
            <div className={styles.filterPanel}>
              {[
                { key: 'domain',  label: 'Domaine',  values: availableFilters.domain  || [] },
                { key: 'country', label: 'Pays',     values: availableFilters.country || [] },
                { key: 'donor',   label: 'Bailleur', values: availableFilters.donor   || [] },
                { key: 'year',    label: 'Année',    values: availableFilters.year    || [] },
              ].filter(g => g.values.length > 0).map(group => (
                <div key={group.key} className={styles.filterGroup}>
                  <span className={styles.filterGroupLabel}>{group.label}</span>
                  <div className={styles.filterChips}>
                    {group.values.map(v => (
                      <button
                        key={v}
                        type="button"
                        className={`${styles.filterChip}${selectedFilters[group.key].includes(v) ? ' ' + styles.filterChipActive : ''}`}
                        onClick={() => toggleFilter(group.key, v)}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {activeFilterCount > 0 && (
                <button type="button" className={styles.clearFiltersBtn} onClick={clearFilters}>
                  Effacer les filtres
                </button>
              )}
            </div>
          )}

          <form className={styles.searchForm} onSubmit={handleSubmit}>
            <div className={styles.searchBox}>
              <SearchIcon />
              <textarea
                ref={el => { textareaRef.current = el; inputRef.current = el }}
                value={query}
                onChange={e => { setQuery(e.target.value); autoResize() }}
                onKeyDown={handleKeyDown}
                placeholder="Posez une question sur les TdR…"
                className={styles.searchInput}
                rows={1}
                autoFocus
              />
              {query && (
                <button type="button" className={styles.clearBtn}
                  onClick={() => { setQuery(''); if (textareaRef.current) textareaRef.current.style.height = 'auto' }}>
                  ×
                </button>
              )}
            </div>
            <button type="submit" className={styles.searchBtn} disabled={loading || !query.trim()}>
              {loading ? <SmallSpinner /> : <SendIcon />}
            </button>
          </form>
          <div className={styles.inputMeta}>
            <button
              type="button"
              className={`${styles.filterToggleBtn}${filterPanelOpen ? ' ' + styles.filterToggleBtnActive : ''}`}
              onClick={() => setFilterPanelOpen(o => !o)}
            >
              <FilterIcon />
              Filtres
              {activeFilterCount > 0 && (
                <span className={styles.filterBadge}>{activeFilterCount}</span>
              )}
            </button>
            <p className={styles.inputHint}>Entrée pour envoyer · Maj+Entrée pour nouvelle ligne</p>
          </div>
        </div>
      </div>

    </div>

    {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}
    </>
  )
}

/* ── Icons ──────────────────────────────────────────────────────── */
function SearchIcon() {
  return <svg className={styles.searchIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
}
function SendIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
}
function LogoutIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
}
function PlusIcon() {
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
}
function EYLogo() {
  return <img src="/ey.jpg" alt="EY" style={{ width: 110, height: 110, objectFit: 'contain', borderRadius: 20, position: 'relative', zIndex: 1, boxShadow: '0 12px 40px rgba(46,46,56,0.18)' }} />
}
function SmallSpinner() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
    style={{ animation:'spin .75s linear infinite', display:'block' }}>
    <circle cx="12" cy="12" r="10" strokeOpacity="0.25"/>
    <path d="M12 2a10 10 0 0110 10"/>
  </svg>
}
function RagIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink:0 }}>
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>
}
function SparkleIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/>
  </svg>
}
function DocIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
  </svg>
}
function ChevronIcon({ open }) {
  return <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
    style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition:'transform 0.2s' }}>
    <polyline points="6 9 12 15 18 9"/>
  </svg>
}
function ProfileIcon() {
  return <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>
  </svg>
}
function SkillIcon() {
  return <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
  </svg>
}
function SimilarIcon() {
  return <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="7" height="9" rx="1"/><rect x="15" y="3" width="7" height="9" rx="1"/><rect x="2" y="16" width="7" height="5" rx="1"/><rect x="15" y="16" width="7" height="5" rx="1"/>
  </svg>
}
function FilterIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
  </svg>
}
