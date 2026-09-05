import React, {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { Link } from 'react-router-dom';
import { getCreditHealth } from '../../api/dashboard';
import { getAllAccountDetails } from '../../api/accountDetails';
import { updateAccountBalance, deleteManualAccount } from '../../api/balances';
import { classifyAccountBucket, isInstallmentLoan } from '../../utils/accountBucket';
import AccountSection from './accounts/AccountSection';
import AccountListRow from './accounts/AccountListRow';
import AddAccountModal from './accounts/AddAccountModal';
import useConnectionHealth from './accounts/useConnectionHealth';
import { buildCreditRow, summarize } from './accounts/accountMath';
import {
  createBalanceEditHandler, createDeleteManualHandler, createFieldUpdateHandler, countLabel,
} from './AccountsTab';
import PayoffPlanner from './PayoffPlanner';
import BorrowingPowerPanel from './BorrowingPowerPanel';
import CreditUtilizationCard from './cards/CreditUtilizationCard';
import Num from './Num';
import Icon from '../ui/Icon';

// Same convention as CreditUtilizationCard: the figure's colour carries the
// band, but the word beside it is what actually survives colour-blindness
// and greyscale print.
const STATUS_TEXT = {
  good: 'var(--status-good-text)',
  warn: 'var(--status-warn-text)',
  high: 'var(--status-bad-text)',
  unknown: 'var(--text-muted)',
};

const STATUS_WORD = { good: 'Good', warn: 'Watch', high: 'High' };

export default function DebtPage({ summary, summaryLoading, summaryError, onRefresh }) {
  const [creditHealth, setCreditHealth] = useState(null);
  const [creditHealthError, setCreditHealthError] = useState(null);

  // Bumped when an account is closed or reopened. Credit health is computed
  // server-side from the open accounts, so this page's summary bar and the
  // utilization card below both have to ask again — neither can derive the
  // change locally.
  const [healthKey, setHealthKey] = useState(0);

  useEffect(() => {
    getCreditHealth()
      .then((r) => setCreditHealth(r.data))
      .catch(() => setCreditHealthError('Could not load utilization.'));
  }, [healthKey]);

  // Account-detail metadata (limit, APR, statement/due day, opened-on) — the
  // same store AccountsTab reads, loaded here too since the drawer that edits
  // it now lives on this page.
  const [detailsMap, setDetailsMap] = useState({});
  const detailsRef = useRef({});
  const [detailsLoaded, setDetailsLoaded] = useState(false);
  const [addingKind, setAddingKind] = useState(null);
  const [localError, setLocalError] = useState(null);

  // Which row's drawer is expanded, and whether it was opened to set a limit.
  // The state lives here rather than in each row because the Credit Utilization
  // card below the list links at a specific card's limit field.
  const [openRow, setOpenRow] = useState(null);

  const openLimitFor = useCallback((accountId) => {
    setOpenRow({ id: accountId, focusLimit: true });
  }, []);

  useEffect(() => {
    if (!openRow) return;
    // The card that links here sits below the list, so opening the drawer is
    // not enough on its own — without this the row expands off-screen.
    document.getElementById(`acct-row-${openRow.id}`)
      ?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  }, [openRow]);

  useEffect(() => {
    getAllAccountDetails()
      .then((r) => { detailsRef.current = r.data || {}; setDetailsMap(detailsRef.current); })
      .catch(() => { detailsRef.current = {}; setDetailsMap({}); })
      .finally(() => setDetailsLoaded(true));
  }, []);

  const creditAccounts = useMemo(
    () => summary?.accounts?.filter((a) => classifyAccountBucket(a) === 'credit') ?? [],
    [summary],
  );

  const creditRows = useMemo(
    () => creditAccounts.map((a) => buildCreditRow(a, detailsMap[a.id] || {})),
    [creditAccounts, detailsMap],
  );

  // A closed card owes nothing and has no limit left, so it counts toward no
  // total here — but its transactions and history are still real, so it keeps
  // its row (and its drawer, which is how the closed date gets cleared again).
  const openRows = useMemo(() => creditRows.filter((r) => !r.closedOn), [creditRows]);
  const closedRows = useMemo(() => creditRows.filter((r) => r.closedOn), [creditRows]);

  // Cards and installment loans are different instruments — a loan has no
  // credit limit to be a percentage of, and a fixed schedule rather than a
  // balance you choose how fast to clear. The backend already separates them
  // for utilization; this is the same line drawn in the list.
  const cardRows = useMemo(
    () => openRows.filter((r) => !isInstallmentLoan(r.account)), [openRows],
  );
  const loanRows = useMemo(
    () => openRows.filter((r) => isInstallmentLoan(r.account)), [openRows],
  );

  const totalCards = useMemo(() => summarize(cardRows, []).totalOwed, [cardRows]);
  const totalLoans = useMemo(() => summarize(loanRows, []).totalOwed, [loanRows]);

  // The planner's own account list, not creditRows/creditAccounts above: a
  // paid-off card must stay in the list (creditAccounts, creditRows) so it
  // shows as "Paid off", but has nothing for the planner to schedule, so it
  // is filtered out here. Formerly FinancesPage's `creditAccounts` memo.
  // Installment loans are excluded as well: avalanche and snowball order a
  // queue of revolving balances you choose how fast to clear, and a mortgage
  // is neither — its minimum is not discretionary, and its size would swamp
  // every card in the ordering and in the payoff timeline.
  const payoffAccounts = useMemo(
    () => creditAccounts.filter((a) => (
      !a.closed_on
      && !isInstallmentLoan(a)
      && Math.abs(parseFloat(a.ledger) || 0) >= 0.005
    )),
    [creditAccounts],
  );

  const totalOwed = useMemo(() => summarize(openRows, []).totalOwed, [openRows]);

  const nextDue = useMemo(() => openRows
    .filter((row) => Number.isFinite(row.dueInDays))
    .reduce((soonest, cur) => (
      soonest === null || cur.dueInDays < soonest.dueInDays ? cur : soonest
    ), null) ?? null, [openRows]);

  const health = useConnectionHealth(summary?.connections);
  const brokenNames = useMemo(
    () => new Set(health.broken.map((i) => i.institution)),
    [health.broken],
  );

  const updateField = useMemo(
    () => createFieldUpdateHandler(detailsRef, setDetailsMap),
    [],
  );

  // Closing or reopening an account changes what the server counts, so unlike
  // every other drawer field it needs the summary re-fetched — the totals and
  // the utilization card are computed there, not here.
  const handleFieldUpdate = useCallback(async (accountId, field, value) => {
    await updateField(accountId, field, value);
    if (field === 'closed_on') {
      setHealthKey((k) => k + 1);
      await onRefresh?.();
    }
  }, [updateField, onRefresh]);

  const handleBalanceEdit = useCallback(
    (accountId, manual, payload) =>
      createBalanceEditHandler(updateAccountBalance, onRefresh)(accountId, manual, payload),
    [onRefresh],
  );

  const handleDeleteManual = useCallback(
    (accountId, manual, label) =>
      createDeleteManualHandler(deleteManualAccount, onRefresh, setLocalError)(accountId, manual, label),
    [onRefresh],
  );

  // One renderer for both sections — a closed card keeps the full row, drawer
  // included, because clearing its closed date is what reopens it.
  const renderRow = (row) => (
    <AccountListRow
      key={row.id}
      row={row}
      needsReconnect={!row.manual && brokenNames.has(row.institution)}
      cacheFetchedAt={summary?.cache_fetched_at}
      open={openRow?.id === row.id}
      focusLimit={openRow?.id === row.id && openRow.focusLimit}
      onOpenChange={(next) => setOpenRow(next ? { id: row.id, focusLimit: false } : null)}
      onUpdate={(field, value) => handleFieldUpdate(row.id, field, value)}
      onEditBalance={handleBalanceEdit}
      onDelete={handleDeleteManual}
    />
  );

  return (
    <>
      <div className="eh-topbar">
        <h1 className="eh-topbar-title">Debt</h1>
        {onRefresh && (
          <button
            type="button"
            className="ov-icon-btn"
            onClick={onRefresh}
            aria-label="Refresh"
            title="Refresh"
          >
            <Icon name="refresh" size={16} />
          </button>
        )}
      </div>
      <div className="eh-content">
        {summaryError && (
          <div className="eh-error" role="alert">{summaryError}</div>
        )}
        {localError && (
          <div className="eh-error" role="alert">{localError}</div>
        )}
        <section aria-label="Debt summary" style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Total owed</div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>
              {summaryLoading ? '—' : <Num value={totalOwed} />}
            </div>
          </div>

          {creditHealth && !creditHealthError
            && Number.isFinite(creditHealth.overall_utilization_pct) && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Utilization</div>
              <div style={{
                fontSize: 24, fontWeight: 700,
                color: STATUS_TEXT[creditHealth.overall_status] || 'inherit',
              }}>
                {creditHealth.overall_utilization_pct}%
                {STATUS_WORD[creditHealth.overall_status] && (
                  <span style={{ fontSize: 13, fontWeight: 600, marginLeft: 6 }}>
                    {STATUS_WORD[creditHealth.overall_status]}
                  </span>
                )}
              </div>
            </div>
          )}

          {nextDue && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Next payment due</div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>
                Day {nextDue.dueDay}
                <span style={{ fontSize: 13, fontWeight: 600, marginLeft: 6, color: 'var(--text-muted)' }}>
                  {nextDue.name}
                </span>
              </div>
            </div>
          )}
        </section>

        <AccountSection
          title="Credit cards"
          count={countLabel(cardRows.length)}
          total={totalCards}
        >
          {detailsLoaded ? cardRows.map(renderRow) : (
            <div className="acct-empty-note">Loading…</div>
          )}
          <button type="button" className="acct-add-row" onClick={() => setAddingKind('credit')}>
            <span aria-hidden="true">+</span>
            <span>Add credit card or loan</span>
          </button>
          {/* The button sits directly under a list of synced cards, so it reads
              as the way to add another one. It isn't — it creates a card you
              keep by hand. Connecting a real one lives on Accounts. */}
          <p className="acct-add-note">
            Adds a card you maintain yourself — the balance is whatever you type,
            and nothing updates it.{' '}
            <Link to="/accounts">Connect a bank or card</Link> to have one sync
            on its own.
          </p>
        </AccountSection>

        {loanRows.length > 0 && (
          <AccountSection
            title="Loans"
            count={countLabel(loanRows.length)}
            total={totalLoans}
          >
            {loanRows.map(renderRow)}
          </AccountSection>
        )}

        {closedRows.length > 0 && (
          <AccountSection
            title="Closed"
            count={countLabel(closedRows.length)}
            total={null}
            defaultOpen={false}
          >
            {closedRows.map(renderRow)}
          </AccountSection>
        )}

        {addingKind && (
          <AddAccountModal
            kind={addingKind}
            onClose={() => setAddingKind(null)}
            onSaved={() => onRefresh?.()}
          />
        )}

        <CreditUtilizationCard onSetLimit={openLimitFor} reloadKey={healthKey} />

        {/* A read-only view of the credit list above: it reads the same
            details this page already loaded rather than fetching its own copy,
            and the drawer up there is the only place those values are set. */}
        <PayoffPlanner creditAccounts={payoffAccounts} detailsMap={detailsMap} />
        <BorrowingPowerPanel />
      </div>
    </>
  );
}
