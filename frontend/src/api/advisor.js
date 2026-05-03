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

export const listConversations = () =>
  axios.get(`${API}/api/advisor/conversations`);

export const getConversation = (id) =>
  axios.get(`${API}/api/advisor/conversations/${id}`);

export const deleteConversation = (id) =>
  axios.delete(`${API}/api/advisor/conversations/${id}`);
