import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import axios from 'axios';

import FinancesPage from '../FinancesPage';
import { normalizeTabId } from '../FinancesSidebar';

jest.mock('axios');

// The heavy tabs each self-fetch and pull in charts; stubbing them keeps
// these tests about routing rather than about their internals.
jest.mock('../DashboardTab', () => () => <div>Dashboard stub</div>);
jest.mock('../PropertiesPage', () => () => <div>Properties stub</div>);
jest.mock('../LoansPage', () => () => <div>Loans stub</div>);
jest.mock('../AdvisorChat', () => () => <div>Advisor stub</div>);
jest.mock('../KnowledgeSection', () => () => <div>Knowledge stub</div>);
jest.mock('../InvestmentsTab', () => () => <div>Investments stub</div>);

const renderAt = (path) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/finances" element={<FinancesPage />} />
      <Route path="/finances/:tab" element={<FinancesPage />} />
    </Routes>
  </MemoryRouter>
);

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  axios.get.mockResolvedValue({ data: {} });
});

describe('normalizeTabId', () => {
  test('passes through a known tab', () => {
    expect(normalizeTabId('properties')).toBe('properties');
  });

  test('remaps the retired overview id to accounts', () => {
    // Without this a returning user whose localStorage still says
    // 'overview' would land on an empty shell.
    expect(normalizeTabId('overview')).toBe('accounts');
  });

  test('falls back for an unknown id', () => {
    expect(normalizeTabId('does-not-exist')).toBe('dashboard');
  });

  test('falls back for null', () => {
    expect(normalizeTabId(null)).toBe('dashboard');
  });

  test('honours an explicit fallback', () => {
    expect(normalizeTabId('nope', 'loans')).toBe('loans');
  });
});

describe('routing', () => {
  test('renders the tab named in the URL', async () => {
    renderAt('/finances/properties');
    expect(await screen.findByText('Properties stub')).toBeInTheDocument();
  });

  test('renders loans from its URL', async () => {
    renderAt('/finances/loans');
    expect(await screen.findByText('Loans stub')).toBeInTheDocument();
  });

  test('a bare /finances falls back to the dashboard', async () => {
    renderAt('/finances');
    expect(await screen.findByText('Dashboard stub')).toBeInTheDocument();
  });

  test('a bare /finances honours the stored last tab', async () => {
    localStorage.setItem('finances.activeTab', 'loans');
    renderAt('/finances');
    expect(await screen.findByText('Loans stub')).toBeInTheDocument();
  });

  test('a stored legacy id resolves instead of blanking the shell', async () => {
    localStorage.setItem('finances.activeTab', 'overview');
    renderAt('/finances');
    // Asserted via the sidebar's active marker rather than by text: both the
    // nav button and the page title read "Accounts", so a text query matches
    // twice and throws.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Accounts' }))
        .toHaveAttribute('aria-current', 'page')
    );
    expect(localStorage.getItem('finances.activeTab')).toBe('accounts');
  });

  test('an unknown tab in the URL falls back rather than rendering nothing', async () => {
    renderAt('/finances/not-a-tab');
    expect(await screen.findByText('Dashboard stub')).toBeInTheDocument();
  });

  test('the active tab is persisted for next time', async () => {
    renderAt('/finances/loans');
    await screen.findByText('Loans stub');
    await waitFor(() =>
      expect(localStorage.getItem('finances.activeTab')).toBe('loans')
    );
  });
});

describe('sidebar', () => {
  test('exposes the new Properties and Loans destinations', async () => {
    renderAt('/finances/properties');
    await screen.findByText('Properties stub');
    expect(screen.getByRole('button', { name: 'Properties' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Loans' })).toBeInTheDocument();
  });

  test('marks the active item for assistive tech', async () => {
    renderAt('/finances/properties');
    await screen.findByText('Properties stub');
    expect(screen.getByRole('button', { name: 'Properties' }))
      .toHaveAttribute('aria-current', 'page');
  });

  test('the retired Overview item is gone', async () => {
    renderAt('/finances/dashboard');
    await screen.findByText('Dashboard stub');
    expect(screen.queryByRole('button', { name: 'Overview' })).toBeNull();
  });
});
