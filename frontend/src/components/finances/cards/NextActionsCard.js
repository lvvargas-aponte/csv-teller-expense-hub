import React, { useCallback, useEffect, useState } from 'react';

import Spin from '../../ui/Spin';
import { fmt$ } from '../../../utils/formatting';
import { userMessage } from '../../../utils/errorMessage';
import { dismissAction, getActions } from '../../../api/coach';

const URGENCY_LABEL = {
  now: 'Now',
  this_week: 'This week',
  this_month: 'This month',
  fyi: 'Worth knowing',
};

function Action({ action, onNavigate, onDismiss, dismissing }) {
  return (
    <li className={`act act--${action.urgency}`}>
      <div className="act-head">
        <span className={`act-urgency act-urgency--${action.urgency}`}>
          {URGENCY_LABEL[action.urgency] || action.urgency}
        </span>
        <span className="act-title">{action.title}</span>
        {action.dismissible && (
          <button
            type="button"
            className="act-dismiss"
            onClick={() => onDismiss(action.id)}
            disabled={dismissing}
            aria-label={`Dismiss: ${action.title}`}
            title="Dismiss"
          >✕</button>
        )}
      </div>

      <div className="act-detail">{action.detail}</div>

      {action.why?.length > 0 && (
        <ul className="act-why">
          {action.why.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}

      <div className="act-foot">
        {action.impact && (
          <span className="act-impact">
            {fmt$(action.impact.value)} {action.impact.label}
            {action.impact.horizon && <span className="act-horizon"> · {action.impact.horizon}</span>}
          </span>
        )}
        {action.cta && (
          <button
            type="button"
            className="act-cta"
            onClick={() => onNavigate(action.cta.tab)}
          >
            {action.cta.label} ›
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * The ranked list. Urgency wins over dollar size on purpose: "you're over
 * budget today" sits above "this saves $38,000 over thirty years", because
 * only one of them is about a decision you can still make today.
 */
export default function NextActionsCard({ onNavigate }) {
  const [actions, setActions] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dismissing, setDismissing] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    getActions()
      .then((r) => { setActions(r.data.actions); setTotal(r.data.total); })
      .catch((e) => setError(userMessage(e, 'Could not load your next actions.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const handleDismiss = async (actionId) => {
    setDismissing(actionId);
    // Optimistic — the action is gone from the user's point of view the
    // instant they dismiss it; a failure restores it on the next load.
    setActions((prev) => prev.filter((a) => a.id !== actionId));
    try {
      await dismissAction(actionId);
    } catch (e) {
      setError(userMessage(e, 'Could not dismiss that.'));
      load();
    } finally {
      setDismissing(null);
    }
  };

  if (loading && actions.length === 0) {
    return <section className="ov-card"><Spin /></section>;
  }
  if (error) {
    return <section className="ov-card"><div className="ov-error">{error}</div></section>;
  }
  if (actions.length === 0) {
    return (
      <section className="ov-card">
        <div className="ov-card-header">
          <div className="ov-card-title">Nothing needs you right now</div>
        </div>
        <div className="ov-card-body">
          <div className="act-empty">
            No budgets are over, no bills are close, and nothing is off pace.
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">Do this</div>
        <div className="ov-card-subtitle">
          {total > actions.length
            ? `Top ${actions.length} of ${total}, most urgent first`
            : 'Most urgent first'}
        </div>
      </div>
      <div className="ov-card-body">
        <ul className="act-list">
          {actions.map((action) => (
            <Action
              key={action.id}
              action={action}
              onNavigate={onNavigate}
              onDismiss={handleDismiss}
              dismissing={dismissing === action.id}
            />
          ))}
        </ul>
      </div>
    </section>
  );
}
