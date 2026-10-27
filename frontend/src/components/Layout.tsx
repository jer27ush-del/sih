import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Building2, LayoutDashboard, FileText, ShieldCheck, Bell, ClipboardList, Settings, LogOut, Landmark, ChevronRight } from 'lucide-react';
import { useAuth } from '../auth';
import { can, type Action } from '../domain/permissions';
import { formatRole } from '../utils/format';

const nav: { label: string; to: string; icon: typeof FileText; action: Action | null }[] = [
  { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard, action: null },
  { label: 'Institutions', to: '/institutions', icon: Building2, action: 'manage_institutions' },
  { label: 'All FDRs', to: '/fdrs', icon: FileText, action: 'view_fdrs' },
  { label: 'Register FDR / Bulk Import', to: '/register', icon: Landmark, action: 'register_fdr' },
  { label: 'Verification', to: '/verification', icon: ShieldCheck, action: 'review_fdr' },
  { label: 'Maturity & Renewal', to: '/maturity', icon: Bell, action: 'view_fdrs' },
  { label: 'Release Requests', to: '/release', icon: ClipboardList, action: 'view_fdrs' },
  { label: 'Reports', to: '/reports', icon: FileText, action: 'view_reports' },
  { label: 'Notifications', to: '/notifications', icon: Bell, action: null },
  { label: 'Audit Logs', to: '/audit', icon: ClipboardList, action: 'view_audit_logs' },
  { label: 'Settings & Profile', to: '/settings', icon: Settings, action: null },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const visible = nav.filter((item) => !item.action || can(user.role, item.action) || (item.to === '/audit' && user.role === 'scrutiny_officer'));

  async function signOut() {
    await logout();
    navigate('/login');
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Landmark size={23} /></div><div><strong>AICTE FDR</strong><span>Management Portal</span></div></div>
        <div className="sidebar-label">FDR DESK</div>
        <nav aria-label="Main navigation">
          {visible.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <item.icon size={18} aria-hidden="true" /><span>{item.label}</span>{item.to === '/institutions' && <ChevronRight size={14} />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="avatar">{user.name.split(' ').map((part) => part[0]).slice(0, 2).join('')}</div>
          <div className="user-mini"><strong>{user.name}</strong><span>{formatRole(user.role)}</span></div>
          <button className="icon-button" aria-label="Sign out" onClick={() => void signOut()}><LogOut size={17} /></button>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div><span className="eyebrow">GOVERNMENT OF INDIA</span><strong>All India Council for Technical Education</strong></div>
          <div className="topbar-right">{import.meta.env.DEV && <span className="environment-tag">DEVELOPMENT ENVIRONMENT</span>}<span className="top-user">{user.name}</span></div>
        </header>
        <div className="page-content"><Outlet /></div>
        <footer className="page-footer">AICTE FDR Management Portal <span>Prototype · Fictional demonstration data only</span></footer>
      </main>
    </div>
  );
}
