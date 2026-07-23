// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Route wrapper for the model-issue register (BCF, the BIM Collaboration
 * Format). Resolves the active project and renders the register, which lists,
 * opens, comments on and imports or exports 3D model coordination topics with
 * their captured viewpoints and snapshots. The in-viewer "raise issue here"
 * capture is wired separately from the model viewer through useBcfCapture.
 */
import { useQuery } from '@tanstack/react-query';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { apiGet } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { BcfIssuesPanel } from './BcfIssuesPanel';

export function BcfPage() {
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Array<{ id: string; name: string }>>('/v1/projects/'),
  });
  const projectId = activeProjectId || projects[0]?.id || '';
  return (
    <RequiresProject>{projectId ? <BcfIssuesPanel projectId={projectId} /> : null}</RequiresProject>
  );
}

export default BcfPage;
