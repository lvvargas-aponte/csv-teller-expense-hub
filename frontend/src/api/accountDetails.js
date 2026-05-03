/**
 * Account details API — user-supplied metadata (APR, credit limit, statement/due
 * days, minimum payment) for both Teller and manual accounts.  Stored in a
 * side-car `account_details.json` so Teller refreshes don't blow away edits.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getAccountDetails = (accountId) =>
  axios.get(`${API}/api/accounts/${encodeURIComponent(accountId)}/details`);

export const getAllAccountDetails = () =>
  axios.get(`${API}/api/accounts/details`);

export const upsertAccountDetails = (accountId, data) =>
  axios.put(`${API}/api/accounts/${encodeURIComponent(accountId)}/details`, data);

export const deleteAccountDetails = (accountId) =>
  axios.delete(`${API}/api/accounts/${encodeURIComponent(accountId)}/details`);
