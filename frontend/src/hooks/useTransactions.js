import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/formatting';

// Owns the transaction list + person-name config and the initial load.
// Mutation helpers (split toggle, note save, etc.) live in App so they can
// stay close to the wiring; this hook just exposes the setters they need.
export function useTransactions() {
  const [transactions, setTransactions] = useState([]);
  const [personNames, setPersonNames] = useState({ person_1: 'Person 1', person_2: 'Person 2' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [txRes, nameRes] = await Promise.all([
        axios.get(`${API_BASE}/api/transactions/all`),
        axios.get(`${API_BASE}/api/config/person-names`),
      ]);
      setTransactions(txRes.data);
      setPersonNames(nameRes.data);
    } catch {
      setError('Could not load transactions — is the backend running?');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return {
    transactions,
    personNames,
    loading,
    error,
    setError,
    setTransactions,
    reload,
  };
}
