import React, { useCallback, useEffect, useState } from 'react';
import Spin from '../ui/Spin';
import Icon from '../ui/Icon';
import useSettingsDraft from './useSettingsDraft';
import FinancialProfilePane from './panes/FinancialProfilePane';
import CategoriesPane from './panes/CategoriesPane';
import {
  getCategoryRules, patchCategoryRule, deleteCategoryRule, createCategoryRule,
} from '../../api/categoryRules';
import {
  listCategoryRows, createCategory, patchCategory, renameCategory, mergeCategory,
  deleteCategoryById, setCategoryParent,
} from '../../api/categories';
import { useUnsavedChanges } from '../../contexts/UnsavedChangesContext';

const PANES = [
  { id: 'profile',    icon: 'settings', label: 'Financial profile' },
  { id: 'categories', icon: 'tag',      label: 'Categories & rules' },
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
  initialPane = 'profile',
  onCategoriesChanged,
}) {
  const [pane, setPane] = useState(initialPane);
  const [toast, setToast] = useState(false);
  const draft = useSettingsDraft();
  const { dirty, save, discard, saving, saveError, loading, loadError } = draft;

  // Categories are server rows too. A rename rewrites every transaction,
  // budget and rule that used the old name, so it commits on the spot rather
  // than sitting in the draft the Save bar collects — there is no coherent
  // "discard" for a change that already touched history.
  const [categoryRows, setCategoryRows] = useState([]);
  const [categorySpend, setCategorySpend] = useState({});
  const [categoryCountsLive, setCategoryCountsLive] = useState({});
  const [rules, setRules] = useState([]);
  const [categoriesBusy, setCategoriesBusy] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [categoryError, setCategoryError] = useState(null);

  const reloadCategories = useCallback(async (includeArchived = showArchived) => {
    try {
      const [cats, ruleList] = await Promise.all([
        listCategoryRows(includeArchived),
        getCategoryRules(),
      ]);
      setCategoryRows(cats.data.rows || []);
      setCategorySpend(cats.data.spend || {});
      setCategoryCountsLive(cats.data.counts || {});
      setRules(ruleList.data || []);
      onCategoriesChanged?.();
    } catch {
      setCategoryError('Could not load categories.');
    }
  }, [showArchived, onCategoriesChanged]);

  useEffect(() => { reloadCategories(); }, [reloadCategories]);

  const withCategoryReload = useCallback(async (fn) => {
    setCategoriesBusy(true);
    setCategoryError(null);
    try {
      await fn();
      await reloadCategories();
    } catch {
      setCategoryError('That change could not be saved — please try again.');
    } finally {
      setCategoriesBusy(false);
    }
  }, [reloadCategories]);

  const handleShowArchived = useCallback((next) => {
    setShowArchived(next);
    reloadCategories(next);
  }, [reloadCategories]);

  const renameCategoryRow = useCallback(
    (category, name) => withCategoryReload(() => renameCategory(category.id, name)),
    [withCategoryReload],
  );

  const patchCategoryRow = useCallback(
    (category, fields) => withCategoryReload(() => patchCategory(category.id, fields)),
    [withCategoryReload],
  );

  const mergeCategoryRow = useCallback(
    (category, intoId) => withCategoryReload(() => mergeCategory(category.id, intoId)),
    [withCategoryReload],
  );

  const createCategoryRow = useCallback(
    (name) => withCategoryReload(() => createCategory(name)),
    [withCategoryReload],
  );

  const setParentRow = useCallback(
    (category, parentId) => withCategoryReload(
      () => setCategoryParent(category.id, parentId),
    ),
    [withCategoryReload],
  );

  // Rules are server rows, edited one at a time — a rule change rewrites
  // nothing historical, so there is no draft for the save bar to collect.
  const addRuleRow = useCallback(
    (category, pattern) => withCategoryReload(
      () => createCategoryRule(pattern, category.name, { kind: 'contains' }),
    ),
    [withCategoryReload],
  );

  const toggleRuleRow = useCallback(
    (rule, enabled) => withCategoryReload(() => patchCategoryRule(rule.id, { enabled })),
    [withCategoryReload],
  );

  const deleteRuleRow = useCallback(
    (rule) => withCategoryReload(() => deleteCategoryRule(rule.id)),
    [withCategoryReload],
  );

  const deleteCategoryRow = useCallback((category) => {
    // Deleting strips the label off every transaction that carried it, which
    // no undo puts back — so this one asks.
    const ok = window.confirm(
      `Delete "${category.name}"? Transactions using it lose their category. `
      + 'Archiving instead keeps the history and just stops offering it.',
    );
    if (!ok) return undefined;
    return withCategoryReload(() => deleteCategoryById(category.id));
  }, [withCategoryReload]);

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
            <span className="set-tab-icon" aria-hidden="true">
              <Icon name={p.icon} size={16} />
            </span>
            <span>{p.label}</span>
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
        {pane === 'categories' && (
          <CategoriesPane
            counts={categoryCountsLive}
            spend={categorySpend}
            rules={rules}
            categoryRows={categoryRows}
            categoriesBusy={categoriesBusy}
            showArchived={showArchived}
            onShowArchivedChange={handleShowArchived}
            onRenameCategory={renameCategoryRow}
            onPatchCategory={patchCategoryRow}
            onMergeCategory={mergeCategoryRow}
            onDeleteCategory={deleteCategoryRow}
            onCreateCategory={createCategoryRow}
            onSetCategoryParent={setParentRow}
            onAddRule={addRuleRow}
            onToggleRule={toggleRuleRow}
            onDeleteRule={deleteRuleRow}
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

      {categoryError && (
        <div className="set-inline-error" role="alert">{categoryError}</div>
      )}

      {toast && <div className="set-toast" role="status">✓ Settings saved</div>}
    </div>
  );
}
