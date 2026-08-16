/**
 * Properties API — real-estate holdings and their economics.
 *
 * Every read returns economics computed on the fly (NOI, cash flow, cap
 * rate, DSCR, equity), so a rent change or new valuation shows up
 * immediately rather than waiting for a recalculation step.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listProperties = () =>
  axios.get(`${API}/api/properties`);

export const getPortfolio = () =>
  axios.get(`${API}/api/properties/portfolio`);

export const getProperty = (id) =>
  axios.get(`${API}/api/properties/${encodeURIComponent(id)}`);

export const createProperty = (data) =>
  axios.post(`${API}/api/properties`, data);

export const updateProperty = (id, data) =>
  axios.put(`${API}/api/properties/${encodeURIComponent(id)}`, data);

export const deleteProperty = (id) =>
  axios.delete(`${API}/api/properties/${encodeURIComponent(id)}`);

export const listValuations = (id) =>
  axios.get(`${API}/api/properties/${encodeURIComponent(id)}/valuations`);

/** Only moves current_value when it's the newest on file, so backfilling an
 *  old appraisal can't clobber a current number. */
export const addValuation = (id, data) =>
  axios.post(`${API}/api/properties/${encodeURIComponent(id)}/valuations`, data);

/** Proposed tags for untagged transactions. Suggestions only — confirming
 *  them is a separate write via the transactions API. */
export const suggestTransactions = (limit = 200) =>
  axios.get(`${API}/api/properties/suggest-transactions`, { params: { limit } });
