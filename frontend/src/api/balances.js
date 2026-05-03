/**
 * Balances API calls — all axios calls for balances and manual account endpoints.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getBalancesSummary = (force = false) =>
  axios.get(`${API}/api/balances/summary`, { params: { force } });

export const addManualAccount = (data) =>
  axios.post(`${API}/api/balances/manual`, data);

// Works for any account — manual, csv-synth, or Teller-cached.
export const updateAccountBalance = (id, data) =>
  axios.put(`${API}/api/balances/${encodeURIComponent(id)}`, data);

export const deleteManualAccount = (id) =>
  axios.delete(`${API}/api/balances/manual/${encodeURIComponent(id)}`);

export const getTellerAccounts = () =>
  axios.get(`${API}/api/accounts`);

export const deleteTellerAccount = (id) =>
  axios.delete(`${API}/api/accounts/${id}`);

export const registerTellerToken = (data) =>
  axios.post(`${API}/api/teller/register-token`, data);

export const replaceTellerToken = (data) =>
  axios.post(`${API}/api/teller/replace-token`, data);

export const getTellerConfig = () =>
  axios.get(`${API}/api/config/teller`);
