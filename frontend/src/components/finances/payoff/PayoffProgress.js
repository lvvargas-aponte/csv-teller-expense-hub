import React, { useCallback, useEffect, useState } from 'react';
import { getDebtPayments } from '../../../api/accountDetails';
import { fmt$, fmtDate } from '../../../utils/formatting';

// Where a payment was seen. "both" is the happy case — the funding account's
// debit and the card's credit reconciled to one real payment.
const SOURCE_LABEL = {
  both:    { text: 'matched',   title: 'Seen on both the funding account and the card' },
  funding: { text: 'sent',      title: 'Seen leaving the funding account, not yet posted on the card' },
  account: { text: 'posted',    title: 'Posted on the card — no matching debit found on the funding account' },
};

/**
 * Progress against the recorded starting balance, plus the transactions that
 * got it there. Only rendered for rows backed by a real account: a hand-typed
 * debt has no transactions to match against.
 *
 * `detailsVersion` is the refetch trigger — it ticks once per successful save,
 * so the panel updates after the server has the new starting balance or
 * funding account, and not once per keystroke on the way there.
 */
export default function PayoffProgress({ row, detailsVersion }) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const { accountId } = row;

  const load = useCallback(() => {
    if (!accountId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDebtPayments(accountId)
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setError('Could not load payments for this debt.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [accountId]);

  useEffect(() => load(), [load, detailsVersion]);

  if (!accountId) return null;
  if (loading && !data) return <div className="ov-payoff-progress-empty">Loading payments…</div>;
  if (error) return <div className="ov-payoff-progress-empty">{error}</div>;
  if (!data) return null;

  const { start_balance: start, current_balance: current, paid_down: paid, percent_paid: pct } = data;
  const payments = data.payments || [];
  // Payments matched but not reflected in the gap between the two balances —
  // interest and fees pushing the other way, usually.
  const unexplained = (start !== null && paid !== null)
    ? Math.round((data.total_payments - paid) * 100) / 100
    : 0;

  return (
    <div className="ov-payoff-progress">
      {start !== null ? (
        <>
          <div className="ov-payoff-progress-head">
            <span>
              <span className="ov-payoff-progress-from">{fmt$(start)}</span>
              {' → '}
              <strong>{fmt$(current)}</strong>
            </span>
            <span className={paid > 0 ? 'ov-payoff-progress-paid' : 'ov-payoff-progress-flat'}>
              {paid > 0 ? `${fmt$(paid)} paid off` : 'no progress yet'}
              {pct !== null && paid > 0 ? ` · ${pct}%` : ''}
            </span>
          </div>
          <div className="ov-payoff-progress-bar">
            <div
              className="ov-payoff-progress-fill"
              style={{ width: `${Math.max(0, Math.min(100, pct || 0))}%` }}
            />
          </div>
        </>
      ) : (
        <div className="ov-payoff-progress-empty">
          Set a starting balance above to track how far this debt has moved.
        </div>
      )}

      {payments.length > 0 ? (
        <>
          <div className="ov-payoff-progress-label">
            {payments.length} payment{payments.length === 1 ? '' : 's'} ·{' '}
            {fmt$(data.total_payments)} total
          </div>
          <ul className="ov-payment-list">
            {payments.map((p) => {
              const badge = SOURCE_LABEL[p.source] || SOURCE_LABEL.account;
              return (
                <li key={p.transaction_id} className="ov-payment-row">
                  <span className="ov-payment-date">{fmtDate(p.date)}</span>
                  <span className="ov-payment-desc" title={p.description}>
                    {p.institution ? `${p.institution} · ` : ''}{p.description}
                  </span>
                  <span className={`ov-payment-badge ov-payment-badge--${p.source}`} title={badge.title}>
                    {badge.text}
                  </span>
                  <span className="ov-payment-amount">{fmt$(p.amount)}</span>
                </li>
              );
            })}
          </ul>
          {start !== null && Math.abs(unexplained) >= 1 && (
            <div className="ov-payoff-progress-note">
              {unexplained > 0
                ? `${fmt$(unexplained)} of payments isn't reflected in the balance drop — interest and fees pushing back the other way.`
                : `The balance fell ${fmt$(-unexplained)} more than the payments found here account for.`}
            </div>
          )}
        </>
      ) : (
        <div className="ov-payoff-progress-empty">
          No payments matched yet.{' '}
          {data.payment_account_id
            ? 'Payments show up here once they post.'
            : 'Pick the account you pay this from to catch the outgoing side too.'}
        </div>
      )}
    </div>
  );
}
