/**
 * SnapTrade API calls — brokerage/crypto aggregation connect + sync endpoints.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getSnapTradeConfig = () =>
  axios.get(`${API}/api/config/snaptrade`);

// Returns { redirect_uri } — a SnapTrade connection-portal URL to open.
export const connectSnapTrade = () =>
  axios.post(`${API}/api/snaptrade/connect`);

export const syncSnapTrade = () =>
  axios.post(`${API}/api/snaptrade/sync`);

export const listSnapTradeConnections = () =>
  axios.get(`${API}/api/snaptrade/connections`);

export const removeSnapTradeConnection = (id) =>
  axios.delete(`${API}/api/snaptrade/connections/${encodeURIComponent(id)}`);
