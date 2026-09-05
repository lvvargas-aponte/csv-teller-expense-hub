import React, { useEffect, useState } from 'react';
import Spin from '../ui/Spin';
import { fmt$ } from '../../utils/formatting';
import { getBorrowingPower } from '../../api/dashboard';

// What a lender reads, as opposed to what a score reports.
//
// This replaced a panel framed around FICO's five factors, which could
// honestly measure one of them — payment history needs delinquencies no bank
// feed carries, length of history and new credit need an open date on every
// account, and credit mix is a count nobody can act on. Four of five rendered
// as placeholders.
//
// Debt-to-income is the trade. It is not a score factor at all — no bureau
// holds an income figure — but it is what actually gates a mortgage, and this
// app can compute it precisely because it has the bank feed a credit monitor
// does not. Still no score: see the note in the header.

function dtiColor(pct, ceiling, comfortable) {
  if (pct === null || pct === undefined) return 'var(--text-muted)';
  if (pct >= ceiling) return 'var(--status-bad-text)';
  if (pct > comfortable) return 'var(--status-warn-text)';
  return 'var(--status-good-text)';
}

// Which debts make up the numerator, and where each figure came from. An
// estimated minimum is marked as one everywhere it appears: it is derived from
// the balance and APR on the common 1%-plus-interest shape, and issuers differ
// (Discover bills 2%, Amex carries a $40 floor).
function PaymentBreakdown({ payments }) {
  const rows = (payments || []).filter((p) => p.amount !== null && p.amount !== undefined);
  if (rows.length === 0) return null;

  return (
    <ul className="bp-pay-list">
      {rows.map((p) => (
        <li key={p.account_id} className="bp-pay-row">
          <span className="bp-pay-name">{p.name}</span>
          {p.source === 'estimated' && (
            <span className="bp-pay-tag" title="1% of the balance plus a cycle of interest at the APR you entered">
              estimated
            </span>
          )}
          <span className="bp-pay-amount">{fmt$(p.amount)}</span>
        </li>
      ))}
    </ul>
  );
}

function DebtToIncome({ dti }) {
  const missing = dti?.debts_missing_payment || [];
  const pct = dti?.pct;
  const ceiling = dti?.ceiling_pct ?? 43;
  const comfortable = dti?.comfortable_pct ?? 15;

  // A ratio missing its largest payment scores well for the wrong reason: a
  // household whose mortgage has no minimum payment set sums to the cards
  // that do and reports single digits. Naming the accounts beats publishing
  // a confident wrong number.
  if (missing.length > 0) {
    return (
      <div className="bp-block">
        <div className="bp-block-head">
          <h3 className="bp-block-title">Debt-to-income</h3>
          <span className="bp-block-kicker">what a lender actually checks</span>
        </div>
        <div className="bp-missing">
          <p className="bp-missing-lead">
            Can&apos;t show this yet — {missing.length === 1 ? 'one debt has' : `${missing.length} debts have`}
            {' '}no monthly payment we can read or work out, and leaving
            {' '}{missing.length === 1 ? 'it' : 'them'} out would report a ratio far
            lower than the real one.
          </p>
          <ul className="bp-missing-list">
            {missing.map((m) => (
              <li key={m.account_id}>
                <span className="bp-missing-name">{m.name}</span>
                <span className="bp-missing-bal">{fmt$(m.balance)} owed</span>
              </li>
            ))}
          </ul>
          {/* A card's minimum follows from its balance and APR; a loan's is an
              amortisation schedule the balance cannot reveal, so it has to be
              typed in. */}
          <p className="bp-note">
            Open the account above and set its monthly payment. A loan&apos;s has
            to come off a statement — only a card&apos;s can be worked out from
            the balance and APR.
          </p>
          <PaymentBreakdown payments={dti.payments} />
        </div>
      </div>
    );
  }

  if (pct === null || pct === undefined) {
    return (
      <div className="bp-block">
        <div className="bp-block-head">
          <h3 className="bp-block-title">Debt-to-income</h3>
          <span className="bp-block-kicker">what a lender actually checks</span>
        </div>
        <p className="bp-note">
          Needs a monthly income figure. Nothing in your transactions looks like
          a regular paycheque yet.
        </p>
      </div>
    );
  }

  // The scale is the lenders' own, so the number lands somewhere meaningful
  // rather than floating free.
  const marker = Math.min(100, (pct / 60) * 100);

  return (
    <div className="bp-block">
      <div className="bp-block-head">
        <h3 className="bp-block-title">Debt-to-income</h3>
        <span className="bp-block-kicker">what a lender actually checks</span>
      </div>

      <div className="bp-dti-figure" style={{ color: dtiColor(pct, ceiling, comfortable) }}>
        {pct}%
      </div>
      {/* The arithmetic is shown because a ratio with no visible numerator is
          not worth trusting — and this one is assembled from minimum payments
          that are partly typed in, partly estimated, over a detected paycheque. */}
      <div className="bp-dti-math">
        {fmt$(dti.monthly_debt_payments)} in monthly debt payments ÷{' '}
        {fmt$(dti.monthly_income)} monthly income
        {dti.income_source === 'detected' && ' (detected from your deposits)'}
      </div>

      <PaymentBreakdown payments={dti.payments} />

      <div className="bp-scale">
        <div className="bp-scale-track">
          <div className="bp-scale-band bp-scale-band--good" style={{ width: `${(36 / 60) * 100}%` }} />
          <div className="bp-scale-band bp-scale-band--warn" style={{ width: `${((43 - 36) / 60) * 100}%` }} />
          <div className="bp-scale-band bp-scale-band--bad" style={{ width: `${((60 - 43) / 60) * 100}%` }} />
          <span className="bp-scale-marker" style={{ left: `${marker}%` }} aria-hidden="true" />
        </div>
        <div className="bp-scale-labels">
          <span>36% — comfortable</span>
          <span>43% — the mortgage ceiling</span>
        </div>
      </div>

      <p className="bp-note">
        Lenders read this before they read a score, and no credit bureau holds
        an income figure — which is why no credit monitor can show it to you.
        The 43% line is where a conventional mortgage stops qualifying.
      </p>
    </div>
  );
}

const TREND_WORD = {
  rising: 'and climbing',
  falling: 'and coming down',
  steady: 'and holding steady',
};

function shortMonth(key) {
  const [y, m] = (key || '').split('-');
  const d = new Date(Number(y), Number(m) - 1, 1);
  return Number.isNaN(d.getTime()) ? key : d.toLocaleString(undefined, { month: 'short' });
}

// One series, so no legend and no categorical palette — the heading names it.
// The bars are the neutral accent; only the latest month takes the warning hue,
// and only when it is actually the finding, so colour still means something.
function InterestPaid({ history, carry }) {
  const months = history?.months || [];
  if (months.length === 0) return null;

  const highest = history.highest || 1;
  const latest = months[months.length - 1];
  const rising = history.trend === 'rising';
  const vsAverage = history.average
    ? Math.round((latest.interest / history.average) * 10) / 10
    : null;

  return (
    <div className="bp-block">
      <div className="bp-block-head">
        <h3 className="bp-block-title">What the debt has cost you</h3>
        <span className="bp-block-kicker">interest actually billed</span>
      </div>

      <div className="bp-interest-figure">{fmt$(history.total_paid)}</div>
      <div className="bp-dti-math">
        paid in interest since {shortMonth(months[0].month)}
        {' · '}averaging {fmt$(history.average)} a month {TREND_WORD[history.trend] || ''}
      </div>

      {/* Each bar carries its own reading for a screen reader, which is the
          table view this size of chart warrants. */}
      <ul className="bp-bars" aria-label="Interest billed by month">
        {months.map((m) => {
          const pct = Math.max(2, (m.interest / highest) * 100);
          const isLatest = m.month === latest.month;
          return (
            <li key={m.month} className="bp-bar-col">
              <span className="bp-bar-value">{fmt$(m.interest)}</span>
              <span className="bp-bar-track">
                <span
                  className={`bp-bar${isLatest && rising ? ' is-latest' : ''}`}
                  style={{ height: `${pct}%` }}
                />
              </span>
              <span className="bp-bar-label">{shortMonth(m.month)}</span>
              <span className="sr-only">
                {shortMonth(m.month)}: {fmt$(m.interest)} in interest
              </span>
            </li>
          );
        })}
      </ul>

      <p className="bp-note">
        {rising && vsAverage > 1.2 ? (
          <>
            <strong>{shortMonth(latest.month)} was your most expensive month yet</strong>
            {' '}at {fmt$(latest.interest)} — {vsAverage}× your average. Interest is
            charged on the balance you carry past the due date, so this figure is
            the price of the balance, not of the spending.
          </>
        ) : (
          <>
            This is what the issuers actually billed, taken from the interest
            lines on your statements — not an estimate. It is charged on the
            balance carried past the due date.
          </>
        )}
        {carry?.monthly_interest > 0 && (
          <> At today&apos;s balances it runs about{' '}
            ${Math.round(carry.monthly_interest).toLocaleString()}/month if nothing changes.
          </>
        )}
      </p>
      {carry?.accounts_missing_apr > 0 && (
        <p className="bp-note">
          {carry.accounts_missing_apr === 1
            ? '1 card has'
            : `${carry.accounts_missing_apr} cards have`}
          {' '}no APR recorded, so that projection is short.
        </p>
      )}
    </div>
  );
}

// Static, and deliberately so. These are the things advisors repeat because
// people get them wrong, and none of them needs a number from this app.
function WhatMovesIt() {
  return (
    <div className="bp-block">
      <div className="bp-block-head">
        <h3 className="bp-block-title">Worth knowing</h3>
        <span className="bp-block-kicker">the parts people get wrong</span>
      </div>
      <ul className="bp-facts">
        <li>
          <strong>Rate shopping is one inquiry, not six.</strong> Mortgage, auto
          and student-loan applications inside a 14–45 day window get counted
          once. Spreading them out over months is what actually costs you.
        </li>
        <li>
          <strong>A hard inquiry costs under 5 points</strong> and stops counting
          toward your score after 12 months. Most people badly overestimate this
          one and avoid applying for things they should.
        </li>
        <li>
          <strong>One 30-day late payment is the expensive mistake</strong> — it
          can cost 100+ points and sits on your report for 7 years. Nothing else
          on this page is in the same league, which is why autopay for at least
          the minimum is the highest-value thing you can set up.
        </li>
        <li>
          <strong>Check the report, not just the score.</strong> Roughly one
          report in five has an error on it, and disputing one is the fastest
          repair available to most people. All three bureaus are free weekly at{' '}
          <a href="https://www.annualcreditreport.com" target="_blank" rel="noreferrer">
            annualcreditreport.com
          </a>.
        </li>
        <li>
          <strong>Freezing your credit is free</strong> at each bureau, and does
          not affect your score. It blocks new accounts being opened in your
          name; you thaw it when you actually apply for something.
        </li>
      </ul>
    </div>
  );
}

export default function BorrowingPowerPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    getBorrowingPower()
      .then((r) => { if (live) setData(r.data); })
      .catch(() => { if (live) setError('Could not load borrowing power.'); });
    return () => { live = false; };
  }, []);

  if (error) return <div className="ov-card"><div className="ov-error">{error}</div></div>;
  if (!data) {
    return (
      <div className="ov-card">
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <Spin /> Loading…
        </div>
      </div>
    );
  }

  return (
    <div className="ov-card">
      <div className="ov-card-header">
        <div>
          <h2 className="ov-card-title">Borrowing power</h2>
          <div className="ov-card-subtitle">
            What a lender reads, and what moves it
          </div>
        </div>
      </div>

      <div className="ov-card-body">
        <p className="bp-framing">
          We don&apos;t estimate a credit score — a score is a model fit to a
          bureau file, and this app sees roughly a third of its inputs. For your
          real one, check your card issuer. What&apos;s here is the part a score
          leaves out.
        </p>

        <div className="bp-blocks">
          <DebtToIncome dti={data.dti} />
          <InterestPaid history={data.interest_history} carry={data.carry_cost} />
          <WhatMovesIt />
        </div>
      </div>
    </div>
  );
}
