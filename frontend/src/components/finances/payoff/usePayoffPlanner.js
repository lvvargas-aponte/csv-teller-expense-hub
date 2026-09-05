import {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import axios from 'axios';
import { API_BASE } from '../../../utils/formatting';
import { userMessage } from '../../../utils/errorMessage';
import { blankRow, sortByStrategy } from './helpers';

const str = (v) => ((v !== null && v !== undefined && v !== '') ? String(v) : '');

// A shared empty map, so an omitted `detailsMap` is the same object on every
// render. A `= {}` default is a fresh object each call, which would re-run the
// reconcile effect below forever.
const NO_DETAILS = {};

// Owns all PayoffPlanner state + side-effects: rows, strategy, extra payment,
// results, advice, and the calc/advice fetches.
//
// Account-backed rows track the Credit cards & loans list above rather than
// snapshotting it. This used to seed once behind a `prefilled` flag, off its own
// `getAllAccountDetails()` call — so an APR or minimum entered in that list
// after first paint never reached the planner, and two copies of the same
// details record drifted apart. `detailsMap` now comes from DebtPage, which
// already owns it.
//
// Nothing here writes: an account's balance, APR and minimum are read-only in
// the planner and edited in the Credit cards drawer above.
export function usePayoffPlanner(creditAccounts, detailsMap = NO_DETAILS) {
  const [rows,          setRows]          = useState([]);
  const [strategy,      setStrategy]      = useState('avalanche');
  const [extra,         setExtra]         = useState('200');
  const [results,       setResults]       = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [error,         setError]         = useState(null);
  const [advice,        setAdvice]        = useState(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError,   setAdviceError]   = useState(null);
  // What each account-backed row's balance was last seeded to. A balance typed
  // into the planner is a what-if — the real one comes from the bank — so it is
  // kept until the bank's own figure moves, rather than being overwritten every
  // time an unrelated APR is edited.
  const seededBalances = useRef({});

  // The fields the planner shows for one account, as the source data has them.
  const sourceRow = useCallback((acct) => {
    const details = detailsMap[acct.id] || {};
    return {
      accountId:   acct.id,
      name:        `${acct.institution} ${acct.name}`.trim(),
      balance:     (acct.ledger !== null && acct.ledger !== undefined)
        ? String(Math.abs(parseFloat(acct.ledger))) : '',
      apr:         str(details.apr),
      min_payment: str(details.minimum_payment),
    };
  }, [detailsMap]);

  // Reconcile account-backed rows with the source whenever it changes: accounts
  // that appeared get a row, accounts that went away (a card closed, a balance
  // cleared) lose theirs, and the rest are refreshed in place. Rows the user
  // added by hand have no accountId and no source, so they pass through
  // untouched.
  useEffect(() => {
    setRows((prev) => {
      const byId = new Map(prev.filter((r) => r.accountId).map((r) => [r.accountId, r]));
      const manual = prev.filter((r) => !r.accountId);
      const next = creditAccounts.map((acct) => {
        const src = sourceRow(acct);
        const existing = byId.get(acct.id);
        if (!existing) {
          seededBalances.current[acct.id] = src.balance;
          // Derived from the account, not generated: a setState updater must
          // be pure, and StrictMode double-invokes it — a fresh UUID each
          // time gave the discarded and the kept run different React keys,
          // remounting every row on mount.
          return { _id: `acct-${acct.id}`, ...src };
        }
        // Keep a hand-typed balance unless the bank's own figure has moved.
        const bankMoved = seededBalances.current[acct.id] !== src.balance;
        if (bankMoved) seededBalances.current[acct.id] = src.balance;
        return { ...existing, ...src, balance: bankMoved ? src.balance : existing.balance };
      });
      // Same ordering the one-shot prefill used to apply, now kept in step as
      // rows arrive or their APR and balance change.
      return sortByStrategy([...next, ...manual], strategy);
    });
  }, [creditAccounts, sourceRow, strategy]);

  const setRow = useCallback((id, key, val) => {
    setRows((prev) => prev.map((r) => (r._id === id ? { ...r, [key]: val } : r)));
    setResults(null);
  }, []);

  const addRow = useCallback(() => setRows((prev) => [...prev, blankRow()]), []);
  const removeRow = useCallback((id) => {
    setRows((prev) => prev.filter((r) => r._id !== id));
    setResults(null);
  }, []);

  const handleStrategyChange = useCallback((next) => {
    setStrategy(next);
    setResults(null);
    setRows((prev) => sortByStrategy(prev, next));
  }, []);

  const setExtraPayment = useCallback((val) => {
    setExtra(val);
    setResults(null);
  }, []);

  // Number current active rows by their position in the sorted list.
  // A row needs a balance to be in the payoff queue at all; rows without a
  // balance are treated as inert (no order badge).
  const orderById = useMemo(() => {
    const map = new Map();
    let n = 0;
    for (const r of rows) {
      if ((parseFloat(r.balance) || 0) > 0) { n += 1; map.set(r._id, n); }
    }
    return map;
  }, [rows]);

  const accountsPayload = useCallback(() => rows.map((r) => ({
    name:        r.name,
    balance:     parseFloat(r.balance)     || 0,
    apr:         parseFloat(r.apr)         || 0,
    min_payment: parseFloat(r.min_payment) || 0,
  })), [rows]);

  const handleCalculate = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResults(null);
    setAdvice(null);
    try {
      const res = await axios.post(`${API_BASE}/api/tools/payoff-plan`, {
        accounts:      accountsPayload(),
        strategy,
        extra_monthly: parseFloat(extra) || 0,
      });
      setResults(res.data);
    } catch (e) {
      setError(userMessage(e, 'Calculation failed — please try again.'));
    } finally {
      setLoading(false);
    }
  }, [accountsPayload, strategy, extra]);

  const handleGetAdvice = useCallback(async () => {
    setAdviceLoading(true);
    setAdviceError(null);
    setAdvice(null);
    try {
      const res = await axios.post(`${API_BASE}/api/tools/payoff-advice`, {
        accounts:      accountsPayload(),
        strategy,
        extra_monthly: parseFloat(extra) || 0,
        plan_results:  results ?? undefined,
      });
      if (res.data.ai_available) setAdvice(res.data.advice);
      else setAdviceError('Ollama is not running. Start it with: ollama serve');
    } catch {
      setAdviceError('Could not reach the AI advisor — is the backend running?');
    } finally {
      setAdviceLoading(false);
    }
  }, [accountsPayload, strategy, extra, results]);

  // Derived totals for the result panel. The backend returns
  // `grand_total_months` and per-account `payoff_months` / `total_interest`;
  // it does NOT echo the balance back, so totalPaid sums the user's input rows.
  const totalMonths = useMemo(() => {
    if (!results) return 0;
    const top = parseFloat(results.grand_total_months);
    if (top > 0) return top;
    return (results.accounts || []).reduce(
      (m, a) => Math.max(m, parseFloat(a.payoff_months) || 0), 0
    );
  }, [results]);
  const totalPaid = useMemo(() => {
    if (!results) return 0;
    const principal = rows.reduce((s, r) => s + (parseFloat(r.balance) || 0), 0);
    return principal + (parseFloat(results.grand_total_interest) || 0);
  }, [results, rows]);

  return {
    rows, strategy, extra, results,
    loading, error,
    advice, adviceLoading, adviceError,
    orderById, totalMonths, totalPaid,
    setRow, addRow, removeRow,
    handleStrategyChange, setExtraPayment,
    handleCalculate, handleGetAdvice,
  };
}
