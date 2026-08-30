import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FixBlockedRow from '../FixBlockedRow';

const NAMES = { person_1: 'Valeria', person_2: 'Christy' };

function row(overrides = {}) {
  return {
    transaction_id: 't1',
    owner: 'me',
    description: 'SHELL OIL',
    amount: -20.37,
    who: 'Valeria',
    payer_slot: 1,
    notes: '',
    reviewed: false,
    publishable: false,
    blocked_kind: 'split',
    blocked_reason: 'No split set — nothing to publish.',
    editable: {
      is_shared: true,
      what: '',
      person_1_owes: 0,
      person_2_owes: 0,
      raw_date: '06/11/2026',
      raw_amount: -20.37,
    },
    ...overrides,
  };
}

const mountFix = (overrides = {}, onSave = jest.fn().mockResolvedValue()) => {
  render(
    <FixBlockedRow
      row={row(overrides)}
      peerName="Christy"
      personNames={NAMES}
      mySlot={1}
      onSave={onSave}
      onCancel={jest.fn()}
    />,
  );
  return onSave;
};

describe('a missing split', () => {
  test('opens pre-filled at 50/50 of the row amount', () => {
    mountFix();

    expect(screen.getByText('Total $20.37')).toBeInTheDocument();
    expect(screen.getByLabelText('You pay')).toHaveValue('$10.19');
    expect(screen.getByLabelText('Christy pays')).toHaveValue('$10.18');
  });

  test('saving writes both owes columns by person slot, not by "mine"', async () => {
    const onSave = mountFix();

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    // Valeria is person 1 and paid, so her side is person_1_owes.
    expect(onSave).toHaveBeenCalledWith({
      is_shared: true,
      person_1_owes: 10.19,
      person_2_owes: 10.18,
    });
  });

  test('the slots invert when the peer paid', async () => {
    const onSave = mountFix({ who: 'Christy', payer_slot: 2 });

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    const call = onSave.mock.calls[0][0];
    expect(call.person_1_owes).toBeCloseTo(10.18, 2);
    expect(call.person_2_owes).toBeCloseTo(10.19, 2);
  });

  test('typing a percentage drives both dollar fields', async () => {
    mountFix();

    const pct = screen.getByLabelText(/your %/i);
    await userEvent.clear(pct);
    await userEvent.type(pct, '75');

    expect(screen.getByLabelText('You pay')).toHaveValue('$15.28');
    expect(screen.getByLabelText('Christy pays')).toHaveValue('$5.09');
  });

  test('the two sides always sum to the amount, so one edit moves the other', async () => {
    mountFix();

    const you = screen.getByLabelText('You pay');
    await userEvent.clear(you);
    await userEvent.type(you, '20.37');

    expect(screen.getByLabelText('Christy pays')).toHaveValue('$0.00');
  });

  test('a row that splits to nothing is refused', async () => {
    // Only reachable on a zero-amount row — the editor balances the two sides
    // against the total, so they cannot both be zeroed by hand.
    const onSave = mountFix({
      amount: 0,
      editable: { ...row().editable, raw_amount: 0 },
    });

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/has to owe something/i);
    expect(onSave).not.toHaveBeenCalled();
  });
});

describe('an unrecognised payer', () => {
  test('offers only the two configured names', () => {
    mountFix({ blocked_kind: 'who', who: 'Mom' });

    const picker = screen.getByLabelText(/paid by/i);
    const options = [...picker.options].map((o) => o.text);
    expect(options).toEqual(['Choose…', 'Valeria', 'Christy']);
  });

  test('saving sends the chosen name', async () => {
    const onSave = mountFix({ blocked_kind: 'who', who: 'Mom' });

    await userEvent.selectOptions(screen.getByLabelText(/paid by/i), 'Christy');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith({ who: 'Christy' });
  });

  test('saving without choosing is refused', async () => {
    const onSave = mountFix({ blocked_kind: 'who', who: 'Mom' });

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/pick who paid/i);
    expect(onSave).not.toHaveBeenCalled();
  });
});

describe('an unreadable date', () => {
  test('saving sends the new date', async () => {
    const onSave = mountFix({
      blocked_kind: 'date',
      editable: { ...row().editable, raw_date: 'not-a-date' },
    });

    await userEvent.type(screen.getByLabelText(/^date$/i), '2026-06-11');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith({ date: '2026-06-11' });
  });

  test('saving with no date is refused', async () => {
    const onSave = mountFix({
      blocked_kind: 'date',
      editable: { ...row().editable, raw_date: '' },
    });

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/pick a date/i);
    expect(onSave).not.toHaveBeenCalled();
  });
});

describe('an unreadable amount', () => {
  test('saving sends the amount as a number', async () => {
    const onSave = mountFix({
      blocked_kind: 'amount',
      editable: { ...row().editable, raw_amount: null },
    });

    await userEvent.type(screen.getByLabelText(/^amount$/i), '-24.50');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith({ amount: -24.5 });
  });

  test('a non-numeric amount is refused', async () => {
    const onSave = mountFix({
      blocked_kind: 'amount',
      editable: { ...row().editable, raw_amount: null },
    });

    await userEvent.type(screen.getByLabelText(/^amount$/i), 'lots');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/as a number/i);
    expect(onSave).not.toHaveBeenCalled();
  });
});

test('escape cancels without saving', async () => {
  const onCancel = jest.fn();
  const onSave = jest.fn();
  render(
    <FixBlockedRow
      row={row()}
      peerName="Christy"
      personNames={NAMES}
      mySlot={1}
      onSave={onSave}
      onCancel={onCancel}
    />,
  );

  await userEvent.type(screen.getByLabelText('You pay'), '{Escape}');

  expect(onCancel).toHaveBeenCalled();
  expect(onSave).not.toHaveBeenCalled();
});
