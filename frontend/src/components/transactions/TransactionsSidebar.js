import React from 'react';
import { useSidebarCollapsed } from '../../hooks/useSidebarCollapsed';
import Icon from '../ui/Icon';

const NAV_SECTIONS = [
  {
    label: 'Transactions',
    items: [
      { id: 'current', icon: 'transactions', label: 'Current' },
      { id: 'shared',  icon: 'shared',       label: 'Shared' },
      { id: 'history', icon: 'history',      label: 'History' },
    ],
  },
];

export default function TransactionsSidebar({ activeId, onNavigate }) {
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
        <div className="eh-sidebar-logo-icon" aria-hidden="true">
          <Icon name="transactions" size={18} />
        </div>
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
                title={collapsed ? item.label : undefined}
                aria-label={item.label}
              >
                <span className="eh-nav-icon" aria-hidden="true">
                  <Icon name={item.icon} size={18} />
                </span>
                <span className="eh-nav-text">{item.label}</span>
              </button>
            ))}
          </nav>
        </React.Fragment>
      ))}
    </aside>
  );
}