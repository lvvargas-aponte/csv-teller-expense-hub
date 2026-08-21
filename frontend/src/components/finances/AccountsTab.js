import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Spin from '../ui/Spin';
import { getBalancesSummary, deleteManualAccount, updateAccountBalance } from '../../api/balances';
import {
  getAllAccountDetails,
  upsertAccountDetails,
} from '../../api/accountDetails';
import { groupAccounts } from '../../utils/accountType';
import CreditCardTable from './accounts/CreditCardTable';
import BalanceList from './accounts/BalanceList';
import AccountsSummaryCard from './accounts/AccountsSummaryCard';
import UtilSummaryCard from './accounts/UtilSummaryCard';
import AddAccountModal from './accounts/AddAccountModal';
import EditBalanceModal from './accounts/EditBalanceModal';
import ConnectionsHeader from './accounts/ConnectionsHeader';

// AccountsTab — the account roster, and the only place accounts are listed.
//
// The page used to stack this component and BalancesSection, each rendering its
// own copy of every account under near-identical headings ("Cash & Savings"
// twice, credit cards twice), filtered by different rules — so an investment
// account filed as depository appeared in both the cash list and the investment
// list. The two are merged here: one list per group, grouped by the shared
// classifier that the backend's totals also use.
//
// Receives the cached `summary` from FinancesPage so we don't double-fetch
// balances; account-detail metadata is loaded locally and updated
// optimistically as the user edits cells.
export default function AccountsTab({
  summary,
  summaryLoading,
  summaryError,
  onRefresh,
  onViewNetWorth,
}) {
  const [externalSummary, setExternalSummary] = useState(null);
  const [externalLoading, setExternalLoading] = useState(false);
  const [externalError, setExternalError] = useState(null);
  const [detailsMap, setDetailsMap] = useState({});
  const [detailsLoaded, setDetailsLoaded] = useState(false);
  const [addingKind, setAddingKind] = useState(null);
  const [editingAcct, setEditingAcct] = useState(null);

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
  const { credit, cash, investments } = useMemo(() => groupAccounts(accounts), [accounts]);

  // Server-side totals, so each heading agrees with the Net Worth page rather
  // than re-deriving its own figure from the rows.
  const totals = useMemo(() => ({
    cash:        effectiveSummary?.total_cash,
    credit:      effectiveSummary?.total_credit_debt,
    investments: effectiveSummary?.total_investments,
  }), [effectiveSummary]);

  // Optimistic-merge: apply the edit locally so the cell snaps back with the
  // new value, then PUT in the background. On failure we revert and let the
  // user see the original value.
  const handleFieldUpdate = useCallback(async (accountId, field, value) => {
    const prev = detailsMap[accountId] || {};
    const next = { ...prev, [field]: value };
    setDetailsMap((m) => ({ ...m, [accountId]: next }));

    // Carry the rest of the stored record through. This screen only edits the
    // APR/limit/day fields, but the payoff planner writes debt class, the
    // deferred-interest promo and the payoff-tracking dates onto the same
    // record — sending just this screen's six fields used to wipe them.
    const { account_id, created, updated, ...rest } = next;
    const payload = {
      ...rest,
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

  const handleBalanceSave = useCallback(async ({ available, ledger }) => {
    if (!editingAcct) return;
    const payload = {};
    if (available !== '') payload.available = parseFloat(available) || 0;
    if (ledger    !== '') payload.ledger    = parseFloat(ledger)    || 0;
    await updateAccountBalance(editingAcct.id, payload);
    setEditingAcct(null);
    onRefresh?.();
  }, [editingAcct, onRefresh]);

  const handleDelete = useCallback(async (acct) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Remove ${acct.name}? This deletes the manual account.`)) return;
    try {
      await deleteManualAccount(acct.id);
      onRefresh?.();
    } catch { /* silent — the row stays put if the delete failed */ }
  }, [onRefresh]);

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

  const modals = (
    <>
      {addingKind && (
        <AddAccountModal
          kind={addingKind}
          onClose={() => setAddingKind(null)}
          onSaved={() => onRefresh?.()}
        />
      )}
      {editingAcct && (
        <EditBalanceModal
          acct={editingAcct}
          onSave={handleBalanceSave}
          onClose={() => setEditingAcct(null)}
        />
      )}
    </>
  );

  if (accounts.length === 0) {
    return (
      <>
        <ConnectionsHeader summaryAccounts={accounts} onRefresh={onRefresh} />
        <div className="finances-section" style={{ color: 'var(--text-muted)' }}>
          No accounts yet — connect a bank or add one manually below.
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setAddingKind('credit')}>
              + Add credit card or loan
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setAddingKind('depository')}>
              + Add bank account or savings
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setAddingKind('investment')}>
              + Add investment or retirement
            </button>
          </div>
        </div>
        {modals}
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
            total={totals.credit}
            onUpdate={handleFieldUpdate}
            onAdd={() => setAddingKind('credit')}
            onEdit={setEditingAcct}
            onDelete={handleDelete}
          />
          <BalanceList
            title="Cash & Savings"
            icon="🏦"
            accounts={cash}
            total={totals.cash}
            cacheFetchedAt={effectiveSummary?.cache_fetched_at}
            onAdd={() => setAddingKind('depository')}
            addLabel="Add bank account or savings"
            onEdit={setEditingAcct}
            onDelete={handleDelete}
          />
          <BalanceList
            title="Investments & Retirement"
            icon="📈"
            accounts={investments}
            total={totals.investments}
            cacheFetchedAt={effectiveSummary?.cache_fetched_at}
            onAdd={() => setAddingKind('investment')}
            addLabel="Add investment or retirement account"
            onEdit={setEditingAcct}
            onDelete={handleDelete}
          />
        </div>
        <aside className="acct-grid-rail">
          <AccountsSummaryCard
            creditAccounts={credit}
            cashAccounts={cash}
            investmentAccounts={investments}
            totals={totals}
            detailsMap={detailsMap}
            onViewNetWorth={onViewNetWorth}
          />
          <UtilSummaryCard creditAccounts={credit} detailsMap={detailsMap} />
          {onRefresh && (
            <button type="button" className="btn btn-secondary acct-rail-refresh" onClick={onRefresh}>
              ↺ Refresh balances
            </button>
          )}
        </aside>
      </div>
      {modals}
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
