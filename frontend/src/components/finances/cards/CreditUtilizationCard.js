import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getCreditHealth } from '../../../api/dashboard';
import Num from '../Num';
import { fmt$ } from '../../../utils/formatting';

// Bars keep the saturated fill; the figure beside them uses the text-grade
// sibling and carries the band as a word, so the band survives both a
// colour-blind reader and a greyscale print.
const STATUS_FILL = {
  good: 'var(--accent)',
  warn: 'var(--amber)',
  high: 'var(--red)',
  unknown: 'var(--text-muted)',
};

const STATUS_TEXT = {
  good: 'var(--status-good-text)',
  warn: 'var(--status-warn-text)',
  high: 'var(--status-bad-text)',
  unknown: 'var(--text-muted)',
};

// The projected segment is the same hue as the fill it extends, at tint
// strength — it has to read as "the same card, later", not as a second card.
const STATUS_TINT = {
  good: 'var(--good-tint)',
  warn: 'var(--warn-tint)',
  high: 'var(--bad-tint)',
  unknown: 'var(--border)',
};

const STATUS_WORD = { good: 'Good', warn: 'Watch', high: 'High' };

function monthName(key) {
  if (!key) return '';
  const [y, m] = key.split('-');
  const d = new Date(Number(y), Number(m) - 1, 1);
  return Number.isNaN(d.getTime())
    ? key
    : d.toLocaleString(undefined, { month: 'long' });
}

// An account with no stored limit has no utilization to show. Where the card
// has somewhere to send you — DebtPage, which renders the drawer that edits the
// limit — this is the way there. Where it doesn't, it says so and stops: the
// arrow on its own read as a link for as long as this card existed, and clicking
// it did nothing.
function SetLimit({ accountId, name, onSetLimit }) {
  if (!onSetLimit) return <>No limit</>;
  return (
    <button
      type="button"
      className="eh-util-setlimit"
      onClick={() => onSetLimit(accountId)}
    >
      set limit<span aria-hidden="true"> →</span>
      <span className="sr-only">{` for ${name}`}</span>
    </button>
  );
}

// The 10% and 30% shelves are drawn into every track, so a card's position
// relative to them is read rather than computed. A growing card extends past
// its fill in the same hue at tint strength — that faded segment is where the
// balance lands next month at the pace it just set.
function UtilizationTrack({ pct, status, projectedPct, label }) {
  const width = (pct === null || pct === undefined) ? 0 : Math.min(100, pct);
  const projected = Math.min(100, projectedPct || 0);
  const ghost = projected > width ? projected - width : 0;

  return (
    <div
      className={`eh-util-track${status === 'warn' || status === 'high' ? ' is-flagged' : ''}`}
      role="progressbar"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuetext={
        STATUS_WORD[status] ? `${pct}% used — ${STATUS_WORD[status]}` : `${pct}% used`
      }
    >
      <div
        className="eh-util-fill"
        style={{ width: `${width}%`, background: STATUS_FILL[status] || 'inherit' }}
      />
      {ghost > 0 && (
        <div
          className="eh-util-ghost"
          style={{
            left: `${width}%`,
            width: `${ghost}%`,
            background: STATUS_TINT[status] || 'var(--border)',
          }}
        />
      )}
      <span className="eh-util-tick" style={{ left: '10%' }} aria-hidden="true" />
      <span className="eh-util-tick" style={{ left: '30%' }} aria-hidden="true" />
    </div>
  );
}

export default function CreditUtilizationCard({ onHide, index, kicker, onSetLimit, reloadKey = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // `reloadKey` lets the page re-ask after something that changes which
  // accounts count — closing one, for instance. Utilization is computed on the
  // server, so there is nothing to recompute here.
  useEffect(() => {
    let live = true;
    // Clearing the error first is what lets a retry recover: without it a
    // reloadKey bump after one failure left the card showing the old error
    // for the rest of the session.
    setError(null);
    getCreditHealth()
      .then((r) => { if (live) setData(r.data); })
      .catch(() => { if (live) setError('Could not load credit utilization.'); });
    return () => { live = false; };
  }, [reloadKey]);

  const carry = data?.carry_cost;
  const loading = data === null && !error;
  const accounts = data?.accounts || [];
  const empty = !loading && !error && accounts.length === 0;
  const month = monthName(data?.latest_month);
  const overall = data?.overall_utilization_pct;
  const hasOverall = overall !== null && overall !== undefined;
  const anyProjection = accounts.some((a) => a.projection);

  return (
    <DashboardCard
      title="Credit Utilization"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No credit cards found. Add credit limits from the card drawer above to see utilization."
      onHide={onHide}
      headerExtra={month ? <span className="eh-util-month">{month}</span> : null}
    >
      {hasOverall && (
        <div className="eh-util-headline">
          <div className="eh-util-headline-row">
            <div className="eh-util-overall">
              <span
                className="eh-util-overall-pct"
                style={{ color: STATUS_TEXT[data.overall_status] || 'inherit' }}
              >
                {overall}%
              </span>
              <span className="eh-util-overall-note">
                overall · <Num value={data.total_balance} /> of <Num value={data.total_limit} />
              </span>
            </div>
            {data.cards_over_30 > 0 && (
              <span className="eh-util-chip">
                <span className="eh-util-chip-dot" aria-hidden="true" />
                {data.cards_over_30} card{data.cards_over_30 === 1 ? '' : 's'} over 30%
              </span>
            )}
          </div>
          {/* The aggregate and the per-card figures are separate inputs to a
              score, and they disagree here — saying so is what stops the
              headline from reading as an all-clear. */}
          {data.cards_over_30 > 0 && (
            <div className="eh-util-headline-sub">
              The average looks fine. One card doesn&apos;t — and a score reads both.
            </div>
          )}
        </div>
      )}

      {accounts.length > 0 && (
        <div className="eh-util-legend">
          <span className="eh-util-legend-rule" aria-hidden="true" />
          <span>
            bars mark 10% and 30%
            {anyProjection ? ' · faded segment is next month at this pace' : ''}
          </span>
        </div>
      )}

      <div className="eh-util-cards">
        {accounts.map((a) => {
          const pct = a.utilization_pct;
          const hasPct = pct !== null && pct !== undefined;
          const name = a.name || a.institution;
          const net = a.activity?.latest?.net_change;
          const lever = (a.levers || [])[0];
          const latest = a.activity?.latest;
          // Over the 30% shelf is where the payment-versus-interest gap is
          // worth a sentence; on a card that is nearly clear it is noise.
          const overShelf = hasPct && pct > 30.0;

          return (
            <div key={a.account_id} className={`eh-util-card${overShelf ? ' is-flagged' : ''}`}>
              <div className="eh-util-card-head">
                <span className="eh-util-card-name">{name}</span>
                <span
                  className="eh-util-card-pct"
                  style={{ color: STATUS_TEXT[a.status] || 'inherit' }}
                >
                  {hasPct
                    ? `${pct}%`
                    : <SetLimit accountId={a.account_id} name={name} onSetLimit={onSetLimit} />}
                </span>
              </div>

              <UtilizationTrack
                pct={pct}
                status={a.status}
                projectedPct={a.projection?.projected_pct}
                label={`${name} utilization`}
              />

              <div className="eh-util-card-meta">
                <span>
                  <Num value={a.balance} />
                  {(a.credit_limit !== null && a.credit_limit !== undefined) && (
                    <> / <Num value={a.credit_limit} /></>
                  )}
                  {lever && <> · {fmt$(lever.amount)} → under {lever.gets_to_pct}%</>}
                  {/* A cleared card is not idle: its unused limit is what
                      holds the aggregate down, which matters before closing one. */}
                  {pct === 0 && a.headroom > 0 && (
                    <> · {fmt$(a.headroom)} of headroom holding your overall down</>
                  )}
                </span>
                {/* Zero is a real answer — the month was a wash — so the test
                    is for a number, not for truthiness. */}
                {(net !== null && net !== undefined) && (
                  <span style={{ color: net > 0 ? STATUS_TEXT[a.status] : 'var(--status-good-text)' }}>
                    {net >= 0 ? '+' : '−'}{fmt$(Math.abs(net))}
                    {a.projection && <> → {a.projection.projected_pct}%</>}
                  </span>
                )}
              </div>

              {overShelf && lever && (
                <div className="eh-util-card-say">
                  <strong>{fmt$(lever.amount)}</strong> brings it under {lever.gets_to_pct}%.
                  {latest?.interest > 0 && latest?.payments > 0 && (
                    <> Of the {fmt$(latest.payments)} you paid in {month},{' '}
                      {fmt$(latest.interest)} was interest.
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Two interest figures, and they disagree on purpose: one is what the
          issuers billed last cycle, the other what today's balances would cost
          if they simply sat there. Showing only the model overstates the cost
          of a card that was paid off inside its grace period. */}
      {(data?.interest_billed_latest > 0 || carry?.monthly_interest > 0) && (
        <div className="eh-util-foot">
          {data?.interest_billed_latest > 0 && (
            <div className="eh-util-foot-cell">
              <span className="eh-util-foot-label">Interest billed in {month}</span>
              <span className="eh-util-foot-value">{fmt$(data.interest_billed_latest)}</span>
            </div>
          )}
          {carry?.monthly_interest > 0 && (
            <div className="eh-util-foot-cell">
              <span className="eh-util-foot-label">If today&apos;s balances hold</span>
              <span className="eh-util-foot-value is-muted">
                ~${Math.round(carry.monthly_interest).toLocaleString()}/month
              </span>
            </div>
          )}
        </div>
      )}
      {carry?.accounts_missing_apr > 0 && (
        <div className="eh-util-missing-apr">
          {carry.accounts_missing_apr === 1
            ? '1 card has'
            : `${carry.accounts_missing_apr} cards have`}
          {' '}no APR set — add one to see the cost
        </div>
      )}
    </DashboardCard>
  );
}
