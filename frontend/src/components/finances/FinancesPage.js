import React, { useEffect, useState, useCallback } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router-dom';
import DashboardTab from './DashboardTab';
import AccountsTab from './AccountsTab';
import DebtPage from './DebtPage';
import InvestmentsTab from './InvestmentsTab';
import BudgetsSection from './BudgetsSection';
import GoalsSection from './GoalsSection';
import AdvisorChat from './AdvisorChat';
import KnowledgeSection from './KnowledgeSection';
import SubscriptionsSection from './SubscriptionsSection';
import SettingsPage from '../settings/SettingsPage';
import { useCategories } from '../../hooks/useCategories';
import RecurringChargesCard from './cards/RecurringChargesCard';
import UpcomingBillsCard from './cards/UpcomingBillsCard';
import { getBalancesSummary } from '../../api/balances';
import { pathForTab } from '../../legacyRoutes';
import { NAV } from '../../navConfig';

const COMMITMENTS_TABS = NAV
  .find((s) => s.id === 'plan').children
  .find((c) => c.id === 'commitments').children;

const ASK_TABS = NAV.find((s) => s.id === 'ask').children;

export default function FinancesPage({ section, view, subView, healthScore, healthSignals }) {
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
            />
          </SimplePage>
        )}

        {section === 'debt' && (
          <DebtPage
            summary={summary}
            summaryLoading={summaryLoading}
            summaryError={summaryError}
            onRefresh={() => loadBalances(true)}
          />
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
            <SubTabs tabs={COMMITMENTS_TABS} label="Commitments views" />
            {subView === 'due' && (
              <div style={{ display: 'grid', gap: 16 }}>
                <UpcomingBillsCard onNavigateToAccounts={() => navigate('/debt')} />
                <RecurringChargesCard variant="detail" />
              </div>
            )}
            {subView === 'recurring' && <SubscriptionsSection />}
          </SimplePage>
        )}

        {section === 'ask' && (
          <SimplePage title="Ask">
            <SubTabs tabs={ASK_TABS} label="Ask views" />
            {view === 'chat' && <AdvisorChat />}
            {view === 'memory' && <KnowledgeSection />}
          </SimplePage>
        )}

        {section === 'settings' && (
          <SimplePage title="Profile & settings">
            <SettingsPage
              initialPane={pane || 'profile'}
              categories={categories}
              categoryCounts={categoryCounts}
            />
          </SimplePage>
        )}
      </main>
    </>
  );
}

// Real routes get real links: ctrl/cmd-click, middle-click and "copy link
// address" all need an <a href>, which a button can never give them. Same
// idiom as Sidebar.js's NavLink usage — NavLink supplies isActive and
// aria-current itself, so there's no hand-rolled active-state tracking here.
function SubTabs({ tabs, label }) {
  return (
    <nav className="eh-subtabs" aria-label={label}>
      {tabs.map((tab) => (
        <NavLink
          key={tab.id}
          to={tab.path}
          end={tab.end}
          className={({ isActive }) => (isActive ? 'eh-subtab--active' : undefined)}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
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
