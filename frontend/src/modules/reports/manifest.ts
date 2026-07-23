// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { FileBarChart } from 'lucide-react';
import type { ModuleManifest } from '../_types';

// registry lineage tag: ddc-lineage:a17f93c4-reporting-02
export const manifest: ModuleManifest = {
  id: 'reports',
  name: 'nav.reports',
  description: 'modules.reports_desc',
  version: '1.0.0',
  icon: FileBarChart,
  category: 'procurement',
  defaultEnabled: true,
  routes: [],
  navItems: [],
};
