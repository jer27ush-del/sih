import type { ReactNode } from 'react';

const ACTIVE = ['Active'];
const CLOSED = ['Released / Closed', 'Rejected', 'Inactive', 'Completed', 'Rejected'];

export function StatusBadge({ status }: { status: string }) {
  const tone = ACTIVE.includes(status) ? 'status-active' : CLOSED.includes(status) ? 'status-inactive' : 'status-pending';
  return <span className={`status-badge ${tone}`}>{status}</span>;
}

export function PageHeading({ crumb, title, children }: { crumb: string; title: string; children?: ReactNode }) {
  return (
    <div className="page-heading">
      <div>
        <div className="breadcrumb">FDR Desk <span>/</span> {crumb}</div>
        <h1>{title}</h1>
      </div>
      {children}
    </div>
  );
}

export function Banner({ tone, children }: { tone: 'info' | 'error' | 'success'; children: ReactNode }) {
  if (tone === 'error') return <div className="form-alert" role="alert">{children}</div>;
  return <div className={`notice ${tone === 'success' ? 'info' : 'info'}`} role="status">{children}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty-state"><strong>{title}</strong>{children && <p>{children}</p>}</div>;
}
