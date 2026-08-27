import React, {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { getCreditHealth } from '../../api/dashboard';
import { getAllAccountDetails } from '../../api/accountDetails';
import { updateAccountBalance, deleteManualAccount } from '../../api/balances';
import { classifyAccountBucket } from '../../utils/accountBucket';
import { daysUntilNextDue } from './accounts/dueDate';
import AccountSection from './accounts/AccountSection';
import AccountListRow from './accounts/AccountListRow';
import AddAccountModal from './accounts/AddAccountModal';
import useConnectionHealth from './accounts/useConnectionHealth';
import { buildCreditRow, summarize } from './accounts/accountMath';
import {
  createBalanceEditHandler, createDeleteManualHandler, createFieldUpdateHandler, countLabel,
} from './AccountsTab';
import Num from './Num';

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

  useEffect(() => {
    getCreditHealth()
      .then((r) => setCreditHealth(r.data))
      .catch(() => setCreditHealthError('Could not load utilization.'));
  }, []);

  // Account-detail metadata (limit, APR, statement/due day, opened-on) — the
  // same store AccountsTab reads, loaded here too since the drawer that edits
  // it now lives on this page.
  const [detailsMap, setDetailsMap] = useState({});
  const detailsRef = useRef({});
  const [detailsLoaded, setDetailsLoaded] = useState(false);
  const [addingKind, setAddingKind] = useState(null);
  const [localError, setLocalError] = useState(null);

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

  const totalOwed = useMemo(() => summarize(creditRows, []).totalOwed, [creditRows]);

  const nextDue = useMemo(() => creditAccounts
    .map((a) => ({ account: a, days: daysUntilNextDue(a.due_day) }))
    .filter(({ days }) => days !== null && days !== undefined)
    .reduce((soonest, cur) => (soonest === null || cur.days < soonest.days ? cur : soonest), null)
    ?.account ?? null, [creditAccounts]);

  const health = useConnectionHealth(summary?.connections);
  const brokenNames = useMemo(
    () => new Set(health.broken.map((i) => i.institution)),
    [health.broken],
  );

  const handleFieldUpdate = useMemo(
    () => createFieldUpdateHandler(detailsRef, setDetailsMap),
    [],
  );

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

  return (
    <>
      <div className="eh-topbar">
        <h1 className="eh-topbar-title">Debt</h1>
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

          {creditHealth && !creditHealthError && (
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
                Day {nextDue.due_day}
                <span style={{ fontSize: 13, fontWeight: 600, marginLeft: 6, color: 'var(--text-muted)' }}>
                  {nextDue.name}
                </span>
              </div>
            </div>
          )}
        </section>

        <AccountSection
          title="Credit cards & loans"
          count={countLabel(creditRows.length)}
          total={totalOwed}
        >
          {detailsLoaded ? creditRows.map((row) => (
            <AccountListRow
              key={row.id}
              row={row}
              needsReconnect={!row.manual && brokenNames.has(row.institution)}
              cacheFetchedAt={summary?.cache_fetched_at}
              onUpdate={(field, value) => handleFieldUpdate(row.id, field, value)}
              onEditBalance={handleBalanceEdit}
              onDelete={handleDeleteManual}
            />
          )) : (
            <div className="acct-empty-note">Loading…</div>
          )}
          <button type="button" className="acct-add-row" onClick={() => setAddingKind('credit')}>
            <span aria-hidden="true">+</span>
            <span>Add credit card or loan</span>
          </button>
        </AccountSection>

        {addingKind && (
          <AddAccountModal
            kind={addingKind}
            onClose={() => setAddingKind(null)}
            onSaved={() => onRefresh?.()}
          />
        )}

        {onRefresh && (
          <button type="button" onClick={onRefresh} style={{
            background: 'none', border: 'none', padding: 0, font: 'inherit',
            color: 'var(--accent)', textDecoration: 'underline', cursor: 'pointer',
          }}>
            Refresh
          </button>
        )}
      </div>
    </>
  );
}
