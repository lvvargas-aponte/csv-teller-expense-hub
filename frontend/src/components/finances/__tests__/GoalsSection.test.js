import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axios from 'axios';
import GoalsSection from '../GoalsSection';

jest.mock('axios');

const account = (over = {}) => ({
  id: 'x', institution: 'Bank', name: 'Account', type: 'depository',
  subtype: '', available: 100, ledger: 100, source: 'manual', manual: true,
  ...over,
});

const mockApis = (accounts) => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/goals')) return Promise.resolve({ data: [] });
    if (url.includes('/api/balances/summary')) {
      return Promise.resolve({ data: { accounts } });
    }
    if (url.includes('/api/accounts/metadata')) {
      return Promise.resolve({ data: { investment_subtypes: null } });
    }
    return Promise.reject(new Error(`Unexpected GET ${url}`));
  });
};

beforeEach(() => jest.clearAllMocks());

// A goal is funded from wherever the money actually sits. Filtering the picker
// on `type === 'depository'` excluded every brokerage, so a "house deposit"
// held in a taxable brokerage could not be linked to its goal at all.
test('the funding picker offers investment accounts as well as cash', async () => {
  mockApis([
    account({ id: 'c1', name: 'Ally Savings' }),
    account({ id: 'i1', name: 'Vanguard Brokerage', type: 'investment', subtype: 'brokerage' }),
    account({ id: 'd1', name: 'Chase Sapphire', type: 'credit' }),
    account({ id: 'a1', name: 'Maple Street', type: 'asset', subtype: 'home' }),
  ]);

  const user = userEvent.setup();
  render(<GoalsSection />);
  await user.click(await screen.findByRole('button', { name: /Add Goal/ }));

  await waitFor(() => expect(screen.getByRole('option', { name: /Ally Savings/ })).toBeInTheDocument());
  expect(screen.getByRole('option', { name: /Vanguard Brokerage/ })).toBeInTheDocument();
  // A card and a house are not funding sources.
  expect(screen.queryByRole('option', { name: /Chase Sapphire/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('option', { name: /Maple Street/ })).not.toBeInTheDocument();
});
