import React, { useCallback, useEffect, useState } from 'react';
import Num from './Num';
import { pickIcon, prettifyName } from './cards/RecurringChargesCard';
import {
  clearSubscriptionReview,
  listCommitmentCandidates,
  listSubscriptions,
  mergeMerchant,
  reviewSubscription,
} from '../../api/subscriptions';

const CADENCE_LABELS = {
  weekly: 'Weekly',
  biweekly: 'Every 2 weeks',
  monthly: 'Monthly',
  bimonthly: 'Every 2 months',
  quarterly: 'Quarterly',
  semiannual: 'Twice a year',
  annual: 'Yearly',
  irregular: 'Irregular',
};

const DECISION_LABELS = { keep: 'Keeping', cancel: 'Canceling', ignore: 'Not a subscription' };

function Badge({ children, tone = 'muted' }) {
  const tones = {
    muted: { background: 'var(--surface-muted)', color: 'var(--text-muted)' },
    warn: { background: 'var(--warn-wash)', color: 'var(--warn-text)' },
    danger: { background: 'var(--bad-wash)', color: 'var(--bad-text)' },
    ok: { background: 'var(--good-wash)', color: 'var(--good-text)' },
  };
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.04em', padding: '2px 8px', borderRadius: 99,
      whiteSpace: 'nowrap', ...tones[tone],
    }}>
      {children}
    </span>
  );
}

function SummaryStat({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 18, fontWeight: 700, fontFamily: "'DM Mono', monospace" }}>
        {children}
      </span>
    </div>
  );
}

export default function SubscriptionsSection() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busyKey, setBusyKey] = useState(null);

  const load = useCallback(() => {
    listSubscriptions()
      .then((r) => { setData(r.data); setError(null); })
      .catch(() => setError('Could not load subscriptions — is the backend running?'));
  }, []);

  useEffect(() => { load(); }, [load]);

  const act = useCallback((merchantKey, decision, declared = {}) => {
    setBusyKey(merchantKey);
    const call = decision === null
      ? clearSubscriptionReview(merchantKey)
      : reviewSubscription(merchantKey, decision, declared);
    call.then(load).catch(load).finally(() => setBusyKey(null));
  }, [load]);

  const merge = useCallback((merchantKey, into) => {
    setBusyKey(merchantKey);
    mergeMerchant(merchantKey, into).then(load).catch(load)
      .finally(() => setBusyKey(null));
  }, [load]);

  if (error) return <div className="eh-card" style={{ padding: 16 }}>{error}</div>;
  if (!data) return <div className="eh-card" style={{ padding: 16 }}>Loading…</div>;

  // Defaults, not decoration: this renders beside two other sections now, so
  // a payload missing its summary must degrade to an empty list rather than
  // take the whole Commitments page down.
  const { subscriptions = [], dormant = [], summary = {} } = data;
  // Merge targets come from both lists: the renamed half of a pair is usually
  // the dormant one, and either half can be the survivor.
  const allRows = [...subscriptions, ...dormant];

  return (
    <div className="eh-card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Subscriptions &amp; recurring charges</h2>
        {summary.needs_review_count > 0 && (
          <Badge tone="warn">{summary.needs_review_count} to review</Badge>
        )}
      </div>
      <div style={{ display: 'flex', gap: 32, margin: '12px 0 16px', flexWrap: 'wrap' }}>
        <SummaryStat label="Active per month"><Num value={summary.active_monthly_cost} /></SummaryStat>
        <SummaryStat label="Savings once canceled"><Num value={summary.cancel_monthly_savings} /></SummaryStat>
      </div>

      {subscriptions.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          No recurring charges detected yet (need ≥2 months of similar charges).
        </div>
      )}

      <div style={{ display: 'grid', gap: 8 }}>
        {subscriptions.map((s) => (
          <SubRow key={s.merchant_key} s={s} busy={busyKey === s.merchant_key}
                  act={act} peers={allRows} onMerge={merge} />
        ))}
      </div>

      {dormant.length > 0 && (
        // Collapsed, not hidden: a charge that quietly stopped is sometimes a
        // failed payment rather than a cancellation, and that is worth seeing.
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--text-muted)' }}>
            {dormant.length} no longer seen
            {summary.as_of ? ` (as of your latest transaction, ${summary.as_of})` : ''}
          </summary>
          <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
            {dormant.map((s) => (
              <SubRow key={s.merchant_key} s={s} busy={busyKey === s.merchant_key}
                      act={act} peers={allRows} onMerge={merge} />
            ))}
          </div>
        </details>
      )}

      <AddCommitment onAdded={load} />
    </div>
  );
}

// Detection needs two charges to measure a gap, so a yearly renewal in a
// seven-month history and a bill that has charged once are both invisible to
// it — and invisible means they can never be declared either. This is the way
// in: pick the merchant, say how often it bills, and it becomes a commitment.
function AddCommitment({ onAdded }) {
  const [open, setOpen] = useState(false);
  const [candidates, setCandidates] = useState(null);
  const [merchantKey, setMerchantKey] = useState('');
  const [cadence, setCadence] = useState('monthly');
  const [type, setType] = useState('subscription');
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || candidates !== null) return;
    listCommitmentCandidates()
      .then((r) => setCandidates(r.data.candidates || []))
      .catch(() => setCandidates([]));
  }, [open, candidates]);

  const save = () => {
    if (!merchantKey) return;
    setSaving(true);
    setFailed(false);
    reviewSubscription(merchantKey, 'keep', {
      declared_cadence: cadence,
      declared_type: type,
    })
      .then(() => {
        setMerchantKey('');
        setCandidates(null);
        onAdded();
      })
      .catch(() => setFailed(true))
      .finally(() => setSaving(false));
  };

  if (!open) {
    return (
      <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 12 }}
              onClick={() => setOpen(true)}>
        + Add a commitment we missed
      </button>
    );
  }

  return (
    <div style={{
      marginTop: 12, padding: 12, borderRadius: 10,
      border: '1px dashed var(--border)', display: 'grid', gap: 8,
    }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        Something billed once so far — a yearly renewal, or a payment we have
        too little history to spot? Tell us how often it bills.
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label className="sr-only" htmlFor="add-commitment-merchant">Merchant</label>
        <select id="add-commitment-merchant" className="form-input" disabled={saving}
                style={{ flex: '2 1 260px', minWidth: 0 }}
                value={merchantKey} onChange={(e) => setMerchantKey(e.target.value)}>
          <option value="">{candidates === null ? 'Loading…' : 'Pick a merchant…'}</option>
          {(candidates || []).map((c) => (
            <option key={c.merchant_key} value={c.merchant_key}>
              {prettifyName(c.sample_description)} — ${c.latest_amount} ({c.last_seen})
            </option>
          ))}
        </select>

        <label className="sr-only" htmlFor="add-commitment-cadence">Billing frequency</label>
        <select id="add-commitment-cadence" className="form-input" disabled={saving}
                style={{ flex: '1 1 140px' }}
                value={cadence} onChange={(e) => setCadence(e.target.value)}>
          {Object.entries(CADENCE_LABELS)
            .filter(([value]) => value !== 'irregular')
            .map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>

        <label className="sr-only" htmlFor="add-commitment-type">Kind</label>
        <select id="add-commitment-type" className="form-input" disabled={saving}
                style={{ flex: '1 1 140px' }}
                value={type} onChange={(e) => setType(e.target.value)}>
          <option value="subscription">Subscription</option>
          <option value="bill">Bill</option>
          <option value="recurring_spend">Recurring spend</option>
        </select>

        <button type="button" className="btn btn-secondary btn-sm"
                disabled={saving || !merchantKey} onClick={save}>
          Add
        </button>
        <button type="button" className="btn btn-ghost btn-sm" disabled={saving}
                onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {candidates?.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Nothing left to add — every merchant we can see is already tracked.
        </div>
      )}
      {failed && (
        <div style={{ fontSize: 12, color: 'var(--red)' }}>
          Could not save that — is the backend running?
        </div>
      )}
    </div>
  );
}

// One row, used by both the live list and the collapsed "no longer seen"
// group. Dormant rows differ only in what they ask and what they offer:
// there is nothing to cancel on a charge that already stopped.
function SubRow({ s, busy, act, peers = [], onMerge }) {
  const { icon, color } = pickIcon(s.sample_description, s.category);
  const name = prettifyName(s.sample_description);
  const decision = s.review?.decision || null;
  const changePct = s.price_change_since_review_pct ?? s.price_change_pct;
  const priceUp = changePct > 0 && Math.abs(changePct) >= 10;
  const dormant = s.status === 'dormant';
  const question = s.open_question;

  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px',
        borderRadius: 10, flexWrap: 'wrap',
        border: `1px solid ${s.needs_review ? 'var(--warn)' : 'var(--border)'}`,
        opacity: decision === 'ignore' || decision === 'cancel' ? 0.6 : 1,
      }}
    >
      <span style={{
        width: 32, height: 32, borderRadius: 8, flexShrink: 0,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: color, fontSize: 16,
      }}>{icon}</span>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 600 }}>{name}</span>
          {dormant && <Badge>No longer seen</Badge>}
          {!dormant && s.status === 'overdue' && <Badge tone="warn">Overdue</Badge>}
          {s.needs_review && !question && <Badge tone="warn">Review</Badge>}
          {priceUp && (
            <Badge tone="danger">
              <span aria-hidden="true">▲</span> up {Math.abs(changePct).toFixed(0)}%
            </Badge>
          )}
          {s.overlap_group && <Badge tone="warn">Overlaps</Badge>}
          {decision && !s.needs_review && <Badge tone="ok">{DECISION_LABELS[decision]}</Badge>}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
          {CADENCE_LABELS[s.cadence] || s.cadence}
          {s.cadence_declared ? ' (you set this)' : ''}
          {s.interval_days && !s.cadence_declared ? ` · every ~${s.interval_days}d` : ''}
          {s.category && s.category !== 'Uncategorized' ? ` · ${s.category}` : ''}
          {` · last ${s.last_seen}`}
        </div>
      </div>

      <div style={{ textAlign: 'right', fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
        <Num value={s.estimated_monthly_cost} />
        <div style={{ fontSize: 10, fontWeight: 400, color: 'var(--text-muted)' }}>/mo</div>
      </div>

      <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
        {decision === null && !question && (
          <>
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                    onClick={() => act(s.merchant_key, 'keep')}>
              Keep
            </button>
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                    onClick={() => act(s.merchant_key, 'cancel')}>
              Cancel it
            </button>
            <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
                    title="Not a subscription — hide from review"
                    onClick={() => act(s.merchant_key, 'ignore')}>
              Ignore
            </button>
          </>
        )}
        {decision !== null && !question && (
          s.needs_review ? (
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                    onClick={() => act(s.merchant_key, decision)}>
              Confirm
            </button>
          ) : (
            <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
                    onClick={() => act(s.merchant_key, null)}>
              Undo
            </button>
          )
        )}
      </div>

      {question && (
        <Question s={s} busy={busy} act={act} kind={question} />
      )}

      {onMerge && <MergeControl s={s} busy={busy} peers={peers} onMerge={onMerge} />}
    </div>
  );
}

// A merchant that renames itself ("Google FIBER" → "GFiber") forks into two
// rows, each with half the history. Merging is user-declared: matching names
// automatically would fold together things that merely look alike.
function MergeControl({ s, busy, peers, onMerge }) {
  const [open, setOpen] = useState(false);
  const targets = peers.filter((p) => p.merchant_key !== s.merchant_key);
  const mergedFrom = s.merged_from || [];

  if (mergedFrom.length > 0) {
    return (
      <div style={{ flexBasis: '100%', fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
        Includes {mergedFrom.length} merged {mergedFrom.length === 1 ? 'name' : 'names'}:{' '}
        {mergedFrom.join(', ')}
      </div>
    );
  }
  if (targets.length === 0) return null;

  if (!open) {
    return (
      <button type="button" className="btn btn-ghost btn-sm"
              style={{ flexBasis: '100%', textAlign: 'left', fontSize: 11 }}
              disabled={busy} onClick={() => setOpen(true)}>
        Same as another merchant?
      </button>
    );
  }

  return (
    <div style={{
      flexBasis: '100%', marginTop: 8, paddingTop: 8,
      borderTop: '1px dashed var(--border)',
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
    }}>
      <label className="sr-only" htmlFor={`merge-${s.merchant_key}`}>
        Merge {prettifyName(s.sample_description)} into
      </label>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Merge into</span>
      <select id={`merge-${s.merchant_key}`} className="form-input" defaultValue=""
              disabled={busy}
              style={{ width: 'auto', fontSize: 'var(--text-sm)', padding: '4px 8px' }}
              onChange={(e) => {
                if (!e.target.value) return;
                onMerge(s.merchant_key, e.target.value);
              }}>
        <option value="" disabled>Pick the merchant to keep…</option>
        {targets.map((p) => (
          <option key={p.merchant_key} value={p.merchant_key}>
            {prettifyName(p.sample_description)}
          </option>
        ))}
      </select>
      <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
              onClick={() => setOpen(false)}>
        Cancel
      </button>
    </div>
  );
}

// The detector guessed and could not settle it. Rather than pick for the user
// and be wrong in silence, ask — and store the answer so it is asked once.
function Question({ s, busy, act, kind }) {
  const ask = kind === 'cadence'
    ? 'No steady pattern here. How often is this billed?'
    : `Nothing since ${s.last_seen}. Is this still active?`;

  return (
    <div style={{
      flexBasis: '100%', marginTop: 8, paddingTop: 8,
      borderTop: '1px dashed var(--border)',
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
    }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{ask}</span>
      <label className="sr-only" htmlFor={`cadence-${s.merchant_key}`}>
        Billing frequency for {prettifyName(s.sample_description)}
      </label>
      <select
        id={`cadence-${s.merchant_key}`}
        className="form-input"
        style={{ width: 'auto', fontSize: 'var(--text-sm)', padding: '4px 8px' }}
        defaultValue=""
        disabled={busy}
        onChange={(e) => {
          if (!e.target.value) return;
          act(s.merchant_key, 'keep', { declared_cadence: e.target.value });
        }}
      >
        <option value="" disabled>Set frequency…</option>
        {Object.entries(CADENCE_LABELS)
          .filter(([value]) => value !== 'irregular')
          .map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
      </select>
      <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
              onClick={() => act(s.merchant_key, 'ignore')}>
        {kind === 'cadence' ? 'One-time thing' : 'It ended'}
      </button>
    </div>
  );
}
