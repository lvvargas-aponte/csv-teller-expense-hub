import React from 'react';

const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { id: 'dashboard', icon: '📊', label: 'Dashboard' },
      { id: 'overview',  icon: '📋', label: 'Overview' },
      { id: 'accounts',  icon: '🏦', label: 'Accounts' },
    ],
  },
  {
    label: 'Plan',
    items: [
      { id: 'budgets', icon: '🎯', label: 'Budgets' },
      { id: 'goals',   icon: '⭐', label: 'Goals' },
      { id: 'bills',   icon: '📅', label: 'Bills' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { id: 'advisor', icon: '🤖', label: 'AI Advisor' },
    ],
  },
];

export default function FinancesSidebar({ activeId, onNavigate, healthScore }) {
  return (
    <aside className="eh-sidebar">
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
              >
                <span className="eh-nav-icon">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        </React.Fragment>
      ))}

      <div className="eh-sidebar-footer">
        <div className="eh-health-card">
          <div className="eh-health-card-label">Financial Health</div>
          <div className="eh-health-card-score">
            {healthScore == null ? '—' : healthScore}
          </div>
          <div className="eh-health-card-sub">
            {healthScore == null
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
