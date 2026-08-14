/**
 * Weekly digest API — lazily generated summary with unread state.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getLatestDigest = (force = false) =>
  axios.get(`${API}/api/digest/latest`, { params: force ? { force: true } : {} });

export const markDigestRead = (id) =>
  axios.post(`${API}/api/digest/${id}/read`);