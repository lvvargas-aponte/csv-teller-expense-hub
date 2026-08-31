import React, { useCallback, useEffect, useMemo, useState } from 'react';
import SyncStatusLine from './SyncStatusLine';
import CorrectionsFeed from './CorrectionsFeed';
import SettleUpCard from './SettleUpCard';
import SettleActions from './SettleActions';
import AttentionStrip from './AttentionStrip';
import SharedFilters, { matchesFilter } from './SharedFilters';
import SharedDayGroup from './SharedDayGroup';
import Spin from '../ui/Spin';
import { SyncIcon } from './icons';
import {
  getSharedRows, getSyncStatus, syncShared, acknowledgeCorrection, setDispute,
  markPeriodReady, withdrawPeriodReady, markPeriodPaid, reopenPeriod,
} from '../../api/sync';
import { putTransactionFields, getPersonNames } from '../../api/transactions';
import { userMessage } from '../../utils/errorMessage';

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

function groupByDate(rows) {
  const byDate = new Map();
  rows.forEach((row) => {
    const key = row.date || '';
    if (!byDate.has(key)) byDate.set(key, []);
    byDate.get(key).push(row);
  });
  return [...byDate.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([date, dayRows]) => ({ date, rows: dayRows }));
}

export default function SharedPage() {
  const months = useMemo(() => monthOptions(), []);
  const [period, setPeriod] = useState(months[months.length - 1]?.key || CUTOVER_PERIOD);
  const [rows, setRows] = useState([]);
  const [settlement, setSettlement] = useState(null);
  const [settleState, setSettleState] = useState(null);
  const [settling, setSettling] = useState(false);
  const [peer, setPeer] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState(null);
  const [filter, setFilter] = useState('all');
  // The two configured names, for the "who paid" repair. Person slots are
  // config, not per-row data, so this is fetched once rather than per period.
  const [personNames, setPersonNames] = useState({ person_1: '', person_2: '' });
  const [mySlot, setMySlot] = useState(1);
  // What the last settlement action managed to write to the spreadsheet.
  const [published, setPublished] = useState(null);

  const load = useCallback(async (p) => {
    setLoading(true);
    try {
      const [rowsRes, statusRes] = await Promise.all([getSharedRows(p), getSyncStatus()]);
      setRows(rowsRes.data.rows);
      setSettlement(rowsRes.data.settlement || null);
      setSettleState(rowsRes.data.settlement_state || null);
      setPublished(null);
      setPeer(rowsRes.data.peer);
      setMySlot(rowsRes.data.me ? rowsRes.data.me.person_slot : 1);
      setStatus(statusRes.data);
      setError(null);
    } catch (e) {
      setError(userMessage(e, 'Could not load shared expenses — please try again.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(period); }, [period, load]);

  useEffect(() => {
    getPersonNames()
      .then((res) => setPersonNames(res.data))
      .catch(() => {});   // the who-repair falls back to a blank picker
  }, []);

  // Repairing a blocked row of ours. PUT /transactions/{id} replaces the whole
  // shared block, so putTransactionFields re-sends what we already know and
  // overlays the patch; then the month reloads, which is what moves the row out
  // of "not counted" and into the settle-up total.
  const handleFix = useCallback(async (row, patch) => {
    const editable = row.editable || {};
    await putTransactionFields(
      {
        id: row.transaction_id,
        is_shared: editable.is_shared,
        who: row.who,
        what: editable.what,
        notes: row.notes,
        person_1_owes: editable.person_1_owes,
        person_2_owes: editable.person_2_owes,
        reviewed: row.reviewed,
      },
      patch,
    );
    await load(period);
  }, [period, load]);

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
      const disputed = results.reduce((n, r) => n + (r.disputes_pushed || 0), 0);
      const disputeText = disputed > 0 ? `, ${disputed} dispute${disputed === 1 ? '' : 's'} sent` : '';
      setSyncMessage({ kind: 'ok', text: `${pushed} sent, ${pulled} received${disputeText}` });
      await load(period);
    } catch (e) {
      setSyncMessage({ kind: 'error', text: userMessage(e, 'Sync failed — please try again.') });
    } finally {
      setSyncing(false);
    }
  }, [period, load]);

  const handleDispute = useCallback(async (txnId, payload) => {
    try {
      await setDispute(txnId, payload);
      await load(period);
    } catch (e) {
      setError(userMessage(e, 'Could not update the dispute — please try again.'));
      throw e;
    }
  }, [period, load]);

  // Every settlement call answers with the period's whole recomputed position,
  // so the card updates from the response rather than a second round trip.
  const runSettle = useCallback(async (call) => {
    setSettling(true);
    try {
      const res = await call(period);
      setSettlement(res.data.settlement || null);
      setSettleState(res.data.settlement_state || null);
      setPublished(res.data.published || null);
      setError(null);
    } catch (e) {
      // 409 means the other side settled it first. Their record is the truth,
      // so reload rather than leaving the page showing a state that lost.
      setPublished(null);
      if (e?.response?.status === 409) {
        await load(period);
      } else {
        setError(userMessage(e, 'Could not update the settlement — please try again.'));
      }
    } finally {
      setSettling(false);
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

  const peerName = peer && peer.display_name ? peer.display_name : 'peer';
  const monthLabel = (months.find((m) => m.key === period) || {}).label || period;
  const visible = useMemo(() => rows.filter((r) => matchesFilter(r, filter)), [rows, filter]);
  const groups = useMemo(() => groupByDate(visible), [visible]);

  return (
    <div className="shared-page">
      <div className="sh-head">
        <h2>Shared</h2>
        <div className="tx-sel-wrap">
          <select
            aria-label="Month"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            {months.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        </div>
        <span className="sh-spacer" />
        <button type="button" className="sh-btn" onClick={handleSync} disabled={syncing}>
          {syncing ? <><Spin /> Syncing…</> : <><SyncIcon /> Sync now</>}
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

      <SettleUpCard settlement={settlement} peerName={peerName} monthLabel={monthLabel} />

      <SettleActions
        state={settleState}
        peerName={peerName}
        busy={settling}
        published={published}
        onReady={() => runSettle(markPeriodReady)}
        onWithdrawReady={() => runSettle(withdrawPeriodReady)}
        onPaid={(note) => runSettle((p) => markPeriodPaid(p, note))}
        onReopen={() => runSettle(reopenPeriod)}
      />

      <SyncStatusLine
        status={status}
        syncMessage={syncMessage}
        onDismissMessage={() => setSyncMessage(null)}
        onSync={handleSync}
        syncing={syncing}
      />

      <CorrectionsFeed corrections={status?.corrections || []} onDismiss={dismissCorrection} />

      <AttentionStrip rows={rows} peerName={peerName} onReview={() => setFilter('attention')} />

      {rows.length > 0 && (
        <SharedFilters rows={rows} value={filter} onChange={setFilter} peerName={peerName} />
      )}

      <div className="sh-list">
        {loading ? (
          <div className="sh-empty"><span>Loading…</span></div>
        ) : groups.length === 0 ? (
          <div className="sh-empty">
            <b>Nothing shared in {monthLabel} yet</b>
            <span>Mark a transaction as shared and it shows up here.</span>
          </div>
        ) : (
          groups.map((g) => (
            <SharedDayGroup
              key={g.date}
              date={g.date}
              rows={g.rows}
              peerName={peerName}
              personNames={personNames}
              mySlot={mySlot}
              onDispute={handleDispute}
              onFix={handleFix}
            />
          ))
        )}
      </div>

      <div className="sh-legend">
        <i><span className="sh-k sh-k--me" /> Paid by you</i>
        <i><span className="sh-k sh-k--peer" /> Paid by {peerName}</i>
        <i>Only rows with a split are counted toward settle up.</i>
      </div>
    </div>
  );
}
