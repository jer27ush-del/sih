import { api } from './client';
import type { User } from '../types';

/** Demo accounts shown on the sign-in page only. Authentication itself is done by the server. */
const DEMO_ACCOUNTS: User[] = [
  { id: 'demo-institution', name: 'Demo Institution User', email: 'institution@demo.test', role: 'institution_user', institutionId: null, status: 'Active', lastLogin: null },
  { id: 'demo-officer', name: 'Sample Scrutiny Officer', email: 'officer@demo.test', role: 'scrutiny_officer', institutionId: null, status: 'Active', lastLogin: null },
  { id: 'demo-admin', name: 'Demo Administrator', email: 'admin@demo.test', role: 'administrator', institutionId: null, status: 'Active', lastLogin: null },
  { id: 'demo-auditor', name: 'Sample Auditor', email: 'auditor@demo.test', role: 'auditor', institutionId: null, status: 'Active', lastLogin: null },
];

export const authApi = {
  getDemoUsers: () => DEMO_ACCOUNTS,
  /** Returns the signed-in user, or null when there is no active session. */
  async me(): Promise<User | null> {
    try {
      return await api<User>('/auth/me/');
    } catch {
      return null;
    }
  },
  login: (email: string, password: string) => api<User>('/auth/login/', { method: 'POST', body: { email, password } }),
  logout: () => api<void>('/auth/logout/', { method: 'POST' }),
  changePassword: (currentPassword: string, newPassword: string) =>
    api<void>('/auth/password/change/', { method: 'POST', body: { currentPassword, newPassword } }),
};
