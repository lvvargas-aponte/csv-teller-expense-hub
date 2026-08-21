/**
 * The retirement goal — one number to aim at, and how close the portfolio is.
 *
 * The target is the projection's own feasibility test solved for the balance,
 * so it can never disagree with the retirement year shown above it. It is a
 * today's-dollars figure on purpose: a target you can compare against the
 * balance you actually hold is worth more than a more precise one you can't.
 */
import React from 'react';

import Num from '../Num';

export default function GoalCard({ goal }) {
  if (!goal) return null;

  const {
    target, current_balance: balance, gap, funded_pct: funded,
    annual_spending: spending, multiple, fully_funded: done,
    rental_offset: rental, social_security_offset: ss,
    social_security_pending: ssPending,
    social_security_start_age: ssAge,
    fund_from_investments: fromInvestments,
    effective_withdrawal_rate_pct: rate,
    gross_target: gross,
    after_payoff: afterPayoff,
  } = goal;

  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">Your retirement goal</div>
        <div className="ov-card-subtitle">
          What you&apos;d need invested to cover today&apos;s spending, in
          today&apos;s dollars. Every mortgage payoff lowers it.
        </div>
      </div>

      <div className="ov-card-body">
        <div className="ret-goal-headline">
          <div className="ret-goal-target">
            <div className="ret-goal-target-label">
              {afterPayoff ? 'Target while the mortgages run' : 'Target'}
            </div>
            <div className="ret-goal-target-value"><Num value={target} /></div>
            <div className="ret-goal-target-sub">
              {multiple}× your annual spending
            </div>
          </div>
          <div className="ret-goal-status">
            <div className="ret-goal-pct">{funded}%</div>
            <div className="ret-goal-status-sub">
              {done
                ? 'funded — the portfolio covers it'
                : <>funded · <Num value={gap} /> to go</>}
            </div>
          </div>
        </div>

        <div
          className="ret-goal-bar"
          role="progressbar"
          aria-valuenow={funded}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Progress toward the retirement goal"
        >
          <div
            className={`ret-goal-bar-fill ${done ? 'ret-goal-bar-fill--done' : ''}`}
            style={{ width: `${Math.max(funded, 0.5)}%` }}
          />
        </div>

        <div className="ret-goal-math">
          <div className="prop-row">
            <span className="prop-row-label">Spending to cover</span>
            <span className="prop-row-value"><Num value={spending} />/yr</span>
          </div>
          {rental > 0 && (
            <div className="prop-row">
              <span
                className="prop-row-label"
                title="Net of today's debt service and tax. This rises as mortgages finish."
              >
                Less rental profit
              </span>
              <span className="prop-row-value neg">−<Num value={rental} />/yr</span>
            </div>
          )}
          {ss > 0 && (
            <div className="prop-row">
              <span className="prop-row-label">Less Social Security</span>
              <span className="prop-row-value neg">−<Num value={ss} />/yr</span>
            </div>
          )}
          <div className="prop-row prop-row--emphasis">
            <span className="prop-row-label">Investments must fund</span>
            <span className="prop-row-value">
              <Num value={fromInvestments} />/yr
            </span>
          </div>
          <div className="prop-row">
            <span
              className="prop-row-label"
              title="Your safe withdrawal rate, after tax on withdrawals."
            >
              At {rate}% a year, that needs
            </span>
            <span className="prop-row-value"><Num value={target} /></span>
          </div>
          <div className="prop-row">
            <span className="prop-row-label">You have invested</span>
            <span className="prop-row-value"><Num value={balance} /></span>
          </div>
        </div>

        {afterPayoff && (
          <div className="ret-goal-payoff">
            <div className="ret-goal-payoff-head">
              <div>
                <div className="ret-goal-payoff-label">
                  Once the mortgages are done · {afterPayoff.final_payoff_year}
                  {afterPayoff.final_payoff_age
                    ? `, age ${afterPayoff.final_payoff_age}` : ''}
                </div>
                <div className="ret-goal-payoff-value">
                  <Num value={afterPayoff.target} />
                </div>
              </div>
              <div className="ret-goal-payoff-delta">
                −<Num value={afterPayoff.reduction} />
              </div>
            </div>
            <p className="ret-goal-payoff-body">
              You keep collecting rent after you stop working — but right now
              most of it goes to the banks. With the debt service gone, the
              properties pay you <Num value={afterPayoff.rental_offset} />/yr
              instead of <Num value={rental} />, leaving only{' '}
              <Num value={afterPayoff.fund_from_investments} />/yr for the
              portfolio to cover. Same spending, same rents — the tenants just
              finished buying the properties.
            </p>
          </div>
        )}

        {ssPending && (
          <div className="ret-goal-note">
            Social Security isn&apos;t subtracted here — it starts at age {ssAge}.
            The target drops once it begins.
          </div>
        )}
        {rental > 0 && (
          <div className="ret-goal-note">
            Without the rentals the same spending would need{' '}
            <Num value={gross} />. The properties are doing that much of the work.
          </div>
        )}
      </div>
    </section>
  );
}
