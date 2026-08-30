import React, { useEffect, useRef, useState } from 'react';
import DashboardCard from './cards/DashboardCard';
import Icon from '../ui/Icon';
import { getAlerts } from '../../api/dashboard';
import { getLatestDigest, markDigestRead } from '../../api/digest';
import { getAllTransactions } from '../../api/transactions';
import { getAllAccountDetails } from '../../api/accountDetails';
import { buildInsights } from '../../utils/insightBuilder';

export default function NeedsYouFeed({ summary, dashboard, onNavigate }) {
  const [insights, setInsights] = useState(null);
  const markedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    Promise.allSettled([
      getAlerts(),
      getLatestDigest(),
      getAllTransactions(),
      getAllAccountDetails(),
    ]).then(([alertsRes, digestRes, transactionsRes, accountDetailsRes]) => {
      if (cancelled) return;

      const alerts = alertsRes.status === 'fulfilled' ? alertsRes.value.data?.alerts : [];
      const digest = digestRes.status === 'fulfilled' ? digestRes.value.data : null;
      const transactions = transactionsRes.status === 'fulfilled'
        ? transactionsRes.value.data?.transactions : [];
      const accountDetails = accountDetailsRes.status === 'fulfilled'
        ? accountDetailsRes.value.data : {};

      if (digest && !digest.read && !markedRef.current) {
        markedRef.current = true;
        Promise.resolve(markDigestRead(digest.id)).catch(() => {});
      }

      setInsights(buildInsights({
        summary, dashboard, transactions, accountDetails, alerts, digest,
      }));
    });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loading = insights === null;
  const empty = !loading && insights.length === 0;

  return (
    <DashboardCard
      title="Needs you"
      loading={loading}
      empty={empty}
      emptyText="Nothing needs you right now."
    >
      <ul style={{ display: 'grid', gap: 6, margin: 0, padding: 0, listStyle: 'none' }}>
        {insights && insights.map((insight) => (
          <li
            key={insight.id}
            style={{
              display: 'flex',
              gap: 10,
              padding: '8px 10px',
              background: 'var(--bg-secondary)',
              alignItems: 'flex-start',
            }}
          >
            <span
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: insight.iconBg,
                flexShrink: 0,
              }}
            >
              <Icon name={insight.icon} size={16} />
            </span>
            <div style={{ display: 'grid', gap: 2, flex: 1 }}>
              <span className={insight.tagClass} style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
                {insight.tag}
              </span>
              <span style={{ fontWeight: 700, fontSize: 13 }}>{insight.title}</span>
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{insight.body}</span>
              {insight.action && (
                <button
                  type="button"
                  onClick={() => onNavigate && onNavigate(insight.action.target)}
                  style={{
                    justifySelf: 'start',
                    marginTop: 4,
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    font: 'inherit',
                    color: 'var(--brand)',
                    cursor: 'pointer',
                  }}
                >
                  {insight.action.label}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </DashboardCard>
  );
}
