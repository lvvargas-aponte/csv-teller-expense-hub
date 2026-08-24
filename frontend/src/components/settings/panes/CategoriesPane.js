import React from 'react';
import SettingsCard from '../SettingsCard';
import categoryColor from '../categoryColor';

function RuleRow({ rule, categories, onChange, onRemove }) {
  return (
    <div className="set-rule-row">
      <div className="set-rule-col">
        <span className="set-rule-prefix">When the merchant contains</span>
        <input
          className="form-input set-input--mono"
          value={rule.match}
          placeholder="TRADER JOE"
          aria-label="Merchant text to match"
          onChange={(e) => onChange({ ...rule, match: e.target.value })}
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
        aria-label={`Delete rule for ${rule.match || 'new rule'}`}
        onClick={onRemove}
      >
        ×
      </button>
    </div>
  );
}

export default function CategoriesPane({ categories, counts, rules, onRulesChange }) {
  const addRule = () => {
    onRulesChange([
      ...rules,
      { key: `new${Date.now()}`, match: '', category: categories[0] || '' },
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
          Transactions are categorized automatically. Rules run in order, top
          to bottom — the first match wins, and a rule always beats the
          automatic guess.
        </p>
      </div>

      <SettingsCard
        title="Categories"
        hint={`${categories.length} in use`}
      >
        <div className="set-chips">
          {categories.map((name) => (
            <span key={name} className="set-chip">
              <span
                className="set-chip-dot"
                style={{ background: categoryColor(name) }}
                aria-hidden="true"
              />
              {name}
              <span className="set-chip-count">{counts?.[name] ?? 0}</span>
            </span>
          ))}
        </div>
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
