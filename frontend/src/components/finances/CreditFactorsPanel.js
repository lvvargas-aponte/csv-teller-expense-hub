import React, { useEffect, useState } from 'react';
import Spin from '../ui/Spin';
import { fmt$, fmtDate } from '../../utils/formatting';
import { getCreditFactors } from '../../api/dashboard';

// The factors a credit score is built from — and deliberately no score.
// See backend/credit_factors.py for why: a score is a model fit to a bureau
// file, and this app can see roughly a third of its inputs. No composite
// number, no gauge, no letter grade, no "estimated range" — any of those
// become the thing users quote in a real borrowing decision.

const GOOD = 'var(--status-good-text)';
const WARN = 'var(--status-warn-text)';
const BAD = 'var(--status-bad-text)';

function utilizationColor(pct) {
  if (pct === null || pct === undefined) return 'var(--text-muted)';
  if (pct <= 10) return GOOD;
  if (pct <= 30) return WARN;
  return BAD;
}

function pct(value) {
  return (value === null || value === undefined) ? '—' : `${value}%`;
}

function Factor({ label, weight, value, valueColor, children }) {
  return (
    <div className="cf-factor" role="group" aria-label={label}>
      <div className="cf-factor-head">
        <span className="cf-factor-label">{label}</span>
        <span className="cf-factor-weight">{weight}</span>
      </div>
      {value !== undefined && (
        <div className="cf-factor-value" style={{ color: valueColor }}>{value}</div>
      )}
      <div className="cf-factor-body">{children}</div>
    </div>
  );
}

export default function CreditFactorsPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCreditFactors()
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load credit factors.'));
  }, []);

  if (error) return <div className="ov-card"><div className="ov-error">{error}</div></div>;
  if (!data) {
    return (
      <div className="ov-card">
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <Spin /> Loading credit factors…
        </div>
      </div>
    );
  }

  const util = data.utilization || {};
  const timeliness = data.payment_timeliness || {};
  const history = data.history || {};
  const cards = util.cards || [];

  return (
    <div className="ov-card">
      <div className="ov-card-header">
        <div>
          <h2 className="ov-card-title">Credit factors</h2>
          <div className="ov-card-subtitle">{data.coverage_note}</div>
        </div>
      </div>

      <div className="ov-card-body">
        <p className="cf-framing">
          These are the factors your credit score is built from, measured on the
          accounts you&apos;ve connected here. We don&apos;t estimate a score — for your
          real one, check your card issuer or annualcreditreport.com. It&apos;s free.
        </p>

        <div className="cf-factors">
          <Factor
            label="Credit utilization"
            weight="~30% of a score"
            value={pct(util.overall_reported_pct)}
            valueColor={utilizationColor(util.overall_reported_pct)}
          >
            <div className="cf-note">
              That is what your <strong>statement</strong> balances reported.
              Today you are at {pct(util.overall_current_pct)} — the gap is the
              part most people never see, because the bureau reads the card on
              its statement date, not after you pay it.
            </div>
            <div className="cf-cards">
              {cards.map((c) => (
                <div key={c.account_id} className="cf-card-row">
                  <div className="cf-card-name">{c.name}</div>
                  {c.reported_pct === null || c.reported_pct === undefined ? (
                    <div className="cf-note">
                      No statement-date balance recorded yet — it appears after a
                      sync lands near day {c.statement_day || '—'}.
                      Today: {pct(c.current_pct)}.
                    </div>
                  ) : (
                    <div className="cf-note">
                      <span style={{ color: utilizationColor(c.reported_pct), fontWeight: 600 }}>
                        {pct(c.reported_pct)} reported
                      </span>
                      {' '}on {fmtDate(c.as_of)} ({fmt$(c.reported_balance)} of {fmt$(c.limit)})
                      {' · '}{pct(c.current_pct)} today
                    </div>
                  )}
                  {c.lever && (
                    <div className="cf-lever">
                      Pay {fmt$(c.lever.amount)}
                      {c.lever.pay_by ? ` by ${fmtDate(c.lever.pay_by)}` : ''}
                      {' '}to report {c.lever.gets_to_pct}%
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Factor>

          <Factor
            label="Payment history"
            weight="~35% of a score"
            value={`${timeliness.cycles_with_payment_before_due ?? 0} / ${timeliness.cycles_observed ?? 0}`}
          >
            <div className="cf-note">
              {timeliness.cycles_with_payment_before_due ?? 0} of{' '}
              {timeliness.cycles_observed ?? 0} observed cycles paid before the due
              date on your connected accounts. A missed payment reported to a
              bureau is not visible here, and neither is any account you
              haven&apos;t connected.
            </div>
          </Factor>

          <Factor
            label="Length of history"
            weight="~15% of a score"
            value={
              history.average_age_months === null || history.average_age_months === undefined
                ? '—'
                : `${Math.round(history.average_age_months / 12 * 10) / 10} yrs avg`
            }
          >
            <div className="cf-note">
              {history.oldest_account_months
                ? `Oldest connected account: ${Math.round(history.oldest_account_months / 12 * 10) / 10} years.`
                : 'No open dates recorded yet.'}
              {history.accounts_missing_opened_on > 0 && (
                <>
                  {' '}
                  {history.accounts_missing_opened_on} account
                  {history.accounts_missing_opened_on === 1 ? '' : 's'} have no open
                  date — add it on the Accounts tab to include them.
                </>
              )}
            </div>
          </Factor>

          <Factor
            label="New credit"
            weight="~10% of a score"
            value={String(data.new_credit?.opened_last_12_months ?? 0)}
          >
            <div className="cf-note">
              Accounts opened in the last 12 months. Hard inquiries also count
              toward this factor and are not visible to this app.
            </div>
          </Factor>

          <Factor
            label="Credit mix"
            weight="~10% of a score"
            value={`${data.mix?.revolving ?? 0} / ${data.mix?.installment ?? 0}`}
          >
            <div className="cf-note">
              {data.mix?.revolving ?? 0} revolving, {data.mix?.installment ?? 0}{' '}
              installment among your connected accounts.
            </div>
          </Factor>
        </div>
      </div>
    </div>
  );
}
