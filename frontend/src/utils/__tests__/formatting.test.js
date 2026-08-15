import {
  fmt$, fmtDate, toYMD, prevMonthRange, thisMonthRange, greetingFor, formatToday,
} from '../formatting';

describe('greetingFor', () => {
  const at = (hour) => new Date(2026, 7, 15, hour, 0, 0);

  test('morning covers midnight through 11:59', () => {
    expect(greetingFor(at(0))).toBe('Good morning');
    expect(greetingFor(at(11))).toBe('Good morning');
  });

  test('afternoon starts at noon and runs to 17:59', () => {
    expect(greetingFor(at(12))).toBe('Good afternoon');
    expect(greetingFor(at(17))).toBe('Good afternoon');
  });

  test('evening starts at 18:00', () => {
    expect(greetingFor(at(18))).toBe('Good evening');
    expect(greetingFor(at(23))).toBe('Good evening');
  });
});

describe('formatToday', () => {
  test('renders month name and day without the year', () => {
    // Month is 0-indexed: 7 === August.
    expect(formatToday(new Date(2026, 7, 15))).toBe('August 15');
  });

  test('does not zero-pad single-digit days', () => {
    expect(formatToday(new Date(2026, 0, 1))).toBe('January 1');
  });
});

describe('fmt$', () => {
  test('formats positive number as USD currency', () => {
    expect(fmt$(4.5)).toBe('$4.50');
  });

  test('formats negative number as absolute value (no minus sign)', () => {
    expect(fmt$(-29.99)).toBe('$29.99');
  });

  test('handles zero', () => {
    expect(fmt$(0)).toBe('$0.00');
  });

  test('handles numeric string input', () => {
    expect(fmt$('100')).toBe('$100.00');
  });

  test('handles non-numeric string gracefully (treats as 0)', () => {
    expect(fmt$('not-a-number')).toBe('$0.00');
  });

  test('handles undefined/null gracefully', () => {
    expect(fmt$(undefined)).toBe('$0.00');
    expect(fmt$(null)).toBe('$0.00');
  });
});

describe('fmtDate', () => {
  test('formats ISO date string to readable date', () => {
    const result = fmtDate('2024-01-15');
    expect(result).toMatch(/Jan/);
    expect(result).toMatch(/15/);
    expect(result).toMatch(/2024/);
  });

  test('returns original string for invalid dates', () => {
    expect(fmtDate('not-a-date')).toBe('not-a-date');
  });

  test('returns original string for empty input', () => {
    expect(fmtDate('')).toBe('');
  });
});

describe('toYMD', () => {
  test('converts Date to YYYY-MM-DD format', () => {
    // Use UTC to avoid timezone issues in the test
    const d = new Date('2024-01-15T00:00:00');
    const result = toYMD(d);
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe('prevMonthRange', () => {
  test('from date is before or equal to to date', () => {
    const { from, to } = prevMonthRange();
    expect(from <= to).toBe(true);
  });

  test('from date starts on first day of month', () => {
    const { from } = prevMonthRange();
    expect(from).toMatch(/-01$/);
  });

  test('returns strings in YYYY-MM-DD format', () => {
    const { from, to } = prevMonthRange();
    expect(from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe('thisMonthRange', () => {
  test('from date starts on first day of current month', () => {
    const { from } = thisMonthRange();
    expect(from).toMatch(/-01$/);
  });

  test('from is before or equal to to', () => {
    const { from, to } = thisMonthRange();
    expect(from <= to).toBe(true);
  });
});
