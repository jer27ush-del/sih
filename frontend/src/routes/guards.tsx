import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../auth';
import type { Role } from '../types';

export function RequireAuth() {
  const { user, loading } = useAuth();
  if (loading) return <div className="route-loading" role="status">Checking your session…</div>;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

/** Convenience only: the server rejects any request the role may not make. */
export function RequireRole({ roles }: { roles: Role[] }) {
  const { user } = useAuth();
  return user && roles.includes(user.role) ? <Outlet /> : <Navigate to="/dashboard" replace />;
}
