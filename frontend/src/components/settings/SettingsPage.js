import React, { useCallback, useEffect, useState } from 'react';
import Spin from '../ui/Spin';
import useSettingsDraft from './useSettingsDraft';
import FinancialProfilePane from './panes/FinancialProfilePane';
import ConnectionsPane from './panes/ConnectionsPane';
import CategoriesPane from './panes/CategoriesPane';
import { useUnsavedChanges } from '../../contexts/UnsavedChangesContext';

const PANES = [
  { id: 'profile',     icon: '🧭', label: 'Financial profile' },
  { id: 'connections', icon: '🔗', label: 'Connected institutions' },
  { id: 'categories',  icon: '🏷️', label: 'Categories & rules' },
];

const TOAST_MS = 2200;

/**
 * Profile & Settings.
 *
 * The draft spans every pane — switching sub-nav items must not drop an
 * edit, and Save commits the whole form at once, so both live here rather
 * than inside the panes.
 */
export default function SettingsPage({
  initialPane = 'profile', health, summary, onRefreshBalances,
  categories = [], categoryCounts = {},
}) {
  const [pane, setPane] = useState(initialPane);
  const [toast, setToast] = useState(false);
  const draft = useSettingsDraft();
  const { dirty, save, discard, saving, saveError, loading, loadError } = draft;

  // Deep links from the Accounts page land on a specific pane.
  useEffect(() => { setPane(initialPane); }, [initialPane]);

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const { setUnsaved } = useUnsavedChanges();
  useEffect(() => { setUnsaved(dirty); }, [dirty, setUnsaved]);
  useEffect(() => () => setUnsaved(false), [setUnsaved]);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(false), TOAST_MS);
    return () => clearTimeout(t);
  }, [toast]);

  const handleSave = useCallback(async () => {
    if (await save()) setToast(true);
  }, [save]);

  const needsAttention = (health?.broken?.length ?? 0) > 0;

  if (loading) {
    return (
      <div className="set-loading"><Spin large /> Loading settings…</div>
    );
  }

  if (loadError) {
    return (
      <div className="set-page">
        <div className="set-inline-error">
          {loadError}{' '}
          <button type="button" className="btn btn-secondary btn-sm"
                  onClick={draft.reload}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="set-page">
      <div className="set-tabs" role="tablist" aria-label="Settings sections">
        {PANES.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            id={`set-tab-${p.id}`}
            aria-selected={pane === p.id}
            aria-controls={`set-panel-${p.id}`}
            className={`set-tab${pane === p.id ? ' set-tab--active' : ''}`}
            onClick={() => setPane(p.id)}
          >
            <span className="set-tab-icon" aria-hidden="true">{p.icon}</span>
            <span>{p.label}</span>
            {p.id === 'connections' && needsAttention && (
              <span className="set-tab-dot" aria-label="needs attention" />
            )}
          </button>
        ))}
      </div>

      <div
        className="set-panes"
        role="tabpanel"
        id={`set-panel-${pane}`}
        aria-labelledby={`set-tab-${pane}`}
      >
        {pane === 'profile' && (
          <FinancialProfilePane
            profile={draft.profile}
            onChange={draft.setProfileField}
          />
        )}
        {pane === 'connections' && (
          <ConnectionsPane
            health={health}
            summary={summary}
            onRefresh={onRefreshBalances}
          />
        )}
        {pane === 'categories' && (
          <CategoriesPane
            categories={categories}
            counts={categoryCounts}
            rules={draft.rules}
            onRulesChange={draft.setRules}
          />
        )}
      </div>

      {dirty && (
        <div className="set-savebar">
          <span className="set-savebar-text">
            {saveError || 'Unsaved changes'}
          </span>
          <div className="set-savebar-actions">
            <button type="button" className="btn btn-secondary"
                    onClick={discard} disabled={saving}>
              Discard
            </button>
            <button type="button" className="btn btn-primary"
                    onClick={handleSave} disabled={saving}>
              {saving ? <><Spin /> Saving…</> : 'Save changes'}
            </button>
          </div>
        </div>
      )}

      {toast && <div className="set-toast" role="status">✓ Settings saved</div>}
    </div>
  );
}
