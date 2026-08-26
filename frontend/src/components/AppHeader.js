import React from 'react';

import { API_BASE } from '../utils/formatting';
import Icon from './ui/Icon';

// Navigation lives in the sidebar. The header carries only what is global to
// every route: help, and the theme toggle.
export default function AppHeader({ isDark, onToggleTheme }) {
  const helpHref = `${API_BASE || ''}/help/`;
  return (
    <header className="tx-header">
      <div className="tx-header-inner">
        <div className="tx-header-right">
          <a
            href={helpHref}
            target="_blank"
            rel="noopener noreferrer"
            className="tx-header-icon-btn"
            aria-label="Open help"
            title="Help & documentation"
          >
            <Icon name="info" size={16} />
          </a>
          <button
            type="button"
            className="tx-header-icon-btn"
            onClick={onToggleTheme}
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            <Icon name={isDark ? 'sun' : 'moon'} size={16} />
          </button>
        </div>
      </div>
    </header>
  );
}
