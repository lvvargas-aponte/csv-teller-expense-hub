import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import Spin from '../ui/Spin';
import AdvisorMemory from './AdvisorMemory';
import {
  sendMessage,
  sendMessageStream,
  listConversations,
  getConversation,
  deleteConversation,
  submitFeedback,
  getStyleProfile,
  refreshStyleProfile,
} from '../../api/advisor';

const TOOL_STATUS = {
  think: 'Planning…',
  web_search: 'Searching the web…',
  fetch_webpage: 'Reading a page…',
  get_stock_quote: 'Checking live prices…',
  get_stock_history: 'Pulling price history…',
  get_stock_fundamentals: 'Checking fundamentals…',
  get_investments: 'Looking at your portfolio…',
  list_accounts: 'Looking up your accounts…',
  search_transactions: 'Searching your transactions…',
  get_category_spending: 'Adding up your spending…',
  search_documents: 'Checking your documents…',
  recall_past_conversation: 'Recalling past chats…',
  recall_about_user: 'Checking what I remember…',
  remember_about_user: 'Noting that down…',
  sync_transactions: 'Syncing your bank transactions…',
  refresh_balances: 'Refreshing your balances…',
  sync_investments: 'Syncing your brokerage holdings…',
  schedule_sync: 'Setting up the schedule…',
  list_scheduled_tasks: 'Checking your schedules…',
  cancel_scheduled_task: 'Cancelling the schedule…',
};

const EXAMPLES = [
  'How did our dining spending change this month?',
  'Are our shared splits fair between the two of us?',
  'Can I afford $300 extra toward my credit card debt?',
  'Where is our biggest opportunity to save next month?',
];

export default function AdvisorChat() {
  const [conversations, setConversations] = useState([]);
  const [activeId,      setActiveId]      = useState(null);
  const [messages,      setMessages]      = useState([]);
  const [input,         setInput]         = useState('');
  const [sending,       setSending]       = useState(false);
  const [loadingConv,   setLoadingConv]   = useState(false);
  const [error,         setError]         = useState(null);
  const [aiUnavailable, setAiUnavailable] = useState(false);
  // Per-message thumbs state, keyed by turn_id. -1 / +1 once rated.
  const [ratings, setRatings] = useState({});
  const [draft, setDraft] = useState('');           // streamed reply so far
  const [toolStatus, setToolStatus] = useState(null); // live "Searching…" line
  const [styleProfile, setStyleProfile] = useState(null);
  const [styleOpen, setStyleOpen] = useState(false);
  const [styleRefreshing, setStyleRefreshing] = useState(false);
  const scrollRef = useRef(null);

  const loadList = useCallback(async () => {
    try {
      const r = await listConversations();
      setConversations(r.data);
    } catch {
      /* silent — sidebar can stay empty */
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  // Auto-scroll to the newest message
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, draft, toolStatus]);

  const openConversation = useCallback(async (id) => {
    setLoadingConv(true);
    setError(null);
    try {
      const r = await getConversation(id);
      setActiveId(id);
      setMessages(r.data.messages || []);
      setAiUnavailable(false);
    } catch {
      setError('Could not load conversation.');
    } finally {
      setLoadingConv(false);
    }
  }, []);

  const startNew = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setError(null);
    setAiUnavailable(false);
  }, []);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    const optimistic = { role: 'user', content: text, ts: new Date().toISOString() };
    setMessages((prev) => [...prev, optimistic]);
    setInput('');
    setSending(true);
    setError(null);
    setAiUnavailable(false);
    setDraft('');
    setToolStatus(null);

    const applyDone = ({ conversation_id, reply, ai_available, turn_id }) => {
      if (!activeId) setActiveId(conversation_id);
      if (ai_available && reply) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: reply, ts: new Date().toISOString(), turn_id },
        ]);
      } else {
        setAiUnavailable(true);
      }
      loadList();
    };

    try {
      const done = await sendMessageStream(activeId, text, {
        onToken: (t) => {
          setToolStatus(null);
          setDraft((prev) => prev + t);
        },
        onTool: (ev) => {
          if (ev.type === 'tool_call') {
            // Any pre-tool text was deliberation, not the answer — clear it.
            setDraft('');
            setToolStatus(TOOL_STATUS[ev.name] || 'Working…');
          }
        },
      });
      applyDone(done);
    } catch {
      // Streaming unavailable (proxy, older backend) — fall back to blocking.
      try {
        const r = await sendMessage(activeId, text);
        applyDone(r.data);
      } catch {
        setError('Could not reach the advisor — is the backend running?');
      }
    } finally {
      setSending(false);
      setDraft('');
      setToolStatus(null);
    }
  }, [input, sending, activeId, loadList]);

  const handleDelete = useCallback(async (id, e) => {
    e.stopPropagation();
    try {
      await deleteConversation(id);
      if (activeId === id) startNew();
      loadList();
    } catch {
      /* silent */
    }
  }, [activeId, startNew, loadList]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleRate = useCallback(async (turnId, rating) => {
    if (!turnId) return;
    setRatings((prev) => ({ ...prev, [turnId]: rating }));   // optimistic
    try {
      await submitFeedback(turnId, rating);
    } catch {
      setRatings((prev) => {
        const next = { ...prev };
        delete next[turnId];
        return next;
      });
    }
  }, []);

  const loadStyleProfile = useCallback(async () => {
    try {
      const r = await getStyleProfile();
      setStyleProfile(r.data);
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => { loadStyleProfile(); }, [loadStyleProfile]);

  const handleRefreshStyle = useCallback(async () => {
    setStyleRefreshing(true);
    try {
      const r = await refreshStyleProfile();
      setStyleProfile(r.data);
    } catch {
      /* silent */
    } finally {
      setStyleRefreshing(false);
    }
  }, []);

  return (
    <div className="advisor-chat">
      <aside className="advisor-sidebar">
        <button type="button" className="btn btn-primary btn-sm" onClick={startNew}
                style={{ width: '100%', marginBottom: 12 }}>
          + New chat
        </button>
        <div className="advisor-conv-list">
          {conversations.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 4px' }}>
              No conversations yet.
            </div>
          )}
          {conversations.map((c) => (
            <div key={c.conversation_id} className="advisor-conv-row">
              <button
                type="button"
                onClick={() => openConversation(c.conversation_id)}
                className={'advisor-conv-item' + (activeId === c.conversation_id ? ' advisor-conv-item--active' : '')}
              >
                <div className="advisor-conv-preview">{c.preview || '(empty)'}</div>
                <div className="advisor-conv-meta">{c.message_count} msgs</div>
              </button>
              <button
                type="button"
                aria-label={`Delete conversation: ${c.preview || 'empty conversation'}`}
                onClick={(e) => handleDelete(c.conversation_id, e)}
                className="advisor-conv-delete"
              >
                <span aria-hidden="true">✕</span>
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="advisor-main">
        <div ref={scrollRef} className="advisor-messages">
          {loadingConv && (
            <div style={{ textAlign: 'center', padding: 20 }}><Spin /> Loading…</div>
          )}
          {!loadingConv && messages.length === 0 && (
            <div className="advisor-empty">
              <div className="advisor-empty-title">Ask Fin anything</div>
              <div className="advisor-empty-hint">
                Fin sees your transactions, balances, and shared splits.
                Try one of these:
              </div>
              <div className="advisor-empty-examples">
                {EXAMPLES.map((e, i) => (
                  <button key={i} type="button" className="advisor-example"
                          onClick={() => setInput(e)}>
                    {e}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => {
            const rated = m.turn_id ? ratings[m.turn_id] : null;
            return (
              <div key={i} className={`advisor-msg advisor-msg--${m.role}`}>
                <div className="advisor-msg-role">{m.role === 'user' ? 'You' : 'Fin'}</div>
                <div className="advisor-msg-content">
                  {m.role === 'assistant'
                    ? <ReactMarkdown>{m.content}</ReactMarkdown>
                    : m.content}
                </div>
                {m.role === 'assistant' && m.turn_id && (
                  <div className="advisor-msg-feedback" style={{ marginTop: 6, display: 'flex', gap: 8 }}>
                    <button
                      type="button"
                      aria-label="Helpful reply"
                      onClick={() => handleRate(m.turn_id, 1)}
                      className="advisor-thumb"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: 14,
                        opacity: rated === 1 ? 1 : 0.5,
                      }}
                    >
                      <span aria-hidden="true">👍</span>
                    </button>
                    <button
                      type="button"
                      aria-label="Unhelpful reply"
                      onClick={() => handleRate(m.turn_id, -1)}
                      className="advisor-thumb"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: 14,
                        opacity: rated === -1 ? 1 : 0.5,
                      }}
                    >
                      <span aria-hidden="true">👎</span>
                    </button>
                  </div>
                )}
              </div>
            );
          })}
          {sending && (
            <div className="advisor-msg advisor-msg--assistant">
              <div className="advisor-msg-role">Fin</div>
              <div className="advisor-msg-content">
                {draft
                  ? <ReactMarkdown>{draft}</ReactMarkdown>
                  : <><Spin /> {toolStatus || 'Thinking…'}</>}
              </div>
            </div>
          )}
          {aiUnavailable && (
            <div className="ai-card ai-card--nudge" style={{ marginTop: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Advisor offline</div>
              <div style={{ fontSize: 13 }}>
                Start Ollama with <code>ollama serve</code> and pull a model, e.g.{' '}
                <code>ollama pull qwen2.5:14b-instruct</code>.
              </div>
            </div>
          )}
          {error && <div style={{ color: 'var(--status-bad-text)', fontSize: 13 }}>{error}</div>}
        </div>

        <AdvisorMemory />

        <div className="advisor-style-panel" style={{ borderTop: '1px solid var(--border)', padding: '8px 12px' }}>
          <button
            type="button"
            onClick={() => setStyleOpen((v) => !v)}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontSize: 12, color: 'var(--text-muted)', padding: 0,
            }}
          >
            <span aria-hidden="true">{styleOpen ? '▼' : '▶'}</span> Fin&apos;s read on you
            {styleProfile?.updated_at && (
              <span style={{ marginLeft: 8, opacity: 0.6 }}>
                · updated {new Date(styleProfile.updated_at).toLocaleString()}
              </span>
            )}
          </button>
          {styleOpen && (
            <div style={{ marginTop: 6 }}>
              <pre style={{
                whiteSpace: 'pre-wrap', fontSize: 12,
                background: 'var(--surface-muted)',
                padding: 8, borderRadius: 6, margin: 0,
              }}>
                {styleProfile?.style_notes
                  ? styleProfile.style_notes
                  : '(no profile yet — chat a bit, then refresh)'}
              </pre>
              <button
                type="button"
                className="btn btn-sm"
                onClick={handleRefreshStyle}
                disabled={styleRefreshing}
                style={{ marginTop: 6 }}
              >
                {styleRefreshing ? <Spin /> : 'Refresh'}
              </button>
            </div>
          )}
        </div>

        <div className="advisor-input-row">
          <textarea
            className="form-input advisor-input"
            placeholder="Ask about spending, debts, shared splits…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
          />
          <button type="button" className="btn btn-primary"
                  onClick={handleSend}
                  disabled={sending || !input.trim()}>
            {sending ? <Spin /> : 'Send'}
          </button>
        </div>
      </section>
    </div>
  );
}
