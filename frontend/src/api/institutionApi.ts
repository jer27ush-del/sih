import { api, fetchAll } from './client';
import type { Institution } from '../types';

export type InstitutionInput = Pick<Institution, 'code' | 'name' | 'state' | 'contactName' | 'email' | 'phone'>;

/** The server identifies the acting user from the session, so no actor arguments are sent. */
export const institutionApi = {
  list: () => fetchAll<Institution>('/institutions/'),
  save: (input: InstitutionInput, id?: string) =>
    id
      ? api<Institution>(`/institutions/${id}/`, { method: 'PATCH', body: input })
      : api<Institution>('/institutions/', { method: 'POST', body: input }),
  deactivate: (id: string) => api<Institution>(`/institutions/${id}/`, { method: 'PATCH', body: { status: 'Inactive' } }),
};
