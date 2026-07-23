// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// API client for File Approvals (W8).
//
// Endpoints (mounted at /api/v1/file-approvals):
//   GET    /v1/file-approvals/?project_id={uuid}&status={s}
//   POST   /v1/file-approvals/
//   GET    /v1/file-approvals/{id}/
//   POST   /v1/file-approvals/{id}/steps/{stepId}/decide/
//   POST   /v1/file-approvals/{id}/withdraw/
//   GET    /v1/file-approvals/{id}/stamped/
//   GET    /v1/file-approvals/stamp-templates/?project_id={uuid}
//   POST   /v1/file-approvals/stamp-templates/

import { apiGet, apiPost } from '@/shared/lib/api';
import type {
  ApprovalDecidePayload,
  ApprovalWorkflow,
  ApprovalWorkflowCreatePayload,
  StampTemplate,
  StampTemplatePayload,
} from './types';

const BASE = '/v1/file-approvals';

export async function listWorkflows(
  projectId: string,
  statusFilter?: string,
): Promise<ApprovalWorkflow[]> {
  const params = new URLSearchParams({ project_id: projectId });
  if (statusFilter) params.set('status', statusFilter);
  return apiGet<ApprovalWorkflow[]>(`${BASE}/?${params.toString()}`);
}

export async function getWorkflow(workflowId: string): Promise<ApprovalWorkflow> {
  return apiGet<ApprovalWorkflow>(`${BASE}/${workflowId}/`);
}

export async function submitForApproval(
  payload: ApprovalWorkflowCreatePayload,
): Promise<ApprovalWorkflow> {
  return apiPost<ApprovalWorkflow, ApprovalWorkflowCreatePayload>(
    `${BASE}/`,
    payload,
  );
}

export async function decideStep(
  workflowId: string,
  stepId: string,
  payload: ApprovalDecidePayload,
): Promise<ApprovalWorkflow> {
  return apiPost<ApprovalWorkflow, ApprovalDecidePayload>(
    `${BASE}/${workflowId}/steps/${stepId}/decide/`,
    payload,
  );
}

export async function withdrawWorkflow(
  workflowId: string,
): Promise<ApprovalWorkflow> {
  return apiPost<ApprovalWorkflow>(`${BASE}/${workflowId}/withdraw/`, {});
}

export async function listStampTemplates(
  projectId?: string | null,
): Promise<StampTemplate[]> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  const qs = params.toString();
  return apiGet<StampTemplate[]>(`${BASE}/stamp-templates/${qs ? `?${qs}` : ''}`);
}

export async function createStampTemplate(
  payload: StampTemplatePayload,
): Promise<StampTemplate> {
  return apiPost<StampTemplate, StampTemplatePayload>(
    `${BASE}/stamp-templates/`,
    payload,
  );
}
