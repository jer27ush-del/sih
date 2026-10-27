import type { Role } from '../types';
export type Action = 'view_fdrs' | 'register_fdr' | 'import_fdrs' | 'manage_institutions' | 'review_fdr' | 'reply_query' | 'submit_request' | 'recommend_release' | 'approve_release' | 'change_settings' | 'view_reports' | 'view_audit_logs' | 'view_limited_audit_logs';
const matrix: Record<Role, readonly Action[]> = {
 institution_user:['view_fdrs','register_fdr','import_fdrs','reply_query','submit_request','view_reports'],
 scrutiny_officer:['view_fdrs','review_fdr','recommend_release','view_reports','view_limited_audit_logs'],
 administrator:['view_fdrs','register_fdr','import_fdrs','manage_institutions','review_fdr','submit_request','recommend_release','approve_release','change_settings','view_reports','view_audit_logs'],
 auditor:['view_fdrs','view_reports','view_audit_logs']
};
export function can(role: Role, action: Action): boolean { return matrix[role].includes(action); }
export function visibleInstitutionIds(role: Role, ownInstitutionId: string | null, allIds: string[]): string[] { return role === 'institution_user' ? (ownInstitutionId ? [ownInstitutionId] : []) : allIds; }
export function canApproveRelease(input: { role: Role; userId: string; submittedBy: string; recommendedBy: string | null }): boolean {
 return input.role === 'administrator' && input.userId !== input.submittedBy && input.userId !== input.recommendedBy;
}
