import { useState, useEffect } from 'react';
import Head from 'next/head';

const DATA_URL = "https://raw.githubusercontent.com/clawtje94/panden-scanner/data/leads.json";

const eur = (n) => n ? `€${Math.round(n).toLocaleString('nl-NL')}` : '-';

export default function Home() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('kansen');
  const [stad, setStad] = useState('alle');
  const [minMarge, setMinMarge] = useState(0);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    fetch(DATA_URL)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { console.error(e); setLoading(false); });
  }, []);

  if (loading) return <div className="container"><p>Laden...</p></div>;
  if (!data) return <div className="container"><p>Geen data beschikbaar. Scan moet eerst draaien.</p></div>;

  const kansen = data.kansen || [];
  const biedboek = data.biedboek || [];

  const steden = ['alle', ...new Set(kansen.map(k => k.stad))].slice(0, 10);

  const gefilterdeKansen = kansen
    .filter(k => stad === 'alle' || k.stad === stad)
    .filter(k => k.marge_pct >= minMarge)
    .filter(k => !search || k.adres.toLowerCase().includes(search.toLowerCase()) || k.stad.toLowerCase().includes(search.toLowerCase()));

  const gefilterdeBiedboek = biedboek
    .filter(b => !search || (b.adres || '').toLowerCase().includes(search.toLowerCase()) || (b.stad || '').toLowerCase().includes(search.toLowerCase()));

  const topScore = kansen.filter(k => k.score >= 6).length;
  const gemMarge = kansen.length ? (kansen.reduce((s, k) => s + k.marge_pct, 0) / kansen.length).toFixed(1) : 0;
  const scanDatum = new Date(data.scan_datum).toLocaleString('nl-NL');

  return (
    <>
      <Head>
        <title>Panden Scanner — Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <div className="container">
        <header>
          <h1>Panden <span>Scanner</span></h1>
          <p className="subtitle">Fix & flip kansen Zuid-Holland · Laatst gescand: {scanDatum}</p>
          <div className="stats">
            <div className="stat">
              <div className="stat-label">Kansen</div>
              <div className="stat-value">{kansen.length}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Score 6+</div>
              <div className="stat-value">{topScore}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Gem. marge</div>
              <div className="stat-value">{gemMarge}%</div>
            </div>
            <div className="stat">
              <div className="stat-label">Biedboek</div>
              <div className="stat-value">{biedboek.length}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Gescand</div>
              <div className="stat-value">{data.totaal_gescand}</div>
            </div>
          </div>
        </header>

        <div className="tabs">
          <div className={`tab ${tab === 'kansen' ? 'active' : ''}`} onClick={() => setTab('kansen')}>
            Kansen ({kansen.length})
          </div>
          <div className={`tab ${tab === 'biedboek' ? 'active' : ''}`} onClick={() => setTab('biedboek')}>
            Biedboek ({biedboek.length})
          </div>
        </div>

        {tab === 'kansen' && (
          <>
            <div className="filters">
              <input
                className="search"
                placeholder="Zoek adres of stad..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              {steden.map(s => (
                <button
                  key={s}
                  className={`filter-btn ${stad === s ? 'active' : ''}`}
                  onClick={() => setStad(s)}
                >
                  {s}
                </button>
              ))}
              <button className={`filter-btn ${minMarge === 0 ? 'active' : ''}`} onClick={() => setMinMarge(0)}>Alle marges</button>
              <button className={`filter-btn ${minMarge === 10 ? 'active' : ''}`} onClick={() => setMinMarge(10)}>≥10%</button>
              <button className={`filter-btn ${minMarge === 15 ? 'active' : ''}`} onClick={() => setMinMarge(15)}>≥15%</button>
              <button className={`filter-btn ${minMarge === 20 ? 'active' : ''}`} onClick={() => setMinMarge(20)}>≥20%</button>
            </div>

            {gefilterdeKansen.length === 0 ? (
              <div className="empty">Geen kansen met deze filters</div>
            ) : (
              <div className="grid">
                {gefilterdeKansen.map((k, i) => (
                  <div key={i} className={`card ${k.score >= 6 ? 'high-score' : ''}`} onClick={() => setSelected(k)}>
                    <div className="card-header">
                      <div>
                        <div className="card-title">{k.adres}</div>
                        <div className="card-location">
                          {k.stad}{k.wijk ? ` · ${k.wijk}` : ''}
                        </div>
                      </div>
                      <div className="card-score">{k.score}/10</div>
                    </div>

                    <div className="card-details">
                      <div className="detail">Vraagprijs<b>{eur(k.prijs)}</b></div>
                      <div className="detail">Oppervlak<b>{k.opp_m2} m²</b></div>
                      <div className="detail">Per m²<b>{eur(k.prijs_per_m2)}</b></div>
                    </div>

                    <div className="metrics">
                      <div className="metric">
                        <div className="metric-label">Winst</div>
                        <div className="metric-value">{eur(k.winst_euro)}</div>
                      </div>
                      <div className="metric">
                        <div className="metric-label">Marge</div>
                        <div className="metric-value">{k.marge_pct}%</div>
                      </div>
                      <div className="metric">
                        <div className="metric-label">ROI</div>
                        <div className="metric-value">{k.roi_pct}%</div>
                      </div>
                    </div>

                    <div className="badges">
                      {k.energie_label && <span className="badge label">{k.energie_label}</span>}
                      {k.bouwjaar > 0 && <span className="badge">bj {k.bouwjaar}</span>}
                      {k.kamers > 0 && <span className="badge">{k.kamers} kamers</span>}
                      {k.type_woning && <span className="badge">{k.type_woning}</span>}
                      {k.is_opknapper && <span className="badge opknapper">OPKNAPPER</span>}
                      <span className="badge">{k.source}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {tab === 'biedboek' && (
          <>
            <div className="filters">
              <input
                className="search"
                placeholder="Zoek adres of stad..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>

            {gefilterdeBiedboek.length === 0 ? (
              <div className="empty">Geen biedboek panden</div>
            ) : (
              <div className="grid">
                {gefilterdeBiedboek.map((b, i) => (
                  <div key={i} className="card">
                    <div className="card-title">{b.adres || 'Onbekend adres'}</div>
                    <div className="card-location">{b.stad} {b.postcode && `· ${b.postcode}`}</div>

                    <div className="card-details">
                      {b.prijs > 0 && <div className="detail">Prijs<b>{eur(b.prijs)}</b></div>}
                      {b.opp_m2 > 0 && <div className="detail">Oppervlak<b>{b.opp_m2} m²</b></div>}
                      {b.prijs_per_m2 > 0 && <div className="detail">Per m²<b>{eur(b.prijs_per_m2)}</b></div>}
                    </div>

                    <div className="badges">
                      {b.type_woning && <span className="badge">{b.type_woning}</span>}
                      {b.is_commercieel && <span className="badge">commercieel</span>}
                      {b.bouwjaar > 0 && <span className="badge">bj {b.bouwjaar}</span>}
                    </div>

                    <div style={{ marginTop: 12 }}>
                      <a href={b.url} target="_blank" rel="noopener noreferrer">Bekijk op Biedboek →</a>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {selected && (
          <div className="detail-modal" onClick={() => setSelected(null)}>
            <div className="detail-content" onClick={e => e.stopPropagation()}>
              <button className="detail-close" onClick={() => setSelected(null)}>×</button>
              <h2>{selected.adres}</h2>
              <p className="card-location">{selected.stad}{selected.wijk ? ` · ${selected.wijk}` : ''}</p>

              <div style={{ marginTop: 16 }}>
                <a href={selected.url} target="_blank" rel="noopener noreferrer">Bekijk op {selected.source} →</a>
              </div>

              <div className="calc-section">
                <h3>Aankoop</h3>
                {selected.calc?.vraagprijs && (
                  <>
                    <div className="calc-row"><span>Vraagprijs</span><b>{eur(selected.calc.vraagprijs)}</b></div>
                    <div className="calc-row"><span>OVB {selected.calc.ovb_pct}%</span><b>{eur(selected.calc.ovb)}</b></div>
                    <div className="calc-row"><span>Notaris + makelaar</span><b>{eur(selected.calc.notaris_makelaar_aankoop)}</b></div>
                    <div className="calc-row total"><span>Totaal aankoop</span><b>{eur(selected.calc.aankoop_totaal)}</b></div>
                  </>
                )}
              </div>

              <div className="calc-section">
                <h3>Verbouwing ({eur(selected.calc?.renovatie_per_m2)}/m²)</h3>
                {selected.calc?.renovatie_detail?.componenten?.map((c, i) => (
                  c.kosten >= 1000 && (
                    <div key={i} className="calc-row">
                      <span>{c.naam}</span>
                      <b>{eur(c.kosten)}</b>
                    </div>
                  )
                ))}
                <div className="calc-row total"><span>Totaal bouw</span><b>{eur(selected.calc?.bouw_totaal)}</b></div>
              </div>

              <div className="calc-section">
                <h3>Financiering</h3>
                <div className="calc-row"><span>Looptijd</span><b>{selected.calc?.looptijd_maanden} mnd</b></div>
                <div className="calc-row"><span>Rente {selected.calc?.rente_pct}%</span><b>{eur(selected.calc?.rente)}</b></div>
              </div>

              <div className="calc-section" style={{ background: '#1a0f00', borderLeft: '3px solid #ff6b00' }}>
                <h3>Totaal investering</h3>
                <div className="calc-row total"><span>Totaal</span><b>{eur(selected.calc?.totaal_kosten)}</b></div>
              </div>

              <div className="calc-section">
                <h3>Verkoop na renovatie</h3>
                <div className="calc-row"><span>Prijs/m² (ref)</span><b>{eur(selected.calc?.verkoop_m2)}</b></div>
                <div className="calc-row"><span>Bruto verkoop</span><b>{eur(selected.calc?.bruto_verkoopprijs)}</b></div>
                <div className="calc-row"><span>Kosten (makelaar + notaris)</span><b>-{eur(selected.calc?.verkoop_kosten)}</b></div>
                <div className="calc-row total"><span>Netto opbrengst</span><b>{eur(selected.calc?.netto_opbrengst)}</b></div>
              </div>

              {selected.calc?.referenties?.length > 0 && (
                <div className="calc-section">
                  <h3>Referentie panden {selected.calc.referenties[0]?.wijk && `(${selected.calc.referenties[0].wijk})`}</h3>
                  {selected.calc.referenties.map((r, i) => (
                    <div key={i} className="ref-item">
                      <b>{r.adres}</b><br />
                      {eur(r.prijs)} · {r.opp_m2}m² · {eur(r.prijs_per_m2)}/m² · label {r.energie_label}
                    </div>
                  ))}
                </div>
              )}

              <div className="calc-section" style={{ background: '#001a00', borderLeft: '3px solid #00b894' }}>
                <h3>Resultaat</h3>
                <div className="calc-row"><span>Winst</span><b style={{color: '#00b894'}}>{eur(selected.winst_euro)}</b></div>
                <div className="calc-row"><span>Marge</span><b>{selected.marge_pct}%</b></div>
                <div className="calc-row"><span>ROI</span><b>{selected.roi_pct}%</b></div>
              </div>

              {selected.calc?.bod && (
                <div className="calc-section">
                  <h3>Bij bod {eur(selected.calc.bod)} (-{selected.calc.bod_korting_pct}%)</h3>
                  <div className="calc-row"><span>Investering</span><b>{eur(selected.calc.bod_totaal_investering)}</b></div>
                  <div className="calc-row"><span>Winst</span><b>{eur(selected.calc.bod_winst)}</b></div>
                  <div className="calc-row"><span>Marge</span><b>{selected.calc.bod_marge_pct}%</b></div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
