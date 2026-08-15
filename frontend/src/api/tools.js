/**
 * Tools API — the debt-payoff calculator and its optional AI narration.
 *
 * `payoffPlan` is deterministic and always available. `payoffAdvice` needs a
 * local Ollama; it resolves with `{ ai_available: false }` rather than
 * throwing when Ollama is unreachable, so callers must check that flag.
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
