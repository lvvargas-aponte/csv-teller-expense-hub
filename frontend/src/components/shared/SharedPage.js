import React, { useCallback, useEffect, useMemo, useState } from 'react';
import SyncStatusStrip from './SyncStatusStrip';
import CorrectionsFeed from './CorrectionsFeed';
import SharedRow from './SharedRow';
import Spin from '../ui/Spin';
import { getSharedRows, getSyncStatus, syncShared, acknowledgeCorrection } from '../../api/sync';
import { userMessage } from '../../utils/errorMessage';
import './SharedPage.css';

const CUTOVER_PERIOD = '2026-06';

function monthOptions() {
  const now = new Date();
  const [cutoverYear, cutoverMonth] = CUTOVER_PERIOD.split('-').map(Number);
  const endYear = now.getFullYear();
  const endMonth = now.getMonth() + 1;

  const months = [];
  let y = cutoverYear;
  let m = cutoverMonth;
  while (y < endYear || (y === endYear && m <= endMonth)) {
    const key = `${y}-${String(m).padStart(2, '0')}`;
    const label = new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    months.push({ key, label });
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  }
  return months;
}

export default function SharedPage() {
  const months = useMemo(() => monthOptions(), []);
  const [period, setPeriod] = useState(months[months.length - 1].key);
  const [rows, setRows] = useState([]);
  const [peer, setPeer] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState(null);

  const load = useCallback(async (p) => {
    setLoading(true);
    try {
      const [rowsRes, statusRes] = await Promise.all([getSharedRows(p), getSyncStatus()]);
      setRows(rowsRes.data.rows);
      setPeer(rowsRes.data.peer);
      setStatus(statusRes.data);
      setError(null);
    } catch (e) {
      setError(userMessage(e, 'Could not load shared expenses — please try again.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(period); }, [period, load]);

  const handleSync = useCallback(async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const res = await syncShared({ period });
      const results = res.data.results || [];

      if (res.data.status === 'refused') {
        const refused = results.find((r) => r.refusal_message);
        setSyncMessage({ kind: 'refused', text: refused ? refused.refusal_message : 'Sync was refused.' });
        await load(period);
        return;
      }
      if (res.data.status === 'error') {
        const failed = results.find((r) => r.error_detail);
        setSyncMessage({ kind: 'error', text: failed ? failed.error_detail : 'Sync failed — please try again.' });
        await load(period);
        return;
      }

      const pushed = results.reduce((n, r) => n + (r.rows_pushed || 0), 0);
      const pulled = results.reduce((n, r) => n + (r.rows_pulled || 0), 0);
      setSyncMessage({ kind: 'ok', text: `${pushed} sent, ${pulled} received` });
      await load(period);
    } catch (e) {
      setSyncMessage({ kind: 'error', text: userMessage(e, 'Sync failed — please try again.') });
    } finally {
      setSyncing(false);
    }
  }, [period, load]);

  const dismissCorrection = useCallback(async (id) => {
    try {
      await acknowledgeCorrection(id);
      setStatus((prev) => (prev ? {
        ...prev,
        corrections: prev.corrections.filter((c) => c.id !== id),
      } : prev));
    } catch (e) {
      setError(userMessage(e, 'Could not dismiss correction — please try again.'));
    }
  }, []);

  return (
    <div className="shared-page">
      <div className="shared-header">
        <h2 className="shared-title">Shared</h2>
        <div className="tx-sel-wrap shared-month-wrap">
          <select
            aria-label="Month"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            {months.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        </div>
        <button
          type="button"
          className="tx-btn tx-btn-primary"
          onClick={handleSync}
          disabled={syncing}
        >
          {syncing ? <><Spin /> Syncing…</> : 'Sync now'}
        </button>
      </div>

      {error && (
        <div className="tx-error-banner">
          <span>⚠️ {error}</span>
          <button
            type="button"
            className="tx-error-close"
            aria-label="Dismiss error"
            onClick={() => setError(null)}
          >✕</button>
        </div>
      )}

      {syncMessage && syncMessage.kind !== 'ok' && (
        <div className="tx-error-banner">
          <span>⚠️ {syncMessage.text}</span>
          <button
            type="button"
            className="tx-error-close"
            aria-label="Dismiss sync message"
            onClick={() => setSyncMessage(null)}
          >✕</button>
        </div>
      )}
      {syncMessage && syncMessage.kind === 'ok' && (
        <div className="shared-sync-toast" role="status">✓ {syncMessage.text}</div>
      )}

      <SyncStatusStrip status={status} />

      <CorrectionsFeed corrections={status?.corrections || []} onDismiss={dismissCorrection} />

      <div className="tx-table-card">
        <table className="tx-table shared-table">
          <thead>
            <tr>
              <th>Who</th>
              <th>Date</th>
              <th>Description</th>
              <th className="tx-col-amt">Amount</th>
              <th className="tx-col-amt">You owe</th>
              <th className="tx-col-amt">{peer && peer.display_name ? `${peer.display_name} owes` : 'They owe'}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6}>
                <div className="tx-empty"><div style={{ fontSize: 28 }}>⏳</div><p>Loading…</p></div>
              </td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={6}>
                <div className="tx-empty">
                  <div style={{ fontSize: 28 }}>🔍</div>
                  <p>No shared expenses for this month.</p>
                </div>
              </td></tr>
            ) : (
              rows.map((row) => <SharedRow key={row.transaction_id} row={row} />)
            )}
          </tbody>
        </table>
      </div>

      <div className="shared-legend">
        <span><span className="shared-owner-dot shared-owner-dot--me" aria-hidden="true">●</span> yours</span>
        <span><span className="shared-owner-dot shared-owner-dot--peer" aria-hidden="true">○</span> {peer ? peer.display_name : 'peer'}</span>
      </div>
    </div>
  );
}
