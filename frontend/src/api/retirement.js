/**
 * Retirement API — assumptions and the projection.
 *
 * `earliest_retirement_year` is the first year feasibility holds *and keeps
 * holding*. A crossing that later reverses, because inflation outruns a
 * fixed income stream, is not a retirement date and isn't reported as one.
 *
 * The model is deterministic — `monte_carlo` is always false and the
 * `sensitivity` rows stand in for a probability figure. Copy should say so.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getAssumptions = () =>
  axios.get(`${API}/api/retirement/assumptions`);

export const saveAssumptions = (data) =>
  axios.put(`${API}/api/retirement/assumptions`, data);

export const getProjection = ({ asOf, includeSensitivity = true } = {}) =>
  axios.get(`${API}/api/retirement/projection`, {
    params: {
      ...(asOf ? { as_of: asOf } : {}),
      include_sensitivity: includeSensitivity,
    },
  });

/** Run a projection against supplied assumptions without saving them. */
export const runWhatIf = (assumptions) =>
  axios.post(`${API}/api/retirement/projection`, assumptions);
