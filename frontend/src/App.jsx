import { useState, useEffect, useCallback } from 'react'
import './App.css'

// Static mode: when VITE_STATIC=1 is set at build time (e.g. Vercel deploy),
// the app loads a snapshot from /data.json instead of hitting a live backend.
// All mutation actions (scan, delete, toggle) are disabled in this mode.
const STATIC_MODE = import.meta.env.VITE_STATIC === '1'
const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '')
const API = STATIC_MODE ? null : `${API_BASE}/api`
let _snapshot = null
async function loadSnapshot() {
  if (_snapshot) return _snapshot
  const res = await fetch('/data.json')
  _snapshot = await res.json()
  return _snapshot
}

const COUNTRIES = [
  'Turkey', 'USA', 'Germany', 'UK', 'France', 'Netherlands', 'Spain',
  'Italy', 'Sweden', 'Switzerland', 'Israel', 'UAE', 'India', 'Brazil',
  'Canada', 'Australia', 'Singapore', 'Japan', 'South Korea', 'Indonesia',
  'Nigeria', 'Kenya', 'Egypt', 'Saudi Arabia', 'Poland', 'Ireland',
  'Finland', 'Norway', 'Denmark', 'Belgium', 'Austria', 'Portugal',
  'Czech Republic', 'Romania', 'Estonia', 'Latvia', 'Lithuania',
  'Mexico', 'Colombia', 'Argentina', 'Chile', 'China',
]

function loadRecent(key) {
  try { return JSON.parse(localStorage.getItem(key) || '[]') } catch { return [] }
}
function saveRecent(key, value, max = 5) {
  const list = loadRecent(key).filter(v => v !== value)
  list.unshift(value)
  localStorage.setItem(key, JSON.stringify(list.slice(0, max)))
}

function App() {
  const [tab, setTab] = useState('dashboard')
  const [stats, setStats] = useState(null)
  const [sources, setSources] = useState([])
  const [topics, setTopics] = useState([])
  const [companies, setCompanies] = useState([])
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState(null)
  const [newSource, setNewSource] = useState({ name: '', url: '' })
  const [newTopic, setNewTopic] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [showNewOnly, setShowNewOnly] = useState(false)
  const [showRaisingOnly, setShowRaisingOnly] = useState(false)
  const [activityFilter, setActivityFilter] = useState('') // '', raising, recent_round, demo_day
  const [topicFilter, setTopicFilter] = useState(false)
  const [error, setError] = useState('')
  const [scanCountry, setScanCountry] = useState('')
  const [scanTopicIds, setScanTopicIds] = useState([])
  const [showScanModal, setShowScanModal] = useState(false)
  const [countrySearch, setCountrySearch] = useState('')
  const [recentCountries, setRecentCountries] = useState(() => loadRecent('recentCountries'))
  const [recentTopicIds, setRecentTopicIds] = useState(() => loadRecent('recentTopicIds'))
  const [expandedRow, setExpandedRow] = useState(null)
  const [yearMin, setYearMin] = useState('')
  const [yearMax, setYearMax] = useState('')
  const [locationFilter, setLocationFilter] = useState('')

  const fetchStats = useCallback(async () => {
    try {
      if (STATIC_MODE) { setStats((await loadSnapshot()).dashboard); return }
      const res = await fetch(`${API}/dashboard`)
      if (res.ok) setStats(await res.json())
    } catch {}
  }, [])

  const fetchSources = useCallback(async () => {
    try {
      if (STATIC_MODE) { setSources((await loadSnapshot()).sources); return }
      const res = await fetch(`${API}/sources`)
      if (res.ok) setSources(await res.json())
    } catch {}
  }, [])

  const fetchTopics = useCallback(async () => {
    try {
      if (STATIC_MODE) { setTopics((await loadSnapshot()).topics); return }
      const res = await fetch(`${API}/topics`)
      if (res.ok) setTopics(await res.json())
    } catch {}
  }, [])

  const fetchCompanies = useCallback(async () => {
    try {
      if (STATIC_MODE) {
        const snap = await loadSnapshot()
        let list = snap.companies
        if (showNewOnly) list = list.filter(c => c.is_new)
        if (showRaisingOnly) list = list.filter(c => c.is_raising)
        if (activityFilter) list = list.filter(c => c.activity_type === activityFilter)
        if (searchQuery) {
          const q = searchQuery.toLowerCase()
          list = list.filter(c =>
            (c.name && c.name.toLowerCase().includes(q)) ||
            (c.description && c.description.toLowerCase().includes(q)) ||
            (c.industry && c.industry.toLowerCase().includes(q)) ||
            (c.founders && c.founders.join(' ').toLowerCase().includes(q))
          )
        }
        if (yearMin) list = list.filter(c => c.founded_year && c.founded_year >= parseInt(yearMin))
        if (yearMax) list = list.filter(c => c.founded_year && c.founded_year <= parseInt(yearMax))
        if (locationFilter) {
          const l = locationFilter.toLowerCase()
          list = list.filter(c => (c.location || '').toLowerCase().includes(l))
        }
        setCompanies(list)
        return
      }
      const params = new URLSearchParams()
      if (showNewOnly) params.set('new_only', 'true')
      if (showRaisingOnly) params.set('raising_only', 'true')
      if (activityFilter) params.set('activity_type', activityFilter)
      if (searchQuery) params.set('search', searchQuery)
      if (topicFilter) params.set('topic_filter', 'true')
      if (yearMin) params.set('year_min', yearMin)
      if (yearMax) params.set('year_max', yearMax)
      if (locationFilter) params.set('location', locationFilter)
      const res = await fetch(`${API}/companies?${params}`)
      if (res.ok) setCompanies(await res.json())
    } catch {}
  }, [showNewOnly, showRaisingOnly, activityFilter, searchQuery, topicFilter, yearMin, yearMax, locationFilter])

  useEffect(() => {
    fetchStats(); fetchSources(); fetchTopics(); fetchCompanies()
  }, [fetchStats, fetchSources, fetchTopics, fetchCompanies])

  useEffect(() => { fetchCompanies() }, [showNewOnly, showRaisingOnly, activityFilter, searchQuery, topicFilter, yearMin, yearMax, locationFilter, fetchCompanies])

  const addSource = async (e) => {
    e.preventDefault()
    setError('')
    if (!newSource.name || !newSource.url) return
    try {
      const res = await fetch(`${API}/sources`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSource),
      })
      if (res.ok) {
        setNewSource({ name: '', url: '' })
        fetchSources(); fetchStats()
      } else {
        const data = await res.json()
        setError(data.detail || 'Failed to add source')
      }
    } catch { setError('Connection failed') }
  }

  const deleteSource = async (id) => {
    await fetch(`${API}/sources/${id}`, { method: 'DELETE' })
    fetchSources(); fetchStats()
  }

  const toggleSource = async (id) => {
    await fetch(`${API}/sources/${id}/toggle`, { method: 'PATCH' })
    fetchSources()
  }

  const addTopic = async (e) => {
    e.preventDefault()
    setError('')
    if (!newTopic) return
    try {
      const res = await fetch(`${API}/topics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newTopic }),
      })
      if (res.ok) {
        setNewTopic('')
        fetchTopics(); fetchStats()
      } else {
        const data = await res.json()
        setError(data.detail || 'Failed')
      }
    } catch { setError('Connection failed') }
  }

  const deleteTopic = async (id) => {
    await fetch(`${API}/topics/${id}`, { method: 'DELETE' })
    fetchTopics(); fetchStats()
  }

  const toggleTopic = async (id) => {
    await fetch(`${API}/topics/${id}/toggle`, { method: 'PATCH' })
    fetchTopics()
  }

  const seedTopics = async () => {
    await fetch(`${API}/seed`, { method: 'POST' })
    fetchTopics(); fetchStats()
  }

  const seedTurkishSources = async () => {
    await fetch(`${API}/seed-sources-tr`, { method: 'POST' })
    fetchSources(); fetchStats()
  }

  const toggleScanTopic = (id) => {
    setScanTopicIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const selectCountry = (c) => {
    setScanCountry(c)
    setCountrySearch('')
  }

  const runScan = async () => {
    setScanning(true)
    setScanResult(null)
    setError('')
    // Save to recents
    if (scanCountry.trim()) {
      saveRecent('recentCountries', scanCountry.trim())
      setRecentCountries(loadRecent('recentCountries'))
    }
    if (scanTopicIds.length > 0) {
      const key = scanTopicIds.sort().join(',')
      saveRecent('recentTopicIds', key)
      setRecentTopicIds(loadRecent('recentTopicIds'))
    }
    try {
      const body = {}
      if (scanCountry.trim()) body.country = scanCountry.trim()
      if (scanTopicIds.length > 0) body.topic_ids = scanTopicIds
      const res = await fetch(`${API}/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const data = await res.json()
        setScanResult(data)
        fetchCompanies(); fetchStats(); fetchSources()
        setTab('results')
      } else {
        const data = await res.json()
        setError(data.detail || 'Scan failed')
      }
    } catch {
      setError('Connection failed. Is the backend running?')
    }
    setScanning(false)
  }

  const markSeen = async (id) => {
    await fetch(`${API}/companies/${id}/mark-seen`, { method: 'PATCH' })
    fetchCompanies(); fetchStats()
  }

  const markAllSeen = async () => {
    await fetch(`${API}/companies/mark-all-seen`, { method: 'PATCH' })
    fetchCompanies(); fetchStats()
  }

  const deleteCompany = async (id) => {
    await fetch(`${API}/companies/${id}`, { method: 'DELETE' })
    fetchCompanies(); fetchStats()
  }

  const exportExcel = () => {
    const params = new URLSearchParams()
    if (showNewOnly) params.set('new_only', 'true')
    if (showRaisingOnly) params.set('raising_only', 'true')
    window.open(`${API}/export/excel?${params}`, '_blank')
  }

  const filteredCountries = countrySearch
    ? COUNTRIES.filter(c => c.toLowerCase().includes(countrySearch.toLowerCase()))
    : []

  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'sources', label: 'Sources' },
    { id: 'topics', label: 'Topics' },
    { id: 'results', label: `Companies${stats?.new_companies ? ` (${stats.new_companies})` : ''}` },
  ]

  return (
    <div className="app">
      <header>
        <div className="header-row">
          <h1>VC Scout {STATIC_MODE && <span className="static-badge">Read-only snapshot</span>}</h1>
          {!STATIC_MODE && (
            <button className={`btn-primary ${scanning ? 'loading' : ''}`} onClick={() => { if (!scanning) setShowScanModal(true) }} disabled={scanning}>
              {scanning ? 'Scanning...' : 'Run Scan'}
            </button>
          )}
        </div>
        <nav>
          {tabs.map(t => (
            <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {showScanModal && (
        <div className="modal-overlay" onClick={() => setShowScanModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Scan Settings</h2>
              <button className="modal-close" onClick={() => setShowScanModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              {/* Country Selection */}
              <div className="scan-field">
                <label>Country</label>
                {scanCountry ? (
                  <div className="selected-value">
                    <span>{scanCountry}</span>
                    <button onClick={() => setScanCountry('')}>&times;</button>
                  </div>
                ) : (
                  <>
                    <input
                      type="text"
                      placeholder="Search country..."
                      value={countrySearch}
                      onChange={e => setCountrySearch(e.target.value)}
                      autoFocus
                    />
                    {recentCountries.length > 0 && !countrySearch && (
                      <div className="recent-section">
                        <span className="recent-label">Recent</span>
                        <div className="option-chips">
                          {recentCountries.map(c => (
                            <button key={c} className="option-chip recent" onClick={() => selectCountry(c)}>{c}</button>
                          ))}
                        </div>
                      </div>
                    )}
                    {!countrySearch && (
                      <div className="option-grid">
                        {COUNTRIES.map(c => (
                          <button key={c} className="option-chip" onClick={() => selectCountry(c)}>{c}</button>
                        ))}
                      </div>
                    )}
                    {countrySearch && (
                      <div className="option-grid">
                        {filteredCountries.length === 0 && (
                          <button className="option-chip" onClick={() => selectCountry(countrySearch)}>{countrySearch} (custom)</button>
                        )}
                        {filteredCountries.map(c => (
                          <button key={c} className="option-chip" onClick={() => selectCountry(c)}>{c}</button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Topic Selection */}
              <div className="scan-field">
                <label>Topics</label>
                {topics.length === 0 ? (
                  <span className="muted small">No topics yet. Add them in the Topics tab.</span>
                ) : (
                  <>
                    {recentTopicIds.length > 0 && scanTopicIds.length === 0 && (
                      <div className="recent-section">
                        <span className="recent-label">Recent combinations</span>
                        <div className="option-chips">
                          {recentTopicIds.map((combo, i) => {
                            const ids = combo.split(',').map(Number)
                            const names = ids.map(id => topics.find(t => t.id === id)?.name).filter(Boolean)
                            if (names.length === 0) return null
                            return (
                              <button key={i} className="option-chip recent" onClick={() => setScanTopicIds(ids)}>
                                {names.join(', ')}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )}
                    <div className="scan-topic-chips">
                      {topics.map(t => (
                        <span
                          key={t.id}
                          className={`chip ${scanTopicIds.includes(t.id) ? 'active' : ''}`}
                          onClick={() => toggleScanTopic(t.id)}
                        >
                          {t.name}
                        </span>
                      ))}
                    </div>
                    {scanTopicIds.length > 0 && (
                      <button className="btn-sm" style={{ marginTop: 6, alignSelf: 'flex-start' }} onClick={() => setScanTopicIds([])}>Clear topics</button>
                    )}
                  </>
                )}
              </div>

              {/* Summary */}
              {(scanCountry || scanTopicIds.length > 0) && (
                <div className="scan-summary">
                  {scanCountry && <span className="tag">Country: {scanCountry}</span>}
                  {scanTopicIds.length > 0 && (
                    <span className="tag">{scanTopicIds.length} topic(s): {scanTopicIds.map(id => topics.find(t => t.id === id)?.name).filter(Boolean).join(', ')}</span>
                  )}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-outline" onClick={() => setShowScanModal(false)}>Cancel</button>
              <button className="btn-primary" onClick={() => { setShowScanModal(false); runScan() }}>Start Scan</button>
            </div>
          </div>
        </div>
      )}

      {error && <div className="error">{error}<button onClick={() => setError('')}>Dismiss</button></div>}

      <main>
        {tab === 'dashboard' && (
          <section>
            <div className="stats">
              <div className="stat"><span className="stat-n">{stats?.total_companies || 0}</span><span className="stat-l">Companies</span></div>
              <div className="stat accent"><span className="stat-n">{stats?.new_companies || 0}</span><span className="stat-l">New</span></div>
              <div className="stat raising" style={{ cursor: 'pointer' }} onClick={() => { setActivityFilter('raising'); setTab('results') }}>
                <span className="stat-n">{stats?.raising_now || 0}</span>
                <span className="stat-l">Raising Now 💰</span>
              </div>
              <div className="stat recent" style={{ cursor: 'pointer' }} onClick={() => { setActivityFilter('recent_round'); setTab('results') }}>
                <span className="stat-n">{stats?.recent_round || 0}</span>
                <span className="stat-l">Recently Raised 📰</span>
              </div>
              <div className="stat vc" style={{ cursor: 'pointer' }} onClick={() => { setActivityFilter('vc_portfolio'); setTab('results') }}>
                <span className="stat-n">{stats?.vc_portfolio || 0}</span>
                <span className="stat-l">VC-Backed 🏦</span>
              </div>
              <div className="stat demo" style={{ cursor: 'pointer' }} onClick={() => { setActivityFilter('demo_day'); setTab('results') }}>
                <span className="stat-n">{stats?.demo_day || 0}</span>
                <span className="stat-l">Demo Day 🎤</span>
              </div>
              <div className="stat"><span className="stat-n">{stats?.total_sources || 0}</span><span className="stat-l">Sources</span></div>
              <div className="stat"><span className="stat-n">{stats?.active_topics || 0}</span><span className="stat-l">Topics</span></div>
            </div>
            {stats?.last_scan && <p className="muted small">Last scan: {new Date(stats.last_scan).toLocaleString()}</p>}
            {scanResult && (
              <div className="notice">
                Scanned {scanResult.sources_scanned} source(s), crawled {scanResult.pages_crawled} page(s), found {scanResult.new_companies_found} new company(ies).
              </div>
            )}
            <div className="help-box">
              <p><strong>1.</strong> Add website URLs in Sources</p>
              <p><strong>2.</strong> Optionally set topic filters</p>
              <p><strong>3.</strong> Click Run Scan — the crawler will explore each website to find companies</p>
            </div>
          </section>
        )}

        {tab === 'sources' && (
          <section>
            <h2>Sources</h2>
            <p className="muted">Add the websites you want to scan for companies. The crawler will follow internal links to find portfolio/company pages.</p>
            {!STATIC_MODE && (
            <form className="inline-form" onSubmit={addSource}>
              <input placeholder="Name" value={newSource.name} onChange={e => setNewSource({ ...newSource, name: e.target.value })} />
              <input type="url" placeholder="https://..." value={newSource.url} onChange={e => setNewSource({ ...newSource, url: e.target.value })} />
              <button type="submit" className="btn-primary">Add</button>
              <button type="button" className="btn-outline" onClick={seedTurkishSources}>Load Turkish Raising Sources</button>
            </form>
            )}
            {sources.length === 0 && <p className="empty">No sources yet.</p>}
            <div className="list">
              {sources.map(s => (
                <div key={s.id} className={`list-row ${!s.is_active ? 'dimmed' : ''}`}>
                  <div className="list-info">
                    <strong>{s.name}</strong>
                    <span className="muted small">{s.url}</span>
                    {s.last_scraped_at && <span className="muted small">Scraped: {new Date(s.last_scraped_at).toLocaleString()}</span>}
                  </div>
                  <div className="list-actions">
                    <span className={`btn-sm ${s.is_active ? 'on' : 'off'}`}>
                      {s.is_active ? 'Active' : 'Off'}
                    </span>
                    {!STATIC_MODE && (
                      <>
                        <button className={`btn-sm ${s.is_active ? 'on' : 'off'}`} onClick={() => toggleSource(s.id)}>Toggle</button>
                        <button className="btn-sm danger" onClick={() => deleteSource(s.id)}>Delete</button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {tab === 'topics' && (
          <section>
            <h2>Topics</h2>
            <p className="muted">Filter results by topic. If none are active, all found companies are shown.</p>
            <div className="topic-bar">
              <form className="inline-form" onSubmit={addTopic}>
                <input placeholder="Add topic..." value={newTopic} onChange={e => setNewTopic(e.target.value)} />
                <button type="submit" className="btn-primary">Add</button>
              </form>
              <button className="btn-outline" onClick={seedTopics}>Load Defaults</button>
            </div>
            <div className="chips">
              {topics.length === 0 && <p className="empty">No topics yet.</p>}
              {topics.map(t => (
                <span key={t.id} className={`chip ${t.is_active ? 'active' : ''}`} onClick={() => toggleTopic(t.id)}>
                  {t.name}
                  <button onClick={e => { e.stopPropagation(); deleteTopic(t.id) }}>x</button>
                </span>
              ))}
            </div>
          </section>
        )}

        {tab === 'results' && (
          <section>
            <div className="results-top">
              <h2>Companies ({companies.length})</h2>
              <div className="results-controls">
                <input type="text" placeholder="Search..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className="search" />
                <label className="check"><input type="checkbox" checked={showNewOnly} onChange={e => setShowNewOnly(e.target.checked)} /> New only</label>
                <div className="activity-chips">
                  <button className={`chip ${activityFilter === '' ? 'active' : ''}`} onClick={() => setActivityFilter('')}>All</button>
                  <button className={`chip ${activityFilter === 'raising' ? 'active' : ''}`} onClick={() => setActivityFilter('raising')}>💰 Raising Now</button>
                  <button className={`chip ${activityFilter === 'recent_round' ? 'active' : ''}`} onClick={() => setActivityFilter('recent_round')}>📰 Recently Raised</button>
                  <button className={`chip ${activityFilter === 'vc_portfolio' ? 'active' : ''}`} onClick={() => setActivityFilter('vc_portfolio')}>🏦 VC-Backed</button>
                  <button className={`chip ${activityFilter === 'demo_day' ? 'active' : ''}`} onClick={() => setActivityFilter('demo_day')}>🎤 Demo Day</button>
                </div>
                <label className="check"><input type="checkbox" checked={topicFilter} onChange={e => setTopicFilter(e.target.checked)} /> Topic filter</label>
                <select className="location-select" value={locationFilter} onChange={e => setLocationFilter(e.target.value)}>
                  <option value="">All locations</option>
                  {COUNTRIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <div className="year-filter">
                  <input type="number" placeholder="From" value={yearMin} onChange={e => setYearMin(e.target.value)} className="year-input" min="1900" max="2030" />
                  <span className="muted">–</span>
                  <input type="number" placeholder="To" value={yearMax} onChange={e => setYearMax(e.target.value)} className="year-input" min="1900" max="2030" />
                </div>
                {!STATIC_MODE && <button className="btn-outline" onClick={exportExcel}>Export Excel</button>}
                {!STATIC_MODE && <button className="btn-outline" onClick={markAllSeen}>Mark All Seen</button>}
              </div>
            </div>
            {companies.length === 0 && <p className="empty">No companies found. Run a scan to discover companies.</p>}
            {companies.length > 0 && (
              <div className="table-wrap">
                <table className="company-table">
                  <thead>
                    <tr>
                      <th className="th-status"></th>
                      <th className="th-name">Company</th>
                      <th className="th-raising">Raising</th>
                      <th className="th-founders">Founders</th>
                      <th className="th-industry">Industry</th>
                      <th className="th-location">Location</th>
                      <th className="th-founded">Founded</th>
                      <th className="th-website">Website</th>
                      <th className="th-actions"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {companies.map(c => (
                      <>
                        <tr key={c.id} className={`table-row ${c.is_new ? 'row-new' : ''} ${c.is_raising ? 'row-raising' : ''} ${expandedRow === c.id ? 'row-expanded' : ''}`} onClick={() => setExpandedRow(expandedRow === c.id ? null : c.id)}>
                          <td className="td-status">
                            {c.is_new && <span className="dot-new"></span>}
                          </td>
                          <td className="td-name">
                            <strong>{c.name}</strong>
                            {c.description && <span className="td-desc">{c.description.length > 80 ? c.description.slice(0, 80) + '...' : c.description}</span>}
                          </td>
                          <td className="td-raising">
                            {c.is_raising ? (
                              <span className={`raising-badge act-${c.activity_type || 'raising'}`} title={c.raising_evidence || ''}>
                                {c.activity_type === 'recent_round' ? '📰 ' : c.activity_type === 'vc_portfolio' ? '🏦 ' : c.activity_type === 'demo_day' ? '🎤 ' : '💰 '}
                                {c.seeking_amount || (c.activity_type === 'recent_round' ? 'Recent' : c.activity_type === 'vc_portfolio' ? 'VC-Backed' : c.activity_type === 'demo_day' ? 'Demo Day' : 'Raising')}
                                {c.funding_stage && <span className="stage-sub">{c.funding_stage}</span>}
                              </span>
                            ) : <span className="muted">-</span>}
                          </td>
                          <td className="td-founders">
                            {c.founders && c.founders.length > 0
                              ? <span>{c.founders.slice(0, 2).join(', ')}{c.founders.length > 2 ? ` +${c.founders.length - 2}` : ''}</span>
                              : <span className="muted">-</span>}
                          </td>
                          <td className="td-industry">{c.industry ? <span className="tag">{c.industry}</span> : <span className="muted">-</span>}</td>
                          <td className="td-location">{c.location || <span className="muted">-</span>}</td>
                          <td className="td-founded">{c.founded_year || <span className="muted">-</span>}</td>
                          <td className="td-website">{c.website ? <a href={c.website} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>{c.website.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}</a> : <span className="muted">-</span>}</td>
                          <td className="td-actions">
                            {!STATIC_MODE && c.is_new && <button className="btn-sm" onClick={e => { e.stopPropagation(); markSeen(c.id) }}>Seen</button>}
                            {!STATIC_MODE && <button className="btn-sm danger" onClick={e => { e.stopPropagation(); deleteCompany(c.id) }}>Del</button>}
                          </td>
                        </tr>
                        {expandedRow === c.id && (
                          <tr key={`${c.id}-detail`} className="detail-row">
                            <td colSpan={9}>
                              <div className="detail-content">
                                {c.is_raising && (
                                  <div className="detail-field raising-block">
                                    <span className="detail-label">💰 Fundraising</span>
                                    <p>
                                      <strong>{c.seeking_amount || 'Amount not specified'}</strong>
                                      {c.funding_stage && <> · <em>{c.funding_stage}</em></>}
                                    </p>
                                    {c.raising_evidence && <p className="muted small">"{c.raising_evidence}"</p>}
                                  </div>
                                )}
                                {c.founders && c.founders.length > 0 && (
                                  <div className="detail-field">
                                    <span className="detail-label">Founders</span>
                                    <p>{c.founders.join(', ')}</p>
                                  </div>
                                )}
                                {c.description && (
                                  <div className="detail-field">
                                    <span className="detail-label">Description</span>
                                    <p>{c.description}</p>
                                  </div>
                                )}
                                <div className="detail-grid">
                                  {c.industry && (
                                    <div className="detail-field">
                                      <span className="detail-label">Industry</span>
                                      <p>{c.industry}</p>
                                    </div>
                                  )}
                                  {c.location && (
                                    <div className="detail-field">
                                      <span className="detail-label">Location</span>
                                      <p>{c.location}</p>
                                    </div>
                                  )}
                                  {c.website && (
                                    <div className="detail-field">
                                      <span className="detail-label">Website</span>
                                      <p><a href={c.website} target="_blank" rel="noopener noreferrer">{c.website}</a></p>
                                    </div>
                                  )}
                                  {c.source_name && (
                                    <div className="detail-field">
                                      <span className="detail-label">Found via</span>
                                      <p>{c.source_name}</p>
                                    </div>
                                  )}
                                  {c.page_url && (
                                    <div className="detail-field">
                                      <span className="detail-label">Source page</span>
                                      <p><a href={c.page_url} target="_blank" rel="noopener noreferrer">{c.page_url}</a></p>
                                    </div>
                                  )}
                                  <div className="detail-field">
                                    <span className="detail-label">Discovered</span>
                                    <p>{c.discovered_at ? new Date(c.discovered_at).toLocaleString() : '-'}</p>
                                  </div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  )
}

export default App
