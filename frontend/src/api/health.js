/**
 * Health API — the household financial health score, computed backend-side
 * so the sidebar and the dashboard read one number from one source.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getHealthScore = () => axios.get(`${API}/api/health/score`);

// Savings rate, emergency-fund runway and debt-to-income.
export const getRatios = () => axios.get(`${API}/api/health/ratios`);
