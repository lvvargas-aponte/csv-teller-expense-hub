import React from 'react';
import { render, screen } from '@testing-library/react';
import StatCard from '../ui/StatCard';

// styles.js injects a <style> tag on import — mock it to avoid DOM side effects in tests
jest.mock('../ui/styles', () => ({
  statCard:  {},
  statVal:   {},
  statLabel: {},
}));

test('renders label and value', () => {
  render(<StatCard label="Total" value={42} />);
  expect(screen.getByText('Total')).toBeInTheDocument();
  expect(screen.getByText('42')).toBeInTheDocument();
});

test('renders string value', () => {
  render(<StatCard label="Shared $" value="$123.45" />);
  expect(screen.getByText('$123.45')).toBeInTheDocument();
});

test('renders without accent prop', () => {
  render(<StatCard label="Unreviewed" value={5} />);
  expect(screen.getByText('Unreviewed')).toBeInTheDocument();
});

test('renders with accent color prop', () => {
  render(<StatCard label="Shared" value={3} accent="#10b981" />);
  expect(screen.getByText('3')).toBeInTheDocument();
});
