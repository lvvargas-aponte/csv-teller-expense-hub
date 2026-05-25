import React from 'react';

const NAV_SECTIONS = [
  {
    label: 'Transactions',
    items: [
      { id: 'current', icon: '📋', label: 'Current' },
      { id: 'history', icon: '🕓', label: 'History' },
    ],
  },
];

export default function TransactionsSidebar({ activeId, onNavigate }) {
  return (
    <aside className="eh-sidebar">
      <div className="eh-sidebar-logo">
        <div className="eh-sidebar-logo-icon">📋</div>
        <div className="eh-sidebar-logo-text">Transactions</div>
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
    </aside>
  );
}
