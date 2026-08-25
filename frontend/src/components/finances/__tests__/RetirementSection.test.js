import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axios from 'axios';
import RetirementSection from '../RetirementSection';

jest.mock('axios');

const projection = (over = {}) => ({
  available: true,
  missing: [],
  years_to_retirement: 24,
  current_balance: 210000,
  monthly_contribution: 1450,
  contribution_confidence: 'low',
  contribution_caveat:
    "Estimated from the account's balance history, so it includes market movement as well as contributions.",
  contribution_by_account: [
    {
      account_id: 'k401',
      name: 'Fidelity 401(k)',
      monthly: 1450,
      method: 'snapshot_velocity',
      confidence: 'low',
    },
  ],
  target_pot: 1500000,
  target_annual_spend: 60000,
  scenarios: { low: 1180000, base: 1520000, high: 1910000 },
  base_shortfall: null,
  low_shortfall: 320000,
  required_monthly_for_target: 1380,
  assumptions: {
    nominal_return_pct: 6,
    inflation_pct: 2.5,
    real_return_pct: 3.5,
    withdrawal_rate_pct: 4,
    scenario_spread_pct: 2,
    source: 'risk_tolerance',
    target_spend_source: 'profile',
  },
  ...over,
});

const mockGet = (data) => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/retirement/projection')) return Promise.resolve({ data });
    return Promise.reject(new Error(`Unexpected GET ${url}`));
  });
};

describe('RetirementSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    axios.put.mockResolvedValue({ data: {} });
  });

  it('leads with the gap against the target, not the pot alone', async () => {
    mockGet(projection());
    render(<RetirementSection />);

    expect(await screen.findByText(/on track/i)).toBeInTheDocument();
    expect(screen.getByText(/\$1\.5M target/i)).toBeInTheDocument();
  });

  it('states a shortfall and what closes it', async () => {
    mockGet(projection({
      scenarios: { low: 900000, base: 1180000, high: 1500000 },
      base_shortfall: 320000,
      required_monthly_for_target: 1630,
    }));
    render(<RetirementSection />);

    expect(await screen.findByText(/\$320,000 short/i)).toBeInTheDocument();
    expect(screen.getByText(/\$1,630\/month/i)).toBeInTheDocument();
  });

  it('renders the three scenarios as a range, never one number', async () => {
    mockGet(projection());
    render(<RetirementSection />);

    await screen.findByTestId('retirement-band');
    const band = screen.getByTestId('retirement-band');
    expect(band).toHaveTextContent(/\$1\.18M/);
    expect(band).toHaveTextContent(/\$1\.91M/);
  });

  it('shows every assumption on the card without a click', async () => {
    mockGet(projection());
    render(<RetirementSection />);

    expect(await screen.findByLabelText(/return/i)).toHaveValue(6);
    expect(screen.getByLabelText(/inflation/i)).toHaveValue(2.5);
    expect(screen.getByLabelText(/withdrawal rate/i)).toHaveValue(4);
    expect(screen.getByLabelText(/retirement age/i)).toBeInTheDocument();
  });

  it('editing the expected return saves it to the profile and refetches', async () => {
    mockGet(projection());
    render(<RetirementSection />);

    const input = await screen.findByLabelText(/return/i);
    await userEvent.clear(input);
    await userEvent.type(input, '7');
    input.blur();

    await waitFor(() => {
      expect(axios.put).toHaveBeenCalledWith(
        expect.stringContaining('/api/profile'),
        { expected_return_pct: 7 },
      );
    });
  });

  it('shows the contribution method and its caveat', async () => {
    mockGet(projection());
    render(<RetirementSection />);

    expect(await screen.findByText(/from balance history/i)).toBeInTheDocument();
    expect(screen.getByText(/includes market movement/i)).toBeInTheDocument();
  });

  it('names the missing field and offers the settings link when unavailable', async () => {
    const onOpenSettings = jest.fn();
    mockGet(projection({
      available: false,
      missing: ['birth_year'],
      scenarios: null,
      target_pot: null,
    }));
    render(<RetirementSection onOpenSettings={onOpenSettings} />);

    expect(await screen.findByText(/birth year/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /profile/i }));
    expect(onOpenSettings).toHaveBeenCalledWith('profile');
  });
});
