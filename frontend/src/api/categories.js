/**
 * Categories API.
 *
 * A category is a row now, not a string derived from whatever transactions
 * happen to carry — so it can be renamed, merged, archived and given roles.
 * Roles are what analytics reads to decide whether a category marks a bill,
 * a subscription, or money that never left the household.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listCategories = () =>
  axios.get(`${API}/api/categories`);

export const deleteCategory = (name) =>
  axios.delete(`${API}/api/categories/${encodeURIComponent(name)}`);

export const listCategoryRows = (includeArchived = false) =>
  axios.get(`${API}/api/categories`, { params: { include_archived: includeArchived } });

export const createCategory = (name, { color = null, roles = null } = {}) =>
  axios.post(`${API}/api/categories`, { name, color, roles });

export const patchCategory = (id, fields) =>
  axios.patch(`${API}/api/categories/${id}`, fields);

/** Rename everywhere at once. Renaming onto an existing name merges. */
export const renameCategory = (id, name) =>
  axios.post(`${API}/api/categories/${id}/rename`, { name });

/** Fold one category into another; the survivor keeps both role sets. */
export const mergeCategory = (id, intoId) =>
  axios.post(`${API}/api/categories/${id}/merge`, { into_id: intoId });

export const deleteCategoryById = (id) =>
  axios.delete(`${API}/api/categories/id/${id}`);

/** Group under a parent (one level), or ungroup with null. */
export const setCategoryParent = (id, parentId) =>
  axios.post(`${API}/api/categories/${id}/parent`, { parent_id: parentId });
