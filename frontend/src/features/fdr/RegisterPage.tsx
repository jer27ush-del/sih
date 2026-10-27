import { useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { institutionApi } from '../../api/institutionApi';
import { portalApi } from '../../api/portalApi';
import { errorText } from '../../api/client';
import { workflowApi, type ImportPreview } from '../../api/workflowApi';
import { useAuth } from '../../auth';
import { formatBytes, rupeesToPaise } from '../../utils/money';
import { Banner, PageHeading } from '../common';

const EMPTY = { institutionId: '', fdrNumber: '', bank: '', branch: '', amount: '', issueDate: '', maturityDate: '', interestRate: '', payoutType: 'cumulative', category: '', lienMarked: false, heldInFavourOfAICTE: true };

export function RegisterPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isInstitution = user?.role === 'institution_user';
  const options = useQuery({ queryKey: ['settings-options'], queryFn: portalApi.options });
  const institutions = useQuery({ queryKey: ['institutions'], queryFn: institutionApi.list, enabled: !isInstitution });
  const [form, setForm] = useState(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  // Bulk import state
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importInstitution, setImportInstitution] = useState('');
  const [preview, setPreview] = useState<ImportPreview | null>(null);

  const set = (key: keyof typeof EMPTY, value: string | boolean) => setForm((current) => ({ ...current, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setNotice('');
    if (!file) return setError('Attach the supporting PDF or image.');
    if (options.data && file.size > options.data.documentMaxBytes) return setError(`The file is larger than the ${formatBytes(options.data.documentMaxBytes)} limit.`);
    if (!isInstitution && !form.institutionId) return setError('Choose the institution this FDR belongs to.');
    setBusy(true);
    try {
      const created = await workflowApi.register({
        institutionId: isInstitution ? undefined : form.institutionId,
        fdrNumber: form.fdrNumber.trim(), bank: form.bank, branch: form.branch.trim(),
        amountPaise: rupeesToPaise(form.amount), issueDate: form.issueDate, maturityDate: form.maturityDate,
        interestRate: Number(form.interestRate || 0), payoutType: form.payoutType as 'cumulative' | 'periodic',
        category: form.category, lienMarked: form.lienMarked, heldInFavourOfAICTE: form.heldInFavourOfAICTE,
      }, file);
      setNotice(`FDR ${created.fdrNumber} submitted (reference ${created.id.slice(0, 8).toUpperCase()}). It is now awaiting automated checks and officer review.`);
      setForm(EMPTY);
      setFile(null);
      await queryClient.invalidateQueries({ queryKey: ['fdrs'] });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function runPreview() {
    if (!importFile) return;
    setError('');
    setBusy(true);
    try {
      setPreview(await workflowApi.importPreview(importFile, isInstitution ? undefined : importInstitution));
    } catch (err) {
      setPreview(null);
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function commitImport() {
    if (!importFile) return;
    setBusy(true);
    try {
      const result = await workflowApi.importCommit(importFile, isInstitution ? undefined : importInstitution);
      setNotice(`Imported ${result.created} valid row(s). ${result.skipped} row(s) were skipped and are recorded in the audit log.`);
      setPreview(null);
      setImportFile(null);
      await queryClient.invalidateQueries({ queryKey: ['fdrs'] });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const banks = options.data?.banks ?? [];
  const categories = options.data?.categories ?? [];

  return (
    <section>
      <PageHeading crumb="Register" title="Register FDR / Bulk Import" />
      {error && <Banner tone="error">{error}</Banner>}
      {notice && <Banner tone="info">{notice}</Banner>}

      <div className="dashboard-grid">
        <form className="panel" onSubmit={(e) => void submit(e)} noValidate>
          <div className="panel-heading"><div><h2>Register a new FDR</h2><p>Each FDR needs a supporting document. Amounts are stored exactly, in paise.</p></div></div>
          <div className="form-grid" style={{ padding: 20 }}>
            {!isInstitution && (
              <div className="field"><label htmlFor="inst">Institution *</label>
                <select id="inst" value={form.institutionId} onChange={(e) => set('institutionId', e.target.value)}>
                  <option value="">Choose institution</option>
                  {(institutions.data ?? []).filter((i) => i.status === 'Active').map((i) => <option key={i.id} value={i.id}>{i.code} — {i.name}</option>)}
                </select></div>
            )}
            <Input id="fdrNumber" label="FDR / reference number *" value={form.fdrNumber} onChange={(v) => set('fdrNumber', v)} />
            <div className="field"><label htmlFor="bank">Bank *</label>
              <select id="bank" value={form.bank} onChange={(e) => set('bank', e.target.value)}>
                <option value="">Choose bank</option>{banks.map((b) => <option key={b}>{b}</option>)}
              </select></div>
            <Input id="branch" label="Branch *" value={form.branch} onChange={(v) => set('branch', v)} />
            <Input id="amount" label="Deposit amount (INR) *" value={form.amount} onChange={(v) => set('amount', v)} placeholder="500000.00" />
            <Input id="issue" label="Issue date *" type="date" value={form.issueDate} onChange={(v) => set('issueDate', v)} />
            <Input id="maturity" label="Maturity date *" type="date" value={form.maturityDate} onChange={(v) => set('maturityDate', v)} />
            <Input id="rate" label="Interest rate (%)" type="number" value={form.interestRate} onChange={(v) => set('interestRate', v)} />
            <div className="field"><label htmlFor="payout">Payout type</label>
              <select id="payout" value={form.payoutType} onChange={(e) => set('payoutType', e.target.value)}><option value="cumulative">Cumulative</option><option value="periodic">Periodic</option></select></div>
            <div className="field"><label htmlFor="category">Deposit category *</label>
              <select id="category" value={form.category} onChange={(e) => set('category', e.target.value)}>
                <option value="">Choose category</option>{categories.map((c) => <option key={c}>{c}</option>)}
              </select></div>
            <label className="checkbox-row"><input type="checkbox" checked={form.lienMarked} onChange={(e) => set('lienMarked', e.target.checked)} /> Lien marked</label>
            <label className="checkbox-row"><input type="checkbox" checked={form.heldInFavourOfAICTE} onChange={(e) => set('heldInFavourOfAICTE', e.target.checked)} /> Held in favour of AICTE</label>
            <div className="field" style={{ gridColumn: '1/-1' }}>
              <label htmlFor="file">Supporting document (PDF, PNG or JPEG) *</label>
              <input id="file" type="file" accept=".pdf,image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              {options.data && <small>Maximum {formatBytes(options.data.documentMaxBytes)}. The file type is checked from its content.</small>}
            </div>
          </div>
          <div className="modal-actions" style={{ padding: '0 20px 20px' }}><button className="button primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit FDR'}</button></div>
        </form>

        <section className="panel">
          <div className="panel-heading"><div><h2>Bulk import CSV</h2><p>Every row is checked before anything is saved.</p></div></div>
          <div style={{ padding: 20, display: 'grid', gap: 12 }}>
            <button className="button secondary" onClick={() => void workflowApi.downloadImportTemplate()}>Download CSV template</button>
            <div className="field"><label htmlFor="import-file">CSV file</label>
              <input id="import-file" type="file" accept=".csv,text/csv" onChange={(e) => { setImportFile(e.target.files?.[0] ?? null); setPreview(null); }} /></div>
            {!isInstitution && (
              <div className="field"><label htmlFor="import-inst">Institution *</label>
                <select id="import-inst" value={importInstitution} onChange={(e) => setImportInstitution(e.target.value)}>
                  <option value="">Choose institution</option>
                  {(institutions.data ?? []).map((i) => <option key={i.id} value={i.id}>{i.code} — {i.name}</option>)}
                </select></div>
            )}
            <button className="button secondary" disabled={!importFile || busy || (!isInstitution && !importInstitution)} onClick={() => void runPreview()}>Preview and validate</button>
            {preview && (
              <>
                <p className="muted-copy">Valid: <b>{preview.summary.valid}</b> · Errors: <b>{preview.summary.error}</b> · Duplicates: <b>{preview.summary.duplicate}</b></p>
                <div className="table-wrap" style={{ maxHeight: 260, overflow: 'auto' }}>
                  <table className="table compact">
                    <thead><tr><th>Line</th><th>FDR number</th><th>Result</th><th>Reason</th></tr></thead>
                    <tbody>{preview.rows.slice(0, 200).map((row) => (
                      <tr key={row.line}><td>{row.line}</td><td>{row.fdrNumber}</td><td>{row.status}</td><td>{row.messages.filter(Boolean).join('; ') || '—'}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
                <button className="button primary" disabled={busy || preview.summary.valid === 0} onClick={() => void commitImport()}>Import {preview.summary.valid} valid row(s)</button>
                {(preview.summary.error > 0 || preview.summary.duplicate > 0) && (
                  <button className="button secondary" onClick={() => importFile && void workflowApi.downloadImportErrors(importFile, isInstitution ? undefined : importInstitution)}>Download error report</button>
                )}
              </>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

function Input({ id, label, value, onChange, type = 'text', placeholder }: { id: string; label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string }) {
  return <div className="field"><label htmlFor={id}>{label}</label><input id={id} type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} /></div>;
}
