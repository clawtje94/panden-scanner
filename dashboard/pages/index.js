import { useState, useEffect, useRef, useMemo } from 'react';
import Head from 'next/head';

const DATA_URL = "https://raw.githubusercontent.com/clawtje94/panden-scanner/data/leads.json";

const eur = (n) => n ? `€${Math.round(n).toLocaleString('nl-NL')}` : '-';
const pct = (n) => (n || n === 0) ? `${n}%` : '-';

// ── Motion / EP-Online helpers ─────────────────────────────────────────────
const isMotivated = (m) => m && m.motivated;
const motionFlags = (m) => {
  if (!m) return [];
  const out = [];
  if (m.prijsverlaging_pct >= 5) out.push({ kind: 'price-strong', label: `-${m.prijsverlaging_pct}% prijs` });
  else if (m.prijsverlaging_pct >= 1) out.push({ kind: 'price', label: `-${m.prijsverlaging_pct}% prijs` });
  if (m.aantal_prijsverlagingen >= 2) out.push({ kind: 'price', label: `${m.aantal_prijsverlagingen}x verlaagd` });
  if (m.dagen_online >= 365) out.push({ kind: 'stale-strong', label: `${m.dagen_online}d online` });
  else if (m.dagen_online >= 180) out.push({ kind: 'stale', label: `${m.dagen_online}d online` });
  else if (m.dagen_online >= 120) out.push({ kind: 'stale-mild', label: `${m.dagen_online}d online` });
  if (m.makelaarswissel) out.push({ kind: 'switch', label: 'Makelaarswissel' });
  if (m.onder_bod_terug) out.push({ kind: 'bid-back', label: 'Bod terug' });
  return out;
};

function PhotoCarousel({ photos, alt, score }) {
  const [idx, setIdx] = useState(0);
  const containerRef = useRef(null);
  const startX = useRef(0);

  if (!photos || photos.length === 0) return null;

  const go = (dir) => {
    setIdx(prev => {
      if (dir > 0) return prev < photos.length - 1 ? prev + 1 : 0;
      return prev > 0 ? prev - 1 : photos.length - 1;
    });
  };

  const onTouchStartPhoto = (e) => { e.stopPropagation(); startX.current = e.touches[0].clientX; };
  const onTouchEndPhoto = (e) => {
    e.stopPropagation();
    const dx = e.changedTouches[0].clientX - startX.current;
    if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
  };

  return (
    <div
      className="card-photo"
      ref={containerRef}
      onTouchStart={onTouchStartPhoto}
      onTouchEnd={onTouchEndPhoto}
      onClick={(e) => {
        e.stopPropagation();
        const rect = containerRef.current.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        go(clickX > rect.width / 2 ? 1 : -1);
      }}
    >
      <img src={photos[idx]} alt={alt} />
      <div className="card-score-big">{score}/10</div>
      {photos.length > 1 && (
        <>
          <div className="photo-dots">
            {photos.map((_, i) => (
              <span key={i} className={`dot ${i === idx ? 'active' : ''}`} />
            ))}
          </div>
          <div className="photo-counter">{idx + 1}/{photos.length}</div>
        </>
      )}
    </div>
  );
}

function SignalBadges({ pand, compact = false }) {
  const m = pand.motion || pand.calc?.motion || {};
  const ep = pand.ep_online || pand.calc?.ep_online || {};
  const wijk = pand.calc?.splitsen?.wijkcheck;

  const flags = motionFlags(m);
  const badges = [];

  if (isMotivated(m)) {
    badges.push(<span key="mv" className="signal-badge motivated">🔥 MOTIVATED {m.motivated_score}/10</span>);
  }
  if (ep.forced_renovation_sterk) {
    badges.push(<span key="frs" className="signal-badge forced-sterk">⚡ FORCED RENO ({ep.label})</span>);
  } else if (ep.forced_renovation) {
    badges.push(<span key="fr" className="signal-badge forced">Label {ep.label} → reno-verplicht</span>);
  }
  if (wijk && wijk.regime === 'den_haag_2026' && wijk.mag === true) {
    badges.push(<span key="dh" className="signal-badge splits-dh">🎯 DH splits-wijk {wijk.wijkscore ? `(score ${wijk.wijkscore})` : ''}</span>);
  }
  if (wijk && wijk.regime === 'rotterdam_2025' && wijk.is_nprz) {
    badges.push(<span key="nprz" className="signal-badge nprz">NPRZ 85m²</span>);
  }

  // Classificatie category badge
  const klass = pand.calc?.classificatie;
  if (klass?.category === 'transformatie') {
    badges.push(<span key="klass" className="signal-badge transformatie">🏢 Transformatie-kandidaat</span>);
  }
  if (klass?.is_verhuurd) {
    badges.push(<span key="verh" className="signal-badge verhuurd">⚠ Verhuurd</span>);
  }

  if (!compact) {
    flags.forEach((f, i) => badges.push(
      <span key={`f${i}`} className={`signal-badge mtn-${f.kind}`}>{f.label}</span>
    ));
  } else if (flags.length > 0) {
    // compact: alleen sterkste flag
    const sterk = flags.find(f => f.kind.endsWith('strong')) || flags[0];
    badges.push(<span key="cflag" className={`signal-badge mtn-${sterk.kind}`}>{sterk.label}</span>);
  }

  return badges.length > 0 ? <div className={`signal-badges ${compact ? 'compact' : ''}`}>{badges}</div> : null;
}

const STATUS = {
  NEW: 'new', SAVED: 'saved', HOT: 'hot', REJECTED: 'rejected',
  VIEWED: 'viewed', CONTACTED: 'contacted', ARCHIVED: 'archived',
};

const STATUS_COLORS = {
  new: '#888', saved: '#00b894', hot: '#ff6b00', rejected: '#666',
  viewed: '#0984e3', contacted: '#fdcb6e', archived: '#444',
};

const SORT_OPTIONS = [
  { key: 'marge', label: 'Marge ↓', fn: (a, b) => (b.marge_pct || 0) - (a.marge_pct || 0) },
  { key: 'winst', label: 'Winst ↓', fn: (a, b) => (b.winst_euro || 0) - (a.winst_euro || 0) },
  { key: 'score', label: 'Score ↓', fn: (a, b) => (b.score || 0) - (a.score || 0) },
  { key: 'motivated', label: 'Motivated ↓', fn: (a, b) => ((b.motion?.motivated_score || 0) - (a.motion?.motivated_score || 0)) || ((b.marge_pct || 0) - (a.marge_pct || 0)) },
  { key: 'dagen', label: 'Dagen online ↓', fn: (a, b) => (b.motion?.dagen_online || 0) - (a.motion?.dagen_online || 0) },
  { key: 'prijs_asc', label: 'Prijs ↑', fn: (a, b) => (a.prijs || 0) - (b.prijs || 0) },
];

export default function Home() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [userState, setUserState] = useState({});
  const [view, setView] = useState('swipe');
  const [currentIdx, setCurrentIdx] = useState(0);
  const [stadFilter, setStadFilter] = useState('alle');
  const [minMarge, setMinMarge] = useState(0);
  const [motivatedOnly, setMotivatedOnly] = useState(false);
  const [forcedOnly, setForcedOnly] = useState(false);
  const [splitsDhOnly, setSplitsDhOnly] = useState(false);
  const [sortKey, setSortKey] = useState('marge');
  const [swipeDir, setSwipeDir] = useState(null);
  const [showNotes, setShowNotes] = useState(false);
  const [notesText, setNotesText] = useState('');
  const touchStart = useRef({ x: 0, y: 0 });

  useEffect(() => {
    fetch(DATA_URL)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { console.error(e); setLoading(false); });

    const saved = localStorage.getItem('panden_state');
    if (saved) { try { setUserState(JSON.parse(saved)); } catch {} }
  }, []);

  const updateStatus = (url, status, extraData = {}) => {
    const newState = {
      ...userState,
      [url]: { ...userState[url], status, updated: new Date().toISOString(), ...extraData },
    };
    setUserState(newState);
    localStorage.setItem('panden_state', JSON.stringify(newState));
  };

  const getStatus = (url) => userState[url]?.status || STATUS.NEW;

  const kansen = useMemo(() => (data?.kansen || []).map(k => ({
    ...k,
    _status: getStatus(k.url),
    _notes: userState[k.url]?.notes || '',
  })), [data, userState]);

  const swipeList = useMemo(() => {
    const sortFn = (SORT_OPTIONS.find(s => s.key === sortKey) || SORT_OPTIONS[0]).fn;
    return kansen
      .filter(k => k._status === STATUS.NEW)
      .filter(k => stadFilter === 'alle' || k.stad === stadFilter)
      .filter(k => k.marge_pct >= minMarge)
      .filter(k => !motivatedOnly || (k.motion?.motivated))
      .filter(k => !forcedOnly || (k.ep_online?.forced_renovation))
      .filter(k => !splitsDhOnly || (k.calc?.splitsen?.wijkcheck?.regime === 'den_haag_2026' && k.calc?.splitsen?.wijkcheck?.mag === true))
      .sort(sortFn);
  }, [kansen, stadFilter, minMarge, motivatedOnly, forcedOnly, splitsDhOnly, sortKey]);

  useEffect(() => {
    const handler = (e) => {
      if (view !== 'swipe' || showNotes) return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); doAction(STATUS.REJECTED); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); doAction(STATUS.SAVED); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); doAction(STATUS.HOT); }
      else if (e.key === ' ') { e.preventDefault(); skipNext(); }
      else if (e.key === 'n' || e.key === 'N') { e.preventDefault(); setShowNotes(true); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  if (loading) return <div className="loading">Laden...</div>;
  if (!data) return <div className="loading">Geen data beschikbaar. Scan moet eerst draaien.</div>;

  const veilingen = data.veilingen || [];
  const kavels = data.kavels || [];
  const biedboek = data.biedboek || [];
  const beleggingen = data.beleggingen || [];
  const steden = ['alle', ...new Set(kansen.map(k => k.stad).filter(Boolean))].sort();

  const savedList = kansen.filter(k => [STATUS.SAVED, STATUS.HOT, STATUS.VIEWED, STATUS.CONTACTED].includes(k._status));
  const rejectedList = kansen.filter(k => k._status === STATUS.REJECTED);
  const hotList = kansen.filter(k => k._status === STATUS.HOT);

  // Counters voor tabs
  const motivatedCount = kansen.filter(k => k._status === STATUS.NEW && k.motion?.motivated).length;
  const forcedCount = kansen.filter(k => k._status === STATUS.NEW && k.ep_online?.forced_renovation).length;

  const current = swipeList[currentIdx];

  const doAction = (status) => {
    if (!current) return;
    setSwipeDir(status === STATUS.REJECTED ? 'left' : status === STATUS.SAVED ? 'right' : 'up');
    setTimeout(() => {
      updateStatus(current.url, status);
      setSwipeDir(null);
    }, 250);
  };
  const skipNext = () => { if (currentIdx < swipeList.length - 1) setCurrentIdx(currentIdx + 1); };

  const onTouchStart = (e) => { touchStart.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }; };
  const onTouchEnd = (e) => {
    const dx = e.changedTouches[0].clientX - touchStart.current.x;
    const dy = e.changedTouches[0].clientY - touchStart.current.y;
    if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy)) doAction(dx > 0 ? STATUS.SAVED : STATUS.REJECTED);
    else if (dy < -80 && Math.abs(dy) > Math.abs(dx)) doAction(STATUS.HOT);
  };

  const saveNotes = () => {
    if (!current) return;
    updateStatus(current.url, current._status, { notes: notesText });
    setShowNotes(false);
    setNotesText('');
  };

  return (
    <>
      <Head>
        <title>Panden Scanner</title>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
      </Head>

      <div className="app">
        <nav className="nav">
          <div className="nav-brand">Panden <span>Scanner</span></div>
          <div className="nav-meta">
            {data.scan_datum && <span>Laatste scan: {new Date(data.scan_datum).toLocaleString('nl-NL')}</span>}
            {motivatedCount > 0 && <span className="meta-chip mv">🔥 {motivatedCount} motivated</span>}
            {forcedCount > 0 && <span className="meta-chip frc">⚡ {forcedCount} forced-reno</span>}
          </div>
          <div className="nav-tabs">
            <button className={`nav-tab ${view === 'swipe' ? 'active' : ''}`} onClick={() => { setView('swipe'); setCurrentIdx(0); }}>
              Nieuw<span className="count">{kansen.filter(k => k._status === STATUS.NEW).length}</span>
            </button>
            <button className={`nav-tab ${view === 'hot' ? 'active' : ''}`} onClick={() => setView('hot')}>
              🔥 Top<span className="count">{hotList.length}</span>
            </button>
            <button className={`nav-tab ${view === 'saved' ? 'active' : ''}`} onClick={() => setView('saved')}>
              💾 Opgeslagen<span className="count">{savedList.length}</span>
            </button>
            <button className={`nav-tab ${view === 'rejected' ? 'active' : ''}`} onClick={() => setView('rejected')}>
              Prullenbak<span className="count">{rejectedList.length}</span>
            </button>
            <button className={`nav-tab ${view === 'veilingen' ? 'active' : ''}`} onClick={() => setView('veilingen')}>
              Veilingen<span className="count">{veilingen.length}</span>
            </button>
            <button className={`nav-tab ${view === 'kavels' ? 'active' : ''}`} onClick={() => setView('kavels')}>
              Kavels<span className="count">{kavels.length}</span>
            </button>
            <button className={`nav-tab ${view === 'beleggingen' ? 'active' : ''}`} onClick={() => setView('beleggingen')}>
              Beleggingen<span className="count">{beleggingen.length}</span>
            </button>
          </div>
        </nav>

        {view === 'swipe' && (
          <div className="swipe-screen">
            <div className="swipe-filters">
              <select value={stadFilter} onChange={e => { setStadFilter(e.target.value); setCurrentIdx(0); }}>
                {steden.map(s => <option key={s}>{s}</option>)}
              </select>
              <select value={minMarge} onChange={e => { setMinMarge(Number(e.target.value)); setCurrentIdx(0); }}>
                <option value={0}>Alle marges</option>
                <option value={10}>≥ 10%</option>
                <option value={15}>≥ 15%</option>
                <option value={20}>≥ 20%</option>
              </select>
              <select value={sortKey} onChange={e => { setSortKey(e.target.value); setCurrentIdx(0); }}>
                {SORT_OPTIONS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
              <div className="progress">{swipeList.length === 0 ? '0 / 0' : `${currentIdx + 1} / ${swipeList.length}`}</div>
            </div>

            <div className="signal-toggles">
              <button
                className={`toggle ${motivatedOnly ? 'on' : ''}`}
                onClick={() => { setMotivatedOnly(!motivatedOnly); setCurrentIdx(0); }}
                title="Alleen motivated sellers tonen"
              >🔥 Motivated</button>
              <button
                className={`toggle ${forcedOnly ? 'on' : ''}`}
                onClick={() => { setForcedOnly(!forcedOnly); setCurrentIdx(0); }}
                title="Alleen panden met verplichte renovatie (label E/F/G)"
              >⚡ Forced-reno</button>
              <button
                className={`toggle ${splitsDhOnly ? 'on' : ''}`}
                onClick={() => { setSplitsDhOnly(!splitsDhOnly); setCurrentIdx(0); }}
                title="Alleen DH splits-wijken (Leefbaarometer ≥ goed)"
              >🎯 DH-splits</button>
            </div>

            {!current ? (
              <div className="empty-state">
                <h2>🎉 Alles doorlopen!</h2>
                <p>Geen nieuwe panden met deze filters.</p>
                <p>Nieuwe kansen verschijnen na de volgende scan (dagelijks 09:00).</p>
              </div>
            ) : (
              <>
                <div
                  className={`swipe-card ${swipeDir ? `swipe-${swipeDir}` : ''}`}
                  onTouchStart={onTouchStart}
                  onTouchEnd={onTouchEnd}
                >
                  {(current.foto_urls?.length > 0 || current.foto_url) && (
                    <PhotoCarousel
                      photos={current.foto_urls?.length > 0 ? current.foto_urls : [current.foto_url]}
                      alt={current.adres}
                      score={current.score}
                    />
                  )}
                  <div className="card-hero">
                    {!current.foto_url && !current.foto_urls?.length && <div className="card-score-big">{current.score}/10</div>}
                    <h1>{current.adres}</h1>
                    <div className="card-location">
                      📍 {current.stad}{current.wijk ? ` · ${current.wijk}` : ''}{current.postcode ? ` · ${current.postcode}` : ''}
                    </div>
                  </div>

                  <SignalBadges pand={current} />

                  <div className="card-quick">
                    <div className="quick-item">
                      <div className="quick-label">Vraagprijs</div>
                      <div className="quick-value">{eur(current.prijs)}</div>
                      <div className="quick-sub">{eur(current.prijs_per_m2)}/m²</div>
                    </div>
                    <div className="quick-item green">
                      <div className="quick-label">Winst</div>
                      <div className="quick-value">{eur(current.winst_euro)}</div>
                      <div className="quick-sub">{current.marge_pct}% marge</div>
                    </div>
                    <div className="quick-item">
                      <div className="quick-label">ROI</div>
                      <div className="quick-value">{current.roi_pct}%</div>
                      <div className="quick-sub">over looptijd</div>
                    </div>
                  </div>

                  <div className="badges">
                    {current.energie_label && <span className="badge label">Label {current.energie_label}</span>}
                    {current.bouwjaar > 0 && <span className="badge">bj {current.bouwjaar}</span>}
                    {current.kamers > 0 && <span className="badge">{current.kamers} kamers</span>}
                    <span className="badge">{current.opp_m2} m²</span>
                    {current.type_woning && <span className="badge">{current.type_woning}</span>}
                    {current.is_opknapper && <span className="badge hot">OPKNAPPER</span>}
                    <span className="badge src">{current.source}</span>
                    {current.calc?.validatie?.goedgekeurd === true && <span className="badge validated">✓ Gevalideerd</span>}
                    {current.calc?.validatie?.goedgekeurd === false && <span className="badge invalidated">⚠ Gecorrigeerd {current.calc.validatie.afwijking_pct}%</span>}
                    {current.calc?.has_garden && <span className="badge extra">Tuin</span>}
                    {current.calc?.has_balcony && <span className="badge extra">Balkon</span>}
                    {current.calc?.has_roof_terrace && <span className="badge extra">Dakterras</span>}
                    {current.calc?.has_parking_on_site && <span className="badge extra">Parkeren</span>}
                    {current.calc?.has_solar_panels && <span className="badge extra">Zonnepanelen</span>}
                    {current.calc?.erfpacht && <span className="badge warn">Erfpacht</span>}
                    {current.calc?.vve_bijdrage > 0 && <span className="badge">VvE €{current.calc.vve_bijdrage}/mnd</span>}
                    {current.calc?.verdieping !== undefined && <span className="badge">Verd. {current.calc.verdieping}</span>}
                    {current.calc?.splitsen?.mag_splitsen === true && <span className="badge extra">Splitsen mogelijk</span>}
                    {current.calc?.opbouwen?.mag_opbouwen === true && <span className="badge extra">Opbouwen mogelijk</span>}
                  </div>

                  <MotionSection motion={current.motion || current.calc?.motion} />
                  <EpOnlineSection ep={current.ep_online || current.calc?.ep_online} />
                  <WijkCheckSection wijk={current.calc?.splitsen?.wijkcheck} />

                  <div className="card-calc">
                    <h3>Aankoop</h3>
                    <div className="calc-grid">
                      <div><span>Vraagprijs</span><b>{eur(current.calc?.vraagprijs)}</b></div>
                      <div><span>OVB + notaris</span><b>{eur((current.calc?.ovb || 0) + (current.calc?.notaris_makelaar_aankoop || 0))}</b></div>
                      <div className="total"><span>Totaal aankoop</span><b>{eur(current.calc?.aankoop_totaal)}</b></div>
                    </div>
                  </div>

                  <div className="card-calc">
                    <h3>Verbouwing ({eur(current.calc?.renovatie_per_m2)}/m²)</h3>
                    <div className="calc-grid">
                      {current.calc?.renovatie_detail?.componenten?.map((comp, i) => (
                        comp.kosten >= 1000 && (
                          <div key={i}><span>{comp.naam}</span><b>{eur(comp.kosten)}</b></div>
                        )
                      ))}
                      <div className="total"><span>Totaal verbouwing</span><b>{eur(current.calc?.bouw_totaal)}</b></div>
                    </div>
                  </div>

                  <div className="card-calc">
                    <h3>Financiering + Verkoop</h3>
                    <div className="calc-grid">
                      <div><span>Rente {current.calc?.rente_pct}% ({current.calc?.looptijd_maanden} mnd)</span><b>{eur(current.calc?.rente)}</b></div>
                      <div className="total"><span>Totale investering</span><b>{eur(current.calc?.totaal_kosten)}</b></div>
                      <div><span>Verkoop ({eur(current.calc?.verkoop_m2)}/m²)</span><b>{eur(current.calc?.bruto_verkoopprijs)}</b></div>
                      <div><span>Kosten makelaar + notaris</span><b>-{eur(current.calc?.verkoop_kosten)}</b></div>
                      <div className="total"><span>Netto opbrengst</span><b>{eur(current.calc?.netto_opbrengst)}</b></div>
                      <div className="profit"><span>Winst</span><b>{eur(current.winst_euro)}</b></div>
                    </div>

                    {current.calc?.bod && (
                      <div className="bod-teaser">
                        Bod {eur(current.calc.bod)} (-{current.calc.bod_korting_pct}%) → winst {eur(current.calc.bod_winst)} · marge {current.calc.bod_marge_pct}%
                      </div>
                    )}
                  </div>

                  {current.calc?.referenties?.length > 0 && (
                    <div className="card-refs">
                      <h3>Referentie panden {current.calc.referenties[0]?.wijk && `(${current.calc.referenties[0].wijk})`}</h3>
                      {current.calc.referenties.slice(0, 3).map((r, i) => (
                        <div key={i} className="ref">
                          <div className="ref-addr">{r.adres}</div>
                          <div className="ref-details">
                            {eur(r.prijs)} · {r.opp_m2}m² · <b>{eur(r.prijs_per_m2)}/m²</b> · label {r.energie_label}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <a href={current.url} target="_blank" rel="noopener noreferrer" className="view-link">
                    Bekijk op {current.source} →
                  </a>
                </div>

                <div className="swipe-actions">
                  <button className="action reject" onClick={() => doAction(STATUS.REJECTED)} title="Afwijzen (←)">✕</button>
                  <button className="action skip" onClick={skipNext} title="Overslaan (space)">→</button>
                  <button className="action note" onClick={() => { setNotesText(current._notes); setShowNotes(true); }} title="Notitie (N)">📝</button>
                  <button className="action save" onClick={() => doAction(STATUS.SAVED)} title="Opslaan (→)">💾</button>
                  <button className="action hot" onClick={() => doAction(STATUS.HOT)} title="Top deal (↑)">🔥</button>
                </div>

                <div className="swipe-hints">
                  <span>← afwijzen</span><span>→ opslaan</span><span>↑ top deal</span>
                  <span>space skip</span><span>N notitie</span>
                </div>
              </>
            )}
          </div>
        )}

        {(view === 'saved' || view === 'hot' || view === 'rejected') && (
          <ListView
            title={
              view === 'saved' ? `💾 Opgeslagen (${savedList.length})` :
              view === 'hot' ? `🔥 Top deals (${hotList.length})` :
              `🗑️ Prullenbak (${rejectedList.length})`
            }
            items={view === 'saved' ? savedList : view === 'hot' ? hotList : rejectedList}
            userState={userState}
            updateStatus={updateStatus}
            showRestore={view === 'rejected'}
          />
        )}

        {(view === 'veilingen' || view === 'kavels' || view === 'beleggingen') && (
          <div className="list-screen">
            <h2 className="list-title">
              {view === 'veilingen' ? `Veilingen (${veilingen.length})` :
               view === 'kavels' ? `Kavels (${kavels.length})` :
               `Beleggingen & verhuurde panden (${beleggingen.length})`}
            </h2>
            {view === 'beleggingen' && (
              <p className="subtle">Deze panden zijn verhuurd of als belegging aangeboden. Géén directe ontwikkel-kans: eerst huurder uit of uitpond-strategie beoordelen.</p>
            )}
            <div className="list-grid">
              {(view === 'veilingen' ? veilingen : view === 'kavels' ? kavels : beleggingen).map((item, i) => (
                <div key={i} className="list-card">
                  {item.foto_url && (
                    <div className="list-card-photo">
                      <img src={item.foto_url} alt={item.adres} />
                    </div>
                  )}
                  <div className="list-card-header" style={{padding: '12px 16px 0'}}>
                    <div>
                      <div className="list-card-title">{item.adres}</div>
                      <div className="list-card-sub">{item.stad}{item.postcode ? ` · ${item.postcode}` : ''}</div>
                    </div>
                  </div>
                  <div className="list-card-metrics" style={{padding: '8px 16px'}}>
                    {item.prijs > 0 && <div><span>{view === 'veilingen' ? 'Startbod' : 'Prijs'}</span><b>{eur(item.prijs)}</b></div>}
                    {item.opp_m2 > 0 && <div><span>Oppervlak</span><b>{item.opp_m2} m²</b></div>}
                    {view === 'beleggingen' && item.huursom_jaar > 0 && (
                      <div><span>Huursom/jr</span><b>{eur(item.huursom_jaar)}</b></div>
                    )}
                    {view === 'beleggingen' && item.bar_pct > 0 && (
                      <div><span>BAR</span><b>{item.bar_pct}%</b></div>
                    )}
                    {(view !== 'beleggingen') && item.type_woning && <div><span>Type</span><b>{item.type_woning}</b></div>}
                  </div>
                  {item.calc?.classificatie && (
                    <div style={{padding: '0 16px 8px'}}>
                      <span className={`signal-badge ${item.calc.classificatie.category === 'transformatie' ? 'transformatie' : item.calc.classificatie.is_verhuurd ? 'verhuurd' : ''}`}>
                        {item.calc.classificatie.category === 'transformatie' ? '🏢 Transformatie' :
                         item.calc.classificatie.is_verhuurd ? '⚠ Verhuurd' : '🏠 Wonen'}
                      </span>
                    </div>
                  )}
                  {view === 'beleggingen' && item.is_verhuurd && (
                    <div style={{padding: '0 16px 8px'}}>
                      <span className="signal-badge verhuurd">⚠ Verhuurd — huurder zit erin</span>
                    </div>
                  )}
                  {item.calc?.veiling_datum && (
                    <div style={{padding: '0 16px 8px', fontSize: 12, color: '#ff6b00'}}>
                      Veiling: {item.calc.veiling_datum}
                    </div>
                  )}
                  {item.calc?.is_veiling && item.calc?.onderhands_bod_mogelijk === 'ja' && (
                    <div style={{padding: '0 16px 8px'}}>
                      <span className="badge extra">Onderhands bod mogelijk</span>
                    </div>
                  )}
                  {view === 'beleggingen' && item.makelaar && (
                    <div style={{padding: '0 16px 8px', fontSize: 11, color: '#888'}}>
                      {item.makelaar}
                    </div>
                  )}
                  <div style={{padding: '8px 16px 16px'}}>
                    <a href={item.url} target="_blank" rel="noopener noreferrer">Bekijk →</a>
                  </div>
                </div>
              ))}
              {(view === 'veilingen' ? veilingen : view === 'kavels' ? kavels : beleggingen).length === 0 && (
                <div className="empty-state">Geen {view} gevonden in Zuid-Holland</div>
              )}
            </div>
          </div>
        )}

        {showNotes && current && (
          <div className="modal-overlay" onClick={() => setShowNotes(false)}>
            <div className="modal" onClick={e => e.stopPropagation()}>
              <h3>Notitie voor {current.adres}</h3>
              <textarea
                value={notesText}
                onChange={e => setNotesText(e.target.value)}
                placeholder="Jouw aantekeningen..."
                autoFocus
              />
              <div className="modal-actions">
                <button className="btn-secondary" onClick={() => setShowNotes(false)}>Annuleren</button>
                <button className="btn-primary" onClick={saveNotes}>Opslaan</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// ── Motion / EP-Online / Wijk-check secties ───────────────────────────────
function MotionSection({ motion }) {
  if (!motion || !motion.dagen_online) return null;
  const m = motion;
  return (
    <div className={`card-calc motion-card ${m.motivated ? 'motion-hot' : ''}`}>
      <h3>{m.motivated ? '🔥 Motivated seller' : 'Motion signalen'}</h3>
      <div className="calc-grid">
        <div><span>Dagen online</span><b>{m.dagen_online}</b></div>
        {m.prijsverlaging_pct > 0 && (
          <div>
            <span>Prijs verlaagd</span>
            <b style={{color: m.prijsverlaging_pct >= 5 ? '#ff6b00' : '#fff'}}>
              -{m.prijsverlaging_pct}% ({eur(m.prijsverlaging_euro)})
            </b>
          </div>
        )}
        {m.aantal_prijsverlagingen >= 2 && (
          <div><span>Aantal verlagingen</span><b>{m.aantal_prijsverlagingen}</b></div>
        )}
        {m.eerste_prijs > 0 && m.eerste_prijs !== m.huidige_prijs && (
          <div><span>Startprijs / nu</span><b>{eur(m.eerste_prijs)} → {eur(m.huidige_prijs)}</b></div>
        )}
        {m.makelaarswissel && (
          <div><span>Makelaarswissel</span><b style={{color: '#ff6b00'}}>{m.makelaars_recent?.slice(0,2).join(' → ') || 'Ja'}</b></div>
        )}
        {m.onder_bod_terug && (
          <div><span>Onder bod → terug</span><b style={{color: '#ff6b00'}}>Ja</b></div>
        )}
        <div className="total">
          <span>Motivated score</span>
          <b style={{color: m.motivated_score >= 5 ? '#ff6b00' : '#aaa'}}>{m.motivated_score}/10</b>
        </div>
      </div>
    </div>
  );
}

function EpOnlineSection({ ep }) {
  if (!ep || !ep.label) return null;
  const sterk = ep.forced_renovation_sterk;
  const forced = ep.forced_renovation;
  return (
    <div className={`card-calc ep-card ${sterk ? 'ep-sterk' : forced ? 'ep-forced' : ''}`}>
      <h3>⚡ EP-Online (RVO)</h3>
      <div className="calc-grid">
        <div><span>Label</span><b style={{color: forced ? '#ff6b00' : '#fff'}}>{ep.label}{sterk ? ' (sterk)' : ''}</b></div>
        {ep.bouwjaar && <div><span>Bouwjaar (EP)</span><b>{ep.bouwjaar}</b></div>}
        {ep.gebruiksoppervlakte && <div><span>GBO (EP)</span><b>{ep.gebruiksoppervlakte} m²</b></div>}
        {ep.geldig_tot && <div><span>Geldig tot</span><b>{String(ep.geldig_tot).slice(0, 10)}</b></div>}
        {ep.pand_type && <div><span>Type (EP)</span><b>{ep.pand_type}</b></div>}
      </div>
      {forced && (
        <div className="ep-reno-note">
          Verhuurverbod 2028 dreigt bij label E/F/G — eigenaar vaak motivated om te verkopen of moet renoveren.
        </div>
      )}
    </div>
  );
}

function WijkCheckSection({ wijk }) {
  if (!wijk) return null;
  const mag = wijk.mag;
  const color = mag === true ? '#00b894' : mag === false ? '#e74c3c' : '#888';
  return (
    <div className="card-calc wijk-card">
      <h3>🎯 Wijk-check splitsen</h3>
      <div className="calc-grid">
        <div><span>Regime</span><b>{wijk.regime === 'den_haag_2026' ? 'Den Haag (1-4-2026)' : wijk.regime === 'rotterdam_2025' ? 'Rotterdam (1-7-2025)' : wijk.regime}</b></div>
        <div><span>Status</span><b style={{color}}>{mag === true ? 'Toegestaan' : mag === false ? 'NIET toegestaan' : 'Onbekend'}</b></div>
        {wijk.wijkscore != null && (
          <div><span>Leefbaarometer</span><b>{wijk.wijkscore}/9 {wijk.wijkscore >= 7 ? '(goed+)' : '(te laag)'}</b></div>
        )}
        {wijk.parkeerdruk_hoog != null && (
          <div><span>Parkeerdruk ≥90%</span><b style={{color: wijk.parkeerdruk_hoog ? '#ffb74d' : '#00b894'}}>{wijk.parkeerdruk_hoog ? 'Ja (risico)' : 'Nee'}</b></div>
        )}
        {wijk.is_nprz != null && (
          <div><span>NPRZ-kerngebied</span><b>{wijk.is_nprz ? 'Ja (85 m²)' : 'Nee (50 m²)'}</b></div>
        )}
        {wijk.opp_per_unit != null && (
          <div><span>m² per unit</span><b>{wijk.opp_per_unit} m²</b></div>
        )}
      </div>
      {wijk.redenen?.length > 0 && (
        <div className="wijk-redenen">
          {wijk.redenen.map((r, i) => <div key={i}>• {r}</div>)}
        </div>
      )}
    </div>
  );
}

function ListView({ title, items, userState, updateStatus, showRestore }) {
  const [selected, setSelected] = useState(null);
  const [notesText, setNotesText] = useState('');
  const [editNotes, setEditNotes] = useState(null);

  return (
    <div className="list-screen">
      <h2 className="list-title">{title}</h2>
      {items.length === 0 ? (
        <div className="empty-state">Geen panden in deze lijst</div>
      ) : (
        <div className="list-grid">
          {items.map((k, i) => (
            <div key={i} className="list-card" onClick={() => setSelected(k)}>
              {k.foto_url && (
                <div className="list-card-photo">
                  <img src={k.foto_url} alt={k.adres} />
                </div>
              )}
              <div className="list-card-header">
                <div>
                  <div className="list-card-title">{k.adres}</div>
                  <div className="list-card-sub">{k.stad}{k.wijk ? ` · ${k.wijk}` : ''}</div>
                </div>
                <div className="list-card-score">{k.score}/10</div>
              </div>

              <SignalBadges pand={k} compact />

              <div className="list-card-metrics">
                <div><span>Prijs</span><b>{eur(k.prijs)}</b></div>
                <div><span>Winst</span><b className="green">{eur(k.winst_euro)}</b></div>
                <div><span>Marge</span><b>{k.marge_pct}%</b></div>
              </div>

              {userState[k.url]?.notes && (
                <div className="list-card-notes">📝 {userState[k.url].notes}</div>
              )}

              <div className="list-card-actions" onClick={e => e.stopPropagation()}>
                <select
                  value={userState[k.url]?.status || STATUS.SAVED}
                  onChange={e => updateStatus(k.url, e.target.value)}
                  style={{ borderColor: STATUS_COLORS[userState[k.url]?.status || STATUS.SAVED] }}
                >
                  <option value={STATUS.SAVED}>💾 Opgeslagen</option>
                  <option value={STATUS.HOT}>🔥 Top deal</option>
                  <option value={STATUS.VIEWED}>👀 Bezichtigd</option>
                  <option value={STATUS.CONTACTED}>📞 Contact gehad</option>
                  <option value={STATUS.REJECTED}>✕ Afwijzen</option>
                  <option value={STATUS.ARCHIVED}>📦 Archief</option>
                </select>
                {showRestore && (
                  <button className="btn-restore" onClick={() => updateStatus(k.url, STATUS.NEW)}>↺ Terug</button>
                )}
                <button className="btn-notes" onClick={() => {
                  setEditNotes(k.url);
                  setNotesText(userState[k.url]?.notes || '');
                }}>📝</button>
                <a href={k.url} target="_blank" rel="noopener noreferrer" className="btn-link">🔗</a>
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && <DetailModal pand={selected} onClose={() => setSelected(null)} />}

      {editNotes && (
        <div className="modal-overlay" onClick={() => setEditNotes(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>Notitie</h3>
            <textarea value={notesText} onChange={e => setNotesText(e.target.value)} autoFocus />
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setEditNotes(null)}>Annuleren</button>
              <button className="btn-primary" onClick={() => {
                updateStatus(editNotes, userState[editNotes]?.status || STATUS.SAVED, { notes: notesText });
                setEditNotes(null);
              }}>Opslaan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DetailModal({ pand, onClose }) {
  const c = pand.calc || {};
  const motion = pand.motion || c.motion;
  const ep = pand.ep_online || c.ep_online;
  const wijk = c.splitsen?.wijkcheck;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal detail-modal" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>
        {(pand.foto_urls?.length > 0 || pand.foto_url) && (
          <div className="detail-photo-wrap">
            <PhotoCarousel
              photos={pand.foto_urls?.length > 0 ? pand.foto_urls : [pand.foto_url]}
              alt={pand.adres}
              score={pand.score}
            />
          </div>
        )}
        <h2>{pand.adres}</h2>
        <p className="card-location">{pand.stad}{pand.wijk ? ` · ${pand.wijk}` : ''}</p>

        <SignalBadges pand={pand} />

        <a href={pand.url} target="_blank" rel="noopener noreferrer" className="view-link">
          Bekijk op {pand.source} →
        </a>

        <MotionSection motion={motion} />
        <EpOnlineSection ep={ep} />
        <WijkCheckSection wijk={wijk} />

        <div className="detail-section">
          <h3>Aankoop</h3>
          <div className="calc-row"><span>Vraagprijs</span><b>{eur(c.vraagprijs)}</b></div>
          <div className="calc-row"><span>OVB {c.ovb_pct}%</span><b>{eur(c.ovb)}</b></div>
          <div className="calc-row"><span>Notaris + makelaar</span><b>{eur(c.notaris_makelaar_aankoop)}</b></div>
          <div className="calc-row total"><span>Totaal</span><b>{eur(c.aankoop_totaal)}</b></div>
        </div>

        {c.renovatie_detail?.componenten && (
          <div className="detail-section">
            <h3>Verbouwing ({eur(c.renovatie_per_m2)}/m²)</h3>
            {c.renovatie_detail.componenten.map((comp, i) => (
              <div key={i} className="calc-row" title={comp.reden || ''}>
                <span>{comp.naam}</span><b>{eur(comp.kosten)}</b>
              </div>
            ))}
            <div className="calc-row total"><span>Totaal bouw</span><b>{eur(c.bouw_totaal)}</b></div>
          </div>
        )}

        <div className="detail-section">
          <h3>Financiering</h3>
          <div className="calc-row"><span>Looptijd</span><b>{c.looptijd_maanden} mnd</b></div>
          <div className="calc-row"><span>Rente {c.rente_pct}%</span><b>{eur(c.rente)}</b></div>
        </div>

        <div className="detail-section highlight">
          <h3>Totaal investering</h3>
          <div className="calc-row total"><b>{eur(c.totaal_kosten)}</b></div>
        </div>

        <div className="detail-section">
          <h3>Verkoop na renovatie</h3>
          <div className="calc-row"><span>Prijs/m² (ref)</span><b>{eur(c.verkoop_m2)}</b></div>
          <div className="calc-row"><span>Bruto</span><b>{eur(c.bruto_verkoopprijs)}</b></div>
          <div className="calc-row"><span>Kosten</span><b>-{eur(c.verkoop_kosten)}</b></div>
          <div className="calc-row total"><span>Netto</span><b>{eur(c.netto_opbrengst)}</b></div>
        </div>

        {c.referenties?.length > 0 && (
          <div className="detail-section">
            <h3>Referentie {c.referenties[0]?.wijk && `(${c.referenties[0].wijk})`}</h3>
            {c.referenties.map((r, i) => (
              <div key={i} className="ref-item">
                <b>{r.adres}</b><br />
                {eur(r.prijs)} · {r.opp_m2}m² · {eur(r.prijs_per_m2)}/m² · label {r.energie_label}
              </div>
            ))}
          </div>
        )}

        <div className="detail-section profit-section">
          <h3>Resultaat</h3>
          <div className="calc-row"><span>Winst</span><b style={{color: '#00b894'}}>{eur(pand.winst_euro)}</b></div>
          <div className="calc-row"><span>Marge</span><b>{pand.marge_pct}%</b></div>
          <div className="calc-row"><span>ROI</span><b>{pand.roi_pct}%</b></div>
        </div>

        {c.bod && (
          <div className="detail-section">
            <h3>Bij bod {eur(c.bod)} (-{c.bod_korting_pct}%)</h3>
            <div className="calc-row"><span>Investering</span><b>{eur(c.bod_totaal_investering)}</b></div>
            <div className="calc-row"><span>Winst</span><b>{eur(c.bod_winst)}</b></div>
            <div className="calc-row"><span>Marge</span><b>{c.bod_marge_pct}%</b></div>
          </div>
        )}

        {c.validatie && (
          <div className={`detail-section ${c.validatie.goedgekeurd ? 'validated-section' : 'invalidated-section'}`}>
            <h3>Prijs validatie</h3>
            <div className="calc-row">
              <span>Status</span>
              <b style={{ color: c.validatie.goedgekeurd ? '#00b894' : '#e74c3c' }}>
                {c.validatie.goedgekeurd ? '✓ Gevalideerd' : '⚠ Gecorrigeerd'}
              </b>
            </div>
            {c.validatie.afwijking_pct !== 0 && (
              <div className="calc-row"><span>Afwijking</span><b>{c.validatie.afwijking_pct}%</b></div>
            )}
            {c.validatie.bronnen && Object.entries(c.validatie.bronnen).map(([k, v]) => (
              <div key={k} className="calc-row"><span>{k}</span><b>{eur(v)}/m²</b></div>
            ))}
            {c.validatie.reden && <div style={{fontSize: 11, color: '#888', marginTop: 8}}>{c.validatie.reden}</div>}
          </div>
        )}

        {c.splitsen && (
          <div className="detail-section">
            <h3>Splitsen</h3>
            <div className="calc-row">
              <span>Mogelijk?</span>
              <b style={{ color: c.splitsen.mag_splitsen ? '#00b894' : c.splitsen.mag_splitsen === false ? '#e74c3c' : '#888' }}>
                {c.splitsen.mag_splitsen ? 'Ja' : c.splitsen.mag_splitsen === false ? 'Nee' : 'Onbekend'}
              </b>
            </div>
            <div style={{fontSize: 12, color: '#aaa', marginTop: 4}}>{c.splitsen.uitleg}</div>
            {c.splitsen.vergunning && <div style={{fontSize: 11, color: '#888', marginTop: 4}}>Vergunning: {c.splitsen.vergunning}</div>}
            {c.splitsen.bijzonderheden && <div style={{fontSize: 11, color: '#666', marginTop: 4}}>{c.splitsen.bijzonderheden}</div>}
          </div>
        )}

        {c.opbouwen && (
          <div className="detail-section">
            <h3>Opbouwen / Dakopbouw</h3>
            <div className="calc-row">
              <span>Mogelijk?</span>
              <b style={{ color: c.opbouwen.mag_opbouwen ? '#00b894' : c.opbouwen.mag_opbouwen === false ? '#e74c3c' : '#888' }}>
                {c.opbouwen.mag_opbouwen ? 'Ja' : c.opbouwen.mag_opbouwen === false ? 'Nee' : 'Onbekend'}
              </b>
            </div>
            <div style={{fontSize: 12, color: '#aaa', marginTop: 4}}>{c.opbouwen.uitleg}</div>
          </div>
        )}

        {c.plattegrond_urls?.length > 0 ? (
          <div className="detail-section">
            <h3>Plattegronden</h3>
            <div className="plattegrond-grid">
              {c.plattegrond_urls.map((url, i) => (
                <img key={i} src={url} alt={`Plattegrond ${i + 1}`} className="plattegrond-img" />
              ))}
            </div>
          </div>
        ) : pand.url && (
          <div className="detail-section">
            <h3>Plattegrond</h3>
            <div style={{fontSize: 13, color: '#888'}}>
              Niet beschikbaar via API — <a href={pand.url} target="_blank" rel="noopener noreferrer">bekijk op Funda</a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
