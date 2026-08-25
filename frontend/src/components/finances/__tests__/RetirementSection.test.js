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

const headroom = (over = {}) => ({
  available: true,
  reason: null,
  year: 2026,
  as_of: '2026-09-01',
  months_remaining: 4,
  catch_up_eligible: false,
  groups: [
    {
      key: 'ira',
      label: 'IRA',
      ytd: 4200,
      limit: 7500,
      limit_note: null,
      headroom: 3300,
      months_remaining: 4,
      monthly_to_use_remaining: 825,
      accounts: ['Fidelity Roth IRA'],
      approximate: false,
      approximate_reason: null,
    },
  ],
  ...over,
});

const mockGet = (data, headroomData = { available: false, groups: [] }) => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/retirement/projection')) return Promise.resolve({ data });
    if (url.includes('/api/tax/contribution-headroom')) {
      return Promise.resolve({ data: headroomData });
    }
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

describe('RetirementSection contribution headroom', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    axios.put.mockResolvedValue({ data: {} });
  });

  it("compares this year's contributions against the published limit", async () => {
    mockGet(projection(), headroom());
    render(<RetirementSection />);

    const bar = await screen.findByRole('progressbar', { name: /IRA contributions/i });
    expect(bar).toHaveAttribute('aria-valuenow', '4200');
    expect(bar).toHaveAttribute('aria-valuemax', '7500');
    expect(screen.getByText(/\$3,300 of room left/i)).toBeInTheDocument();
    expect(screen.getByText(/\$825\/month/i)).toBeInTheDocument();
    expect(screen.getByText(/4 months left/i)).toBeInTheDocument();
  });

  it('says why a velocity-derived figure is only approximate', async () => {
    mockGet(projection(), headroom({
      groups: [{
        ...headroom().groups[0],
        key: 'workplace',
        label: 'Workplace plan',
        approximate: true,
        approximate_reason:
          'Approximate — based on balance changes, which include growth as well as contributions.',
      }],
    }));
    render(<RetirementSection />);

    expect(await screen.findByText(/based on balance changes, which include growth/i))
      .toBeInTheDocument();
  });

  it('names the year when its limits have not been added', async () => {
    mockGet(projection(), {
      available: false,
      reason: "Contribution limits for 2099 haven't been added yet.",
      groups: [],
    });
    render(<RetirementSection />);

    expect(await screen.findByText(/limits for 2099/i)).toBeInTheDocument();
  });
});
