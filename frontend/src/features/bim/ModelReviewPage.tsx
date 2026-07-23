// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Model Review - a focused, site-facing surface for walking a 3D model and
 * raising coordination issues against it.
 *
 * It deliberately reuses the shared <BIMViewer> (so it inherits the fast
 * streaming tile loader) and the <BcfIssuesPanel> register, and wires the two
 * together with a live capture bridge: pick an element, hit "Raise issue
 * here", and the issue records the camera, the selection and a snapshot of
 * exactly what is on screen. Unlike the full BIM workspace it drops the upload
 * / filmstrip / cost panels - this page is for reviewing, not authoring.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Cuboid, PanelRightClose, PanelRightOpen } from 'lucide-react';

import { BcfIssuesPanel } from '@/features/bcf';
import type { Topic, Viewpoint } from '@/features/bcf/api';
import { listAnchors } from '@/features/geo-hub/api';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { apiGet } from '@/shared/lib/api';
import { BIMViewer } from '@/shared/ui/BIMViewer';
import type { BIMElementData, ElementManager, SelectionManager } from '@/shared/ui/BIMViewer';
import { metresToModelUnits as unitsToModelScale } from '@/shared/ui/BIMViewer/geoLocate';
import { buildElementQuestion } from '@/shared/ui/BIMViewer/elementQuestion';
import { OfflineModelButton } from '@/shared/ui/BIMViewer/OfflineModelButton';
import type { SceneManager } from '@/shared/ui/BIMViewer/SceneManager';
import { useFloatingChatStore } from '@/features/erp-chat/useFloatingChat';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

import { makeBcfBridge } from './bcfBridge';
import { restoreBcfViewpoint } from './restoreViewpoint';
import { useModelViewerData } from './useModelViewerData';

function ModelReviewInner({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [activeModelId, setActiveModelId] = useState<string | null>(null);
  const [issuesOpen, setIssuesOpen] = useState(true);

  const { models, activeModel, elements, geometryUrl, isLoadingModels, isLoadingElements } =
    useModelViewerData(projectId, activeModelId);

  // Project geo anchor + model units power the viewer's "locate me" pin. The
  // control hides itself when the project has no anchor.
  const geoAnchorQuery = useQuery({
    queryKey: ['geo-hub', 'anchors', projectId],
    queryFn: () => listAnchors(projectId),
    enabled: Boolean(projectId),
    staleTime: 60_000,
  });
  const geoAnchor = useMemo(() => {
    const a = geoAnchorQuery.data?.[0];
    if (!a) return null;
    const lat = Number(a.lat);
    const lon = Number(a.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return { lat, lon };
  }, [geoAnchorQuery.data]);
  const modelUnitsScale = useMemo(() => {
    const meta = (activeModel?.metadata ?? null) as Record<string, unknown> | null;
    const units =
      (meta?.units as unknown) ??
      ((meta?.metadata as Record<string, unknown> | undefined)?.units as unknown);
    return unitsToModelScale(units);
  }, [activeModel]);

  // Auto-pick the first renderable model so the page is useful on open.
  useEffect(() => {
    if (activeModelId || models.length === 0) return;
    const firstReady =
      models.find((m) => m.status === 'ready' || m.status === 'degraded') ?? models[0];
    if (firstReady) setActiveModelId(firstReady.id);
  }, [models, activeModelId]);

  // A stable BCF bridge that reads the live scene + selection through refs, so
  // its identity never changes (and never re-renders the issues panel) even as
  // the camera moves and the selection changes.
  const sceneRef = useRef<SceneManager | null>(null);
  const guidsRef = useRef<string[]>([]);
  const [sceneReady, setSceneReady] = useState(false);
  const bridge = useMemo(
    () =>
      makeBcfBridge(
        () => sceneRef.current,
        () => guidsRef.current,
      ),
    [],
  );

  const handleSceneReady = useCallback((scene: SceneManager | null) => {
    sceneRef.current = scene;
    setSceneReady(!!scene);
  }, []);

  // "Ask AI about this element" - seed the shared assistant with a full
  // element-context prompt. Same behaviour as on the main BIM page.
  const handleAskAiAboutElement = useCallback((element: BIMElementData) => {
    useFloatingChatStore.getState().seedPrompt(buildElementQuestion(element));
  }, []);

  const handleSelectionChange = useCallback((_ids: string[], els: BIMElementData[]) => {
    // BCF wants stable ids (IFC GlobalId / RVT UniqueId); fall back to the
    // mesh ref, then the row id, and drop anything empty.
    guidsRef.current = els
      .map((e) => e.stable_id ?? e.mesh_ref ?? e.id)
      .filter((v): v is string => !!v);
  }, []);

  // Map a viewpoint's stable ids (IFC GlobalId / RVT UniqueId / mesh ref) back
  // to the internal element id the scene managers key on, so restoring a
  // viewpoint can select exactly the elements the issue was raised against.
  const stableIdToElementId = useMemo(() => {
    const map = new Map<string, string>();
    for (const el of elements) {
      if (el.id) map.set(el.id, el.id);
      if (el.stable_id) map.set(el.stable_id, el.id);
      if (el.mesh_ref) map.set(el.mesh_ref, el.id);
    }
    return (stableId: string): string | undefined => map.get(stableId);
  }, [elements]);

  // "Zoom to issue" / coordination walk-through: fly the scene to a saved BCF
  // viewpoint and select its elements. The element + selection managers come
  // from the live window.__oeBim bridge the viewer installs.
  const handleOpenViewpoint = useCallback(
    (_topic: Topic, vp: Viewpoint) => {
      const scene = sceneRef.current;
      if (!scene) return;
      const bim = (
        window as unknown as {
          __oeBim?: {
            elementManager: ElementManager | null;
            selectionManager: SelectionManager | null;
          };
        }
      ).__oeBim;
      void restoreBcfViewpoint(vp, {
        scene,
        elementManager: bim?.elementManager ?? null,
        selectionManager: bim?.selectionManager ?? null,
        stableIdToElementId,
      });
    },
    [stableIdToElementId],
  );

  return (
    <div className="flex h-full flex-col">
      {/* Header: title + model picker + issues toggle */}
      <div className="flex items-center gap-3 border-b border-border-light px-4 py-2.5">
        <Cuboid size={18} className="shrink-0 text-oe-blue" />
        <h1 className="text-sm font-semibold text-content-primary">
          {t('nav.model_review', { defaultValue: 'Model Review' })}
        </h1>
        <select
          className="ms-2 max-w-[280px] rounded-lg border border-border-light bg-surface-primary px-2.5 py-1.5 text-sm text-content-secondary"
          value={activeModelId ?? ''}
          onChange={(e) => setActiveModelId(e.target.value || null)}
          disabled={isLoadingModels || models.length === 0}
        >
          {models.length === 0 && (
            <option value="">
              {isLoadingModels
                ? t('common.loading', { defaultValue: 'Loading...' })
                : t('bim.no_models', { defaultValue: 'No models yet' })}
            </option>
          )}
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
        <div className="flex-1" />
        {activeModelId && <OfflineModelButton modelId={activeModelId} />}
        <button
          type="button"
          onClick={() => setIssuesOpen((v) => !v)}
          className="flex items-center gap-1.5 rounded-lg border border-border-light px-2.5 py-1.5 text-sm text-content-secondary hover:bg-surface-hover"
          aria-pressed={issuesOpen}
        >
          {issuesOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
          {t('bim.issues', { defaultValue: 'Issues' })}
        </button>
      </div>

      {/* Body: viewer + issues dock */}
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          {activeModelId ? (
            <BIMViewer
              modelId={activeModelId}
              projectId={projectId}
              modelName={activeModel?.name}
              modelMetadata={activeModel?.metadata ?? null}
              elements={elements}
              geometryUrl={geometryUrl}
              geoAnchor={geoAnchor}
              metresToModelUnits={modelUnitsScale}
              isLoading={isLoadingElements}
              onSelectionChange={handleSelectionChange}
              onSceneReady={handleSceneReady}
              onAskAiAboutElement={handleAskAiAboutElement}
              className="h-full"
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <Cuboid size={40} className="mx-auto mb-3 text-content-quaternary" />
                <p className="text-sm text-content-tertiary">
                  {t('bim.select_model_prompt', {
                    defaultValue: 'Select a model to view',
                  })}
                </p>
              </div>
            </div>
          )}
        </div>

        {issuesOpen && (
          <div className="flex w-[380px] shrink-0 flex-col border-s border-border-light bg-surface-primary">
            <BcfIssuesPanel
              projectId={projectId}
              bimModelId={activeModelId}
              bridge={sceneReady ? bridge : undefined}
              onOpenViewpoint={sceneReady ? handleOpenViewpoint : undefined}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/** Route wrapper: resolve the active project, then render the review surface. */
export function ModelReviewPage() {
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Array<{ id: string; name: string }>>('/v1/projects/'),
  });
  const projectId = activeProjectId || projects[0]?.id || '';
  return (
    <RequiresProject>
      {projectId ? <ModelReviewInner projectId={projectId} /> : null}
    </RequiresProject>
  );
}

export default ModelReviewPage;
