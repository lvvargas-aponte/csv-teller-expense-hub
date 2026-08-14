/**
 * Subscriptions API — detected recurring charges + keep/cancel/ignore reviews.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listSubscriptions = () =>
  axios.get(`${API}/api/subscriptions`);

export const reviewSubscription = (merchantKey, decision) =>
  axios.post(
    `${API}/api/subscriptions/${encodeURIComponent(merchantKey)}/review`,
    { decision },
  );

export const clearSubscriptionReview = (merchantKey) =>
  axios.delete(
    `${API}/api/subscriptions/${encodeURIComponent(merchantKey)}/review`,
  );