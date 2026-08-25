import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Spin from '../ui/Spin';
import { fmt$, fmtSigned } from '../../utils/formatting';
import {
  getSnapTradeConfig,
  connectSnapTrade,
  syncSnapTrade,
  syncSnapTradeAccount,
  listSnapTradeConnections,
} from '../../api/snaptrade';
import { getPortfolio, setCostBasis, clearCostBasis } from '../../api/investments';
import RetirementSection from './RetirementSection';
import PortfolioQuality from './PortfolioQuality';

const ASSET_LABEL = {
  stock: 'Stock',
  etf: 'ETF',
  crypto: 'Crypto',
  option: 'Option',
  cash: 'Cash',
  other: 'Other',
};

const ALLOC_COLORS = {
  stock: '#6366f1',
  etf: '#0ea5e9',
  crypto: '#f59e0b',
  option: '#a855f7',
  cash: '#10b981',
  other: '#94a3b8',
};

// Avg-cost cell. Brokerages often report no average purchase price, which is
// exactly where a gain figure would be most useful, so the user can type one.
// A typed value is labelled "yours" so the origin of a gain is never
// ambiguous; it lives in its own table and survives the next sync.
function CostBasisCell({ holding, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const avg = holding.average_purchase_price;
  const mine = holding.cost_basis_source === 'user';
  const known = avg !== null && avg !== undefined;

  const startEdit = () => {
    setDraft(known ? String(avg) : '');
    setFailed(false);
    setEditing(true);
  };

  const run = async (fn) => {
    setBusy(true);
    setFailed(false);
    try {
      await fn();
      setEditing(false);
      await onSaved();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  const save = () => {
    const value = Number(draft);
    if (!Number.isFinite(value) || value <= 0) {
      setFailed(true);
      return;
    }
    run(() => setCostBasis(holding.account_id, holding.symbol, value));
  };

  if (!editing) {
    return (
      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', alignItems: 'center' }}>
        {known ? (
          <>
            <span style={{ fontFamily: "'DM Mono', monospace" }}>{fmt$(avg)}</span>
            {mine && (
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }} title="You entered this cost basis">
                yours
              </span>
            )}
            <button
              type="button"
              className="btn-link"
              onClick={startEdit}
              style={{ fontSize: 11, background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}
            >
              Edit
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={startEdit}
            style={{ fontSize: 11, background: 'none', border: 'none', color: '#0ea5e9', cursor: 'pointer', padding: 0 }}
          >
            Add cost basis
          </button>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end', alignItems: 'center', flexWrap: 'wrap' }}>
      <input
        type="number"
        min="0"
        step="0.01"
        value={draft}
        aria-label={`Average cost per share for ${holding.symbol}`}
        onChange={(e) => setDraft(e.target.value)}
        disabled={busy}
        style={{ width: 88, fontSize: 12, textAlign: 'right' }}
      />
      <button type="button" className="btn btn-secondary" onClick={save} disabled={busy} style={{ fontSize: 11, padding: '2px 8px' }}>
        Save
      </button>
      {mine && (
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => run(() => clearCostBasis(holding.account_id, holding.symbol))}
          disabled={busy}
          style={{ fontSize: 11, padding: '2px 8px' }}
        >
          Clear
        </button>
      )}
      <button
        type="button"
        onClick={() => setEditing(false)}
        disabled={busy}
        style={{ fontSize: 11, background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
      >
        Cancel
      </button>
      {failed && <span style={{ fontSize: 10, color: '#ef4444' }}>Enter a price above 0.</span>}
    </div>
  );
}

// InvestmentsTab — connects brokerages via SnapTrade and shows holdings,
// allocation, and unrealized gain/loss. Mirrors the connect flow used for
// bank accounts (accounts/AccountsModal.js) but SnapTrade hands back a
// portal URL rather than a JS SDK, so we open it and sync once it closes.
export default function InvestmentsTab({ onOpenSettings }) {
  const [config, setConfig] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncingAccount, setSyncingAccount] = useState(null);
  const [notice, setNotice] = useState(null);
  // Bumped on every reload so the self-fetching quality card refreshes with
  // the rest of the page after a sync or a cost-basis edit.
  const [dataVersion, setDataVersion] = useState(0);
  const pollRef = useRef(null);

  const reload = useCallback(() => {
    setDataVersion((v) => v + 1);
    return Promise.all([
      getPortfolio().then((r) => setPortfolio(r.data)),
      listSnapTradeConnections()
        .then((r) => setConnections(r.data.connections || []))
        .catch(() => setConnections([])),
    ]);
  }, []);

  useEffect(() => {
    getSnapTradeConfig()
      .then((r) => {
        setConfig(r.data);
        if (r.data.configured) return reload();
        return null;
      })
      .catch(() => setError('Could not reach the server.'))
      .finally(() => setLoading(false));
  }, [reload]);

  // Clear the popup poller if the user navigates away mid-connect.
  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  const runSync = useCallback(async () => {
    setSyncing(true);
    setError(null);
    try {
      const { data } = await syncSnapTrade();
      setNotice(data.message || 'Sync complete.');
      await reload();
    } catch {
      setError('Sync failed — could not fetch holdings from SnapTrade.');
    } finally {
      setSyncing(false);
      setConnecting(false);
    }
  }, [reload]);

  const runAccountSync = useCallback(async (accountId, accountName) => {
    setSyncingAccount(accountId);
    setError(null);
    try {
      const { data } = await syncSnapTradeAccount(accountId);
      setNotice(data.message || `Synced ${accountName}.`);
      await reload();
    } catch {
      setError(`Sync failed for ${accountName}.`);
    } finally {
      setSyncingAccount(null);
    }
  }, [reload]);

  const handleConnect = useCallback(async () => {
    setConnecting(true);
    setError(null);
    setNotice(null);
    try {
      const { data } = await connectSnapTrade();
      const popup = window.open(
        data.redirect_uri,
        'snaptrade-connect',
        'width=520,height=740',
      );
      if (!popup) {
        setError('Popup blocked — allow popups for this site and try again.');
        setConnecting(false);
        return;
      }
      const finish = (shouldSync) => {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        window.removeEventListener('message', onMessage);
        if (!popup.closed) popup.close();
        if (shouldSync) {
          runSync();
        } else {
          setConnecting(false);
        }
      };
      const onMessage = (evt) => {
        const payload = typeof evt.data === 'string' ? evt.data : evt.data?.status;
        if (!payload) return;
        const status = String(payload).toUpperCase();
        if (status === 'SUCCESS' || status === 'CLOSED') finish(true);
        else if (status === 'ABANDONED' || status === 'ERROR') finish(false);
      };
      window.addEventListener('message', onMessage);
      pollRef.current = setInterval(() => {
        if (popup.closed) finish(true);
      }, 800);
    } catch {
      setError('Could not start the SnapTrade connection.');
      setConnecting(false);
    }
  }, [runSync]);

  const groups = useMemo(() => {
    const map = {};
    for (const a of portfolio?.by_account || []) {
      map[a.account_id] = {
        account_id: a.account_id,
        account_name: a.account_name,
        institution: a.institution,
        source: a.source,
        value: a.value,
        holdings: [],
      };
    }
    for (const h of portfolio?.holdings || []) {
      // An account with positions but no by_account entry can only have come
      // from a positions sync, so it gets the snaptrade treatment (per-account
      // Sync button) rather than falling through to the balance-only branch.
      const g = map[h.account_id] || (map[h.account_id] = {
        account_id: h.account_id,
        account_name: h.account_name,
        institution: h.institution,
        source: h.source || 'snaptrade',
        value: null,
        holdings: [],
      });
      g.holdings.push(h);
    }
    return Object.values(map);
  }, [portfolio]);

  if (loading) {
    return (
      <div className="finances-section">
        <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin /> Loading…</div>
      </div>
    );
  }

  if (config && !config.configured) {
    // The projection reads balances, not positions, so it still has something
    // to say when no brokerage is linked.
    return (
      <div style={{ display: 'grid', gap: 16 }}>
        <div className="finances-section" style={{ color: 'var(--text-muted)' }}>
          SnapTrade isn&apos;t configured on the server. Add <code>SNAPTRADE_CLIENT_ID</code> and{' '}
          <code>SNAPTRADE_CONSUMER_KEY</code> to your <code>.env</code>, then restart the backend.
        </div>
        <RetirementSection onOpenSettings={onOpenSettings} />
      </div>
    );
  }

  const hasHoldings = portfolio && portfolio.holding_count > 0;
  const gain = portfolio?.total_gain ?? 0;
  const gainColor = gain >= 0 ? '#059669' : '#ef4444';

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* Summary + actions */}
      <div className="finances-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Portfolio Value</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{fmt$(portfolio?.total_value || 0)}</div>
            {hasHoldings && (
              <div style={{ fontSize: 13, color: gainColor, marginTop: 2 }}>
                {fmtSigned(gain)} unrealized
                {portfolio.total_gain_pct !== null && portfolio.total_gain_pct !== undefined
                  ? ` (${portfolio.total_gain_pct >= 0 ? '+' : ''}${portfolio.total_gain_pct}%)`
                  : ''}
                {' · '}cost basis {fmt$(portfolio.total_cost || 0)}
              </div>
            )}
            {portfolio?.balance_only_value > 0 && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                Includes {fmt$(portfolio.balance_only_value)} from accounts that report a
                balance but no positions — gain and allocation below cover the rest.
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleConnect}
              disabled={connecting || syncing}
            >
              {connecting ? 'Connecting…' : '+ Connect a brokerage'}
            </button>
            {connections.length > 0 && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={runSync}
                disabled={syncing || connecting}
              >
                {syncing ? 'Syncing…' : '↺ Sync now'}
              </button>
            )}
          </div>
        </div>

        {notice && <div style={{ marginTop: 10, color: '#059669', fontSize: 13 }}>{notice}</div>}
        {error && <div style={{ marginTop: 10, color: '#ef4444', fontSize: 13 }}>{error}</div>}

        {connections.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {connections.map((c) => (
              <span
                key={c.id}
                style={{
                  fontSize: 12, padding: '3px 10px', borderRadius: 12,
                  background: 'var(--border, #334155)',
                  color: c.disabled ? '#ef4444' : 'var(--text, inherit)',
                }}
              >
                {c.brokerage}{c.disabled ? ' · needs reconnect' : ''}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Allocation */}
      {hasHoldings && portfolio.allocation.length > 0 && (
        <div className="finances-section">
          <h3 className="finances-section-title" style={{ marginTop: 0 }}>Allocation</h3>
          <div style={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden', marginBottom: 10 }}>
            {portfolio.allocation.map((a) => (
              <div
                key={a.asset_type}
                title={`${ASSET_LABEL[a.asset_type] || a.asset_type}: ${a.pct}%`}
                style={{ width: `${a.pct}%`, background: ALLOC_COLORS[a.asset_type] || ALLOC_COLORS.other }}
              />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12 }}>
            {portfolio.allocation.map((a) => (
              <span key={a.asset_type} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  width: 10, height: 10, borderRadius: 2,
                  background: ALLOC_COLORS[a.asset_type] || ALLOC_COLORS.other,
                }}
                />
                {ASSET_LABEL[a.asset_type] || a.asset_type} · {fmt$(a.value)} ({a.pct}%)
              </span>
            ))}
          </div>
        </div>
      )}

      {hasHoldings && <PortfolioQuality refreshKey={dataVersion} />}

      <RetirementSection onOpenSettings={onOpenSettings} />

      {/* Holdings by account */}
      {!hasHoldings && groups.length === 0 && (
        <div className="finances-section" style={{ color: 'var(--text-muted)' }}>
          No holdings yet. Connect a brokerage (Robinhood, M1, E-trade, …) to sync your
          stocks and crypto.
        </div>
      )}

      {groups.map((g) => (
        <div className="finances-section" key={g.account_id}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h3 className="finances-section-title" style={{ margin: 0 }}>
              {g.account_name}
              {g.institution ? <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> · {g.institution}</span> : null}
            </h3>
            {/* Per-account sync is a SnapTrade endpoint — a bank-synced
                brokerage refreshes with the rest of the balances instead. */}
            {g.source === 'snaptrade' ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => runAccountSync(g.account_id, g.account_name)}
                disabled={syncing || syncingAccount === g.account_id}
                title="Sync only this account"
              >
                {syncingAccount === g.account_id ? 'Syncing…' : '↺ Sync'}
              </button>
            ) : (
              <span style={{ fontFamily: "'DM Mono', ui-monospace, monospace", fontWeight: 500 }}>
                {fmt$(g.value || 0)}
              </span>
            )}
          </div>
          {g.holdings.length === 0 ? (
            g.source === 'snaptrade' ? (
              <div style={{ fontSize: 13, color: 'var(--text-muted)', padding: '8px 0' }}>
                No positions returned yet for this account. SnapTrade can take up to ~30 minutes
                after a fresh brokerage connection to surface positions. If it stays empty after
                that, reconnect this brokerage via <strong>+ Connect a brokerage</strong>.
              </div>
            ) : (
              <div style={{ fontSize: 13, color: 'var(--text-muted)', padding: '8px 0' }}>
                Balance only — this account is synced through your bank connection, which
                reports its value but not the individual positions. Connect{' '}
                {g.institution || 'this brokerage'} via <strong>+ Connect a brokerage</strong>{' '}
                to see holdings.
              </div>
            )
          ) : (
          <table className="eh-table" style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'right', color: 'var(--text-muted)', fontSize: 11 }}>
                <th style={{ textAlign: 'left' }}>Symbol</th>
                <th>Qty</th>
                <th>Avg cost</th>
                <th>Price</th>
                <th>Value</th>
                <th>Gain / loss</th>
              </tr>
            </thead>
            <tbody>
              {g.holdings.map((h) => {
                const g$ = h.unrealized_gain;
                const gColor = (g$ ?? 0) >= 0 ? '#059669' : '#ef4444';
                return (
                  <tr key={`${h.account_id}-${h.symbol}`} style={{ borderTop: '1px solid var(--border, #334155)' }}>
                    <td style={{ padding: '6px 0' }}>
                      <span style={{ fontWeight: 600 }}>{h.symbol}</span>
                      <span style={{
                        fontSize: 10, marginLeft: 6, padding: '1px 6px', borderRadius: 8,
                        background: ALLOC_COLORS[h.asset_type] || ALLOC_COLORS.other, color: '#fff',
                      }}
                      >
                        {ASSET_LABEL[h.asset_type] || h.asset_type}
                      </span>
                      {h.description && (
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{h.description}</div>
                      )}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: "'DM Mono', monospace" }}>{h.quantity}</td>
                    <td style={{ textAlign: 'right' }}>
                      <CostBasisCell holding={h} onSaved={reload} />
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: "'DM Mono', monospace" }}>
                      {h.last_price !== null && h.last_price !== undefined ? fmt$(h.last_price) : '—'}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
                      {h.market_value !== null && h.market_value !== undefined ? fmt$(h.market_value) : '—'}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: "'DM Mono', monospace", color: gColor }}>
                      {g$ !== null && g$ !== undefined
                        ? `${fmtSigned(g$)}${h.gain_pct !== null && h.gain_pct !== undefined
                          ? ` (${h.gain_pct >= 0 ? '+' : ''}${h.gain_pct}%)` : ''}`
                        : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          )}
        </div>
      ))}
    </div>
  );
}
