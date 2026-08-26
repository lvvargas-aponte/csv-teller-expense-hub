import axios from 'axios';
import { API_BASE } from '../utils/formatting';

const API = API_BASE;

// A real bank pull, as opposed to a balances cache refresh.
export const syncSimplefin = () => axios.post(`${API}/api/simplefin/sync`, {});
