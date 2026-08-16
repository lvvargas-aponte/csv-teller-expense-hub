import React, { useState } from 'react';

import Backdrop from '../../ui/Backdrop';
import { Z_BACKDROP_DIALOG } from '../../../utils/zIndex';

const EMPTY = {
  name: '', address: '', property_type: 'single_family', status: 'rental', units: 1,
  purchase_date: '', purchase_price: '', closing_costs: '', capital_improvements: '',
  monthly_rent: '', other_monthly_income: '', vacancy_rate_pct: 5,
  property_tax_annual: '', insurance_annual: '', hoa_monthly: '',
  utilities_monthly: '', landscaping_monthly: '', other_monthly_expense: '',
  mgmt_fee_pct: 0, maintenance_pct_of_rent: 5, capex_reserve_pct_of_rent: 5,
  notes: '',
};

const PROPERTY_TYPES = [
  ['single_family', 'Single family'], ['multi_family', 'Multi-family'],
  ['condo', 'Condo'], ['townhouse', 'Townhouse'],
  ['land', 'Land'], ['commercial', 'Commercial'],
];

const STATUSES = [
  ['rental', 'Rental'], ['primary_residence', 'Primary residence'],
  ['vacation', 'Vacation'], ['held_for_sale', 'Held for sale'],
  ['under_renovation', 'Under renovation'],
];

// Blank numeric inputs mean "not recorded", which is different from zero —
// cash-on-cash deliberately returns null without a purchase price rather
// than inventing a denominator. Send null, not 0.
const num = (v) => (v === '' || v === null || v === undefined ? null : parseFloat(v));

export default function PropertyForm({ initial, onSubmit, onClose, saving }) {
  const [draft, setDraft] = useState(() => ({ ...EMPTY, ...(initial || {}) }));
  const [error, setError] = useState(null);

  const set = (key) => (e) => setDraft((d) => ({ ...d, [key]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    if (!draft.name.trim()) { setError('Give the property a name.'); return; }
    setError(null);
    onSubmit({
      ...draft,
      name: draft.name.trim(),
      units: parseInt(draft.units, 10) || 1,
      purchase_date: draft.purchase_date || null,
      purchase_price: num(draft.purchase_price),
      closing_costs: num(draft.closing_costs) ?? 0,
      capital_improvements: num(draft.capital_improvements) ?? 0,
      monthly_rent: num(draft.monthly_rent) ?? 0,
      other_monthly_income: num(draft.other_monthly_income) ?? 0,
      vacancy_rate_pct: num(draft.vacancy_rate_pct) ?? 0,
      property_tax_annual: num(draft.property_tax_annual) ?? 0,
      insurance_annual: num(draft.insurance_annual) ?? 0,
      hoa_monthly: num(draft.hoa_monthly) ?? 0,
      utilities_monthly: num(draft.utilities_monthly) ?? 0,
      landscaping_monthly: num(draft.landscaping_monthly) ?? 0,
      other_monthly_expense: num(draft.other_monthly_expense) ?? 0,
      mgmt_fee_pct: num(draft.mgmt_fee_pct) ?? 0,
      maintenance_pct_of_rent: num(draft.maintenance_pct_of_rent) ?? 0,
      capex_reserve_pct_of_rent: num(draft.capex_reserve_pct_of_rent) ?? 0,
    });
  };

  const field = (key, label, type = 'number', extra = {}) => (
    <label className="prop-field">
      <span className="prop-field-label">{label}</span>
      <input
        type={type}
        value={draft[key] ?? ''}
        onChange={set(key)}
        step={type === 'number' ? 'any' : undefined}
        {...extra}
      />
    </label>
  );

  return (
    <Backdrop onClose={onClose} zIndex={Z_BACKDROP_DIALOG}>
      <form className="modal prop-form" onSubmit={submit}>
        <h3>{initial?.name ? 'Edit property' : 'Add a property'}</h3>

        <div className="prop-form-grid">
          {field('name', 'Name', 'text')}
          {field('address', 'Address', 'text')}

          <label className="prop-field">
            <span className="prop-field-label">Type</span>
            <select value={draft.property_type} onChange={set('property_type')}>
              {PROPERTY_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>

          <label className="prop-field">
            <span className="prop-field-label">Status</span>
            <select value={draft.status} onChange={set('status')}>
              {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>

          {field('units', 'Units')}
          {field('purchase_date', 'Purchase date', 'date')}
          {field('purchase_price', 'Purchase price')}
          {field('closing_costs', 'Closing costs')}
          {field('capital_improvements', 'Capital improvements')}
        </div>

        <div className="prop-form-section">Income</div>
        <div className="prop-form-grid">
          {field('monthly_rent', 'Monthly rent')}
          {field('other_monthly_income', 'Other monthly income')}
          {field('vacancy_rate_pct', 'Vacancy %')}
        </div>

        <div className="prop-form-section">
          Operating expenses
          <span className="prop-form-hint">
            Excludes the mortgage — debt service is tracked on the loan.
          </span>
        </div>
        <div className="prop-form-grid">
          {field('property_tax_annual', 'Property tax (annual)')}
          {field('insurance_annual', 'Insurance (annual)')}
          {field('hoa_monthly', 'HOA (monthly)')}
          {field('utilities_monthly', 'Utilities (monthly)')}
          {field('landscaping_monthly', 'Landscaping (monthly)')}
          {field('other_monthly_expense', 'Other (monthly)')}
          {field('mgmt_fee_pct', 'Management % of rent collected')}
          {field('maintenance_pct_of_rent', 'Maintenance % of rent')}
          {field('capex_reserve_pct_of_rent', 'CapEx reserve % of rent')}
        </div>

        {error && <div className="ov-error">{error}</div>}

        <div className="modal-actions">
          <button type="button" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save property'}
          </button>
        </div>
      </form>
    </Backdrop>
  );
}
