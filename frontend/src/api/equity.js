/**
 * Equity API — borrowing capacity and the deal analyzer.
 *
 * Capacity responses always pair the extractable amount with the payment
 * increase and the cash flow that survives it. Render them together: the
 * proceeds figure alone reads as free money when it is a payment rise.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getCapacity = ({ maxLtvPct, maxCltvPct } = {}) =>
  axios.get(`${API}/api/equity/capacity`, {
    params: {
      ...(maxLtvPct !== undefined ? { max_ltv_pct: maxLtvPct } : {}),
      ...(maxCltvPct !== undefined ? { max_cltv_pct: maxCltvPct } : {}),
    },
  });

export const getCapacityFor = (propertyId) =>
  axios.get(`${API}/api/equity/capacity/${encodeURIComponent(propertyId)}`);

/** Read `net_effect.portfolio_cash_flow_delta` before the deal's own cash
 *  flow when the down payment is borrowed against something you own. */
export const analyzeDeal = (inputs) =>
  axios.post(`${API}/api/equity/analyze-deal`, inputs);
