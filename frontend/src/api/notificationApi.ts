import { api, fetchAll } from './client';
import type { NotificationItem } from '../types';

export const notificationApi = {
  list: () => fetchAll<NotificationItem>('/notifications/'),
  markRead: (id: string) => api<NotificationItem>(`/notifications/${id}/`, { method: 'PATCH', body: { read: true } }),
};
