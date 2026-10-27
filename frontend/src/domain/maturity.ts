import type { FDRStatus } from '../types';
export type MaturityState = 'Active' | 'Nearing Maturity' | 'Matured' | 'Overdue';
export function daysToMaturity(maturityDate: string, today = new Date()): number { const target = new Date(`${maturityDate}T00:00:00`); const current = new Date(today.getFullYear(),today.getMonth(),today.getDate()); return Math.ceil((target.getTime()-current.getTime())/86400000); }
export function deriveMaturityState(maturityDate: string, thresholds: number[] = [90,60,30], today = new Date(), hasOutcome = false): MaturityState {
 const days = daysToMaturity(maturityDate,today); if (days < 0 && !hasOutcome) return 'Overdue'; if (days <= 0) return 'Matured'; if (thresholds.some((threshold) => days <= threshold)) return 'Nearing Maturity'; return 'Active';
}
export function isMaturityStatus(status: FDRStatus): boolean { return ['Active','Nearing Maturity','Matured'].includes(status); }
