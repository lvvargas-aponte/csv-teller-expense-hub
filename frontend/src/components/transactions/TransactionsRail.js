import React, { useMemo, useState } from 'react';
import { fmt$, calculateHalf, merchantKey } from '../../utils/formatting';
import Spin from '../ui/Spin';

function RailProgressCard({ txns, progress, onOpenDetail }) {
  const total = progress.total;
  const reviewed = progress.reviewed;
  const unreviewed = total - reviewed;
  const pct = total ? Math.round((reviewed / total) * 100) : 0;
  const next = txns.find((t) => !t.reviewed);
  return (
    <div className="tx-rail-card">
      <h3 className="tx-rail-title">Review progress</h3>
      <div className="tx-rail-big">
        {reviewed}<small>of {total} reviewed</small>
      </div>
      <div className="tx-rail-bar"><span style={{ width: `${pct}%` }} /></div>
      <div className="tx-rail-hint">
        {unreviewed ? `${unreviewed} left in this view.` : 'Everything here is reviewed.'}
      </div>
      {unreviewed > 0 && next && (
        <button type="button" className="tx-btn tx-btn-primary tx-rail-btn" onClick={() => onOpenDetail(next.id)}>
          Review next unreviewed
        </button>
      )}
    </div>
  );
}

function RailSimilarCard({ matches, openTxn, pending, onApplyToSimilar, applying }) {
  const n = matches.length;
  const catLabel = pending.category || 'Uncategorized';
  const splitLabel = pending.is_shared ? 'shared' : 'personal';
  return (
    <div className="tx-rail-card">
      <h3 className="tx-rail-title">Apply to similar</h3>
      <div className="tx-rail-merchant" title={openTxn.description}>{merchantKey(openTxn.description)}…</div>
      <div className="tx-rail-hint">
        {n} other transaction{n === 1 ? '' : 's'} {n === 1 ? 'matches' : 'match'} this
        merchant. Apply <b>{catLabel}</b> and <b>{splitLabel}</b> to all of them.
      </div>
      <button
        type="button"
        className="tx-btn tx-btn-primary tx-rail-btn"
        onClick={() => onApplyToSimilar(matches, pending)}
        disabled={applying}
      >
        {applying ? <Spin /> : null} Apply to {n}
      </button>
    </div>
  );
}

function RailSharedCard({ txns, personName, onSendToSheet, sendingSheet }) {
  const shared = useMemo(() => txns.filter((t) => t.is_shared), [txns]);
  const owed = useMemo(
    () => shared.reduce((sum, t) => sum + (Number(t.person_2_owes) || calculateHalf(t.amount)), 0),
    [shared]
  );
  return (
    <div className="tx-rail-card tx-rail-card--dark">
      <h3 className="tx-rail-title">Shared with {personName || 'Person 2'}</h3>
      <div className="tx-rail-big">
        {fmt$(owed)}<small>owed to you</small>
      </div>
      <div className="tx-rail-hint">
        Across {shared.length} shared transaction{shared.length === 1 ? '' : 's'} in this view.
      </div>
      {onSendToSheet && (
        <button
          type="button"
          className="tx-btn tx-rail-btn tx-rail-btn--sheet"
          onClick={onSendToSheet}
          disabled={shared.length === 0 || sendingSheet}
        >
          {sendingSheet ? <Spin /> : null} Send to Sheet ({shared.length})
        </button>
      )}
    </div>
  );
}

function RailCategoriesCard({ txns }) {
  const top = useMemo(() => {
    const totals = {};
    txns.forEach((t) => {
      if (t.transaction_type === 'credit') return;
      const cat = t.category || 'Uncategorized';
      totals[cat] = (totals[cat] || 0) + Math.abs(parseFloat(t.amount) || 0);
    });
    return Object.entries(totals).sort((a, b) => b[1] - a[1]).slice(0, 4);
  }, [txns]);
  const max = top.length ? top[0][1] : 1;
  return (
    <div className="tx-rail-card">
      <h3 className="tx-rail-title">Where it went</h3>
      {top.length === 0 ? (
        <div className="tx-rail-empty">No spending in this view.</div>
      ) : (
        <div className="tx-rail-cats">
          {top.map(([cat, total]) => (
            <div key={cat} className="tx-rail-catline">
              <span>{cat}</span>
              <b>{fmt$(total)}</b>
              <span className="tx-rail-cattrack"><span style={{ width: `${Math.round((total / max) * 100)}%` }} /></span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Supporting rail beside the transactions table (design handoff A2).
// All figures derive from `txns` — the currently filtered set, not the
// whole account.
export default function TransactionsRail({
  txns,
  progress,
  openTxn = null,
  draft = null,
  personName,
  onOpenDetail,
  onApplyToSimilar,
  onSendToSheet = null,
  sendingSheet = false,
}) {
  const [applying, setApplying] = useState(false);

  const matches = useMemo(() => {
    if (!openTxn) return [];
    const key = merchantKey(openTxn.description);
    if (!key) return [];
    return txns.filter((t) => t.id !== openTxn.id && merchantKey(t.description) === key);
  }, [txns, openTxn]);

  const pending = draft || (openTxn
    ? { category: openTxn.category || '', is_shared: !!openTxn.is_shared }
    : null);

  const handleApply = async (matched, values) => {
    if (applying) return;
    setApplying(true);
    try {
      await onApplyToSimilar(matched, values);
    } finally {
      setApplying(false);
    }
  };

  return (
    <aside className="tx-rail" aria-label="Transaction insights">
      <RailProgressCard txns={txns} progress={progress} onOpenDetail={onOpenDetail} />
      {openTxn && matches.length > 0 && (
        <RailSimilarCard
          matches={matches}
          openTxn={openTxn}
          pending={pending}
          onApplyToSimilar={handleApply}
          applying={applying}
        />
      )}
      <RailSharedCard
        txns={txns}
        personName={personName}
        onSendToSheet={onSendToSheet}
        sendingSheet={sendingSheet}
      />
      <RailCategoriesCard txns={txns} />
    </aside>
  );
}
