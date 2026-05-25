/**
 * Investments API calls — read-only holdings + portfolio aggregation.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

// Holdings grouped by account: { accounts: [...], holding_count }.
export const getHoldings = () =>
  axios.get(`${API}/api/investments/holdings`);

// Aggregated portfolio: totals, allocation, concentration, by_account, holdings.
export const getPortfolio = () =>
  axios.get(`${API}/api/investments/portfolio`);
