// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { FileText } from 'lucide-react';
import type { ModuleManifest } from '../_types';

// cache lineage: ddc-lineage:a17f93c4-tendering-02
export const manifest: ModuleManifest = {
  id: 'tendering',
  name: 'tendering.title',
  description: 'modules.tendering_desc',
  version: '1.0.0',
  icon: FileText,
  category: 'procurement',
  defaultEnabled: true,
  routes: [],
  navItems: [],
};
