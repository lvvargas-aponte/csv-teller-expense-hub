import { useCallback, useEffect, useMemo, useState } from 'react';
import { getProfile, updateProfile } from '../../api/profile';
import { getCategoryRules, replaceCategoryRules } from '../../api/categoryRules';

const EMPTY_PROFILE = {
  risk_tolerance: '',
  time_horizon_years: '',
  dependents: '',
  monthly_income: '',
  birth_year: '',
  target_retirement_age: '',
  annual_retirement_spend: '',
  expected_return_pct: '',
  debt_strategy: '',
  emergency_fund_months: '',
  notes: '',
};

// Every profile field is held as a string so an untouched input and a
// cleared one look identical in the draft. `''` means "not set" and is
// sent as an explicit null, which the backend treats as a clear.
const profileToDraft = (p) => ({
  risk_tolerance:        p?.risk_tolerance ?? '',
  time_horizon_years:    p?.time_horizon_years ?? '',
  dependents:            p?.dependents ?? '',
  monthly_income:        p?.monthly_income ?? '',
  birth_year:              p?.birth_year ?? '',
  target_retirement_age:   p?.target_retirement_age ?? '',
  annual_retirement_spend: p?.annual_retirement_spend ?? '',
  expected_return_pct:     p?.expected_return_pct ?? '',
  debt_strategy:         p?.debt_strategy ?? '',
  emergency_fund_months: p?.emergency_fund_months ?? '',
  notes:                 p?.notes ?? '',
});

const numOrNull = (v, parse) => {
  if (v === '' || v === null || v === undefined) return null;
  const n = parse(v);
  return Number.isNaN(n) ? null : n;
};

const draftToPayload = (d) => ({
  risk_tolerance:        d.risk_tolerance || null,
  debt_strategy:         d.debt_strategy || null,
  time_horizon_years:    numOrNull(d.time_horizon_years, (v) => parseInt(v, 10)),
  dependents:            numOrNull(d.dependents, (v) => parseInt(v, 10)),
  emergency_fund_months: numOrNull(d.emergency_fund_months, (v) => parseInt(v, 10)),
  monthly_income:        numOrNull(d.monthly_income, parseFloat),
  birth_year:              numOrNull(d.birth_year, (v) => parseInt(v, 10)),
  target_retirement_age:   numOrNull(d.target_retirement_age, (v) => parseInt(v, 10)),
  annual_retirement_spend: numOrNull(d.annual_retirement_spend, parseFloat),
  expected_return_pct:     numOrNull(d.expected_return_pct, parseFloat),
  notes:                 d.notes ?? '',
});

// Rules carry a client-side key so React can track rows that have no id
// yet. It never reaches the server, so it must not count toward dirty.
const rulesToDraft = (rows) =>
  (rows || []).map((r, i) => ({ key: `r${r.id ?? i}`, match: r.match, category: r.category }));

const comparableRules = (rows) =>
  rows.map(({ match, category }) => ({ match, category }));

/**
 * Page-wide draft for Profile & Settings.
 *
 * One draft spans every pane so switching panes never drops an edit and
 * Save commits the whole form at once — that's the design's contract, and
 * it's why dirty state lives here rather than in each pane.
 */
export default function useSettingsDraft() {
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [rules, setRules]     = useState([]);
  const [saved, setSaved]     = useState({ profile: EMPTY_PROFILE, rules: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving]   = useState(false);
  const [saveError, setSaveError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    Promise.all([getProfile(), getCategoryRules()])
      .then(([p, r]) => {
        const nextProfile = profileToDraft(p.data);
        const nextRules   = rulesToDraft(r.data);
        setProfile(nextProfile);
        setRules(nextRules);
        setSaved({ profile: nextProfile, rules: nextRules });
      })
      .catch(() => setLoadError('Could not load settings — is the backend running?'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Restoring a field to its original value clears the bar, so this is a
  // value comparison rather than a "was touched" flag.
  const dirty = useMemo(() => (
    JSON.stringify(profile) !== JSON.stringify(saved.profile)
    || JSON.stringify(comparableRules(rules)) !== JSON.stringify(comparableRules(saved.rules))
  ), [profile, rules, saved]);

  const setProfileField = useCallback((field, value) => {
    setProfile((p) => ({ ...p, [field]: value }));
  }, []);

  const discard = useCallback(() => {
    setProfile(saved.profile);
    setRules(saved.rules);
    setSaveError(null);
  }, [saved]);

  const save = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    try {
      // Blank rows are dropped server-side; mirror that locally so the
      // snapshot we compare against matches what was actually stored.
      const [p, r] = await Promise.all([
        updateProfile(draftToPayload(profile)),
        replaceCategoryRules(
          rules
            .filter((x) => x.match.trim() && x.category.trim())
            .map(({ match, category }) => ({ match: match.trim(), category })),
        ),
      ]);
      const nextProfile = profileToDraft(p.data);
      const nextRules   = rulesToDraft(r.data);
      setProfile(nextProfile);
      setRules(nextRules);
      setSaved({ profile: nextProfile, rules: nextRules });
      return true;
    } catch (e) {
      setSaveError(e.response?.data?.detail || 'Could not save settings — please try again.');
      return false;
    } finally {
      setSaving(false);
    }
  }, [profile, rules]);

  return {
    profile, setProfileField,
    rules, setRules,
    dirty, loading, loadError, saving, saveError,
    save, discard, reload: load,
  };
}
