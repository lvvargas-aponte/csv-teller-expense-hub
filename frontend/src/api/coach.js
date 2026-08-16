/**
 * Coach API — ranked next actions.
 *
 * `/api/alerts` answers "what's wrong?"; this answers "what should I do?".
 * Every action carries a dollar amount and, where one exists, a deadline.
 *
 * Narration is optional voice-over from a local LLM. It never originates a
 * number — the backend discards any narration containing a figure the rules
 * didn't produce — so callers can render it verbatim, or not at all.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getActions = (limit = 6) =>
  axios.get(`${API}/api/coach/actions`, { params: { limit } });

export const getNarration = (limit = 3) =>
  axios.post(`${API}/api/coach/narrate`, null, { params: { limit } });

export const dismissAction = (actionId) =>
  axios.post(`${API}/api/coach/actions/${encodeURIComponent(actionId)}/dismiss`);

export const undismissAction = (actionId) =>
  axios.delete(`${API}/api/coach/actions/${encodeURIComponent(actionId)}/dismiss`);
