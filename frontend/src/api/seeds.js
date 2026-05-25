/**
 * Seeds API — runtime-editable curated reading list.
 *
 * Backend merges the JSON defaults with DB overrides; this client just
 * passes calls through.  Seed ids are strings: ``"d:irs-pub-17"`` for
 * defaults, ``"c:42"`` for customs.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listSeeds = () =>
  axios.get(`${API}/api/seeds`);

export const listHiddenSeeds = () =>
  axios.get(`${API}/api/seeds/hidden`);

export const addSeed = (payload) =>
  axios.post(`${API}/api/seeds`, payload);

export const deleteSeed = (id) =>
  axios.delete(`${API}/api/seeds/${encodeURIComponent(id)}`);

export const restoreDefault = (defaultId) =>
  axios.post(`${API}/api/seeds/restore/${encodeURIComponent(defaultId)}`);
