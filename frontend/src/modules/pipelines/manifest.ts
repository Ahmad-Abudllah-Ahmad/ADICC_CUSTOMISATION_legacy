// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { lazy } from 'react';
import { Workflow } from 'lucide-react';
import type { ModuleManifest } from '../_types';

/**
 * Pipeline Builder — visual node-graph automation editor (BETA, Phase 1).
 *
 * Cloned from the EAC block-editor stack (`@xyflow/react` v12) — no new
 * dependency. Route `/pipelines`, advanced-only, registered via the central
 * registry (no `App.tsx` / `Sidebar.tsx` edit — routes resolve through
 * `useModuleRouteElements`, the sidebar nav item through `getModuleNavItems`).
 *
 * NOTE: the shared `ModuleNavItem` contract only carries
 * `labelKey/to/icon/group/advancedOnly`, and the Sidebar derives the module
 * id from `labelKey.split('.')[1]` — so the labelKey is `nav.pipelines` to
 * resolve `isModuleEnabled('pipelines')`. The requested `badge:'BETA'` and
 * `data-tour="pipelines"` are not part of that contract; the BETA label is
 * surfaced in the page itself and `data-tour="pipelines"` is set on the page
 * root for onboarding instead.
 */
export const manifest: ModuleManifest = {
  id: 'pipelines',
  name: 'Pipeline Builder',
  description:
    'Visually compose construction automations: triggers, data sources, transforms, validation gates and outputs as a node graph.',
  version: '0.1.0',
  icon: Workflow,
  category: 'tools',
  // Enabled by default so the statically-listed "Pipeline Builder" sidebar
  // entry (Automation & AI group, advanced-only) resolves to a mounted
  // route. `useModuleRouteElements` only mounts a module's routes when
  // `isModuleEnabled(id)` is true; with this false the nav link 404'd (the
  // sidebar item is NOT gated by module-enabled, so the link showed while
  // the route was absent). Every other statically-listed feature module
  // (schedule, validation, tendering, cost-benchmark, …) is defaultEnabled
  // too. BETA is still communicated via the in-page BetaBanner.
  defaultEnabled: true,
  depends: ['validation'],
  routes: [
    {
      path: '/pipelines',
      title: 'Pipeline Builder',
      component: lazy(() => import('@/features/pipelines/PipelinesPage')),
    },
  ],
  navItems: [
    {
      labelKey: 'nav.pipelines',
      to: '/pipelines',
      icon: Workflow,
      group: 'ai',
      advancedOnly: true,
    },
  ],
  searchEntries: [
    {
      label: 'Pipeline Builder',
      path: '/pipelines',
      keywords: [
        'pipeline',
        'automation',
        'workflow',
        'node graph',
        'flow',
        'trigger',
        'no-code',
        'orchestration',
      ],
    },
  ],
  translations: {
    en: {
      'nav.pipelines': 'Pipeline Builder',
    },
    es: {
      'nav.pipelines': 'Constructor de pipelines',
    },
    de: {
      'nav.pipelines': 'Pipeline-Builder',
    },
    fr: {
      'nav.pipelines': 'Générateur de pipelines',
    },
    ru: {
      'nav.pipelines': 'Конструктор конвейеров',
    },
  },
};
