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

  // Risk-flags indicator (alleen als er echte risks zijn)
  const risks = pand.risks || pand.calc?.risks;
  if (risks?.aantal > 0) {
    const niv = risks.zwaarste;
    const kleur = niv === 'rood' ? 'risk-rood' : niv === 'oranje' ? 'risk-oranje' : 'risk-geel';
    badges.push(<span key="risk" className={`signal-badge ${kleur}`}>⚠ {risks.aantal} risico's</span>);
  }
  // Monument
  if ((pand.monument || pand.calc?.monument)?.is_rijksmonument) {
    badges.push(<span key="mon" className="signal-badge monument">🏛️ Rijksmonument</span>);
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
  { key: 'dealscore', label: 'Dealscore ↓', fn: (a, b) => (b.dealscore?.score || 0) - (a.dealscore?.score || 0) },
  { key: 'marge', label: 'Marge ↓', fn: (a, b) => (b.marge_pct || 0) - (a.marge_pct || 0) },
  { key: 'winst', label: 'Winst ↓', fn: (a, b) => (b.winst_euro || 0) - (a.winst_euro || 0) },
  { key: 'score', label: 'Score ↓', fn: (a, b) => (b.score || 0) - (a.score || 0) },
  { key: 'motivated', label: 'Motivated ↓', fn: (a, b) => ((b.motion?.motivated_score || 0) - (a.motion?.motivated_score || 0)) || ((b.marge_pct || 0) - (a.marge_pct || 0)) },
  { key: 'dagen', label: 'Dagen online ↓', fn: (a, b) => (b.motion?.dagen_online || 0) - (a.motion?.dagen_online || 0) },
  { key: 'prijs_asc', label: 'Prijs ↑', fn: (a, b) => (a.prijs || 0) - (b.prijs || 0) },
];

const GRADE_COLOR = {
  'A+': '#00b894', 'A': '#00a885', 'B': '#fdcb6e',
  'C': '#ff9b44', 'D': '#e74c3c',
};

function DealscorePill({ dealscore, compact = false }) {
  if (!dealscore || !dealscore.score && dealscore.score !== 0) return null;
  const color = GRADE_COLOR[dealscore.grade] || '#888';
  return (
    <div className={`dealscore-pill ${compact ? 'compact' : ''}`} style={{ borderColor: color, color }}>
      <span className="ds-grade" style={{ background: color }}>{dealscore.grade}</span>
      <span className="ds-num">{dealscore.score}</span>
      {!compact && <span className="ds-label">Deal</span>}
    </div>
  );
}

function RisksSection({ risks }) {
  if (!risks) return null;
  const flags = risks.flags || [];
  const kansen = risks.kansen || [];
  if (flags.length === 0 && kansen.length === 0) return null;

  const iconFor = (niveau) => ({ rood: '🚫', oranje: '⚠️', geel: '⚡' }[niveau] || '•');
  return (
    <div className="card-calc risks-card">
      <h3>Risico-profiel</h3>
      {flags.map((f, i) => (
        <div key={i} className={`risk-row risk-${f.niveau}`}>
          <span className="risk-icon">{iconFor(f.niveau)}</span>
          <div className="risk-body">
            <div className="risk-label">{f.label}</div>
            {f.details && <div className="risk-details">{f.details}</div>}
          </div>
        </div>
      ))}
      {kansen.length > 0 && <h4 className="kansen-h4">Kansen</h4>}
      {kansen.map((k, i) => (
        <div key={i} className="risk-row kans-row">
          <span className="risk-icon">✓</span>
          <div className="risk-body">
            <div className="risk-label">{k.label}</div>
            {k.details && <div className="risk-details">{k.details}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

function DealscoreBreakdown({ dealscore }) {
  if (!dealscore || !dealscore.breakdown) return null;
  return (
    <div className="card-calc ds-breakdown-card">
      <h3>Dealscore breakdown · {dealscore.score}/100 · grade {dealscore.grade}</h3>
      {dealscore.breakdown.map((b, i) => (
        <div key={i} className="ds-row">
          <span>{b.onderdeel}</span>
          <b style={{ color: b.punten < 0 ? '#e74c3c' : '#00b894' }}>
            {b.punten > 0 ? '+' : ''}{b.punten}
          </b>
          <span className="ds-uitleg">{b.uitleg}</span>
        </div>
      ))}
    </div>
  );
}

function BagSection({ bag, funda_bouwjaar, funda_opp }) {
  if (!bag || !bag.oppervlakte) return null;
  return (
    <div className="card-calc bag-card">
      <h3>🏛️ BAG (Kadaster)</h3>
      <div className="calc-grid">
        <div><span>Gebruiksdoel</span><b>{bag.gebruiksdoel || '—'}</b></div>
        {bag.bouwjaar && <div><span>Bouwjaar</span><b>{bag.bouwjaar}{funda_bouwjaar && funda_bouwjaar !== bag.bouwjaar ? ` (Funda: ${funda_bouwjaar})` : ''}</b></div>}
        {bag.oppervlakte && <div><span>Oppervlakte</span><b>{bag.oppervlakte} m²{funda_opp && Math.abs(funda_opp - bag.oppervlakte) / bag.oppervlakte > 0.1 ? ` (Funda: ${funda_opp})` : ''}</b></div>}
        {bag.pandstatus && <div><span>Pandstatus</span><b>{bag.pandstatus}</b></div>}
        {bag.status && <div><span>VO status</span><b>{bag.status}</b></div>}
        {bag.wijk && <div><span>Wijk</span><b>{bag.wijk}</b></div>}
        {bag.buurt && <div><span>Buurt</span><b>{bag.buurt}</b></div>}
      </div>
    </div>
  );
}

function MonumentSection({ monument }) {
  if (!monument || !monument.is_rijksmonument) return null;
  return (
    <div className="card-calc monument-card">
      <h3>🏛️ Rijksmonument</h3>
      <div className="calc-grid">
        <div><span>Nummer</span><b>{monument.rijksmonument_nr}</b></div>
        {monument.hoofdcategorie && <div><span>Categorie</span><b>{monument.hoofdcategorie}</b></div>}
        {monument.subcategorie && <div><span>Subcategorie</span><b>{monument.subcategorie}</b></div>}
      </div>
      {monument.url && (
        <a href={monument.url} target="_blank" rel="noopener noreferrer" className="view-link" style={{ marginTop: 8 }}>
          Monumentenregister →
        </a>
      )}
      <div className="monument-note">
        Verbouwing 30-50% duurder + welstandseisen + vergunningstraject. Check ook beschermd stadsgezicht.
      </div>
    </div>
  );
}

function genereerChecklist(pand) {
  const checks = [];
  const bj = pand.bouwjaar || pand.bag?.bouwjaar || 0;
  const label = (pand.ep_online?.label || pand.energie_label || '').toUpperCase().slice(0, 1);
  const tw = (pand.type_woning || '').toLowerCase();
  const monument = pand.monument?.is_rijksmonument;

  if (bj && bj < 1940) {
    checks.push({ cat: 'Constructie', punt: 'Houten vloeren — houtworm, schimmel, veerkracht', urg: 'hoog' });
    checks.push({ cat: 'Constructie', punt: 'Fundering staal/houten palen — verzakking', urg: 'hoog' });
    checks.push({ cat: 'Water', punt: 'Loden waterleidingen (vervang verplicht)', urg: 'hoog' });
    checks.push({ cat: 'Asbest', punt: 'Asbest in dakbeschot/leidingisolatie', urg: 'hoog' });
  } else if (bj && bj < 1975) {
    checks.push({ cat: 'Asbest', punt: 'Asbest in plaatmateriaal (gevel/dak)', urg: 'hoog' });
    checks.push({ cat: 'Constructie', punt: 'Beton-rot in galerijen/balkons', urg: 'hoog' });
    checks.push({ cat: 'Isolatie', punt: 'Vrijwel zeker ongeïsoleerd', urg: 'middel' });
  } else if (bj && bj < 1992) {
    checks.push({ cat: 'Isolatie', punt: 'Spouw meestal aanwezig, dak variabel', urg: 'middel' });
    checks.push({ cat: 'CV', punt: 'CV-ketel 20+ jaar — vervanging plannen', urg: 'middel' });
  }
  if (label === 'E' || label === 'F' || label === 'G') {
    checks.push({ cat: 'Verhuurverbod', punt: `Label ${label} — B verplicht voor verhuur 2028`, urg: 'hoog' });
  } else if (label === 'C' || label === 'D') {
    checks.push({ cat: 'Energie', punt: `Label ${label} — naar A/B te tillen`, urg: 'middel' });
  }
  if (tw.includes('appartement') || tw.includes('portiek') || tw.includes('galerij')) {
    checks.push({ cat: 'VvE', punt: 'MJOP opvragen + reserves check', urg: 'hoog' });
    checks.push({ cat: 'VvE', punt: 'Geluidsisolatie NEN 5077', urg: 'middel' });
  }
  if (monument) {
    checks.push({ cat: 'Monument', punt: 'Verbouwing alleen na omgevings + erfgoed-akkoord', urg: 'hoog' });
  }
  checks.push({ cat: 'Algemeen', punt: 'Bouwkundige keuring erkend keurder', urg: 'hoog' });
  checks.push({ cat: 'Algemeen', punt: 'Bestemmingsplan-wijziging omgeving check', urg: 'middel' });
  return checks;
}

function BouwkundigSection({ pand }) {
  const checks = genereerChecklist(pand);
  if (checks.length === 0) return null;
  const color = { hoog: '#e74c3c', middel: '#fdcb6e', laag: '#888' };
  return (
    <div className="card-calc bouw-card">
      <h3>🔧 Bouwkundige checklist</h3>
      {checks.map((c, i) => (
        <div key={i} className="bouw-check">
          <span className="bouw-urg" style={{ background: color[c.urg] }} />
          <span className="bouw-cat">{c.cat}</span>
          <span className="bouw-punt">{c.punt}</span>
        </div>
      ))}
    </div>
  );
}

function MapsSection({ pand }) {
  if (!pand?.adres) return null;
  const q = encodeURIComponent(`${pand.adres}, ${pand.stad} ${pand.postcode || ''}`.trim());
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${q}`;
  const sviewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${q}`;
  const bagId = pand.calc?.bag?.bag_id;
  return (
    <div className="card-calc maps-card">
      <h3>🗺️ Locatie</h3>
      <div className="maps-links">
        <a href={mapsUrl} target="_blank" rel="noopener noreferrer">📍 Google Maps</a>
        <a href={sviewUrl} target="_blank" rel="noopener noreferrer">🚶 Street View</a>
        <a href={`https://bagviewer.kadaster.nl/lvbag/bag-viewer/?searchQuery=${q}`} target="_blank" rel="noopener noreferrer">🏛️ BAG-viewer</a>
        <a href={`https://www.wozwaardeloket.nl/#!/zoek/?wq=${q}`} target="_blank" rel="noopener noreferrer">💰 WOZ-loket</a>
      </div>
    </div>
  );
}

const ACTIEPLAN_STAPPEN = [
  { key: 'bezichtiging', label: 'Bezichtiging ingepland' },
  { key: 'bezichtigd', label: 'Bezichtigd' },
  { key: 'keuring', label: 'Bouwkundige keuring' },
  { key: 'bod', label: 'Bod uitgebracht' },
  { key: 'geaccepteerd', label: 'Bod geaccepteerd' },
  { key: 'financiering', label: 'Financiering rond' },
  { key: 'notaris', label: 'Notaris + transport' },
  { key: 'sleutel', label: 'Sleutel overhandigd' },
];

function ActieplanSection({ pandUrl }) {
  const [plan, setPlan] = useState({});
  const storageKey = `actieplan:${pandUrl}`;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) setPlan(JSON.parse(raw));
    } catch {}
  }, [storageKey]);

  const toggle = (key) => {
    const next = { ...plan, [key]: plan[key] ? null : new Date().toISOString() };
    setPlan(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  };

  const done = Object.values(plan).filter(Boolean).length;
  return (
    <div className="card-calc actie-card">
      <h3>✅ Actieplan ({done}/{ACTIEPLAN_STAPPEN.length})</h3>
      <div className="actie-list">
        {ACTIEPLAN_STAPPEN.map(s => (
          <label key={s.key} className={`actie-item ${plan[s.key] ? 'done' : ''}`}>
            <input
              type="checkbox"
              checked={!!plan[s.key]}
              onChange={() => toggle(s.key)}
            />
            <span className="actie-label">{s.label}</span>
            {plan[s.key] && (
              <span className="actie-date">{new Date(plan[s.key]).toLocaleDateString('nl-NL')}</span>
            )}
          </label>
        ))}
      </div>
    </div>
  );
}

function BodAdviesSection({ advies }) {
  if (!advies) return null;
  return (
    <div className="card-calc bod-card">
      <h3>🎯 Bod-advies</h3>
      <div className="bod-grid">
        <div className="bod-niveau aggressief">
          <div className="bod-label">Agressief</div>
          <div className="bod-price">{eur(advies.aggressief?.bod)}</div>
          <div className="bod-korting">-{advies.aggressief?.korting_pct}%</div>
        </div>
        <div className="bod-niveau markt">
          <div className="bod-label">Markt</div>
          <div className="bod-price">{eur(advies.markt?.bod)}</div>
          <div className="bod-korting">-{advies.markt?.korting_pct}%</div>
        </div>
        <div className="bod-niveau plafond">
          <div className="bod-label">Plafond</div>
          <div className="bod-price">{eur(advies.plafond?.bod)}</div>
          <div className="bod-korting">10% worst-marge</div>
        </div>
      </div>
      <div className="bod-strategie">{advies.strategie}</div>
      {advies.argumenten?.length > 0 && (
        <div className="bod-argumenten">
          <div className="bod-arg-header">Onderhandelings-argumenten</div>
          {advies.argumenten.map((a, i) => (
            <div key={i} className="bod-arg">• {a}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function VerkoopSection({ scenarios, verkoop_referentie, calc }) {
  const s = scenarios || calc?.scenarios;
  const vr = verkoop_referentie || calc?.verkoop_referentie;
  if (!s && !vr) return null;

  const confColor = {
    hoog: '#00b894', middel: '#fdcb6e',
    laag: '#ff9b44', onvoldoende: '#e74c3c',
  }[vr?.confidence_label] || '#888';

  return (
    <div className="card-calc verkoop-card">
      <h3>💰 Verkoop-scenario's</h3>

      {s && (
        <div className="scen-grid">
          <div className="scen worst">
            <div className="scen-label">Worst (P25)</div>
            <div className="scen-price">{eur(s.worst?.verkoop_m2)}/m²</div>
            <div className="scen-marge" style={{ color: (s.worst?.marge_pct || 0) < 8 ? '#e74c3c' : '#ffb074' }}>
              Marge {s.worst?.marge_pct}%
            </div>
            <div className="scen-winst">{eur(s.worst?.winst)}</div>
          </div>
          <div className="scen real">
            <div className="scen-label">Realistisch (P50)</div>
            <div className="scen-price">{eur(s.realistic?.verkoop_m2)}/m²</div>
            <div className="scen-marge">Marge {s.realistic?.marge_pct}%</div>
            <div className="scen-winst">{eur(s.realistic?.winst)}</div>
          </div>
          <div className="scen best">
            <div className="scen-label">Best (P75)</div>
            <div className="scen-price">{eur(s.best?.verkoop_m2)}/m²</div>
            <div className="scen-marge" style={{ color: '#00b894' }}>Marge {s.best?.marge_pct}%</div>
            <div className="scen-winst">{eur(s.best?.winst)}</div>
          </div>
        </div>
      )}

      {vr && (
        <div className="ref-breakdown">
          <div className="conf-pill" style={{ borderColor: confColor, color: confColor }}>
            Confidence: <b>{vr.confidence_label} ({vr.confidence}/100)</b>
          </div>
          <div className="ref-meta">
            <div><span>N referenties</span><b>{vr.n_refs}</b></div>
            <div><span>Met label A/B/C</span><b>{vr.n_high_label}</b></div>
            <div><span>Spread (P75-P25)</span><b>{vr.spread_pct}%</b></div>
            {vr.avg_days_online != null && (
              <div><span>Gem. dagen online</span><b>{vr.avg_days_online}</b></div>
            )}
            <div><span>Match-niveau</span><b>{vr.match_niveau}</b></div>
            {vr.wijk && <div><span>Wijk</span><b>{vr.wijk}</b></div>}
          </div>
          {vr.waarschuwingen?.length > 0 && (
            <div className="ref-warnings">
              {vr.waarschuwingen.map((w, i) => <div key={i}>⚠ {w}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ErfpachtSection({ erfpacht }) {
  if (!erfpacht || (!erfpacht.is_erfpacht && !erfpacht.toelichting)) return null;
  const risk = erfpacht.risk_level || 'geen';
  return (
    <div className={`card-calc erfpacht-card erfpacht-${risk}`}>
      <h3>Erfpacht</h3>
      <div className="calc-grid">
        <div><span>Status</span><b>{erfpacht.is_eeuwigdurend ? 'Eeuwigdurend' : erfpacht.is_afgekocht ? 'Afgekocht' : erfpacht.is_erfpacht ? 'Tijdelijk / actief' : 'Eigen grond'}</b></div>
        {erfpacht.eindjaar && <div><span>Eindjaar</span><b>{erfpacht.eindjaar} ({erfpacht.jaren_resterend}j te gaan)</b></div>}
        {erfpacht.canon_euro && <div><span>Canon</span><b>€{erfpacht.canon_euro.toLocaleString('nl-NL')}/jr</b></div>}
        <div><span>Risico</span><b style={{ color: risk === 'hoog' ? '#e74c3c' : risk === 'middel' ? '#ff9b44' : '#00b894' }}>{risk}</b></div>
      </div>
      {erfpacht.toelichting && <div className="erfpacht-note">{erfpacht.toelichting}</div>}
    </div>
  );
}

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
  const [sortKey, setSortKey] = useState('dealscore');
  const [search, setSearch] = useState('');
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

  const addToPortfolio = (kans) => {
    try {
      const raw = localStorage.getItem('bateau_portfolio');
      const items = raw ? JSON.parse(raw) : [];
      const verbouw = kans.calc?.bouw_totaal || 0;
      const exit = kans.calc?.netto_opbrengst || kans.calc?.bruto_verkoopprijs || 0;
      const item = {
        _id: 'p_' + Date.now(),
        _created: new Date().toISOString(),
        _from_url: kans.url,
        adres: kans.adres,
        stad: kans.stad,
        postcode: kans.postcode,
        status: 'prospect',
        koopprijs: kans.prijs,
        verbouwkosten: verbouw,
        verwachte_exit: exit,
        url: kans.url,
        notities: `Van scanner · ${kans.strategie} · marge ${kans.marge_pct}% · dealscore ${kans.dealscore?.score || '?'}/100 ${kans.dealscore?.grade || ''}`.trim(),
      };
      localStorage.setItem('bateau_portfolio', JSON.stringify([item, ...items]));
      updateStatus(kans.url, STATUS.SAVED);
      alert(`"${kans.adres}" toegevoegd aan portfolio als prospect.`);
    } catch (e) {
      console.error(e);
      alert('Kon niet opslaan in portfolio.');
    }
  };

  const getStatus = (url) => userState[url]?.status || STATUS.NEW;

  const kansen = useMemo(() => (data?.kansen || []).map(k => ({
    ...k,
    _status: getStatus(k.url),
    _notes: userState[k.url]?.notes || '',
  })), [data, userState]);

  const swipeList = useMemo(() => {
    const sortFn = (SORT_OPTIONS.find(s => s.key === sortKey) || SORT_OPTIONS[0]).fn;
    const q = search.trim().toLowerCase();
    return kansen
      .filter(k => k._status === STATUS.NEW)
      .filter(k => stadFilter === 'alle' || k.stad === stadFilter)
      .filter(k => k.marge_pct >= minMarge)
      .filter(k => !motivatedOnly || (k.motion?.motivated))
      .filter(k => !forcedOnly || (k.ep_online?.forced_renovation))
      .filter(k => !splitsDhOnly || (k.calc?.splitsen?.wijkcheck?.regime === 'den_haag_2026' && k.calc?.splitsen?.wijkcheck?.mag === true))
      .filter(k => !q || (
        (k.adres || '').toLowerCase().includes(q) ||
        (k.stad || '').toLowerCase().includes(q) ||
        (k.postcode || '').toLowerCase().includes(q) ||
        (k.calc?.bag?.wijk || '').toLowerCase().includes(q) ||
        (k.calc?.bag?.buurt || '').toLowerCase().includes(q)
      ))
      .sort(sortFn);
  }, [kansen, stadFilter, minMarge, motivatedOnly, forcedOnly, splitsDhOnly, sortKey, search]);

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
  const verdwenen = data.verdwenen || [];
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
            <button className={`nav-tab ${view === 'portfolio' ? 'active' : ''}`} onClick={() => setView('portfolio')}>
              🏘️ Portfolio
            </button>
            <button className={`nav-tab ${view === 'stats' ? 'active' : ''}`} onClick={() => setView('stats')}>
              📊 Stats
            </button>
            <button className={`nav-tab ${view === 'compare' ? 'active' : ''}`} onClick={() => setView('compare')}>
              ⚖️ Compare
            </button>
            <button className={`nav-tab ${view === 'recent' ? 'active' : ''}`} onClick={() => setView('recent')}>
              🕑 Recent
            </button>
            {verdwenen.length > 0 && (
              <button className={`nav-tab ${view === 'verdwenen' ? 'active' : ''}`} onClick={() => setView('verdwenen')}>
                👻 Verdwenen<span className="count">{verdwenen.length}</span>
              </button>
            )}
          </div>
        </nav>

        {view === 'swipe' && (
          <div className="swipe-screen">
            <input
              type="search"
              className="search-box"
              placeholder="Zoek op adres, stad, postcode, wijk..."
              value={search}
              onChange={e => { setSearch(e.target.value); setCurrentIdx(0); }}
            />
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
                    {current.dealscore && <DealscorePill dealscore={current.dealscore} />}
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

                  <RisksSection risks={current.risks || current.calc?.risks} />
                  <BodAdviesSection advies={current.bod_advies || current.calc?.bod_advies} />
                  <VerkoopSection
                    scenarios={current.scenarios || current.calc?.scenarios}
                    verkoop_referentie={current.verkoop_referentie || current.calc?.verkoop_referentie}
                  />
                  <MotionSection motion={current.motion || current.calc?.motion} />
                  <EpOnlineSection ep={current.ep_online || current.calc?.ep_online} />
                  <BagSection bag={current.bag || current.calc?.bag} funda_bouwjaar={current.bouwjaar} funda_opp={current.opp_m2} />
                  <MonumentSection monument={current.monument || current.calc?.monument} />
                  <ErfpachtSection erfpacht={current.erfpacht_detail || current.calc?.erfpacht_detail} />
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
                  <button className="action portfolio" onClick={() => addToPortfolio(current)} title="Naar portfolio">🏘️</button>
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

        {view === 'portfolio' && <PortfolioView />}
        {view === 'stats' && <StatsView kansen={kansen} />}
        {view === 'compare' && <CompareView kansen={[...kansen, ...savedList, ...hotList]} />}
        {view === 'verdwenen' && (
          <div className="list-screen">
            <h2 className="list-title">👻 Verdwenen ({verdwenen.length})</h2>
            <p className="subtle">Panden die sinds minimaal 3 dagen niet meer in een scan voorkomen. Vaak verkocht of ingetrokken.</p>
            <div className="list-grid">
              {verdwenen.map((v, i) => (
                <div key={i} className="list-card">
                  <div className="list-card-header">
                    <div>
                      <div className="list-card-title">{v.adres}</div>
                      <div className="list-card-sub">{v.stad} — laatste scan: {v.laatste_gezien?.slice(0, 10)}</div>
                    </div>
                    <div className="port-status" style={{ background: '#666' }}>verdwenen</div>
                  </div>
                  <div className="list-card-metrics">
                    <div><span>Laatste prijs</span><b>{eur(v.laatste_prijs)}</b></div>
                  </div>
                  {v.url && (
                    <div style={{ padding: '8px 16px 16px' }}>
                      <a href={v.url} target="_blank" rel="noopener noreferrer">Check URL (404?) →</a>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        {view === 'recent' && <RecentView allKansen={kansen} onOpen={(u) => {
          const k = kansen.find(x => x.url === u);
          if (k) setView('swipe'); // of open detail
        }} />}

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
                <button
                  className="btn-secondary"
                  onClick={() => {
                    const sug = suggereerNotitie(current);
                    if (sug) setNotesText(t => t ? `${t}\n\n${sug}` : sug);
                  }}
                  title="Auto-gegenereerde samenvatting toevoegen"
                >💡 Suggereer</button>
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
function PriceHistoryChart({ history }) {
  if (!history || history.length < 2) return null;
  const prices = history.map(h => h.prijs);
  const max = Math.max(...prices), min = Math.min(...prices);
  const range = max - min || 1;
  const points = history.map((h, i) => {
    const x = (i / (history.length - 1)) * 100;
    const y = 100 - ((h.prijs - min) / range) * 85 - 7;
    return `${x},${y}`;
  }).join(' ');
  return (
    <div className="price-chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        <polyline points={points} fill="none" stroke="#ff6b00" strokeWidth="1" />
        {history.map((h, i) => {
          const x = (i / (history.length - 1)) * 100;
          const y = 100 - ((h.prijs - min) / range) * 85 - 7;
          return <circle key={i} cx={x} cy={y} r="1.2" fill="#ff6b00" />;
        })}
      </svg>
      <div className="price-chart-labels">
        <span>€{Math.round(history[0].prijs / 1000)}k</span>
        <span>€{Math.round(history[history.length - 1].prijs / 1000)}k</span>
      </div>
    </div>
  );
}

function MotionSection({ motion }) {
  if (!motion || !motion.dagen_online) return null;
  const m = motion;
  return (
    <div className={`card-calc motion-card ${m.motivated ? 'motion-hot' : ''}`}>
      <h3>{m.motivated ? '🔥 Motivated seller' : 'Motion signalen'}</h3>
      {m.prijs_historie && m.prijs_historie.length >= 2 && (
        <PriceHistoryChart history={m.prijs_historie} />
      )}
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
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    const h = (e) => {
      if (editNotes || selected) return;
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setCursor(c => Math.min(items.length - 1, c + 1));
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setCursor(c => Math.max(0, c - 1));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (items[cursor]) setSelected(items[cursor]);
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [items, cursor, editNotes, selected]);

  return (
    <div className="list-screen">
      <h2 className="list-title">{title}</h2>
      {items.length === 0 ? (
        <div className="empty-state">Geen panden in deze lijst</div>
      ) : (
        <div className="list-grid">
          {items.map((k, i) => (
            <div key={i} className={`list-card ${i === cursor ? 'cursor-active' : ''}`} onClick={() => setSelected(k)}>
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

// ── Recent viewed ─────────────────────────────────────────────────────────
function RecentView({ allKansen, onOpen }) {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  useEffect(() => {
    try {
      const raw = localStorage.getItem('recent_viewed');
      if (raw) setItems(JSON.parse(raw));
    } catch {}
  }, []);
  const clear = () => {
    localStorage.removeItem('recent_viewed');
    setItems([]);
  };
  if (items.length === 0) {
    return (
      <div className="list-screen">
        <h2 className="list-title">🕑 Recent bekeken</h2>
        <div className="empty-state">
          <p>Nog geen panden bekeken.</p>
          <p>Klik in een lijst op een kaart — verschijnt hier.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="list-screen">
      <h2 className="list-title">🕑 Recent bekeken ({items.length})</h2>
      <button className="btn-secondary" onClick={clear} style={{ marginBottom: 12 }}>Leegmaken</button>
      <div className="list-grid">
        {items.map((r, i) => {
          const full = allKansen.find(k => k.url === r.url) || r;
          return (
            <div key={i} className="list-card" onClick={() => setSelected(full)}>
              {r.foto_url && (
                <div className="list-card-photo">
                  <img src={r.foto_url} alt={r.adres} />
                </div>
              )}
              <div className="list-card-header">
                <div>
                  <div className="list-card-title">{r.adres}</div>
                  <div className="list-card-sub">{r.stad} · {new Date(r.viewed_at).toLocaleString('nl-NL')}</div>
                </div>
                {r.dealscore && <DealscorePill dealscore={r.dealscore} compact />}
              </div>
              <div className="list-card-metrics">
                <div><span>Prijs</span><b>{eur(r.prijs)}</b></div>
                <div><span>Marge</span><b>{r.marge_pct}%</b></div>
              </div>
            </div>
          );
        })}
      </div>
      {selected && <DetailModal pand={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

// ── Compare tab (2 panden naast elkaar) ──────────────────────────────────
function CompareView({ kansen }) {
  const [picks, setPicks] = useState([null, null]);
  const unique = Array.from(new Map(kansen.map(k => [k.url, k])).values());

  const pickFor = (idx, url) => {
    const next = [...picks];
    next[idx] = unique.find(k => k.url === url) || null;
    setPicks(next);
  };

  const row = (label, v1, v2, fmt = (x) => x) => {
    const a = picks[0] ? fmt(v1) : '—';
    const b = picks[1] ? fmt(v2) : '—';
    const better = (() => {
      if (!picks[0] || !picks[1]) return null;
      if (typeof v1 === 'number' && typeof v2 === 'number') {
        if (v1 > v2) return 0;
        if (v2 > v1) return 1;
      }
      return null;
    })();
    return (
      <div className="cmp-row">
        <div className="cmp-label">{label}</div>
        <div className={`cmp-cell ${better === 0 ? 'cmp-better' : ''}`}>{a}</div>
        <div className={`cmp-cell ${better === 1 ? 'cmp-better' : ''}`}>{b}</div>
      </div>
    );
  };

  const negRow = (label, v1, v2, fmt = (x) => x) => {
    // Voor velden waar lager beter is (bv prijs, risico-aantal)
    const a = picks[0] ? fmt(v1) : '—';
    const b = picks[1] ? fmt(v2) : '—';
    const better = (() => {
      if (!picks[0] || !picks[1]) return null;
      if (typeof v1 === 'number' && typeof v2 === 'number') {
        if (v1 < v2) return 0;
        if (v2 < v1) return 1;
      }
      return null;
    })();
    return (
      <div className="cmp-row">
        <div className="cmp-label">{label}</div>
        <div className={`cmp-cell ${better === 0 ? 'cmp-better' : ''}`}>{a}</div>
        <div className={`cmp-cell ${better === 1 ? 'cmp-better' : ''}`}>{b}</div>
      </div>
    );
  };

  return (
    <div className="list-screen">
      <h2 className="list-title">⚖️ Compare</h2>
      <p className="subtle">Twee kansen naast elkaar vergelijken. Groen = beter van de twee.</p>

      <div className="cmp-picker">
        {[0, 1].map(i => (
          <select key={i} value={picks[i]?.url || ''} onChange={e => pickFor(i, e.target.value)}>
            <option value="">Kies pand {i + 1}...</option>
            {unique.map(k => (
              <option key={k.url} value={k.url}>
                {k.adres} — {k.stad} — {eur(k.prijs)}
              </option>
            ))}
          </select>
        ))}
      </div>

      <div className="cmp-table">
        <div className="cmp-row cmp-header">
          <div className="cmp-label"></div>
          <div className="cmp-cell">{picks[0]?.adres || 'Pand 1'}</div>
          <div className="cmp-cell">{picks[1]?.adres || 'Pand 2'}</div>
        </div>
        {row('Dealscore', picks[0]?.dealscore?.score, picks[1]?.dealscore?.score,
             v => v != null ? `${v}/100 (${picks[0]?.dealscore?.grade || picks[1]?.dealscore?.grade || '?'})` : '—')}
        {row('Marge %', picks[0]?.marge_pct, picks[1]?.marge_pct, v => `${v}%`)}
        {row('Winst', picks[0]?.winst_euro, picks[1]?.winst_euro, eur)}
        {negRow('Vraagprijs', picks[0]?.prijs, picks[1]?.prijs, eur)}
        {row('Oppervlak', picks[0]?.opp_m2, picks[1]?.opp_m2, v => `${v} m²`)}
        {negRow('Prijs/m²', picks[0]?.prijs_per_m2, picks[1]?.prijs_per_m2, eur)}
        {row('Worst-case marge', picks[0]?.scenarios?.worst?.marge_pct, picks[1]?.scenarios?.worst?.marge_pct, v => v != null ? `${v}%` : '—')}
        {row('Best-case marge', picks[0]?.scenarios?.best?.marge_pct, picks[1]?.scenarios?.best?.marge_pct, v => v != null ? `${v}%` : '—')}
        {row('Confidence', picks[0]?.verkoop_referentie?.confidence, picks[1]?.verkoop_referentie?.confidence, v => v != null ? `${v}/100` : '—')}
        {row('# Refs', picks[0]?.verkoop_referentie?.n_refs, picks[1]?.verkoop_referentie?.n_refs)}
        {negRow('# Risk flags', picks[0]?.risks?.aantal, picks[1]?.risks?.aantal)}
        {row('Motion dagen online', picks[0]?.motion?.dagen_online, picks[1]?.motion?.dagen_online)}
        {row('Bouwjaar (BAG)', picks[0]?.bag?.bouwjaar, picks[1]?.bag?.bouwjaar)}
        {row('Label (EP)', picks[0]?.ep_online?.label || picks[0]?.energie_label, picks[1]?.ep_online?.label || picks[1]?.energie_label)}
        {row('Rijksmonument', picks[0]?.monument?.is_rijksmonument ? 'Ja' : 'Nee', picks[1]?.monument?.is_rijksmonument ? 'Ja' : 'Nee')}
        {row('Erfpacht', picks[0]?.erfpacht_detail?.is_erfpacht ? 'Ja' : 'Nee', picks[1]?.erfpacht_detail?.is_erfpacht ? 'Ja' : 'Nee')}
      </div>

      {picks[0] && picks[1] && (
        <div className="cmp-links">
          <a href={picks[0].url} target="_blank" rel="noopener noreferrer">Bekijk pand 1 →</a>
          <a href={picks[1].url} target="_blank" rel="noopener noreferrer">Bekijk pand 2 →</a>
        </div>
      )}
    </div>
  );
}

// ── Stats tab + CSV export ────────────────────────────────────────────────
function StatsView({ kansen }) {
  const gradeCount = { 'A+': 0, 'A': 0, 'B': 0, 'C': 0, 'D': 0, '?': 0 };
  const stadCount = {};
  const strategieCount = {};
  let motivated = 0, forcedReno = 0, dhSplits = 0, rdamNprz = 0, monument = 0, erfpacht = 0;
  let margeSum = 0, scoreSum = 0, winstSum = 0;

  kansen.forEach(k => {
    const g = k.dealscore?.grade || '?';
    gradeCount[g] = (gradeCount[g] || 0) + 1;
    stadCount[k.stad] = (stadCount[k.stad] || 0) + 1;
    strategieCount[k.strategie] = (strategieCount[k.strategie] || 0) + 1;
    if (k.motion?.motivated) motivated++;
    if (k.ep_online?.forced_renovation) forcedReno++;
    const wijk = k.calc?.splitsen?.wijkcheck;
    if (wijk?.regime === 'den_haag_2026' && wijk?.mag) dhSplits++;
    if (wijk?.is_nprz) rdamNprz++;
    if (k.monument?.is_rijksmonument) monument++;
    if (k.erfpacht_detail?.is_erfpacht) erfpacht++;
    margeSum += k.marge_pct || 0;
    scoreSum += k.dealscore?.score || 0;
    winstSum += k.winst_euro || 0;
  });

  const n = kansen.length || 1;
  const gemMarge = Math.round((margeSum / n) * 10) / 10;
  const gemScore = Math.round(scoreSum / n);

  const topStad = Object.entries(stadCount).sort((a, b) => b[1] - a[1]);
  const topStratArr = Object.entries(strategieCount).sort((a, b) => b[1] - a[1]);

  const maxStad = topStad[0]?.[1] || 1;
  const maxGrade = Math.max(...Object.values(gradeCount), 1);

  const downloadCsv = () => {
    const headers = [
      'adres', 'stad', 'postcode', 'wijk', 'source', 'prijs', 'prijs_per_m2',
      'opp_m2', 'type_woning', 'bouwjaar', 'energie_label', 'kamers',
      'strategie', 'marge_pct', 'winst_euro', 'roi_pct',
      'dealscore', 'grade', 'score_basis',
      'motivated', 'motivated_score', 'dagen_online', 'prijsverlaging_pct',
      'forced_renovation', 'ep_label', 'is_rijksmonument',
      'is_erfpacht', 'erfpacht_risk', 'rotterdam_afkoopkans',
      'bag_gebruiksdoel', 'bag_bouwjaar', 'bag_oppervlakte',
      'url',
    ];
    const esc = (v) => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? '"' + s.replace(/"/g, '""') + '"'
        : s;
    };
    const rows = kansen.map(k => ([
      k.adres, k.stad, k.postcode, k.wijk || '', k.source,
      k.prijs, k.prijs_per_m2, k.opp_m2, k.type_woning,
      k.bouwjaar, k.energie_label, k.kamers,
      k.strategie, k.marge_pct, k.winst_euro, k.roi_pct,
      k.dealscore?.score ?? '', k.dealscore?.grade ?? '', k.score,
      k.motion?.motivated ? 'ja' : 'nee',
      k.motion?.motivated_score ?? '',
      k.motion?.dagen_online ?? '',
      k.motion?.prijsverlaging_pct ?? '',
      k.ep_online?.forced_renovation ? 'ja' : 'nee',
      k.ep_online?.label ?? '',
      k.monument?.is_rijksmonument ? 'ja' : 'nee',
      k.erfpacht_detail?.is_erfpacht ? 'ja' : 'nee',
      k.erfpacht_detail?.risk_level ?? '',
      k.erfpacht_detail?.rotterdam_afkoopkans ? 'ja' : 'nee',
      k.bag?.gebruiksdoel ?? '',
      k.bag?.bouwjaar ?? '',
      k.bag?.oppervlakte ?? '',
      k.url,
    ].map(esc).join(',')));
    const csv = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `panden-scanner-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="list-screen">
      <h2 className="list-title">📊 Stats</h2>
      <p className="subtle">Overzicht van de huidige scan. Dubbelklik CSV voor ruwe export.</p>

      <div className="stats-topline">
        <div><span>Kansen</span><b>{kansen.length}</b></div>
        <div><span>Gem. dealscore</span><b>{gemScore}/100</b></div>
        <div><span>Gem. marge</span><b>{gemMarge}%</b></div>
        <div className="green"><span>Tot. verwachte winst</span><b>{eur(winstSum)}</b></div>
      </div>

      <div className="stats-row">
        <div className="stats-card">
          <h3>Grade verdeling</h3>
          {['A+', 'A', 'B', 'C', 'D'].map(g => (
            <div key={g} className="bar-row">
              <span className="bar-label" style={{ color: GRADE_COLOR[g] }}>{g}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{
                  width: `${(gradeCount[g] || 0) / maxGrade * 100}%`,
                  background: GRADE_COLOR[g],
                }} />
              </div>
              <span className="bar-n">{gradeCount[g] || 0}</span>
            </div>
          ))}
        </div>

        <div className="stats-card">
          <h3>Signalen</h3>
          <div className="sig-list">
            <div><span>🔥 Motivated</span><b>{motivated}</b></div>
            <div><span>⚡ Forced-reno (E/F/G)</span><b>{forcedReno}</b></div>
            <div><span>🎯 DH splits-wijk</span><b>{dhSplits}</b></div>
            <div><span>RDAM NPRZ-zone</span><b>{rdamNprz}</b></div>
            <div><span>🏛️ Rijksmonument</span><b>{monument}</b></div>
            <div><span>Erfpacht</span><b>{erfpacht}</b></div>
          </div>
        </div>
      </div>

      <div className="stats-card">
        <h3>Per stad (top 10)</h3>
        {topStad.slice(0, 10).map(([stad, n]) => (
          <div key={stad} className="bar-row">
            <span className="bar-label">{stad}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${n / maxStad * 100}%`, background: '#ff6b00' }} />
            </div>
            <span className="bar-n">{n}</span>
          </div>
        ))}
      </div>

      <StadDealscoreHeatmap kansen={kansen} />

      <MakelaarIntel kansen={kansen} />

      <div className="stats-card">
        <h3>Per strategie</h3>
        {topStratArr.map(([s, n]) => (
          <div key={s} className="bar-row">
            <span className="bar-label">{s}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${n / (topStratArr[0]?.[1] || 1) * 100}%`, background: '#4fc3f7' }} />
            </div>
            <span className="bar-n">{n}</span>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 20, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button className="btn-primary" onClick={downloadCsv}>📥 CSV alle kansen ({kansen.length})</button>
        <button className="btn-secondary" onClick={() => {
          try {
            const raw = localStorage.getItem('panden_state');
            const state = raw ? JSON.parse(raw) : {};
            const saved = Object.entries(state)
              .filter(([_, s]) => ['saved', 'hot', 'viewed', 'contacted'].includes(s?.status))
              .map(([url, s]) => {
                const k = kansen.find(x => x.url === url);
                if (!k) return null;
                return { ...k, _status: s.status, _notes: s.notes || '', _updated: s.updated };
              })
              .filter(Boolean);
            if (saved.length === 0) { alert('Geen opgeslagen panden'); return; }
            const h = ['status','adres','stad','prijs','marge','winst','dealscore','grade','notes','updated','url'];
            const rows = saved.map(k => [
              k._status, k.adres, k.stad, k.prijs, k.marge_pct, k.winst_euro,
              k.dealscore?.score ?? '', k.dealscore?.grade ?? '',
              k._notes, k._updated?.slice(0, 10) || '', k.url,
            ].map(v => {
              const s = String(v ?? '');
              return s.includes(',') || s.includes('"') || s.includes('\n') ? '"' + s.replace(/"/g, '""') + '"' : s;
            }).join(','));
            const csv = [h.join(','), ...rows].join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `bateau-saved-${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(a); a.click(); document.body.removeChild(a);
            URL.revokeObjectURL(url);
          } catch (e) { console.error(e); alert('Export mislukt'); }
        }}>💾 CSV saved/hot/contacted</button>
        <button className="btn-secondary" onClick={() => {
          try {
            const raw = localStorage.getItem('bateau_portfolio');
            const items = raw ? JSON.parse(raw) : [];
            if (items.length === 0) { alert('Geen portfolio items'); return; }
            const h = ['status','adres','stad','postcode','koopprijs','koopdatum','verbouwkosten','verwachte_exit','winst','makelaar','aannemer','notaris','financier','notities'];
            const rows = items.map(p => {
              const koop = Number(p.koopprijs) || 0;
              const vb = Number(p.verbouwkosten) || 0;
              const exit = Number(p.verwachte_exit) || 0;
              return [p.status, p.adres, p.stad, p.postcode, koop, p.koopdatum || '', vb, exit, exit - koop - vb,
                      p.makelaar || '', p.aannemer || '', p.notaris || '', p.financier || '', p.notities || ''];
            }).map(r => r.map(v => {
              const s = String(v ?? '');
              return s.includes(',') || s.includes('"') || s.includes('\n') ? '"' + s.replace(/"/g, '""') + '"' : s;
            }).join(','));
            const csv = [h.join(','), ...rows].join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `bateau-portfolio-${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(a); a.click(); document.body.removeChild(a);
            URL.revokeObjectURL(url);
          } catch (e) { console.error(e); alert('Export mislukt'); }
        }}>🏘️ CSV portfolio</button>
      </div>
    </div>
  );
}

function StadDealscoreHeatmap({ kansen }) {
  // Gem dealscore per stad + aantal
  const byStad = new Map();
  kansen.forEach(k => {
    const s = k.stad;
    if (!s) return;
    if (!byStad.has(s)) byStad.set(s, { n: 0, scoreSum: 0, margeSum: 0, winstSum: 0 });
    const e = byStad.get(s);
    e.n += 1;
    e.scoreSum += k.dealscore?.score || 0;
    e.margeSum += k.marge_pct || 0;
    e.winstSum += k.winst_euro || 0;
  });
  const rows = Array.from(byStad.entries()).map(([stad, e]) => ({
    stad,
    n: e.n,
    gemScore: Math.round(e.scoreSum / e.n),
    gemMarge: Math.round((e.margeSum / e.n) * 10) / 10,
    totWinst: e.winstSum,
  })).sort((a, b) => b.gemScore - a.gemScore);

  if (rows.length === 0) return null;
  const maxScore = Math.max(...rows.map(r => r.gemScore), 1);

  const colorFor = (score) => {
    if (score >= 70) return '#00b894';
    if (score >= 55) return '#7cb342';
    if (score >= 40) return '#fdcb6e';
    if (score >= 25) return '#ff9b44';
    return '#e74c3c';
  };

  return (
    <div className="stats-card">
      <h3>Dealscore-heatmap per stad</h3>
      {rows.map(r => (
        <div key={r.stad} className="heat-row">
          <span className="heat-stad">{r.stad}</span>
          <div className="heat-track">
            <div className="heat-fill" style={{
              width: `${r.gemScore / maxScore * 100}%`,
              background: colorFor(r.gemScore),
            }}>
              <span className="heat-score">{r.gemScore}</span>
            </div>
          </div>
          <span className="heat-n">{r.n} deals · {r.gemMarge}% · {eur(r.totWinst)}</span>
        </div>
      ))}
    </div>
  );
}

function MakelaarIntel({ kansen }) {
  // Aggregeer per makelaar: # listings, gem dealscore, # motivated, gem dagen online
  const byMak = new Map();
  kansen.forEach(k => {
    const m = k.calc?.beschrijving_parsed?.makelaar || k.calc?.motion?.makelaars_recent?.[0]
      || k.calc?.makelaar || (k.source?.startsWith('mkl_') ? k.source.replace('mkl_', '').replace(/_/g, ' ') : null);
    if (!m) return;
    if (!byMak.has(m)) byMak.set(m, { n: 0, dealscoreSum: 0, motivated: 0, dagenSum: 0, dagenN: 0, verlaagdN: 0 });
    const e = byMak.get(m);
    e.n += 1;
    e.dealscoreSum += k.dealscore?.score || 0;
    if (k.motion?.motivated) e.motivated += 1;
    if (k.motion?.dagen_online) { e.dagenSum += k.motion.dagen_online; e.dagenN += 1; }
    if (k.motion?.prijsverlaging_pct > 0) e.verlaagdN += 1;
  });
  const rows = Array.from(byMak.entries())
    .filter(([_, e]) => e.n >= 1)
    .map(([m, e]) => ({
      mak: m,
      n: e.n,
      gemScore: Math.round(e.dealscoreSum / e.n),
      motivated: e.motivated,
      gemDagen: e.dagenN > 0 ? Math.round(e.dagenSum / e.dagenN) : null,
      verlaagdPct: e.n > 0 ? Math.round(e.verlaagdN / e.n * 100) : 0,
    }))
    .sort((a, b) => b.motivated - a.motivated || b.n - a.n)
    .slice(0, 10);

  if (rows.length === 0) return null;

  return (
    <div className="stats-card">
      <h3>Makelaar-intelligence (top 10)</h3>
      <div className="mkl-row mkl-header">
        <div>Makelaar</div>
        <div>N</div>
        <div>Score</div>
        <div>Motiv.</div>
        <div>Dagen</div>
        <div>% verl.</div>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="mkl-row">
          <div className="mkl-name">{r.mak}</div>
          <div>{r.n}</div>
          <div>{r.gemScore}</div>
          <div>{r.motivated}</div>
          <div>{r.gemDagen ?? '-'}</div>
          <div>{r.verlaagdPct}%</div>
        </div>
      ))}
    </div>
  );
}

// ── Portfolio tab (eigen Bateau panden) ──────────────────────────────────
const PORTFOLIO_STATUSES = [
  { key: 'prospect', label: 'Prospect', color: '#888' },
  { key: 'onderhandeling', label: 'Onderhandeling', color: '#fdcb6e' },
  { key: 'aangekocht', label: 'Aangekocht', color: '#00b894' },
  { key: 'verbouwing', label: 'Verbouwing', color: '#ff6b00' },
  { key: 'in_verkoop', label: 'In verkoop', color: '#0984e3' },
  { key: 'verhuurd', label: 'Verhuurd', color: '#6c5ce7' },
  { key: 'verkocht', label: 'Verkocht', color: '#2d3436' },
];
const EMPTY_ITEM = {
  adres: '', stad: '', postcode: '', status: 'prospect',
  koopprijs: '', koopdatum: '', verwachte_exit: '', exit_datum: '',
  verbouwkosten: '', verbouw_start: '', verbouw_eind: '',
  makelaar: '', aannemer: '', notaris: '', financier: '',
  notities: '', url: '',
};

function PortfolioView() {
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);  // object or null
  const [filterStatus, setFilterStatus] = useState('alle');

  useEffect(() => {
    try {
      const raw = localStorage.getItem('bateau_portfolio');
      if (raw) setItems(JSON.parse(raw));
    } catch {}
  }, []);

  const save = (next) => {
    setItems(next);
    localStorage.setItem('bateau_portfolio', JSON.stringify(next));
  };

  const upsert = (item) => {
    if (item._id) {
      save(items.map(x => x._id === item._id ? item : x));
    } else {
      item._id = 'p_' + Date.now();
      item._created = new Date().toISOString();
      save([...items, item]);
    }
    setEditing(null);
  };
  const remove = (id) => {
    if (!confirm('Pand verwijderen uit portfolio?')) return;
    save(items.filter(x => x._id !== id));
  };

  const filtered = filterStatus === 'alle' ? items : items.filter(x => x.status === filterStatus);

  // Aggregaten
  const totaalKoop = items.reduce((s, x) => s + (Number(x.koopprijs) || 0), 0);
  const totaalVerbouw = items.reduce((s, x) => s + (Number(x.verbouwkosten) || 0), 0);
  const totaalExit = items.reduce((s, x) => s + (Number(x.verwachte_exit) || 0), 0);
  const verwachteWinst = totaalExit - totaalKoop - totaalVerbouw;

  return (
    <div className="list-screen">
      <h2 className="list-title">🏘️ Bateau Portfolio</h2>
      <p className="subtle">Eigen panden + projecten. Data lokaal in je browser (localStorage).</p>

      <div className="portfolio-aggregate">
        <div><span>Panden</span><b>{items.length}</b></div>
        <div><span>Investering</span><b>{eur(totaalKoop + totaalVerbouw)}</b></div>
        <div><span>Exit (verwacht)</span><b>{eur(totaalExit)}</b></div>
        <div className={verwachteWinst > 0 ? 'green' : 'red'}><span>Verwachte winst</span><b>{eur(verwachteWinst)}</b></div>
      </div>

      <div className="portfolio-actions">
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="alle">Alle statussen</option>
          {PORTFOLIO_STATUSES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <button className="btn-primary" onClick={() => setEditing({ ...EMPTY_ITEM })}>+ Pand toevoegen</button>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">
          <p>Nog geen panden in portfolio.</p>
          <p>Voeg er één toe om ROI, status en contactpersonen te tracken.</p>
        </div>
      ) : (
        <div className="list-grid">
          {filtered.map(p => {
            const status = PORTFOLIO_STATUSES.find(s => s.key === p.status) || PORTFOLIO_STATUSES[0];
            const kost = (Number(p.koopprijs) || 0) + (Number(p.verbouwkosten) || 0);
            const winst = (Number(p.verwachte_exit) || 0) - kost;
            return (
              <div key={p._id} className="list-card" onClick={() => setEditing(p)}>
                <div className="list-card-header">
                  <div>
                    <div className="list-card-title">{p.adres || '(geen adres)'}</div>
                    <div className="list-card-sub">{p.stad}{p.postcode ? ` · ${p.postcode}` : ''}</div>
                  </div>
                  <div className="port-status" style={{ background: status.color }}>{status.label}</div>
                </div>
                <div className="list-card-metrics">
                  <div><span>Koop</span><b>{eur(p.koopprijs)}</b></div>
                  <div><span>Verbouw</span><b>{eur(p.verbouwkosten)}</b></div>
                  <div><span>Exit</span><b>{eur(p.verwachte_exit)}</b></div>
                </div>
                {winst !== 0 && (
                  <div className="port-winst" style={{ color: winst > 0 ? '#00b894' : '#e74c3c' }}>
                    Winst: {eur(winst)}
                  </div>
                )}
                {p.notities && <div className="list-card-notes">📝 {p.notities}</div>}
              </div>
            );
          })}
        </div>
      )}

      {editing && (
        <div className="modal-overlay" onClick={() => setEditing(null)}>
          <div className="modal detail-modal" onClick={e => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setEditing(null)}>×</button>
            <h3>{editing._id ? 'Pand bewerken' : 'Nieuw pand'}</h3>
            <PortfolioForm item={editing} onSave={upsert} onDelete={editing._id ? () => { remove(editing._id); setEditing(null); } : null} />
          </div>
        </div>
      )}
    </div>
  );
}

function PortfolioForm({ item, onSave, onDelete }) {
  const [form, setForm] = useState({ ...item });
  const set = (k, v) => setForm({ ...form, [k]: v });
  return (
    <div className="portfolio-form">
      <div className="pf-row">
        <label>Adres<input value={form.adres || ''} onChange={e => set('adres', e.target.value)} /></label>
      </div>
      <div className="pf-row">
        <label>Stad<input value={form.stad || ''} onChange={e => set('stad', e.target.value)} /></label>
        <label>Postcode<input value={form.postcode || ''} onChange={e => set('postcode', e.target.value)} /></label>
      </div>
      <div className="pf-row">
        <label>Status
          <select value={form.status} onChange={e => set('status', e.target.value)}>
            {PORTFOLIO_STATUSES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
        <label>URL<input value={form.url || ''} onChange={e => set('url', e.target.value)} placeholder="Funda link / dossier" /></label>
      </div>
      <div className="pf-row">
        <label>Koopprijs €<input type="number" value={form.koopprijs || ''} onChange={e => set('koopprijs', e.target.value)} /></label>
        <label>Koopdatum<input type="date" value={form.koopdatum || ''} onChange={e => set('koopdatum', e.target.value)} /></label>
      </div>
      <div className="pf-row">
        <label>Verbouwkosten €<input type="number" value={form.verbouwkosten || ''} onChange={e => set('verbouwkosten', e.target.value)} /></label>
        <label>Verwachte exit €<input type="number" value={form.verwachte_exit || ''} onChange={e => set('verwachte_exit', e.target.value)} /></label>
      </div>
      <div className="pf-row">
        <label>Verbouw start<input type="date" value={form.verbouw_start || ''} onChange={e => set('verbouw_start', e.target.value)} /></label>
        <label>Verbouw eind<input type="date" value={form.verbouw_eind || ''} onChange={e => set('verbouw_eind', e.target.value)} /></label>
      </div>
      <div className="pf-row">
        <label>Makelaar<input value={form.makelaar || ''} onChange={e => set('makelaar', e.target.value)} /></label>
        <label>Aannemer<input value={form.aannemer || ''} onChange={e => set('aannemer', e.target.value)} /></label>
      </div>
      <div className="pf-row">
        <label>Notaris<input value={form.notaris || ''} onChange={e => set('notaris', e.target.value)} /></label>
        <label>Financier<input value={form.financier || ''} onChange={e => set('financier', e.target.value)} /></label>
      </div>
      <div className="pf-row">
        <label>Notities<textarea value={form.notities || ''} onChange={e => set('notities', e.target.value)} /></label>
      </div>
      <div className="modal-actions">
        {onDelete && <button className="btn-secondary" onClick={onDelete} style={{ color: '#e74c3c' }}>Verwijder</button>}
        <button className="btn-primary" onClick={() => onSave(form)}>Opslaan</button>
      </div>
    </div>
  );
}

function addToRecent(pand) {
  try {
    const raw = localStorage.getItem('recent_viewed');
    const recent = raw ? JSON.parse(raw) : [];
    const filtered = recent.filter(r => r.url !== pand.url);
    const next = [{
      url: pand.url, adres: pand.adres, stad: pand.stad,
      prijs: pand.prijs, marge_pct: pand.marge_pct,
      dealscore: pand.dealscore,
      foto_url: pand.foto_url,
      viewed_at: new Date().toISOString(),
    }, ...filtered].slice(0, 20);
    localStorage.setItem('recent_viewed', JSON.stringify(next));
  } catch {}
}

function suggereerNotitie(pand) {
  const tips = [];
  const c = pand.calc || {};
  const ds = pand.dealscore || c.dealscore;
  if (ds?.grade) tips.push(`Dealscore ${ds.score}/${ds.grade}.`);
  const m = pand.motion || c.motion;
  if (m?.motivated) tips.push(`Motivated seller (score ${m.motivated_score}/10).`);
  if (m?.prijsverlaging_pct > 0) tips.push(`Prijs al ${m.prijsverlaging_pct}% verlaagd.`);
  if (m?.dagen_online >= 120) tips.push(`${m.dagen_online} dagen online.`);
  if (m?.makelaarswissel) tips.push(`Makelaarswissel — vorige strategie faalde.`);
  const ep = pand.ep_online || c.ep_online;
  if (ep?.forced_renovation) tips.push(`Label ${ep.label} — verhuurverbod 2028 leverage.`);
  const mon = pand.monument || c.monument;
  if (mon?.is_rijksmonument) tips.push(`Rijksmonument #${mon.rijksmonument_nr} — reno +30-50%.`);
  const erf = pand.erfpacht_detail || c.erfpacht_detail;
  if (erf?.is_erfpacht && !erf.is_afgekocht) tips.push(`Erfpacht (${erf.risk_level}).`);
  const risks = pand.risks || c.risks;
  risks?.flags?.forEach(f => {
    if (!f.niveau || f.niveau === 'geel') return;
    tips.push(`⚠ ${f.label}.`);
  });
  const vr = pand.verkoop_referentie || c.verkoop_referentie;
  if (vr) tips.push(`Verkoop-confidence ${vr.confidence_label} (N=${vr.n_refs}).`);
  const sc = pand.scenarios || c.scenarios;
  if (sc?.worst?.marge_pct !== undefined) tips.push(`Worst-case marge: ${sc.worst.marge_pct}%.`);
  return tips.join(' ');
}

function DetailModal({ pand, onClose }) {
  useEffect(() => { addToRecent(pand); }, [pand?.url]);
  const c = pand.calc || {};
  const motion = pand.motion || c.motion;
  const ep = pand.ep_online || c.ep_online;
  const wijk = c.splitsen?.wijkcheck;
  const toPortfolio = () => {
    try {
      const raw = localStorage.getItem('bateau_portfolio');
      const items = raw ? JSON.parse(raw) : [];
      const item = {
        _id: 'p_' + Date.now(), _created: new Date().toISOString(),
        _from_url: pand.url, adres: pand.adres, stad: pand.stad, postcode: pand.postcode,
        status: 'prospect', koopprijs: pand.prijs,
        verbouwkosten: c.bouw_totaal || 0,
        verwachte_exit: c.netto_opbrengst || c.bruto_verkoopprijs || 0,
        url: pand.url,
        notities: `Van scanner · ${pand.strategie} · marge ${pand.marge_pct}% · dealscore ${pand.dealscore?.score || '?'}/100 ${pand.dealscore?.grade || ''}`.trim(),
      };
      localStorage.setItem('bateau_portfolio', JSON.stringify([item, ...items]));
      alert(`"${pand.adres}" toegevoegd aan portfolio.`);
    } catch { alert('Kon niet opslaan.'); }
  };
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

        {pand.dealscore && <DealscorePill dealscore={pand.dealscore} />}

        <SignalBadges pand={pand} />

        <div className="detail-actions">
          <a href={pand.url} target="_blank" rel="noopener noreferrer" className="view-link">
            Bekijk op {pand.source} →
          </a>
          <button className="btn-print" onClick={() => window.print()}>🖨️ PDF</button>
          <button className="btn-print" onClick={toPortfolio}>🏘️ Portfolio</button>
        </div>

        <RisksSection risks={pand.risks || c.risks} />
        <ActieplanSection pandUrl={pand.url} />
        <BodAdviesSection advies={pand.bod_advies || c.bod_advies} />
        <BouwkundigSection pand={pand} />
        <MapsSection pand={pand} />
        <VerkoopSection
          scenarios={pand.scenarios || c.scenarios}
          verkoop_referentie={pand.verkoop_referentie || c.verkoop_referentie}
        />
        <DealscoreBreakdown dealscore={pand.dealscore || c.dealscore} />
        <MotionSection motion={motion} />
        <EpOnlineSection ep={ep} />
        <BagSection bag={pand.bag || c.bag} funda_bouwjaar={pand.bouwjaar} funda_opp={pand.opp_m2} />
        <MonumentSection monument={pand.monument || c.monument} />
        <ErfpachtSection erfpacht={pand.erfpacht_detail || c.erfpacht_detail} />
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

        {(pand.foto_urls?.length > 1) && (
          <div className="detail-section">
            <h3>📸 Alle foto's ({pand.foto_urls.length})</h3>
            <div className="foto-grid">
              {pand.foto_urls.map((u, i) => (
                <a key={i} href={u} target="_blank" rel="noopener noreferrer">
                  <img src={u} alt={`Foto ${i + 1}`} loading="lazy" />
                </a>
              ))}
            </div>
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
