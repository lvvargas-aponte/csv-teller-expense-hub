import React, { useCallback, useContext, useEffect, useRef, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getCreditHealth } from '../../../api/dashboard';
import { getAccountDetails, upsertAccountDetails } from '../../../api/accountDetails';
import InlineField from '../accounts/InlineField';
import Num, { BlurContext } from '../Num';

const STATUS_COLOR = {
  good: '#059669',
  warn: '#f59e0b',
  high: '#ef4444',
  unknown: 'var(--text-muted)',
};

export default function CreditUtilizationCard({ onHide, index, kicker }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const blur = useContext(BlurContext);
  // One element per account row, so the "set limit →" affordance can focus
  // the limit input that sits below it.
  const rowRefs = useRef({});

  const load = useCallback(() => getCreditHealth().then((r) => setData(r.data)), []);

  useEffect(() => {
    load().catch(() => setError('Could not load credit utilization.'));
  }, [load]);

  // The details endpoint is a PUT that replaces the whole record, so merge the
  // new limit onto what's already stored (APR, due day, payoff fields) instead
  // of blanking those out. Reload afterwards so the percentage, the bar and the
  // overall headline all come back from the same server-side thresholds.
  const saveLimit = useCallback(async (accountId, limit) => {
    setSaveError(null);
    try {
      const existing = await getAccountDetails(accountId)
        .then((r) => r.data)
        .catch(() => ({}));  // 404 — no details configured for this account yet
      const { account_id, created, updated, ...rest } = existing || {};
      await upsertAccountDetails(accountId, { ...rest, credit_limit: limit });
      await load();
    } catch {
      setSaveError('Could not save that limit. Try again.');
    }
  }, [load]);

  const focusLimit = (accountId) => {
    rowRefs.current[accountId]?.querySelector('input')?.focus();
  };

  const loading = data === null && !error;
  const accounts = data?.accounts || [];
  const empty = !loading && !error && accounts.length === 0;

  return (
    <DashboardCard
      title="Credit Utilization"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No credit cards found. Add credit limits on the Accounts tab to see utilization."
      onHide={onHide}
    >
      {(data?.overall_utilization_pct !== null && data?.overall_utilization_pct !== undefined) && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Overall</div>
          <div style={{
            fontSize: 20, fontWeight: 700,
            color: STATUS_COLOR[data.overall_status] || 'inherit',
          }}>
            {data.overall_utilization_pct}%
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            <Num value={data.total_balance} /> of <Num value={data.total_limit} />
          </div>
        </div>
      )}
      <div style={{ display: 'grid', gap: 8 }}>
        {accounts.map((a) => {
          const pct = a.utilization_pct;
          const barWidth = (pct === null || pct === undefined) ? 0 : Math.min(100, pct);
          const color = STATUS_COLOR[a.status] || 'inherit';
          const name = a.name || a.institution;
          return (
            <div
              key={a.account_id}
              ref={(el) => { rowRefs.current[a.account_id] = el; }}
              style={{ fontSize: 13 }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontWeight: 500 }}>{name}</span>
                {(pct !== null && pct !== undefined) ? (
                  <span style={{ color, fontSize: 12 }}>{pct}%</span>
                ) : (
                  <button
                    type="button"
                    className="eh-linkish"
                    onClick={() => focusLimit(a.account_id)}
                    title={`Set the credit limit for ${name}`}
                  >
                    set limit →
                  </button>
                )}
              </div>
              <div style={{ height: 6, background: 'var(--border, #334155)', borderRadius: 3, marginTop: 3 }}>
                <div style={{ height: '100%', width: `${barWidth}%`, background: color, borderRadius: 3 }} />
              </div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 2,
                fontSize: 11, color: 'var(--text-muted)', marginTop: 2,
              }}>
                <Num value={a.balance} />
                <span>/</span>
                <span style={{ width: 92 }}>
                  <InlineField
                    value={a.credit_limit}
                    onChange={(v) => saveLimit(a.account_id, v)}
                    type="number"
                    prefix="$"
                    placeholder="set limit"
                    className={blur ? 'eh-blur' : ''}
                    step="0.01"
                    min="0"
                  />
                </span>
              </div>
            </div>
          );
        })}
      </div>
      {saveError && (
        <div style={{ fontSize: 11, color: 'var(--red, #ef4444)', marginTop: 8 }}>
          {saveError}
        </div>
      )}
    </DashboardCard>
  );
}
