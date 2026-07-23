// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { lazy } from 'react';
import { Layers3 } from 'lucide-react';
import type { ModuleManifest } from '../_types';

/**
 * Estimating methodologies - the data-driven markup-cascade engine.
 *
 * Two routes: the hub (`/methodologies`, templates gallery + installed list)
 * and the editor (`/methodologies/:methodologyId`). The sidebar entry is a
 * STATIC row in the `grp_estimating` group (Sidebar.tsx), like `/boq` and
 * `/assemblies`, so `navItems` here stays empty - the Sidebar only pulls
 * dynamic module navItems for its `grp_*` group ids, never for the legacy
 * group strings a manifest declares, so a dynamic entry would render nowhere.
 *
 * The active-methodology switch lives in project Settings
 * (MethodologyActiveCard), not in the sidebar.
 */
const MethodologiesPage = lazy(() =>
  import('@/features/methodology/MethodologiesPage').then((m) => ({
    default: m.MethodologiesPage,
  })),
);

const MethodologyEditorPage = lazy(() =>
  import('@/features/methodology/MethodologyEditorPage').then((m) => ({
    default: m.MethodologyEditorPage,
  })),
);

export const manifest: ModuleManifest = {
  id: 'methodology',
  name: 'nav.methodologies',
  description: 'modules.methodology_desc',
  version: '1.0.0',
  icon: Layers3,
  category: 'estimation',
  defaultEnabled: true,
  depends: ['boq'],
  routes: [
    {
      path: '/methodologies',
      title: 'Estimating methodologies',
      component: MethodologiesPage,
    },
    {
      path: '/methodologies/:methodologyId',
      title: 'Methodology editor',
      component: MethodologyEditorPage,
    },
  ],
  navItems: [],
  searchEntries: [
    {
      label: 'Estimating methodologies',
      path: '/methodologies',
      keywords: [
        'methodology',
        'methodologies',
        'markup',
        'cascade',
        'overhead',
        'profit',
        'vat',
        'smr',
        'template',
        'estimate',
        'estimating',
        'funding source',
        'dimension',
      ],
    },
  ],
  translations: {
    en: {
      'nav.methodologies': 'Methodologies',
      'modules.methodology_desc':
        'Data-driven estimating: install or build a markup cascade (works vs equipment split, base sets, sequential percentage steps and VAT), with analytical dimensions and funding sources.',
    },
  },
};
