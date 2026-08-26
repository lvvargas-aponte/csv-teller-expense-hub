// The one definition of what exists and where it lives. Sidebar, header and
// routes all read this — nothing hardcodes a path or a label.
export const NAV = [
  { id: 'home', path: '/', label: 'Home', icon: 'home', end: true },
  {
    id: 'transactions',
    path: '/transactions',
    label: 'Transactions',
    icon: 'transactions',
    children: [
      { id: 'current', path: '/transactions', label: 'Current', end: true },
      { id: 'shared', path: '/transactions/shared', label: 'Shared' },
      { id: 'history', path: '/transactions/history', label: 'History' },
    ],
  },
  { id: 'accounts', path: '/accounts', label: 'Accounts', icon: 'accounts' },
  { id: 'debt', path: '/debt', label: 'Debt', icon: 'debt' },
  { id: 'invest', path: '/invest', label: 'Invest', icon: 'invest' },
  {
    id: 'plan',
    path: '/plan',
    label: 'Plan',
    icon: 'plan',
    children: [
      { id: 'budgets', path: '/plan/budgets', label: 'Budgets', icon: 'plan' },
      { id: 'goals', path: '/plan/goals', label: 'Goals', icon: 'goal' },
      { id: 'commitments', path: '/plan/commitments', label: 'Commitments', icon: 'calendar' },
    ],
  },
  { id: 'ask', path: '/ask', label: 'Ask', icon: 'ask' },
  { id: 'settings', path: '/settings', label: 'Settings', icon: 'settings' },
];

export const ALL_PATHS = NAV.flatMap(
  (s) => [s.path, ...(s.children ?? []).map((c) => c.path)],
).filter((p, i, all) => all.indexOf(p) === i);

// Prefix match on path SEGMENTS, so /accountsomething never resolves to
// /accounts.
function owns(sectionPath, pathname) {
  if (sectionPath === '/') return pathname === '/';
  return pathname === sectionPath || pathname.startsWith(`${sectionPath}/`);
}

export function findSection(pathname) {
  return NAV.find((s) => owns(s.path, pathname));
}
