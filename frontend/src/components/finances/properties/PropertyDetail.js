import React, { useCallback, useEffect, useState } from 'react';

import Spin from '../../ui/Spin';
import Num from '../Num';
import AmortizationTable from '../loans/AmortizationTable';
import { fmt$, fmtSigned, fmtDate } from '../../../utils/formatting';
import { userMessage } from '../../../utils/errorMessage';
import { addValuation, listValuations } from '../../../api/properties';
import { listLoans } from '../../../api/loans';

const pct = (v) => (v === null || v === undefined ? '—' : `${v.toFixed(2)}%`);
const ratio = (v) => (v === null || v === undefined ? '—' : v.toFixed(2));

function Row({ label, value, hint, emphasis }) {
  return (
    <div className={`prop-row${emphasis ? ' prop-row--emphasis' : ''}`}>
      <span className="prop-row-label" title={hint}>{label}</span>
      <span className="prop-row-value">{value}</span>
    </div>
  );
}

export default function PropertyDetail({ property, onBack, onEdit, onDelete, onChanged }) {
  const [loans, setLoans] = useState([]);
  const [valuations, setValuations] = useState([]);
  const [newValue, setNewValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const pid = property.property_id;

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([listLoans(pid), listValuations(pid)])
      .then(([l, v]) => { setLoans(l.data); setValuations(v.data); })
      .catch((e) => setError(userMessage(e, 'Could not load property detail.')))
      .finally(() => setLoading(false));
  }, [pid]);

  useEffect(load, [load]);

  const saveValuation = async (e) => {
    e.preventDefault();
    const value = parseFloat(newValue);
    if (!value || value <= 0) { setError('Enter a value above zero.'); return; }
    setSaving(true);
    setError(null);
    try {
      await addValuation(pid, { value, source: 'manual' });
      setNewValue('');
      load();
      onChanged?.();
    } catch (e2) {
      setError(userMessage(e2, 'Could not save the valuation.'));
    } finally {
      setSaving(false);
    }
  };

  const proForma = property.pro_forma || {};
  const actual = property.actual || {};
  const performance = property.performance || {};

  return (
    <div className="prop-detail">
      <div className="prop-detail-head">
        <button type="button" className="prop-back" onClick={onBack}>‹ All properties</button>
        <div className="prop-detail-actions">
          <button type="button" onClick={() => onEdit(property)}>Edit</button>
          <button type="button" className="btn-danger" onClick={() => onDelete(property)}>
            Delete
          </button>
        </div>
      </div>

      <h2 className="prop-detail-name">{property.name}</h2>

      <div className="prop-detail-grid">
        <section className="ov-card">
          <div className="ov-card-header">
            <div className="ov-card-title">Monthly economics</div>
            <div className="ov-card-subtitle">
              {property.basis === 'actual'
                ? `From ${actual.months_of_data} months of tagged transactions`
                : 'Projected from your assumptions — tag transactions to switch to actuals'}
            </div>
          </div>
          <div className="ov-card-body">
            <Row label="Gross scheduled rent" value={fmt$(proForma.gross_scheduled_income)} />
            <Row label="Vacancy allowance" value={`− ${fmt$(proForma.vacancy_loss)}`} />
            <Row label="Effective gross income" value={fmt$(proForma.effective_gross_income)} />
            <Row label="Operating expenses" value={`− ${fmt$(proForma.operating_expenses)}`}
                 hint="Taxes, insurance, HOA, utilities, landscaping, management, maintenance and CapEx reserves." />
            <Row label="Net operating income" value={fmt$(proForma.noi)} emphasis
                 hint="Excludes the mortgage — that's what makes cap rate comparable across properties." />
            <Row label="Debt service" value={`− ${fmt$(proForma.debt_service)}`}
                 hint="Principal and interest only. Escrow is already counted in operating expenses." />
            <Row label="Cash flow" emphasis
                 value={<span className={proForma.cash_flow < 0 ? 'neg' : 'pos'}>
                   {fmtSigned(proForma.cash_flow)}
                 </span>} />
          </div>
        </section>

        <section className="ov-card">
          <div className="ov-card-header">
            <div className="ov-card-title">Position &amp; returns</div>
          </div>
          <div className="ov-card-body">
            <Row label="Current value" value={<Num value={property.current_value} />} />
            <Row label="Debt" value={<Num value={property.total_debt} />} />
            <Row label="Equity" value={<Num value={property.equity} />} emphasis />
            <Row label="LTV" value={pct(property.ltv)} />
            <Row label="Cap rate" value={pct(property.cap_rate)} />
            <Row label="Cash-on-cash" value={pct(property.cash_on_cash)}
                 hint="Annual cash flow over cash invested. Needs a recorded purchase price." />
            <Row label="DSCR" value={ratio(property.dscr)} />
            <Row label="Principal paid down" value={<Num value={property.ytd_principal_paid} />}
                 hint="How much of the loan the rent has retired so far." />
          </div>
        </section>
      </div>

      <section className={`prop-verdict prop-verdict--${performance.rating || 'strong'}`}>
        <div className="prop-verdict-title">
          {performance.rating === 'underperforming' ? 'Underperforming'
            : performance.rating === 'watch' ? 'Worth watching'
            : performance.rating === 'not_rated' ? 'Not held as a rental'
            : 'Performing'}
        </div>
        <ul>
          {(performance.reasons || []).map((r) => <li key={r}>{r}</li>)}
        </ul>
        {(performance.notes || []).length > 0 && (
          <ul className="prop-verdict-notes">
            {performance.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        )}
      </section>

      {loading ? <Spin /> : (
        <>
          {loans.map((loan) => (
            <AmortizationTable key={loan.id} loan={loan} />
          ))}
          {loans.length === 0 && (
            <div className="prop-empty-inline">
              No loan attached. Add one from the Loans tab to see the
              interest-versus-principal split.
            </div>
          )}
        </>
      )}

      <section className="ov-card">
        <div className="ov-card-header">
          <div className="ov-card-title">Valuations</div>
          <div className="ov-card-subtitle">
            Equity and LTV are only as current as the newest value here.
          </div>
        </div>
        <div className="ov-card-body">
          <form className="prop-valuation-form" onSubmit={saveValuation}>
            <input
              type="number"
              step="any"
              placeholder="Current value"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              aria-label="New valuation"
            />
            <button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Record value'}
            </button>
          </form>
          {error && <div className="ov-error">{error}</div>}
          <table className="prop-valuation-table">
            <tbody>
              {valuations.map((v) => (
                <tr key={v.as_of}>
                  <td>{fmtDate(v.as_of)}</td>
                  <td>{v.source}</td>
                  <td className="prop-valuation-amount"><Num value={v.value} /></td>
                </tr>
              ))}
              {valuations.length === 0 && (
                <tr><td colSpan={3} className="prop-empty-inline">No valuations recorded yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
