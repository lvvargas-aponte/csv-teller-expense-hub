import React, { useMemo } from 'react';
import { fmtSigned } from '../../utils/formatting';
import { balanceSheetParts } from '../../utils/netWorth';
import InfoPopover from '../ui/InfoPopover';

// The household's position, as one figure and the parts that make it.
//
// This replaced a gradient banner and a row of four KPI tiles. The banner spent
// roughly 180px on a greeting, two decorative circles and a line of
// encouragement; the tiles gave four unequal readings the same weight, and one
// of them ("This Month") reported a spending collapse whenever a sync was
// simply late.
//
// The bar is the point. A net worth of −$87,399 reads as a catastrophe until
// you can see that a mortgage is 97% of the debt behind it, so the composition
// is shown to scale rather than left for the reader to infer from a total.

const WHOLE = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
});

function Reading({ label, value, tone, note }) {
  return (
    <div className="eh-hero-reading">
      <span className="eh-hero-reading-label">{label}</span>
      <span className="eh-hero-reading-value" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      {note && <span className="eh-hero-reading-note">{note}</span>}
    </div>
  );
}

export default function BalanceSheetHero({
  summary, healthScore, healthSignals, ratios, creditHealth, blur,
}) {
  // Walks every account, on a component that re-renders for the blur toggle
  // and for two independent fetches.
  const parts = useMemo(() => balanceSheetParts(summary), [summary]);
  const netWorth = summary?.net_worth;
  const hasNetWorth = netWorth !== null && netWorth !== undefined;

  const runway = ratios?.emergency_fund?.months_covered;
  const income = ratios?.income?.monthly;
  const utilization = creditHealth?.overall_utilization_pct;
  const cardsOver30 = creditHealth?.cards_over_30 ?? 0;

  const signalCount = healthSignals?.length ?? 0;
  const availableCount = healthSignals?.filter((s) => s.available).length ?? 0;

  return (
    <section className="eh-hero" aria-label="Where you stand">
      <div className="eh-hero-top">
        <div className="eh-hero-total">
          <div className="eh-hero-label">
            <span>Net worth</span>
            <InfoPopover className="eh-info--kpi" label="net worth" title="Net worth">
              Everything you own minus everything you owe, across all linked and
              manual accounts. Property and vehicles are included in the total and
              called out separately below, because they raise net worth without
              making a hard month any easier — the emergency-fund runway ignores
              them on purpose.
            </InfoPopover>
          </div>
          <div
            className={`eh-hero-figure${hasNetWorth && netWorth < 0 ? ' is-neg' : ''}${blur ? ' eh-blur' : ''}`}
          >
            {hasNetWorth ? fmtSigned(netWorth) : '—'}
          </div>
        </div>

        <div className="eh-hero-readings">
          <Reading
            label="Health score"
            value={(healthScore === null || healthScore === undefined) ? '—' : healthScore}
            note={signalCount ? `${availableCount} of ${signalCount} signals` : null}
          />
          {(runway !== null && runway !== undefined) && (
            <Reading label="Runway" value={`${runway} mo`} note="of expenses in cash" />
          )}
          {(income !== null && income !== undefined && income > 0) && (
            <Reading
              label="Income"
              value={WHOLE.format(income)}
              note={ratios?.income?.source === 'detected' ? 'detected monthly' : 'monthly'}
            />
          )}
          {(utilization !== null && utilization !== undefined) && (
            <Reading
              label="Utilization"
              value={`${utilization}%`}
              tone={utilization > 30 ? 'var(--status-warn-text)' : 'var(--status-good-text)'}
              note={cardsOver30 > 0 ? `${cardsOver30} card${cardsOver30 === 1 ? '' : 's'} over 30%` : 'all cards under 30%'}
            />
          )}
        </div>
      </div>

      {parts && parts.segments.length > 0 && (
        <>
          <div className="eh-hero-bar" role="img" aria-label="What you own against what you owe">
            {parts.segments.map((s) => (
              <span
                key={s.key}
                className="eh-hero-seg"
                style={{ width: `${s.pct}%`, background: s.fill }}
              />
            ))}
          </div>
          <div className="eh-hero-key">
            {parts.segments.map((s) => (
              <span key={s.key} className="eh-hero-key-item">
                <span className="eh-hero-swatch" style={{ background: s.fill }} aria-hidden="true" />
                {s.label}
                <span className={`eh-hero-key-value${blur ? ' eh-blur' : ''}`}>
                  {WHOLE.format(s.value)}
                </span>
              </span>
            ))}
          </div>
          {/* Only worth saying when a loan is actually doing the damage. */}
          {parts.withoutLoans !== null && parts.installmentShareOfDebt >= 50 && (
            <p className={`eh-hero-note${blur ? ' eh-blur' : ''}`}>
              Loans are {parts.installmentShareOfDebt}% of what you owe. Without them
              you would be <strong>{fmtSigned(parts.withoutLoans)}</strong> — the figure
              the runway and savings ratios reason about, because a house is not
              spendable.
            </p>
          )}
        </>
      )}
    </section>
  );
}
