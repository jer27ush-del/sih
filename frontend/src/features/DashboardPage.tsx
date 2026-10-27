import { useQuery } from '@tanstack/react-query';
import { Building2, FileText, ShieldCheck, Clock3, Bell } from 'lucide-react';
import { portalApi } from '../api/portalApi';
import { errorText } from '../api/client';
import { useAuth } from '../auth';
import { formatINR, formatRole } from '../utils/format';
import { formatDate } from '../utils/money';
import { Banner, PageHeading, StatusBadge } from './common';

export function DashboardPage() {
  const { user } = useAuth();
  const summary = useQuery({ queryKey: ['dashboard'], queryFn: portalApi.dashboard });
  const d = summary.data;

  return (
    <section>
      <PageHeading crumb="Overview" title="Dashboard">
        <span className="date-pill">{new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date())}</span>
      </PageHeading>
      <p className="muted-copy">Welcome back, {user?.name} ({formatRole(user?.role ?? '')}). Figures are calculated from the live register and reflect your role's scope.</p>
      {summary.isError && <Banner tone="error">{errorText(summary.error)}</Banner>}
      {d && (
        <>
          <div className="dashboard-stats">
            <Stat icon={<FileText size={21} />} tone="teal" label="Registered FDRs" value={d.totalFdrs} note={formatINR(d.totalDepositPaise)} />
            <Stat icon={<ShieldCheck size={21} />} tone="blue" label="Active FDRs" value={d.activeFdrs} note={`${d.flaggedForReview} flagged for review`} />
            <Stat icon={<Clock3 size={21} />} tone="amber" label="Pending verification" value={d.pendingVerification} note={`${d.openQueries} open querie(s)`} />
            <Stat icon={<Bell size={21} />} tone="violet" label="Maturing in 30 days" value={d.maturing30Days} note={`${d.maturing90Days} within 90 days`} />
            <Stat icon={<Building2 size={21} />} tone="blue" label="Overdue / unactioned" value={d.overdueUnactioned} note={`${d.pendingRequests} open request(s)`} />
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading"><div><h2>Upcoming maturities</h2><p>Next five active deposits</p></div></div>
              {d.upcomingMaturities.length === 0 ? <p className="muted-copy">No upcoming maturities.</p> : (
                <table className="table compact"><tbody>{d.upcomingMaturities.map((f) => (
                  <tr key={f.id}><td><b>{f.fdrNumber}</b><span className="table-subtext">{f.institutionCode}</span></td><td>{formatDate(f.maturityDate)}</td><td>{f.daysToMaturity} days</td></tr>
                ))}</tbody></table>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading"><div><h2>Recent submissions</h2><p>Latest five records</p></div></div>
              {d.recentSubmissions.length === 0 ? <p className="muted-copy">No records yet.</p> : (
                <table className="table compact"><tbody>{d.recentSubmissions.map((f) => (
                  <tr key={f.id}><td><b>{f.fdrNumber}</b><span className="table-subtext">{f.institutionCode}</span></td><td><StatusBadge status={f.status} /></td></tr>
                ))}</tbody></table>
              )}
            </section>
          </div>
        </>
      )}
      {summary.isLoading && <p className="muted-copy" role="status">Loading dashboard…</p>}
    </section>
  );
}

function Stat({ icon, tone, label, value, note }: { icon: React.ReactNode; tone: string; label: string; value: number; note: string }) {
  return (
    <article className="dashboard-stat">
      <div className={`dashboard-stat-icon ${tone}`}>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}
