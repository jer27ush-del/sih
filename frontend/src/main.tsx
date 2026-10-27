import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './auth';
import { RequireAuth, RequireRole } from './routes/guards';
import { Layout } from './components/Layout';
import { LoginPage } from './features/LoginPage';
import { DashboardPage } from './features/DashboardPage';
import { FdrListPage } from './features/fdr/FdrListPage';
import { RegisterPage } from './features/fdr/RegisterPage';
import { MaturityPage } from './features/fdr/MaturityPage';
import { RequestsPage } from './features/fdr/RequestsPage';
import { ReportsPage } from './features/admin/ReportsPage';
import { AuditPage } from './features/admin/AuditPage';
import { SettingsPage } from './features/admin/SettingsPage';
import { NotificationsPage } from './features/NotificationsPage';
import './i18n';
import './styles.css';

const InstitutionsPage = lazy(async () => import('./features/institutions/InstitutionsPage').then((module) => ({ default: module.InstitutionsPage })));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15000 } } });

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<div className="route-loading" role="status">Loading module…</div>}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<RequireAuth />}>
                <Route element={<Layout />}>
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route element={<RequireRole roles={['administrator']} />}>
                    <Route path="/institutions" element={<InstitutionsPage />} />
                  </Route>
                  <Route path="/fdrs" element={<FdrListPage title="All FDRs" />} />
                  <Route path="/verification" element={<FdrListPage title="Verification" statuses={['Submitted', 'Under Verification', 'Query Raised', 'Corrected']} />} />
                  <Route path="/register" element={<RegisterPage />} />
                  <Route path="/maturity" element={<MaturityPage />} />
                  <Route path="/release" element={<RequestsPage />} />
                  <Route path="/reports" element={<ReportsPage />} />
                  <Route path="/notifications" element={<NotificationsPage />} />
                  <Route path="/audit" element={<AuditPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
              </Route>
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
