/**
 * Budgets API — monthly per-category caps.  GET returns enriched status
 * (current_month_spent, percent_used, over_budget).
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listBudgets = () =>
  axios.get(`${API}/api/budgets`);

export const upsertBudget = (category, data) =>
  axios.put(`${API}/api/budgets/${encodeURIComponent(category)}`, data);

export const deleteBudget = (category) =>
  axios.delete(`${API}/api/budgets/${encodeURIComponent(category)}`);
