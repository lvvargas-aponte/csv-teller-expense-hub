/**
 * Subscriptions API — detected recurring charges + keep/cancel/ignore reviews.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listSubscriptions = () =>
  axios.get(`${API}/api/subscriptions`);

// Merchants the detector never claimed — a yearly renewal it has too little
// history to spot, or a bill that has only charged once. Declaring a cadence
// on one promotes it to a commitment.
export const listCommitmentCandidates = () =>
  axios.get(`${API}/api/subscriptions/candidates`);

// `declared` optionally carries the user's answers to what the detector could
// not infer: { declared_cadence, declared_type }. Omitted keys leave whatever
// was stored before untouched.
export const reviewSubscription = (merchantKey, decision, declared = {}) =>
  axios.post(
    `${API}/api/subscriptions/${encodeURIComponent(merchantKey)}/review`,
    { decision, ...declared },
  );

// Fold one merchant into another so a service that renamed itself keeps a
// single history instead of appearing twice with half of it each.
export const mergeMerchant = (merchantKey, into) =>
  axios.post(
    `${API}/api/subscriptions/${encodeURIComponent(merchantKey)}/merge`,
    { into },
  );

export const unmergeMerchant = (merchantKey) =>
  axios.delete(
    `${API}/api/subscriptions/${encodeURIComponent(merchantKey)}/merge`,
  );

export const clearSubscriptionReview = (merchantKey) =>
  axios.delete(
    `${API}/api/subscriptions/${encodeURIComponent(merchantKey)}/review`,
  );