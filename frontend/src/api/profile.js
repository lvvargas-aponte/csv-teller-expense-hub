/**
 * User profile — household-wide preferences (risk tolerance, time horizon,
 * dependents, debt strategy).  Single-row resource: GET fetches, PUT
 * partial-merges.  Both return the full current shape.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getProfile = () =>
  axios.get(`${API}/api/profile`);

export const updateProfile = (patch) =>
  axios.put(`${API}/api/profile`, patch);
