// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * <RequiresProject> — project-gating wrapper.
 *
 * Renders children only when an active project is selected. Otherwise
 * surfaces a single, consistent EmptyState that points the user to the
 * Projects page. Before this wrapper, ~30 pages reinvented this gate
 * inline with slightly different wording (UX audit blocker).
 *
 * Resolution chain mirrors what every page already did manually:
 *   1. ``:projectId`` route param (when the page is mounted under a
 *      project-scoped route)
 *   2. ``useProjectContextStore`` ``activeProjectId`` (header switcher)
 *
 * Usage:
 *   <RequiresProject>
 *     <MyProjectScopedContent />
 *   </RequiresProject>
 *
 *   // Override the default description (e.g. module-specific hint):
 *   <RequiresProject emptyHint={t('rfi.select_project_hint')}>
 *     ...
 *   </RequiresProject>
 */

import type { ReactNode } from 'react';
import { FolderOpen } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@/shared/ui/EmptyState';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

export interface RequiresProjectProps {
  children: ReactNode;
  /** Optional override for the description shown in the empty state. */
  emptyHint?: string;
  /** Optional override for the title shown in the empty state. */
  emptyTitle?: string;
}

export function RequiresProject({ children, emptyHint, emptyTitle }: RequiresProjectProps) {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams<{ projectId?: string }>();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const projectId = routeProjectId || activeProjectId || '';

  if (projectId) {
    return <>{children}</>;
  }

  return (
    <EmptyState
      icon={<FolderOpen size={28} strokeWidth={1.5} />}
      title={
        emptyTitle ??
        t('requiresProject.title', { defaultValue: 'No project selected' })
      }
      description={
        emptyHint ??
        t('requiresProject.description', {
          defaultValue:
            'Pick a project from the header to continue, or open the Projects page to create or select one.',
        })
      }
      action={
        <Link
          to="/projects"
          className="inline-flex h-10 items-center justify-center rounded-md bg-oe-blue px-4 text-sm font-medium text-white hover:bg-oe-blue/90 transition-colors"
        >
          {t('requiresProject.cta', { defaultValue: 'Open Projects' })}
        </Link>
      }
    />
  );
}
