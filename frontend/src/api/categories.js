/**
 * Categories API — the union of known categories (distinct txn categories +
 * budget categories + categorizer defaults).
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listCategories = () =>
  axios.get(`${API}/api/categories`);

export const deleteCategory = (name) =>
  axios.delete(`${API}/api/categories/${encodeURIComponent(name)}`);
