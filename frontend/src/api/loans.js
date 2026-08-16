/**
 * Loans API — amortizing debt, schedules, and payment breakdowns.
 *
 * `getCurrentPayment` is the interest-vs-principal split for the payment
 * due now, plus cumulative principal paid to date.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listLoans = (propertyId) =>
  axios.get(`${API}/api/loans`, {
    params: propertyId ? { property_id: propertyId } : {},
  });

export const getLoan = (id) =>
  axios.get(`${API}/api/loans/${encodeURIComponent(id)}`);

export const createLoan = (data) =>
  axios.post(`${API}/api/loans`, data);

export const updateLoan = (id, data) =>
  axios.put(`${API}/api/loans/${encodeURIComponent(id)}`, data);

export const deleteLoan = (id) =>
  axios.delete(`${API}/api/loans/${encodeURIComponent(id)}`);

export const getCurrentPayment = (id) =>
  axios.get(`${API}/api/loans/${encodeURIComponent(id)}/current-payment`);

/** Paginated — the backend defaults to 60 periods because a 360-row table
 *  is unreadable. Totals in the response describe the whole loan. */
export const getSchedule = (id, { fromPeriod = 1, limit = 60 } = {}) =>
  axios.get(`${API}/api/loans/${encodeURIComponent(id)}/schedule`, {
    params: { from_period: fromPeriod, limit },
  });

export const getWhatIf = (id, extraMonthly) =>
  axios.post(`${API}/api/loans/${encodeURIComponent(id)}/what-if`, {
    extra_monthly: extraMonthly,
  });
