import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { NAV, findSection } from '../navConfig';
import { useSidebarCollapsed } from '../hooks/useSidebarCollapsed';
import { useUnsavedChanges } from '../contexts/UnsavedChangesContext';
import Icon from './ui/Icon';
import InfoPopover from './ui/InfoPopover';

export default function Sidebar({ healthScore, healthSignals }) {
  const [collapsed, toggleCollapsed] = useSidebarCollapsed();
  const { pathname } = useLocation();
  const active = findSection(pathname);
  const { unsaved } = useUnsavedChanges();

  const confirmLeave = (e) => {
    // eslint-disable-next-line no-alert
    if (unsaved && !window.confirm('You have unsaved settings. Leave without saving?')) {
      e.preventDefault();
    }
  };

  return (
    <aside className={`eh-sidebar${collapsed ? ' eh-sidebar--collapsed' : ''}`}>
      <button
        type="button"
        className="eh-sidebar-toggle"
        onClick={toggleCollapsed}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-expanded={!collapsed}
      >
        <Icon name={collapsed ? 'chevron' : 'chevronDown'} size={14} />
      </button>

      <div className="eh-sidebar-logo">
        <div className="eh-sidebar-logo-icon" aria-hidden="true">
          <Icon name="ask" size={18} />
        </div>
        <div className="eh-sidebar-logo-text">Fin</div>
      </div>

      <nav className="eh-sidebar-nav" aria-label="Main">
        {NAV.map((section) => (
          <React.Fragment key={section.id}>
            <NavLink
              to={section.path}
              end={section.end}
              className={({ isActive }) => `eh-nav-item${isActive ? ' eh-nav-item--active' : ''}`}
              title={collapsed ? section.label : undefined}
              aria-label={section.label}
              onClick={confirmLeave}
            >
              <span className="eh-nav-icon" aria-hidden="true">
                <Icon name={section.icon} size={18} />
              </span>
              <span className="eh-nav-text">{section.label}</span>
            </NavLink>

            {active?.id === section.id && section.children
              && section.subnavPlacement !== 'page' && !collapsed && (
              <div className="eh-sidebar-subnav">
                {section.children.map((child) => (
                  <NavLink
                    key={child.id}
                    to={child.path}
                    end={child.end}
                    className={({ isActive }) => `eh-subnav-item${isActive ? ' eh-subnav-item--active' : ''}`}
                    onClick={confirmLeave}
                  >
                    {child.label}
                  </NavLink>
                ))}
              </div>
            )}
          </React.Fragment>
        ))}
      </nav>

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
