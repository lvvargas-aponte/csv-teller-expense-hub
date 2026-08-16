import React from 'react';

import Num from '../Num';
import { fmt$, fmtSigned } from '../../../utils/formatting';

const RATING_LABEL = {
  strong: 'Performing',
  watch: 'Watch',
  underperforming: 'Underperforming',
  not_rated: 'Not a rental',
};

function Metric({ label, value, title }) {
  return (
    <div className="prop-metric" title={title}>
      <div className="prop-metric-label">{label}</div>
      <div className="prop-metric-value">{value}</div>
    </div>
  );
}

const pct = (v) => (v === null || v === undefined ? '—' : `${v.toFixed(2)}%`);
const ratio = (v) => (v === null || v === undefined ? '—' : v.toFixed(2));

export default function PropertyCard({ property, onOpen }) {
  const { pro_forma: proForma = {}, performance = {} } = property;
  const rating = performance.rating || 'strong';
  const cashFlow = proForma.cash_flow ?? 0;

  // Equity bar: how much of the property's value is actually owned. Null
  // value means no valuation on file, so the bar is suppressed rather than
  // rendered at a misleading 0%.
  const equityPct = property.equity_pct;

  return (
    <button type="button" className="prop-card" onClick={() => onOpen(property.property_id)}>
      <div className="prop-card-head">
        <div>
          <div className="prop-card-name">{property.name}</div>
          <div className="prop-card-sub">
            {property.status === 'rental' ? 'Rental' : RATING_LABEL.not_rated}
            {property.basis === 'actual' ? ' · actuals' : ' · projected'}
          </div>
        </div>
        <span className={`prop-pill prop-pill--${rating}`}>
          {RATING_LABEL[rating] || rating}
        </span>
      </div>

      {equityPct !== null && equityPct !== undefined && (
        <div className="prop-equity">
          <div className="prop-equity-bar">
            <div
              className="prop-equity-fill"
              style={{ width: `${Math.max(0, Math.min(100, equityPct))}%` }}
            />
          </div>
          <div className="prop-equity-legend">
            <span><Num value={property.equity} /> equity</span>
            <span className="prop-equity-of">of <Num value={property.current_value} /></span>
          </div>
        </div>
      )}

      <div className="prop-metrics">
        <Metric
          label="Cash flow"
          value={<span className={cashFlow < 0 ? 'neg' : 'pos'}>{fmtSigned(cashFlow)}/mo</span>}
          title="NOI minus debt service."
        />
        <Metric label="NOI" value={`${fmt$(proForma.noi)}/mo`}
                title="Net operating income — excludes the mortgage." />
        <Metric label="Cap rate" value={pct(property.cap_rate)}
                title="Annual NOI as a percentage of current value." />
        <Metric label="DSCR" value={ratio(property.dscr)}
                title="NOI over debt service. Lenders look for 1.25+." />
      </div>

      {performance.reasons?.length > 0 && rating !== 'strong' && (
        <ul className="prop-reasons">
          {performance.reasons.slice(0, 2).map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </button>
  );
}
