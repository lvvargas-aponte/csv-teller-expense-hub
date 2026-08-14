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

// PUT /transactions/{id} replaces the shared-expense block wholesale, so every
// field must be re-sent even when only one is changing.
export const putTransactionFields = (txn, patch) =>
  updateTransaction(txn.id, {
    is_shared:     !!txn.is_shared,
    who:           txn.who   || '',
    what:          txn.what  || '',
    notes:         txn.notes || '',
    person_1_owes: txn.person_1_owes || 0,
    person_2_owes: txn.person_2_owes || 0,
    reviewed:      !!txn.reviewed,
    ...patch,
  });

export const bulkUpdateTransactions = (data) =>
  axios.put(`${API}/api/transactions/bulk`, data);

export const bulkSuggestCategories = (transaction_ids) =>
  axios.post(`${API}/api/transactions/suggest-categories/bulk`, { transaction_ids });

export const applyCategoryAssignments = (items) =>
  axios.put(`${API}/api/transactions/categories`, { items });

export const syncTeller = (body) =>
  axios.post(`${API}/api/teller/sync`, body);

export const deleteTransaction = (id) =>
  axios.delete(`${API}/api/transactions/${encodeURIComponent(id)}`);

export const previewDuplicates = () =>
  axios.post(`${API}/api/transactions/dedupe`, { mode: 'preview' });

export const applyDeduplication = () =>
  axios.post(`${API}/api/transactions/dedupe`, { mode: 'apply' });

export const getPersonNames = () =>
  axios.get(`${API}/api/config/person-names`);

export const sendToSheet = (body) =>
  axios.post(`${API}/api/send-to-gsheet`, body);
