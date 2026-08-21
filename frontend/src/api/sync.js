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
  axios.put(`${API}/api/sync/peer-rows/${txnId}/dispute`, body);
