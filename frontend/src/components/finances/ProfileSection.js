/**
 * ProfileSection — household preferences the advisor uses to tailor advice.
 *
 * Single-row resource (one profile per household).  Loads on mount, edits
 * stay local until "Save" PUTs the changed fields and the server returns
 * the merged row.  All fields optional — empty strings clear the local
 * draft but the backend ignores nulls so unset fields stay unset.
 */
import React, { useCallback, useEffect, useState } from 'react';
import Field from '../ui/Field';
import Spin from '../ui/Spin';
import { getProfile, updateProfile } from '../../api/profile';

const RISK_OPTIONS = [
  { value: '',             label: '—' },
  { value: 'conservative', label: 'Conservative — capital preservation' },
  { value: 'balanced',     label: 'Balanced — mix of growth and safety' },
  { value: 'aggressive',   label: 'Aggressive — growth-focused, ok with volatility' },
];

const DEBT_OPTIONS = [
  { value: '',          label: '—' },
  { value: 'avalanche', label: 'Avalanche — highest APR first (math-optimal)' },
  { value: 'snowball',  label: 'Snowball — smallest balance first (motivation)' },
  { value: 'minimum',   label: 'Minimum payments only' },
];

export default function ProfileSection() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [error,   setError]   = useState(null);

  // Editable draft — initialized from profile on load, sent on save.
  const [draft, setDraft] = useState({
    risk_tolerance: '',
    time_horizon_years: '',
    dependents: '',
    debt_strategy: '',
    notes: '',
  });

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getProfile()
      .then((r) => {
        setProfile(r.data);
        setDraft({
          risk_tolerance:     r.data?.risk_tolerance     ?? '',
          time_horizon_years: r.data?.time_horizon_years ?? '',
          dependents:         r.data?.dependents         ?? '',
          debt_strategy:      r.data?.debt_strategy      ?? '',
          notes:              r.data?.notes              ?? '',
        });
      })
      .catch(() => setError('Could not load profile.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    // Build a sparse patch: only include fields the user actually filled in.
    // Empty strings on the typed enums mean "leave unchanged" (the backend
    // ignores null/missing keys via exclude_none).
    const patch = {};
    if (draft.risk_tolerance) patch.risk_tolerance = draft.risk_tolerance;
    if (draft.debt_strategy)  patch.debt_strategy  = draft.debt_strategy;
    if (draft.time_horizon_years !== '' && draft.time_horizon_years !== null) {
      patch.time_horizon_years = parseInt(draft.time_horizon_years, 10);
    }
    if (draft.dependents !== '' && draft.dependents !== null) {
      patch.dependents = parseInt(draft.dependents, 10);
    }
    // Notes accept "" to overwrite — distinct from the typed enums.
    if (draft.notes !== profile?.notes) patch.notes = draft.notes;

    try {
      const r = await updateProfile(patch);
      setProfile(r.data);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not save profile.');
    } finally {
      setSaving(false);
    }
  }, [draft, profile]);

  if (loading) {
    return (
      <div className="finances-section">
        <h2 className="finances-section-title">Profile</h2>
        <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin /> Loading…</div>
      </div>
    );
  }

  return (
    <div className="finances-section">
      <h2 className="finances-section-title">Profile</h2>
      <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
        These shape how the AI advisor frames recommendations — risk, time
        horizon, dependents, and debt-payoff strategy.  All fields optional.
      </div>

      <div className="form-row-2">
        <Field label="Risk tolerance">
          <select className="form-input"
                  value={draft.risk_tolerance}
                  onChange={(e) => setDraft((d) => ({ ...d, risk_tolerance: e.target.value }))}>
            {RISK_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Investment time horizon (years)">
          <input className="form-input" type="number" min="0" max="60" step="1"
                 placeholder="e.g. 25"
                 value={draft.time_horizon_years}
                 onChange={(e) => setDraft((d) => ({ ...d, time_horizon_years: e.target.value }))} />
        </Field>
      </div>

      <div className="form-row-2">
        <Field label="Dependents">
          <input className="form-input" type="number" min="0" max="20" step="1"
                 placeholder="e.g. 0"
                 value={draft.dependents}
                 onChange={(e) => setDraft((d) => ({ ...d, dependents: e.target.value }))} />
        </Field>
        <Field label="Debt-payoff strategy">
          <select className="form-input"
                  value={draft.debt_strategy}
                  onChange={(e) => setDraft((d) => ({ ...d, debt_strategy: e.target.value }))}>
            {DEBT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
      </div>

      <Field label="Notes (e.g. one partner is self-employed; we live in a HCOL area)">
        <textarea className="form-input" rows="2"
                  value={draft.notes}
                  onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))} />
      </Field>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
        <button type="button" className="btn btn-primary"
                onClick={handleSave} disabled={saving}>
          {saving ? <><Spin /> Saving…</> : 'Save profile'}
        </button>
        {saved && (
          <span style={{ fontSize: 13, color: 'var(--success, #4ade80)' }}>Saved</span>
        )}
        {error && (
          <span style={{ fontSize: 13, color: '#f87171' }}>{error}</span>
        )}
      </div>
    </div>
  );
}
