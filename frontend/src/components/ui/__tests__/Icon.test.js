import React from 'react';
import { render } from '@testing-library/react';
import Icon, { ICON_NAMES } from '../Icon';

test('renders an svg hidden from assistive technology', () => {
  const { container } = render(<Icon name="home" />);
  const svg = container.querySelector('svg');
  expect(svg).toBeInTheDocument();
  expect(svg).toHaveAttribute('aria-hidden', 'true');
});

test('inherits colour so active and hover states work', () => {
  const { container } = render(<Icon name="home" />);
  expect(container.querySelector('svg')).toHaveAttribute('stroke', 'currentColor');
});

test('honours the size prop', () => {
  const { container } = render(<Icon name="home" size={24} />);
  const svg = container.querySelector('svg');
  expect(svg).toHaveAttribute('width', '24');
  expect(svg).toHaveAttribute('height', '24');
});

test('renders nothing for an unknown name', () => {
  const { container } = render(<Icon name="not-a-real-icon" />);
  expect(container.querySelector('svg')).toBeNull();
});

test('every navigation icon the app needs exists', () => {
  for (const name of [
    'home', 'transactions', 'accounts', 'debt',
    'invest', 'plan', 'ask', 'settings',
  ]) {
    expect(ICON_NAMES).toContain(name);
  }
});

test('every declared icon actually renders', () => {
  for (const name of ICON_NAMES) {
    const { container } = render(<Icon name={name} />);
    expect(container.querySelector('svg')).toBeInTheDocument();
  }
});
