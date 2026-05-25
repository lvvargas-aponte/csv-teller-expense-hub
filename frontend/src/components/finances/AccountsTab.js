import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Spin from '../ui/Spin';
import { getBalancesSummary } from '../../api/balances';
import {
  getAllAccountDetails,
  upsertAccountDetails,
} from '../../api/accountDetails';
import CreditCardTable from './accounts/CreditCardTable';
import CashList from './accounts/CashList';
import AccountsSummaryCard from './accounts/AccountsSummaryCard';
import UtilSummaryCard from './accounts/UtilSummaryCard';
import AddAccountModal from './accounts/AddAccountModal';
import ConnectionsHeader from './accounts/ConnectionsHeader';

// AccountsTab — dense, scannable view with inline-editable per-account
// metadata. Receives the cached `summary` from FinancesPage so we don't
// double-fetch balances; account-detail metadata is loaded locally and
// updated optimistically as the user edits cells.
export default function AccountsTab({ summary, summaryLoading, summaryError, onRefresh }) {
  const [externalSummary, setExternalSummary] = useState(null);
  const [externalLoading, setExternalLoading] = useState(false);
  const [externalError, setExternalError] = useState(null);
  const [detailsMap, setDetailsMap] = useState({});
  const [detailsLoaded, setDetailsLoaded] = useState(false);
  const [addingKind, setAddingKind] = useState(null);

  // If the parent didn't pass summary in (e.g. AccountsTab rendered standalone
  // in a test), fetch it ourselves. The normal path is through FinancesPage.
  useEffect(() => {
    if (summary !== undefined) return;
    setExternalLoading(true);
    getBalancesSummary(false)
      .then((r) => setExternalSummary(r.data))
      .catch(() => setExternalError('Could not load accounts — is the backend running?'))
      .finally(() => setExternalLoading(false));
  }, [summary]);

  useEffect(() => {
    getAllAccountDetails()
      .then((r) => setDetailsMap(r.data || {}))
      .catch(() => setDetailsMap({}))
      .finally(() => setDetailsLoaded(true));
  }, []);

  const effectiveSummary = summary !== undefined ? summary : externalSummary;
  const loading = summary !== undefined ? !!summaryLoading : externalLoading;
  const error   = summary !== undefined ? summaryError    : externalError;

  const accounts = useMemo(() => effectiveSummary?.accounts ?? [], [effectiveSummary]);
  const credit     = useMemo(() => accounts.filter((a) => a.type === 'credit'),     [accounts]);
  const depository = useMemo(() => accounts.filter((a) => a.type === 'depository'), [accounts]);

  // Optimistic-merge: apply the edit locally so the cell snaps back with the
  // new value, then PUT in the background. On failure we revert and let the
  // user see the original value.
  const handleFieldUpdate = useCallback(async (accountId, field, value) => {
    const prev = detailsMap[accountId] || {};
    const next = { ...prev, [field]: value };
    setDetailsMap((m) => ({ ...m, [accountId]: next }));

    const payload = {
      apr:             toNum(next.apr),
      credit_limit:    toNum(next.credit_limit),
      minimum_payment: toNum(next.minimum_payment),
      statement_day:   toInt(next.statement_day),
      due_day:         toInt(next.due_day),
      notes:           next.notes ?? '',
    };
    try {
      await upsertAccountDetails(accountId, payload);
    } catch {
      setDetailsMap((m) => ({ ...m, [accountId]: prev }));
    }
  }, [detailsMap]);

  if (loading || !detailsLoaded) {
    return (
      <div className="finances-section">
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <Spin /> Loading…
        </div>
      </div>
    );
  }
  if (error) {
    return <div className="finances-section" style={{ color: '#f87171' }}>{error}</div>;
  }
  if (accounts.length === 0) {
    return (
      <>
        <ConnectionsHeader summaryAccounts={accounts} onRefresh={onRefresh} />
        <div className="finances-section" style={{ color: 'var(--text-muted)' }}>
          No accounts yet — connect a bank or add one manually below.
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button type="button" className="btn btn-secondary" onClick={() => setAddingKind('credit')}>
              + Add credit card or loan
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setAddingKind('depository')}>
              + Add bank account or savings
            </button>
          </div>
        </div>
        {addingKind && (
          <AddAccountModal
            kind={addingKind}
            onClose={() => setAddingKind(null)}
            onSaved={() => onRefresh?.()}
          />
        )}
      </>
    );
  }

  return (
    <>
      <ConnectionsHeader summaryAccounts={accounts} onRefresh={onRefresh} />
      <div className="acct-grid">
        <div className="acct-grid-main">
          <CreditCardTable
            accounts={credit}
            detailsMap={detailsMap}
            cacheFetchedAt={effectiveSummary?.cache_fetched_at}
            onUpdate={handleFieldUpdate}
            onAdd={() => setAddingKind('credit')}
          />
          <CashList
            accounts={depository}
            cacheFetchedAt={effectiveSummary?.cache_fetched_at}
            onAdd={() => setAddingKind('depository')}
          />
        </div>
        <aside className="acct-grid-rail">
          <AccountsSummaryCard
            creditAccounts={credit}
            cashAccounts={depository}
            detailsMap={detailsMap}
          />
          <UtilSummaryCard creditAccounts={credit} detailsMap={detailsMap} />
          {onRefresh && (
            <button type="button" className="btn btn-secondary acct-rail-refresh" onClick={onRefresh}>
              ↺ Refresh balances
            </button>
          )}
        </aside>
      </div>
      {addingKind && (
        <AddAccountModal
          kind={addingKind}
          onClose={() => setAddingKind(null)}
          onSaved={() => onRefresh?.()}
        />
      )}
    </>
  );
}

function toNum(v) {
  if (v === '' || (v === null || v === undefined)) return null;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}
function toInt(v) {
  if (v === '' || (v === null || v === undefined)) return null;
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : null;
}
