import { useEffect, Component as ReactComponent } from 'react';
import Head from 'next/head';
import '../styles/globals.css';

class ErrorBoundary extends ReactComponent {
  constructor(props) { super(props); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) { console.error('ErrorBoundary', err, info); }
  reset() { this.setState({ err: null }); }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div style={{
        padding: '24px', maxWidth: '600px', margin: '60px auto',
        background: '#1a0a0a', border: '1px solid #7a1e1e',
        borderRadius: '12px', color: '#ccc',
      }}>
        <h2 style={{ color: '#e74c3c', marginBottom: 12 }}>Er ging iets mis</h2>
        <p>Een onderdeel van het dashboard kon niet renderen. De scan-data werkt nog wel — laad de pagina opnieuw.</p>
        <pre style={{
          background: '#0f0f0f', padding: 12, borderRadius: 6, fontSize: 11,
          marginTop: 12, overflow: 'auto', maxHeight: 200, color: '#888',
        }}>{String(this.state.err?.stack || this.state.err || 'Onbekende fout')}</pre>
        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <button onClick={() => location.reload()} style={{
            background: '#ff6b00', color: '#000', border: 'none',
            borderRadius: 8, padding: '10px 16px', fontWeight: 700, cursor: 'pointer',
          }}>Herlaad pagina</button>
          <button onClick={() => this.reset()} style={{
            background: '#1a1a1a', color: '#ccc', border: '1px solid #333',
            borderRadius: 8, padding: '10px 16px', cursor: 'pointer',
          }}>Probeer opnieuw</button>
          <button onClick={() => {
            if (confirm('localStorage wissen? Dit verwijdert al je saved/portfolio/actieplan data.')) {
              localStorage.clear();
              location.reload();
            }
          }} style={{
            background: '#1a1a1a', color: '#e74c3c', border: '1px solid #7a1e1e',
            borderRadius: 8, padding: '10px 16px', cursor: 'pointer',
          }}>Reset localStorage</button>
        </div>
      </div>
    );
  }
}

export default function App({ Component, pageProps }) {
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch((err) => {
        console.warn('SW registration failed', err);
      });
    }
  }, []);

  return (
    <>
      <Head>
        <link rel="manifest" href="/manifest.json" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png" />
        <meta name="theme-color" content="#ff6b00" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="Panden" />
        <meta name="mobile-web-app-capable" content="yes" />
      </Head>
      <ErrorBoundary>
        <Component {...pageProps} />
      </ErrorBoundary>
    </>
  );
}
