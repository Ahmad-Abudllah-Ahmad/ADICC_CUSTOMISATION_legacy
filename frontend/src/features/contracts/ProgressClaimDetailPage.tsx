// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// ProgressClaimDetailPage — full detail view for a single progress claim.
//
// Route: /projects/:projectId/contracts/claims/:claimId
//
// Shows the claim header (totals + status pipeline), the editable line-item
// table, the "Populate from progress observations" action (Gap I bridge), and
// the lifecycle transition buttons (Submit → Approve → Certify → Mark paid /
// Reject) gated by status + role. Certify and Mark-paid are MANAGER-gated on
// the backend, so the affordances are hidden for editors/viewers.

import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Send,
  CheckCircle2,
  XCircle,
  DollarSign,
  Download,
} from 'lucide-react';

import {
  Button,
  Card,
  Badge,
  Breadcrumb,
  DismissibleInfo,
  IntroRichText,
  RecoveryCard,
  SkeletonTable,
} from '@/shared/ui';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { useAuthStore } from '@/stores/useAuthStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  getProgressClaim,
  listClaimLines,
  submitClaim,
  approveClaim,
  certifyClaim,
  rejectClaim,
  markClaimPaid,
  type ProgressClaimItem,
  type ClaimStatus,
} from './api';
import { PopulatePreviewModal } from './PopulatePreviewModal';
import { ProgressClaimLineTable } from './ProgressClaimLineTable';
import { AIAApplicationPanel } from './AIAApplicationPanel';
import { projectsApi } from '@/features/projects/api';

const CLAIM_STATUS_VARIANT: Record<
  ClaimStatus,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  draft: 'neutral',
  submitted: 'blue',
  approved: 'success',
  certified: 'success',
  paid: 'success',
  rejected: 'error',
};

const CLAIM_STATUS_LABELS: Record<ClaimStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  approved: 'Approved',
  certified: 'Certified',
  paid: 'Paid',
  rejected: 'Rejected',
};

function claimStatusLabel(t: TFunction, status: ClaimStatus): string {
  return t(`contracts.claim_status_${status}`, {
    defaultValue: CLAIM_STATUS_LABELS[status] ?? status,
  });
}

function toNum(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === 'string' ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}

/** Lines are only editable while the claim is draft or submitted. */
function isEditable(status: ClaimStatus): boolean {
  return status === 'draft' || status === 'submitted';
}

export function ProgressClaimDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { projectId, claimId } = useParams<{ projectId: string; claimId: string }>();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const userRole = useAuthStore((s) => s.userRole);
  const canManageClaim = userRole === 'admin' || userRole === 'manager';

  const [populateOpen, setPopulateOpen] = useState(false);

  const claimQ = useQuery<ProgressClaimItem>({
    queryKey: ['contracts', 'claim', claimId],
    queryFn: () => getProgressClaim(claimId as string),
    enabled: !!claimId,
  });

  const linesQ = useQuery({
    queryKey: ['contracts', 'claim-lines', claimId],
    queryFn: () => listClaimLines(claimId as string),
    enabled: !!claimId,
  });

  // Load the project so we can country-gate the AIA G702/G703 panel. The flag
  // is computed server-side (US/CA/AU only); the panel renders only when true,
  // and the AIA endpoints independently 404 elsewhere.
  const projectQ = useQuery({
    queryKey: ['projects', 'detail', projectId],
    queryFn: () => projectsApi.get(projectId as string),
    enabled: !!projectId,
  });

  const claim = claimQ.data;
  const aiaEligible = projectQ.data?.is_aia_eligible === true;

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['contracts', 'claim', claimId] });
    qc.invalidateQueries({ queryKey: ['contracts', 'claim-lines', claimId] });
    qc.invalidateQueries({ queryKey: ['contracts', 'claims'] });
  };

  const transitionMut = (
    fn: (id: string) => Promise<ProgressClaimItem>,
    okMsg: string,
  ) =>
    useMutation({
      mutationFn: () => fn(claimId as string),
      onSuccess: () => {
        invalidate();
        addToast({ type: 'success', title: okMsg });
      },
      onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
    });

  const submit = transitionMut(
    submitClaim,
    t('contracts.claim_submitted', { defaultValue: 'Claim submitted' }),
  );
  const approve = transitionMut(
    approveClaim,
    t('contracts.claim_approved', { defaultValue: 'Claim approved' }),
  );
  const certify = transitionMut(
    certifyClaim,
    t('contracts.claim_certified', { defaultValue: 'Claim certified' }),
  );
  const reject = transitionMut(
    rejectClaim,
    t('contracts.claim_rejected', { defaultValue: 'Claim rejected' }),
  );
  const paid = transitionMut(
    markClaimPaid,
    t('contracts.claim_paid', { defaultValue: 'Claim marked paid' }),
  );

  const contractsHref = projectId
    ? `/projects/${projectId}/contracts`
    : '/contracts';

  if (claimQ.isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonTable rows={6} columns={4} />
      </div>
    );
  }

  if (claimQ.isError || !claim) {
    return (
      <RecoveryCard error={claimQ.error} onRetry={() => void claimQ.refetch()} />
    );
  }

  const editable = isEditable(claim.status);

  return (
    <div className="space-y-5" data-testid="progress-claim-detail">
      <Breadcrumb
        items={[
          ...(projectQ.data
            ? [{ label: projectQ.data.name, to: `/projects/${projectQ.data.id}` }]
            : []),
          { label: t('nav.contracts', { defaultValue: 'Contracts' }), to: contractsHref },
          { label: claim.claim_number || t('contracts.claim', { defaultValue: 'Claim' }) },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <Link
              to={contractsHref}
              className="text-content-tertiary hover:text-oe-blue"
              aria-label={t('common.back', { defaultValue: 'Back' })}
            >
              <ArrowLeft size={18} />
            </Link>
            <h1 className="text-2xl font-semibold text-content-primary">
              {t('contracts.claim_title', {
                number: claim.claim_number,
                defaultValue: 'Progress claim {{number}}',
              })}
            </h1>
            <Badge variant={CLAIM_STATUS_VARIANT[claim.status]} dot>
              {claimStatusLabel(t, claim.status)}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-content-secondary">
            {claim.period_start ? <DateDisplay value={claim.period_start} /> : '—'}
            {' → '}
            {claim.period_end ? <DateDisplay value={claim.period_end} /> : '—'}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {editable && (
            <Button
              variant="primary"
              icon={<Download size={14} />}
              onClick={() => setPopulateOpen(true)}
              data-testid="populate-button"
            >
              {t('contracts.populate_from_progress', {
                defaultValue: 'Populate from progress',
              })}
            </Button>
          )}
          {claim.status === 'draft' && (
            <Button
              variant="secondary"
              icon={<Send size={14} />}
              onClick={() => submit.mutate()}
              loading={submit.isPending}
            >
              {t('contracts.submit', { defaultValue: 'Submit' })}
            </Button>
          )}
          {claim.status === 'submitted' && (
            <>
              <Button
                variant="secondary"
                icon={<CheckCircle2 size={14} />}
                onClick={() => approve.mutate()}
                loading={approve.isPending}
              >
                {t('contracts.approve', { defaultValue: 'Approve' })}
              </Button>
              <Button
                variant="ghost"
                icon={<XCircle size={14} />}
                onClick={() => reject.mutate()}
                loading={reject.isPending}
              >
                {t('contracts.reject', { defaultValue: 'Reject' })}
              </Button>
            </>
          )}
          {claim.status === 'approved' && canManageClaim && (
            <Button
              variant="secondary"
              onClick={() => certify.mutate()}
              loading={certify.isPending}
            >
              {t('contracts.certify', { defaultValue: 'Certify' })}
            </Button>
          )}
          {claim.status === 'certified' && canManageClaim && (
            <Button
              variant="primary"
              icon={<DollarSign size={14} />}
              onClick={() => paid.mutate()}
              loading={paid.isPending}
            >
              {t('contracts.mark_paid', { defaultValue: 'Mark paid' })}
            </Button>
          )}
        </div>
      </div>

      <DismissibleInfo
        storageKey="contracts-claim"
        title={t('contracts_claim.intro_title', {
          defaultValue: 'Bill exactly what was built this period',
        })}
        more={
          t('contracts_claim.intro_more', { defaultValue: '' })
            ? <IntroRichText text={t('contracts_claim.intro_more')} />
            : undefined
        }
        links={[
          {
            label: t('nav.contracts', { defaultValue: 'Contracts' }),
            onClick: () => navigate(contractsHref),
          },
          {
            label: t('nav.finance', { defaultValue: 'Finance' }),
            onClick: () => navigate('/finance'),
          },
        ]}
      >
        {t('contracts_claim.intro_body', {
          defaultValue:
            'Enter the percent or value complete against each schedule-of-values line, or pull it straight from progress observations, and the claim totals gross, retention and net due for you. Walk it through Submit, Approve, Certify and Mark paid, and the certified amount flows back to the contract and into Finance as a payable.',
        })}
      </DismissibleInfo>

      {/* Totals */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KPI
          label={t('contracts.gross', { defaultValue: 'Gross' })}
          value={
            <MoneyDisplay
              amount={toNum(claim.gross_amount)}
              currency={claim.currency || undefined}
            />
          }
        />
        <KPI
          label={t('contracts.retention', { defaultValue: 'Retention' })}
          value={
            <MoneyDisplay
              amount={toNum(claim.retention_amount)}
              currency={claim.currency || undefined}
            />
          }
        />
        <KPI
          label={t('contracts.prior_claims', { defaultValue: 'Prior claims' })}
          value={
            <MoneyDisplay
              amount={toNum(claim.prior_claims_total)}
              currency={claim.currency || undefined}
            />
          }
        />
        <KPI
          label={t('contracts.net_due', { defaultValue: 'Net due' })}
          value={
            <MoneyDisplay
              amount={toNum(claim.net_due)}
              currency={claim.currency || undefined}
            />
          }
        />
      </div>

      {/* Line items */}
      <Card padding="sm">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-secondary">
          {t('contracts.claim_lines', { defaultValue: 'Claim lines' })}
          <span className="ml-2 normal-case text-content-tertiary">
            ({(linesQ.data ?? []).length})
          </span>
        </p>
        <ProgressClaimLineTable
          claimId={claimId as string}
          lines={linesQ.data ?? []}
          currency={claim.currency}
          editable={editable}
          isLoading={linesQ.isLoading}
        />
      </Card>

      {/* AIA G702/G703 — US/CA/AU only (gated on project.is_aia_eligible). */}
      {aiaEligible && (
        <AIAApplicationPanel claimId={claimId as string} currency={claim.currency} />
      )}

      {populateOpen && (
        <PopulatePreviewModal
          claimId={claimId as string}
          currency={claim.currency}
          onClose={() => setPopulateOpen(false)}
          onCommitted={invalidate}
        />
      )}
    </div>
  );
}

function KPI({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border-light bg-surface-secondary px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-content-tertiary">
        {label}
      </p>
      <p className="mt-0.5 text-sm font-semibold text-content-primary">{value}</p>
    </div>
  );
}
