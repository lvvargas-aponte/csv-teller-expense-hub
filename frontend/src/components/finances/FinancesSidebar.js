import React from 'react';
import { useSidebarCollapsed } from '../../hooks/useSidebarCollapsed';

const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { id: 'dashboard',   icon: '📊', label: 'Dashboard' },
      { id: 'overview',    icon: '📋', label: 'Overview' },
      { id: 'accounts',    icon: '🏦', label: 'Accounts' },
      { id: 'investments', icon: '📈', label: 'Investments' },
    ],
  },
  {
    label: 'Plan',
    items: [
      { id: 'budgets',       icon: '🎯', label: 'Budgets' },
      { id: 'goals',         icon: '⭐', label: 'Goals' },
      { id: 'bills',         icon: '📅', label: 'Bills' },
      { id: 'subscriptions', icon: '🔁', label: 'Subscriptions' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { id: 'knowledge', icon: '📚', label: 'Knowledge' },
      { id: 'advisor',   icon: '🤖', label: 'Ask Fin' },
    ],
  },
];

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
        <div className="eh-sidebar-logo-text">ExpensesHub</div>
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