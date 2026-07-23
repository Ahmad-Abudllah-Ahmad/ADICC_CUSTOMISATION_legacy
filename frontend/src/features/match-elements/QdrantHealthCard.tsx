// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// QdrantHealthCard — surfaces the "vector DB not running" UX gap on
// /match-elements. Polls GET /api/v1/match_elements/qdrant/health and,
// when Qdrant is unreachable, renders a clear two-button card:
//
//   * "Install Qdrant (no Docker)" — calls POST /qdrant/install which
//     downloads the official binary from GitHub Releases and spawns it
//     locally. Mirrors the existing converter-install pattern from
//     /takeoff (BIM page) so the user gets a familiar one-click flow.
//   * "Refresh status" — re-probes /qdrant/health.
//
// We deliberately do NOT mention Docker anywhere in the user-facing
// copy. Every other heavy dependency in OpenConstructionERP runs
// without Docker (Postgres→SQLite, Redis→memory, MinIO→local fs); the
// native binary brings Qdrant in line with that policy.

import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Loader2,
  RefreshCw,
  Server,
} from 'lucide-react';
import clsx from 'clsx';

import { useToastStore } from '@/stores/useToastStore';
import {
  fetchQdrantHealth,
  installQdrantNative,
  type QdrantHealth,
} from './api';

interface Props {
  /** When true, the card renders even when Qdrant is healthy (used for
   *  diagnostics / smoke tests). Default behaviour is "only render when
   *  unreachable", which keeps the page uncluttered on a healthy box. */
  alwaysShow?: boolean;
  /** Optional callback fired the moment Qdrant flips to reachable.
   *  Lets the parent page invalidate catalogue / vector-readiness
   *  queries so the rest of the UI catches up. */
  onReachable?: () => void;
}

export function QdrantHealthCard({ alwaysShow = false, onReachable }: Props) {
  const { t } = useTranslation();
  const { addToast } = useToastStore();
  const queryClient = useQueryClient();
  const [isInstalling, setIsInstalling] = useState(false);

  const healthQ = useQuery<QdrantHealth>({
    queryKey: ['match-qdrant-health'],
    queryFn: fetchQdrantHealth,
    // Re-poll every 30s when down so a user who fixed the issue
    // elsewhere (started a manual qdrant from terminal etc.) sees the
    // card disappear without a hard refresh. We do not poll when
    // reachable — no point hitting the backend on a stable box.
    refetchInterval: (q) => (q.state.data?.reachable ? false : 30_000),
    staleTime: 5_000,
  });

  const handleRefresh = useCallback(async () => {
    const next = await healthQ.refetch();
    if (next.data?.reachable && onReachable) onReachable();
  }, [healthQ, onReachable]);

  const handleInstall = useCallback(async () => {
    setIsInstalling(true);
    try {
      const result = await installQdrantNative();
      // Push the install result straight into the React Query cache so
      // the card flips to "running" without waiting for the next poll.
      queryClient.setQueryData(['match-qdrant-health'], result);
      if (result.reachable) {
        addToast({
          type: 'success',
          title: t(
            'qdrant_health.install_success_title',
            'Vector database ready',
          ),
          message: t(
            'qdrant_health.install_success_body',
            'Qdrant is now running locally. You can install catalogues.',
          ),
        });
        // Invalidate downstream queries so the catalogues panel and
        // readiness pill refresh — they consult Qdrant directly.
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ['catalogues-v3'] }),
          queryClient.invalidateQueries({
            queryKey: ['match-vector-readiness'],
          }),
        ]);
        if (onReachable) onReachable();
      } else {
        addToast({
          type: 'warning',
          title: t(
            'qdrant_health.install_partial_title',
            'Vector database installed',
          ),
          message:
            result.message ||
            t(
              'qdrant_health.install_partial_body',
              'Installation finished but the server did not bind to the port. Click Refresh in a few seconds.',
            ),
        });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      addToast({
        type: 'error',
        title: t(
          'qdrant_health.install_failed_title',
          'Vector database install failed',
        ),
        message: msg,
      });
    } finally {
      setIsInstalling(false);
    }
  }, [addToast, onReachable, queryClient, t]);

  // Loading / error before first response → suppress to avoid flashing
  // a placeholder. The page already has the readiness pill which carries
  // its own loading state.
  if (healthQ.isLoading || !healthQ.data) {
    return null;
  }

  const health = healthQ.data;

  if (health.reachable && !alwaysShow) {
    return null;
  }

  // Reachable diagnostic state (alwaysShow=true) — small green pill.
  if (health.reachable) {
    return (
      <div
        role="status"
        className="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/30 px-4 py-3 flex items-center gap-3"
      >
        <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-300 shrink-0" />
        <div className="text-sm">
          <div className="font-semibold text-emerald-900 dark:text-emerald-100">
            {t('qdrant_health.up_title', 'Vector database is running')}
          </div>
          <div className="text-xs text-emerald-800 dark:text-emerald-200">
            {health.url}
          </div>
        </div>
      </div>
    );
  }

  return (
    <section
      role="alert"
      aria-live="polite"
      className="rounded-xl border border-rose-200 dark:border-rose-800 bg-rose-50/70 dark:bg-rose-950/30 shadow-sm"
    >
      <div className="px-4 py-4 flex items-start gap-3">
        <div className="shrink-0 w-10 h-10 rounded-lg bg-rose-100 dark:bg-rose-900/50 border border-rose-200 dark:border-rose-800 flex items-center justify-center">
          <Server className="w-5 h-5 text-rose-700 dark:text-rose-200" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-rose-900 dark:text-rose-100 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            {t(
              'qdrant_health.down_title',
              'Vector database is not running',
            )}
          </h3>
          <p className="mt-1 text-xs text-rose-800 dark:text-rose-200 leading-relaxed">
            {health.message}
          </p>
          {health.install_hint && (
            <p className="mt-1 text-xs text-rose-700/90 dark:text-rose-300/90 leading-relaxed">
              {health.install_hint}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {!health.installed && (
              <button
                type="button"
                onClick={handleInstall}
                disabled={isInstalling}
                className={clsx(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold',
                  'bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-60 disabled:cursor-not-allowed',
                  'transition-colors shadow-sm',
                )}
                aria-label={t(
                  'qdrant_health.install_aria',
                  'Install the native Qdrant binary (no Docker)',
                )}
              >
                {isInstalling ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Download className="w-3.5 h-3.5" />
                )}
                {isInstalling
                  ? t('qdrant_health.install_in_progress', 'Installing…')
                  : t(
                      'qdrant_health.install_button',
                      'Install Qdrant (no Docker)',
                    )}
              </button>
            )}
            <button
              type="button"
              onClick={handleRefresh}
              disabled={healthQ.isFetching || isInstalling}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium',
                'border border-rose-300 dark:border-rose-700 bg-white/70 dark:bg-rose-950/40',
                'text-rose-800 dark:text-rose-100 hover:bg-white dark:hover:bg-rose-900/50',
                'disabled:opacity-60 transition-colors',
              )}
            >
              <RefreshCw
                className={clsx(
                  'w-3.5 h-3.5',
                  healthQ.isFetching && 'animate-spin',
                )}
              />
              {t('qdrant_health.refresh_button', 'Refresh status')}
            </button>
            {health.download_url && !health.installed && (
              <a
                href={health.download_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs underline text-rose-700 dark:text-rose-200 hover:text-rose-900 dark:hover:text-rose-50"
              >
                {t(
                  'qdrant_health.download_manual',
                  'Manual download',
                )}
              </a>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
