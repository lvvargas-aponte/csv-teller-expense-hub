import React from 'react';
import { render, screen } from '@testing-library/react';
import KpiCard from '../KpiCard';

test('renders label and value', () => {
  render(<KpiCard label="Net Worth" value="$1,234.00" barColor="#059669" />);
  expect(screen.getByText('Net Worth')).toBeInTheDocument();
  expect(screen.getByText('$1,234.00')).toBeInTheDocument();
});

test('omits the delta row when delta is null', () => {
  const { container } = render(<KpiCard label="Income" value="$0.00" delta={null} />);
  expect(container.querySelector('.eh-kpi-delta')).toBeNull();
});

test('omits the delta row when delta is undefined', () => {
  const { container } = render(<KpiCard label="Income" value="$0.00" />);
  expect(container.querySelector('.eh-kpi-delta')).toBeNull();
});

test('renders a delta of exactly zero rather than treating it as absent', () => {
  const { container } = render(<KpiCard label="Income" value="$0.00" delta={0} />);
  expect(container.querySelector('.eh-kpi-delta')).not.toBeNull();
  expect(screen.getByText('↑')).toBeInTheDocument();
});

test('a rise is green by default', () => {
  const { container } = render(<KpiCard label="Net Worth" value="$1.00" delta={250} />);
  expect(screen.getByText('↑')).toBeInTheDocument();
  expect(container.querySelector('.eh-kpi-delta')).toHaveStyle({ color: '#059669' });
});

test('a fall is red by default', () => {
  const { container } = render(<KpiCard label="Net Worth" value="$1.00" delta={-250} />);
  expect(screen.getByText('↓')).toBeInTheDocument();
  expect(container.querySelector('.eh-kpi-delta')).toHaveStyle({ color: '#ef4444' });
});

test('deltaInverse flips the colors so falling spend reads as good', () => {
  const { container: rising } = render(
    <KpiCard label="This Month" value="$1.00" delta={250} deltaInverse />
  );
  expect(rising.querySelector('.eh-kpi-delta')).toHaveStyle({ color: '#ef4444' });

  const { container: falling } = render(
    <KpiCard label="This Month" value="$1.00" delta={-250} deltaInverse />
  );
  expect(falling.querySelector('.eh-kpi-delta')).toHaveStyle({ color: '#059669' });
});

test('the delta amount is rendered unsigned — direction is carried by the arrow', () => {
  render(<KpiCard label="Net Worth" value="$1.00" delta={-250} />);
  expect(screen.getByText('$250.00')).toBeInTheDocument();
});

test('renders the info tooltip only when help text is supplied', () => {
  const { container: without } = render(<KpiCard label="Income" value="$0.00" />);
  expect(without.querySelector('.eh-kpi-info')).toBeNull();

  render(<KpiCard label="Income" value="$0.00" help="Credits received last month." />);
  expect(screen.getByLabelText('About Income')).toBeInTheDocument();
  expect(screen.getByText('Credits received last month.')).toBeInTheDocument();
});

test('blur applies to both the value and the delta amount', () => {
  const { container } = render(
    <KpiCard label="Net Worth" value="$1.00" delta={250} blur />
  );
  expect(container.querySelector('.eh-kpi-value')).toHaveClass('eh-blur');
  expect(screen.getByText('$250.00')).toHaveClass('eh-blur');
});
