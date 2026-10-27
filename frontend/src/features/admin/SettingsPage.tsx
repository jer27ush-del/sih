import { useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi } from '../../api/authApi';
import { portalApi } from '../../api/portalApi';
import { errorText } from '../../api/client';
import { useAuth } from '../../auth';
import { can } from '../../domain/permissions';
import { formatRole } from '../../utils/format';
import { Banner, PageHeading } from '../common';

const list = (value: string) => value.split(',').map((item) => item.trim()).filter(Boolean);

export function SettingsPage() {
  const { user } = useAuth();
  const isAdmin = can(user?.role ?? 'auditor', 'change_settings');
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ['settings'], queryFn: portalApi.settings, enabled: isAdmin });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' });

  async function saveSettings() {
    setError('');
    setNotice('');
    try {
      const patch = {
        maturityThresholds: list(draft.thresholds ?? settings.data?.maturityThresholds.join(',') ?? '').map(Number),
        minimumTenureDays: Number(draft.tenure ?? settings.data?.minimumTenureDays),
        documentMaxBytes: Number(draft.maxBytes ?? settings.data?.documentMaxBytes),
        banks: list(draft.banks ?? settings.data?.banks.join(',') ?? ''),
        categories: list(draft.categories ?? settings.data?.categories.join(',') ?? ''),
        escalationContacts: list(draft.contacts ?? settings.data?.escalationContacts.join(',') ?? ''),
        overdueEscalationDays: Number(draft.overdue ?? settings.data?.overdueEscalationDays),
      };
      await portalApi.saveSettings(patch);
      setDraft({});
      setNotice('Settings saved. The change is recorded in the audit log.');
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
      await queryClient.invalidateQueries({ queryKey: ['settings-options'] });
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setError('');
    setNotice('');
    if (passwords.next !== passwords.confirm) return setError('The new passwords do not match.');
    try {
      await authApi.changePassword(passwords.current, passwords.next);
      setPasswords({ current: '', next: '', confirm: '' });
      setNotice('Password changed.');
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <PageHeading crumb="Settings & Profile" title="Settings & Profile" />
      {error && <Banner tone="error">{error}</Banner>}
      {notice && <Banner tone="info">{notice}</Banner>}

      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-heading"><div><h2>Profile</h2><p>Your account on this portal.</p></div></div>
          <div className="session-card"><div className="avatar large">{user?.name.split(' ').map((p) => p[0]).slice(0, 2).join('')}</div><div><strong>{user?.name}</strong><span>{user?.email}</span><small>{formatRole(user?.role ?? '')}</small></div></div>
        </section>
        <form className="panel" onSubmit={(e) => void changePassword(e)}>
          <div className="panel-heading"><div><h2>Change password</h2><p>At least 10 characters, not a common password.</p></div></div>
          <div style={{ padding: 20, display: 'grid', gap: 12 }}>
            <div className="field"><label htmlFor="pw-current">Current password</label><input id="pw-current" type="password" autoComplete="current-password" value={passwords.current} onChange={(e) => setPasswords({ ...passwords, current: e.target.value })} /></div>
            <div className="field"><label htmlFor="pw-new">New password</label><input id="pw-new" type="password" autoComplete="new-password" value={passwords.next} onChange={(e) => setPasswords({ ...passwords, next: e.target.value })} /></div>
            <div className="field"><label htmlFor="pw-confirm">Confirm new password</label><input id="pw-confirm" type="password" autoComplete="new-password" value={passwords.confirm} onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} /></div>
            <button className="button primary" disabled={!passwords.current || !passwords.next}>Change password</button>
          </div>
        </form>
      </div>

      {isAdmin && settings.data && (
        <section className="panel" style={{ marginTop: 18 }}>
          <div className="panel-heading"><div><h2>System configuration</h2><p>Administrator only. Every change is audited.</p></div></div>
          <form style={{ padding: 20 }} onSubmit={(e) => { e.preventDefault(); void saveSettings(); }}>
            <div className="form-grid">
              <Field id="thresholds" label="Reminder thresholds (days, comma-separated)" value={draft.thresholds ?? settings.data.maturityThresholds.join(',')} onChange={(v) => setDraft({ ...draft, thresholds: v })} />
              <Field id="tenure" label="Minimum tenure (days)" type="number" value={draft.tenure ?? String(settings.data.minimumTenureDays)} onChange={(v) => setDraft({ ...draft, tenure: v })} />
              <Field id="maxBytes" label="Maximum document size (bytes)" type="number" value={draft.maxBytes ?? String(settings.data.documentMaxBytes)} onChange={(v) => setDraft({ ...draft, maxBytes: v })} />
              <Field id="overdue" label="Days after maturity before escalation" type="number" value={draft.overdue ?? String(settings.data.overdueEscalationDays)} onChange={(v) => setDraft({ ...draft, overdue: v })} />
              <Field id="banks" label="Banks (comma-separated)" value={draft.banks ?? settings.data.banks.join(',')} onChange={(v) => setDraft({ ...draft, banks: v })} />
              <Field id="categories" label="Deposit categories (comma-separated)" value={draft.categories ?? settings.data.categories.join(',')} onChange={(v) => setDraft({ ...draft, categories: v })} />
              <Field id="contacts" label="Escalation email addresses (comma-separated)" value={draft.contacts ?? settings.data.escalationContacts.join(',')} onChange={(v) => setDraft({ ...draft, contacts: v })} />
            </div>
            <button className="button primary" style={{ marginTop: 18 }}>Save settings</button>
          </form>
        </section>
      )}
    </section>
  );
}

function Field({ id, label, value, onChange, type = 'text' }: { id: string; label: string; value: string; onChange: (v: string) => void; type?: string }) {
  return <div className="field"><label htmlFor={id}>{label}</label><input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)} /></div>;
}
