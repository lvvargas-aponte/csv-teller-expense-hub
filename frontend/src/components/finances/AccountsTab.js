import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Spin from '../ui/Spin';
import { getBalancesSummary, updateAccountBalance, deleteManualAccount } from '../../api/balances';
import {
  getAllAccountDetails,
  upsertAccountDetails,
} from '../../api/accountDetails';
import useSyncAll from '../../hooks/useSyncAll';
import ConnectionsStrip from './accounts/ConnectionsStrip';
import AccountSection from './accounts/AccountSection';
import AccountListRow from './accounts/AccountListRow';
import SimpleAccountRow from './accounts/SimpleAccountRow';
import AddAccountModal from './accounts/AddAccountModal';
import AssetRow from './accounts/AssetRow';
import useConnectionHealth from './accounts/useConnectionHealth';
import { buildCreditRow, buildCashRow, buildAssetRow, summarize } from './accounts/accountMath';
import { toYMD } from '../../utils/formatting';
import { classifyAccountBucket, loadInvestmentSubtypes } from '../../utils/accountBucket';

// AccountsTab — one summary bar, a connection-health strip, then collapsible
// account groups whose rows expand into an inline editor. Receives the cached
// `summary` from FinancesPage so we don't double-fetch balances; account-detail
// metadata is loaded locally and updated optimistically as the user edits.
export default function AccountsTab({
  summary, summaryLoading, summaryError, onRefresh,
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
  // Surfaces errors the sync hook can't: a manual-account delete failure, or
  // onRefresh itself rejecting (the hook lets that propagate — see useSyncAll).
  const [localError, setLocalError] = useState(null);

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

  const assetRows = useMemo(
    () => accounts
      .filter((a) => bucketOf(a) === 'real_asset')
      .map((a) => buildAssetRow({
        ...a,
        valuation_updated_on:
          detailsMap[a.id]?.valuation_updated_on ?? a.valuation_updated_on ?? null,
        secured_by_account_id:
          detailsMap[a.id]?.secured_by_account_id ?? a.secured_by_account_id ?? null,
      })),
    [accounts, detailsMap, bucketOf],
  );

  const stats = useMemo(
    () => summarize(creditRows, cashRows, investmentAccounts, assetRows),
    [creditRows, cashRows, investmentAccounts, assetRows],
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
      opened_on:       next.opened_on || null,
      valuation_updated_on: next.valuation_updated_on || null,
      secured_by_account_id: next.secured_by_account_id || null,
      tax_treatment:   next.tax_treatment || null,
      notes:           next.notes ?? '',
    };
    try {
      await upsertAccountDetails(accountId, payload);
    } catch {
      detailsRef.current = { ...detailsRef.current, [accountId]: prev };
      setDetailsMap(detailsRef.current);
    }
  }, []);

  // Revaluing a real asset is the only thing that moves its worth — no
  // transaction does, and nothing estimates it. The new figure and the date
  // it was true are written together so the row can never show a fresh value
  // under a stale date.
  const handleAssetRevalue = useCallback(async (accountId, value) => {
    if (value === null || value === undefined) return;
    await updateAccountBalance(accountId, { available: value, ledger: value });
    await handleFieldUpdate(accountId, 'valuation_updated_on', toYMD(new Date()));
    await onRefresh?.();
  }, [handleFieldUpdate, onRefresh]);

  // A synced balance comes from the bank; only manual accounts are editable
  // here. The row hides the control (first line of defence), and each row
  // reports its own `manual` flag on every call — the handler bails if it is
  // not manual, so a stray call for a synced account (a bypassed row, a
  // future caller) is a no-op even if the control were somehow shown. The
  // bail check lives in a standalone factory (below) so it can be exercised
  // directly in a test, independent of any row's rendering.
  const handleBalanceEdit = useCallback(
    createBalanceEditHandler(updateAccountBalance, onRefresh),
    [onRefresh],
  );

  const handleDeleteManual = useCallback(
    createDeleteManualHandler(deleteManualAccount, onRefresh, setLocalError),
    [onRefresh],
  );

  // "Sync all" — the one hook shared with Settings' former connections pane,
  // so a bank pull and a brokerage pull always mean the same thing everywhere.
  const { syncAll, syncing, syncError } = useSyncAll({ onRefresh });

  // syncAll() lets onRefresh's rejection propagate uncaught (see useSyncAll) —
  // catch it here so a failing refresh still lands as a visible message
  // instead of an unhandled rejection.
  const handleSyncAllClick = useCallback(() => {
    setLocalError(null);
    syncAll().catch(() => setLocalError('could not reach the backend.'));
  }, [syncAll]);

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
          onClick={handleSyncAllClick}
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
        summary={effectiveSummary}
        cacheFetchedAt={cacheFetchedAt}
        syncing={syncing}
        syncError={localError || syncError}
        onRefresh={onRefresh}
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
            onEditBalance={handleBalanceEdit}
            onDelete={handleDeleteManual}
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
            onEditBalance={handleBalanceEdit}
            onDelete={handleDeleteManual}
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
        ) : (
          <Link to="/invest" className="acct-add-row">
            <span>
              {countLabel(investmentRows.length)} — view in Invest
            </span>
          </Link>
        )}
      </AccountSection>

      <AccountSection
        title="Property & vehicles"
        count={countLabel(assetRows.length)}
        total={assetRows.length ? stats.totalAssets : null}
        defaultOpen={assetRows.length > 0}
      >
        {assetRows.length === 0 ? (
          <div className="acct-empty-note">
            Add a home or a vehicle to count it toward net worth. You set the
            value — nothing here estimates it.
          </div>
        ) : assetRows.map((row) => (
          <AssetRow
            key={row.id}
            row={row}
            creditAccounts={creditRows}
            onValueChange={(v) => handleAssetRevalue(row.id, v)}
            onSecuredByChange={(v) => handleFieldUpdate(row.id, 'secured_by_account_id', v)}
          />
        ))}
        <button type="button" className="acct-add-row" onClick={() => setAddingKind('asset')}>
          <span aria-hidden="true">+</span>
          <span>Add property or vehicle</span>
        </button>
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

// Exported so the manual-only bail check can be exercised directly in a test
// (called with `manual: false`) without needing to render a row and click
// through it — the row's own gating is a separate, independent check.
export function createBalanceEditHandler(updateBalance, onRefresh) {
  return async (accountId, manual, { available, ledger }) => {
    if (!manual) return;
    await updateBalance(accountId, { available, ledger });
    await onRefresh?.();
  };
}

export function createDeleteManualHandler(deleteAccount, onRefresh, onError) {
  return async (accountId, manual, label) => {
    if (!manual) return;
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Remove ${label}? Its transaction history is kept.`)) return;
    try {
      await deleteAccount(accountId);
      await onRefresh?.();
    } catch {
      onError?.('Could not remove the account — please try again.');
    }
  };
}
