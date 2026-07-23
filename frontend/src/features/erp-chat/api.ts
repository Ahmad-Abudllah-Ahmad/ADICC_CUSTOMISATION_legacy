// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { apiGet, apiPost, apiDelete } from '@/shared/lib/api';
import type { AdminStats, ChatSession, FeedbackResponse } from './types';

export async function fetchChatSessions(): Promise<{ items: ChatSession[]; total: number }> {
  return apiGet('/v1/erp_chat/sessions/');
}

export async function createChatSession(projectId?: string): Promise<ChatSession> {
  return apiPost('/v1/erp_chat/sessions/', { project_id: projectId, title: 'New Chat' });
}

export async function fetchSessionMessages(sessionId: string): Promise<unknown[]> {
  return apiGet(`/v1/erp_chat/sessions/${sessionId}/messages/`);
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  return apiDelete(`/v1/erp_chat/sessions/${sessionId}/`);
}

// ── T8: thumbs feedback + admin observability ────────────────────────────

/**
 * Submit (or flip) a thumbs up / down rating on an assistant message.
 *
 * The backend is idempotent per `(message_id, user)` — re-calling with a
 * different `rating` updates the existing row in place.
 */
export async function submitFeedback(
  messageId: string,
  rating: 1 | -1,
  comment?: string,
): Promise<FeedbackResponse> {
  return apiPost(`/v1/erp_chat/messages/${messageId}/feedback/`, { rating, comment });
}

/**
 * Fetch the admin observability rollup (token spend, feedback, cache hit
 * rate, daily breakdown, top thumbed-down prompts). Requires the
 * `erp_chat.admin` permission (manager+); 403 propagates as a thrown error.
 */
export async function getAdminStats(windowDays = 30): Promise<AdminStats> {
  return apiGet(`/v1/erp_chat/admin/stats/?window_days=${windowDays}`);
}
