import React, { useState } from 'react';

/**
 * Offered under a row right after you set its category: remember this
 * merchant, and optionally sweep the transactions already imported.
 *
 * The remember box is checked by default — categorizing the same merchant
 * over and over is the tedium this exists to end, so the common answer is
 * the pre-selected one. The sweep is not: it rewrites rows you can already
 * see, so it asks.
 *
 * Rows a higher source owns are never touched, which is why the count says
 * "categorized by rules or the bank" rather than a bare total.
 */
export default function RulePromptRow({
  colSpan,
  merchant,
  category,
  claimable = 0,
  protectedCount = 0,
  saving = false,
  onConfirm,
  onDismiss,
}) {
  const [remember, setRemember] = useState(true);
  const [applyExisting, setApplyExisting] = useState(false);

  return (
    <tr className="tx-rule-prompt-row">
      <td colSpan={colSpan}>
        <div className="tx-rule-prompt">
          <span className="tx-rule-prompt-icon" aria-hidden="true">✦</span>
          <div className="tx-rule-prompt-body">
            <label className="tx-rule-prompt-check">
              <input
                type="checkbox"
                checked={remember}
                disabled={saving}
                onChange={(e) => setRemember(e.target.checked)}
              />
              <span>
                Always categorize <code>{merchant}</code> as{' '}
                <strong>{category}</strong>
              </span>
            </label>

            {claimable > 0 && (
              <label className="tx-rule-prompt-check tx-rule-prompt-check--sub">
                <input
                  type="checkbox"
                  checked={applyExisting}
                  disabled={saving || !remember}
                  onChange={(e) => setApplyExisting(e.target.checked)}
                />
                <span>
                  Also apply to {claimable} past transaction
                  {claimable === 1 ? '' : 's'}
                </span>
              </label>
            )}

            {protectedCount > 0 && (
              <p className="tx-rule-prompt-note">
                {protectedCount} other match{protectedCount === 1 ? '' : 'es'} keep
                the category you or a rule already gave them.
              </p>
            )}
          </div>

          <div className="tx-rule-prompt-actions">
            <button
              type="button"
              className="tx-btn tx-btn-secondary"
              onClick={onDismiss}
              disabled={saving}
            >
              Not now
            </button>
            <button
              type="button"
              className="tx-btn tx-btn-primary"
              onClick={() => onConfirm({ remember, applyExisting })}
              disabled={saving || !remember}
            >
              {saving ? 'Saving…' : 'Remember'}
            </button>
          </div>
        </div>
      </td>
    </tr>
  );
}
