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

// ── Close ─────────────────────────────────────────────────────────────────────

test('Close button calls onClose', async () => {
  const mockClose = jest.fn();
  render(<AccountsModal onClose={mockClose} />);
  await screen.findByText('First Bank');

  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(mockClose).toHaveBeenCalled();
});
