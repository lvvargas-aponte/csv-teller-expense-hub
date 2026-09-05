import React, { useEffect, useMemo, useRef, useState } from 'react';
import DashboardCard from './cards/DashboardCard';
import Icon from '../ui/Icon';
import { getAlerts } from '../../api/dashboard';
import { getLatestDigest, markDigestRead } from '../../api/digest';
import { getAllTransactions } from '../../api/transactions';
import { getAllAccountDetails } from '../../api/accountDetails';
import { buildInsights } from '../../utils/insightBuilder';
import { pathForTarget } from '../../legacyRoutes';

// The feed is the first thing on Home and has no upper bound of its own — a
// week with several alerts pushed everything else below the fold. Five is
// what fits beside the cards next to it; the rest stay one click away.
const VISIBLE_LIMIT = 5;

// summary/dashboard arrive as props that start null and fill in asynchronously
// (DashboardTab, FinancesPage). Fetching lives in one mount-only effect; the
// insight list is a separate memo so it recomputes once those props land,
// instead of being frozen at whatever they were on first render.
export default function NeedsYouFeed({ summary, dashboard, onNavigate, currentPath }) {
  const [loaded, setLoaded] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [alertsFailed, setAlertsFailed] = useState(false);
  const [digest, setDigest] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [accountDetails, setAccountDetails] = useState({});
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

      if (alertsRes.status === 'fulfilled') {
        setAlerts(alertsRes.value.data?.alerts || []);
      } else {
        setAlertsFailed(true);
      }

      const fetchedDigest = digestRes.status === 'fulfilled' ? digestRes.value.data : null;
      setDigest(fetchedDigest);
      setTransactions(transactionsRes.status === 'fulfilled'
        ? (transactionsRes.value.data?.transactions || []) : []);
      setAccountDetails(accountDetailsRes.status === 'fulfilled'
        ? (accountDetailsRes.value.data || {}) : {});

      if (fetchedDigest && !fetchedDigest.read && !markedRef.current) {
        markedRef.current = true;
        Promise.resolve(markDigestRead(fetchedDigest.id)).catch(() => {});
      }

      setLoaded(true);
    });

    return () => { cancelled = true; };
  }, []);

  const insights = useMemo(() => {
    if (!loaded) return null;
    return buildInsights({
      summary, dashboard, transactions, accountDetails, alerts, digest,
    });
  }, [loaded, summary, dashboard, transactions, accountDetails, alerts, digest]);

  const loading = insights === null;
  // Alerts are the primary source — a rejection there means the feed could
  // not tell whether anything needs attention, not that nothing does.
  const error = (!loading && alertsFailed)
    ? 'Could not load insights — is the backend running?' : null;
  const empty = !loading && !error && insights.length === 0;

  const shown = (!insights || expanded) ? insights : insights.slice(0, VISIBLE_LIMIT);
  const hiddenCount = insights ? insights.length - (shown ? shown.length : 0) : 0;

  return (
    <DashboardCard
      title="Needs you"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="Nothing needs you right now."
    >
      <ul style={{ display: 'grid', gap: 6, margin: 0, padding: 0, listStyle: 'none' }}>
        {shown && shown.map((insight) => (
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
              {/* A link to the page you are reading is not an action. The
                  cashflow alert targets the dashboard, and this feed only
                  renders on the dashboard. */}
              {insight.action && pathForTarget(insight.action.target) !== currentPath && (
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
      {(hiddenCount > 0 || expanded) && (
        <button
          type="button"
          className="eh-needsyou-more"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Show less' : `Show ${hiddenCount} more`}
        </button>
      )}
    </DashboardCard>
  );
}
