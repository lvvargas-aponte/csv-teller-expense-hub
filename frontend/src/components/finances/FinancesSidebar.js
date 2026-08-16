import React from 'react';
import { useSidebarCollapsed } from '../../hooks/useSidebarCollapsed';

// Grouped by what the user is trying to do, not by data type. "Wealth"
// holds the things that compound; "Debt" holds the things being retired.
const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { id: 'today',       icon: '☀️', label: 'Today' },
      { id: 'dashboard',   icon: '📊', label: 'Dashboard' },
      { id: 'accounts',    icon: '🏦', label: 'Accounts' },
    ],
  },
  {
    label: 'Spending',
    items: [
      { id: 'spending',    icon: '💸', label: 'Spending' },
      { id: 'budgets',     icon: '🎯', label: 'Budgets' },
      { id: 'bills',       icon: '📅', label: 'Bills' },
    ],
  },
  {
    label: 'Debt',
    items: [
      { id: 'debt-payoff', icon: '💳', label: 'Payoff Plan' },
      { id: 'loans',       icon: '🏛️', label: 'Loans' },
    ],
  },
  {
    label: 'Wealth',
    items: [
      { id: 'properties',  icon: '🏠', label: 'Properties' },
      { id: 'investments', icon: '📈', label: 'Investments' },
      { id: 'goals',       icon: '⭐', label: 'Goals' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { id: 'knowledge',   icon: '📚', label: 'Knowledge' },
      { id: 'advisor',     icon: '🤖', label: 'Ask Fin' },
    ],
  },
];

// Every tab id the sidebar can reach — used to validate a :tab URL segment
// before rendering, so a bad path falls back instead of blanking the shell.
export const VALID_TAB_IDS = new Set(
  NAV_SECTIONS.flatMap((section) => section.items.map((item) => item.id)),
);

// The 'overview' tab was split: balances moved to Accounts, spending
// insights to Spending. Without this remap a returning user whose
// localStorage still says 'overview' lands on an empty shell.
export const LEGACY_TAB_IDS = { overview: 'accounts' };

export function normalizeTabId(id, fallback = 'dashboard') {
  const remapped = LEGACY_TAB_IDS[id] || id;
  return VALID_TAB_IDS.has(remapped) ? remapped : fallback;
}

export default function FinancesSidebar({ activeId, onNavigate, healthScore }) {
  const [collapsed, toggleCollapsed] = useSidebarCollapsed();
  return (
    <aside className={`eh-sidebar${collapsed ? ' eh-sidebar--collapsed' : ''}`}>
      <button
        type="button"
        className="eh-sidebar-toggle"
        onClick={toggleCollapsed}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-expanded={!collapsed}
      >{collapsed ? '›' : '‹'}</button>

      <div className="eh-sidebar-logo">
        <div className="eh-sidebar-logo-icon">💰</div>
        <div className="eh-sidebar-logo-text">Financial Freedom</div>
      </div>

      {NAV_SECTIONS.map((section) => (
        <React.Fragment key={section.label}>
          <div className="eh-sidebar-section-label">{section.label}</div>
          <nav className="eh-sidebar-nav">
            {section.items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`eh-nav-item${activeId === item.id ? ' eh-nav-item--active' : ''}`}
                onClick={() => onNavigate(item.id)}
                title={collapsed ? item.label : undefined}
                aria-label={item.label}
                aria-current={activeId === item.id ? 'page' : undefined}
              >
                <span className="eh-nav-icon">{item.icon}</span>
                <span className="eh-nav-text">{item.label}</span>
              </button>
            ))}
          </nav>
        </React.Fragment>
      ))}

      <div className="eh-sidebar-footer">
        <div className="eh-health-card">
          <div className="eh-health-card-label">Financial Health</div>
          <div className="eh-health-card-score">
            {(healthScore === null || healthScore === undefined) ? '—' : healthScore}
          </div>
          <div className="eh-health-card-sub">
            {(healthScore === null || healthScore === undefined)
              ? 'Add data to see your score'
              : healthScore >= 70 ? 'Looking strong'
              : healthScore >= 50 ? 'On track'
              : 'Room to improve'}
          </div>
        </div>
      </div>
    </aside>
  );
}
