/**
 * Auto-categorization rules — merchant substring → category, evaluated in
 * list order with the first match winning.
 *
 * PUT replaces the whole list rather than patching rows: the settings page
 * saves edits, reorders, and deletions together, and a partial apply would
 * leave the evaluation order meaningless.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getCategoryRules = () =>
  axios.get(`${API}/api/category-rules`);

export const replaceCategoryRules = (rules) =>
  axios.put(`${API}/api/category-rules`, { rules });
