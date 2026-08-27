import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DebtPage from '../DebtPage';
import { getCreditHealth } from '../../../api/dashboard';

jest.mock('../../../api/dashboard');

const summary = {
  accounts: [
    { id: 'c1', name: 'Chase Sapphire', institution: 'Chase', type: 'credit', ledger: 4820, due_day: 14 },
    { id: 'c2', name: 'Amex Gold', institution: 'Amex', type: 'credit', ledger: 1240, due_day: 2 },
    { id: 'd1', name: 'Ally Savings', institution: 'Ally', type: 'depository', available: 18400 },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  getCreditHealth.mockResolvedValue({
    data: { overall_utilization_pct: 42, overall_status: 'warn', total_balance: 6060, total_limit: 14400 },
  });
});

const renderPage = (props = {}) => render(
  <MemoryRouter><DebtPage summary={summary} onRefresh={jest.fn()} {...props} /></MemoryRouter>,
);

test('names itself Debt', async () => {
  renderPage();
  expect(await screen.findByRole('heading', { level: 1, name: 'Debt' })).toBeInTheDocument();
});

test('totals only what is owed, ignoring cash', async () => {
  renderPage();
  expect(await screen.findByText(/6,060/)).toBeInTheDocument();
  expect(screen.queryByText(/18,400/)).toBeNull();
});

test('reports utilization from the API rather than recomputing it', async () => {
  renderPage();
  expect(await screen.findByText(/42%/)).toBeInTheDocument();
  expect(getCreditHealth).toHaveBeenCalled();
});

test('utilization is not conveyed by colour alone', async () => {
  renderPage();
  // A colour-coded status must carry text too — see the repo's a11y commit.
  expect(await screen.findByText(/42%/)).toBeInTheDocument();
  expect(screen.getByText(/warn|watch|high/i)).toBeInTheDocument();
});

test('survives a credit-health outage without blanking the page', async () => {
  getCreditHealth.mockRejectedValue(new Error('down'));
  renderPage();
  expect(await screen.findByRole('heading', { level: 1, name: 'Debt' })).toBeInTheDocument();
  expect(screen.getByText(/6,060/)).toBeInTheDocument();
});

test('the next payment is the nearest upcoming date, not the smallest day number', async () => {
  jest.useFakeTimers().setSystemTime(new Date('2026-08-20T12:00:00Z'));
  // due_day 25 is five days out; due_day 2 already passed and wraps to next month.
  renderPage({ summary: { accounts: [
    { id: 'c1', name: 'Near Card', institution: 'A', type: 'credit', ledger: 100, due_day: 25 },
    { id: 'c2', name: 'Far Card', institution: 'B', type: 'credit', ledger: 100, due_day: 2 },
  ] } });

  expect(await screen.findByText(/Near Card/)).toBeInTheDocument();
  expect(screen.queryByText(/Far Card/)).toBeNull();
  jest.useRealTimers();
});
