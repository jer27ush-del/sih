import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { auditApi } from '../../api/auditApi';
import { errorText } from '../../api/client';
import { formatDateTime } from '../../utils/money';
import { Banner, PageHeading } from '../common';

const ENTITIES = ['', 'FDR', 'Query', 'FdrRequest', 'BankConfirmation', 'Document', 'Institution', 'User', 'Settings', 'Report', 'ImportBatch'];

export function AuditPage() {
  const [entity, setEntity] = useState('');
  const [action, setAction] = useState('');
  const [page, setPage] = useState(1);
  const logs = useQuery({ queryKey: ['audit', entity, action, page], queryFn: () => auditApi.page({ entity, action, page }), placeholderData: (previous) => previous });

  return (
    <section>
      <PageHeading crumb="Audit Logs" title="Audit history" />
      <p className="muted-copy">Append-only. Entries cannot be edited or deleted by any user, including administrators.</p>
      <div className="panel">
        <div className="table-tools">
          <div className="field"><label htmlFor="audit-entity">Entity</label>
            <select id="audit-entity" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1); }}>
              {ENTITIES.map((item) => <option key={item} value={item}>{item || 'All entities'}</option>)}
            </select></div>
          <div className="field"><label htmlFor="audit-action">Action contains</label><input id="audit-action" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} placeholder="e.g. status_changed" /></div>
        </div>
        {logs.isError && <Banner tone="error">{errorText(logs.error)}</Banner>}
        {logs.data && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Change</th><th>IP</th></tr></thead>
              <tbody>
                {logs.data.results.map((entry) => (
                  <tr key={entry.id}>
                    <td>{formatDateTime(entry.timestamp)}</td>
                    <td>{entry.actorLabel}</td>
                    <td>{entry.action}</td>
                    <td>{entry.entity}<span className="table-subtext">{entry.entityId}</span></td>
                    <td className="table-subtext">{JSON.stringify(entry.oldValue ?? null)} → {JSON.stringify(entry.newValue ?? null)}</td>
                    <td>{entry.ipAddress ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="table-footnote pager">
          <button className="button secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page}</span>
          <button className="button secondary" disabled={!logs.data?.next} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
    </section>
  );
}
