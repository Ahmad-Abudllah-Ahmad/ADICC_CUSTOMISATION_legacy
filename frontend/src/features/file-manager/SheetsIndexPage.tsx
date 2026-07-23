// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import clsx from 'clsx';
import { FileText, Search, Check } from 'lucide-react';
import {
  Badge,
  Breadcrumb,
  Card,
  DateDisplay,
  EmptyState,
  SkeletonTable,
} from '@/shared/ui';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { apiGet } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

/* ── API types — mirror SheetResponse from backend ───────────────────── */

interface SheetRow {
  id: string;
  project_id: string;
  document_id: string;
  page_number: number;
  sheet_number: string | null;
  sheet_title: string | null;
  discipline: string | null;
  revision: string | null;
  revision_date: string | null;
  scale: string | null;
  is_current: boolean;
  previous_version_id: string | null;
  thumbnail_path: string | null;
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

interface ProjectLite {
  id: string;
  name: string;
}

/* ── Helpers ─────────────────────────────────────────────────────────── */

function disciplineVariant(d: string | null): 'neutral' | 'blue' | 'success' | 'warning' | 'error' {
  if (!d) return 'neutral';
  // Stable pseudo-hash → keeps the same colour across renders.
  let h = 0;
  for (let i = 0; i < d.length; i += 1) {
    h = (h * 31 + d.charCodeAt(i)) >>> 0;
  }
  const pool = ['blue', 'success', 'warning', 'neutral'] as const;
  return pool[h % pool.length] ?? 'neutral';
}

const inputCls =
  'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

/* ── Main page ───────────────────────────────────────────────────────── */

export function SheetsIndexPage() {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams<{ projectId: string }>();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);

  const [searchQuery, setSearchQuery] = useState('');
  const [disciplineFilter, setDisciplineFilter] = useState<string | null>(null);

  // Pick a working project id (route → store → first available).
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<ProjectLite[]>('/v1/projects/'),
    staleTime: 5 * 60_000,
  });

  const projectId = routeProjectId || activeProjectId || projects[0]?.id || '';
  const projectName = projects.find((p) => p.id === projectId)?.name || '';

  const { data: sheets = [], isLoading } = useQuery({
    queryKey: ['sheets', projectId],
    queryFn: () =>
      apiGet<SheetRow[]>(
        `/v1/documents/sheets/?project_id=${encodeURIComponent(projectId)}&limit=500`,
      ),
    enabled: !!projectId,
  });

  const { data: disciplines = [] } = useQuery({
    queryKey: ['sheet-disciplines', projectId],
    queryFn: () =>
      apiGet<string[]>(
        `/v1/documents/sheets/disciplines/?project_id=${encodeURIComponent(projectId)}`,
      ),
    enabled: !!projectId,
  });

  /* Client-side filter (discipline chip + free-text search). Sheets are
     usually <500 per project, so filtering in memory keeps the UI snappy
     without extra round-trips. */
  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return sheets.filter((s) => {
      if (disciplineFilter && s.discipline !== disciplineFilter) return false;
      if (!q) return true;
      const hay = [
        s.sheet_number,
        s.sheet_title,
        s.discipline,
        s.revision,
        s.scale,
      ]
        .filter((x): x is string => Boolean(x))
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  }, [sheets, disciplineFilter, searchQuery]);

  return (
    <div className="w-full animate-fade-in">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { label: t('nav.dashboard', { defaultValue: 'Dashboard' }), to: '/' },
          { label: t('files.title', { defaultValue: 'Files' }), to: '/files' },
          ...(projectName ? [{ label: projectName }] : []),
          { label: t('sheets.title', { defaultValue: 'Sheets' }) },
        ]}
        className="mb-4"
      />

      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-content-primary">
            {t('sheets.page_title', { defaultValue: 'Drawing Sheets' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('sheets.subtitle', {
              defaultValue:
                'Indexed drawing sheets across project documents - filter by discipline or search by number, title, revision.',
            })}
          </p>
        </div>
      </div>

      {!projectId && <RequiresProject>{null}</RequiresProject>}

      {projectId && (
        <>
          {/* Discipline filter chips */}
          {disciplines.length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setDisciplineFilter(null)}
                className={clsx(
                  'inline-flex items-center h-7 px-3 rounded-full text-xs font-medium transition-colors',
                  disciplineFilter === null
                    ? 'bg-oe-blue text-white'
                    : 'bg-surface-secondary text-content-secondary hover:bg-surface-tertiary',
                )}
              >
                {t('sheets.filter_all_disciplines', { defaultValue: 'All disciplines' })}
                <span className="ms-1.5 tabular-nums opacity-70">{sheets.length}</span>
              </button>
              {disciplines.map((d) => {
                const count = sheets.filter((s) => s.discipline === d).length;
                const active = disciplineFilter === d;
                return (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDisciplineFilter(d)}
                    className={clsx(
                      'inline-flex items-center h-7 px-3 rounded-full text-xs font-medium transition-colors',
                      active
                        ? 'bg-oe-blue text-white'
                        : 'bg-surface-secondary text-content-secondary hover:bg-surface-tertiary',
                    )}
                  >
                    {d}
                    <span className="ms-1.5 tabular-nums opacity-70">{count}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Search */}
          <div className="mb-6 flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary"
              />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('sheets.search_placeholder', {
                  defaultValue: 'Search by sheet #, title, revision…',
                })}
                aria-label={t('sheets.search_placeholder', {
                  defaultValue: 'Search by sheet #, title, revision…',
                })}
                className={inputCls + ' pl-9'}
              />
            </div>
          </div>

          {/* Table */}
          {isLoading ? (
            <SkeletonTable rows={6} columns={7} />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<FileText size={28} strokeWidth={1.5} />}
              title={
                searchQuery || disciplineFilter
                  ? t('sheets.no_results', { defaultValue: 'No matching sheets' })
                  : t('sheets.no_sheets', { defaultValue: 'No sheets indexed yet' })
              }
              description={
                searchQuery || disciplineFilter
                  ? t('sheets.no_results_hint', {
                      defaultValue:
                        'Try adjusting the search box or pick a different discipline.',
                    })
                  : t('sheets.no_sheets_hint', {
                      defaultValue:
                        'Upload a multi-page PDF drawing set to the Files module - each page becomes a sheet here automatically.',
                    })
              }
            />
          ) : (
            <>
              <p className="mb-3 text-sm text-content-tertiary">
                {t('sheets.showing_count', {
                  defaultValue: '{{count}} sheets',
                  count: filtered.length,
                })}
              </p>

              <Card padding="none" className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead className="sticky top-0 z-10 bg-surface-secondary/95 backdrop-blur-sm">
                    <tr className="text-2xs font-medium text-content-tertiary uppercase tracking-wider">
                      <th className="text-start px-4 py-2.5 border-b border-border-light font-medium">
                        {t('sheets.col_number', { defaultValue: 'Sheet #' })}
                      </th>
                      <th className="text-start px-4 py-2.5 border-b border-border-light font-medium">
                        {t('sheets.col_title', { defaultValue: 'Title' })}
                      </th>
                      <th className="text-start px-4 py-2.5 border-b border-border-light font-medium">
                        {t('sheets.col_discipline', { defaultValue: 'Discipline' })}
                      </th>
                      <th className="text-start px-4 py-2.5 border-b border-border-light font-medium">
                        {t('sheets.col_revision', { defaultValue: 'Rev' })}
                      </th>
                      <th className="text-start px-4 py-2.5 border-b border-border-light font-medium">
                        {t('sheets.col_issue_date', { defaultValue: 'Issue Date' })}
                      </th>
                      <th className="text-start px-4 py-2.5 border-b border-border-light font-medium">
                        {t('sheets.col_scale', { defaultValue: 'Scale' })}
                      </th>
                      <th className="text-center px-4 py-2.5 border-b border-border-light font-medium">
                        {t('sheets.col_current', { defaultValue: 'Current?' })}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((s) => (
                      <tr
                        key={s.id}
                        className="hover:bg-surface-secondary/50 transition-colors border-b border-border-light last:border-b-0"
                      >
                        <td className="px-4 py-3 font-mono text-content-primary whitespace-nowrap">
                          {s.sheet_number ?? `p.${s.page_number}`}
                        </td>
                        <td className="px-4 py-3 text-content-primary">
                          {s.sheet_title ?? (
                            <span className="text-content-quaternary">&mdash;</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {s.discipline ? (
                            <Badge variant={disciplineVariant(s.discipline)} size="sm">
                              {s.discipline}
                            </Badge>
                          ) : (
                            <span className="text-content-quaternary">&mdash;</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {s.revision ? (
                            <Badge variant="neutral" size="sm">
                              {s.revision}
                            </Badge>
                          ) : (
                            <span className="text-content-quaternary">&mdash;</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-content-secondary">
                          {s.revision_date ? (
                            <span
                              title={new Date(s.revision_date).toLocaleString()}
                            >
                              <DateDisplay value={s.revision_date} format="relative" />
                            </span>
                          ) : (
                            <span className="text-content-quaternary">&mdash;</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-content-secondary tabular-nums">
                          {s.scale ?? <span className="text-content-quaternary">&mdash;</span>}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {s.is_current ? (
                            <Check
                              size={16}
                              className="inline-block text-semantic-success"
                              aria-label={t('sheets.is_current_yes', {
                                defaultValue: 'Current revision',
                              })}
                            />
                          ) : (
                            <span
                              className="text-content-quaternary"
                              aria-label={t('sheets.is_current_no', {
                                defaultValue: 'Superseded',
                              })}
                            >
                              &mdash;
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
