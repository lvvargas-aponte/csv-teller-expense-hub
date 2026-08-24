import React, { useState } from 'react';
import axios from 'axios';
import Spin from '../ui/Spin';

const API = process.env.REACT_APP_BACKEND_URL || '';

/**
 * Setup-token claim form.
 *
 * Once a SimpleFIN connection exists this collapses behind a disclosure —
 * extra banks are normally added at the bridge under the existing account and
 * arrive through the same access URL, so a second token is a rare path.
 */
export default function SimplefinConnectForm({ collapsible, onClaimed }) {
  const [opened,   setOpened]   = useState(false);
  const [token,    setToken]    = useState('');
  const [claiming, setClaiming] = useState(false);
  const [status,   setStatus]   = useState(null);  // { type: 'success'|'error', message }

  // Derived, not stored: `collapsible` flips once the first connection lands,
  // and seeding state from it would freeze the initial (still-loading) value.
  const expanded = !collapsible || opened;

  const handleClaim = async () => {
    const trimmed = token.trim();
    if (!trimmed) return;
    setClaiming(true);
    setStatus(null);
    try {
      const res = await axios.post(`${API}/api/simplefin/claim`, { setup_token: trimmed });
      setStatus({
        type: 'success',
        message: res.data.claimed === false
          ? 'This SimpleFIN connection was already added.'
          : 'SimpleFIN connected! Its accounts will appear after your next Sync.',
      });
      setToken('');
      // The refresh below makes this collapsible; stay open so the result is read.
      setOpened(true);
      onClaimed?.();
    } catch (e) {
      setStatus({
        type: 'error',
        message: 'Failed to connect SimpleFIN: ' + (e.response?.data?.detail || e.message),
      });
    } finally {
      setClaiming(false);
    }
  };

  if (!expanded) {
    return (
      <button type="button" className="account-connect-toggle" onClick={() => setOpened(true)}>
        + Connect another bank
      </button>
    );
  }

  return (
    <div className="account-connect">
      <div className="field-label">Connect via SimpleFIN</div>
      <div className="account-connect-help">
        Visit <a href="https://bridge.simplefin.org/simplefin/create" target="_blank" rel="noopener noreferrer">
          bridge.simplefin.org
        </a>, connect a bank, and paste the Setup Token it gives you below.
      </div>
      <div className="account-connect-controls">
        <input
          type="text"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Paste Setup Token"
          disabled={claiming}
          className="form-input"
        />
        <button type="button" className="btn btn-secondary btn-sm"
                disabled={claiming || !token.trim()} onClick={handleClaim}>
          {claiming ? <><Spin /> Connecting…</> : 'Connect'}
        </button>
      </div>

      {status && (
        <div className={`account-connect-status account-connect-status--${status.type}`}>
          <span>{status.type === 'success' ? '✓ ' : '✕ '}{status.message}</span>
          <button type="button" aria-label="Dismiss" className="account-connect-dismiss"
                  onClick={() => setStatus(null)}>
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
