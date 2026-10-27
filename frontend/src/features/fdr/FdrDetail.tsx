import { useState, type ReactNode } from 'react';
import { useQueryClient, useQuery } from '@tanstack/react-query';
import { fdrApi } from '../../api/fdrApi';
import { workflowApi, type BankMode, type RegisterInput } from '../../api/workflowApi';
import { errorText } from '../../api/client';
import { useAuth } from '../../auth';
import { can } from '../../domain/permissions';
import { formatINR } from '../../utils/format';
import { formatBytes, formatDate, formatDateTime, rupeesToPaise, todayIso } from '../../utils/money';
import { Banner, StatusBadge } from '../common';

const RULE_LABELS: Record<string, string> = {
  requiredFields: 'Required fields', duplicateReference: 'Duplicate reference', dateLogic: 'Date logic',
  tenureValidity: 'Tenure / validity', amountRange: 'Amount range', documentQuality: 'Document quality',
  bankConfirmation: 'Bank confirmation',
};
const REVIEW_STATES = ['Under Verification', 'Query Raised', 'Corrected'];
const UPLOAD_STATES = ['Submitted', 'Under Verification', 'Query Raised', 'Corrected'];
const RELEASE_STATES = ['Active', 'Nearing Maturity', 'Matured'];
const RENEW_STATES = ['Nearing Maturity', 'Matured'];

export function FdrDetail({ fdrId, onClose }: { fdrId: string; onClose: () => void }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ['fdr', fdrId], queryFn: () => fdrApi.get(fdrId) });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  // Form state for each action (kept separate so one half-filled form does not affect another).
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [queryText, setQueryText] = useState('');
  const [replyText, setReplyText] = useState<Record<string, string>>({});
  const [bank, setBank] = useState({ date: todayIso(), mode: 'email' as BankMode, reference: '' });
  const [decisionReason, setDecisionReason] = useState('');
  const [renewal, setRenewal] = useState<Partial<RegisterInput> & { fdrNumber?: string; amountRupees?: string }>({ lienMarked: false, heldInFavourOfAICTE: true, payoutType: 'cumulative' });
  const [release, setRelease] = useState({ reason: '', bankTermsNoted: false });

  if (detail.isLoading) return <Modal onClose={onClose}><p role="status">Loading record…</p></Modal>;
  if (detail.isError || !detail.data) return <Modal onClose={onClose}><Banner tone="error">{errorText(detail.error)}</Banner></Modal>;

  const fdr = detail.data;
  const role = user?.role ?? 'auditor';
  const canReview = can(role, 'review_fdr');
  const canRegister = can(role, 'register_fdr');
  const canReply = can(role, 'reply_query');
  const canRequest = can(role, 'submit_request');
  const openQuery = fdr.queries.find((q) => q.status === 'open');
  const latestRun = fdr.verificationRuns[0];

  async function run(action: () => Promise<unknown>, success: string) {
    setError('');
    setNotice('');
    setBusy(true);
    try {
      await action();
      setNotice(success);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['fdr', fdrId] }),
        queryClient.invalidateQueries({ queryKey: ['fdrs'] }),
        queryClient.invalidateQueries({ queryKey: ['maturity'] }),
        queryClient.invalidateQueries({ queryKey: ['requests'] }),
      ]);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} title={fdr.fdrNumber} wide>
      <div className="detail-badges"><StatusBadge status={fdr.status} />{fdr.reviewFlag && <span className="status-badge status-pending">Flagged for review</span>}</div>
      {error && <Banner tone="error">{error}</Banner>}
      {notice && <Banner tone="info">{notice}</Banner>}

      <section className="detail-section">
        <div className="form-grid">
          <Info label="Institution" value={`${fdr.institutionCode ?? ''} ${fdr.institutionName ?? ''}`} />
          <Info label="Bank / branch" value={`${fdr.bank} — ${fdr.branch}`} />
          <Info label="Amount" value={formatINR(fdr.amountPaise)} />
          <Info label="Interest / payout" value={`${fdr.interestRate}% · ${fdr.payoutType}`} />
          <Info label="Issue date" value={formatDate(fdr.issueDate)} />
          <Info label="Maturity date" value={`${formatDate(fdr.maturityDate)} (${fdr.daysToMaturity ?? '—'} days)`} />
          <Info label="Category" value={`${fdr.category}${fdr.lienMarked ? ' · lien marked' : ''}`} />
          <Info label="Bank confirmation" value={fdr.bankConfirmed ? `Confirmed ${formatDate(fdr.bankConfirmedOn)}` : 'Not recorded'} />
        </div>
        {fdr.statusNote && <p className="muted-copy">Last note: {fdr.statusNote}</p>}
      </section>

      <Section title="Documents">
        {fdr.documents.length === 0 && <p className="muted-copy">No document uploaded yet.</p>}
        {fdr.documents.map((doc) => (
          <div className="detail-row" key={doc.id}>
            <span>v{doc.version} · {doc.originalName} · {formatBytes(doc.sizeBytes)} {doc.active ? '(current)' : '(superseded)'}</span>
            <button className="button secondary" onClick={() => void run(() => workflowApi.downloadDocument(doc), 'Download started.')}>Download</button>
          </div>
        ))}
        {canRegister && UPLOAD_STATES.includes(fdr.status) && (
          <div className="inline-form">
            <input type="file" accept=".pdf,image/png,image/jpeg" aria-label="Choose document" onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)} />
            <button className="button secondary" disabled={!uploadFile || busy} onClick={() => uploadFile && void run(async () => { await workflowApi.uploadDocument(fdrId, uploadFile); setUploadFile(null); }, 'Document uploaded. Automated checks were re-run.')}>Upload new version</button>
          </div>
        )}
      </Section>

      <Section title="Automated checks">
        {!latestRun ? <p className="muted-copy">No checks have been run yet.</p> : (
          <table className="table compact">
            <tbody>
              {Object.entries(latestRun.ruleResults).map(([key, flag]) => (
                <tr key={key}><td>{RULE_LABELS[key] ?? key}</td><td><span className={`status-badge ${flag === 'pass' ? 'status-active' : flag === 'fail' ? 'status-inactive' : 'status-pending'}`}>{flag}</span></td></tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted-copy">Checks flag records for review; they never reject a record on their own.</p>
        {canReview && REVIEW_STATES.includes(fdr.status) && (
          <button className="button secondary" disabled={busy} onClick={() => void run(() => workflowApi.runChecks(fdrId), 'Automated checks completed.')}>Run checks again</button>
        )}
      </Section>

      <Section title="Queries">
        {fdr.queries.length === 0 && <p className="muted-copy">No queries raised.</p>}
        {fdr.queries.map((q) => (
          <div className="detail-row column" key={q.id}>
            <span><b>{q.message}</b> · raised by {q.raisedByName} · {q.daysPending} day(s) · {q.status}</span>
            {q.reply && <span>Reply: {q.reply}</span>}
            {canReply && q.status === 'open' && fdr.status === 'Query Raised' && (
              <div className="inline-form">
                <input aria-label="Reply to query" value={replyText[q.id] ?? ''} onChange={(e) => setReplyText({ ...replyText, [q.id]: e.target.value })} placeholder="Explain or confirm the correction" />
                <button className="button primary" disabled={!replyText[q.id]?.trim() || busy} onClick={() => void run(() => workflowApi.replyQuery(q.id, replyText[q.id] ?? ''), 'Reply sent. The record is now awaiting re-review.')}>Send reply</button>
              </div>
            )}
          </div>
        ))}
        {canReview && fdr.status === 'Under Verification' && (
          <div className="inline-form">
            <input aria-label="New query" value={queryText} onChange={(e) => setQueryText(e.target.value)} placeholder="What does the institution need to correct?" />
            <button className="button secondary" disabled={!queryText.trim() || busy} onClick={() => void run(async () => { await workflowApi.raiseQuery(fdrId, queryText); setQueryText(''); }, 'Query sent to the institution.')}>Raise query</button>
          </div>
        )}
        {openQuery && role === 'institution_user' && fdr.status !== 'Query Raised' && <p className="muted-copy">Query answered; awaiting officer review.</p>}
      </Section>

      <Section title="Bank confirmation">
        {fdr.bankConfirmations.map((c) => (
          <div className="detail-row" key={c.id}><span>{formatDate(c.confirmedOn)} · {c.mode} · ref {c.reference} · by {c.confirmedByName}</span></div>
        ))}
        {canReview && REVIEW_STATES.includes(fdr.status) && (
          <div className="form-grid">
            <div className="field"><label htmlFor="bank-date">Confirmed on</label><input id="bank-date" type="date" max={todayIso()} value={bank.date} onChange={(e) => setBank({ ...bank, date: e.target.value })} /></div>
            <div className="field"><label htmlFor="bank-mode">How it was confirmed</label>
              <select id="bank-mode" value={bank.mode} onChange={(e) => setBank({ ...bank, mode: e.target.value as BankMode })}>
                <option value="letter">Bank letter</option><option value="email">Email from bank</option><option value="phone">Telephone</option><option value="bank_portal">Bank portal</option><option value="other">Other</option>
              </select></div>
            <div className="field"><label htmlFor="bank-ref">Reference / letter number</label><input id="bank-ref" value={bank.reference} onChange={(e) => setBank({ ...bank, reference: e.target.value })} /></div>
            <button className="button secondary" style={{ alignSelf: 'end' }} disabled={!bank.reference.trim() || busy} onClick={() => void run(() => workflowApi.bankConfirm(fdrId, { confirmedOn: bank.date, mode: bank.mode, reference: bank.reference.trim() }), 'Bank confirmation recorded.')}>Record confirmation</button>
          </div>
        )}
      </Section>

      {canReview && fdr.status === 'Under Verification' && (
        <Section title="Decision">
          <div className="field"><label htmlFor="decision-reason">Reason (required)</label><input id="decision-reason" value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)} /></div>
          <div className="modal-actions" style={{ justifyContent: 'flex-start' }}>
            <button className="button primary" disabled={!fdr.bankConfirmed || !decisionReason.trim() || busy} onClick={() => void run(() => workflowApi.decide(fdrId, 'Verified', decisionReason), 'Record verified and activated.')}>Verify</button>
            <button className="button danger" disabled={!decisionReason.trim() || busy} onClick={() => void run(() => workflowApi.decide(fdrId, 'Rejected', decisionReason), 'Record rejected. The reason is kept in the audit log.')}>Reject</button>
          </div>
          {!fdr.bankConfirmed && <p className="muted-copy">Verification is blocked until a bank confirmation is recorded.</p>}
        </Section>
      )}

      {canRequest && RENEW_STATES.includes(fdr.status) && (
        <Section title="Submit renewal (replacement FDR)">
          <div className="form-grid">
            <Text label="New FDR number" value={renewal.fdrNumber ?? ''} onChange={(v) => setRenewal({ ...renewal, fdrNumber: v })} />
            <Text label="Bank" value={renewal.bank ?? fdr.bank} onChange={(v) => setRenewal({ ...renewal, bank: v })} />
            <Text label="Branch" value={renewal.branch ?? ''} onChange={(v) => setRenewal({ ...renewal, branch: v })} />
            <Text label="Amount (INR)" value={renewal.amountRupees ?? ''} onChange={(v) => setRenewal({ ...renewal, amountRupees: v })} />
            <Text label="Issue date" type="date" value={renewal.issueDate ?? ''} onChange={(v) => setRenewal({ ...renewal, issueDate: v })} />
            <Text label="Maturity date" type="date" value={renewal.maturityDate ?? ''} onChange={(v) => setRenewal({ ...renewal, maturityDate: v })} />
            <Text label="Interest rate (%)" value={String(renewal.interestRate ?? '')} onChange={(v) => setRenewal({ ...renewal, interestRate: Number(v) })} />
            <Text label="Category" value={renewal.category ?? fdr.category} onChange={(v) => setRenewal({ ...renewal, category: v })} />
          </div>
          <button className="button primary" style={{ marginTop: 12 }} disabled={busy} onClick={() => void run(async () => {
            const { amountRupees, ...rest } = renewal;
            await workflowApi.renew(fdrId, { ...(rest as RegisterInput), amountPaise: rupeesToPaise(amountRupees ?? ''), bank: rest.bank ?? fdr.bank, branch: rest.branch ?? '', category: rest.category ?? fdr.category, interestRate: rest.interestRate ?? 0, payoutType: rest.payoutType ?? 'cumulative', lienMarked: false, heldInFavourOfAICTE: true });
          }, 'Replacement FDR submitted for verification.')}>Submit renewal</button>
        </Section>
      )}

      {canRequest && RELEASE_STATES.includes(fdr.status) && (
        <Section title="Request release or premature withdrawal">
          <div className="field"><label htmlFor="release-reason">Reason</label><input id="release-reason" value={release.reason} onChange={(e) => setRelease({ ...release, reason: e.target.value })} /></div>
          {fdr.status !== 'Matured' && (
            <label className="checkbox-row"><input type="checkbox" checked={release.bankTermsNoted} onChange={(e) => setRelease({ ...release, bankTermsNoted: e.target.checked })} /> I have noted the bank's premature-closure terms (penalty or reduced interest).</label>
          )}
          <p className="muted-copy">{fdr.status === 'Matured' ? 'This FDR has matured, so the request is for release at maturity.' : 'This FDR has not matured, so the request is for premature withdrawal.'} Attach supporting documents before submitting.</p>
          <button className="button primary" disabled={!release.reason.trim() || busy || (fdr.status !== 'Matured' && !release.bankTermsNoted)} onClick={() => void run(() => workflowApi.submitRelease(fdrId, { releaseKind: fdr.status === 'Matured' ? 'at_maturity' : 'premature', reason: release.reason, bankTermsNoted: release.bankTermsNoted }), 'Release request submitted.')}>Submit request</button>
        </Section>
      )}

      {fdr.requests.length > 0 && (
        <Section title="Requests">
          {fdr.requests.map((r) => <div className="detail-row" key={r.id}><span>{r.requestType} · {r.status} · {r.reason}</span></div>)}
        </Section>
      )}

      <Section title="Timeline">
        {fdr.reminders.slice(0, 5).map((r, i) => <div className="detail-row" key={i}><span>{r.kind} reminder</span><span>{formatDateTime(r.sentAt)}</span></div>)}
        {fdr.renewals.map((r) => <div className="detail-row" key={r.id}><span>Replaced by {r.fdrNumber}</span><StatusBadge status={r.status} /></div>)}
        {fdr.parentFdrId && <p className="muted-copy">This FDR is a renewal of an earlier deposit.</p>}
      </Section>
    </Modal>
  );
}

function Modal({ title, onClose, wide, children }: { title?: string; onClose: () => void; wide?: boolean; children: ReactNode }) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title ?? 'Record'} onClick={(e) => e.stopPropagation()}>
        <div className="modal-heading"><div><span className="eyebrow">FDR DESK</span><h2>{title ?? 'Record'}</h2></div><button className="button secondary" onClick={onClose}>Close</button></div>
        {children}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="detail-section"><h3>{title}</h3>{children}</section>;
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><b>{label}</b><p>{value}</p></div>;
}

function Text({ label, value, onChange, type = 'text' }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  const id = `f-${label.replace(/\W+/g, '-').toLowerCase()}`;
  return <div className="field"><label htmlFor={id}>{label}</label><input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)} /></div>;
}
