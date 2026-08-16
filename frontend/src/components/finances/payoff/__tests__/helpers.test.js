import { deferredPlan, monthsBetween, parseISODate } from '../helpers';

// Fixed "today" so the month arithmetic is pinned. Month is 0-indexed.
const TODAY = new Date(2026, 7, 15); // 2026-08-15

// The CareCredit case this was built for: a deferred-interest promo at 0%
// that bills back 29% on the whole balance if anything survives 2028-06-01.
const careCredit = (over = {}) => ({
  balance: '15465',
  apr: '29',
  promoApr: '0',
  promoExpires: '2028-06-01',
  min_payment: '350',
  minPaymentUntil: '',
  ...over,
});

describe('parseISODate', () => {
  test('parses as a local date, not UTC', () => {
    const d = parseISODate('2028-06-01');
    expect(d.getFullYear()).toBe(2028);
    expect(d.getMonth()).toBe(5);
    expect(d.getDate()).toBe(1);
  });

  test('rejects blanks and malformed values', () => {
    expect(parseISODate('')).toBeNull();
    expect(parseISODate(undefined)).toBeNull();
    expect(parseISODate('06/01/2028')).toBeNull();
  });
});

describe('monthsBetween', () => {
  test('counts calendar months and ignores day-of-month', () => {
    expect(monthsBetween(new Date(2026, 7, 15), new Date(2028, 5, 1))).toBe(22);
    expect(monthsBetween(new Date(2026, 7, 1), new Date(2026, 7, 28))).toBe(0);
  });
});

describe('deferredPlan', () => {
  test('returns null without a balance or a deadline', () => {
    expect(deferredPlan(careCredit({ balance: '' }), TODAY)).toBeNull();
    expect(deferredPlan(careCredit({ promoExpires: '' }), TODAY)).toBeNull();
  });

  test('with no minimum-only window the full balance is due over the whole runway', () => {
    const p = deferredPlan(careCredit(), TODAY);
    expect(p.monthsToDeadline).toBe(22);
    expect(p.minMonths).toBe(0);
    expect(p.balanceAtWindowEnd).toBeCloseTo(15465, 2);
    // 0% promo, so it's a straight division across the runway.
    expect(p.requiredMonthly).toBeCloseTo(15465 / 22, 2);
  });

  test('a minimum-only stretch shrinks the balance and raises the catch-up payment', () => {
    const p = deferredPlan(careCredit({ minPaymentUntil: '2027-08-01' }), TODAY);
    expect(p.minMonths).toBe(12);
    expect(p.catchUpMonths).toBe(10);
    // 12 months of $350 against a 0% promo balance.
    expect(p.balanceAtWindowEnd).toBeCloseTo(15465 - 12 * 350, 2);
    expect(p.requiredMonthly).toBeCloseTo((15465 - 12 * 350) / 10, 2);
    expect(p.requiredMonthly).toBeGreaterThan(350);
  });

  test('flags the retroactive charge when minimums alone miss the deadline', () => {
    const p = deferredPlan(careCredit(), TODAY);
    expect(p.clearedByMinimums).toBe(false);
    expect(p.leftoverAtDeadline).toBeCloseTo(15465 - 22 * 350, 2);
    expect(p.retroInterest).toBeGreaterThan(0);
  });

  test('no retro warning when the minimum clears it in time on its own', () => {
    const p = deferredPlan(careCredit({ min_payment: '900' }), TODAY);
    expect(p.clearedByMinimums).toBe(true);
    expect(p.leftoverAtDeadline).toBe(0);
  });

  test('a window running to the deadline leaves a lump sum, not a monthly', () => {
    const p = deferredPlan(careCredit({ minPaymentUntil: '2028-06-01' }), TODAY);
    expect(p.catchUpMonths).toBe(0);
    expect(p.lumpSum).toBe(true);
    expect(p.requiredMonthly).toBeCloseTo(p.balanceAtWindowEnd, 2);
  });

  test('window past the deadline is clamped to it rather than running over', () => {
    const p = deferredPlan(careCredit({ minPaymentUntil: '2030-01-01' }), TODAY);
    expect(p.minMonths).toBe(p.monthsToDeadline);
    expect(p.catchUpMonths).toBe(0);
  });

  test('flags a minimum too small to cover the promo interest', () => {
    const p = deferredPlan(
      careCredit({ promoApr: '12', min_payment: '50' }), TODAY,
    );
    expect(p.minCoversInterest).toBe(false);
  });

  test('a zero minimum never counts as covering interest', () => {
    const p = deferredPlan(
      careCredit({ min_payment: '0', minPaymentUntil: '2027-08-01' }), TODAY,
    );
    expect(p.minCoversInterest).toBe(false);
  });

  test('a past deadline reports as expired with the balance still owing', () => {
    const p = deferredPlan(careCredit({ promoExpires: '2026-01-01' }), TODAY);
    expect(p.expired).toBe(true);
    expect(p.monthsToDeadline).toBe(0);
    expect(p.requiredMonthly).toBeCloseTo(15465, 2);
  });

  test('a non-zero promo rate pushes the catch-up above straight division', () => {
    const p = deferredPlan(careCredit({ promoApr: '9.99' }), TODAY);
    expect(p.requiredMonthly).toBeGreaterThan(15465 / 22);
  });
});
