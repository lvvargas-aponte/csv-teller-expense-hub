import React from 'react';
import Field from '../../ui/Field';
import SettingsCard from '../SettingsCard';
import SegmentedRadio from '../SegmentedRadio';

const RISK_OPTIONS = [
  { value: 'conservative', label: 'Conservative' },
  { value: 'balanced',     label: 'Balanced' },
  { value: 'aggressive',   label: 'Aggressive' },
];

const DEBT_OPTIONS = [
  { value: '',          label: 'Not set' },
  { value: 'avalanche', label: 'Avalanche — highest APR first' },
  { value: 'snowball',  label: 'Snowball — smallest balance first' },
  { value: 'minimum',   label: 'Minimum payments only' },
];

const EMERGENCY_OPTIONS = [
  { value: '',   label: 'Not set' },
  { value: '3',  label: '3 months' },
  { value: '6',  label: '6 months' },
  { value: '9',  label: '9 months' },
  { value: '12', label: '12 months' },
];

export default function FinancialProfilePane({ profile, onChange }) {
  const set = (field) => (e) => onChange(field, e.target.value);

  return (
    <>
      <div className="set-pane-head">
        <h2 className="set-pane-title">Financial profile</h2>
        <p className="set-pane-desc">
          These answers shape the recommendations your AI advisor makes. All
          optional — the more you fill in, the more specific the advice.
        </p>
      </div>

      <SettingsCard title="Risk &amp; horizon">
        <div className="set-field-block">
          <span className="field-label" id="risk-label">Risk tolerance</span>
          <SegmentedRadio
            label="Risk tolerance"
            value={profile.risk_tolerance}
            onChange={(v) => onChange('risk_tolerance', v)}
            options={RISK_OPTIONS}
          />
          <div className="set-help">
            How much short-term volatility you&apos;re willing to accept for
            higher expected returns.
          </div>
        </div>

        <div className="set-grid3">
          <Field label="Horizon (years)">
            <input
              className="form-input set-input--num" type="number"
              min="0" max="60" step="1" placeholder="25"
              value={profile.time_horizon_years}
              onChange={set('time_horizon_years')}
            />
          </Field>
          <Field label="Dependents">
            <input
              className="form-input set-input--num" type="number"
              min="0" max="20" step="1" placeholder="0"
              value={profile.dependents}
              onChange={set('dependents')}
            />
          </Field>
          <Field label="Monthly take-home">
            <input
              className="form-input set-input--num" type="number"
              min="0" step="0.01" placeholder="$0.00"
              value={profile.monthly_income}
              onChange={set('monthly_income')}
            />
          </Field>
        </div>
      </SettingsCard>

      <SettingsCard title="Debt &amp; reserves">
        <div className="set-grid2">
          <Field
            label="Debt-payoff strategy"
            hint="Avalanche saves the most interest. Snowball gives faster wins."
          >
            <select
              className="form-input"
              value={profile.debt_strategy}
              onChange={set('debt_strategy')}
            >
              {DEBT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field
            label="Emergency fund target"
            hint="Months of expenses you want held in cash."
          >
            <select
              className="form-input"
              value={profile.emergency_fund_months}
              onChange={set('emergency_fund_months')}
            >
              {EMERGENCY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
        </div>
      </SettingsCard>

      <SettingsCard title="Context" hint="optional">
        <Field
          label="Notes for the advisor"
          hint="Anything that changes the advice — irregular income, a move, a big purchase coming."
        >
          <textarea
            className="form-input set-textarea"
            placeholder="e.g. self-employed, income varies month to month, HCOL area…"
            value={profile.notes}
            onChange={set('notes')}
          />
        </Field>
      </SettingsCard>
    </>
  );
}
