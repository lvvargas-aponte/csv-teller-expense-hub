import React, { useMemo, useState } from 'react';
import SettingsCard from '../SettingsCard';
import CategoryRow from './CategoryRow';

/**
 * Categories & rules.
 *
 * One list rather than three cards. A rule exists to pick a category, so it
 * lives inside the category it picks — there is nothing to cross-reference.
 * The cost of that layout is that rule order stops being visible, and order
 * decides the answer (first match wins), so each category shows its own
 * rules in evaluation order: merchant rules first, unnumbered because their
 * order is not a choice, then the text rules numbered as they run.
 */
export default function CategoriesPane({
  categoryRows = [],
  counts = {},
  spend = {},
  rules = [],
  categoriesBusy = false,
  showArchived = false,
  onShowArchivedChange,
  onRenameCategory,
  onPatchCategory,
  onMergeCategory,
  onDeleteCategory,
  onCreateCategory,
  onSetCategoryParent,
  onAddRule,
  onToggleRule,
  onDeleteRule,
}) {
  const [newCategory, setNewCategory] = useState('');
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState(null);

  const nameById = useMemo(
    () => new Map(categoryRows.map((c) => [c.id, c.name])),
    [categoryRows],
  );

  const childCounts = useMemo(() => {
    const counted = new Map();
    categoryRows.forEach((c) => {
      if (c.parent_id !== null && c.parent_id !== undefined) {
        counted.set(c.parent_id, (counted.get(c.parent_id) || 0) + 1);
      }
    });
    return counted;
  }, [categoryRows]);

  // Rules arrive as one flat list in evaluation order; bucket them by the
  // category they target so each row can show its own.
  const rulesByCategory = useMemo(() => {
    const grouped = new Map();
    rules.forEach((r) => {
      const key = (r.category || '').trim().toLowerCase();
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(r);
    });
    return grouped;
  }, [rules]);

  const rulesFor = (name) => rulesByCategory.get((name || '').trim().toLowerCase()) || [];

  // Matching a rule's pattern too, so searching a merchant finds the category
  // it feeds rather than nothing.
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return categoryRows;
    const forName = (name) => rulesByCategory.get((name || '').trim().toLowerCase()) || [];
    return categoryRows.filter((c) => (
      c.name.toLowerCase().includes(q)
      || forName(c.name).some((r) => (r.pattern || '').toLowerCase().includes(q))
    ));
  }, [categoryRows, query, rulesByCategory]);

  const addCategory = () => {
    const name = newCategory.trim();
    if (!name) return;
    setNewCategory('');
    onCreateCategory(name);
  };

  const toggleOpen = (category) => {
    setOpenId((current) => (current === category.id ? null : category.id));
  };

  return (
    <>
      <div className="set-pane-head">
        <h2 className="set-pane-title">Categories &amp; rules</h2>
        <p className="set-pane-desc">
          One list. Each category carries the rules that pick it, so you never
          have to match a rule to a category in your head.
        </p>
      </div>

      <SettingsCard
        title="Categories"
        hint={`${visible.length} of ${categoryRows.length}`}
        flush
      >
        <div className="set-cat-toolbar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" />
          </svg>
          <input
            className="set-cat-search"
            value={query}
            aria-label="Filter categories and rules"
            placeholder="Filter categories and rules"
            onChange={(e) => setQuery(e.target.value)}
          />
          <label className="set-cat-showarchived">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => onShowArchivedChange(e.target.checked)}
            />
            <span>Archived</span>
          </label>
        </div>

        {visible.length === 0 ? (
          <div className="set-empty">
            {categoryRows.length === 0 ? 'No categories yet.' : 'Nothing matches that.'}
          </div>
        ) : visible.map((row) => (
          <CategoryRow
            key={row.id}
            category={row}
            count={counts?.[row.name] ?? 0}
            spend={spend?.[row.name] ?? 0}
            rules={rulesFor(row.name)}
            open={openId === row.id}
            onToggleOpen={toggleOpen}
            // One level deep: only a category that is not itself grouped can
            // be a parent, and nothing can be its own.
            parentOptions={categoryRows.filter(
              (c) => c.id !== row.id && (c.parent_id === null || c.parent_id === undefined),
            )}
            mergeOptions={categoryRows.filter((c) => c.id !== row.id)}
            parentName={nameById.get(row.parent_id) || null}
            childCount={childCounts.get(row.id) || 0}
            busy={categoriesBusy}
            onRename={onRenameCategory}
            onPatch={onPatchCategory}
            onMerge={onMergeCategory}
            onDelete={onDeleteCategory}
            onSetParent={onSetCategoryParent}
            onAddRule={onAddRule}
            onToggleRule={onToggleRule}
            onDeleteRule={onDeleteRule}
          />
        ))}

        <div className="set-cat-add">
          <input
            className="form-input"
            value={newCategory}
            placeholder="New category"
            aria-label="New category name"
            disabled={categoriesBusy}
            onChange={(e) => setNewCategory(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') addCategory(); }}
          />
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={categoriesBusy || !newCategory.trim()}
            onClick={addCategory}
          >
            Add
          </button>
        </div>
      </SettingsCard>

      <p className="set-cat-footnote">
        A merchant rule matches one merchant exactly, so store numbers and
        card-processor prefixes fall out — those are checked before any text
        rule. Text rules match any description containing the text, and the
        numbers above are the order they run in.
      </p>
    </>
  );
}
