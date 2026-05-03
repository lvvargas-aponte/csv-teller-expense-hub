/**
 * Transaction API calls — all axios calls for transaction-related endpoints.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getAllTransactions = () =>
  axios.get(`${API}/api/transactions/all`);

export const uploadCSV = (file) => {
  const fd = new FormData();
  fd.append('file', file);
  return axios.post(`${API}/api/upload-csv`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const updateTransaction = (id, data) =>
  axios.put(`${API}/api/transactions/${encodeURIComponent(id)}`, data);

export const bulkUpdateTransactions = (data) =>
  axios.put(`${API}/api/transactions/bulk`, data);

export const bulkSuggestCategories = (transaction_ids) =>
  axios.post(`${API}/api/transactions/suggest-categories/bulk`, { transaction_ids });

export const applyCategoryAssignments = (items) =>
  axios.put(`${API}/api/transactions/categories`, { items });

export const syncTeller = (body) =>
  axios.post(`${API}/api/teller/sync`, body);

export const getPersonNames = () =>
  axios.get(`${API}/api/config/person-names`);

export const sendToSheet = (body) =>
  axios.post(`${API}/api/send-to-gsheet`, body);
