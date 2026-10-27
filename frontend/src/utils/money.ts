/** Converts a rupee amount typed by a user (for example "5,00,000.50") into integer paise, exactly. */
export function rupeesToPaise(input: string): number {
  const cleaned = input.replace(/,/g, '').trim();
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) {
    throw new Error('Enter the amount in rupees, with at most two decimal places (for example 500000 or 500000.50).');
  }
  const [whole = '0', fraction = ''] = cleaned.split('.');
  const paise = Number(whole) * 100 + Number((fraction + '00').slice(0, 2));
  if (paise <= 0) throw new Error('Amount must be greater than zero.');
  return paise;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const date = value.length === 10 ? new Date(`${value}T00:00:00`) : new Date(value);
  return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('en-IN') : '—';
}

export function formatBytes(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${Math.round(bytes / 1024 / 1024)} MB` : `${Math.round(bytes / 1024)} KB`;
}

export function todayIso(): string {
  return new Date().toLocaleDateString('en-CA');
}
