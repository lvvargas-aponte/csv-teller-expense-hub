/**
 * Tax awareness — read-only estimates.
 *
 * Both endpoints answer with `available: false` and a reason rather than a
 * number whenever an input the user has to supply is missing, so callers
 * render the reason instead of a placeholder figure.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getAfterTaxNetWorth = () =>
  axios.get(`${API}/api/tax/after-tax-net-worth`);
