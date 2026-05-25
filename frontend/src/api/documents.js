/**
 * Documents API — knowledge-base RAG corpus.  Supports PDF / TXT / MD.
 *
 * Upload returns immediately with status='pending'; the backend embeds
 * in a background task.  Poll listDocuments() to watch status flip to
 * 'embedding' → 'ready' (or 'failed' with an error message).
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const listDocuments = () =>
  axios.get(`${API}/api/documents`);

export const uploadDocument = ({ file, scope, category, title, metadata }) => {
  const form = new FormData();
  form.append('file', file);
  form.append('scope', scope);
  form.append('category', category);
  if (title)    form.append('title', title);
  if (metadata) form.append('metadata', JSON.stringify(metadata));
  return axios.post(`${API}/api/documents`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const deleteDocument = (id) =>
  axios.delete(`${API}/api/documents/${id}`);

export const reembedDocument = (id) =>
  axios.post(`${API}/api/documents/${id}/reembed`);

export const importDocumentFromUrl = ({ url, scope, category, title, metadata }) =>
  axios.post(`${API}/api/documents/from-url`, {
    url, scope, category, title, metadata,
  });

export const getAllowedHosts = () =>
  axios.get(`${API}/api/documents/allowed-hosts`);
