/**
 * Auto-categorization rules.
 *
 * Two kinds. A `merchant` rule matches the whole normalized merchant key
 * and is created from the transactions table when you categorize a row —
 * "always categorize CHIPOTLE as Dining". A `contains` rule is the
 * substring test the settings form owns, evaluated in list order.
 *
 * PUT replaces the whole `contains` list rather than patching rows: the
 * settings form saves edits, reorders and deletions together, and a partial
 * apply would leave the evaluation order meaningless. Merchant rules carry
 * their own identity and use the per-row endpoints below.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getCategoryRules = () =>
  axios.get(`${API}/api/category-rules`);

export const replaceCategoryRules = (rules) =>
  axios.put(`${API}/api/category-rules`, { rules });

/** The merchant key for a description, plus any rule already on it. */
export const getRuleForMerchant = (description) =>
  axios.get(`${API}/api/category-rules/for-merchant`, { params: { description } });

/** What a rule would do to transactions already imported, without writing. */
export const previewCategoryRule = (pattern, category, kind = 'merchant') =>
  axios.post(`${API}/api/category-rules/preview`, { pattern, category, kind });

export const createCategoryRule = (
  pattern, category, { kind = 'merchant', applyToExisting = false } = {},
) => axios.post(`${API}/api/category-rules`, {
  pattern, category, kind, apply_to_existing: applyToExisting,
});

export const patchCategoryRule = (id, fields) =>
  axios.patch(`${API}/api/category-rules/${id}`, fields);

export const deleteCategoryRule = (id) =>
  axios.delete(`${API}/api/category-rules/${id}`);

/** Sweep an existing rule over the transactions already imported. */
export const applyCategoryRule = (id) =>
  axios.post(`${API}/api/category-rules/${id}/apply`);
