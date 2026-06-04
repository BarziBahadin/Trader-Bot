import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AlertTriangle, CheckCircle2, PauseCircle, PlayCircle, RefreshCw, Shield, XCircle } from 'lucide-react';
import TradingChart from './TradingChart.jsx';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1';
const API_TOKEN = import.meta.env.VITE_API_TOKEN || '';

async function api(path, options) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(API_TOKEN ? { 'X-API-Key': API_TOKEN } : {}) },
    ...options,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function App() {
  const [status, setStatus] = useState(null);
  const [settings, setSettings] = useState(null);
  const [symbols, setSymbols] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [signals, setSignals] = useState([]);
  const [trades, setTrades] = useState([]);
  const [riskEvents, setRiskEvents] = useState([]);
  const [candles, setCandles] = useState([]);
  const [preview, setPreview] = useState(null);
  const [closeCode, setCloseCode] = useState('');
  const [error, setError] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const loadingRef = useRef(false);

  const load = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      setError('');
      const [nextStatus, nextSettings, nextSymbols, nextWatchlist, nextSignals, nextTrades, nextRisk] = await Promise.all([
        api('/status'),
        api('/settings'),
        api('/symbols'),
        api('/watchlist'),
        api('/signals'),
        api('/trades'),
        api('/risk-events'),
      ]);
      setStatus(nextStatus);
      setSettings(nextSettings);
      setSymbols(nextSymbols);
      setWatchlist(nextWatchlist);
      setSignals(nextSignals);
      setTrades(nextTrades);
      setRiskEvents(nextRisk);
      const symbol = nextStatus.symbol;
      setCandles(await api(`/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${nextStatus.timeframe}&limit=80`));
      setPreview(await api('/position-size', { method: 'POST', body: JSON.stringify({ symbol }) }));
    } catch (err) {
      setError(err.message);
    } finally {
      loadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') {
        load();
      }
    }, 30000);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  async function activateSymbol(symbol) {
    setCandles([]);
    await api('/symbols/activate', { method: 'POST', body: JSON.stringify({ symbol }) });
    await load();
  }

  async function updateSetting(key, value) {
    const next = { ...settings, [key]: value };
    setSettings(next);
    await api('/settings', { method: 'PATCH', body: JSON.stringify({ [key]: value }) });
    await load();
  }

  async function stop() {
    await api('/emergency-stop', { method: 'POST' });
    await load();
  }

  async function resume() {
    await api('/resume', { method: 'POST' });
    await load();
  }

  async function previewClose() {
    const result = await api('/position/close/preview', { method: 'POST' });
    setCloseCode(result.code);
  }

  async function confirmClose() {
    await api('/position/close/confirm', { method: 'POST', body: JSON.stringify({ code: closeCode }) });
    setCloseCode('');
    await load();
  }

  const selectedSymbol = status?.symbol || settings?.active_symbol || '';
  const instrumentOptions = watchlist.length ? watchlist : symbols;

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>Trader Console</h1>
          <p>{status ? `${status.mode.toUpperCase()} · ${status.provider} · ${status.asset_class}` : 'Loading market state'}</p>
        </div>
        <button className="iconButton" onClick={load} title="Refresh">
          <RefreshCw size={18} />
        </button>
      </header>

      {error && <div className="notice danger"><XCircle size={18} /> {error}</div>}

      <section className="toolbar">
        <label>
          Instrument
          <select value={selectedSymbol} onChange={(event) => activateSymbol(event.target.value)}>
            {instrumentOptions.map((item) => <option key={`${item.provider}:${item.symbol}`} value={item.symbol}>{item.symbol} · {item.asset_class}</option>)}
          </select>
        </label>
        <label>
          Timeframe
          <select value={settings?.timeframe || '15m'} onChange={(event) => updateSetting('timeframe', event.target.value)}>
            {['1s', '1m', '5m', '15m', '30m', '1h', '4h', '1d'].map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <button onClick={status?.emergency_stop ? resume : stop} className={status?.emergency_stop ? 'success' : 'danger'}>
          {status?.emergency_stop ? <PlayCircle size={18} /> : <PauseCircle size={18} />}
          {status?.emergency_stop ? 'Resume' : 'Stop'}
        </button>
        <button onClick={() => setAutoRefresh((value) => !value)} className={autoRefresh ? 'success' : ''}>
          <RefreshCw size={18} />
          Auto {autoRefresh ? 'On' : 'Off'}
        </button>
      </section>

      <section className="grid four">
        <StatusCard title="Provider" value={status?.provider_status?.connected ? 'Connected' : 'Disconnected'} detail={status?.provider_status?.message} icon={status?.provider_status?.connected ? CheckCircle2 : AlertTriangle} />
        <StatusCard title="Equity" value={format(status?.account?.equity)} detail={status?.account?.currency || 'USDT'} />
        <StatusCard title="Free Balance" value={format(status?.account?.free)} detail={`Used ${format(status?.account?.used)}`} />
        <StatusCard title="Unrealized PnL" value={format(status?.account?.unrealized_pnl)} detail={status?.account?.message} />
      </section>

      <section className="grid four">
        <StatusCard title="Latest Price" value={format(status?.latest_price)} detail={selectedSymbol} />
        <StatusCard title="Market Type" value={status?.account?.market_type || '-'} detail={status?.account?.margin_mode ? `${status.account.margin_mode} margin` : ''} />
        <StatusCard title="Open Position" value={status?.open_position ? 'Yes' : 'No'} detail={status?.open_position ? 'Manage below' : 'No active trade'} />
        <StatusCard title="Live Futures" value={status?.live_readiness?.ready ? 'Ready' : 'Blocked'} detail={status?.real_trading_enabled ? 'Real trading flag on' : 'Real trading flag off'} icon={Shield} />
      </section>

      <section className="split">
        <div className="panel chartPanel">
          <div className="panelHeader">
            <h2>{selectedSymbol} Chart</h2>
            <span>{status?.timeframe}</span>
          </div>
          <TradingChart
            key={`${selectedSymbol}:${status?.timeframe}`}
            candles={candles}
            symbol={selectedSymbol}
            timeframe={status?.timeframe}
            onTimeframeChange={(value) => updateSetting('timeframe', value)}
          />
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Position Size</h2>
            <span>{settings?.active_asset_class}</span>
          </div>
          <div className="formGrid">
            <NumberInput label="Risk %" value={settings?.risk_percent} onChange={(value) => updateSetting('risk_percent', value)} />
            <NumberInput label="SL distance" value={settings?.stop_loss_distance} onChange={(value) => updateSetting('stop_loss_distance', value)} />
            <NumberInput label="TP distance" value={settings?.take_profit_distance} onChange={(value) => updateSetting('take_profit_distance', value)} />
            <NumberInput label="Leverage" value={settings?.leverage} onChange={(value) => updateSetting('leverage', value)} />
          </div>
          <div className="metrics">
            <Metric label="Lot" value={preview?.lot_size} />
            <Metric label="Margin" value={format(preview?.margin_required)} />
            <Metric label="Risk" value={format(preview?.risk_amount)} />
            <Metric label="Tick value" value={format(preview?.pip_or_tick_value)} />
          </div>
        </div>
      </section>

      <section className="split">
        <TablePanel title="Watchlist" rows={watchlist} columns={['symbol', 'asset_class', 'provider']} />
        <div className="panel">
          <div className="panelHeader">
            <h2>Close Position</h2>
            <span>Two-step</span>
          </div>
          <button onClick={previewClose} disabled={!status?.open_position}>Preview close</button>
          {closeCode && (
            <div className="confirmBox">
              <p>Confirmation code: <strong>{closeCode}</strong></p>
              <button className="danger" onClick={confirmClose}>Confirm close</button>
            </div>
          )}
        </div>
      </section>

      <section className="grid three">
        <TablePanel title="Signals" rows={signals.slice(0, 8)} columns={['symbol', 'signal', 'reason', 'price', 'rsi']} />
        <TablePanel title="Trades" rows={trades.slice(0, 8)} columns={['symbol', 'status', 'entry_price', 'pnl']} />
        <TablePanel title="Risk Events" rows={riskEvents.slice(0, 8)} columns={['event_type', 'message']} />
      </section>
    </main>
  );
}

function StatusCard({ title, value, detail, icon: Icon = CheckCircle2 }) {
  return <div className="statusCard"><Icon size={20} /><h3>{title}</h3><strong>{value || '-'}</strong><p>{detail || ''}</p></div>;
}

function NumberInput({ label, value, onChange }) {
  return <label>{label}<input type="number" value={value ?? ''} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}

function Metric({ label, value }) {
  return <div><span>{label}</span><strong>{value ?? '-'}</strong></div>;
}

function TablePanel({ title, rows, columns }) {
  return (
    <div className="panel tablePanel">
      <div className="panelHeader"><h2>{title}</h2><span>{rows.length}</span></div>
      <table>
        <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{String(row[column] ?? '')}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

function format(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 5 });
}

createRoot(document.getElementById('root')).render(<App />);
