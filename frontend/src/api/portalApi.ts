import { api, downloadFile } from './client';
import type { DashboardSummary, SettingsOptions, SystemSettings } from '../types';

export interface ReportResult { name: string; columns: string[]; rows: (string | number)[][] }

export const portalApi = {
  dashboard: () => api<DashboardSummary>('/dashboard/summary/'),
  options: () => api<SettingsOptions>('/settings/options/'),
  settings: () => api<SystemSettings>('/settings/'),
  saveSettings: (patch: Partial<SystemSettings>) => api<SystemSettings>('/settings/', { method: 'PATCH', body: patch }),
  report: (name: string, params: Record<string, string> = {}) => {
    const query = new URLSearchParams({ format: 'json', ...params });
    return api<ReportResult>(`/reports/${name}/?${query}`);
  },
  downloadReport: (name: string, params: Record<string, string> = {}) => {
    const query = new URLSearchParams({ format: 'csv', ...params });
    return downloadFile(`/reports/${name}/?${query}`, `${name}.csv`);
  },
};
