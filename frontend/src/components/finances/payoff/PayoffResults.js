import React from 'react';
import { fmt$, fmtDate } from '../../../utils/formatting';
import { fmtMonths } from './helpers';

export default function PayoffResults({ results, strategy, totalMonths, totalPaid, rows = [], hasSecured = false }) {
  if (!results || !results.accounts || results.accounts.length === 0) return null;

  const promoWarnings = results.accounts.filter((a) => a.promo_expired_before_payoff);

  return (
    <div className="ov-payoff-result">
      <div className="ov-payoff-grid">
        <div>
          {/* Only the unsecured queue is simulated, so claiming "debt-free"
              would be wrong for anyone still carrying a mortgage. */}
          <div className="ov-payoff-stat-label">{hasSecured ? 'Cards clear in' : 'Debt-free in'}</div>
          <div className="ov-payoff-stat-value">{fmtMonths(totalMonths)}</div>
          <div className="ov-payoff-stat-sub">
            {totalMonths} monthly payments{hasSecured ? ' · loans excluded' : ''}
          </div>
        </div>
        <div>
          <div className="ov-payoff-stat-label">Total interest</div>
          <div className="ov-payoff-stat-value ov-payoff-stat-value--red">
            {fmt$(results.grand_total_interest ?? 0)}
          </div>
          <div className="ov-payoff-stat-sub">cost of carrying debt</div>
        </div>
        <div>
          <div className="ov-payoff-stat-label">Total paid</div>
          <div className="ov-payoff-stat-value">{fmt$(totalPaid)}</div>
          <div className="ov-payoff-stat-sub">principal + interest</div>
        </div>
      </div>

      <div className="ov-payoff-schedule">
        <div className="ov-payoff-schedule-title">
          Payoff order ({strategy === 'avalanche' ? 'highest APR first' : 'lowest balance first'})
        </div>
        {results.accounts
          .filter((a) => (parseFloat(a.payoff_months) || 0) > 0)
          .map((a, i) => {
            const months = parseFloat(a.payoff_months) || 0;
            const pct = totalMonths > 0 ? Math.min(100, (months / totalMonths) * 100) : 0;
            const color = i === 0 ? '#ef4444' : i === 1 ? '#f59e0b' : '#059669';
            return (
              <div key={i} className="ov-payoff-debt-item">
                <span className="ov-order-badge" style={{ background: color }}>{i + 1}</span>
                <div className="ov-payoff-debt-name">{a.name || `Debt ${i + 1}`}</div>
                <div className="ov-payoff-bar-wrap">
                  <div
                    className="ov-payoff-bar"
                    style={{ width: `${pct}%`, background: color, opacity: 0.7 }}
                  />
                </div>
                <div className="ov-payoff-debt-months">{fmtMonths(months)}</div>
              </div>
            );
          })}
      </div>

      {(results.interest_saved_vs_minimums !== null && results.interest_saved_vs_minimums !== undefined) && results.interest_saved_vs_minimums > 0 && (
        <div style={{
          marginTop: 14, fontSize: 12, color: '#059669', fontWeight: 600,
        }}>
          You save {fmt$(results.interest_saved_vs_minimums)} vs. paying minimums only.
        </div>
      )}

      {promoWarnings.map((a) => {
        const row = rows.find((r) => r.name === a.name);
        return (
          <div key={a.name} className="ov-promo-warning">
            ⚠️ {a.name}{row?.promoApr ? `'s ${row.promoApr}% promo` : "'s promo"}
            {row?.promoExpires ? ` ends ${fmtDate(row.promoExpires)}` : ' expires'} — it won't
            be paid off by then, so deferred interest may apply retroactively per the card's terms.
          </div>
        );
      })}
    </div>
  );
}
