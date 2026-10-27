export function formatINR(paise: number): string {
 if (!Number.isSafeInteger(paise)) throw new Error('Amount must be an integer number of paise');
 return new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:2, minimumFractionDigits:2 }).format(paise / 100);
}
export function formatRole(role: string): string { return role.split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' '); }
