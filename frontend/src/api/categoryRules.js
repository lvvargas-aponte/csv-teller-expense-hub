/**
 * Category rules API — standing "this description + amount is always
 * category X" decisions, applied automatically on CSV upload and SimpleFIN
 * sync.
 *
 * Saving a rule never touches existing transactions; `applyCategoryRules`
 * with mode 'preview' reports what would change and mode 'apply' writes it.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listCategoryRules = () =>
  axios.get(`${API}/api/category-rules`);

export const createCategoryRule = (data) =>
  axios.post(`${API}/api/category-rules`, data);

export const updateCategoryRule = (id, data) =>
  axios.put(`${API}/api/category-rules/${encodeURIComponent(id)}`, data);

export const deleteCategoryRule = (id) =>
  axios.delete(`${API}/api/category-rules/${encodeURIComponent(id)}`);

export const applyCategoryRules = ({ mode = 'preview', ruleId = null, overwrite = false } = {}) =>
  axios.post(`${API}/api/category-rules/apply`, {
    mode,
    rule_id: ruleId,
    overwrite,
  });
