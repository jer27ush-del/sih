import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { workflowApi } from '../../api/workflowApi';
import { errorText } from '../../api/client';
import { formatINR } from '../../utils/format';
import { formatDate } from '../../utils/money';
import { Banner, Empty, PageHeading, StatusBadge } from '../common';
import { FdrDetail } from './FdrDetail';

export function MaturityPage() {
  const list = useQuery({ queryKey: ['maturity'], queryFn: workflowApi.maturity });
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <section>
      <PageHeading crumb="Maturity & Renewal" title="Maturity & Renewal" />
      <p className="muted-copy">Deposits in their maturity cycle, soonest first. Maturity never releases a deposit on its own; each one needs a renewal or release request.</p>
      {list.isError && <Banner tone="error">{errorText(list.error)}</Banner>}
      {list.data?.length === 0 && <Empty title="No deposits are in the maturity cycle" />}
      {list.data && list.data.length > 0 && (
        <div className="panel"><div className="table-wrap">
          <table className="table">
            <thead><tr><th>FDR number</th><th>Institution</th><th>Amount</th><th>Maturity date</th><th>Days remaining</th><th>Status</th></tr></thead>
            <tbody>
              {list.data.map((f) => (
                <tr key={f.id} className="clickable" tabIndex={0} onClick={() => setOpenId(f.id)} onKeyDown={(e) => e.key === 'Enter' && setOpenId(f.id)}>
                  <td><b>{f.fdrNumber}</b></td>
                  <td>{f.institutionCode}</td>
                  <td>{formatINR(f.amountPaise)}</td>
                  <td>{formatDate(f.maturityDate)}</td>
                  <td>{(f.daysToMaturity ?? 0) < 0 ? `${Math.abs(f.daysToMaturity ?? 0)} days overdue` : `${f.daysToMaturity} days`}</td>
                  <td><StatusBadge status={f.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div></div>
      )}
      {openId && <FdrDetail fdrId={openId} onClose={() => setOpenId(null)} />}
    </section>
  );
}
