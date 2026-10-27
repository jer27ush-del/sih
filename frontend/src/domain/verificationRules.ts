import type { AppSettings, Document, FDR, Institution, Verification } from '../types';
export type RuleFlag = 'pass' | 'warning' | 'fail';
export interface VerificationContext { fdr: FDR; institution: Institution | undefined; documents: Document[]; existingFdrs: FDR[]; settings: AppSettings; bankConfirmation: Verification | undefined; today?: Date }
export type VerificationRule = 'required_fields' | 'duplicate_reference' | 'date_logic' | 'tenure_validity' | 'amount_range' | 'document_quality' | 'bank_confirmation';
export type RuleResults = Record<VerificationRule, RuleFlag>;
export function runVerificationRules(context: VerificationContext): RuleResults {
 const {fdr, institution, documents, existingFdrs, settings, bankConfirmation, today = new Date()} = context;
 const validDoc = documents.some((doc) => doc.active && doc.sizeBytes > 0 && settings.allowedDocumentTypes.includes(doc.mimeType));
 const duplicate = existingFdrs.some((item) => item.id !== fdr.id && item.fdrNumber.trim().toLowerCase() === fdr.fdrNumber.trim().toLowerCase() && item.bank.trim().toLowerCase() === fdr.bank.trim().toLowerCase());
 const issue = new Date(`${fdr.issueDate}T00:00:00`); const maturity = new Date(`${fdr.maturityDate}T00:00:00`); const current = new Date(today.getFullYear(),today.getMonth(),today.getDate());
 const tenure = Math.round((maturity.getTime()-issue.getTime())/86400000);
 return {
  required_fields: fdr.fdrNumber.trim() && fdr.bank.trim() && fdr.branch.trim() && fdr.institutionId && institution && fdr.amountPaise > 0 && fdr.issueDate && fdr.maturityDate && validDoc ? 'pass':'fail',
  duplicate_reference: duplicate ? 'fail':'pass',
  date_logic: maturity > issue && issue <= current ? 'pass':'warning',
  tenure_validity: tenure >= settings.minimumTenureDays ? 'pass':'warning',
  amount_range: fdr.amountPaise >= settings.amountLimitsPaise.min && fdr.amountPaise <= settings.amountLimitsPaise.max ? 'pass':'warning',
  document_quality: documents.some((doc) => doc.active && doc.sizeBytes > 0 && settings.allowedDocumentTypes.includes(doc.mimeType)) ? 'pass':'warning',
  bank_confirmation: bankConfirmation?.bankConfirmedOn && bankConfirmation.bankReference ? 'pass':'fail'
 };
}
