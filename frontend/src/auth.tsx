import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { User } from './types';
import { authApi } from './api/authApi';

interface AuthValue {
  user: User | null;
  /** True until the session check finishes, so guards do not redirect too early. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    authApi.me().then((current) => {
      if (active) setUser(current);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthValue>(() => ({
    user,
    loading,
    async login(email, password) {
      setUser(await authApi.login(email, password));
    },
    async logout() {
      try {
        await authApi.logout();
      } finally {
        setUser(null);
      }
    },
  }), [user, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
