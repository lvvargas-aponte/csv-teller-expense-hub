import React from 'react';
import { render, screen } from '@testing-library/react';
import NetWorthPage from '../NetWorthPage';

jest.mock('../../ui/Spin', () => () => <span data-testid="spin" />);
// Recharts needs a real layout box; the breakdown is what these tests are about.
jest.mock('recharts', () => new Proxy({}, { get: () => () => null }));

// Shaped like the real payload for a household with a mortgage: the loan syncs
// from the bank as a `credit` account, so it sits inside total_credit_debt and
// is reported as *linked* property debt. Subtracting total_property_debt on top
// of that would count the mortgage twice.
const summary = {
  net_worth: 313545.38,
  total_cash: 21430.83,
  total_investments: 88166.05,
  total_credit_debt: 428151.50,
  total_property_value: 632100.00,
  total_property_debt: 411071.12,
  total_property_debt_linked: 411071.12,
  total_property_debt_unlinked: 0,
  total_property_equity: 221028.88,
  unvalued_properties: [],
  accounts: [],
};

test('reports the summary net worth, property equity included', () => {
  render(<NetWorthPage summary={summary} loading={false} />);
  // Cash − debt alone would read about −$406,720 for this household.
  expect(screen.getAllByText('$313,545.38').length).toBeGreaterThan(0);
});

test('the breakdown rows reconcile to the reported total', () => {
  const { container } = render(<NetWorthPage summary={summary} loading={false} />);
  // assets 741,696.88 − liabilities 428,151.50 = 313,545.38, so no drift note.
  const totals = [...container.querySelectorAll('.nw-group-total')].map((n) => n.textContent);
  expect(totals).toEqual(['$741,696.88', '−$428,151.50']);
  expect(screen.queryByText(/doesn't match the reported net worth/i)).toBeNull();
});

test('does not subtract a synced mortgage twice', () => {
  render(<NetWorthPage summary={summary} loading={false} />);
  // The mortgage is disclosed as already inside the credit total rather than
  // added again as a separate liability row.
  expect(screen.getByText(/includes \$411,071\.12 of mortgage balances/i)).toBeInTheDocument();
  expect(screen.queryByText('Other property debt')).toBeNull();
});

test('explains the property equity carried in the total', () => {
  render(<NetWorthPage summary={summary} loading={false} />);
  expect(screen.getByText(/property equity: \$221,028\.88/i)).toBeInTheDocument();
});

test('subtracts hand-entered property loans that no account carries', () => {
  render(
    <NetWorthPage
      loading={false}
      summary={{
        ...summary,
        net_worth: 213545.38,
        total_property_debt: 511071.12,
        total_property_debt_unlinked: 100000,
        total_property_equity: 121028.88,
      }}
    />
  );
  expect(screen.getByText('Other property debt')).toBeInTheDocument();
  // 428,151.50 of credit + the 100,000 loan no account carries.
  expect(screen.getByText('−$528,151.50')).toHaveClass('nw-group-total');
  expect(screen.queryByText(/doesn't match the reported net worth/i)).toBeNull();
});

test('flags a total the itemised rows cannot account for', () => {
  render(<NetWorthPage summary={{ ...summary, net_worth: 999999 }} loading={false} />);
  expect(screen.getByText(/doesn't match the reported net worth/i)).toBeInTheDocument();
});

test('names properties left out for want of a valuation', () => {
  render(
    <NetWorthPage
      loading={false}
      summary={{ ...summary, unvalued_properties: ['Maple St Duplex'] }}
    />
  );
  expect(screen.getByText(/Maple St Duplex/)).toBeInTheDocument();
});
