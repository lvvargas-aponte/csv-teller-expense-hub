/**
 * Shared-expense sync API calls — all axios calls for the sync/shared-rows endpoints.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getSharedRows = (period) =>
  axios.get(`${API}/api/sync/shared-rows`, { params: { period } });

export const getSyncStatus = () => axios.get(`${API}/api/sync/status`);

export const syncShared = (body) => axios.post(`${API}/api/sync/shared`, body);

export const acknowledgeCorrection = (id) =>
  axios.post(`${API}/api/sync/corrections/${id}/acknowledge`);

export const setDispute = (txnId, body) =>
  axios.put(`${API}/api/sync/peer-rows/${encodeURIComponent(txnId)}/dispute`, body);

// Settling a month. Advisory on both sides: either instance may declare a
// month paid, and either may reopen only its own declaration.
export const markPeriodReady = (period) =>
  axios.post(`${API}/api/sync/periods/${period}/ready`);

export const withdrawPeriodReady = (period) =>
  axios.delete(`${API}/api/sync/periods/${period}/ready`);

export const markPeriodPaid = (period, note) =>
  axios.post(`${API}/api/sync/periods/${period}/paid`, { note: note || null });

export const reopenPeriod = (period) =>
  axios.delete(`${API}/api/sync/periods/${period}/paid`);
