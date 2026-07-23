// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Sparkles, ExternalLink, ArrowRight, Send } from 'lucide-react';

interface BackendModulePageProps {
  moduleKey: string;
  apiPath: string;
  iconClass?: string;
  highlights?: string[];
}

export function BackendModulePage({
  moduleKey,
  apiPath,
  highlights,
}: BackendModulePageProps) {
  const { t } = useTranslation();
  const title = t(`backend_modules.${moduleKey}.title`, {
    defaultValue: moduleKey
      .split('_')
      .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
      .join(' '),
  });
  const description = t(`backend_modules.${moduleKey}.desc`, {
    defaultValue: 'Backend API is live. The interactive UI for this module is in progress.',
  });
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="relative overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700 bg-gradient-to-br from-violet-500 via-violet-600 to-blue-600 text-white px-8 py-10">
        <div className="absolute -top-20 -right-20 h-64 w-64 rounded-full bg-white/10 blur-3xl" />
        <div className="relative">
          <div className="flex items-center gap-3 mb-4">
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 backdrop-blur-sm">
              <Sparkles size={22} strokeWidth={2.25} />
            </span>
            <span className="inline-flex items-center rounded-full bg-white/15 text-white text-[11px] font-semibold uppercase tracking-wide px-2.5 py-0.5">
              {t('backend_modules.badge', { defaultValue: 'Backend API live' })}
            </span>
          </div>
          <h1 className="text-3xl font-semibold leading-tight">{title}</h1>
          <p className="mt-2 text-white/90 text-base max-w-2xl">{description}</p>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4 mt-6">
        <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3">
            {t('backend_modules.endpoints_title', { defaultValue: 'API endpoints' })}
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
            {t('backend_modules.endpoints_body', {
              defaultValue: 'All routes are mounted and authenticated. Browse the OpenAPI spec to explore models, schemas, and try requests.',
            })}
          </p>
          <a
            href="/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-violet-600 dark:text-violet-400 hover:underline"
          >
            {t('backend_modules.open_api', { defaultValue: 'Open API docs' })}
            <ExternalLink size={14} />
          </a>
          <div className="mt-3 rounded-md bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-3 py-2 font-mono text-xs text-slate-700 dark:text-slate-300">
            GET /api/v1/{apiPath}/
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3">
            {t('backend_modules.ui_title', { defaultValue: 'UI status' })}
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
            {t('backend_modules.ui_body', {
              defaultValue: 'The interactive frontend for this module is on the roadmap. Tell us your priority - we ship most-requested modules first, for free.',
            })}
          </p>
          <Link
            to="/modules/developer-guide"
            className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-violet-600 dark:text-violet-400 hover:underline"
          >
            {t('backend_modules.dev_guide', { defaultValue: 'Build the UI yourself' })}
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>

      {highlights && highlights.length > 0 && (
        <div className="mt-6 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3">
            {t('backend_modules.what_works', { defaultValue: "What's already working" })}
          </h2>
          <ul className="space-y-1.5">
            {highlights.map((h) => (
              <li
                key={h}
                className="text-sm text-slate-700 dark:text-slate-300 flex items-start gap-2"
              >
                <span className="text-emerald-600 dark:text-emerald-400 mt-0.5">✓</span>
                {h}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6 rounded-2xl border border-violet-200 dark:border-violet-900/60 bg-violet-50/50 dark:bg-violet-950/30 p-5 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {t('backend_modules.cta_title', { defaultValue: 'Need this UI soon?' })}
          </h2>
          <p className="text-sm text-slate-700 dark:text-slate-300 mt-0.5">
            {t('backend_modules.cta_body', {
              defaultValue: 'Drop us a line - popular requests get built for free.',
            })}
          </p>
        </div>
        <a
          href="https://datadrivenconstruction.io/contact-support/"
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 inline-flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors"
        >
          <Send size={14} />
          {t('backend_modules.contact', { defaultValue: 'Contact us' })}
        </a>
      </div>
    </div>
  );
}
