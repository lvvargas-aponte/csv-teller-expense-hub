/**
 * Investments API calls — holdings, portfolio aggregation, cost-basis overrides.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

// Holdings grouped by account: { accounts: [...], holding_count }.
export const getHoldings = () =>
  axios.get(`${API}/api/investments/holdings`);

// Aggregated portfolio: totals, allocation, concentration, by_account, holdings.
export const getPortfolio = () =>
  axios.get(`${API}/api/investments/portfolio`);

// User-entered average cost for one position. Stored apart from the synced
// holding, so a resync can't wipe it.
export const setCostBasis = (accountId, symbol, averagePurchasePrice) =>
  axios.put(
    `${API}/api/investments/holdings/${encodeURIComponent(accountId)}/${encodeURIComponent(symbol)}/cost-basis`,
    { average_purchase_price: averagePurchasePrice },
  );

export const clearCostBasis = (accountId, symbol) =>
  axios.delete(
    `${API}/api/investments/holdings/${encodeURIComponent(accountId)}/${encodeURIComponent(symbol)}/cost-basis`,
  );
