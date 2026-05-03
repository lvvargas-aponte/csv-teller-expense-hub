import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import axios from 'axios';
import AccountsModal from '../accounts/AccountsModal';

jest.mock('axios');
jest.mock('../ui/Backdrop', () => ({ children }) => <div data-testid="backdrop">{children}</div>);
jest.mock('../ui/Spin', () => () => <span data-testid="spin" />);
jest.mock('../ui/styles', () => ({}));
jest.mock('../../utils/formatting', () => ({ formatAccountType: (t) => t }));

const mockAccounts = [
  {
    id: 'acct_1',
    name: 'Checking',
    type: 'depository',
    subtype: 'checking',
    institution: { name: 'First Bank' },
    balance: {},
  },
];

beforeEach(() => {
  jest.clearAllMocks();
  delete window.TellerConnect;

  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: mockAccounts });
    if (url.includes('/api/config/teller'))
      return Promise.resolve({ data: { application_id: 'app_1', environment: 'sandbox' } });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });
});

// ── Rendering ─────────────────────────────────────────────────────────────────

test('renders linked accounts on load', async () => {
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('First Bank')).toBeInTheDocument();
  expect(screen.getByText(/Checking/)).toBeInTheDocument();
});

test('renders Connect a Bank button when teller config is available', async () => {
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByRole('button', { name: /Connect a Bank/ })).toBeInTheDocument();
});

test('shows loading indicator while fetching accounts', () => {
  axios.get.mockImplementation(() => new Promise(() => {})); // never resolves
  render(<AccountsModal onClose={jest.fn()} />);
  expect(screen.getByText(/Loading/)).toBeInTheDocument();
});

test('shows empty state when no accounts are linked', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [] });
    if (url.includes('/api/config/teller'))
      return Promise.resolve({ data: { application_id: 'app_1', environment: 'sandbox' } });
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText(/No linked accounts/)).toBeInTheDocument();
});

// ── Config error ──────────────────────────────────────────────────────────────

test('shows config error and hides Connect button when teller config fails', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [] });
    if (url.includes('/api/config/teller'))
      return Promise.reject({ response: { data: { detail: 'TELLER_APP_ID not set' } } });
    return Promise.reject(new Error('Unknown URL'));
  });

  render(<AccountsModal onClose={jest.fn()} />);

  expect(await screen.findByText(/TELLER_APP_ID not set/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Connect a Bank/ })).not.toBeInTheDocument();
});

// ── Connect flow ──────────────────────────────────────────────────────────────

test('shows SDK error when TellerConnect is not on window', async () => {
  delete window.TellerConnect;
  render(<AccountsModal onClose={jest.fn()} />);

  const btn = await screen.findByRole('button', { name: /Connect a Bank/ });
  fireEvent.click(btn);

  expect(await screen.findByText(/Teller SDK failed to load/)).toBeInTheDocument();
});

test('opens TellerConnect dialog when button clicked and SDK is loaded', async () => {
  const mockOpen = jest.fn();
  window.TellerConnect = {
    setup: jest.fn(() => ({ open: mockOpen })),
  };

  render(<AccountsModal onClose={jest.fn()} />);
  const btn = await screen.findByRole('button', { name: /Connect a Bank/ });
  fireEvent.click(btn);

  expect(window.TellerConnect.setup).toHaveBeenCalledWith(
    expect.objectContaining({ applicationId: 'app_1', environment: 'sandbox' })
  );
  expect(mockOpen).toHaveBeenCalled();
});

test('shows success banner and refreshes accounts after enrollment', async () => {
  const mockOpen = jest.fn();
  window.TellerConnect = {
    setup: jest.fn(({ onSuccess }) => {
      setTimeout(() => onSuccess({
        accessToken: 'tok_new',
        enrollment: { id: 'enr_1', institution: { name: 'Test Bank' } },
      }), 0);
      return { open: mockOpen };
    }),
  };
  axios.post.mockResolvedValue({ data: { registered: true, total_tokens: 1 } });

  render(<AccountsModal onClose={jest.fn()} />);
  const btn = await screen.findByRole('button', { name: /Connect a Bank/ });
  fireEvent.click(btn);

  expect(await screen.findByText(/Test Bank connected/)).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining('/api/teller/register-token'),
    expect.objectContaining({ access_token: 'tok_new', enrollment_id: 'enr_1' })
  );
  // Should have re-fetched accounts
  expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/api/accounts'));
});

test('shows already-connected message for duplicate token', async () => {
  const mockOpen = jest.fn();
  window.TellerConnect = {
    setup: jest.fn(({ onSuccess }) => {
      setTimeout(() => onSuccess({
        accessToken: 'tok_existing',
        enrollment: { id: 'enr_2', institution: { name: 'Same Bank' } },
      }), 0);
      return { open: mockOpen };
    }),
  };
  axios.post.mockResolvedValue({ data: { registered: false, reason: 'duplicate', total_tokens: 1 } });

  render(<AccountsModal onClose={jest.fn()} />);
  const btn = await screen.findByRole('button', { name: /Connect a Bank/ });
  fireEvent.click(btn);

  expect(await screen.findByText(/already connected/)).toBeInTheDocument();
});

test('shows error banner when register-token POST fails', async () => {
  const mockOpen = jest.fn();
  window.TellerConnect = {
    setup: jest.fn(({ onSuccess }) => {
      setTimeout(() => onSuccess({
        accessToken: 'tok_bad',
        enrollment: { id: 'enr_3', institution: { name: 'Bad Bank' } },
      }), 0);
      return { open: mockOpen };
    }),
  };
  axios.post.mockRejectedValue({ response: { data: { detail: 'Server error' } } });

  render(<AccountsModal onClose={jest.fn()} />);
  const btn = await screen.findByRole('button', { name: /Connect a Bank/ });
  fireEvent.click(btn);

  expect(await screen.findByText(/Failed to save token/)).toBeInTheDocument();
});

test('dismisses status banner when ✕ is clicked', async () => {
  const mockOpen = jest.fn();
  window.TellerConnect = {
    setup: jest.fn(({ onSuccess }) => {
      setTimeout(() => onSuccess({
        accessToken: 'tok_dismiss',
        enrollment: { id: 'enr_4', institution: { name: 'Dismiss Bank' } },
      }), 0);
      return { open: mockOpen };
    }),
  };
  axios.post.mockResolvedValue({ data: { registered: true, total_tokens: 1 } });

  render(<AccountsModal onClose={jest.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: /Connect a Bank/ }));

  await screen.findByText(/Dismiss Bank connected/);
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

  await waitFor(() => {
    expect(screen.queryByText(/Dismiss Bank connected/)).not.toBeInTheDocument();
  });
});

// ── Status chips ─────────────────────────────────────────────────────────────

test('shows Active chip for open accounts', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [{ ...mockAccounts[0], status: 'open' }] });
    if (url.includes('/api/config/teller'))
      return Promise.resolve({ data: { application_id: 'app_1', environment: 'sandbox' } });
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('Active')).toBeInTheDocument();
});

test('shows Closed chip for closed accounts', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [{ ...mockAccounts[0], status: 'closed' }] });
    if (url.includes('/api/config/teller'))
      return Promise.resolve({ data: { application_id: 'app_1', environment: 'sandbox' } });
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('Closed')).toBeInTheDocument();
});

test('shows Connection Error chip for failed tokens', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [{ id: '_error_tok1234', name: 'Unknown account', type: '', subtype: '', institution: { name: '—' }, balance: {}, _connection_error: true }] });
    if (url.includes('/api/config/teller'))
      return Promise.resolve({ data: { application_id: 'app_1', environment: 'sandbox' } });
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('Connection Error')).toBeInTheDocument();
});

// ── Re-connect flow ───────────────────────────────────────────────────────────

const errorAccount = {
  id: '_error_tok1234',
  name: 'Unknown account',
  type: '', subtype: '',
  institution: { name: '—' },
  balance: {},
  _connection_error: true,
  _enrollment_id: 'enr_broken',
};

function setupReconnectMocks() {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [errorAccount] });
    if (url.includes('/api/config/teller'))
      return Promise.resolve({ data: { application_id: 'app_1', environment: 'sandbox' } });
    return Promise.reject(new Error('Unknown URL'));
  });
}

test('shows Re-connect button for connection error accounts', async () => {
  setupReconnectMocks();
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByRole('button', { name: "Reconnect account" })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Disconnect/ })).toBeInTheDocument();
});

test('Re-connect calls replace-token when enrollment_id is known', async () => {
  setupReconnectMocks();
  const mockOpen = jest.fn();
  window.TellerConnect = {
    setup: jest.fn(({ onSuccess }) => {
      setTimeout(() => onSuccess({
        accessToken: 'tok_fresh',
        enrollment: { id: 'enr_broken', institution: { name: 'First Bank' } },
      }), 0);
      return { open: mockOpen };
    }),
  };
  axios.post.mockResolvedValue({ data: { replaced: true, total_tokens: 1 } });

  render(<AccountsModal onClose={jest.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: "Reconnect account" }));

  expect(await screen.findByText(/First Bank reconnected/)).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining('/api/teller/replace-token'),
    expect.objectContaining({
      old_enrollment_id: 'enr_broken',
      new_access_token: 'tok_fresh',
    })
  );
});

test('Re-connect passes enrollmentId to TellerConnect when known', async () => {
  setupReconnectMocks();
  window.TellerConnect = {
    setup: jest.fn(() => ({ open: jest.fn() })),
  };

  render(<AccountsModal onClose={jest.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: "Reconnect account" }));

  expect(window.TellerConnect.setup).toHaveBeenCalledWith(
    expect.objectContaining({ enrollmentId: 'enr_broken' })
  );
});

test('Re-connect falls back to register-token when no enrollment_id', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [{ ...errorAccount, _enrollment_id: null }] });
    if (url.includes('/api/config/teller'))
      return Promise.resolve({ data: { application_id: 'app_1', environment: 'sandbox' } });
    return Promise.reject(new Error('Unknown URL'));
  });

  const mockOpen = jest.fn();
  window.TellerConnect = {
    setup: jest.fn(({ onSuccess }) => {
      setTimeout(() => onSuccess({
        accessToken: 'tok_new',
        enrollment: { id: 'enr_new', institution: { name: 'Some Bank' } },
      }), 0);
      return { open: mockOpen };
    }),
  };
  axios.post.mockResolvedValue({ data: { registered: true, total_tokens: 1 } });

  render(<AccountsModal onClose={jest.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: "Reconnect account" }));

  expect(await screen.findByText(/Some Bank reconnected/)).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining('/api/teller/register-token'),
    expect.objectContaining({ access_token: 'tok_new' })
  );
});

// ── Disconnect flow ───────────────────────────────────────────────────────────

test('Disconnect button shows confirmation prompt', async () => {
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');

  fireEvent.click(screen.getByRole('button', { name: /Disconnect/ }));

  expect(screen.getByText(/Disconnect\?/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Yes' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
});

test('Cancel on confirmation hides the prompt', async () => {
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');

  fireEvent.click(screen.getByRole('button', { name: /Disconnect/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

  expect(screen.queryByText(/Disconnect\?/)).not.toBeInTheDocument();
});

test('Yes on confirmation calls DELETE and removes account from list', async () => {
  axios.delete.mockResolvedValue({});

  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');

  fireEvent.click(screen.getByRole('button', { name: /Disconnect/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Yes' }));

  await waitFor(() => {
    expect(screen.queryByText('First Bank')).not.toBeInTheDocument();
  });
  expect(axios.delete).toHaveBeenCalledWith(expect.stringContaining('acct_1'));
});

// ── Close ─────────────────────────────────────────────────────────────────────

test('Close button calls onClose', async () => {
  const mockClose = jest.fn();
  render(<AccountsModal onClose={mockClose} />);
  await screen.findByText('First Bank');

  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(mockClose).toHaveBeenCalled();
});
