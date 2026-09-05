import React, { useState } from 'react';
import categoryColor from '../categoryColor';

// What a role means, in the terms the user sees it in rather than the
// internal name. These drive real behaviour — recurring detection and the
// spending total both read them — so the labels say what changes.
export const ROLE_LABELS = {
  non_spending:     ['Not spending', 'Moves money between your own accounts — kept out of spending totals'],
  always_recurring: ['Varies monthly', 'A recurring bill even when the amount swings (utilities, insurance)'],
  bill:             ['Bill', 'Shows up under Bills'],
  subscription:     ['Subscription', 'Shows up under Commitments, and counts toward overlap warnings'],
  non_commitment:   ['Not a commitment', 'A consequence of a balance (interest, fees) rather than something you signed up for'],
};

/**
 * One category, editable in place.
 *
 * Rename is the operation this row exists for — it rewrites the label on
 * every transaction, re-keys any budget, and repoints any rule, which is
 * why it commits against the server rather than into a draft the Save bar
 * collects.
 */
export default function CategoryRow({
  category,
  siblings = [],
  busy = false,
  count = 0,
  onRename,
  onPatch,
  onMerge,
  onDelete,
}) {
  const [draftName, setDraftName] = useState(category.name);
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const commitName = () => {
    const next = draftName.trim();
    setEditing(false);
    if (!next || next === category.name) {
      setDraftName(category.name);
      return;
    }
    onRename(category, next);
  };

  const toggleRole = (role, on) => {
    const roles = on
      ? [...category.roles, role]
      : category.roles.filter((r) => r !== role);
    onPatch(category, { roles });
  };

  return (
    <div className={`set-cat-row${category.archived ? ' set-cat-row--archived' : ''}`}>
      <div className="set-cat-main">
        <span
          className="set-chip-dot"
          style={{ background: category.color || categoryColor(category.name) }}
          aria-hidden="true"
        />
        {editing ? (
          <input
            className="form-input set-cat-name-input"
            value={draftName}
            autoFocus
            disabled={busy}
            aria-label={`Rename ${category.name}`}
            onChange={(e) => setDraftName(e.target.value)}
            onBlur={commitName}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitName();
              if (e.key === 'Escape') { setDraftName(category.name); setEditing(false); }
            }}
          />
        ) : (
          <button
            type="button"
            className="set-cat-name"
            disabled={busy}
            onClick={() => setEditing(true)}
          >
            {category.name}
          </button>
        )}
        <span className="set-chip-count">{count}</span>

        {category.roles.map((role) => (
          <span key={role} className="set-cat-role" title={ROLE_LABELS[role]?.[1]}>
            {ROLE_LABELS[role]?.[0] || role}
          </span>
        ))}

        <span className="set-cat-spacer" />

        <button
          type="button"
          className="set-cat-more"
          aria-expanded={expanded}
          aria-label={`Options for ${category.name}`}
          onClick={() => setExpanded((v) => !v)}
        >
          ⋯
        </button>
      </div>

      {expanded && (
        <div className="set-cat-options">
          <fieldset className="set-cat-roles">
            <legend>How this category behaves</legend>
            {Object.entries(ROLE_LABELS).map(([role, [label, hint]]) => (
              <label key={role} className="set-cat-role-check" title={hint}>
                <input
                  type="checkbox"
                  checked={category.roles.includes(role)}
                  disabled={busy}
                  onChange={(e) => toggleRole(role, e.target.checked)}
                />
                <span>{label}</span>
              </label>
            ))}
          </fieldset>

          <div className="set-cat-actions">
            <label className="set-cat-merge">
              <span>Merge into</span>
              <select
                className="form-input"
                value=""
                disabled={busy || siblings.length === 0}
                aria-label={`Merge ${category.name} into another category`}
                onChange={(e) => e.target.value && onMerge(category, Number(e.target.value))}
              >
                <option value="">Choose…</option>
                {siblings.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>

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

          <p className="set-cat-note">
            {category.archived
              ? 'Archived: no longer offered when categorizing, and the transactions that used it keep it.'
              : 'Renaming updates every transaction, budget and rule that uses this category.'}
          </p>
        </div>
      )}
    </div>
  );
}
