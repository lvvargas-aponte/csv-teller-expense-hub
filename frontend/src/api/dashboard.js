/**
 * Dashboard API — chart-friendly aggregations consumed by DashboardTab.
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const getDashboard = (months = 6) =>
  axios.get(`${API}/api/dashboard`, { params: { months } });

export const getIncomeVsExpenses = (months = 6) =>
  axios.get(`${API}/api/dashboard/income-vs-expenses`, { params: { months } });

export const getDashboardLayout = () =>
  axios.get(`${API}/api/dashboard/layout`);

export const saveDashboardLayout = (payload) =>
  axios.put(`${API}/api/dashboard/layout`, payload);

export const resetDashboardLayout = () =>
  axios.delete(`${API}/api/dashboard/layout`);

export const getCreditHealth = () =>
  axios.get(`${API}/api/accounts/credit-health`);

export const getAlerts = () =>
  axios.get(`${API}/api/alerts`);

export const getUpcomingBills = (windowDays = 30) =>
  axios.get(`${API}/api/bills/upcoming`, { params: { window_days: windowDays } });
