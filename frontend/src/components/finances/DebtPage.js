import React, { useEffect, useMemo, useState } from 'react';
import { getCreditHealth } from '../../api/dashboard';
import { classifyAccountBucket } from '../../utils/accountBucket';
import { daysUntilNextDue } from './accounts/dueDate';
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

  const creditAccounts = useMemo(
    () => summary?.accounts?.filter((a) => classifyAccountBucket(a) === 'credit') ?? [],
    [summary],
  );

  const totalOwed = useMemo(
    () => creditAccounts.reduce((sum, a) => sum + (parseFloat(a.ledger) || 0), 0),
    [creditAccounts],
  );

  const nextDue = useMemo(() => {
    return creditAccounts
      .map((a) => ({ account: a, days: daysUntilNextDue(a.due_day) }))
      .filter(({ days }) => days !== null && days !== undefined)
      .reduce((soonest, cur) => (soonest === null || cur.days < soonest.days ? cur : soonest), null)
      ?.account ?? null;
  }, [creditAccounts]);

  return (
    <>
      <div className="eh-topbar">
        <h1 className="eh-topbar-title">Debt</h1>
      </div>
      <div className="eh-content">
        {summaryError && (
          <div className="eh-error" role="alert">{summaryError}</div>
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
