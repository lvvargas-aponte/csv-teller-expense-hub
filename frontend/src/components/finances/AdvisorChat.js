import React, { useState, useEffect, useRef, useCallback } from 'react';
import Spin from '../ui/Spin';
import {
  sendMessage,
  listConversations,
  getConversation,
  deleteConversation,
} from '../../api/advisor';

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
  }, [messages]);

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

    try {
      const r = await sendMessage(activeId, text);
      const { conversation_id, reply, ai_available } = r.data;
      if (!activeId) setActiveId(conversation_id);

      if (ai_available && reply) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: reply, ts: new Date().toISOString() },
        ]);
      } else {
        setAiUnavailable(true);
      }
      loadList();
    } catch (e) {
      setError('Could not reach the advisor — is the backend running?');
    } finally {
      setSending(false);
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
            <button
              key={c.conversation_id}
              type="button"
              onClick={() => openConversation(c.conversation_id)}
              className={'advisor-conv-item' + (activeId === c.conversation_id ? ' advisor-conv-item--active' : '')}
            >
              <div className="advisor-conv-preview">{c.preview || '(empty)'}</div>
              <div className="advisor-conv-meta">{c.message_count} msgs</div>
              <span
                role="button"
                aria-label="Delete conversation"
                onClick={(e) => handleDelete(c.conversation_id, e)}
                className="advisor-conv-delete"
              >
                ✕
              </span>
            </button>
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
              <div className="advisor-empty-title">Ask your finance advisor anything</div>
              <div className="advisor-empty-hint">
                The advisor sees your transactions, balances, and shared splits.
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
          {messages.map((m, i) => (
            <div key={i} className={`advisor-msg advisor-msg--${m.role}`}>
              <div className="advisor-msg-role">{m.role === 'user' ? 'You' : 'Advisor'}</div>
              <div className="advisor-msg-content">{m.content}</div>
            </div>
          ))}
          {sending && (
            <div className="advisor-msg advisor-msg--assistant">
              <div className="advisor-msg-role">Advisor</div>
              <div className="advisor-msg-content"><Spin /> Thinking…</div>
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
          {error && <div style={{ color: '#f87171', fontSize: 13 }}>{error}</div>}
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
