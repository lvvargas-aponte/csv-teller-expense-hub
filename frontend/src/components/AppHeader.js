import React from 'react';
import { NavLink } from 'react-router-dom';

import { API_BASE } from '../utils/formatting';

export default function AppHeader({ isDark, onToggleTheme }) {
  const helpHref = `${API_BASE || ''}/help/`;
  return (
    <header className="tx-header">
      <div className="tx-header-inner">
        <NavLink to="/" className="tx-brand" end>
          <div className="tx-brand-icon" aria-hidden="true">💚</div>
          <span className="tx-brand-name">Expenses<span>Hub</span></span>
        </NavLink>
        <nav className="tx-tabs" aria-label="Modules">
          <NavLink
            to="/"
            end
            className={({ isActive }) => 'tx-tab' + (isActive ? ' tx-tab--active' : '')}
          >
            <span aria-hidden="true">📋</span>
            <span className="tx-tab-label">Transactions</span>
          </NavLink>
          <NavLink
            to="/finances"
            className={({ isActive }) => 'tx-tab' + (isActive ? ' tx-tab--active' : '')}
          >
            <span aria-hidden="true">📊</span>
            <span className="tx-tab-label">Finances</span>
          </NavLink>
        </nav>
        <div className="tx-header-right">
          <a
            href={helpHref}
            target="_blank"
            rel="noopener noreferrer"
            className="tx-header-icon-btn"
            aria-label="Open help"
            title="Help & documentation"
          >
            ❔
          </a>
          <button
            type="button"
            className="tx-header-icon-btn"
            onClick={onToggleTheme}
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? '☀️' : '🌙'}
          </button>
        </div>
      </div>
    </header>
  );
}
