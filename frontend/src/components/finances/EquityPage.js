import React, { useCallback, useEffect, useState } from 'react';

import Spin from '../ui/Spin';
import KpiCard from '../ui/KpiCard';
import UsableEquityCard from './equity/UsableEquityCard';
import DealAnalyzer from './equity/DealAnalyzer';
import { fmt$ } from '../../utils/formatting';
import { userMessage } from '../../utils/errorMessage';
import { getCapacity } from '../../api/equity';

export default function EquityPage() {
  const [capacity, setCapacity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    getCapacity()
      .then((r) => setCapacity(r.data))
      .catch((e) => setError(userMessage(e, 'Could not load equity capacity.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const properties = capacity?.properties ?? [];

  return (
    <>
      <div className="eh-topbar">
        <div className="eh-topbar-title">Equity &amp; Deals</div>
      </div>

      <div className="eh-content">
        {error && <div className="ov-error">{error}</div>}

        {loading && !capacity ? <Spin /> : (
          <>
            <section className="eh-kpi-row">
              <KpiCard
                label="Total equity"
                value={fmt$(capacity?.total_equity)}
                barColor="#059669"
                help="Property value minus outstanding loan balances."
              />
              <KpiCard
                label="Cash-out available"
                value={fmt$(capacity?.total_cash_out_available)}
                barColor="#6366f1"
                help="Net of closing costs, at 75% LTV. Raises your payments — see each property below."
              />
              <KpiCard
                label="HELOC available"
                value={fmt$(capacity?.total_heloc_available)}
                barColor="#8b5cf6"
                help="At 85% CLTV, behind the existing mortgage. Variable rate."
              />
              <KpiCard
                label="Properties"
                value={String(capacity?.count ?? 0)}
                barColor="#059669"
              />
            </section>

            {capacity?.needs_valuation?.length > 0 && (
              <section className="prop-alert">
                <div className="prop-alert-title">
                  Not counted above — no current value on file
                </div>
                <ul>
                  {capacity.needs_valuation.map((p) => (
                    <li key={p.property_id}>{p.name}</li>
                  ))}
                </ul>
              </section>
            )}

            {properties.length === 0 ? (
              <div className="prop-empty">
                <div className="prop-empty-icon" aria-hidden="true">🔑</div>
                <div className="prop-empty-title">No borrowable equity yet</div>
                <div className="prop-empty-sub">
                  Add a property with a current value and a mortgage, and this
                  page shows what you could draw against it — and what that
                  would do to your cash flow.
                </div>
              </div>
            ) : (
              <>
                <div className="eq-preamble">
                  Every figure below is paired with what it costs. Borrowing
                  against a property raises its payment, and on thin margins
                  that can flip it from paying you to costing you.
                </div>
                {properties.map((p) => (
                  <UsableEquityCard key={p.property_id} capacity={p} />
                ))}
              </>
            )}

            <DealAnalyzer properties={properties} />
          </>
        )}
      </div>
    </>
  );
}
