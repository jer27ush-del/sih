import { api, fetchAll } from './client';
import type { FDR, FdrDetail } from '../types';

/** The API sends `heldInFavourOfAicte`; the UI type uses the document's spelling. */
export function mapFdr(raw: FDR & { heldInFavourOfAicte?: boolean }): FDR {
  return { ...raw, heldInFavourOfAICTE: raw.heldInFavourOfAicte ?? raw.heldInFavourOfAICTE };
}

export interface FdrFilters {
  search?: string;
  status?: string;
  reviewFlag?: boolean;
  ordering?: string;
}

export const fdrApi = {
  /** Every FDR the signed-in user may see (used by dashboards and institution pages). */
  list: async (): Promise<FDR[]> => (await fetchAll<FDR>('/fdrs/')).map(mapFdr),

  /** One page of the register, filtered on the server. */
  async page(filters: FdrFilters, page: number): Promise<{ count: number; results: FDR[] }> {
    const params = new URLSearchParams({ page: String(page) });
    if (filters.search) params.set('search', filters.search);
    if (filters.status) params.set('status', filters.status);
    if (filters.reviewFlag !== undefined) params.set('review_flag', String(filters.reviewFlag));
    if (filters.ordering) params.set('ordering', filters.ordering);
    const data = await api<{ count: number; results: FDR[] }>(`/fdrs/?${params}`);
    return { count: data.count, results: data.results.map(mapFdr) };
  },

  async get(id: string): Promise<FdrDetail> {
    const raw = await api<FdrDetail & { heldInFavourOfAicte?: boolean }>(`/fdrs/${id}/`);
    return { ...mapFdr(raw), ...raw, heldInFavourOfAICTE: raw.heldInFavourOfAicte ?? raw.heldInFavourOfAICTE } as FdrDetail;
  },
};
