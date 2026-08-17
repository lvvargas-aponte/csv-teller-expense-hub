import React from 'react';

import Num from '../Num';

const TIER_ICON = {
  employer_match: '🎁',
  emergency_fund: '🛟',
  high_interest_debt: '🔥',
  tax_advantaged: '🛡️',
  property_fund: '🏠',
  taxable_investing: '📈',
  extra_mortgage_principal: '🏦',
};

/**
 * One tier of the split.
 *
 * The benefit line is deliberately labelled guaranteed or not. Paying a 24%
 * card and expecting 7% from the market are not the same kind of claim, and
 * a UI that renders both as plain numbers quietly says they are.
 */
function AllocationRow({ row, total }) {
  const share = total > 0 ? (row.amount / total) * 100 : 0;
  const benefit = row.quantified_benefit;

  return (
    <li className="alloc-row">
      <div className="alloc-row-head">
        <span className="alloc-row-icon" aria-hidden="true">
          {TIER_ICON[row.key] || '•'}
        </span>
        <span className="alloc-row-label">{row.label}</span>
        <span className="alloc-row-amount"><Num value={row.amount} /></span>
      </div>

      <div className="alloc-bar" aria-hidden="true">
        <div className="alloc-bar-fill" style={{ width: `${share}%` }} />
      </div>

      <p className="alloc-row-why">{row.rationale}</p>

      {benefit && benefit.value !== null && benefit.value !== undefined && (
        <p className={`alloc-benefit${benefit.guaranteed ? ' alloc-benefit--sure' : ''}`}>
          <strong>{benefit.guaranteed ? 'Guaranteed' : 'Projected'}:</strong>
          {' '}
          {benefit.label} — <Num value={benefit.value} />
          {benefit.horizon ? ` (${benefit.horizon})` : ''}
          {!benefit.guaranteed && ' · not a promise; markets fall as well as rise'}
        </p>
      )}
    </li>
  );
}

export default function WaterfallList({ plan }) {
  const { allocations = [], skipped = [], questions = [], caveats = [] } = plan;
  const total = allocations.reduce((sum, a) => sum + a.amount, 0);

  return (
    <>
      {questions.length > 0 && (
        <section className="ov-card alloc-questions">
          <div className="ov-card-header">
            <div className="ov-card-title">Answer these and the split changes</div>
            <div className="ov-card-subtitle">
              Rather than assume, the waterfall asks. Each unanswered question
              could move money to a higher tier.
            </div>
          </div>
          <div className="ov-card-body">
            {questions.map((q) => (
              <div className="alloc-question" key={q.key}>
                <div className="alloc-question-text">{q.question}</div>
                <div className="alloc-question-why">{q.why}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="ov-card">
        <div className="ov-card-header">
          <div className="ov-card-title">Where it goes</div>
          <div className="ov-card-subtitle">
            In order. Each tier takes what it needs and passes the rest down.
          </div>
        </div>
        <div className="ov-card-body">
          <ol className="alloc-list">
            {allocations.map((row) => (
              <AllocationRow key={`${row.tier}-${row.key}-${row.label}`} row={row} total={total} />
            ))}
          </ol>
        </div>
      </section>

      {skipped.length > 0 && (
        <section className="ov-card">
          <div className="ov-card-header">
            <div className="ov-card-title">What it skipped, and why</div>
            <div className="ov-card-subtitle">
              &ldquo;Why not the mortgage?&rdquo; is the question worth
              answering, so it is answered here rather than left out.
            </div>
          </div>
          <div className="ov-card-body">
            {skipped.map((s) => (
              <div className="alloc-skip" key={`${s.tier}-${s.key}`}>
                <span className="alloc-skip-label">{s.label}</span>
                <span className="alloc-skip-reason">{s.reason}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {caveats.length > 0 && (
        <section className="ov-card alloc-caveats">
          <div className="ov-card-header">
            <div className="ov-card-title">Where this answer is soft</div>
          </div>
          <div className="ov-card-body">
            <ul>
              {caveats.map((c) => <li key={c}>{c}</li>)}
            </ul>
          </div>
        </section>
      )}
    </>
  );
}
