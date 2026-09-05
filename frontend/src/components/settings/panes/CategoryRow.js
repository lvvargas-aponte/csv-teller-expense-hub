import React, { useState } from 'react';
import categoryColor from '../categoryColor';
import { fmt$ } from '../../../utils/formatting';

// What a role means, in the terms the user sees it in rather than the
// internal name. These drive real behaviour — recurring detection and the
// spending total both read them — so the labels say what changes.
export const ROLE_LABELS = {
  non_spending:     ['Not spending', 'Moves money between your own accounts — kept out of spending totals'],
  always_recurring: ['Varies monthly', 'Still a recurring bill when the amount swings'],
  bill:             ['Bill', 'Shows under Bills'],
  subscription:     ['Subscription', 'Shows under Commitments, and counts toward overlap warnings'],
  non_commitment:   ['Not a commitment', 'A consequence of a balance, like interest or fees'],
};

function Caret({ open }) {
  return (
    <svg
      className="set-cat-caret"
      width="14" height="14" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      style={{ transform: `rotate(${open ? 90 : 0}deg)` }}
      aria-hidden="true"
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

function fmtLastUsed(iso) {
  if (!iso) return 'never used';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'never used';
  return `used ${d.toLocaleDateString()}`;
}

/**
 * One category, expanded in place.
 *
 * The rules that pick this category live inside it, so there is nothing to
 * cross-reference — but first match wins, so the order still has to be
 * visible. Merchant rules are exact and always run first, which is why they
 * carry no number; the text rules below them are numbered in the order they
 * actually run.
 */
export default function CategoryRow({
  category,
  count = 0,
  spend = 0,
  rules = [],
  parentOptions = [],
  mergeOptions = [],
  parentName = null,
  childCount = 0,
  busy = false,
  open = false,
  onToggleOpen,
  onRename,
  onPatch,
  onMerge,
  onDelete,
  onSetParent,
  onAddRule,
  onToggleRule,
  onDeleteRule,
}) {
  const [draftName, setDraftName] = useState(category.name);
  const [newPattern, setNewPattern] = useState('');

  const commitName = () => {
    const next = draftName.trim();
    if (!next || next === category.name) {
      setDraftName(category.name);
      return;
    }
    onRename(category, next);
  };

  const toggleRole = (role, on) => {
    const next = on
      ? [...category.roles, role]
      : category.roles.filter((r) => r !== role);
    onPatch(category, { roles: next });
  };

  const addRule = () => {
    const pattern = newPattern.trim();
    if (!pattern) return;
    setNewPattern('');
    onAddRule(category, pattern);
  };

  // Merchant rules run before every text rule, so only the text ones have an
  // order worth numbering.
  let textSeen = 0;
  const ordered = rules.map((rule) => {
    if (rule.kind !== 'merchant') textSeen += 1;
    return { rule, order: rule.kind === 'merchant' ? null : textSeen };
  });

  const rowClass = [
    'set-cat-row',
    category.archived ? 'set-cat-row--archived' : '',
    open ? 'set-cat-row--open' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={rowClass}>
      <button
        type="button"
        className="set-cat-main"
        // Explicit, because the row also carries its parent name and role
        // chips — the concatenated text would name one row after another.
        aria-label={category.name}
        aria-expanded={open}
        onClick={() => onToggleOpen(category)}
      >
        <Caret open={open} />
        <span
          className="set-chip-dot"
          style={{ background: category.color || categoryColor(category.name) }}
          aria-hidden="true"
        />
        <span className="set-cat-name">{category.name}</span>

        {childCount > 0 && (
          <span className="set-cat-tag">group of {childCount}</span>
        )}
        {parentName && (
          <span className="set-cat-tag" title={`Rolls up into ${parentName}`}>↳ {parentName}</span>
        )}
        {category.archived && <span className="set-cat-tag">archived</span>}

        {category.roles.map((role) => (
          <span key={role} className="set-cat-role" title={ROLE_LABELS[role]?.[1]}>
            {ROLE_LABELS[role]?.[0] || role}
          </span>
        ))}

        <span className="set-cat-spacer" />
        <span className={`set-cat-rulecount${rules.length ? '' : ' set-cat-rulecount--none'}`}>
          {rules.length === 0 ? 'no rules' : `${rules.length} rule${rules.length === 1 ? '' : 's'}`}
        </span>
        <span className="set-cat-count">{count}</span>
        <span className={`set-cat-spend${spend ? '' : ' set-cat-spend--zero'}`}>{fmt$(spend)}</span>
      </button>

      {open && (
        <div className="set-cat-panel">

          <div className="set-cat-fields">
            <label className="set-cat-field">
              <span>Name</span>
              <input
                className="form-input"
                value={draftName}
                disabled={busy}
                onChange={(e) => setDraftName(e.target.value)}
                onBlur={commitName}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitName();
                  if (e.key === 'Escape') setDraftName(category.name);
                }}
              />
            </label>

            <label className="set-cat-field">
              <span>Grouped under</span>
              <select
                className="form-input"
                value={category.parent_id ?? ''}
                disabled={busy || childCount > 0}
                title={childCount > 0
                  ? 'This category already holds others — grouping is one level deep'
                  : undefined}
                onChange={(e) => onSetParent(
                  category, e.target.value ? Number(e.target.value) : null,
                )}
              >
                <option value="">Not grouped</option>
                {parentOptions.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>

            <span className="set-cat-spacer" />

            <label className="set-cat-field">
              <span>Merge into</span>
              <select
                className="form-input"
                value=""
                disabled={busy || mergeOptions.length === 0}
                onChange={(e) => e.target.value && onMerge(category, Number(e.target.value))}
              >
                <option value="">Choose…</option>
                {mergeOptions.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>

            <div className="set-cat-actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={busy}
                onClick={() => onPatch(category, { archived: !category.archived })}
              >
                {category.archived ? 'Un-archive' : 'Archive'}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm set-cat-delete"
                disabled={busy}
                onClick={() => onDelete(category)}
              >
                Delete
              </button>
            </div>
          </div>

          <p className="set-cat-note">
            Renaming updates every transaction, budget and rule that uses it.
            {childCount > 0 && ' Spending from the categories inside rolls up here.'}
          </p>

          <div className="set-cat-subhead">
            <span>Rules that pick it</span>
            <span className="set-cat-subhint">merchant rules first, then text rules in order</span>
          </div>

          <div className="set-cat-rules">
            {ordered.map(({ rule, order }) => (
              <div
                key={rule.id}
                className={`set-cat-rule${rule.enabled ? '' : ' set-cat-rule--off'}`}
              >
                <span className="set-cat-rule-order">{order === null ? '—' : `${order}.`}</span>
                <span className={`set-cat-rule-kind set-cat-rule-kind--${rule.kind}`}>
                  {rule.kind}
                </span>
                <code className="set-cat-rule-pattern">{rule.pattern}</code>
                <span className="set-cat-spacer" />
                <span className="set-cat-rule-used">{fmtLastUsed(rule.last_matched_at)}</span>
                <label className="set-cat-rule-toggle">
                  <input
                    type="checkbox"
                    checked={rule.enabled}
                    disabled={busy}
                    aria-label={`Rule ${rule.pattern} is on`}
                    onChange={(e) => onToggleRule(rule, e.target.checked)}
                  />
                </label>
                <button
                  type="button"
                  className="set-rule-del"
                  disabled={busy}
                  aria-label={`Delete rule ${rule.pattern}`}
                  onClick={() => onDeleteRule(rule)}
                >
                  ×
                </button>
              </div>
            ))}

            {rules.length === 0 && (
              <p className="set-cat-norules">
                No rules yet. Categorize a transaction and say yes when it offers to
                remember the merchant — that writes one here.
              </p>
            )}

            <div className="set-cat-addrule">
              <input
                className="form-input"
                value={newPattern}
                placeholder="Text a description contains"
                aria-label={`New text rule for ${category.name}`}
                disabled={busy}
                onChange={(e) => setNewPattern(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addRule(); }}
              />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={busy || !newPattern.trim()}
                onClick={addRule}
              >
                Add text rule
              </button>
            </div>
          </div>

          <div className="set-cat-subhead"><span>How it behaves</span></div>
          <div className="set-cat-roles">
            {Object.entries(ROLE_LABELS).map(([role, [label, hint]]) => {
              const on = category.roles.includes(role);
              return (
                <label key={role} className="set-cat-role-check">
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={busy}
                    aria-label={`${label} — ${category.name}`}
                    onChange={(e) => toggleRole(role, e.target.checked)}
                  />
                  <span>
                    <span className={`set-cat-role-label${on ? ' set-cat-role-label--on' : ''}`}>{label}</span>
                    <span className="set-cat-role-hint">{hint}</span>
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
