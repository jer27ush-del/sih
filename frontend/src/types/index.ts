export type Role = 'institution_user' | 'scrutiny_officer' | 'administrator' | 'auditor';
export type RecordStatus = 'Active' | 'Inactive';
export type FDRStatus = 'Submitted' | 'Under Verification' | 'Query Raised' | 'Corrected' | 'Verified' | 'Active' | 'Nearing Maturity' | 'Matured' | 'Renewed' | 'Release Requested' | 'Released / Closed' | 'Rejected';
export type RuleFlag = 'pass' | 'warning' | 'fail';

export interface Institution { id: string; code: string; name: string; state: string; contactName: string; email: string; phone: string; status: RecordStatus; fdrCount?: number; createdAt: string; updatedAt: string }
export interface User { id: string; name: string; email: string; role: Role; institutionId: string | null; status: RecordStatus; lastLogin: string | null }

/** An FDR as returned by the API (list and detail). Fields added for the detail view are optional. */
export interface FDR {
  id: string; fdrNumber: string; institutionId: string; institutionCode?: string; institutionName?: string;
  bank: string; branch: string; amountPaise: number; issueDate: string; maturityDate: string;
  interestRate: number; payoutType: 'cumulative' | 'periodic'; category: string; lienMarked: boolean;
  heldInFavourOfAICTE: boolean; status: FDRStatus; statusNote?: string; parentFdrId: string | null;
  reviewFlag: boolean; daysToMaturity?: number; bankConfirmed?: boolean; bankConfirmedOn?: string | null;
  bankReference?: string | null; createdAt: string; updatedAt: string;
}
export interface FdrDocument { id: string; originalName: string; mimeType: string; sizeBytes: number; sha256: string; version: number; uploadedByName: string; uploadedAt: string; active: boolean; scanStatus: string }
export interface VerificationRun { id: string; ruleResults: Record<string, RuleFlag>; runByName: string; createdAt: string }
export interface BankConfirmation { id: string; confirmedOn: string; mode: string; reference: string; confirmedByName: string; createdAt: string }
export interface QueryRecord { id: string; fdrId: string; message: string; reply: string; status: 'open' | 'resolved'; raisedByName: string; raisedAt: string; repliedAt: string | null; resolvedAt: string | null; daysPending: number }
export interface RequestRecord { id: string; fdrId: string; fdrNumber: string; requestType: 'renewal' | 'release'; releaseKind: '' | 'at_maturity' | 'premature'; reason: string; status: 'Submitted' | 'Recommended' | 'Approved' | 'Rejected' | 'Completed'; previousStatus: string; bankTermsNoted: boolean; submittedByName: string; recommendedByName: string | null; recommendedAt: string | null; recommendationNote: string; decidedByName: string | null; decidedAt: string | null; actionTaken: string; createdAt: string }
export interface FdrDetail extends FDR {
  documents: FdrDocument[]; verificationRuns: VerificationRun[]; bankConfirmations: BankConfirmation[];
  queries: QueryRecord[]; requests: RequestRecord[]; renewals: { id: string; fdrNumber: string; status: string }[];
  reminders: { kind: string; sentAt: string }[];
}
export interface NotificationItem { id: string; type: string; message: string; link: string; read: boolean; sentAt: string }
export interface AuditEntry { id: number; timestamp: string; actorLabel: string; action: string; entity: string; entityId: string; oldValue: unknown; newValue: unknown; ipAddress: string | null }
export interface SystemSettings { maturityThresholds: number[]; escalationContacts: string[]; overdueEscalationDays: number; queryFollowupDays: number; documentMaxBytes: number; allowedDocumentTypes: string[]; banks: string[]; categories: string[]; minimumTenureDays: number; amountMinPaise: number; amountMaxPaise: number }
export interface SettingsOptions { banks: string[]; categories: string[]; allowedDocumentTypes: string[]; documentMaxBytes: number; minimumTenureDays: number; amountLimitsPaise: { min: number; max: number }; maturityThresholds: number[] }
export interface DashboardSummary {
  totalFdrs: number; totalDepositPaise: number; activeFdrs: number; maturing30Days: number; maturing60Days: number; maturing90Days: number;
  overdueUnactioned: number; pendingVerification: number; openQueries: number; flaggedForReview: number; pendingRequests: number;
  statusBreakdown: { status: string; count: number }[]; recentSubmissions: FDR[]; upcomingMaturities: FDR[];
}
export interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }

/** Shapes used by the pure domain rules in src/domain (also exercised by unit tests). */
export interface AppSettings { maturityThresholds: number[]; escalationContacts: string[]; documentMaxBytes: number; allowedDocumentTypes: string[]; banks: string[]; categories: string[]; minimumTenureDays: number; amountLimitsPaise: { min: number; max: number } }
export interface Document { id: string; fdrId: string; fileName: string; mimeType: string; sizeBytes: number; version: number; uploadedBy: string; uploadedAt: string; active: boolean }
export interface Verification { id: string; fdrId: string; ruleResults: Record<string, 'pass' | 'warning' | 'fail'>; officerId: string | null; bankConfirmedOn: string | null; bankReference: string | null; decision: 'Verified' | 'Rejected' | null; reason: string | null }
