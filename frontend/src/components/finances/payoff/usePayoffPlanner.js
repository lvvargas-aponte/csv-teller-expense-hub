import { useCallback, useEffect, useMemo, useState } from 'react';
import { userMessage } from '../../../utils/errorMessage';
import { getAllAccountDetails, upsertAccountDetails } from '../../../api/accountDetails';
import { payoffPlan, payoffAdvice } from '../../../api/tools';
import { blankRow, isSecured, sortByStrategy } from './helpers';

// Owns all PayoffPlanner state + side-effects: rows, strategy, extra payment,
// results, advice, prefill from credit accounts, and the calc/advice fetches.
// The parent component just wires these to subcomponents.
export function usePayoffPlanner(creditAccounts) {
  const [rows,          setRows]          = useState([]);
  const [strategy,      setStrategy]      = useState('avalanche');
  const [extra,         setExtra]         = useState('200');
  const [results,       setResults]       = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [error,         setError]         = useState(null);
  const [advice,        setAdvice]        = useState(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError,   setAdviceError]   = useState(null);
  const [prefilled,     setPrefilled]     = useState(false);
  // Last-known full account-details record per accountId (backend field
  // names), used to merge partial edits before PUTing — a bare partial PUT
  // would otherwise null out any fields not included in this edit.
  const [detailsByAccountId, setDetailsByAccountId] = useState({});
  // Bumped after each successful detail save. Anything deriving server-side
  // state from these fields (payoff progress) watches this rather than the
  // input values themselves, so a half-typed balance doesn't trigger a fetch
  // per keystroke.
  const [detailsVersion, setDetailsVersion] = useState(0);

  // Prefill once when credit accounts become available.
  useEffect(() => {
    if (prefilled || creditAccounts.length === 0) return;
    let cancelled = false;
    (async () => {
      let detailsMap = {};
      try {
        const r = await getAllAccountDetails();
        detailsMap = r.data || {};
      } catch { /* no details configured yet */ }
      const enriched = creditAccounts.map((acct) => {
        const details = detailsMap[acct.id] || null;
        const inferredClass = acct.subtype === 'loan' ? 'loan' : 'credit_card';
        return {
          _id:         crypto.randomUUID(),
          accountId:   acct.id,
          name:        `${acct.institution} ${acct.name}`.trim(),
          balance:     (acct.ledger !== null && acct.ledger !== undefined) ? String(Math.abs(parseFloat(acct.ledger))) : '',
          apr:         (details?.apr !== null && details?.apr !== undefined) ? String(details.apr) : '',
          min_payment: (details?.minimum_payment !== null && details?.minimum_payment !== undefined) ? String(details.minimum_payment) : '',
          debtClass:        details?.debt_class || inferredClass,
          assetValue:       (details?.asset_value !== null && details?.asset_value !== undefined) ? String(details.asset_value) : '',
          dueDate:          details?.due_date || '',
          deferredInterest: !!details?.deferred_interest,
          promoApr:         (details?.promo_apr !== null && details?.promo_apr !== undefined) ? String(details.promo_apr) : '',
          promoExpires:     details?.promo_expires || '',
          minPaymentFrom:   details?.min_payment_from  || '',
          minPaymentUntil:  details?.min_payment_until || '',
          payoffStartBalance: (details?.payoff_start_balance !== null && details?.payoff_start_balance !== undefined) ? String(details.payoff_start_balance) : '',
          payoffStartDate:  details?.payoff_start_date || '',
          paymentAccountId: details?.payment_account_id || '',
        };
      });
      if (!cancelled) {
        setRows(sortByStrategy(enriched, 'avalanche'));
        setDetailsByAccountId(detailsMap);
        setPrefilled(true);
      }
    })();
    return () => { cancelled = true; };
  }, [creditAccounts, prefilled]);

  const setRow = useCallback((id, key, val) => {
    setRows((prev) => prev.map((r) => (r._id === id ? { ...r, [key]: val } : r)));
    setResults(null);
  }, []);

  // Merge `patch` (backend field names, e.g. { apr } or { debt_class }) into
  // the last-known full details record for this row's account, then PUT the
  // merged object so unrelated saved fields (due_day, notes, …) survive.
  // Manually-added debts (no accountId) are never persisted — same as
  // balance/min_payment today.
  const persistDetail = useCallback(async (id, patch) => {
    const row = rows.find((r) => r._id === id);
    if (!row?.accountId) return;
    const prevDetails = detailsByAccountId[row.accountId] || {};
    const merged = { ...prevDetails, ...patch };
    setDetailsByAccountId((m) => ({ ...m, [row.accountId]: merged }));
    const payload = {
      apr:                merged.apr ?? null,
      credit_limit:       merged.credit_limit ?? null,
      minimum_payment:    merged.minimum_payment ?? null,
      statement_day:      merged.statement_day ?? null,
      due_day:            merged.due_day ?? null,
      notes:              merged.notes ?? '',
      debt_class:         merged.debt_class ?? null,
      asset_value:        merged.asset_value ?? null,
      due_date:           merged.due_date ?? null,
      deferred_interest:  !!merged.deferred_interest,
      promo_apr:          merged.promo_apr ?? null,
      promo_expires:      merged.promo_expires ?? null,
      min_payment_from:   merged.min_payment_from ?? null,
      min_payment_until:  merged.min_payment_until ?? null,
      payoff_start_balance: merged.payoff_start_balance ?? null,
      payoff_start_date:    merged.payoff_start_date ?? null,
      payment_account_id:   merged.payment_account_id ?? null,
    };
    try {
      await upsertAccountDetails(row.accountId, payload);
      setDetailsVersion((v) => v + 1);
    } catch (e) {
      setDetailsByAccountId((m) => ({ ...m, [row.accountId]: prevDetails }));
      setError(userMessage(e, 'Failed to save.'));
    }
  }, [rows, detailsByAccountId]);

  const persistApr = useCallback((id, apr) => {
    const value = apr === '' || apr === null || apr === undefined ? null : parseFloat(apr);
    if (value !== null && Number.isNaN(value)) return;
    return persistDetail(id, { apr: value });
  }, [persistDetail]);

  // Fired on blur rather than on every keystroke: the field is free-typed, so
  // per-character PUTs would persist half-typed amounts ("3" on the way to
  // "350") and hammer the endpoint.
  const persistMinPayment = useCallback((id, minPayment) => {
    const value = minPayment === '' || minPayment === null || minPayment === undefined
      ? null
      : parseFloat(minPayment);
    if (value !== null && Number.isNaN(value)) return;
    return persistDetail(id, { minimum_payment: value });
  }, [persistDetail]);

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

  // Secured debt is split out of the payoff queue entirely — see `isSecured`.
  // Both lists keep the strategy sort order they had in `rows`, so partitioning
  // never reshuffles anything.
  const revolvingRows = useMemo(() => rows.filter((r) => !isSecured(r)), [rows]);
  const securedRows   = useMemo(() => rows.filter((r) =>  isSecured(r)), [rows]);

  // Number current active rows by their position in the sorted list.
  // A row needs a balance to be in the payoff queue at all; rows without a
  // balance are treated as inert (no order badge). Secured rows are never
  // numbered — they aren't in the queue.
  const orderById = useMemo(() => {
    const map = new Map();
    let n = 0;
    for (const r of revolvingRows) {
      if ((parseFloat(r.balance) || 0) > 0) { n += 1; map.set(r._id, n); }
    }
    return map;
  }, [revolvingRows]);

  const accountsPayload = useCallback(() => revolvingRows.map((r) => ({
    name:        r.name,
    balance:     parseFloat(r.balance)     || 0,
    apr:         parseFloat(r.apr)         || 0,
    min_payment: parseFloat(r.min_payment) || 0,
    ...(r.deferredInterest && r.promoExpires ? {
      promo_apr:     parseFloat(r.promoApr) || 0,
      promo_expires: r.promoExpires,
    } : {}),
  })), [revolvingRows]);

  const handleCalculate = useCallback(async () => {
    if (revolvingRows.length === 0) {
      setError('Nothing to simulate — the payoff queue only covers cards and other unsecured debt. Add one, or switch a row\'s type off "Loan".');
      return;
    }
    setLoading(true);
    setError(null);
    setResults(null);
    setAdvice(null);
    try {
      const res = await payoffPlan({
        accounts:     accountsPayload(),
        strategy,
        extraMonthly: parseFloat(extra) || 0,
      });
      setResults(res.data);
    } catch (e) {
      setError(userMessage(e, 'Calculation failed — please try again.'));
    } finally {
      setLoading(false);
    }
  }, [accountsPayload, revolvingRows, strategy, extra]);

  const handleGetAdvice = useCallback(async () => {
    setAdviceLoading(true);
    setAdviceError(null);
    setAdvice(null);
    try {
      const res = await payoffAdvice({
        accounts:     accountsPayload(),
        strategy,
        extraMonthly: parseFloat(extra) || 0,
        planResults:  results,
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
  // it does NOT echo the balance back, so totalPaid sums the user's input rows
  // — the queued ones only, or a mortgage principal that was never simulated
  // would land in "total paid".
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
    const principal = revolvingRows.reduce((s, r) => s + (parseFloat(r.balance) || 0), 0);
    return principal + (parseFloat(results.grand_total_interest) || 0);
  }, [results, revolvingRows]);

  return {
    rows, revolvingRows, securedRows, strategy, extra, results,
    loading, error,
    advice, adviceLoading, adviceError,
    orderById, totalMonths, totalPaid, detailsVersion,
    setRow, persistApr, persistMinPayment, persistDetail, addRow, removeRow,
    handleStrategyChange, setExtraPayment,
    handleCalculate, handleGetAdvice,
  };
}
