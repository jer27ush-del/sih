import { api } from './client';
import type { AuditEntry, Page } from '../types';

export const auditApi = {
  /** One page of the audit history. The server limits what officers may see. */
  page: (params: { entity?: string; action?: string; page?: number }) => {
    const query = new URLSearchParams({ page: String(params.page ?? 1) });
    if (params.entity) query.set('entity', params.entity);
    if (params.action) query.set('action', params.action);
    return api<Page<AuditEntry>>(`/audit-logs/?${query}`);
  },
};
