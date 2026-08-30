// Before Phase 2, the finances section lived in localStorage instead of the
// URL. A returning user still holds that key — sometimes with an id that was
// retired before Phase 2. Land them somewhere sensible once, then clear it.
export const ACTIVE_TAB_KEY = 'finances.activeTab';

const TAB_TO_PATH = {
  dashboard: '/',
  overview: '/',            // held net worth, payoff and insights — three unrelated things
  transactions: '/transactions',   // alert targets use this id; without it they fall back to Home
  accounts: '/accounts',
  debt: '/debt',
  investments: '/invest',
  budgets: '/plan/budgets',
  goals: '/plan/goals',
  commitments: '/plan/commitments',
  bills: '/plan/commitments',
  subscriptions: '/plan/commitments',
  advisor: '/ask',
  knowledge: '/ask/memory', // Knowledge was never a peer of Budgets; it is Fin's memory
  settings: '/settings',
};

// Several components still hand around legacy tab ids — server-supplied alert
// targets among them, so the set is not fully knowable at build time. They map
// through this same table rather than a parallel one.
export function pathForTab(tabId) {
  return TAB_TO_PATH[tabId] ?? '/';
}

export function resolveLegacyRoute(storage) {
  let stored = null;
  try {
    stored = storage.getItem(ACTIVE_TAB_KEY);
  } catch {
    return null;            // private mode, quota, disabled storage
  }
  if (!stored) return null;
  try {
    storage.removeItem(ACTIVE_TAB_KEY);
  } catch { /* best effort — the redirect still happens */ }
  return TAB_TO_PATH[stored] ?? '/';
}
