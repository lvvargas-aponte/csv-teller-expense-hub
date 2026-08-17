/**
 * Dashboard layout persistence.
 *
 * The backend has stored layouts since the grid dependency was first added;
 * nothing read them until the wealth cards made a customizable dashboard
 * worth having. An empty `layout` means "never saved" — the UI applies its
 * own default rather than rendering nothing.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getLayout = () => axios.get(`${API}/api/dashboard/layout`);

export const saveLayout = ({ layout, hidden }) =>
  axios.put(`${API}/api/dashboard/layout`, { layout, hidden });

export const resetLayout = () => axios.delete(`${API}/api/dashboard/layout`);
