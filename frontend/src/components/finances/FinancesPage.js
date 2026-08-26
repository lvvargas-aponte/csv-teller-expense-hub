import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import DashboardTab from './DashboardTab';
import AccountsTab from './AccountsTab';
import InvestmentsTab from './InvestmentsTab';
import PayoffPlanner from './PayoffPlanner';
import CreditFactorsPanel from './CreditFactorsPanel';
import BudgetsSection from './BudgetsSection';
import GoalsSection from './GoalsSection';
import AdvisorChat from './AdvisorChat';
import KnowledgeSection from './KnowledgeSection';
import SubscriptionsSection from './SubscriptionsSection';
import SettingsPage from '../settings/SettingsPage';
import useConnectionHealth from './accounts/useConnectionHealth';
import { useCategories } from '../../hooks/useCategories';
import RecurringChargesCard from './cards/RecurringChargesCard';
import UpcomingBillsCard from './cards/UpcomingBillsCard';
import { getBalancesSummary } from '../../api/balances';
import { pathForTab } from '../../legacyRoutes';

export default function FinancesPage({ section, view, healthScore, healthSignals }) {
  const navigate = useNavigate();
  const { pane } = useParams();

  const handleInsightAction = useCallback((target) => {
    if (!target) return;
    if (target.financesTab) navigate(pathForTab(target.financesTab));
    else if (target.route)  navigate(target.route);
  }, [navigate]);

  const openSettings = useCallback(
    (paneId = 'profile') => navigate(`/settings/${paneId}`),
    [navigate],
  );

  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(null);

  // Refreshing swaps every number on the page with nothing to hear. One
  // polite region carries the outcome.
  const [announcement, setAnnouncement] = useState('');

  const loadBalances = useCallback((force = false) => {
    setSummaryLoading(true);
    setSummaryError(null);
    setAnnouncement('');
    getBalancesSummary(force)
      .then((r) => {
        setSummary(r.data);
        setAnnouncement('Balances updated');
      })
      .catch(() => {
        setSummaryError('Could not load balances — is the backend running?');
        setAnnouncement('Could not update balances');
      })
      .finally(() => setSummaryLoading(false));
  }, []);

  useEffect(() => {
    loadBalances(false);
  }, [loadBalances]);

  const creditAccounts = useMemo(
    () => summary?.accounts?.filter(
      (a) => a.type === 'credit' && Math.abs(parseFloat(a.ledger) || 0) >= 0.005,
    ) ?? [],
    [summary],
  );

  const health = useConnectionHealth(summary?.connections);
  const { categories, counts: categoryCounts } = useCategories();

  const handleTabNavigate = useCallback((tabId) => {
    navigate(pathForTab(tabId));
  }, [navigate]);

  return (
    <>
      <main className="eh-main" id="eh-main">
        <div className="eh-live-region" role="status" aria-live="polite">
          {announcement}
        </div>
        {section === 'home' && (
          <DashboardTab
            healthScore={healthScore}
            healthSignals={healthSignals}
            summary={summary}
            summaryLoading={summaryLoading}
            summaryError={summaryError}
            onOpenSettings={openSettings}
            onNavigate={handleTabNavigate}
            onInsightAction={handleInsightAction}
          />
        )}

        {section === 'accounts' && (
          <SimplePage title="Accounts">
            <AccountsTab
              summary={summary}
              summaryLoading={summaryLoading}
              summaryError={summaryError}
              onRefresh={() => loadBalances(true)}
              onManageConnections={() => openSettings('connections')}
            />
            {/* The payoff planner belongs beside the accounts it acts on,
                not on a separate Overview page. */}
            <PayoffPlanner creditAccounts={creditAccounts} />
            <CreditFactorsPanel />
          </SimplePage>
        )}

        {section === 'invest' && (
          <SimplePage title="Invest">
            <InvestmentsTab onOpenSettings={openSettings} />
          </SimplePage>
        )}

        {section === 'plan' && view === 'budgets' && (
          <SimplePage title="Budgets"><BudgetsSection /></SimplePage>
        )}

        {section === 'plan' && view === 'goals' && (
          <SimplePage title="Goals"><GoalsSection /></SimplePage>
        )}

        {section === 'plan' && view === 'commitments' && (
          <SimplePage title="Commitments">
            <div style={{ display: 'grid', gap: 16 }}>
              <UpcomingBillsCard onNavigateToAccounts={() => navigate('/accounts')} />
              <RecurringChargesCard variant="detail" />
            </div>
            <SubscriptionsSection />
          </SimplePage>
        )}

        {section === 'ask' && (
          <SimplePage title="Ask">
            <AdvisorChat />
            <KnowledgeSection />
          </SimplePage>
        )}

        {section === 'settings' && (
          <SimplePage title="Profile & settings">
            <SettingsPage
              initialPane={pane || 'profile'}
              health={health}
              summary={summary}
              categories={categories}
              categoryCounts={categoryCounts}
              onRefreshBalances={() => loadBalances(true)}
            />
          </SimplePage>
        )}
      </main>
    </>
  );
}

function SimplePage({ title, children }) {
  return (
    <>
      <div className="eh-topbar">
        <h1 className="eh-topbar-title">{title}</h1>
      </div>
      <div className="eh-content">{children}</div>
    </>
  );
}
