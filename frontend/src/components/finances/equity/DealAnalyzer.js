import React, { useState } from 'react';

import { fmt$, fmtSigned } from '../../../utils/formatting';
import { userMessage } from '../../../utils/errorMessage';
import { analyzeDeal } from '../../../api/equity';

const EMPTY = {
  purchase_price: '', down_pct: 25, rate_pct: 7, term_months: 360,
  monthly_rent: '', vacancy_pct: 5, opex_pct: 35, closing_pct: 3, rehab: '',
  funded_from: 'cash', source_property_id: '',
};

const num = (v, fallback = 0) => {
  const parsed = parseFloat(v);
  return Number.isNaN(parsed) ? fallback : parsed;
};

function Metric({ label, value, tone, hint }) {
  return (
    <div className="eq-metric" title={hint}>
      <div className="eq-metric-label">{label}</div>
      <div className={`eq-metric-value ${tone || ''}`}>{value}</div>
    </div>
  );
}

export default function DealAnalyzer({ properties }) {
  const [draft, setDraft] = useState(EMPTY);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

  const set = (key) => (e) => setDraft((d) => ({ ...d, [key]: e.target.value }));
  const borrowed = draft.funded_from !== 'cash';

  const run = async (e) => {
    e.preventDefault();
    if (!num(draft.purchase_price)) { setError('Enter a purchase price.'); return; }
    if (borrowed && !draft.source_property_id) {
      setError('Pick which property the money comes from.');
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const r = await analyzeDeal({
        purchase_price: num(draft.purchase_price),
        down_pct: num(draft.down_pct, 25),
        rate_pct: num(draft.rate_pct, 7),
        term_months: parseInt(draft.term_months, 10) || 360,
        monthly_rent: num(draft.monthly_rent),
        vacancy_pct: num(draft.vacancy_pct, 5),
        opex_pct: num(draft.opex_pct, 35),
        closing_pct: num(draft.closing_pct, 3),
        rehab: num(draft.rehab),
        funded_from: draft.funded_from,
        source_property_id: borrowed ? draft.source_property_id : null,
      });
      setResult(r.data);
    } catch (e2) {
      setError(userMessage(e2, 'Could not analyze that deal.'));
    } finally {
      setRunning(false);
    }
  };

  const field = (key, label, type = 'number') => (
    <label className="prop-field">
      <span className="prop-field-label">{label}</span>
      <input type={type} step="any" value={draft[key]} onChange={set(key)} />
    </label>
  );

  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">Deal analyzer</div>
        <div className="ov-card-subtitle">
          Model a purchase before you make it
        </div>
      </div>

      <div className="ov-card-body">
        <form onSubmit={run}>
          <div className="prop-form-grid">
            {field('purchase_price', 'Purchase price')}
            {field('monthly_rent', 'Expected monthly rent')}
            {field('down_pct', 'Down payment %')}
            {field('rate_pct', 'Rate %')}
            {field('term_months', 'Term (months)')}
            {field('vacancy_pct', 'Vacancy %')}
            {field('opex_pct', 'Operating expenses % of rent')}
            {field('closing_pct', 'Closing costs %')}
            {field('rehab', 'Rehab budget')}

            <label className="prop-field">
              <span className="prop-field-label">Down payment comes from</span>
              <select value={draft.funded_from} onChange={set('funded_from')}>
                <option value="cash">Cash on hand</option>
                <option value="heloc">HELOC on a property I own</option>
                <option value="cash_out_refi">Cash-out refinance</option>
              </select>
            </label>

            {borrowed && (
              <label className="prop-field">
                <span className="prop-field-label">Borrow against</span>
                <select
                  value={draft.source_property_id}
                  onChange={set('source_property_id')}
                >
                  <option value="">Pick a property…</option>
                  {(properties || []).map((p) => (
                    <option key={p.property_id} value={p.property_id}>{p.name}</option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {error && <div className="ov-error">{error}</div>}

          <div className="modal-actions">
            <button type="submit" className="btn-primary" disabled={running}>
              {running ? 'Working…' : 'Analyze'}
            </button>
          </div>
        </form>

        {result?.available && (
          <div className="eq-result">
            {/* Warnings sit above the attractive numbers, deliberately. This
                is the screen that makes over-leverage feel easy. */}
            {result.warnings.length > 0 && (
              <div className="eq-warnings">
                {result.warnings.map((w) => <div key={w}>{w}</div>)}
              </div>
            )}

            <div className="eq-headline">
              <div className="eq-headline-label">
                Change to total portfolio cash flow
              </div>
              <div className={`eq-headline-value ${
                result.net_effect.portfolio_cash_flow_delta < 0 ? 'neg' : 'pos'
              }`}>
                {fmtSigned(result.net_effect.portfolio_cash_flow_delta)}/mo
              </div>
              <div className="eq-headline-note">
                {result.net_effect.funding_note}
              </div>
            </div>

            <div className="eq-metrics">
              <Metric label="Deal cash flow"
                      value={`${fmtSigned(result.economics.cash_flow)}/mo`}
                      tone={result.economics.cash_flow < 0 ? 'neg' : 'pos'}
                      hint="Before any cost of the money used to buy it." />
              <Metric label="Cap rate"
                      value={result.returns.cap_rate ? `${result.returns.cap_rate}%` : '—'} />
              <Metric label="Cash-on-cash"
                      value={result.returns.cash_on_cash ? `${result.returns.cash_on_cash}%` : '—'} />
              <Metric label="DSCR"
                      value={result.returns.dscr ?? '—'}
                      tone={result.returns.dscr && result.returns.dscr < 1.25 ? 'neg' : ''}
                      hint="Lenders generally want 1.25 or better." />
              <Metric label="Cash needed"
                      value={fmt$(result.financing.total_cash_needed)} />
              <Metric label="Break-even rent"
                      value={fmt$(result.returns.break_even_rent)}
                      hint="Rent at which the property exactly covers itself." />
            </div>

            <div className="eq-sensitivity">
              <div className="eq-sensitivity-title">If things go worse than planned</div>
              {result.sensitivity.map((s) => (
                <div className="eq-sensitivity-row" key={s.label}>
                  <span>{s.label}</span>
                  <span className={s.cash_flow < 0 ? 'neg' : 'pos'}>
                    {fmtSigned(s.cash_flow)}/mo
                  </span>
                </div>
              ))}
            </div>

            <div className="eq-note">{result.assumptions.note}</div>
          </div>
        )}
      </div>
    </section>
  );
}
