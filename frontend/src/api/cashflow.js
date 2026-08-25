/**
 * Cash-flow outlook — the forward-looking counterpart to Commitments.
 *
 * The payload is an estimate and carries its own confidence: when
 * `discretionary_basis.confidence` is "none" the typical-spending figure is
 * omitted and `projection_incomplete` is true, so callers say so rather than
 * presenting a recurring-only net as the whole picture.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getCashflowProjection = (horizonDays = 30) =>
  axios.get(`${API}/api/cashflow/projection`, { params: { horizon_days: horizonDays } });
