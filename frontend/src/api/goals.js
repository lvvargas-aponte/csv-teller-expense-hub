/**
 * Goals API — savings + emergency-fund targets.  GET returns enriched status
 * (current_balance, progress_pct, monthly_required).
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listGoals = () =>
  axios.get(`${API}/api/goals`);

export const createGoal = (data) =>
  axios.post(`${API}/api/goals`, data);

export const updateGoal = (id, data) =>
  axios.put(`${API}/api/goals/${id}`, data);

export const deleteGoal = (id) =>
  axios.delete(`${API}/api/goals/${id}`);
