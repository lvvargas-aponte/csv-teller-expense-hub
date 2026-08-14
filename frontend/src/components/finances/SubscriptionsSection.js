import React, { useCallback, useEffect, useState } from 'react';
import Num from './Num';
import { pickIcon, prettifyName } from './cards/RecurringChargesCard';
import {
  clearSubscriptionReview,
  listSubscriptions,
  reviewSubscription,
} from '../../api/subscriptions';

const CADENCE_LABELS = {
  weekly: 'Weekly',
  biweekly: 'Every 2 weeks',
  monthly: 'Monthly',
  bimonthly: 'Every 2 months',
  quarterly: 'Quarterly',
  semiannual: 'Twice a year',
  annual: 'Yearly',
  irregular: 'Irregular',
};

const DECISION_LABELS = { keep: 'Keeping', cancel: 'Canceling', ignore: 'Not a subscription' };

function Badge({ children, tone = 'muted' }) {
  const tones = {
    muted: { background: 'var(--surface-2, #1e293b)', color: 'var(--text-muted)' },
    warn: { background: '#fef3c7', color: '#b45309' },
    danger: { background: '#fee2e2', color: '#b91c1c' },
    ok: { background: '#d1fae5', color: '#047857' },
  };
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.04em', padding: '2px 8px', borderRadius: 99,
      whiteSpace: 'nowrap', ...tones[tone],
    }}>
      {children}
    </span>
  );
}

function SummaryStat({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 18, fontWeight: 700, fontFamily: "'DM Mono', monospace" }}>
        {children}
      </span>
    </div>
  );
}

export default function SubscriptionsSection() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busyKey, setBusyKey] = useState(null);

  const load = useCallback(() => {
    listSubscriptions()
      .then((r) => { setData(r.data); setError(null); })
      .catch(() => setError('Could not load subscriptions — is the backend running?'));
  }, []);

  useEffect(() => { load(); }, [load]);

  const act = useCallback((merchantKey, decision) => {
    setBusyKey(merchantKey);
    const call = decision === null
      ? clearSubscriptionReview(merchantKey)
      : reviewSubscription(merchantKey, decision);
    call.then(load).catch(load).finally(() => setBusyKey(null));
  }, [load]);

  if (error) return <div className="eh-card" style={{ padding: 16 }}>{error}</div>;
  if (!data) return <div className="eh-card" style={{ padding: 16 }}>Loading…</div>;

  const { subscriptions, summary } = data;

  return (
    <div className="eh-card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <h3 style={{ margin: 0 }}>Subscriptions &amp; recurring charges</h3>
        {summary.needs_review_count > 0 && (
          <Badge tone="warn">{summary.needs_review_count} to review</Badge>
        )}
      </div>
      <div style={{ display: 'flex', gap: 32, margin: '12px 0 16px', flexWrap: 'wrap' }}>
        <SummaryStat label="Active per month"><Num value={summary.active_monthly_cost} /></SummaryStat>
        <SummaryStat label="Savings once canceled"><Num value={summary.cancel_monthly_savings} /></SummaryStat>
      </div>

      {subscriptions.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          No recurring charges detected yet (need ≥2 months of similar charges).
        </div>
      )}

      <div style={{ display: 'grid', gap: 8 }}>
        {subscriptions.map((s) => {
          const { icon, color } = pickIcon(s.sample_description, s.category);
          const name = prettifyName(s.sample_description);
          const decision = s.review?.decision || null;
          const priceUp = (s.price_change_since_review_pct ?? s.price_change_pct) > 0
            && Math.abs(s.price_change_since_review_pct ?? s.price_change_pct) >= 10;
          const busy = busyKey === s.merchant_key;
          return (
            <div
              key={s.merchant_key}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px',
                borderRadius: 10,
                border: `1px solid ${s.needs_review ? '#f59e0b' : 'var(--border, #334155)'}`,
                opacity: decision === 'ignore' || decision === 'cancel' ? 0.6 : 1,
              }}
            >
              <span style={{
                width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                background: color, fontSize: 16,
              }}>{icon}</span>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 600 }}>{name}</span>
                  {s.needs_review && <Badge tone="warn">Review</Badge>}
                  {priceUp && (
                    <Badge tone="danger">
                      ▲ {Math.abs(s.price_change_since_review_pct ?? s.price_change_pct).toFixed(0)}%
                    </Badge>
                  )}
                  {s.overlap_group && <Badge tone="warn">Overlaps</Badge>}
                  {decision && !s.needs_review && <Badge tone="ok">{DECISION_LABELS[decision]}</Badge>}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {CADENCE_LABELS[s.cadence] || s.cadence}
                  {s.interval_days ? ` · every ~${s.interval_days}d` : ''}
                  {s.category && s.category !== 'Uncategorized' ? ` · ${s.category}` : ''}
                  {` · last ${s.last_seen}`}
                </div>
              </div>

              <div style={{ textAlign: 'right', fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
                <Num value={s.estimated_monthly_cost} />
                <div style={{ fontSize: 10, fontWeight: 400, color: 'var(--text-muted)' }}>/mo</div>
              </div>

              <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                {decision === null ? (
                  <>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                            onClick={() => act(s.merchant_key, 'keep')}>
                      Keep
                    </button>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                            onClick={() => act(s.merchant_key, 'cancel')}>
                      Cancel it
                    </button>
                    <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
                            title="Not a subscription — hide from review"
                            onClick={() => act(s.merchant_key, 'ignore')}>
                      Ignore
                    </button>
                  </>
                ) : s.needs_review ? (
                  <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                          onClick={() => act(s.merchant_key, decision)}>
                    Confirm
                  </button>
                ) : (
                  <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
                          onClick={() => act(s.merchant_key, null)}>
                    Undo
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}