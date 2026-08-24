import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BudgetPresetModal from '../BudgetPresetModal';
import { getRatios } from '../../../api/health';

jest.mock('axios');
jest.mock('../../../api/health');

const renderModal = (monthly, source = 'profile') => {
  getRatios.mockResolvedValue({
    data: { income: { monthly, source, detected_monthly: null, profile_monthly: monthly } },
  });
  return render(
    <BudgetPresetModal
      categories={['Dining']}
      existingBudgets={[]}
      onClose={jest.fn()}
      onApplied={jest.fn()}
    />,
  );
};

const incomeInput = () => screen.getByLabelText(/monthly take-home income/i);

beforeEach(() => jest.clearAllMocks());

test('the wizard prefills income the app already knows', async () => {
  renderModal(5000);

  await waitFor(() => expect(incomeInput()).toHaveValue('5000'));
  expect(screen.getByText(/from your financial profile/i)).toBeInTheDocument();
});

test('detected income is labelled so the user can correct it', async () => {
  renderModal(7100, 'detected');

  await waitFor(() => expect(incomeInput()).toHaveValue('7100'));
  expect(screen.getByText(/detected from your deposits/i)).toBeInTheDocument();
});

test('a figure the user typed is never overwritten by the fetch', async () => {
  const user = userEvent.setup();
  let resolveRatios;
  getRatios.mockReturnValue(new Promise((res) => { resolveRatios = res; }));

  render(
    <BudgetPresetModal
      categories={['Dining']}
      existingBudgets={[]}
      onClose={jest.fn()}
      onApplied={jest.fn()}
    />,
  );

  await user.type(incomeInput(), '1234');
  resolveRatios({ data: { income: { monthly: 5000, source: 'profile' } } });

  await waitFor(() => expect(getRatios).toHaveBeenCalled());
  expect(incomeInput()).toHaveValue('1234');
});
