import React, { useState } from 'react';

const FIELDS = [
  ['current_age', 'Your age today', ''],
  ['retirement_spending_monthly', 'Monthly spending in retirement',
   'Blank uses your actual trailing spending.'],
  ['monthly_contribution', 'Monthly investing contribution', ''],
  ['investment_return_pct', 'Investment return %', 'Long-run average, before inflation.'],
  ['inflation_pct', 'Inflation %', ''],
  ['rent_growth_pct', 'Rent growth %', ''],
  ['expense_growth_pct', 'Property expense growth %', ''],
  ['appreciation_pct', 'Property appreciation %', ''],
  ['safe_withdrawal_rate_pct', 'Safe withdrawal rate %',
   'What you can draw from investments each year without running out.'],
  ['social_security_monthly', 'Social Security (monthly)', ''],
  ['social_security_start_age', 'Social Security starts at age', ''],
  ['tax_rate_on_withdrawals_pct', 'Tax on withdrawals %', ''],
  ['effective_tax_rate_on_rental_pct', 'Tax on rental income %', ''],
  ['horizon_years', 'Project how many years', ''],
];

const num = (v) => (v === '' || v === null || v === undefined ? null : parseFloat(v));

export default function AssumptionsForm({ assumptions, onSave, onWhatIf, saving }) {
  const [draft, setDraft] = useState(() => ({ ...assumptions }));
  const [open, setOpen] = useState(false);

  const set = (key) => (e) => setDraft((d) => ({ ...d, [key]: e.target.value }));

  const payload = () => Object.fromEntries(
    FIELDS.map(([key]) => [key, num(draft[key])]).filter(([, v]) => v !== null)
  );

  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">Assumptions</div>
        <div className="ov-card-subtitle">
          Every number below is a guess about the future. Change one and see
          how much the answer moves.
        </div>
      </div>

      <div className="ov-card-body">
        <button
          type="button"
          className="ret-toggle"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          {open ? '▾ Hide assumptions' : '▸ Show and edit assumptions'}
        </button>

        {open && (
          <>
            <div className="prop-form-grid ret-assumptions">
              {FIELDS.map(([key, label, hint]) => (
                <label className="prop-field" key={key}>
                  <span className="prop-field-label">{label}</span>
                  <input
                    type="number"
                    step="any"
                    value={draft[key] ?? ''}
                    onChange={set(key)}
                  />
                  {hint && <span className="ret-hint">{hint}</span>}
                </label>
              ))}
            </div>

            <div className="modal-actions">
              <button type="button" onClick={() => onWhatIf(payload())}>
                Try it without saving
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={() => onSave(payload())}
                disabled={saving}
              >
                {saving ? 'Saving…' : 'Save assumptions'}
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
