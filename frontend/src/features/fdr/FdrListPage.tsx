import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fdrApi } from '../../api/fdrApi';
import { errorText } from '../../api/client';
import { formatINR } from '../../utils/format';
import { formatDate } from '../../utils/money';
import { Banner, Empty, PageHeading, StatusBadge } from '../common';
import { FdrDetail } from './FdrDetail';

const ALL_STATUSES = ['Submitted', 'Under Verification', 'Query Raised', 'Corrected', 'Verified', 'Active', 'Nearing Maturity', 'Matured', 'Renewed', 'Release Requested', 'Released / Closed', 'Rejected'];

export function FdrListPage({ title, statuses }: { title: string; statuses?: string[] }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [flagged, setFlagged] = useState(false);
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<string | null>(null);

  const filters = {
    search: search.trim() || undefined,
    status: status || (statuses ? statuses.join(',') : undefined),
    reviewFlag: flagged ? true : undefined,
  };
  const list = useQuery({ queryKey: ['fdrs', 'page', filters, page], queryFn: () => fdrApi.page(filters, page), placeholderData: (previous) => previous });
  const pageSize = 25;
  const total = list.data?.count ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <section>
      <PageHeading crumb={title} title={title}>
        <span className="count-pill">{list.isLoading ? '…' : `${total} record(s)`}</span>
      </PageHeading>
      <div className="panel">
        <div className="table-tools">
          <div className="field"><label htmlFor="fdr-search">Search</label><input id="fdr-search" type="search" placeholder="FDR number, bank, institution code or name" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} /></div>
          {!statuses && (
            <div className="field"><label htmlFor="fdr-status">Status</label>
              <select id="fdr-status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
                <option value="">All statuses</option>{ALL_STATUSES.map((s) => <option key={s}>{s}</option>)}
              </select></div>
          )}
          <label className="checkbox-row"><input type="checkbox" checked={flagged} onChange={(e) => { setFlagged(e.target.checked); setPage(1); }} /> Flagged for review only</label>
        </div>

        {list.isError && <Banner tone="error">{errorText(list.error)}</Banner>}
        {list.isLoading && <p className="muted-copy" role="status">Loading records…</p>}
        {list.data && list.data.results.length === 0 && <Empty title="No records match these filters" />}
        {list.data && list.data.results.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>FDR number</th><th>Institution</th><th>Bank</th><th>Amount</th><th>Maturity</th><th>Status</th><th>Review</th></tr></thead>
              <tbody>
                {list.data.results.map((f) => (
                  <tr key={f.id} className="clickable" onClick={() => setOpenId(f.id)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && setOpenId(f.id)}>
                    <td><b>{f.fdrNumber}</b></td>
                    <td>{f.institutionCode}<span className="table-subtext">{f.institutionName}</span></td>
                    <td>{f.bank}<span className="table-subtext">{f.branch}</span></td>
                    <td>{formatINR(f.amountPaise)}</td>
                    <td>{formatDate(f.maturityDate)}<span className="table-subtext">{f.daysToMaturity} days</span></td>
                    <td><StatusBadge status={f.status} /></td>
                    <td>{f.reviewFlag ? 'Flagged' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="table-footnote pager">
          <button className="button secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} of {lastPage}</span>
          <button className="button secondary" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
      {openId && <FdrDetail fdrId={openId} onClose={() => setOpenId(null)} />}
    </section>
  );
}
