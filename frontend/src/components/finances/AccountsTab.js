import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Spin from '../ui/Spin';
import { getBalancesSummary } from '../../api/balances';
import {
  getAllAccountDetails,
  upsertAccountDetails,
} from '../../api/accountDetails';
import { syncSnapTrade } from '../../api/snaptrade';
import ConnectionsStrip from './accounts/ConnectionsStrip';
import AccountSection from './accounts/AccountSection';
import AccountListRow from './accounts/AccountListRow';
import SimpleAccountRow from './accounts/SimpleAccountRow';
import AddAccountModal from './accounts/AddAccountModal';
import useConnectionHealth from './accounts/useConnectionHealth';
import { buildCreditRow, buildCashRow, summarize } from './accounts/accountMath';
import { classifyAccountBucket, loadInvestmentSubtypes } from '../../utils/accountBucket';

// AccountsTab — one summary bar, a connection-health strip, then collapsible
// account groups whose rows expand into an inline editor. Receives the cached
// `summary` from FinancesPage so we don't double-fetch balances; account-detail
// metadata is loaded locally and updated optimistically as the user edits.
export default function AccountsTab({
  summary, summaryLoading, summaryError, onRefresh, onManageConnections,
}) {
  const [externalSummary, setExternalSummary] = useState(null);
  const [externalLoading, setExternalLoading] = useState(false);
  const [externalError, setExternalError] = useState(null);
  const [detailsMap, setDetailsMap] = useState({});
  // Mirrors detailsMap synchronously so back-to-back edits to the same account
  // don't each read a render-stale map and overwrite one another.
  const detailsRef = useRef({});
  const [detailsLoaded, setDetailsLoaded] = useState(false);
  const [addingKind, setAddingKind] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(null);

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
      .then((r) => { detailsRef.current = r.data || {}; setDetailsMap(detailsRef.current); })
      .catch(() => { detailsRef.current = {}; setDetailsMap({}); })
      .finally(() => setDetailsLoaded(true));
  }, []);

  const effectiveSummary = summary !== undefined ? summary : externalSummary;
  const loading = summary !== undefined ? !!summaryLoading : externalLoading;
  const error   = summary !== undefined ? summaryError    : externalError;

  const accounts = useMemo(() => effectiveSummary?.accounts ?? [], [effectiveSummary]);
  const cacheFetchedAt = effectiveSummary?.cache_fetched_at;

  // Grouping goes through the shared classifier, not a bare `type` test — a
  // Roth IRA held as a manual depository account belongs under Investments
  // here and in the cash total, same as everywhere else in the app.
  const [bucketOf, setBucketOf] = useState(() => classifyAccountBucket);
  useEffect(() => {
    // The server's subtype vocabulary lands after first paint; re-bucket then.
    loadInvestmentSubtypes().then(() => setBucketOf(() => classifyAccountBucket));
  }, []);

  const creditRows = useMemo(
    () => accounts
      .filter((a) => bucketOf(a) === 'credit')
      .map((a) => buildCreditRow(a, detailsMap[a.id] || {})),
    [accounts, detailsMap, bucketOf],
  );
  const cashRows = useMemo(
    () => accounts.filter((a) => bucketOf(a) === 'cash').map(buildCashRow),
    [accounts, bucketOf],
  );
  const investmentAccounts = useMemo(
    () => accounts.filter((a) => bucketOf(a) === 'investment'),
    [accounts, bucketOf],
  );
  const investmentRows = useMemo(
    () => investmentAccounts.map(buildCashRow),
    [investmentAccounts],
  );

  const stats = useMemo(
    () => summarize(creditRows, cashRows, investmentAccounts),
    [creditRows, cashRows, investmentAccounts],
  );

  const health = useConnectionHealth(effectiveSummary?.connections);
  const brokenNames = useMemo(
    () => new Set(health.broken.map((i) => i.institution)),
    [health.broken],
  );

  // Optimistic-merge: apply the edit locally so the field snaps back with the
  // new value, then PUT in the background. On failure we revert and let the
  // user see the original value.
  const handleFieldUpdate = useCallback(async (accountId, field, value) => {
    const prev = detailsRef.current[accountId] || {};
    const next = { ...prev, [field]: value };
    detailsRef.current = { ...detailsRef.current, [accountId]: next };
    setDetailsMap(detailsRef.current);

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
      detailsRef.current = { ...detailsRef.current, [accountId]: prev };
      setDetailsMap(detailsRef.current);
    }
  }, []);

  // "Sync all" — force a balances refresh and, when brokerages are connected,
  // a SnapTrade pull. Failures surface in the connections strip, not per row.
  const handleSyncAll = useCallback(async () => {
    setSyncing(true);
    setSyncError(null);
    try {
      if (investmentAccounts.length > 0) {
        await syncSnapTrade().catch(() => { /* brokerage sync is best-effort */ });
      }
      await onRefresh?.();
    } catch {
      setSyncError('could not reach the backend.');
    } finally {
      setSyncing(false);
    }
  }, [investmentAccounts.length, onRefresh]);

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
    return <div className="finances-section" style={{ color: 'var(--red)' }}>{error}</div>;
  }

  return (
    <>
      <div className="acct-page-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleSyncAll}
          disabled={syncing}
        >
          <span className={`acct-sync-glyph${syncing ? ' is-spinning' : ''}`} aria-hidden="true">↺</span>
          {syncing ? 'Syncing…' : 'Sync all'}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => setAddingKind('credit')}
        >
          + Add account
        </button>
      </div>

      <ConnectionsStrip
        health={health}
        cacheFetchedAt={cacheFetchedAt}
        syncError={syncError}
        onRefresh={onRefresh}
        onManageConnections={onManageConnections}
      />

      {accounts.length === 0 && (
        <div className="finances-section" style={{ color: 'var(--text-muted)' }}>
          No accounts yet — connect a bank above, or add one manually below.
        </div>
      )}

      <AccountSection
        title="Credit cards & loans"
        count={countLabel(creditRows.length)}
        total={stats.totalOwed}
      >
        {creditRows.map((row) => (
          <AccountListRow
            key={row.id}
            row={row}
            needsReconnect={!row.manual && brokenNames.has(row.institution)}
            cacheFetchedAt={cacheFetchedAt}
            onUpdate={(field, value) => handleFieldUpdate(row.id, field, value)}
          />
        ))}
        <button type="button" className="acct-add-row" onClick={() => setAddingKind('credit')}>
          <span aria-hidden="true">+</span>
          <span>Add credit card or loan</span>
        </button>
      </AccountSection>

      <AccountSection
        title="Cash & savings"
        count={countLabel(cashRows.length)}
        total={stats.totalCash}
      >
        {cashRows.map((row) => (
          <SimpleAccountRow
            key={row.id}
            row={row}
            needsReconnect={!row.manual && brokenNames.has(row.institution)}
            cacheFetchedAt={cacheFetchedAt}
          />
        ))}
        <button type="button" className="acct-add-row" onClick={() => setAddingKind('depository')}>
          <span aria-hidden="true">+</span>
          <span>Add bank account or savings</span>
        </button>
      </AccountSection>

      <AccountSection
        title="Investments"
        count={countLabel(investmentRows.length)}
        total={investmentRows.length ? stats.totalInvestments : null}
        defaultOpen={investmentRows.length > 0}
      >
        {investmentRows.length === 0 ? (
          <div className="acct-empty-note">
            Connect a brokerage or retirement account to track it here.
          </div>
        ) : investmentRows.map((row) => (
          <SimpleAccountRow
            key={row.id}
            row={row}
            glyph="📈"
            needsReconnect={!row.manual && brokenNames.has(row.institution)}
            cacheFetchedAt={cacheFetchedAt}
          />
        ))}
      </AccountSection>

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

function countLabel(n) {
  if (n === 0) return 'none yet';
  return `${n} account${n === 1 ? '' : 's'}`;
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
