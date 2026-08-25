import React, { useCallback, useEffect, useState } from 'react';
import Spin from '../ui/Spin';
import { fmt$ } from '../../utils/formatting';
import { getProjection } from '../../api/retirement';
import { updateProfile } from '../../api/profile';

const MISSING_LABEL = {
  birth_year: 'your birth year',
  target_retirement_age: 'the age you want to retire',
  annual_retirement_spend: 'what a year of retirement should cost',
  risk_tolerance: 'your risk tolerance',
};

const METHOD_LABEL = {
  recurring_transfer: 'from tagged transfers',
  snapshot_velocity: 'from balance history',
};

// Compact money for the band and the target — a projection reported to the
// dollar claims the precision that three scenarios exist precisely because
// the inputs lack.
const fmtM = (n) => {
  const v = Math.abs(parseFloat(n) || 0);
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2).replace(/\.?0+$/, '')}M`;
  if (v >= 1e3) return `$${Math.round(v / 1e3)}k`;
  return fmt$(v);
};

// Whole dollars: cents on a figure this uncertain are noise.
const fmtWhole = (n) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
}).format(Math.abs(parseFloat(n) || 0));

const num = (v) => {
  if (v === '' || v === null || v === undefined) return null;
  const n = parseFloat(v);
  return Number.isNaN(n) ? null : n;
};

/**
 * Inline-editable assumption. Committing on blur rather than per keystroke
 * keeps a half-typed "7." from being sent as an assumption.
 */
function Assumption({ id, label, value, suffix, step, onCommit }) {
  const [draft, setDraft] = useState(value ?? '');
  useEffect(() => { setDraft(value ?? ''); }, [value]);

  const commit = () => {
    const parsed = num(draft);
    if (parsed !== value) onCommit(parsed);
  };

  return (
    <label className="ret-assumption" htmlFor={id}>
      <span className="ret-assumption-label">{label}</span>
      <span className="ret-assumption-field">
        <input
          id={id}
          type="number"
          className="form-input"
          step={step}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
        />
        {suffix ? <span className="ret-assumption-suffix">{suffix}</span> : null}
      </span>
    </label>
  );
}

/**
 * RetirementSection — the projection, leading with the gap.
 *
 * Lives under Investments rather than in the sidebar: a projection is a view
 * of the portfolio, not a tenth destination. Every number here is an estimate
 * in today's dollars, and the assumptions that produced it sit on the card so
 * the user can move them and watch the band move.
 */
export default function RetirementSection({ onOpenSettings }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // What-ifs: inflation and the withdrawal rate are house-wide constants with
  // no per-household column, so a nudge changes this view and nothing else.
  const [whatIf, setWhatIf] = useState({});

  const load = useCallback((overrides) => {
    setLoading(true);
    return getProjection(overrides)
      .then((r) => { setData(r.data); setError(null); })
      .catch(() => setError('Could not load the retirement projection.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(whatIf); }, [load, whatIf]);

  const saveToProfile = useCallback((patch) => (
    updateProfile(patch)
      .then(() => load(whatIf))
      .catch(() => setError('Could not save that assumption.'))
  ), [load, whatIf]);

  if (loading && !data) {
    return (
      <div className="finances-section">
        <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin /> Loading…</div>
      </div>
    );
  }

  if (error && !data) {
    return <div className="finances-section" style={{ color: '#ef4444' }}>{error}</div>;
  }

  if (!data) return null;

  const a = data.assumptions || {};

  if (!data.available) {
    const named = (data.missing || []).map((m) => MISSING_LABEL[m] || m);
    return (
      <div className="finances-section">
        <h3 className="finances-section-title" style={{ marginTop: 0 }}>Retirement</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          A projection needs {named.join(', ')}. Nothing here is guessed for you.
        </p>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => onOpenSettings?.('profile')}
        >
          Add it in Profile &amp; settings
        </button>
      </div>
    );
  }

  const short = data.base_shortfall;
  const headline = short
    ? `${fmtWhole(short)} short of a ${fmtM(data.target_pot)} target`
    : `On track for ${fmtM(data.scenarios.base)} against a ${fmtM(data.target_pot)} target`;

  return (
    <div className="finances-section">
      <h3 className="finances-section-title" style={{ marginTop: 0 }}>
        Retirement in {data.years_to_retirement} years
      </h3>

      <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.3 }}>{headline}</div>
      {short ? (
        <div style={{ fontSize: 14, color: 'var(--text-muted)', marginTop: 4 }}>
          About <strong>{fmtWhole(data.required_monthly_for_target)}/month</strong> closes it,
          against the {fmtWhole(data.monthly_contribution)}/month going in now.
        </div>
      ) : (
        <div style={{ fontSize: 14, color: 'var(--text-muted)', marginTop: 4 }}>
          At {fmtWhole(data.monthly_contribution)}/month on {fmtWhole(data.current_balance)} today.
        </div>
      )}

      <div data-testid="retirement-band" className="ret-band">
        <span className="ret-band-end">{fmtM(data.scenarios.low)}</span>
        <span className="ret-band-track">
          <span className="ret-band-base">{fmtM(data.scenarios.base)}</span>
        </span>
        <span className="ret-band-end">{fmtM(data.scenarios.high)}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        Range across a return {a.scenario_spread_pct} points either side of the base
        case, in today&apos;s dollars. An estimate, not a forecast.
      </div>

      <div className="ret-assumptions">
        <Assumption
          id="ret-return" label="Return" suffix="% /yr" step="0.1"
          value={a.nominal_return_pct}
          onCommit={(v) => saveToProfile({ expected_return_pct: v })}
        />
        <Assumption
          id="ret-inflation" label="Inflation" suffix="% /yr" step="0.1"
          value={a.inflation_pct}
          onCommit={(v) => setWhatIf((w) => ({ ...w, inflation_pct: v }))}
        />
        <Assumption
          id="ret-withdrawal" label="Withdrawal rate" suffix="% /yr" step="0.1"
          value={a.withdrawal_rate_pct}
          onCommit={(v) => setWhatIf((w) => ({ ...w, withdrawal_rate_pct: v }))}
        />
        <Assumption
          id="ret-age" label="Retirement age" step="1"
          value={data.retirement_age ?? null}
          onCommit={(v) => saveToProfile({ target_retirement_age: v })}
        />
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        Real return {a.real_return_pct}% after inflation
        {a.source === 'risk_tolerance' ? ' · from your risk tolerance' : ''}
        {a.target_spend_source === 'estimated_from_expenses'
          ? ` · target spend estimated from what you spend today (${fmt$(data.target_annual_spend)}/yr)`
          : ''}
      </div>

      <div className="ret-contrib">
        <div style={{ fontSize: 13 }}>
          <strong>{fmtWhole(data.monthly_contribution)}/month</strong> detected going in
          {(data.contribution_by_account || []).length > 0 && (
            <span style={{ color: 'var(--text-muted)' }}>
              {' — '}
              {data.contribution_by_account
                .map((c) => `${c.name} ${METHOD_LABEL[c.method] || c.method}`)
                .join(', ')}
            </span>
          )}
        </div>
        {data.contribution_caveat && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            {data.contribution_caveat}
          </div>
        )}
      </div>

      {error && <div style={{ marginTop: 10, color: '#ef4444', fontSize: 13 }}>{error}</div>}
    </div>
  );
}
