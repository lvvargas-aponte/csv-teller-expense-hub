import React from 'react';

import Num from '../Num';
import { fmt$, fmtSigned } from '../../../utils/formatting';

function Scenario({ title, subtitle, proceeds, proceedsLabel, rows, killsCashFlow, note }) {
  return (
    <div className={`eq-scenario${killsCashFlow ? ' eq-scenario--warn' : ''}`}>
      <div className="eq-scenario-head">
        <span className="eq-scenario-title">{title}</span>
        <span className="eq-scenario-sub">{subtitle}</span>
      </div>

      <div className="eq-proceeds">
        <span className="eq-proceeds-amount"><Num value={proceeds} /></span>
        <span className="eq-proceeds-label">{proceedsLabel}</span>
      </div>

      {/* The cost sits directly beneath the amount, never in a drawer.
          The proceeds figure alone reads as free money. */}
      <dl className="eq-rows">
        {rows.map(({ label, value, tone }) => (
          <div className="eq-row" key={label}>
            <dt>{label}</dt>
            <dd className={tone || ''}>{value}</dd>
          </div>
        ))}
      </dl>

      {killsCashFlow && (
        <div className="eq-warn">
          This would turn a property that pays you into one you subsidize.
        </div>
      )}
      {note && <div className="eq-note">{note}</div>}
    </div>
  );
}

export default function UsableEquityCard({ capacity }) {
  if (!capacity.available) {
    return (
      <section className="ov-card">
        <div className="ov-card-header">
          <div className="ov-card-title">{capacity.name || 'Property'}</div>
        </div>
        <div className="ov-card-body">
          <div className="prop-empty-inline">
            {capacity.detail || 'Borrowing capacity needs a current value.'}
          </div>
        </div>
      </section>
    );
  }

  const refi = capacity.cash_out_refi;
  const heloc = capacity.heloc;

  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">{capacity.name}</div>
        <div className="ov-card-subtitle">
          <Num value={capacity.equity} /> equity ·
          {' '}{capacity.current_ltv}% LTV ·
          {' '}{fmtSigned(capacity.current_cash_flow)}/mo today
        </div>
      </div>

      <div className="ov-card-body eq-scenarios">
        <Scenario
          title="Cash-out refinance"
          subtitle={`up to ${refi.max_ltv_pct}% LTV at ${refi.rate_pct}%`}
          proceeds={refi.net_proceeds}
          proceedsLabel="after closing costs"
          killsCashFlow={refi.kills_cash_flow}
          rows={[
            { label: 'Gross proceeds', value: fmt$(refi.gross_proceeds) },
            {
              label: `Closing costs (${refi.closing_cost_pct}%)`,
              value: `− ${fmt$(refi.estimated_closing_costs)}`,
            },
            {
              label: 'Payment change',
              value: `+${fmt$(refi.payment_delta)}/mo`,
              tone: 'neg',
            },
            {
              label: 'Cash flow after',
              value: `${fmtSigned(refi.cash_flow_after)}/mo`,
              tone: refi.cash_flow_after < 0 ? 'neg' : 'pos',
            },
            { label: 'DSCR after', value: refi.dscr_after ?? '—' },
          ]}
        />

        <Scenario
          title="HELOC"
          subtitle={`up to ${heloc.max_cltv_pct}% CLTV at ${heloc.rate_pct}%`}
          proceeds={heloc.max_line}
          proceedsLabel="available line"
          killsCashFlow={heloc.kills_cash_flow}
          note={heloc.note}
          rows={[
            {
              label: 'Interest-only on a full draw',
              value: `${fmt$(heloc.interest_only_payment)}/mo`,
              tone: 'neg',
            },
            {
              label: 'Cash flow after full draw',
              value: `${fmtSigned(heloc.cash_flow_after_full_draw)}/mo`,
              tone: heloc.cash_flow_after_full_draw < 0 ? 'neg' : 'pos',
            },
          ]}
        />
      </div>
    </section>
  );
}
