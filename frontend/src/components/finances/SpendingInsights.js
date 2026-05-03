import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import Spin from '../ui/Spin';
import { API_BASE, fmt$ } from '../../utils/formatting';

export default function SpendingInsights() {
  const [open,        setOpen]        = useState(false);
  const [loaded,      setLoaded]      = useState(false);
  const [summaryData, setSummaryData] = useState(null);
  const [forecast,    setForecast]    = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);

  useEffect(() => {
    if (!open || loaded) return;
    setLoading(true);
    Promise.all([
      axios.post(`${API_BASE}/api/insights/spending-summary`, {}),
      axios.get(`${API_BASE}/api/insights/forecast`),
    ])
      .then(([sum, fc]) => {
        setSummaryData(sum.data);
        setForecast(fc.data);
        setLoaded(true);
      })
      .catch(() => setError('Could not load insights — is the backend running?'))
      .finally(() => setLoading(false));
  }, [open, loaded]);

  const months = useMemo(() => {
    if (!summaryData?.spending_by_month) return [];
    return Object.keys(summaryData.spending_by_month).sort().slice(-3);
  }, [summaryData]);

  const categories = useMemo(() => {
    if (!summaryData?.spending_by_month) return [];
    const cats = new Set();
    months.forEach((m) =>
      Object.keys(summaryData.spending_by_month[m] || {}).forEach((c) => cats.add(c))
    );
    return Array.from(cats).sort();
  }, [summaryData, months]);

  const forecastRows = useMemo(
    () => forecast?.categories
      ? [...forecast.categories].sort((a, b) => (b.predicted ?? 0) - (a.predicted ?? 0))
      : [],
    [forecast]
  );

  return (
    <div className="finances-section">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 className="finances-section-title" style={{ margin: 0 }}>Spending Insights</h2>
        <button type="button" className="btn btn-secondary btn-sm"
                onClick={() => setOpen((o) => !o)}>
          ✨ {open ? 'Hide Insights' : 'Show Insights'}
        </button>
      </div>

      {open && (
        <div style={{ marginTop: 20 }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <Spin /> Loading insights…
            </div>
          )}
          {error && <div style={{ color: '#f87171', fontSize: 14 }}>{error}</div>}

          {!loading && !error && loaded && (
            <>
              <div className="balance-section-title">AI Summary</div>

              {summaryData?.no_data && (
                <div className="ai-card ai-card--nudge">
                  <div style={{ fontWeight: 600, marginBottom: 6 }}>No spending data yet</div>
                  <div style={{ fontSize: 13 }}>
                    Sync your bank accounts or upload a CSV to generate AI spending insights.
                  </div>
                </div>
              )}
              {summaryData?.ai_available === false && !summaryData?.no_data && (
                <div className="ai-card ai-card--nudge">
                  <div style={{ fontWeight: 600, marginBottom: 6 }}>
                    Start Ollama to unlock AI insights
                  </div>
                  <div style={{ fontSize: 13 }}>
                    Run <code>ollama serve</code> in a terminal, then refresh.
                  </div>
                </div>
              )}
              {summaryData?.ai_available === true && (
                <div className="ai-card">
                  <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.6 }}>
                    {summaryData.ai_summary}
                  </div>
                </div>
              )}

              <div className="balance-section-title" style={{ marginTop: 20 }}>
                Spending by Category
              </div>
              {categories.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>
                  No transaction data loaded yet. Sync or upload a CSV first.
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="insight-table" style={{ width: '100%' }}>
                    <thead>
                      <tr>
                        <th>Category</th>
                        {months.map((m) => (
                          <th key={m} style={{ textAlign: 'right' }}>{m}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {categories.map((cat) => (
                        <tr key={cat}>
                          <td>{cat}</td>
                          {months.map((m) => {
                            const val = summaryData.spending_by_month[m]?.[cat];
                            return (
                              <td key={m} style={{ textAlign: 'right' }}>
                                {val != null ? fmt$(val) : '—'}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {forecastRows.length > 0 && (
                <>
                  <div className="balance-section-title" style={{ marginTop: 20 }}>
                    Next Month Forecast
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="insight-table" style={{ width: '100%' }}>
                      <thead>
                        <tr>
                          <th>Category</th>
                          <th style={{ textAlign: 'right' }}>Predicted</th>
                          <th style={{ textAlign: 'right' }}>Range</th>
                        </tr>
                      </thead>
                      <tbody>
                        {forecastRows.map((row, i) => (
                          <tr key={i}>
                            <td>{row.category}</td>
                            <td style={{ textAlign: 'right' }}>
                              {row.predicted != null ? fmt$(row.predicted) : '—'}
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              {row.low != null && row.high != null ? (
                                <span className="forecast-band">
                                  {fmt$(row.low)} – {fmt$(row.high)}
                                </span>
                              ) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
