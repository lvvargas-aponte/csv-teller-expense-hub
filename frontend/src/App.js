import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';

import { resolveLegacyRoute } from './legacyRoutes';
import AppHeader        from './components/AppHeader';
import Sidebar          from './components/Sidebar';
import FinancesPage     from './components/finances/FinancesPage';
import TransactionsPage from './components/transactions/TransactionsPage';
import SyncModal        from './components/accounts/SyncModal';
import AccountsModal    from './components/accounts/AccountsModal';
import UploadCsvModal   from './components/transactions/UploadCsvModal';
import SyncToast        from './components/ui/SyncToast';
import { getHealthScore } from './api/health';
import { UnsavedChangesContext } from './contexts/UnsavedChangesContext';
import { SyncContext, useSyncProvider } from './contexts/SyncContext';

// A returning user's stored section becomes a URL exactly once, on first
// mount. After that the key is gone and this is inert.
function LegacyTabRedirect() {
  const navigate = useNavigate();
  const initialPathname = useRef(useLocation().pathname);
  useEffect(() => {
    if (initialPathname.current !== '/') return;
    const target = resolveLegacyRoute(window.localStorage);
    if (target && target !== '/') navigate(target, { replace: true });
    // Runs once on mount. A pathname-dependent effect would re-fire on every
    // later arrival at "/" and hijack a deliberate Home click — and would
    // never stop if removeItem throws (Safari private mode).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

export default function App() {
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem('theme');
    return saved ? saved === 'dark' : false;
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  // Fetched once here so both the sidebar's footer and the dashboard's
  // banner read the same number without hitting the endpoint twice.
  const [healthData, setHealthData] = useState(null);
  useEffect(() => {
    getHealthScore().then((r) => setHealthData(r.data)).catch(() => {});
  }, []);
  const healthScore = healthData?.score ?? null;
  const healthSignals = healthData?.signals;

  const [unsaved, setUnsaved] = useState(false);
  const unsavedChangesValue = useMemo(() => ({ unsaved, setUnsaved }), [unsaved]);

  // Sync (bank pull / CSV upload / sheet send) is driven from here so its
  // modals and toast outlive whatever page started them — Transactions
  // unmounts on navigation, but a sync in flight there shouldn't.
  const { syncFlow, syncValue } = useSyncProvider();

  return (
    <div className="app-root">
      <AppHeader isDark={isDark} onToggleTheme={() => setIsDark((d) => !d)} />

      <LegacyTabRedirect />
      <UnsavedChangesContext.Provider value={unsavedChangesValue}>
      <SyncContext.Provider value={syncValue}>
        <div className="eh-app">
          <a className="eh-skip-link" href="#eh-main">Skip to main content</a>
          <Sidebar healthScore={healthScore} healthSignals={healthSignals} />
          <Routes>
            <Route path="/" element={<FinancesPage section="home" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/transactions" element={<TransactionsPage view="current" />} />
            <Route path="/transactions/shared" element={<TransactionsPage view="shared" />} />
            <Route path="/transactions/history" element={<TransactionsPage view="history" />} />
            <Route path="/accounts" element={<FinancesPage section="accounts" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/debt" element={<FinancesPage section="debt" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/invest" element={<FinancesPage section="invest" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/plan" element={<Navigate to="/plan/budgets" replace />} />
            <Route path="/plan/budgets" element={<FinancesPage section="plan" view="budgets" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/plan/goals" element={<FinancesPage section="plan" view="goals" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/plan/commitments" element={<Navigate to="/plan/commitments/due" replace />} />
            <Route path="/plan/commitments/due" element={<FinancesPage section="plan" view="commitments" subView="due" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/plan/commitments/recurring" element={<FinancesPage section="plan" view="commitments" subView="recurring" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/ask" element={<FinancesPage section="ask" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/settings" element={<FinancesPage section="settings" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/settings/:pane" element={<FinancesPage section="settings" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/finances" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>

          {syncFlow.showSyncModal && (
            <SyncModal onSync={syncFlow.syncBanks} onClose={() => syncFlow.setShowSyncModal(false)} />
          )}
          {syncFlow.showAccountsModal && (
            <AccountsModal
              onClose={() => {
                syncFlow.setShowAccountsModal(false);
                syncFlow.setAccountsRefreshKey((k) => k + 1);
              }}
            />
          )}
          {syncFlow.pendingCsvFile && (
            <UploadCsvModal
              file={syncFlow.pendingCsvFile}
              onSubmit={syncFlow.submitCsvUpload}
              onClose={() => syncFlow.setPendingCsvFile(null)}
            />
          )}
          {syncFlow.syncToast && (
            <SyncToast result={syncFlow.syncToast} onClose={() => syncFlow.setSyncToast(null)} />
          )}
        </div>
      </SyncContext.Provider>
      </UnsavedChangesContext.Provider>
    </div>
  );
}
