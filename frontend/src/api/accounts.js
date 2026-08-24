/**
 * Account listing and removal — every axios call for the /api/accounts endpoints.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listAccounts = () => axios.get(`${API}/api/accounts`);

// Default disconnect keeps the local record so transactions, last-known
// balance, and APR/limit details survive a later reconnect. `purge` deletes it.
export const disconnectAccount = (accountId) =>
  axios.delete(`${API}/api/accounts/${accountId}`);

export const purgeAccount = (accountId) =>
  axios.delete(`${API}/api/accounts/${accountId}`, { params: { purge: true } });
