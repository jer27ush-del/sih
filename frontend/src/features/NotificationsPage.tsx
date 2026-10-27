import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { notificationApi } from '../api/notificationApi';
import { errorText } from '../api/client';
import { formatDateTime } from '../utils/money';
import { Banner, Empty, PageHeading } from './common';
import { FdrDetail } from './fdr/FdrDetail';

const UUID = /\/fdrs\/([0-9a-f-]{36})/i;

export function NotificationsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [openFdr, setOpenFdr] = useState<string | null>(null);
  const [error, setError] = useState('');
  const items = useQuery({ queryKey: ['notifications'], queryFn: notificationApi.list });
  const visible = (items.data ?? []).filter((n) => !unreadOnly || !n.read);
  const unread = (items.data ?? []).filter((n) => !n.read).length;

  async function markRead(id: string) {
    try {
      await notificationApi.markRead(id);
      await queryClient.invalidateQueries({ queryKey: ['notifications'] });
    } catch (err) {
      setError(errorText(err));
    }
  }

  function open(link: string) {
    const fdr = link.match(UUID);
    if (fdr) return setOpenFdr(fdr[1] ?? null);
    navigate(link.startsWith('/requests') ? '/release' : '/fdrs');
  }

  return (
    <section>
      <PageHeading crumb="Notifications" title="Notification inbox" />
      {error && <Banner tone="error">{error}</Banner>}
      <div className="panel">
        <div className="panel-heading">
          <div><h2>Your alerts</h2><p>Reminders, queries and decisions. Mandatory alerts cannot be switched off.</p></div>
          <span className="count-pill">{unread} unread</span>
        </div>
        <label className="checkbox-row" style={{ padding: '0 20px' }}><input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} /> Show unread only</label>
        {visible.length === 0 && <Empty title="Your inbox is clear" />}
        {visible.map((n) => (
          <div className="quick-link-disabled" style={{ padding: '14px 20px' }} key={n.id}>
            <span className="quick-icon">•</span>
            <span><b style={{ fontWeight: n.read ? 400 : 700 }}>{n.message}</b><small>{formatDateTime(n.sentAt)}</small></span>
            {!n.read && <button className="button secondary" onClick={() => void markRead(n.id)}>Mark read</button>}
            <button className="button secondary" onClick={() => open(n.link)}>Open</button>
          </div>
        ))}
      </div>
      {openFdr && <FdrDetail fdrId={openFdr} onClose={() => setOpenFdr(null)} />}
    </section>
  );
}
