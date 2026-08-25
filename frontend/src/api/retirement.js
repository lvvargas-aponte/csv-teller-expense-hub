/**
 * Retirement projection — a single read-only estimate.
 *
 * `overrides` are what-if assumptions the card lets the user nudge without
 * committing them to the household profile. Return and retirement age are
 * real profile fields and are saved through `api/profile` instead.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getProjection = (overrides = {}) =>
  axios.get(`${API}/api/retirement/projection`, {
    params: Object.fromEntries(
      Object.entries(overrides).filter(([, v]) => v !== null && v !== undefined && v !== ''),
    ),
  });
