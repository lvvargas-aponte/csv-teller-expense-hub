import axios from 'axios';
import { getDashboard } from '../dashboard';

jest.mock('axios');

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockResolvedValue({ data: {} });
});

test('asks for per-category totals by default', async () => {
  await getDashboard(6);
  expect(axios.get).toHaveBeenCalledWith(
    expect.stringContaining('/api/dashboard'),
    { params: { months: 6, rolled_up: false } },
  );
});

test('passes the roll-up through as the query the backend reads', async () => {
  // The toggle refetches rather than reshaping what is on screen, so dropping
  // this parameter would silently return the same data under a new label.
  await getDashboard(12, true);
  expect(axios.get).toHaveBeenCalledWith(
    expect.stringContaining('/api/dashboard'),
    { params: { months: 12, rolled_up: true } },
  );
});
