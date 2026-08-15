/**
 * Balances API calls — all axios calls for balances and manual account endpoints.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getBalancesSummary = (force = false) =>
  axios.get(`${API}/api/balances/summary`, { params: { force } });

export const addManualAccount = (data) =>
  axios.post(`${API}/api/balances/manual`, data);

// Works for any account — manual, csv-synth, or SimpleFIN-cached.
export const updateAccountBalance = (id, data) =>
  axios.put(`${API}/api/balances/${encodeURIComponent(id)}`, data);

export const deleteManualAccount = (id) =>
  axios.delete(`${API}/api/balances/manual/${encodeURIComponent(id)}`);
