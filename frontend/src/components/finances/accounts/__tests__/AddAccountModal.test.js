import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AddAccountModal from '../AddAccountModal';
import { addManualAccount } from '../../../../api/balances';
import { classifyAccountBucket } from '../../../../utils/accountBucket';
import { summarize } from '../accountMath';

jest.mock('../../../../api/balances');
jest.mock('../../../../api/accountDetails');

beforeEach(() => {
  jest.clearAllMocks();
  addManualAccount.mockResolvedValue({ data: {} });
});

test('offers an investment or retirement account', async () => {
  const user = userEvent.setup();
  render(<AddAccountModal kind="investment" onClose={jest.fn()} onSaved={jest.fn()} />);

  expect(
    screen.getAllByText(/investment|retirement/i)[0]
  ).toBeInTheDocument();

  await user.type(screen.getByLabelText(/institution/i), 'Fidelity');
  await user.type(screen.getByLabelText(/account name/i), '401(k)');
  await user.type(screen.getByLabelText(/balance/i), '36870');
  await user.click(screen.getByRole('button', { name: /add|save/i }));

  expect(addManualAccount).toHaveBeenCalled();
});

test('what it creates actually classifies as an investment', async () => {
  // A preset whose type/subtype lands in the cash bucket would put the
  // account on /accounts instead of /invest, and a test that only checks
  // the modal renders would never notice.
  const user = userEvent.setup();
  render(<AddAccountModal kind="investment" onClose={jest.fn()} onSaved={jest.fn()} />);

  await user.type(screen.getByLabelText(/institution/i), 'Fidelity');
  await user.type(screen.getByLabelText(/account name/i), '401(k)');
  await user.type(screen.getByLabelText(/balance/i), '36870');
  await user.click(screen.getByRole('button', { name: /add|save/i }));

  const [payload] = addManualAccount.mock.calls[0];
  expect(classifyAccountBucket(payload)).toBe('investment');
});

test('stores the one figure the user entered in both balance fields', async () => {
  // accountMath.js and the backend read different fields for "the" value of
  // an account (ledger-first vs. available-first). A preset that only fills
  // one of them would show two different numbers for the same account
  // depending on which screen you're looking at.
  const user = userEvent.setup();
  render(<AddAccountModal kind="investment" onClose={jest.fn()} onSaved={jest.fn()} />);

  await user.type(screen.getByLabelText(/institution/i), 'Fidelity');
  await user.type(screen.getByLabelText(/account name/i), '401(k)');
  await user.type(screen.getByLabelText(/balance/i), '36870');
  await user.click(screen.getByRole('button', { name: /add|save/i }));

  const [payload] = addManualAccount.mock.calls[0];
  expect(payload.available).toBe(36870);
  expect(payload.ledger).toBe(36870);
});

test('the Investments total on /accounts agrees with the value entered', async () => {
  // This is the test that actually pins the bug: accountMath.js#summarize
  // prefers `ledger` for the Investments badge on /accounts. If the preset
  // ever split the entered value across two different fields again, this
  // total would silently diverge from what the user typed.
  const user = userEvent.setup();
  render(<AddAccountModal kind="investment" onClose={jest.fn()} onSaved={jest.fn()} />);

  await user.type(screen.getByLabelText(/institution/i), 'Fidelity');
  await user.type(screen.getByLabelText(/account name/i), '401(k)');
  await user.type(screen.getByLabelText(/balance/i), '36870');
  await user.click(screen.getByRole('button', { name: /add|save/i }));

  const [payload] = addManualAccount.mock.calls[0];
  const { totalInvestments } = summarize([], [], [payload], []);
  expect(totalInvestments).toBe(36870);
});
