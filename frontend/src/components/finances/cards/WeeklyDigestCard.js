import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import Num, { BlurMoney } from '../Num';
import { getLatestDigest, markDigestRead } from '../../../api/digest';

function Stat({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono', monospace" }}>
        {children}
      </span>
    </div>
  );
}

export default function WeeklyDigestCard({ onHide, index, kicker }) {
  const [digest, setDigest] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getLatestDigest()
      .then((r) => { if (!cancelled) setDigest(r.data); })
      .catch(() => { if (!cancelled) setError('Could not load the weekly digest.'); });
    return () => { cancelled = true; };
  }, []);

  // Viewing the card counts as reading the digest.
  useEffect(() => {
    if (digest && !digest.read) {
      markDigestRead(digest.id).catch(() => {});
    }
  }, [digest]);

  const loading = digest === null && !error;
  const p = digest?.payload;
  const spending = p?.spending;
  const changePct = spending?.change_pct;
  const subs = p?.subscriptions;

  return (
    <DashboardCard
      title="Weekly Digest"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      onHide={onHide}
      headerExtra={
        digest && !digest.read ? (
          <span style={{
            fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
            letterSpacing: '0.04em', padding: '2px 8px', borderRadius: 99,
            background: '#dbeafe', color: '#1d4ed8',
          }}>
            New
          </span>
        ) : null
      }
    >
      {p && (
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {p.week_start} → {p.week_end}
          </div>

          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <Stat label="Spent this week"><Num value={spending.this_week} /></Stat>
            <Stat label="Prior week"><Num value={spending.prior_week} /></Stat>
            {changePct !== null && changePct !== undefined && (
              <Stat label="Change">
                <span style={{ color: changePct > 0 ? '#ef4444' : '#059669' }}>
                  {changePct > 0 ? '▲' : '▼'} {Math.abs(changePct).toFixed(0)}%
                </span>
              </Stat>
            )}
          </div>

          {p.narrative && (
            <div style={{
              fontSize: 13, lineHeight: 1.5, padding: '8px 10px',
              borderLeft: '3px solid #059669', background: 'var(--bg-secondary)',
            }}>
              <BlurMoney text={p.narrative} />
            </div>
          )}

          {(p.alert_counts.error > 0 || p.alert_counts.warn > 0
            || subs.needs_review_count > 0 || p.upcoming_bills.length > 0) && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', display: 'grid', gap: 3 }}>
              {p.alert_counts.error + p.alert_counts.warn > 0 && (
                <div>⚠ {p.alert_counts.error + p.alert_counts.warn} alerts need attention</div>
              )}
              {subs.needs_review_count > 0 && (
                <div>🔁 {subs.needs_review_count} subscriptions waiting for review</div>
              )}
              {subs.price_increases.length > 0 && (
                <div>▲ {subs.price_increases.length} recurring charges went up in price</div>
              )}
              {p.upcoming_bills.length > 0 && (
                <div>📅 {p.upcoming_bills.length} bills due in the next 7 days</div>
              )}
            </div>
          )}
        </div>
      )}
    </DashboardCard>
  );
}