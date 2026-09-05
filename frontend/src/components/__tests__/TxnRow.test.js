import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TxnRow from '../transactions/TxnRow';

const baseTxn = {
  id: 'test_1',
  date: '2024-01-15',
  description: 'STARBUCKS',
  amount: -4.50,
  source: 'discover',
  institution: 'Discover',
  is_shared: false,
  person_1_owes: 0,
  person_2_owes: 0,
  notes: '',
  what: '',
  transaction_type: 'debit',
};

function renderRow(overrides = {}, handlers = {}) {
  return render(
    <table><tbody>
      <TxnRow
        txn={{ ...baseTxn, ...overrides }}
        otherPersonName="Bob"
        isSelected={false}
        onToggle={jest.fn()}
        onSplitChange={jest.fn().mockResolvedValue()}
        onToggleType={jest.fn().mockResolvedValue()}
        onOpenAdj={jest.fn()}
        onOpenNote={jest.fn()}
        expandNote={false}
        expandAdj={false}
        {...handlers}
      />
    </tbody></table>
  );
}

test('renders description', () => {
  renderRow();
  expect(screen.getByText('STARBUCKS')).toBeInTheDocument();
});

test('renders short MM/DD/YY date', () => {
  renderRow();
  expect(screen.getByText('01/15/24')).toBeInTheDocument();
});

test('shows the SplitPill in personal state when not shared', () => {
  renderRow({ is_shared: false });
  // P button is active-personal
  const pBtn = screen.getByRole('button', { name: 'Personal' });
  expect(pBtn).toHaveAttribute('aria-pressed', 'true');
});

test('shows the SplitPill in shared state when is_shared is true', () => {
  renderRow({ is_shared: true, person_2_owes: 2.25 });
  const halfBtn = screen.getByRole('button', { name: 'Split 50/50' });
  expect(halfBtn).toHaveAttribute('aria-pressed', 'true');
});

test('shows other person owed amount when shared', () => {
  renderRow({ is_shared: true, person_2_owes: 2.25 });
  expect(screen.getByText(/Bob/)).toBeInTheDocument();
  expect(screen.getByText(/\$2\.25/)).toBeInTheDocument();
});

test('shows formatted category when category is set', () => {
  renderRow({ category: 'food_and_drink' });
  expect(screen.getByText('Food And Drink')).toBeInTheDocument();
});

test('shows note icon with title when notes are present', () => {
  renderRow({ notes: 'Split with roommate' });
  expect(screen.getByTitle('Split with roommate')).toBeInTheDocument();
});

test('calls onSplitChange with (txn, true) when ½ button clicked', async () => {
  const mockSplit = jest.fn().mockResolvedValue();
  renderRow({ is_shared: false }, { onSplitChange: mockSplit });
  fireEvent.click(screen.getByRole('button', { name: 'Split 50/50' }));
  await waitFor(() => expect(mockSplit).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'test_1' }),
    true
  ));
});

test('calls onSplitChange with (txn, false) when P button clicked', async () => {
  const mockSplit = jest.fn().mockResolvedValue();
  renderRow({ is_shared: true }, { onSplitChange: mockSplit });
  fireEvent.click(screen.getByRole('button', { name: 'Personal' }));
  await waitFor(() => expect(mockSplit).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'test_1' }),
    false
  ));
});

test('calls onOpenAdj when the adjust-split button is clicked', () => {
  const mockOpen = jest.fn();
  renderRow({}, { onOpenAdj: mockOpen });
  fireEvent.click(screen.getByTitle('Adjust split'));
  expect(mockOpen).toHaveBeenCalledWith('test_1');
});

test('calls onOpenNote when the note button is clicked', () => {
  const mockOpen = jest.fn();
  renderRow({}, { onOpenNote: mockOpen });
  fireEvent.click(screen.getByLabelText('Add note'));
  expect(mockOpen).toHaveBeenCalledWith('test_1');
});

test('calls onToggle when checkbox is clicked', () => {
  const mockToggle = jest.fn();
  renderRow({}, { onToggle: mockToggle });
  const checkbox = screen.getByRole('checkbox');
  fireEvent.click(checkbox);
  expect(mockToggle).toHaveBeenCalledWith('test_1');
});

test('checkbox is checked when isSelected is true', () => {
  renderRow({}, { isSelected: true });
  expect(screen.getByRole('checkbox')).toBeChecked();
});

test('clicking the row body opens the detail panel', () => {
  const mockOpen = jest.fn();
  renderRow({}, { onOpenDetail: mockOpen });
  fireEvent.click(screen.getByText('01/15/24'));
  expect(mockOpen).toHaveBeenCalledWith('test_1');
});

test('the description is a keyboard-reachable button that opens details', () => {
  const mockOpen = jest.fn();
  renderRow({}, { onOpenDetail: mockOpen });
  fireEvent.click(screen.getByRole('button', { name: 'Open details for STARBUCKS' }));
  expect(mockOpen).toHaveBeenCalledWith('test_1');
});

test.each([
  ['checkbox',     () => screen.getByRole('checkbox')],
  ['split pill',   () => screen.getByRole('button', { name: 'Personal' })],
  ['note button',  () => screen.getByLabelText('Add note')],
  ['adjust split', () => screen.getByTitle('Adjust split')],
  ['CR/DR badge',  () => screen.getByText('DR')],
])('clicking the %s does not open the detail panel', (_label, pick) => {
  const mockOpen = jest.fn();
  renderRow({}, { onOpenDetail: mockOpen });
  fireEvent.click(pick());
  expect(mockOpen).not.toHaveBeenCalled();
});

test('applies tx-row--detail only when the panel is open for this row', () => {
  const { rerender } = renderRow({}, { isDetailOpen: false });
  expect(screen.getByRole('row')).not.toHaveClass('tx-row--detail');
  rerender(
    <table><tbody>
      <TxnRow
        txn={baseTxn}
        otherPersonName="Bob"
        isSelected={false}
        onToggle={jest.fn()}
        onSplitChange={jest.fn().mockResolvedValue()}
        onToggleType={jest.fn().mockResolvedValue()}
        onOpenAdj={jest.fn()}
        onOpenNote={jest.fn()}
        expandNote={false}
        expandAdj={false}
        isDetailOpen
      />
    </tbody></table>
  );
  expect(screen.getByRole('row')).toHaveClass('tx-row--detail');
});

test('shows DR badge for debit and CR badge for credit', () => {
  const { rerender } = renderRow({ transaction_type: 'debit' });
  expect(screen.getByText('DR')).toBeInTheDocument();
  rerender(
    <table><tbody>
      <TxnRow
        txn={{ ...baseTxn, transaction_type: 'credit' }}
        otherPersonName="Bob"
        isSelected={false}
        onToggle={jest.fn()}
        onSplitChange={jest.fn().mockResolvedValue()}
        onToggleType={jest.fn().mockResolvedValue()}
        onOpenAdj={jest.fn()}
        onOpenNote={jest.fn()}
        expandNote={false}
        expandAdj={false}
      />
    </tbody></table>
  );
  expect(screen.getByText('CR')).toBeInTheDocument();
});

describe('category provenance badge', () => {
  test('marks a category the bank reported', () => {
    renderRow({ category: 'Dining', category_source: 'bank' });
    expect(screen.getByTitle(/Reported by the bank feed/)).toHaveTextContent('bank');
  });

  test('marks a category one of your rules set', () => {
    renderRow({ category: 'Dining', category_source: 'rule' });
    expect(screen.getByText('rule')).toBeInTheDocument();
  });

  test('marks an automatic suggestion', () => {
    renderRow({ category: 'Dining', category_source: 'ai' });
    expect(screen.getByText('auto')).toBeInTheDocument();
  });

  test('leaves a category you set unmarked', () => {
    // A label you typed needs no explanation — the badge is there to explain
    // the ones you didn't.
    renderRow({ category: 'Dining', category_source: 'manual' });
    expect(screen.queryByText(/^(rule|bank|auto)$/)).not.toBeInTheDocument();
  });

  test('renders nothing for a transaction with no provenance recorded', () => {
    renderRow({ category: 'Dining' });
    expect(screen.queryByText(/^(rule|bank|auto)$/)).not.toBeInTheDocument();
  });
});
