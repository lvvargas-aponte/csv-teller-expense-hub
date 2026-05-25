import { useMemo, useState } from 'react';
import { txnMonthKey, calculateHalf } from '../utils/formatting';

// Owns filter state (institution / shared / month / search) and derives the
// visible list, available filter options, and aggregate stats.
export function useFilters(transactions) {
  const [filterInstitution, setFilterInstitution] = useState('all');
  const [filterShared, setFilterShared] = useState('all');
  const [filterMonth, setFilterMonth] = useState('all');
  const [search, setSearch] = useState('');

  const availableInstitutions = useMemo(() => {
    const seen = new Set();
    for (const t of transactions) {
      if (t.institution) seen.add(t.institution);
    }
    return Array.from(seen).sort();
  }, [transactions]);

  const availableMonths = useMemo(() => {
    const seen = new Map();
    for (const t of transactions) {
      const m = txnMonthKey(t.date);
      if (m && !seen.has(m.key)) seen.set(m.key, m.label);
    }
    return Array.from(seen.entries())
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([key, label]) => ({ key, label }));
  }, [transactions]);

  const visible = useMemo(() => transactions.filter((t) => {
    if (filterInstitution !== 'all' && (t.institution || '') !== filterInstitution) return false;
    if (filterShared === 'shared' && !t.is_shared) return false;
    if (filterShared === 'personal' && t.is_shared) return false;
    if (filterMonth !== 'all') {
      const m = txnMonthKey(t.date);
      if (!m || m.key !== filterMonth) return false;
    }
    if (search) {
      const q = search.toLowerCase();
      const inDesc = (t.description || '').toLowerCase().includes(q);
      const inBank = (t.institution || '').toLowerCase().includes(q);
      if (!inDesc && !inBank) return false;
    }
    return true;
  }), [transactions, filterInstitution, filterShared, filterMonth, search]);

  const stats = useMemo(() => {
    let shared = 0;
    let sharedAmt = 0;
    let unreviewed = 0;
    for (const t of transactions) {
      if (t.is_shared) {
        shared += 1;
        sharedAmt += Number(t.person_2_owes || calculateHalf(t.amount) || 0);
      }
      if (!t.reviewed) unreviewed += 1;
    }
    return { total: transactions.length, shared, sharedAmt, unreviewed };
  }, [transactions]);

  return {
    filterInstitution, setFilterInstitution,
    filterShared, setFilterShared,
    filterMonth, setFilterMonth,
    search, setSearch,
    availableInstitutions,
    availableMonths,
    visible,
    stats,
  };
}
