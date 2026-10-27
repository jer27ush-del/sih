import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { portalApi, type ReportResult } from '../../api/portalApi';
import { errorText } from '../../api/client';
import { useAuth } from '../../auth';
import { can } from '../../domain/permissions';
import { Banner, Empty, PageHeading } from '../common';

const REPORTS: { id: string; label: string; needsDays?: boolean }[] = [
  { id: 'fdr-register', label: 'Institution-wise FDR register' },
  { id: 'upcoming-maturities', label: 'Upcoming maturities', needsDays: true },
  { id: 'overdue-maturities', label: 'Overdue / unactioned maturities' },
  { id: 'pending-verification', label: 'Pending verification with ageing' },
  { id: 'open-queries', label: 'Open queries' },
  { id: 'requests', label: 'Renewal and release requests' },
  { id: 'bank-summary', label: 'Bank-wise summary' },
  { id: 'institution-summary', label: 'Institution summary' },
];

export function ReportsPage() {
  const { user } = useAuth();
  const [reportId, setReportId] = useState(REPORTS[0]!.id);
  const [institution, setInstitution] = useState('');
  const [status, setStatus] = useState('');
  const [days, setDays] = useState('90');
  const [error, setError] = useState('');
  const report = REPORTS.find((r) => r.id === reportId) ?? REPORTS[0]!;

  const params = () => {
    const p: Record<string, string> = {};
    if (institution.trim()) p.institution = institution.trim();
    if (status.trim()) p.status = status.trim();
    if (report.needsDays) p.days = days;
    return p;
  };
  const view = useMutation<ReportResult, Error>({ mutationFn: () => portalApi.report(reportId, params()), onError: (e) => setError(errorText(e)) });

  if (!user || !can(user.role, 'view_reports')) return <Banner tone="error">Your role cannot view reports.</Banner>;

  return (
    <section>
      <PageHeading crumb="Reports & Analytics" title="Reports & Analytics" />
      {error && <Banner tone="error">{error}</Banner>}
      <div className="panel">
        <div className="form-grid" style={{ padding: 20 }}>
          <div className="field"><label htmlFor="report">Report</label>
            <select id="report" value={reportId} onChange={(e) => { setReportId(e.target.value); view.reset(); }}>
              {REPORTS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select></div>
          <div className="field"><label htmlFor="rep-inst">Institution code (optional)</label><input id="rep-inst" value={institution} onChange={(e) => setInstitution(e.target.value)} /></div>
          <div className="field"><label htmlFor="rep-status">Status (optional)</label><input id="rep-status" value={status} onChange={(e) => setStatus(e.target.value)} placeholder="e.g. Active" /></div>
          {report.needsDays && <div className="field"><label htmlFor="rep-days">Within days</label><input id="rep-days" type="number" min="1" value={days} onChange={(e) => setDays(e.target.value)} /></div>}
        </div>
        <div className="modal-actions" style={{ padding: '0 20px 20px', justifyContent: 'flex-start' }}>
          <button className="button primary" disabled={view.isPending} onClick={() => { setError(''); view.mutate(); }}>{view.isPending ? 'Running…' : 'Run report'}</button>
          <button className="button secondary" onClick={() => { setError(''); portalApi.downloadReport(reportId, params()).catch((e) => setError(errorText(e))); }}>Download CSV</button>
        </div>
      </div>
      {view.data && (view.data.rows.length === 0 ? <Empty title="No rows for these filters" /> : (
        <div className="panel" style={{ marginTop: 18 }}><div className="table-wrap">
          <table className="table">
            <thead><tr>{view.data.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{view.data.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{String(cell)}</td>)}</tr>)}</tbody>
          </table>
        </div></div>
      ))}
    </section>
  );
}
