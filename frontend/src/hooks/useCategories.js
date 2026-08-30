import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/formatting';

// Loads the union of known categories (distinct txn categories + budget
// categories + categorizer defaults) from the backend.
export function useCategories() {
  const [categories, setCategories] = useState([]);
  // Transactions currently carrying each label. Categories that exist only
  // as a budget or a built-in default report 0.
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/api/categories`);
      setCategories(res.data.categories || []);
      setCounts(res.data.counts || {});
    } catch {
      setError('Could not load categories.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Optimistic local insert so a newly-typed category appears immediately
  // without waiting for the next reload.
  const addLocal = useCallback((name) => {
    const trimmed = (name || '').trim();
    if (!trimmed) return;
    setCategories((prev) => {
      if (prev.some((c) => c.toLowerCase() === trimmed.toLowerCase())) return prev;
      return [...prev, trimmed].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
    });
  }, []);

  const remove = useCallback(async (name) => {
    const trimmed = (name || '').trim();
    if (!trimmed) return null;
    const res = await axios.delete(`${API_BASE}/api/categories/${encodeURIComponent(trimmed)}`);
    setCategories((prev) => prev.filter((c) => c.toLowerCase() !== trimmed.toLowerCase()));
    return res.data; // { removed, cleared_txn_count, budget_exists }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return { categories, counts, loading, error, reload, addLocal, remove };
}
