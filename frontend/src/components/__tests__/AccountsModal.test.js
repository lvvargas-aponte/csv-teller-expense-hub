import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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

  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: mockAccounts });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });
});

// ── Rendering ─────────────────────────────────────────────────────────────────

test('renders linked accounts on load', async () => {
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('First Bank')).toBeInTheDocument();
  expect(screen.getByText(/Checking/)).toBeInTheDocument();
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
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText(/No linked accounts/)).toBeInTheDocument();
});

// ── SimpleFIN connect flow ───────────────────────────────────────────────────

test('renders the SimpleFIN setup-token connect form', async () => {
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');
  expect(screen.getByText('Connect via SimpleFIN')).toBeInTheDocument();
  expect(screen.getByPlaceholderText('Paste Setup Token')).toBeInTheDocument();
});

test('Connect button is disabled until a token is entered', async () => {
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');
  expect(screen.getByRole('button', { name: 'Connect' })).toBeDisabled();

  fireEvent.change(screen.getByPlaceholderText('Paste Setup Token'), { target: { value: 'tok_abc' } });
  expect(screen.getByRole('button', { name: 'Connect' })).not.toBeDisabled();
});

test('claims the SimpleFIN token and shows a success message', async () => {
  axios.post.mockResolvedValue({ data: { claimed: true } });

  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');

  fireEvent.change(screen.getByPlaceholderText('Paste Setup Token'), { target: { value: 'tok_abc' } });
  fireEvent.click(screen.getByRole('button', { name: 'Connect' }));

  expect(await screen.findByText(/SimpleFIN connected/)).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining('/api/simplefin/claim'),
    { setup_token: 'tok_abc' },
  );
  // Should have re-fetched accounts
  expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/api/accounts'));
});

test('shows already-connected message for a duplicate token', async () => {
  axios.post.mockResolvedValue({ data: { claimed: false } });

  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');

  fireEvent.change(screen.getByPlaceholderText('Paste Setup Token'), { target: { value: 'tok_dup' } });
  fireEvent.click(screen.getByRole('button', { name: 'Connect' }));

  expect(await screen.findByText(/already added/)).toBeInTheDocument();
});

test('shows error banner when the claim POST fails', async () => {
  axios.post.mockRejectedValue({ response: { data: { detail: 'Bad token' } } });

  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');

  fireEvent.change(screen.getByPlaceholderText('Paste Setup Token'), { target: { value: 'tok_bad' } });
  fireEvent.click(screen.getByRole('button', { name: 'Connect' }));

  expect(await screen.findByText(/Failed to connect SimpleFIN/)).toBeInTheDocument();
});

test('dismisses status banner when ✕ is clicked', async () => {
  axios.post.mockResolvedValue({ data: { claimed: true } });

  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('First Bank');

  fireEvent.change(screen.getByPlaceholderText('Paste Setup Token'), { target: { value: 'tok_abc' } });
  fireEvent.click(screen.getByRole('button', { name: 'Connect' }));

  await screen.findByText(/SimpleFIN connected/);
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

  await waitFor(() => {
    expect(screen.queryByText(/SimpleFIN connected/)).not.toBeInTheDocument();
  });
});

// ── Status chips ─────────────────────────────────────────────────────────────

test('shows Active chip for open accounts', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [{ ...mockAccounts[0], status: 'open' }] });
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('Active')).toBeInTheDocument();
});

test('shows Closed chip for closed accounts', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [{ ...mockAccounts[0], status: 'closed' }] });
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('Closed')).toBeInTheDocument();
});

test('shows Connection Error chip for failed connections', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [{ id: '_error_tok1234', name: 'Unknown account', type: '', subtype: '', institution: { name: '—' }, balance: {}, _connection_error: true, _source: 'simplefin' }] });
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('Connection Error')).toBeInTheDocument();
});

test('shows Rate Limited chip for 429 errors', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts'))
      return Promise.resolve({ data: [{ id: '_error_tok1234', name: 'Unknown account', type: '', subtype: '', institution: { name: '—' }, balance: {}, _connection_error: true, _error_status: 429, _source: 'simplefin' }] });
    return Promise.reject(new Error('Unknown URL'));
  });
  render(<AccountsModal onClose={jest.fn()} />);
  expect(await screen.findByText('Rate Limited')).toBeInTheDocument();
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

// ── Grouping ─────────────────────────────────────────────────────────────────

const groupedAccounts = [
  { id: 'sf_1', name: 'Prime Visa',    type: 'credit',     subtype: 'credit card', institution: { name: 'Chase Bank' },     balance: {}, _source: 'simplefin' },
  { id: 'sf_2', name: 'TOTAL CHECKING', type: 'depository', subtype: 'checking',   institution: { name: 'Chase Bank' },     balance: {}, _source: 'simplefin' },
  { id: 'sf_3', name: 'Cash Rewards',  type: 'credit',     subtype: 'credit card', institution: { name: 'Bank of America' }, balance: {}, _source: 'simplefin' },
  { id: 'mn_1', name: 'HSY',           type: 'depository', subtype: '',            institution: { name: 'Synchrony' },      balance: {}, _source: 'manual' },
];

const mockGrouped = (data = groupedAccounts) => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts')) return Promise.resolve({ data });
    return Promise.reject(new Error('Unknown URL'));
  });
};

test('groups accounts under institution headings with a count', async () => {
  mockGrouped();
  render(<AccountsModal onClose={jest.fn()} />);

  expect(await screen.findByText('Chase Bank')).toBeInTheDocument();
  expect(screen.getByText('Bank of America')).toBeInTheDocument();

  // Chase has two accounts, BofA one.
  const chase = within(screen.getByRole('group', { name: 'Chase Bank' }));
  expect(chase.getByText('2')).toBeInTheDocument();
  expect(chase.getByText('Prime Visa')).toBeInTheDocument();
  expect(chase.getByText('TOTAL CHECKING')).toBeInTheDocument();

  const bofa = within(screen.getByRole('group', { name: 'Bank of America' }));
  expect(bofa.getByText('1')).toBeInTheDocument();
  expect(bofa.queryByText('Prime Visa')).not.toBeInTheDocument();
});

test('puts manual accounts in their own group, last', async () => {
  mockGrouped();
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('Chase Bank');

  const manualGroup = within(screen.getByRole('group', { name: 'Added manually' }));
  expect(manualGroup.getByText('HSY')).toBeInTheDocument();

  const labels = screen.getAllByTestId('account-group-label').map((n) => n.textContent);
  expect(labels[labels.length - 1]).toMatch(/Added manually/);
});

test('puts connection errors in a Needs attention group, first', async () => {
  mockGrouped([
    ...groupedAccounts,
    { id: '_sferror_abc', name: 'Unknown account', type: '', subtype: '', institution: { name: 'SimpleFIN' }, balance: {}, _connection_error: true, _source: 'simplefin' },
  ]);
  render(<AccountsModal onClose={jest.fn()} />);

  expect(await screen.findByText('Needs attention')).toBeInTheDocument();
  const labels = screen.getAllByTestId('account-group-label').map((n) => n.textContent);
  expect(labels[0]).toMatch(/Needs attention/);
});

// ── Connect form disclosure ──────────────────────────────────────────────────

test('collapses the connect form when a SimpleFIN account is already linked', async () => {
  mockGrouped();
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('Chase Bank');

  expect(screen.queryByPlaceholderText('Paste Setup Token')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Connect another bank/ })).toBeInTheDocument();
});

test('expands the connect form when the disclosure is clicked', async () => {
  mockGrouped();
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('Chase Bank');

  fireEvent.click(screen.getByRole('button', { name: /Connect another bank/ }));

  expect(screen.getByPlaceholderText('Paste Setup Token')).toBeInTheDocument();
  expect(screen.getByText('Connect via SimpleFIN')).toBeInTheDocument();
});

test('shows the connect form expanded when no SimpleFIN account is linked', async () => {
  mockGrouped([groupedAccounts[3]]); // manual only
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('Added manually');

  expect(screen.getByPlaceholderText('Paste Setup Token')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Connect another bank/ })).not.toBeInTheDocument();
});

// ── Manual account actions ───────────────────────────────────────────────────

test('manual accounts offer only permanent delete, not disconnect', async () => {
  mockGrouped([groupedAccounts[3]]);
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('Added manually');

  expect(screen.getByText('Manual')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Delete permanently/ })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Disconnect/ })).not.toBeInTheDocument();
});

// ── Brokerages (SnapTrade) ───────────────────────────────────────────────────

const mockWithBrokerages = ({ connections, snaptradeAccounts = [] }) => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/snaptrade/connections')) return Promise.resolve({ data: { connections } });
    if (url.includes('/api/balances/summary'))      return Promise.resolve({ data: { accounts: snaptradeAccounts } });
    if (url.includes('/api/accounts'))              return Promise.resolve({ data: groupedAccounts });
    return Promise.reject(new Error('Unknown URL'));
  });
};

test('renders brokerage connections in their own group with account counts', async () => {
  mockWithBrokerages({
    connections: [
      { id: 'auth_1', brokerage: 'Robinhood', disabled: false },
      { id: 'auth_2', brokerage: 'Fidelity',  disabled: false },
    ],
    snaptradeAccounts: [
      { id: 'a1', institution: 'Robinhood', source: 'snaptrade' },
      { id: 'a2', institution: 'Robinhood', source: 'snaptrade' },
      { id: 'a3', institution: 'Fidelity',  source: 'snaptrade' },
      { id: 'a4', institution: 'Chase Bank', source: 'simplefin' },
    ],
  });
  render(<AccountsModal onClose={jest.fn()} />);

  const group = within(await screen.findByRole('group', { name: 'Brokerages' }));
  expect(group.getByText('Robinhood')).toBeInTheDocument();
  expect(group.getByText('2 accounts')).toBeInTheDocument();
  expect(group.getByText('Fidelity')).toBeInTheDocument();
  expect(group.getByText('1 account')).toBeInTheDocument();
});

test('a healthy brokerage is Active, a disabled one needs reconnect', async () => {
  mockWithBrokerages({
    connections: [
      { id: 'auth_1', brokerage: 'Robinhood', disabled: false },
      { id: 'auth_2', brokerage: 'Fidelity',  disabled: true },
    ],
  });
  render(<AccountsModal onClose={jest.fn()} />);

  const group = within(await screen.findByRole('group', { name: 'Brokerages' }));
  expect(group.getByText('Needs Reconnect')).toBeInTheDocument();
  expect(group.getAllByText('Active').length).toBe(1);
});

test('disconnecting a brokerage revokes the authorization', async () => {
  axios.delete.mockResolvedValue({});
  mockWithBrokerages({ connections: [{ id: 'auth_1', brokerage: 'Robinhood', disabled: false }] });
  render(<AccountsModal onClose={jest.fn()} />);

  const group = within(await screen.findByRole('group', { name: 'Brokerages' }));
  fireEvent.click(group.getByRole('button', { name: /Disconnect/ }));
  fireEvent.click(group.getByRole('button', { name: 'Yes' }));

  await waitFor(() => {
    expect(axios.delete).toHaveBeenCalledWith(
      expect.stringContaining('/api/snaptrade/connections/auth_1'),
    );
  });
});

test('omits the brokerage group when SnapTrade is unconfigured', async () => {
  mockGrouped();  // /api/snaptrade/connections rejects
  render(<AccountsModal onClose={jest.fn()} />);
  await screen.findByText('Chase Bank');

  expect(screen.queryByRole('group', { name: 'Brokerages' })).not.toBeInTheDocument();
});

// ── Close ─────────────────────────────────────────────────────────────────────

test('Close button calls onClose', async () => {
  const mockClose = jest.fn();
  render(<AccountsModal onClose={mockClose} />);
  await screen.findByText('First Bank');

  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(mockClose).toHaveBeenCalled();
});
