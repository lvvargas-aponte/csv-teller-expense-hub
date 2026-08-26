import React, { useEffect, useState } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';

import { resolveLegacyRoute } from './legacyRoutes';
import AppHeader        from './components/AppHeader';
import FinancesPage     from './components/finances/FinancesPage';
import TransactionsPage from './components/transactions/TransactionsPage';

// A returning user's stored section becomes a URL exactly once, on first
// mount. After that the key is gone and this is inert.
function LegacyTabRedirect() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  useEffect(() => {
    if (pathname !== '/') return;
    const target = resolveLegacyRoute(window.localStorage);
    if (target && target !== '/') navigate(target, { replace: true });
  }, [navigate, pathname]);
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

  return (
    <div className="app-root">
      <AppHeader isDark={isDark} onToggleTheme={() => setIsDark((d) => !d)} />

      <LegacyTabRedirect />
      <Routes>
        <Route path="/" element={<FinancesPage section="home" />} />
        <Route path="/transactions" element={<TransactionsPage view="current" />} />
        <Route path="/transactions/shared" element={<TransactionsPage view="shared" />} />
        <Route path="/transactions/history" element={<TransactionsPage view="history" />} />
        <Route path="/accounts" element={<FinancesPage section="accounts" />} />
        <Route path="/invest" element={<FinancesPage section="invest" />} />
        <Route path="/plan" element={<Navigate to="/plan/budgets" replace />} />
        <Route path="/plan/budgets" element={<FinancesPage section="plan" view="budgets" />} />
        <Route path="/plan/goals" element={<FinancesPage section="plan" view="goals" />} />
        <Route path="/plan/commitments" element={<FinancesPage section="plan" view="commitments" />} />
        <Route path="/ask" element={<FinancesPage section="ask" />} />
        <Route path="/settings" element={<FinancesPage section="settings" />} />
        <Route path="/settings/:pane" element={<FinancesPage section="settings" />} />
        <Route path="/finances" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
