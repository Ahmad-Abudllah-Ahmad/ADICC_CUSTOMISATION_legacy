// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Typed client for the /api/v1/retrieval/* surface.

import { apiGet } from '@/shared/lib/api';
import type { RetrievalQuery, RetrievalResponse } from './types';

const BASE = '/v1/retrieval';

/** Run a faceted, ranked search across a project's record. */
export const searchRecords = (projectId: string, query: RetrievalQuery) => {
  const params = new URLSearchParams({ project_id: projectId });
  for (const [key, value] of Object.entries(query)) {
    if (value && value.trim() !== '') {
      params.set(key, value.trim());
    }
  }
  return apiGet<RetrievalResponse>(`${BASE}/search?${params.toString()}`);
};
