// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useTranslation } from 'react-i18next';
import { ArrowUpRight, Newspaper } from 'lucide-react';

/**
 * ArticleNewsCard - a compact promo card pinned near the foot of the sidebar
 * that links out to the featured long-form article on the uberization of
 * construction. It reuses the sidebar card frame (same width, radius, border,
 * shadow and entrance animation) and opens the article in a new tab.
 *
 * This used to embed a YouTube video; it now points at the written article
 * instead, so the whole card is a single external link with a title, a short
 * subtitle and an external-link affordance. It keeps the existing
 * `sidebar.video_news.*` i18n keys for the title/subtitle.
 */

const ARTICLE_URL = 'https://adicc-uae.com';

export function ArticleNewsCard() {
  const { t } = useTranslation();

  const title = t('sidebar.video_news.title', { defaultValue: 'Uberization of Construction' });
  const subtitle = t('sidebar.video_news.subtitle', {
    defaultValue: 'Open data, transparency, and the idea behind the platform',
  });
  const read = t('sidebar.video_news.read', { defaultValue: 'Read the article' });

  return (
    <a
      href={ARTICLE_URL}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="sidebar-article-news"
      aria-label={`${title} - ${read}`}
      className="group mx-2 mb-2 flex items-start gap-2.5 overflow-hidden rounded-lg border border-border-light bg-surface-elevated px-3 py-2.5 shadow-sm ring-1 ring-black/5 transition-shadow animate-card-in hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60 dark:ring-white/5"
    >
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-oe-blue/10 text-oe-blue dark:text-sky-300">
        <Newspaper size={13} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block break-words text-[13px] font-bold leading-tight text-content-primary">
          {title}
        </span>
        <span className="mt-1 block text-[11px] leading-snug text-content-secondary">
          {subtitle}
        </span>
        <span className="mt-1.5 flex items-center gap-1 text-[11px] font-semibold text-blue-600 dark:text-sky-300">
          {read}
          <ArrowUpRight size={11} className="shrink-0" />
        </span>
      </span>
    </a>
  );
}
