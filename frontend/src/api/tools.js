/**
 * Tools API — the debt-payoff calculator, the allocation waterfall, and the
 * optional AI narration.
 *
 * `payoffPlan` and `allocate` are deterministic and always available.
 * `payoffAdvice` needs a local Ollama; it resolves with
 * `{ ai_available: false }` rather than throwing when Ollama is unreachable,
 * so callers must check that flag.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const payoffPlan = ({ accounts, strategy, extraMonthly }) =>
  axios.post(`${API}/api/tools/payoff-plan`, {
    accounts,
    strategy,
    extra_monthly: extraMonthly,
  });

export const payoffAdvice = ({ accounts, strategy, extraMonthly, planResults }) =>
  axios.post(`${API}/api/tools/payoff-advice`, {
    accounts,
    strategy,
    extra_monthly: extraMonthly,
    plan_results: planResults ?? undefined,
  });

// `cadence` is 'monthly' for a recurring surplus or 'one_time' for a bonus —
// the tiers genuinely differ, since an employer match only arrives through
// payroll and a lump sum can't reach it.
export const allocate = ({ amount, cadence = 'monthly' }) =>
  axios.post(`${API}/api/tools/allocate`, { amount, cadence });

export const getAllocationSettings = () =>
  axios.get(`${API}/api/tools/allocation-settings`);

export const saveAllocationSettings = (payload) =>
  axios.put(`${API}/api/tools/allocation-settings`, payload);
