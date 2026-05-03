import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Spin from '../ui/Spin';
import { API_BASE, fmt$ } from '../../utils/formatting';
import { getAllAccountDetails } from '../../api/accountDetails';

const blankRow = () => ({
  _id: crypto.randomUUID(), name: '', balance: '', apr: '', min_payment: '',
});

export default function PayoffPlanner({ creditAccounts = [] }) {
  const [rows,          setRows]          = useState([]);
  const [strategy,      setStrategy]      = useState('avalanche');
  const [extra,         setExtra]         = useState('');
  const [results,       setResults]       = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [error,         setError]         = useState(null);
  const [advice,        setAdvice]        = useState(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError,   setAdviceError]   = useState(null);
  const [prefilled,     setPrefilled]     = useState(false);

  // Prefill once when credit accounts become available.  When the user has
  // configured APR / min-payment on the Accounts tab, use those values so they
  // don't have to retype them for every calculation.
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
        return {
          _id:         crypto.randomUUID(),
          name:        `${acct.institution} ${acct.name}`.trim(),
          balance:     acct.ledger != null ? String(acct.ledger) : '',
          apr:         details?.apr != null ? String(details.apr) : '',
          min_payment: details?.minimum_payment != null ? String(details.minimum_payment) : '',
        };
      });
      if (!cancelled) {
        setRows(enriched);
        setPrefilled(true);
      }
    })();

    return () => { cancelled = true; };
  }, [creditAccounts, prefilled]);

  const setRow    = useCallback((i, key, val) =>
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [key]: val } : r))), []);
  const addRow    = useCallback(() => setRows((prev) => [...prev, blankRow()]), []);
  const removeRow = useCallback((i) => setRows((prev) => prev.filter((_, idx) => idx !== i)), []);

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
      setError('Calculation failed: ' + (e.response?.data?.detail || e.message));
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
      if (res.data.ai_available) {
        setAdvice(res.data.advice);
      } else {
        setAdviceError('Ollama is not running. Start it with: ollama serve');
      }
    } catch {
      setAdviceError('Could not reach the AI advisor — is the backend running?');
    } finally {
      setAdviceLoading(false);
    }
  }, [accountsPayload, strategy, extra, results]);

  return (
    <div className="finances-section">
      <h2 className="finances-section-title">Debt Payoff Planner</h2>

      {rows.length === 0 && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ color: 'var(--text-muted)', fontSize: 14, marginBottom: 12 }}>
            No credit accounts found. Connect a credit card account via Teller or add accounts manually.
          </p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={addRow}>
            + Add Account
          </button>
        </div>
      )}

      <div className="toggle-row" style={{ marginBottom: 16 }}>
        <span className="field-label">Strategy</span>
        <div className="segmented">
          {[
            { value: 'avalanche', label: 'Avalanche (High APR first)' },
            { value: 'snowball',  label: 'Snowball (Low Balance first)' },
          ].map((opt) => (
            <button key={opt.value} type="button"
                    onClick={() => setStrategy(opt.value)}
                    className={`seg${strategy === opt.value ? ' seg--active' : ''}`}>
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {rows.length > 0 && (
        <div style={{ overflowX: 'auto', marginBottom: 16 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border, #333)' }}>
                <th style={{ textAlign: 'left',  padding: '6px 8px', fontWeight: 600 }}>Account</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>Balance ($)</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>APR (%)</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>Min Payment ($)</th>
                <th style={{ width: 32 }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row._id} style={{ borderBottom: '1px solid var(--border, #2a2a2a)' }}>
                  <td style={{ padding: '4px 8px' }}>
                    <input className="form-input" style={{ width: '100%' }} type="text"
                           value={row.name} onChange={(e) => setRow(i, 'name', e.target.value)}
                           placeholder="Account name" />
                  </td>
                  <td style={{ padding: '4px 8px' }}>
                    <input className="form-input" style={{ width: '100%', textAlign: 'right' }}
                           type="number" min="0" step="0.01" value={row.balance}
                           onChange={(e) => setRow(i, 'balance', e.target.value)}
                           placeholder="0.00" />
                  </td>
                  <td style={{ padding: '4px 8px' }}>
                    <input className="form-input" style={{ width: '100%', textAlign: 'right' }}
                           type="number" min="0" step="0.01" value={row.apr}
                           onChange={(e) => setRow(i, 'apr', e.target.value)}
                           placeholder="e.g. 24.99" />
                  </td>
                  <td style={{ padding: '4px 8px' }}>
                    <input className="form-input" style={{ width: '100%', textAlign: 'right' }}
                           type="number" min="0" step="0.01" value={row.min_payment}
                           onChange={(e) => setRow(i, 'min_payment', e.target.value)}
                           placeholder="0.00" />
                  </td>
                  <td style={{ padding: '4px 8px', textAlign: 'center' }}>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeRow(i)}
                            aria-label="Remove row" style={{ padding: '2px 6px' }}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="btn btn-ghost btn-sm" onClick={addRow} style={{ marginTop: 8 }}>
            + Add Account
          </button>
        </div>
      )}

      <div className="field-group">
        <label className="field-label">Additional monthly payment toward debt (optional)</label>
        <input className="form-input" type="number" min="0" step="0.01"
               value={extra} onChange={(e) => setExtra(e.target.value)}
               placeholder="e.g. 200" style={{ maxWidth: 200 }} />
      </div>

      {error && <div style={{ color: '#f87171', fontSize: 13, marginTop: 12 }}>{error}</div>}

      {results && (
        <div style={{ marginTop: 20 }}>
          <div className="balance-section-title">Payoff Plan</div>
          <div style={{ overflowX: 'auto' }}>
            <table className="insight-table" style={{ width: '100%', marginBottom: 12 }}>
              <thead>
                <tr>
                  <th>Account</th><th>Payoff Date</th><th>Months</th><th>Total Interest</th>
                </tr>
              </thead>
              <tbody>
                {(results.accounts || []).map((row, i) => (
                  <tr key={i}>
                    <td>{row.name}</td>
                    <td>{row.payoff_date || '—'}</td>
                    <td style={{ textAlign: 'right' }}>{row.months ?? '—'}</td>
                    <td style={{ textAlign: 'right' }}>{fmt$(row.total_interest ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ fontWeight: 600 }}>
                  <td colSpan={3}>Grand Total Interest</td>
                  <td style={{ textAlign: 'right' }}>{fmt$(results.grand_total_interest ?? 0)}</td>
                </tr>
                {results.interest_saved_vs_minimums != null && (
                  <tr>
                    <td colSpan={3}>Interest Saved vs. Minimums Only</td>
                    <td style={{
                      textAlign: 'right',
                      color: results.interest_saved_vs_minimums > 0 ? '#4ade80' : 'inherit',
                      fontWeight: 600,
                    }}>
                      {fmt$(results.interest_saved_vs_minimums)}
                    </td>
                  </tr>
                )}
              </tfoot>
            </table>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
        <button type="button" className="btn btn-secondary"
                onClick={handleGetAdvice}
                disabled={adviceLoading || rows.length === 0}
                title="Ask your AI financial advisor for personalised advice on this plan">
          {adviceLoading ? <><Spin /> Thinking…</> : '🤖 Ask AI Advisor'}
        </button>
        <button type="button" className="btn btn-primary"
                onClick={handleCalculate}
                disabled={loading || rows.length === 0}>
          {loading ? <><Spin /> Calculating…</> : 'Calculate'}
        </button>
      </div>

      {adviceError && (
        <div className="ai-card ai-card--nudge" style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>AI Advisor unavailable</div>
          <div style={{ fontSize: 13 }}>{adviceError}</div>
        </div>
      )}
      {advice && (
        <div className="ai-card" style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase',
                        letterSpacing: '.06em', color: 'var(--text-muted)', marginBottom: 8 }}>
            AI Advisor
          </div>
          <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.6 }}>{advice}</div>
        </div>
      )}
    </div>
  );
}
