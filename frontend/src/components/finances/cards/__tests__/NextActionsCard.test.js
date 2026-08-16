import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import axios from 'axios';

import NextActionsCard from '../NextActionsCard';

jest.mock('axios');
jest.mock('../../../ui/Spin', () => () => <span data-testid="spin" />);

const action = (overrides = {}) => ({
  id: 'daily_allowance:over:2026-08',
  kind: 'spend_less',
  urgency: 'now',
  rank: 1,
  title: 'Hold off on spending today',
  detail: "You're $340 past this month's plan.",
  amount: 0,
  impact: { label: 'overspend to recover', value: 340, horizon: 'this month' },
  due_date: null,
  cta: { label: 'See today', tab: 'today' },
  why: ['$3,540 spent against a $3,200 pool'],
  source: 'rule:daily_allowance',
  dismissible: true,
  ...overrides,
});

const resolveWith = (actions, total) => {
  axios.get.mockResolvedValue({
    data: { actions, total: total ?? actions.length, counts: {} },
  });
};

beforeEach(() => jest.clearAllMocks());

test('renders an action with its title and detail', async () => {
  resolveWith([action()]);
  render(<NextActionsCard onNavigate={jest.fn()} />);
  expect(await screen.findByText('Hold off on spending today')).toBeInTheDocument();
  expect(screen.getByText(/\$340 past this month/)).toBeInTheDocument();
});

test('shows the urgency badge', async () => {
  resolveWith([action()]);
  render(<NextActionsCard onNavigate={jest.fn()} />);
  expect(await screen.findByText('Now')).toBeInTheDocument();
});

test('renders the quantified impact', async () => {
  resolveWith([action()]);
  render(<NextActionsCard onNavigate={jest.fn()} />);
  expect(await screen.findByText(/\$340\.00 overspend to recover/)).toBeInTheDocument();
});

test('renders the supporting reasons', async () => {
  resolveWith([action()]);
  render(<NextActionsCard onNavigate={jest.fn()} />);
  expect(await screen.findByText(/\$3,540 spent against/)).toBeInTheDocument();
});

test('the CTA navigates to the named tab', async () => {
  const onNavigate = jest.fn();
  resolveWith([action()]);
  render(<NextActionsCard onNavigate={onNavigate} />);

  fireEvent.click(await screen.findByRole('button', { name: /See today/ }));
  expect(onNavigate).toHaveBeenCalledWith('today');
});

test('says so plainly when there is nothing to do', async () => {
  resolveWith([]);
  render(<NextActionsCard onNavigate={jest.fn()} />);
  expect(await screen.findByText('Nothing needs you right now')).toBeInTheDocument();
});

test('notes when the list is truncated', async () => {
  resolveWith([action()], 9);
  render(<NextActionsCard onNavigate={jest.fn()} />);
  expect(await screen.findByText(/Top 1 of 9/)).toBeInTheDocument();
});

test('dismissing removes the action immediately', async () => {
  resolveWith([action()]);
  axios.post.mockResolvedValue({});
  render(<NextActionsCard onNavigate={jest.fn()} />);

  fireEvent.click(await screen.findByRole('button', { name: /Dismiss:/ }));
  await waitFor(() =>
    expect(screen.queryByText('Hold off on spending today')).toBeNull()
  );
  expect(axios.post).toHaveBeenCalled();
});

test('surfaces a load failure rather than rendering an empty list', async () => {
  axios.get.mockRejectedValue(new Error('Network Error'));
  render(<NextActionsCard onNavigate={jest.fn()} />);
  expect(await screen.findByText(/Could not load your next actions/)).toBeInTheDocument();
});

test('an action with no CTA still renders', async () => {
  resolveWith([action({ cta: null, impact: null, why: [] })]);
  render(<NextActionsCard onNavigate={jest.fn()} />);
  expect(await screen.findByText('Hold off on spending today')).toBeInTheDocument();
});
