import React, { useState, useEffect, useCallback } from 'react';
import Spin from '../ui/Spin';
import {
  listFacts,
  createFact,
  updateFact,
  confirmFact,
  rejectFact,
  deleteFact,
} from '../../api/userFacts';

const CATEGORIES = ['preference', 'constraint', 'goal', 'life_event', 'pattern'];

const CATEGORY_LABEL = {
  preference: 'Preference',
  constraint: 'Constraint',
  goal: 'Goal',
  life_event: 'Life event',
  pattern: 'Pattern',
};

function FactRow({ fact, onConfirm, onReject, onDelete, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(fact.fact);
  const [tagsDraft, setTagsDraft] = useState((fact.tags || []).join(', '));
  const [revealed, setRevealed] = useState(!fact.sensitive);

  const isProposed = fact.status === 'proposed';
  const isRejected = fact.status === 'rejected';
  const masked = fact.sensitive && !revealed;

  const handleSave = async () => {
    const tags = tagsDraft.split(',').map((t) => t.trim()).filter(Boolean);
    await onSave(fact.id, { fact: draft.trim(), tags });
    setEditing(false);
  };

  const toggleSensitive = async () => {
    await onSave(fact.id, { sensitive: !fact.sensitive });
  };

  return (
    <div
      className="advisor-memory-row"
      style={{
        padding: '8px 10px',
        borderRadius: 6,
        background: isProposed ? 'rgba(251, 191, 36, 0.08)' : 'var(--bg-subtle, transparent)',
        border: '1px solid var(--border)',
        opacity: isRejected ? 0.5 : 1,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span
          style={{
            fontSize: 10, padding: '2px 6px', borderRadius: 10,
            background: 'var(--bg-muted, rgba(255,255,255,0.05))',
            color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.4,
          }}
        >
          {CATEGORY_LABEL[fact.category] || fact.category}
        </span>
        {isProposed && (
          <span style={{ fontSize: 10, color: 'var(--status-warn-text)' }}>Pending review</span>
        )}
        {isRejected && (
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Rejected</span>
        )}
        {fact.sensitive && (
          <button
            type="button"
            onClick={() => setRevealed((v) => !v)}
            aria-label={revealed ? 'Hide this fact' : 'Reveal this fact'}
            title={revealed ? 'Hide' : 'Reveal'}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontSize: 12, padding: 0, marginLeft: 'auto',
            }}
          >
            <span aria-hidden="true">{revealed ? '🔓' : '🔒'}</span>
          </button>
        )}
      </div>

      {editing ? (
        <>
          <textarea
            className="form-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            style={{ width: '100%', fontSize: 13, marginBottom: 4 }}
          />
          <input
            className="form-input"
            value={tagsDraft}
            onChange={(e) => setTagsDraft(e.target.value)}
            placeholder="tags, comma, separated"
            style={{ width: '100%', fontSize: 12, marginBottom: 6 }}
          />
        </>
      ) : (
        <div style={{ fontSize: 13, marginBottom: 4 }}>
          {masked ? '••••••••••••••' : fact.fact}
        </div>
      )}

      {!editing && fact.tags?.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 4 }}>
          {fact.tags.map((t) => (
            <span
              key={t}
              style={{
                fontSize: 10, padding: '1px 6px', borderRadius: 10,
                background: 'var(--bg-muted, rgba(255,255,255,0.05))',
                color: 'var(--text-muted)',
              }}
            >
              #{t}
            </span>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, fontSize: 12 }}>
        {isProposed && !editing && (
          <>
            <button type="button" className="btn btn-sm" onClick={() => onConfirm(fact.id)}>
              Confirm
            </button>
            <button type="button" className="btn btn-sm" onClick={() => onReject(fact.id)}>
              Reject
            </button>
          </>
        )}
        {editing ? (
          <>
            <button type="button" className="btn btn-sm btn-primary" onClick={handleSave}>
              Save
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-sm" onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
        {!editing && (
          <>
            <button type="button" className="btn btn-sm" onClick={toggleSensitive}>
              {fact.sensitive ? 'Make visible' : 'Mark sensitive'}
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => onDelete(fact.id)}
              aria-label="Forget this fact"
              style={{ marginLeft: 'auto', color: 'var(--status-bad-text)' }}
            >
              <span aria-hidden="true">🗑️</span>
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function AdvisorMemory() {
  const [open, setOpen] = useState(false);
  const [facts, setFacts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ fact: '', category: 'goal', tags: '', sensitive: false });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await listFacts();
      setFacts(r.data || []);
    } catch {
      /* silent — empty list is fine */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) load(); }, [open, load]);

  const proposed = facts.filter((f) => f.status === 'proposed');
  const confirmed = facts.filter((f) => f.status === 'confirmed');

  const handleConfirm = async (id) => { await confirmFact(id); await load(); };
  const handleReject = async (id) => { await rejectFact(id); await load(); };
  const handleDelete = async (id) => { await deleteFact(id); await load(); };
  const handleSave = async (id, patch) => { await updateFact(id, patch); await load(); };

  const handleAdd = async () => {
    if (!draft.fact.trim()) return;
    const tags = draft.tags.split(',').map((t) => t.trim()).filter(Boolean);
    await createFact({
      fact: draft.fact.trim(),
      category: draft.category,
      tags,
      sensitive: draft.sensitive,
    });
    setDraft({ fact: '', category: 'goal', tags: '', sensitive: false });
    setAdding(false);
    await load();
  };

  return (
    <div
      className="advisor-memory-panel"
      style={{ borderTop: '1px solid var(--border)', padding: '8px 12px' }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: 'transparent', border: 'none', cursor: 'pointer',
          fontSize: 12, color: 'var(--text-muted)', padding: 0,
          display: 'flex', alignItems: 'center', gap: 6, width: '100%',
        }}
      >
        <span><span aria-hidden="true">{open ? '▼' : '▶'}</span> Things Fin remembers</span>
        {!loading && facts.length > 0 && (
          <span style={{ opacity: 0.6 }}>
            ({confirmed.length}{proposed.length > 0 ? ` · ${proposed.length} pending` : ''})
          </span>
        )}
        {loading && <Spin />}
      </button>

      {open && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {proposed.length > 0 && (
            <>
              <div style={{ fontSize: 11, color: 'var(--status-warn-text)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Pending review
              </div>
              {proposed.map((f) => (
                <FactRow
                  key={f.id}
                  fact={f}
                  onConfirm={handleConfirm}
                  onReject={handleReject}
                  onDelete={handleDelete}
                  onSave={handleSave}
                />
              ))}
            </>
          )}

          {confirmed.length > 0 && (
            <>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Confirmed memories
              </div>
              {confirmed.map((f) => (
                <FactRow
                  key={f.id}
                  fact={f}
                  onConfirm={handleConfirm}
                  onReject={handleReject}
                  onDelete={handleDelete}
                  onSave={handleSave}
                />
              ))}
            </>
          )}

          {!loading && facts.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Nothing yet. Tell Fin something worth remembering, or add one manually below.
            </div>
          )}

          {adding ? (
            <div style={{
              padding: 8, borderRadius: 6, border: '1px solid var(--border)',
              display: 'flex', flexDirection: 'column', gap: 6,
            }}>
              <textarea
                className="form-input"
                value={draft.fact}
                onChange={(e) => setDraft({ ...draft, fact: e.target.value })}
                placeholder="e.g. I want to retire by 45"
                rows={2}
                style={{ fontSize: 13 }}
              />
              <select
                className="form-input"
                value={draft.category}
                onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                style={{ fontSize: 13 }}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>
                ))}
              </select>
              <input
                className="form-input"
                value={draft.tags}
                onChange={(e) => setDraft({ ...draft, tags: e.target.value })}
                placeholder="tags, comma, separated"
                style={{ fontSize: 12 }}
              />
              <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                <input
                  type="checkbox"
                  checked={draft.sensitive}
                  onChange={(e) => setDraft({ ...draft, sensitive: e.target.checked })}
                />
                Sensitive (masked by default in this panel)
              </label>
              <div style={{ display: 'flex', gap: 6 }}>
                <button type="button" className="btn btn-sm btn-primary" onClick={handleAdd}>
                  Save
                </button>
                <button type="button" className="btn btn-sm" onClick={() => setAdding(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setAdding(true)}
              style={{ alignSelf: 'flex-start' }}
            >
              + Add a memory
            </button>
          )}
        </div>
      )}
    </div>
  );
}
