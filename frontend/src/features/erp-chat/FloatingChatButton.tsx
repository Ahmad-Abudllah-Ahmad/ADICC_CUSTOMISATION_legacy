// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Floating chat button — always visible in the bottom-right corner.
 *
 * Hides itself on routes that already host a full chat experience or where
 * the user isn't authenticated (login, onboarding), so we don't duplicate or
 * leak the assistant before the user has accepted terms.
 *
 * The unread badge is driven by `useFloatingChatStore.unreadCount`, which the
 * panel bumps every time the assistant produces a message while the panel is
 * closed. Opening the panel resets the counter.
 */

import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MessageCircle } from 'lucide-react';
import { useFloatingChatStore } from './useFloatingChat';
import { useAuthStore } from '@/stores/useAuthStore';

const HIDE_ON_PREFIXES = [
  '/chat',          // full-page chat — don't duplicate
  '/login',
  '/onboarding',
  '/license-request',
];

export function FloatingChatButton() {
  const { t } = useTranslation();
  const location = useLocation();
  const isOpen = useFloatingChatStore((s) => s.isOpen);
  const unreadCount = useFloatingChatStore((s) => s.unreadCount);
  const toggle = useFloatingChatStore((s) => s.toggle);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const accessToken = useAuthStore((s) => s.accessToken);

  const hidden = useMemo(() => {
    // Require either explicit isAuthenticated OR the presence of a token in
    // storage — both flags are set after loadFromStorage(), but tests that
    // poke sessionStorage directly only flip the token, not isAuthenticated,
    // until the next React render cycle.
    if (!isAuthenticated && !accessToken) return true;
    return HIDE_ON_PREFIXES.some((p) => location.pathname.startsWith(p));
  }, [location.pathname, isAuthenticated, accessToken]);

  if (hidden) return null;

  const label = t('chat.floating.open', { defaultValue: 'Ask AI about your data' });
  const badgeLabel = t('chat.floating.unread_badge', {
    defaultValue: '{{count}} new',
    count: unreadCount,
  });

  return (
    <button
      type="button"
      onClick={toggle}
      data-testid="floating-chat-button"
      aria-label={label}
      aria-expanded={isOpen}
      title={label}
      className={[
        'fixed bottom-4 right-4 z-50',
        'h-14 w-14 rounded-full',
        'flex items-center justify-center',
        'text-white shadow-lg',
        'bg-gradient-to-br from-oe-blue to-oe-blue-dark',
        'transition-all duration-200 ease-out',
        'hover:scale-105 hover:shadow-xl',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue focus-visible:ring-offset-2',
        'active:scale-95',
      ].join(' ')}
      style={{
        // Fallback for tokens that may not exist in every theme — keep the
        // button visible even if --oe-blue-dark hasn't been defined yet.
        background:
          'linear-gradient(135deg, var(--oe-blue, #2563eb) 0%, var(--oe-blue-dark, #1d4ed8) 100%)',
      }}
    >
      <MessageCircle size={24} strokeWidth={2} aria-hidden />
      {unreadCount > 0 && !isOpen && (
        <span
          aria-label={badgeLabel}
          className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold flex items-center justify-center border-2 border-white"
        >
          {unreadCount > 9 ? '9+' : unreadCount}
        </span>
      )}
    </button>
  );
}

export default FloatingChatButton;
