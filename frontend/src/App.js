import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';

import { resolveLegacyRoute } from './legacyRoutes';
import AppHeader        from './components/AppHeader';
import Sidebar          from './components/Sidebar';
import FinancesPage     from './components/finances/FinancesPage';
import TransactionsPage from './components/transactions/TransactionsPage';
import { getHealthScore } from './api/health';
import { UnsavedChangesContext } from './contexts/UnsavedChangesContext';

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

  return (
    <div className="app-root">
      <AppHeader isDark={isDark} onToggleTheme={() => setIsDark((d) => !d)} />

      <LegacyTabRedirect />
      <UnsavedChangesContext.Provider value={unsavedChangesValue}>
        <div className="eh-app">
          <a className="eh-skip-link" href="#eh-main">Skip to main content</a>
          <Sidebar healthScore={healthScore} healthSignals={healthSignals} />
          <Routes>
            <Route path="/" element={<FinancesPage section="home" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/transactions" element={<TransactionsPage view="current" />} />
            <Route path="/transactions/shared" element={<TransactionsPage view="shared" />} />
            <Route path="/transactions/history" element={<TransactionsPage view="history" />} />
            <Route path="/accounts" element={<FinancesPage section="accounts" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/invest" element={<FinancesPage section="invest" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/plan" element={<Navigate to="/plan/budgets" replace />} />
            <Route path="/plan/budgets" element={<FinancesPage section="plan" view="budgets" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/plan/goals" element={<FinancesPage section="plan" view="goals" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/plan/commitments" element={<FinancesPage section="plan" view="commitments" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/ask" element={<FinancesPage section="ask" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/settings" element={<FinancesPage section="settings" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/settings/:pane" element={<FinancesPage section="settings" healthScore={healthScore} healthSignals={healthSignals} />} />
            <Route path="/finances" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </UnsavedChangesContext.Provider>
    </div>
  );
}
