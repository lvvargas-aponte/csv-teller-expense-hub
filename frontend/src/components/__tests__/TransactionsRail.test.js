import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import TransactionsRail from '../transactions/TransactionsRail';
import { merchantKey } from '../../utils/formatting';

const txn = (id, overrides = {}) => ({
  id,
  date: '2024-01-15',
  description: `TXN ${id}`,
  amount: -10,
  category: '',
  is_shared: false,
  reviewed: false,
  person_2_owes: 0,
  transaction_type: 'debit',
  ...overrides,
});

function renderRail(props = {}) {
  const defaults = {
    txns: [txn('a'), txn('b', { reviewed: true })],
    progress: { reviewed: 1, total: 2 },
    personName: 'Bob',
    onOpenDetail: jest.fn(),
    onApplyToSimilar: jest.fn().mockResolvedValue(),
  };
  return render(<TransactionsRail {...defaults} {...props} />);
}

describe('merchantKey', () => {
  test('takes the first two alphabetic words, uppercased', () => {
    expect(merchantKey('Starbucks Store #123')).toBe('STARBUCKS STORE');
    expect(merchantKey('uber *trip 8f2')).toBe('UBER TRIP');
  });
  test('handles single-word and empty descriptions', () => {
    expect(merchantKey('NETFLIX')).toBe('NETFLIX');
    expect(merchantKey('')).toBe('');
  });
});

describe('review progress card', () => {
  test('shows counts, remaining hint, and the review-next button', () => {
    const onOpenDetail = jest.fn();
    renderRail({ onOpenDetail });
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('of 2 reviewed')).toBeInTheDocument();
    expect(screen.getByText('1 left in this view.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Review next unreviewed' }));
    expect(onOpenDetail).toHaveBeenCalledWith('a');
  });

  test('hides the button and swaps the hint when everything is reviewed', () => {
    renderRail({
      txns: [txn('a', { reviewed: true })],
      progress: { reviewed: 1, total: 1 },
    });
    expect(screen.getByText('Everything here is reviewed.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Review next unreviewed' })).not.toBeInTheDocument();
  });
});

describe('apply-to-similar card', () => {
  const open = txn('open', { description: 'STARBUCKS STORE 1', category: 'Food' });
  const match1 = txn('m1', { description: 'STARBUCKS STORE 2' });
  const match2 = txn('m2', { description: 'Starbucks Store 3', reviewed: true });

  test('absent when no row is open', () => {
    renderRail({ txns: [open, match1] });
    expect(screen.queryByText('Apply to similar')).not.toBeInTheDocument();
  });

  test('absent when the open row has no merchant matches', () => {
    renderRail({ txns: [open, txn('x', { description: 'NETFLIX' })], openTxn: open });
    expect(screen.queryByText('Apply to similar')).not.toBeInTheDocument();
  });

  test('singular copy for one match', () => {
    renderRail({ txns: [open, match1], openTxn: open });
    expect(screen.getByText(/1 other transaction matches/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply to 1' })).toBeInTheDocument();
  });

  test('plural copy and apply passes matches with the pending draft', async () => {
    const onApplyToSimilar = jest.fn().mockResolvedValue();
    renderRail({
      txns: [open, match1, match2],
      openTxn: open,
      draft: { category: 'Coffee', is_shared: true },
      onApplyToSimilar,
    });
    expect(screen.getByText(/2 other transactions match/)).toBeInTheDocument();
    expect(screen.getByText('Coffee')).toBeInTheDocument();
    expect(screen.getByText('shared')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Apply to 2' }));
    await waitFor(() => expect(onApplyToSimilar).toHaveBeenCalledWith(
      [expect.objectContaining({ id: 'm1' }), expect.objectContaining({ id: 'm2' })],
      { category: 'Coffee', is_shared: true }
    ));
  });

  test('falls back to the record values when there is no draft', () => {
    renderRail({ txns: [open, match1], openTxn: open });
    // "Food" also appears in the Where-it-went card — scope to the similar card.
    const card = screen.getByText('Apply to similar').closest('.tx-rail-card');
    expect(within(card).getByText('Food')).toBeInTheDocument();
    expect(within(card).getByText('personal')).toBeInTheDocument();
  });
});

describe('shared card', () => {
  test('sums person_2_owes with a half-amount fallback', () => {
    renderRail({
      txns: [
        txn('s1', { is_shared: true, person_2_owes: 3 }),
        txn('s2', { is_shared: true, person_2_owes: 0, amount: -10 }), // falls back to 5.00
        txn('p1', { is_shared: false, person_2_owes: 99 }),
      ],
    });
    expect(screen.getByText('Shared with Bob')).toBeInTheDocument();
    expect(screen.getByText('$8.00')).toBeInTheDocument();
    expect(screen.getByText(/Across 2 shared transactions/)).toBeInTheDocument();
  });

  test('Send to Sheet renders only when a handler is provided', () => {
    renderRail({});
    expect(screen.queryByRole('button', { name: /Send to Sheet/ })).not.toBeInTheDocument();
  });

  test('Send to Sheet shows the shared count and disables while sending', () => {
    const onSendToSheet = jest.fn();
    const shared = [txn('s1', { is_shared: true }), txn('s2', { is_shared: true })];
    const { rerender } = render(
      <TransactionsRail
        txns={shared}
        progress={{ reviewed: 0, total: 2 }}
        personName="Bob"
        onOpenDetail={jest.fn()}
        onApplyToSimilar={jest.fn()}
        onSendToSheet={onSendToSheet}
      />
    );
    const btn = screen.getByRole('button', { name: /Send to Sheet \(2\)/ });
    fireEvent.click(btn);
    expect(onSendToSheet).toHaveBeenCalled();
    rerender(
      <TransactionsRail
        txns={shared}
        progress={{ reviewed: 0, total: 2 }}
        personName="Bob"
        onOpenDetail={jest.fn()}
        onApplyToSimilar={jest.fn()}
        onSendToSheet={onSendToSheet}
        sendingSheet
      />
    );
    expect(screen.getByRole('button', { name: /Send to Sheet \(2\)/ })).toBeDisabled();
  });
});

describe('where-it-went card', () => {
  test('shows the top four debit categories by total, descending', () => {
    renderRail({
      txns: [
        txn('1', { category: 'Food', amount: -50 }),
        txn('2', { category: 'Food', amount: -30 }),
        txn('3', { category: 'Travel', amount: -60 }),
        txn('4', { category: 'Fun', amount: -20 }),
        txn('5', { category: 'Bills', amount: -15 }),
        txn('6', { category: 'Misc', amount: -1 }),
        txn('7', { category: 'Salary', amount: 500, transaction_type: 'credit' }),
      ],
    });
    expect(screen.getByText('Where it went')).toBeInTheDocument();
    expect(screen.getByText('Food')).toBeInTheDocument();
    expect(screen.getByText('$80.00')).toBeInTheDocument();
    expect(screen.getByText('Travel')).toBeInTheDocument();
    // Only top 4: Misc (smallest) and the credit are excluded.
    expect(screen.queryByText('Misc')).not.toBeInTheDocument();
    expect(screen.queryByText('Salary')).not.toBeInTheDocument();
  });

  test('uses Uncategorized for blank categories and shows an empty state without debits', () => {
    renderRail({ txns: [txn('1', { category: '', amount: -5 })] });
    expect(screen.getByText('Uncategorized')).toBeInTheDocument();
    renderRail({ txns: [] });
    expect(screen.getByText('No spending in this view.')).toBeInTheDocument();
  });
});
