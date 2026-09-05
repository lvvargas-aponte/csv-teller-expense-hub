import React, { useMemo, useState } from 'react';
import SettingsCard from '../SettingsCard';
import categoryColor from '../categoryColor';
import CategoryRow from './CategoryRow';

function RuleRow({ rule, categories, onChange, onRemove }) {
  return (
    <div className="set-rule-row">
      <div className="set-rule-col">
        <span className="set-rule-prefix">When the merchant contains</span>
        <input
          className="form-input set-input--mono"
          value={rule.pattern}
          placeholder="TRADER JOE"
          aria-label="Merchant text to match"
          onChange={(e) => onChange({ ...rule, pattern: e.target.value })}
        />
      </div>
      <div className="set-rule-col">
        <span className="set-rule-prefix">Categorize as</span>
        <select
          className="form-input"
          value={rule.category}
          aria-label="Category to apply"
          onChange={(e) => onChange({ ...rule, category: e.target.value })}
        >
          {!categories.includes(rule.category) && (
            <option value={rule.category}>{rule.category || '—'}</option>
          )}
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <button
        type="button"
        className="set-rule-del"
        aria-label={`Delete rule for ${rule.pattern || 'new rule'}`}
        onClick={onRemove}
      >
        ×
      </button>
    </div>
  );
}

function fmtLastUsed(iso) {
  if (!iso) return 'not used yet';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'not used yet';
  return `last used ${d.toLocaleDateString()}`;
}

// Merchant rules are written by categorizing a transaction, so this card
// reports and manages them rather than offering a form to author one.
function LearnedRuleRow({ rule, onToggle, onRemove, busy }) {
  return (
    <div className={`set-rule-row set-rule-row--learned${rule.enabled ? '' : ' set-rule-row--off'}`}>
      <div className="set-rule-col">
        <span className="set-rule-prefix">Always</span>
        <code className="set-rule-merchant">{rule.pattern}</code>
      </div>
      <div className="set-rule-col">
        <span className="set-rule-prefix">Categorize as</span>
        <span className="set-rule-cat">
          <span
            className="set-chip-dot"
            style={{ background: categoryColor(rule.category) }}
            aria-hidden="true"
          />
          {rule.category}
        </span>
      </div>
      <span className="set-rule-meta">{fmtLastUsed(rule.last_matched_at)}</span>
      <label className="set-rule-toggle">
        <input
          type="checkbox"
          checked={rule.enabled}
          disabled={busy}
          aria-label={`Rule for ${rule.pattern} is on`}
          onChange={(e) => onToggle(rule, e.target.checked)}
        />
        <span className="set-rule-toggle-text">On</span>
      </label>
      <button
        type="button"
        className="set-rule-del"
        disabled={busy}
        aria-label={`Delete rule for ${rule.pattern}`}
        onClick={() => onRemove(rule)}
      >
        ×
      </button>
    </div>
  );
}

export default function CategoriesPane({
  categories,
  counts,
  rules,
  onRulesChange,
  learned = [],
  onToggleLearned,
  onRemoveLearned,
  learnedBusy = false,
  categoryRows = [],
  categoriesBusy = false,
  showArchived = false,
  onShowArchivedChange,
  onRenameCategory,
  onPatchCategory,
  onMergeCategory,
  onDeleteCategory,
  onCreateCategory,
  onSetCategoryParent,
}) {
  const [newCategory, setNewCategory] = useState('');

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

  const addCategory = () => {
    const name = newCategory.trim();
    if (!name) return;
    setNewCategory('');
    onCreateCategory(name);
  };

  const addRule = () => {
    onRulesChange([
      ...rules,
      { key: `new${Date.now()}`, pattern: '', category: categories[0] || '' },
    ]);
  };

  const updateRule = (key, next) => {
    onRulesChange(rules.map((r) => (r.key === key ? { ...next, key } : r)));
  };

  const removeRule = (key) => {
    onRulesChange(rules.filter((r) => r.key !== key));
  };

  return (
    <>
      <div className="set-pane-head">
        <h2 className="set-pane-title">Categories &amp; rules</h2>
        <p className="set-pane-desc">
          Transactions are categorized automatically, and a rule always beats
          the automatic guess. Merchant rules are checked first — they come
          from categorizing a transaction and match that merchant exactly.
          The text rules below run after, in order, first match winning.
        </p>
      </div>

      <SettingsCard
        title="Categories"
        hint={`${categoryRows.length} in use`}
        flush
      >
        {categoryRows.length === 0 ? (
          <div className="set-empty">No categories yet.</div>
        ) : categoryRows.map((row) => (
          <CategoryRow
            key={row.id}
            category={row}
            count={counts?.[row.name] ?? 0}
            siblings={categoryRows.filter((c) => c.id !== row.id)}
            // One level deep: only a category that is not itself grouped can
            // be a parent, and nothing can be its own.
            parentOptions={categoryRows.filter(
              (c) => c.id !== row.id && (c.parent_id === null || c.parent_id === undefined),
            )}
            parentName={nameById.get(row.parent_id) || null}
            childCount={childCounts.get(row.id) || 0}
            busy={categoriesBusy}
            onRename={onRenameCategory}
            onPatch={onPatchCategory}
            onMerge={onMergeCategory}
            onDelete={onDeleteCategory}
            onSetParent={onSetCategoryParent}
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
          <label className="set-cat-showarchived">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => onShowArchivedChange(e.target.checked)}
            />
            <span>Show archived</span>
          </label>
        </div>
      </SettingsCard>

      <SettingsCard
        title="Learned from your transactions"
        hint={learned.length ? `${learned.length} merchant${learned.length === 1 ? '' : 's'}` : undefined}
        flush
      >
        {learned.length === 0 ? (
          <div className="set-empty">
            Nothing learned yet — categorize a transaction and say yes when it
            offers to remember the merchant.
          </div>
        ) : learned.map((rule) => (
          <LearnedRuleRow
            key={rule.id}
            rule={rule}
            busy={learnedBusy}
            onToggle={onToggleLearned}
            onRemove={onRemoveLearned}
          />
        ))}
      </SettingsCard>

      <SettingsCard title="Auto-categorization rules" hint="first match wins" flush>
        {rules.length === 0 ? (
          <div className="set-empty">
            No rules yet — without one, categories come from the automatic guess.
          </div>
        ) : rules.map((rule) => (
          <RuleRow
            key={rule.key}
            rule={rule}
            categories={categories}
            onChange={(next) => updateRule(rule.key, next)}
            onRemove={() => removeRule(rule.key)}
          />
        ))}
        <button type="button" className="set-inst-add" onClick={addRule}>
          + Add rule
        </button>
      </SettingsCard>
    </>
  );
}
