import React from 'react';

import Num from '../Num';
import { fmt$ } from '../../../utils/formatting';

const PACE_COPY = {
  over: 'Ahead of pace for the month',
  on_track: 'Tracking with the month',
  under: 'Behind pace — room to spare',
};

/**
 * The number this whole page exists to show.
 *
 * `delta` is yesterday's figure so the change reads as a consequence of
 * what was spent, not as an unexplained fluctuation.
 */
export default function SafeToSpendCard({ data, yesterday }) {
  if (!data) return null;

  if (!data.available) {
    return (
      <section className="sts sts--unavailable">
        <div className="sts-label">Safe to spend today</div>
        <div className="sts-empty-title">Not enough to go on yet</div>
        <div className="sts-empty-sub">{data.detail}</div>
      </section>
    );
  }

  const delta = yesterday && yesterday.available
    ? data.daily_safe_to_spend - yesterday.daily_safe_to_spend
    : null;

  return (
    <section className={`sts${data.over_budget ? ' sts--over' : ''}`}>
      <div className="sts-label">Safe to spend today</div>

      <div className="sts-amount">
        <Num value={data.daily_safe_to_spend} />
      </div>

      <div className="sts-meta">
        <span>{fmt$(data.weekly_safe_to_spend)} for the next
          {' '}{Math.min(7, data.period.days_remaining)} days</span>
        <span className="sts-dot" aria-hidden="true">·</span>
        <span>{data.period.days_remaining} days left in the month</span>
      </div>

      {data.over_budget ? (
        <div className="sts-alert">
          You&apos;re {fmt$(data.overspend_amount)} past the month&apos;s plan.
          Holding at zero from here keeps the rest of your commitments intact.
        </div>
      ) : (
        <div className={`sts-pace sts-pace--${data.pace}`}>
          {PACE_COPY[data.pace]}
          {delta !== null && Math.abs(delta) >= 0.01 && (
            <span className="sts-delta">
              {delta < 0 ? '▼' : '▲'} {fmt$(Math.abs(delta))} vs. yesterday
            </span>
          )}
        </div>
      )}
    </section>
  );
}
