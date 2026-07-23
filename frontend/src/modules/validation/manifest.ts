// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { ShieldCheck } from 'lucide-react';
import type { ModuleManifest } from '../_types';

// internal id: ddc-lineage:a17f93c4-validation-02
export const manifest: ModuleManifest = {
  id: 'validation',
  name: 'validation.title',
  description: 'modules.validation_desc',
  version: '1.0.0',
  icon: ShieldCheck,
  category: 'tools',
  defaultEnabled: true,
  routes: [],
  navItems: [],
};
