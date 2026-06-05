/**
 * User-facts API — Fin's structured memory.
 *
 * Backs the "Things Fin remembers" panel: list / confirm / reject / edit /
 * delete / manually add facts. The agent writes 'proposed' rows via the
 * remember_about_user tool; the UI surfaces those for the user to curate.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';
const BASE = `${API}/api/user-facts`;

export const listFacts = (params = {}) => axios.get(BASE, { params });

export const createFact = ({ fact, category, tags = [], sensitive = false }) =>
  axios.post(BASE, { fact, category, tags, sensitive });

export const updateFact = (id, patch) => axios.put(`${BASE}/${id}`, patch);

export const confirmFact = (id) => axios.post(`${BASE}/${id}/confirm`);

export const rejectFact = (id) => axios.post(`${BASE}/${id}/reject`);

export const deleteFact = (id) => axios.delete(`${BASE}/${id}`);
