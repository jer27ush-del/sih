import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fdrApi } from '../../api/fdrApi';
import { workflowApi } from '../../api/workflowApi';
import { errorText } from '../../api/client';
import { useAuth } from '../../auth';
import { can } from '../../domain/permissions';
import { formatDate, formatDateTime } from '../../utils/money';
import { Banner, Empty, PageHeading, StatusBadge } from '../common';

export function RequestsPage() {
  const { user } = useAuth();
  const role = user?.role ?? 'auditor';
  const queryClient = useQueryClient();
  const requests = useQuery({ queryKey: ['requests'], queryFn: () => workflowApi.listRequests() });
  const fdrs = useQuery({ queryKey: ['fdrs', 'releasable'], queryFn: fdrApi.list, enabled: can(role, 'submit_request') });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [note, setNote] = useState<Record<string, string>>({});
  const [newRequest, setNewRequest] = useState({ fdrId: '', reason: '', bankTermsNoted: false });

  const releasable = (fdrs.data ?? []).filter((f) => ['Active', 'Nearing Maturity', 'Matured'].includes(f.status));
  const selected = releasable.find((f) => f.id === newRequest.fdrId);

  async function act(action: () => Promise<unknown>, success: string) {
    setError('');
    setNotice('');
    try {
      await action();
      setNotice(success);
      await queryClient.invalidateQueries({ queryKey: ['requests'] });
      await queryClient.invalidateQueries({ queryKey: ['fdrs'] });
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <PageHeading crumb="Release / Premature Withdrawal" title="Release Requests" />
      {error && <Banner tone="error">{error}</Banner>}
      {notice && <Banner tone="info">{notice}</Banner>}

      {can(role, 'submit_request') && (
        <div className="panel" style={{ marginBottom: 18 }}>
          <div className="panel-heading"><div><h2>New release request</h2><p>Choose an active or matured FDR. Supporting documents must already be attached.</p></div></div>
          <div className="form-grid" style={{ padding: 20 }}>
            <div className="field"><label htmlFor="req-fdr">FDR</label>
              <select id="req-fdr" value={newRequest.fdrId} onChange={(e) => setNewRequest({ ...newRequest, fdrId: e.target.value })}>
                <option value="">Choose an FDR</option>{releasable.map((f) => <option key={f.id} value={f.id}>{f.fdrNumber} — {f.bank} ({f.status})</option>)}
              </select></div>
            <div className="field"><label htmlFor="req-reason">Reason</label><input id="req-reason" value={newRequest.reason} onChange={(e) => setNewRequest({ ...newRequest, reason: e.target.value })} /></div>
            {selected && selected.status !== 'Matured' && (
              <label className="checkbox-row"><input type="checkbox" checked={newRequest.bankTermsNoted} onChange={(e) => setNewRequest({ ...newRequest, bankTermsNoted: e.target.checked })} /> I have noted the bank's premature-closure terms.</label>
            )}
          </div>
          <div className="modal-actions" style={{ padding: '0 20px 20px' }}>
            <button className="button primary" disabled={!selected || !newRequest.reason.trim() || (selected?.status !== 'Matured' && !newRequest.bankTermsNoted)}
              onClick={() => selected && void act(async () => { await workflowApi.submitRelease(selected.id, { releaseKind: selected.status === 'Matured' ? 'at_maturity' : 'premature', reason: newRequest.reason, bankTermsNoted: newRequest.bankTermsNoted }); setNewRequest({ fdrId: '', reason: '', bankTermsNoted: false }); }, 'Request submitted for review.')}>Submit request</button>
          </div>
        </div>
      )}

      {requests.isLoading && <p className="muted-copy" role="status">Loading requests…</p>}
      {requests.data?.length === 0 && <Empty title="No requests yet" />}
      {requests.data && requests.data.length > 0 && (
        <div className="panel"><div className="table-wrap">
          <table className="table">
            <thead><tr><th>FDR</th><th>Type</th><th>Status</th><th>Reason</th><th>History</th><th>Action</th></tr></thead>
            <tbody>
              {requests.data.map((r) => (
                <tr key={r.id}>
                  <td><b>{r.fdrNumber}</b></td>
                  <td>{r.requestType}{r.releaseKind && <span className="table-subtext">{r.releaseKind === 'premature' ? 'premature withdrawal' : 'at maturity'}</span>}</td>
                  <td><StatusBadge status={r.status} /></td>
                  <td>{r.reason}</td>
                  <td className="table-subtext">Submitted {formatDate(r.createdAt)} by {r.submittedByName}
                    {r.recommendedByName && <><br />Recommended {formatDateTime(r.recommendedAt)} by {r.recommendedByName}</>}
                    {r.decidedByName && <><br />Decided by {r.decidedByName}: {r.actionTaken}</>}</td>
                  <td>
                    {r.requestType === 'release' && r.status === 'Submitted' && can(role, 'recommend_release') && (
                      <div className="inline-form">
                        <input aria-label="Recommendation note" placeholder="Note" value={note[r.id] ?? ''} onChange={(e) => setNote({ ...note, [r.id]: e.target.value })} />
                        <button className="button secondary" onClick={() => void act(() => workflowApi.recommendRequest(r.id, note[r.id] ?? ''), 'Recommendation recorded.')}>Recommend</button>
                      </div>
                    )}
                    {r.requestType === 'release' && r.status === 'Recommended' && can(role, 'approve_release') && (
                      <div className="inline-form">
                        <input aria-label="Action taken or rejection reason" placeholder="Action taken / reason" value={note[r.id] ?? ''} onChange={(e) => setNote({ ...note, [r.id]: e.target.value })} />
                        <button className="button primary" onClick={() => void act(() => workflowApi.decideRequest(r.id, { decision: 'approve', actionTaken: note[r.id] ?? '' }), 'Request approved and deposit closed.')}>Approve</button>
                        <button className="button danger" onClick={() => void act(() => workflowApi.decideRequest(r.id, { decision: 'reject', reason: note[r.id] ?? '' }), 'Request rejected. The FDR returned to its previous status.')}>Reject</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div></div>
      )}
    </section>
  );
}
