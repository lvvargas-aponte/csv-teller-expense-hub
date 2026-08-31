import React, { useCallback, useEffect, useState } from 'react';
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  reembedDocument,
} from '../../api/documents';
import SuggestedSeeds from './knowledge/SuggestedSeeds';

const EXTERNAL_CATEGORIES = [
  { value: 'tax',       label: 'Tax / IRS guidance' },
  { value: 'credit',    label: 'Credit / debt strategy' },
  { value: 'investing', label: 'Investing / retirement' },
  { value: 'literacy',  label: 'General financial literacy' },
];

const PERSONAL_CATEGORIES = [
  { value: 'tax_return', label: 'Tax return (1040 / W-2 / 1099)' },
  { value: 'statement',  label: 'Account statement' },
  { value: 'paystub',    label: 'Pay stub / benefits' },
  { value: 'loan',       label: 'Loan / mortgage doc' },
];

const STATUS_BADGE = {
  pending:    { color: 'var(--warn-text)', bg: 'var(--warn-wash)', label: 'Pending' },
  embedding:  { color: 'var(--brand)', bg: 'var(--brand-wash)', label: 'Embedding…' },
  ready:      { color: 'var(--good-text)', bg: 'var(--good-wash)', label: 'Ready' },
  failed:     { color: 'var(--bad-text)', bg: 'var(--bad-wash)', label: 'Failed' },
  duplicate:  { color: 'var(--text-muted)', bg: 'var(--surface-muted)', label: 'Duplicate' },
  superseded: { color: 'var(--text-muted)', bg: 'var(--surface-muted)', label: 'Superseded' },
};

export default function KnowledgeSection() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    listDocuments()
      .then((r) => setDocs(r.data || []))
      .catch((e) => setError(e?.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while anything is mid-embed so the badge updates without a manual refresh.
  useEffect(() => {
    const inFlight = docs.some((d) => d.status === 'pending' || d.status === 'embedding');
    if (!inFlight) return;
    const t = setTimeout(load, 2000);
    return () => clearTimeout(t);
  }, [docs, load]);

  const external = docs.filter((d) => d.scope === 'external');
  const personal = docs.filter((d) => d.scope === 'personal');

  return (
    <div style={{ display: 'grid', gap: 24 }}>
      {error && (
        <div style={{ color: 'var(--bad-text)', background: 'var(--bad-wash)', padding: 12, borderRadius: 6 }}>
          {error}
        </div>
      )}

      <UploadPanel
        title="External library"
        subtitle="Reference material the advisor cites for general rules (taxes, payoff strategy, contribution limits)."
        scope="external"
        categories={EXTERNAL_CATEGORIES}
        onUploaded={load}
      />

      <DocList
        heading="External documents"
        docs={external}
        loading={loading}
        onChange={load}
      />

      <UploadPanel
        title="Your documents"
        subtitle="Personal financial documents (tax returns, statements, paystubs).  Stays local — never sent to a cloud LLM."
        scope="personal"
        categories={PERSONAL_CATEGORIES}
        onUploaded={load}
      />

      <DocList
        heading="Personal documents"
        docs={personal}
        loading={loading}
        onChange={load}
      />

      <SuggestedSeeds onImported={load} />
    </div>
  );
}

function UploadPanel({ title, subtitle, scope, categories, onUploaded }) {
  const [file, setFile] = useState(null);
  const [category, setCategory] = useState(categories[0].value);
  const [titleField, setTitleField] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const onPick = (e) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      if (!titleField) setTitleField(f.name.replace(/\.(pdf|txt|md|markdown)$/i, ''));
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setSubmitting(true);
    setFeedback(null);
    try {
      const r = await uploadDocument({
        file, scope, category, title: titleField || file.name,
      });
      const body = r.data;
      if (body.duplicate) {
        setFeedback({ kind: 'info', text: 'Already in the corpus (duplicate content).' });
      } else {
        const detected = body.detected_type && body.detected_type !== 'unknown'
          ? ` — detected: ${body.detected_type}`
          : '';
        const warn = body.warning === 'low_text_yield'
          ? ' — low text yield (looks like a scanned PDF).  OCR is not yet supported.'
          : '';
        setFeedback({ kind: 'success', text: `Uploaded${detected}.${warn}` });
        setFile(null);
        setTitleField('');
      }
      onUploaded();
    } catch (err) {
      setFeedback({ kind: 'error', text: err?.response?.data?.detail || err.message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} style={{
      border: '1px solid var(--border)', borderRadius: 8, padding: 16,
      background: 'var(--bg-card)', color: 'var(--text-primary)',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>{subtitle}</div>

      <div style={{ display: 'grid', gap: 8, gridTemplateColumns: '1fr 1fr', marginBottom: 12 }}>
        <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
          <span>File (.pdf / .txt / .md)</span>
          <input
            type="file"
            accept=".pdf,.txt,.md,.markdown"
            onChange={onPick}
          />
        </label>

        <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
          <span>Category</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {categories.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </label>

        <label style={{ gridColumn: '1 / -1', display: 'grid', gap: 4, fontSize: 13 }}>
          <span>Title (shown to the advisor)</span>
          <input
            type="text"
            value={titleField}
            onChange={(e) => setTitleField(e.target.value)}
            placeholder="e.g. IRS Pub 17 (2024)"
          />
        </label>
      </div>

      <button type="submit" disabled={!file || submitting} style={{
        background: 'var(--accent)', color: 'var(--text-inverse)', border: 0, borderRadius: 6,
        padding: '8px 16px', cursor: file && !submitting ? 'pointer' : 'not-allowed',
      }}>
        {submitting ? 'Uploading…' : 'Upload'}
      </button>

      {feedback && (
        <div style={{
          marginTop: 12, fontSize: 13,
          color: feedback.kind === 'error' ? 'var(--red)'
              : feedback.kind === 'info'  ? 'var(--text-secondary)'
              : 'var(--accent)',
        }}>
          {feedback.text}
        </div>
      )}
    </form>
  );
}

function DocList({ heading, docs, loading, onChange }) {
  if (loading && !docs.length) {
    return <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading {heading.toLowerCase()}…</div>;
  }
  if (!docs.length) {
    return (
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
        No {heading.toLowerCase()} yet.
      </div>
    );
  }

  const onDelete = async (id) => {
    if (!window.confirm('Delete this document and its embeddings?')) return;
    await deleteDocument(id);
    onChange();
  };

  const onReembed = async (id) => {
    await reembedDocument(id);
    onChange();
  };

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', color: 'var(--text-primary)' }}>
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid var(--border)',
        fontWeight: 600, fontSize: 14,
      }}>
        {heading} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>({docs.length})</span>
      </div>
      {docs.map((d) => {
        const badge = STATUS_BADGE[d.status] || STATUS_BADGE.pending;
        return (
          <div key={d.id} style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '10px 16px', borderTop: '1px solid var(--border)',
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {d.title}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {d.category} · {d.chunk_count} chunk{d.chunk_count === 1 ? '' : 's'}
                {d.metadata?.previous_version_id
                  ? ` · replaces v${d.metadata.previous_version_id}`
                  : ''}
                {d.metadata?.replaced_by_id
                  ? ` · replaced by v${d.metadata.replaced_by_id}`
                  : ''}
                {d.error ? ` · ${d.error}` : ''}
              </div>
            </div>
            <span style={{
              fontSize: 12, padding: '2px 8px', borderRadius: 12,
              color: badge.color, background: badge.bg,
            }}>
              {badge.label}
            </span>
            {d.status === 'failed' && (
              <button type="button" onClick={() => onReembed(d.id)} style={btnStyle}>
                Re-embed
              </button>
            )}
            <button type="button" onClick={() => onDelete(d.id)} style={btnStyle}>
              Delete
            </button>
          </div>
        );
      })}
    </div>
  );
}

const btnStyle = {
  background: 'transparent',
  border: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  borderRadius: 6,
  padding: '4px 10px',
  fontSize: 12,
  cursor: 'pointer',
};
