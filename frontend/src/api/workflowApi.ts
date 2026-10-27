import { api, downloadFile } from './client';
import type { BankConfirmation, FDR, FdrDocument, QueryRecord, RequestRecord } from '../types';
import { mapFdr } from './fdrApi';

export interface RegisterInput {
  institutionId?: string;
  fdrNumber: string; bank: string; branch: string; amountPaise: number;
  issueDate: string; maturityDate: string; interestRate: number;
  payoutType: 'cumulative' | 'periodic'; category: string; lienMarked: boolean; heldInFavourOfAICTE: boolean;
}
export type BankMode = 'letter' | 'email' | 'phone' | 'bank_portal' | 'other';
export interface ImportPreview {
  summary: { valid: number; error: number; duplicate: number };
  rows: { line: number; status: 'valid' | 'error' | 'duplicate'; fdrNumber: string; messages: string[] }[];
}

function fileForm(fields: Record<string, string | Blob>): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) form.append(key, value);
  return form;
}

export const workflowApi = {
  /** Registers an FDR. The document is uploaded separately, as the server stores it as a versioned record. */
  async register(input: RegisterInput, file: File): Promise<FDR> {
    const created = mapFdr(await api<FDR>('/fdrs/', { method: 'POST', body: input }));
    await this.uploadDocument(created.id, file);
    return created;
  },
  uploadDocument: (fdrId: string, file: File) =>
    api<FdrDocument>(`/fdrs/${fdrId}/documents/`, { method: 'POST', form: fileForm({ file }) }),
  downloadDocument: (doc: FdrDocument) => downloadFile(`/documents/${doc.id}/download/`, doc.originalName),
  runChecks: (fdrId: string) => api<{ ruleResults: Record<string, string> }>(`/fdrs/${fdrId}/verify/`, { method: 'POST' }),
  raiseQuery: (fdrId: string, message: string) => api<QueryRecord>(`/fdrs/${fdrId}/queries/`, { method: 'POST', body: { message } }),
  replyQuery: (queryId: string, reply: string) => api<QueryRecord>(`/queries/${queryId}/reply/`, { method: 'POST', body: { reply } }),
  bankConfirm: (fdrId: string, input: { confirmedOn: string; mode: BankMode; reference: string }) =>
    api<BankConfirmation>(`/fdrs/${fdrId}/bank-confirmation/`, { method: 'POST', body: input }),
  decide: (fdrId: string, decision: 'Verified' | 'Rejected', reason: string) =>
    api<FDR>(`/fdrs/${fdrId}/decision/`, { method: 'POST', body: { decision, reason } }),
  renew: (fdrId: string, input: RegisterInput) => api<FDR>(`/fdrs/${fdrId}/renewals/`, { method: 'POST', body: input }),
  submitRelease: (fdrId: string, input: { releaseKind: 'at_maturity' | 'premature'; reason: string; bankTermsNoted: boolean }) =>
    api<RequestRecord>(`/fdrs/${fdrId}/requests/`, { method: 'POST', body: input }),
  recommendRequest: (requestId: string, note: string) =>
    api<RequestRecord>(`/requests/${requestId}/recommend/`, { method: 'POST', body: { note } }),
  decideRequest: (requestId: string, input: { decision: 'approve' | 'reject'; actionTaken?: string; reason?: string }) =>
    api<RequestRecord>(`/requests/${requestId}/decision/`, { method: 'POST', body: input }),
  /** Preview validates the file and saves nothing. Commit imports the valid rows only. */
  importPreview: (file: File, institutionId?: string) =>
    api<ImportPreview>('/fdrs/import/', { method: 'POST', form: fileForm({ file, commit: 'false', ...(institutionId ? { institution: institutionId } : {}) }) }),
  importCommit: (file: File, institutionId?: string) =>
    api<{ created: number; skipped: number }>('/fdrs/import/', { method: 'POST', form: fileForm({ file, commit: 'true', ...(institutionId ? { institution: institutionId } : {}) }) }),
  downloadImportTemplate: () => downloadFile('/fdrs/import/template/', 'fdr-import-template.csv'),
  downloadImportErrors: (file: File, institutionId?: string) =>
    fetch('/api/fdrs/import/?report=csv', { method: 'POST', credentials: 'include', body: fileForm({ file, ...(institutionId ? { institution: institutionId } : {}) }), headers: { 'X-CSRFToken': decodeURIComponent((document.cookie.match(/csrftoken=([^;]+)/) ?? [])[1] ?? '') } })
      .then(async (response) => {
        if (!response.ok) throw new Error('The error report could not be created.');
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = url;
        link.download = 'fdr-import-errors.csv';
        link.click();
        URL.revokeObjectURL(url);
      }),
  listRequests: (status?: string) => api<{ results: RequestRecord[] }>(`/requests/${status ? `?status=${status}` : ''}`).then((d) => d.results),
  maturity: () => api<{ results: FDR[] }>('/maturity/?page_size=200').then((d) => d.results.map(mapFdr)),
};
