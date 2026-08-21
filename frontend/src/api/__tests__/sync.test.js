import axios from 'axios';
import { setDispute } from '../sync';

jest.mock('axios');

test('setDispute URL-encodes txnId, since the local half is arbitrary text minted by the peer', async () => {
  axios.put.mockResolvedValue({ data: {} });

  await setDispute('22222222-2222-2222-2222-222222222222:weird/id#with?chars', { flag: 'Y', note: 'x' });

  expect(axios.put).toHaveBeenCalledWith(
    expect.stringContaining(encodeURIComponent('22222222-2222-2222-2222-222222222222:weird/id#with?chars')),
    { flag: 'Y', note: 'x' }
  );
  expect(axios.put.mock.calls[0][0]).not.toContain('weird/id#with?chars');
});
