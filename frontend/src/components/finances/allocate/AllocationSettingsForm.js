import React, { useState } from 'react';

// Only the facts the waterfall genuinely cannot derive from transactions.
// Everything else — income, bills, debt rates, property equity — already
// comes from the data, and asking for it again would be a second source of
// truth to keep in sync.
const NUMBER_FIELDS = [
  ['emergency_fund_months', 'Emergency fund target (months)',
   'How many months of bills and debt minimums to hold in cash before investing.'],
  ['annual_gross_income', 'Annual gross pay',
   'Only used to size the employer match — nothing else reads it.'],
  ['employer_match_pct', 'Employer match (cents per dollar)',
   'A 50% match means they add 50c for every $1 you contribute.'],
  ['employer_match_limit_pct_of_pay', 'Matched up to (% of pay)', ''],
];

const LIMIT_FIELDS = [
  ['401k', '401(k)'],
  ['ira', 'IRA'],
  ['hsa', 'HSA'],
];

const num = (v) => (v === '' || v === null || v === undefined ? null : parseFloat(v));

export default function AllocationSettingsForm({ settings, onSave, saving }) {
  const [draft, setDraft] = useState(() => ({ ...settings }));
  const [ytd, setYtd] = useState(() => ({ ...(settings.contributed_ytd || {}) }));
  const [open, setOpen] = useState(false);

  const set = (key) => (e) => setDraft((d) => ({ ...d, [key]: e.target.value }));
  const setYtdKey = (key) => (e) => setYtd((y) => ({ ...y, [key]: e.target.value }));

  // `employer_match_known` is tri-state on purpose: null means unanswered,
  // which is what makes the waterfall ask instead of assuming no match.
  const matchKnown = draft.employer_match_known;

  const submit = () => {
    const payload = {};
    NUMBER_FIELDS.forEach(([key]) => {
      const v = num(draft[key]);
      if (v !== null && !Number.isNaN(v)) payload[key] = v;
    });
    if (matchKnown !== null && matchKnown !== undefined) {
      payload.employer_match_known = matchKnown === true || matchKnown === 'true';
    }
    const contributed = {};
    LIMIT_FIELDS.forEach(([key]) => {
      const v = num(ytd[key]);
      if (v !== null && !Number.isNaN(v)) contributed[key] = v;
    });
    if (Object.keys(contributed).length) payload.contributed_ytd = contributed;
    onSave(payload);
  };

  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">What the waterfall needs to know</div>
        <div className="ov-card-subtitle">
          Four facts it can&apos;t read from your transactions. Leave one blank
          and it asks rather than guessing.
        </div>
      </div>

      <div className="ov-card-body">
        <button
          type="button"
          className="ret-toggle"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          {open ? '▾ Hide settings' : '▸ Show and edit settings'}
        </button>

        {open && (
          <>
            <fieldset className="alloc-fieldset">
              <legend>Does your employer match retirement contributions?</legend>
              {[['yes', true], ['no', false]].map(([label, value]) => (
                <label className="alloc-radio" key={label}>
                  <input
                    type="radio"
                    name="employer_match_known"
                    checked={matchKnown === value || matchKnown === String(value)}
                    onChange={() => setDraft((d) => ({ ...d, employer_match_known: value }))}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </fieldset>

            <div className="prop-form-grid ret-assumptions">
              {NUMBER_FIELDS.map(([key, label, hint]) => (
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

            <div className="ov-card-subtitle alloc-subhead">
              Contributed so far in {settings.contribution_limits_as_of_year}
            </div>
            <div className="prop-form-grid ret-assumptions">
              {LIMIT_FIELDS.map(([key, label]) => (
                <label className="prop-field" key={key}>
                  <span className="prop-field-label">{label}</span>
                  <input
                    type="number"
                    step="any"
                    value={ytd[key] ?? ''}
                    onChange={setYtdKey(key)}
                  />
                  <span className="ret-hint">
                    Limit ${(settings.annual_contribution_limits?.[key] ?? 0).toLocaleString()}
                  </span>
                </label>
              ))}
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="btn-primary"
                onClick={submit}
                disabled={saving}
              >
                {saving ? 'Saving…' : 'Save settings'}
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
