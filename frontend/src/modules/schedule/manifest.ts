// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { CalendarDays } from 'lucide-react';
import type { ModuleManifest } from '../_types';

// internal-id ddc-lineage:a17f93c4-schedule-02
export const manifest: ModuleManifest = {
  id: 'schedule',
  name: 'schedule.title',
  description: 'modules.schedule_desc',
  version: '1.0.0',
  icon: CalendarDays,
  category: 'planning',
  defaultEnabled: true,
  routes: [],
  navItems: [],
};
