/**
 * Advisor API calls — virtual finance advisor chat endpoints.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const sendMessage = (conversationId, message) =>
  axios.post(`${API}/api/advisor/chat`, {
    conversation_id: conversationId || null,
    message,
  });

/**
 * Streaming chat via Server-Sent Events. Calls the handlers as events
 * arrive and resolves with the final `done` payload (same shape as the
 * blocking endpoint's response body). Throws on network/HTTP failure so
 * callers can fall back to `sendMessage`.
 *
 * handlers: { onToken(text), onTool({type, name}), onDone(done) } — all optional.
 */
export const sendMessageStream = async (conversationId, message, handlers = {}) => {
  const resp = await fetch(`${API}/api/advisor/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId || null, message }),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`stream failed: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let done = null;

  for (;;) {
    const { value, done: eof } = await reader.read();
    if (eof) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!line.startsWith('data: ')) continue;
      let event;
      try {
        event = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (event.type === 'token') {
        handlers.onToken?.(event.text);
      } else if (event.type === 'tool_call' || event.type === 'tool_result' || event.type === 'tool_error') {
        handlers.onTool?.(event);
      } else if (event.type === 'done') {
        done = event;
        handlers.onDone?.(event);
      }
    }
  }

  if (!done) throw new Error('stream ended without a done event');
  return done;
};

export const listConversations = () =>
  axios.get(`${API}/api/advisor/conversations`);

export const getConversation = (id) =>
  axios.get(`${API}/api/advisor/conversations/${id}`);

export const deleteConversation = (id) =>
  axios.delete(`${API}/api/advisor/conversations/${id}`);

export const submitFeedback = (turnId, rating, note = null) =>
  axios.post(`${API}/api/advisor/turns/${turnId}/feedback`, { rating, note });

export const getStyleProfile = () =>
  axios.get(`${API}/api/advisor/style-profile`);

export const refreshStyleProfile = () =>
  axios.post(`${API}/api/advisor/style-profile/refresh`);
