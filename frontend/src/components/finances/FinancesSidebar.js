import React from 'react';
import { useSidebarCollapsed } from '../../hooks/useSidebarCollapsed';
import InfoPopover from '../ui/InfoPopover';
import Icon from '../ui/Icon';

const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { id: 'dashboard',   icon: 'home',     label: 'Dashboard' },
      { id: 'accounts',    icon: 'accounts', label: 'Accounts' },
      { id: 'investments', icon: 'invest',   label: 'Investments' },
    ],
  },
  {
    label: 'Plan',
    items: [
      { id: 'budgets',     icon: 'plan',         label: 'Budgets' },
      { id: 'goals',       icon: 'goal',         label: 'Goals' },
      // Bills and Subscriptions were two views of the same detector under two
      // nav entries; Commitments holds both.
      { id: 'commitments', icon: 'history',      label: 'Commitments' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { id: 'knowledge', icon: 'info',     label: 'Knowledge' },
      { id: 'advisor',   icon: 'ask',      label: 'Ask' },
      { id: 'settings',  icon: 'settings', label: 'Profile & settings' },
    ],
  },
];

// Tab ids that no longer exist, and where a returning user holding one should
// land. Lives beside NAV_SECTIONS so a future rename can't forget the mapping.
const RETIRED_TAB_IDS = {
  bills:         { tab: 'commitments', view: 'due' },
  subscriptions: { tab: 'commitments', view: 'recurring' },
  // Overview held net worth, the payoff planner and spending insights — three
  // unrelated things whose identity against Dashboard was never predictable.
  overview:      { tab: 'dashboard' },
};

export function resolveStoredTab(stored) {
  return RETIRED_TAB_IDS[stored] || { tab: stored || 'dashboard', view: 'due' };
}

export default function FinancesSidebar({ activeId, onNavigate, healthScore, healthSignals }) {
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
      ><span aria-hidden="true">{collapsed ? '›' : '‹'}</span></button>

      <div className="eh-sidebar-logo">
        <div className="eh-sidebar-logo-icon" aria-hidden="true">
          <Icon name="accounts" size={18} />
        </div>
        <div className="eh-sidebar-logo-text">Fin</div>
      </div>

      {NAV_SECTIONS.map((section) => (
        <React.Fragment key={section.label}>
          <div className="eh-sidebar-section-label" id={`nav-${section.label}`}>
            {section.label}
          </div>
          <nav className="eh-sidebar-nav" aria-labelledby={`nav-${section.label}`}>
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
                <span className="eh-nav-icon" aria-hidden="true">
                  <Icon name={item.icon} size={18} />
                </span>
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
            <span>{(healthScore === null || healthScore === undefined) ? '—' : healthScore}</span>
            {healthSignals && healthSignals.length > 0 && (
              <InfoPopover label="the health score" title="Financial Health Score">
                A 0–100 estimate of your overall position. Each signal contributes a
                0–1 sub-score scaled by its weight; signals with no data are skipped
                and the remaining weights are renormalized.
                <ul>
                  {healthSignals.map((s) => (
                    <li key={s.key}>
                      <strong>{s.label} ({s.weight}%)</strong>
                      {s.available ? ` — ${s.detail}` : ` — skipped: ${s.detail}`}
                    </li>
                  ))}
                </ul>
              </InfoPopover>
            )}
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
