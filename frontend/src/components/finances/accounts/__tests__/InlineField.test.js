import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InlineField from '../InlineField';

// The date mode exists so the credit drawer's "Opened on" / "Closed on" get a
// real calendar picker instead of a text box with a YYYY-MM-DD placeholder.
// It deliberately skips the draft/blur machinery the other modes use: a date
// input reports a value only once it holds a complete date.
describe('date mode', () => {
  const renderDate = (props = {}) => {
    const onChange = jest.fn();
    render(<InlineField type="date" ariaLabel="Opened on" onChange={onChange} {...props} />);
    return { onChange, input: screen.getByLabelText('Opened on') };
  };

  test('renders a real date input the browser can offer a picker for', () => {
    const { input } = renderDate({ value: '2016-04-02' });

    expect(input).toHaveAttribute('type', 'date');
    expect(input).toHaveValue('2016-04-02');
  });

  test('commits as soon as a date is chosen, without waiting for blur', () => {
    const { onChange, input } = renderDate({ value: '' });

    fireEvent.change(input, { target: { value: '2026-09-01' } });

    expect(onChange).toHaveBeenCalledWith('2026-09-01');
  });

  test('clearing the field reports null, not an empty string', () => {
    const { onChange, input } = renderDate({ value: '2016-04-02' });

    fireEvent.change(input, { target: { value: '' } });

    expect(onChange).toHaveBeenCalledWith(null);
  });

  test('a date can still be typed rather than picked', async () => {
    const user = userEvent.setup();
    const { onChange, input } = renderDate({ value: '' });

    await user.type(input, '2026-09-01');

    expect(onChange).toHaveBeenLastCalledWith('2026-09-01');
  });

  test('an empty date is styled as empty', () => {
    const { input } = renderDate({ value: null });

    expect(input).toHaveClass('ifield-empty');
    expect(input).toHaveValue('');
  });
});

// The other modes keep committing on blur — a half-typed number must not be
// written on every keystroke.
describe('the other modes are unchanged', () => {
  test('a number commits on blur, not on each keystroke', async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();
    render(<InlineField type="number" ariaLabel="Credit limit" value={null} onChange={onChange} />);

    const input = screen.getByLabelText('Credit limit');
    await user.type(input, '3500');
    expect(onChange).not.toHaveBeenCalled();

    await user.tab();
    expect(onChange).toHaveBeenCalledWith(3500);
  });
});
