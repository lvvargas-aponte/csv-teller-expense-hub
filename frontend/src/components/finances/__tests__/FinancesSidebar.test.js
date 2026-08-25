import React from 'react';
import { render, screen } from '@testing-library/react';
import FinancesSidebar, { resolveStoredTab } from '../FinancesSidebar';

jest.mock('axios');

const renderSidebar = () => render(
  <FinancesSidebar activeId="dashboard" onNavigate={jest.fn()} healthScore={70} />,
);

test('bills and subscriptions are one Commitments entry', () => {
  renderSidebar();

  expect(screen.getByRole('button', { name: 'Commitments' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Bills' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Subscriptions' })).toBeNull();
});

describe('the stored tab id survives the merge', () => {
  test('a returning user holding bills lands on Commitments', () => {
    expect(resolveStoredTab('bills')).toEqual({ tab: 'commitments', view: 'due' });
  });

  test('a returning user holding subscriptions lands on its Recurring view', () => {
    expect(resolveStoredTab('subscriptions')).toEqual({
      tab: 'commitments', view: 'recurring',
    });
  });

  test('any other stored id is left alone', () => {
    expect(resolveStoredTab('accounts')).toEqual({ tab: 'accounts', view: 'due' });
  });

  test('an empty store opens the dashboard', () => {
    expect(resolveStoredTab(null)).toEqual({ tab: 'dashboard', view: 'due' });
  });
});

test('Overview is retired — the dashboard is the landing view', () => {
  renderSidebar();

  expect(screen.queryByRole('button', { name: 'Overview' })).toBeNull();
  // No view: 'due' — that is a Commitments view and means nothing here.
  expect(resolveStoredTab('overview')).toEqual({ tab: 'dashboard' });
});

// A list of buttons that swaps the main region has to say which one is
// current; aria-label with no state is neither a tab pattern nor a nav.
test('the active nav entry says it is the current page', () => {
  renderSidebar();

  expect(screen.getByRole('button', { name: 'Dashboard' }))
    .toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('button', { name: 'Accounts' }))
    .not.toHaveAttribute('aria-current');
});

// "money bag ExpensesHub" and "bar chart Dashboard" are noise; the glyphs
// decorate a label that already reads correctly.
const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

test('nav glyphs are hidden from assistive technology', () => {
  renderSidebar();

  screen.getAllByRole('button').forEach((btn) => {
    expect(btn).toHaveAccessibleName();
    expect(btn.getAttribute('aria-label') ?? btn.textContent).not.toMatch(EMOJI);
  });
  expect(screen.queryByText('💰', { ignore: '[aria-hidden="true"]' })).toBeNull();
});

test('the nav sections are distinguishable landmarks', () => {
  renderSidebar();

  expect(screen.getByRole('navigation', { name: 'Overview' })).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'Plan' })).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'Tools' })).toBeInTheDocument();
});

test('nav items render svg icons, not emoji glyphs', () => {
  const { container } = renderSidebar();

  expect(container.querySelectorAll('svg').length).toBeGreaterThanOrEqual(8);
  expect(container.textContent).not.toMatch(EMOJI);
});
