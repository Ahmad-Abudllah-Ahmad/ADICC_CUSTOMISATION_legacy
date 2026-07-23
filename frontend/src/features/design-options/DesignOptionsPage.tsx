// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * DesignOptionsPage - compare competing design options for a project side by
 * side. Each option carries its own model, which is converted and priced into
 * its own bill of quantities, so a concrete frame can be weighed against a steel
 * frame (or any A/B design choice) on cost, quantity and completeness.
 *
 * The flow is deliberately explicit and human-confirmed: attach a model to an
 * option, generate a dry-run preview of the matched priced BOQ, review it, then
 * apply. Nothing is written to a bill of quantities without that confirmation.
 *
 * Money, quantity and ratio fields arrive as Decimal-as-string from the API and
 * are parsed to numbers only for display formatting.
 */

import {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
  type DragEvent,
  type ChangeEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Layers,
  GitCompareArrows,
  Plus,
  Trash2,
  UploadCloud,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Crown,
  FileStack,
  Download,
  RefreshCw,
  Boxes,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  ConfirmDialog,
  SkeletonTable,
  DismissibleInfo,
  WideModal,
  WideModalSection,
  WideModalField,
  PageHeader,
  InfoHint,
} from '@/shared/ui';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { useConfirm } from '@/shared/hooks/useConfirm';
import { useToastStore } from '@/stores/useToastStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { getIntlLocale } from '@/shared/lib/formatters';
import {
  listOptionSets,
  getOptionSet,
  createOptionSet,
  deleteOptionSet,
  createOption,
  deleteOption,
  setBaseline,
  attachModelFile,
  generateOption,
  getComparison,
  downloadComparisonXlsx,
  type DesignOptionSet,
  type DesignOption,
  type DesignOptionStatus,
  type DesignOptionGenerateResponse,
} from './api';
import { DesignOptionComparisonTable } from './DesignOptionComparisonTable';

type BadgeVariant = 'neutral' | 'blue' | 'success' | 'warning' | 'error';

/* ── Helpers ───────────────────────────────────────────────────────────── */

const TRANSIENT_STATES: DesignOptionStatus[] = ['converting', 'boq_generating'];

function isTransient(status: DesignOptionStatus): boolean {
  return TRANSIENT_STATES.includes(status);
}

function num(v: string | number | null | undefined): number {
  if (v == null) return 0;
  const n = typeof v === 'number' ? v : parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function formatMoney(amount: string | number, currency?: string): string {
  const value = num(amount);
  const code = (currency || '').trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(code)) {
    return new Intl.NumberFormat(getIntlLocale(), { maximumFractionDigits: 0 }).format(value);
  }
  try {
    return new Intl.NumberFormat(getIntlLocale(), {
      style: 'currency',
      currency: code,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${value.toFixed(0)} ${code}`;
  }
}

const STATUS_VARIANT: Record<DesignOptionStatus, BadgeVariant> = {
  draft: 'neutral',
  model_attached: 'blue',
  converting: 'warning',
  boq_generating: 'warning',
  priced: 'success',
  failed: 'error',
};

function OptionStatusChip({ status }: { status: DesignOptionStatus }) {
  const { t } = useTranslation();
  const label: Record<DesignOptionStatus, string> = {
    draft: t('designOptions.status.draft', { defaultValue: 'Draft' }),
    model_attached: t('designOptions.status.modelAttached', { defaultValue: 'Model attached' }),
    converting: t('designOptions.status.converting', { defaultValue: 'Converting' }),
    boq_generating: t('designOptions.status.boqGenerating', { defaultValue: 'Generating' }),
    priced: t('designOptions.status.priced', { defaultValue: 'Priced' }),
    failed: t('designOptions.status.failed', { defaultValue: 'Failed' }),
  };
  return (
    <Badge variant={STATUS_VARIANT[status]} size="sm" dot>
      {label[status]}
    </Badge>
  );
}

/* ── Model dropzone ────────────────────────────────────────────────────── */

const CAD_ACCEPT = '.rvt,.ifc,.dwg,.dgn,.nwd,.nwc,.fbx,.obj,.3ds,.pdf,.csv,.xlsx,.xls';

function ModelDropzone({
  option,
  onChanged,
}: {
  option: DesignOption;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const attach = useMutation({
    mutationFn: (file: File) => attachModelFile(option.id, file),
    onSuccess: () => {
      onChanged();
      addToast({
        type: 'success',
        title: t('designOptions.toast.modelAttached', {
          defaultValue: 'Model uploaded - conversion started',
        }),
      });
    },
    onError: (error: Error) => {
      addToast({
        type: 'error',
        title: t('toasts.error', { defaultValue: 'Error' }),
        message: error.message,
      });
    },
  });

  const pick = (file: File | undefined | null) => {
    if (file) attach.mutate(file);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files?.[0]);
  };

  const onInput = (e: ChangeEvent<HTMLInputElement>) => {
    pick(e.target.files?.[0]);
    e.target.value = '';
  };

  if (attach.isPending) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-lg border border-border-light bg-surface-secondary/40 px-3 py-6 text-sm text-content-secondary">
        <Loader2 size={16} className="animate-spin text-oe-blue" />
        {t('designOptions.uploading', { defaultValue: 'Uploading model...' })}
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed px-3 py-6 text-center transition-colors ${
        dragging
          ? 'border-oe-blue bg-oe-blue-subtle'
          : 'border-border hover:border-oe-blue/60 hover:bg-surface-secondary/40'
      }`}
    >
      <UploadCloud size={20} className="text-oe-blue" />
      <p className="text-sm font-medium text-content-primary">
        {t('designOptions.dropTitle', { defaultValue: 'Attach a model' })}
      </p>
      <p className="text-xs text-content-tertiary">
        {t('designOptions.dropHint', {
          defaultValue: 'Drop a CAD/BIM file or a cad2data sheet, or click to browse.',
        })}
      </p>
      <input
        ref={inputRef}
        type="file"
        accept={CAD_ACCEPT}
        className="hidden"
        onChange={onInput}
      />
    </div>
  );
}

/* ── Generate dry-run preview ──────────────────────────────────────────── */

function PreviewStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border-light bg-surface-secondary/40 px-3 py-2">
      <p className="text-xs text-content-tertiary">{label}</p>
      <p className="text-base font-semibold tabular-nums text-content-primary">{value}</p>
    </div>
  );
}

function GeneratePreviewModal({
  option,
  onApplied,
  onClose,
}: {
  option: DesignOption;
  onApplied: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const started = useRef(false);
  const [preview, setPreview] = useState<DesignOptionGenerateResponse | null>(null);

  const dryRun = useMutation({
    mutationFn: () => generateOption(option.id, true),
    onSuccess: (res) => setPreview(res),
    onError: (error: Error) => {
      addToast({
        type: 'error',
        title: t('toasts.error', { defaultValue: 'Error' }),
        message: error.message,
      });
    },
  });

  const apply = useMutation({
    mutationFn: () => generateOption(option.id, false),
    onSuccess: () => {
      addToast({
        type: 'success',
        title: t('designOptions.toast.generated', {
          defaultValue: 'Priced BOQ generated for this option',
        }),
      });
      onApplied();
      onClose();
    },
    onError: (error: Error) => {
      addToast({
        type: 'error',
        title: t('toasts.error', { defaultValue: 'Error' }),
        message: error.message,
      });
    },
  });

  // Run the preview exactly once when the modal opens. The ref guard keeps
  // React StrictMode's double-mount from firing two preview requests.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    dryRun.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <WideModal
      open
      onClose={onClose}
      title={t('designOptions.previewTitle', { defaultValue: 'Generate priced estimate' })}
      subtitle={t('designOptions.previewSubtitle', {
        defaultValue:
          'Preview the matched, priced bill of quantities before it is written to this option. Nothing is applied until you confirm.',
      })}
      size="lg"
      busy={apply.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={apply.isPending}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            icon={<Sparkles size={14} />}
            loading={apply.isPending}
            disabled={!preview || dryRun.isPending}
            onClick={() => apply.mutate()}
          >
            {t('designOptions.applyGenerate', { defaultValue: 'Apply and price' })}
          </Button>
        </>
      }
    >
      {dryRun.isPending ? (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-content-secondary">
          <Loader2 size={18} className="animate-spin text-oe-blue" />
          {t('designOptions.previewLoading', {
            defaultValue: 'Matching model elements to cost items...',
          })}
        </div>
      ) : preview ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <PreviewStat
              label={t('designOptions.elements', { defaultValue: 'Elements' })}
              value={preview.element_count}
            />
            <PreviewStat
              label={t('designOptions.matched', { defaultValue: 'Matched' })}
              value={preview.groups_confirmed}
            />
            <PreviewStat
              label={t('designOptions.unmatched', { defaultValue: 'Unmatched' })}
              value={Math.max(0, preview.groups_total - preview.groups_confirmed)}
            />
            <PreviewStat
              label={t('designOptions.positions', { defaultValue: 'Positions' })}
              value={preview.position_count}
            />
          </div>

          <div className="rounded-lg border border-border-light bg-surface-secondary/40 px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-content-secondary">
                {t('designOptions.estDirectCost', { defaultValue: 'Estimated direct cost' })}
              </span>
              <span className="text-lg font-semibold tabular-nums text-content-primary">
                {formatMoney(preview.direct_cost, preview.currency)}
              </span>
            </div>
            {num(preview.grand_total) > 0 && (
              <div className="mt-1 flex items-center justify-between">
                <span className="text-sm text-content-secondary">
                  {t('designOptions.estGrandTotal', { defaultValue: 'Estimated grand total' })}
                </span>
                <span className="text-sm font-medium tabular-nums text-content-primary">
                  {formatMoney(preview.grand_total, preview.currency)}
                </span>
              </div>
            )}
          </div>

          {preview.groups_total - preview.groups_confirmed > 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-semantic-warning/30 bg-semantic-warning/10 px-3 py-2 text-xs text-content-secondary">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-semantic-warning" aria-hidden />
              <span>
                {t('designOptions.unmatchedNote', {
                  defaultValue:
                    '{{count}} element(s) could not be matched to a cost item and are left unpriced. You can refine them in the option BOQ after applying.',
                  count: Math.max(0, preview.groups_total - preview.groups_confirmed),
                })}
              </span>
            </div>
          )}

          {preview.warnings.length > 0 && (
            <ul className="space-y-1 text-xs text-content-secondary">
              {preview.warnings.map((w, i) => (
                <li key={i} className="flex gap-1.5">
                  <span aria-hidden="true">-</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          )}

          <p className="text-xs text-content-tertiary">
            {t('designOptions.humanConfirmNote', {
              defaultValue:
                'These matches are AI-assisted suggestions. Review the numbers above, then apply to write the priced BOQ for this option.',
            })}
          </p>
        </div>
      ) : (
        <div className="py-10 text-center text-sm text-content-tertiary">
          {t('designOptions.previewFailed', {
            defaultValue: 'Could not build a preview. Please close and try again.',
          })}
        </div>
      )}
    </WideModal>
  );
}

/* ── Option card ───────────────────────────────────────────────────────── */

function OptionCard({
  option,
  baselineOptionId,
  onChanged,
}: {
  option: DesignOption;
  baselineOptionId: string | null;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const { confirm, ...confirmProps } = useConfirm();
  const [showPreview, setShowPreview] = useState(false);

  const isBaseline = option.id === baselineOptionId;
  const isPriced = option.status === 'priced';

  const baselineMutation = useMutation({
    mutationFn: () => setBaseline(option.set_id, option.id),
    onSuccess: onChanged,
    onError: (error: Error) => {
      addToast({ type: 'error', title: t('toasts.error', { defaultValue: 'Error' }), message: error.message });
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => deleteOption(option.id),
    onSuccess: onChanged,
    onError: (error: Error) => {
      addToast({ type: 'error', title: t('toasts.error', { defaultValue: 'Error' }), message: error.message });
    },
  });

  return (
    <Card padding="none" className={isBaseline ? 'ring-2 ring-oe-blue/40 border-oe-blue/40' : ''}>
      <div className="flex flex-col gap-3 p-4">
        {/* Header */}
        <div className="flex items-start gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-oe-blue-subtle text-oe-blue-text">
            <Boxes size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <h3 className="truncate text-sm font-semibold text-content-primary">{option.name}</h3>
              {isBaseline && (
                <Crown size={13} className="shrink-0 text-oe-blue" aria-label={t('designOptions.baseline', { defaultValue: 'Baseline' })} />
              )}
            </div>
            <div className="mt-1">
              <OptionStatusChip status={option.status} />
            </div>
          </div>
          <button
            type="button"
            aria-label={t('designOptions.removeOption', { defaultValue: 'Remove option' })}
            title={t('designOptions.removeOption', { defaultValue: 'Remove option' })}
            className="shrink-0 rounded-md p-1.5 text-content-tertiary transition-colors hover:bg-semantic-error-bg/40 hover:text-semantic-error disabled:opacity-50"
            disabled={removeMutation.isPending}
            onClick={async () => {
              const ok = await confirm({
                title: t('designOptions.removeOption', { defaultValue: 'Remove option' }),
                message: t('designOptions.removeOptionConfirm', {
                  defaultValue: 'Remove "{{name}}" and its generated BOQ from this comparison?',
                  name: option.name,
                }),
                variant: 'warning',
              });
              if (ok) removeMutation.mutate();
            }}
          >
            <Trash2 size={15} />
          </button>
        </div>

        {/* Body by status */}
        {option.status === 'draft' && <ModelDropzone option={option} onChanged={onChanged} />}

        {option.status === 'converting' && (
          <div className="flex items-center gap-2 rounded-lg border border-border-light bg-surface-secondary/40 px-3 py-4 text-sm text-content-secondary">
            <Loader2 size={16} className="animate-spin text-oe-blue" />
            {t('designOptions.convertingBody', { defaultValue: 'Converting the model...' })}
          </div>
        )}

        {option.status === 'boq_generating' && (
          <div className="flex items-center gap-2 rounded-lg border border-border-light bg-surface-secondary/40 px-3 py-4 text-sm text-content-secondary">
            <Loader2 size={16} className="animate-spin text-oe-blue" />
            {t('designOptions.generatingBody', { defaultValue: 'Generating the priced estimate...' })}
          </div>
        )}

        {option.status === 'model_attached' && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-lg border border-border-light bg-surface-secondary/30 px-3 py-2 text-xs text-content-secondary">
              <CheckCircle2 size={14} className="text-semantic-success" />
              {t('designOptions.modelReady', {
                defaultValue: '{{count}} element(s) ready to price.',
                count: option.element_count,
              })}
            </div>
            <Button
              variant="primary"
              size="sm"
              icon={<Sparkles size={14} />}
              className="w-full"
              onClick={() => setShowPreview(true)}
            >
              {t('designOptions.generate', { defaultValue: 'Generate estimate' })}
            </Button>
          </div>
        )}

        {option.status === 'failed' && (
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-lg border border-semantic-error/30 bg-semantic-error-bg/30 px-3 py-2 text-xs text-semantic-error">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{option.error || t('designOptions.failedGeneric', { defaultValue: 'Processing failed.' })}</span>
            </div>
            <ModelDropzone option={option} onChanged={onChanged} />
          </div>
        )}

        {isPriced && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-border-light bg-surface-secondary/30 px-3 py-2">
                <p className="text-xs text-content-tertiary">
                  {t('designOptions.grandTotal', { defaultValue: 'Grand total' })}
                </p>
                <p className="text-base font-semibold tabular-nums text-content-primary">
                  {formatMoney(option.grand_total, option.currency)}
                </p>
              </div>
              <div className="rounded-lg border border-border-light bg-surface-secondary/30 px-3 py-2">
                <p className="text-xs text-content-tertiary">
                  {t('designOptions.costPerM2', { defaultValue: 'Cost per m2' })}
                </p>
                <p className="text-base font-semibold tabular-nums text-content-primary">
                  {num(option.cost_per_m2) > 0 ? formatMoney(option.cost_per_m2, option.currency) : '-'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs text-content-tertiary">
              <span className="inline-flex items-center gap-1">
                <Boxes size={12} /> {option.element_count}
              </span>
              <span className="inline-flex items-center gap-1">
                <FileStack size={12} /> {option.position_count}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              icon={<RefreshCw size={13} />}
              onClick={() => setShowPreview(true)}
            >
              {t('designOptions.regenerate', { defaultValue: 'Regenerate' })}
            </Button>
          </div>
        )}

        {/* Baseline selector */}
        <div className="mt-1 border-t border-border-light pt-3">
          {isBaseline ? (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-oe-blue-text">
              <Crown size={13} /> {t('designOptions.isBaseline', { defaultValue: 'Comparison baseline' })}
            </span>
          ) : (
            <button
              type="button"
              disabled={baselineMutation.isPending}
              onClick={() => baselineMutation.mutate()}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-content-secondary transition-colors hover:text-oe-blue disabled:opacity-50"
            >
              <Crown size={13} /> {t('designOptions.setBaseline', { defaultValue: 'Set as baseline' })}
            </button>
          )}
        </div>
      </div>

      {showPreview && (
        <GeneratePreviewModal
          option={option}
          onApplied={onChanged}
          onClose={() => setShowPreview(false)}
        />
      )}
      <ConfirmDialog {...confirmProps} />
    </Card>
  );
}

/* ── Create set / add option modals ────────────────────────────────────── */

function CreateSetModal({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: (set: DesignOptionSet) => void;
}) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [name, setName] = useState('');

  const create = useMutation({
    mutationFn: () => createOptionSet({ project_id: projectId, name: name.trim() }),
    onSuccess: (set) => {
      onCreated(set);
      onClose();
      addToast({ type: 'success', title: t('designOptions.toast.setCreated', { defaultValue: 'Option set created' }) });
    },
    onError: (error: Error) => {
      addToast({ type: 'error', title: t('toasts.error', { defaultValue: 'Error' }), message: error.message });
    },
  });

  const fieldCls =
    'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm text-content-primary placeholder:text-content-tertiary transition-all focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

  return (
    <WideModal
      open
      onClose={onClose}
      title={t('designOptions.newSet', { defaultValue: 'New option set' })}
      subtitle={t('designOptions.newSetSubtitle', {
        defaultValue: 'Group the design options you want to weigh against each other.',
      })}
      size="md"
      busy={create.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={create.isPending}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            disabled={!name.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            {t('designOptions.createSet', { defaultValue: 'Create set' })}
          </Button>
        </>
      }
    >
      <WideModalSection columns={1}>
        <WideModalField label={t('designOptions.setName', { defaultValue: 'Set name' })} required>
          <input
            type="text"
            value={name}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && name.trim()) create.mutate();
            }}
            placeholder={t('designOptions.setNamePlaceholder', {
              defaultValue: 'e.g. Superstructure - frame options',
            })}
            className={fieldCls}
          />
        </WideModalField>
      </WideModalSection>
    </WideModal>
  );
}

function AddOptionModal({
  setId,
  onClose,
  onCreated,
}: {
  setId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [name, setName] = useState('');

  const create = useMutation({
    mutationFn: () => createOption(setId, { name: name.trim() }),
    onSuccess: () => {
      onCreated();
      onClose();
    },
    onError: (error: Error) => {
      addToast({ type: 'error', title: t('toasts.error', { defaultValue: 'Error' }), message: error.message });
    },
  });

  const fieldCls =
    'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm text-content-primary placeholder:text-content-tertiary transition-all focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

  return (
    <WideModal
      open
      onClose={onClose}
      title={t('designOptions.newOption', { defaultValue: 'Add option' })}
      size="md"
      busy={create.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={create.isPending}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            disabled={!name.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            {t('designOptions.addOption', { defaultValue: 'Add option' })}
          </Button>
        </>
      }
    >
      <WideModalSection columns={1}>
        <WideModalField label={t('designOptions.optionName', { defaultValue: 'Option name' })} required>
          <input
            type="text"
            value={name}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && name.trim()) create.mutate();
            }}
            placeholder={t('designOptions.optionNamePlaceholder', {
              defaultValue: 'e.g. Reinforced concrete frame',
            })}
            className={fieldCls}
          />
        </WideModalField>
      </WideModalSection>
    </WideModal>
  );
}

/* ── Selected-set detail ───────────────────────────────────────────────── */

function OptionSetDetail({ setId }: { setId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [showAddOption, setShowAddOption] = useState(false);

  const setQuery = useQuery({
    queryKey: ['design-options', 'set', setId],
    queryFn: () => getOptionSet(setId),
    // Poll while any option is converting or generating, so the cards advance
    // from "Converting" to "Priced" without a manual refresh.
    refetchInterval: (query) => {
      const data = query.state.data as DesignOptionSet | undefined;
      const opts = data?.options ?? [];
      return opts.some((o) => isTransient(o.status)) ? 4000 : false;
    },
  });

  const set = setQuery.data;
  const options = useMemo(
    () => [...(set?.options ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [set],
  );
  const pricedCount = options.filter((o) => o.status === 'priced').length;
  const canCompare = pricedCount >= 2;

  const comparisonQuery = useQuery({
    queryKey: ['design-options', 'comparison', setId],
    queryFn: () => getComparison(setId),
    enabled: canCompare,
  });

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['design-options', 'set', setId] });
    queryClient.invalidateQueries({ queryKey: ['design-options', 'comparison', setId] });
  }, [queryClient, setId]);

  const handleExport = useCallback(async () => {
    if (!set) return;
    const safe = set.name.replace(/[^a-z0-9_-]+/gi, '_') || 'design-options';
    try {
      await downloadComparisonXlsx(setId, `${safe}-comparison.xlsx`);
    } catch (error) {
      addToast({
        type: 'error',
        title: t('designOptions.exportFailed', { defaultValue: 'Export failed' }),
        message: error instanceof Error ? error.message : undefined,
      });
    }
  }, [set, setId, addToast, t]);

  if (setQuery.isLoading) {
    return <SkeletonTable rows={3} columns={3} />;
  }
  if (setQuery.isError || !set) {
    return (
      <Card className="py-10">
        <EmptyState
          icon={<AlertTriangle size={26} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('designOptions.setLoadError', {
            defaultValue: 'Could not load this option set. Please try again.',
          })}
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {/* Options grid */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-content-primary">
            {t('designOptions.options', { defaultValue: 'Options' })}
          </h2>
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus size={14} />}
            onClick={() => setShowAddOption(true)}
          >
            {t('designOptions.addOption', { defaultValue: 'Add option' })}
          </Button>
        </div>

        {options.length === 0 ? (
          <EmptyState
            icon={<Layers size={26} strokeWidth={1.5} />}
            title={t('designOptions.noOptions', { defaultValue: 'No options yet' })}
            description={t('designOptions.noOptionsDesc', {
              defaultValue: 'Add two or more options, then attach a model to each to compare them.',
            })}
            action={{
              label: t('designOptions.addOption', { defaultValue: 'Add option' }),
              onClick: () => setShowAddOption(true),
            }}
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {options.map((option) => (
              <OptionCard
                key={option.id}
                option={option}
                baselineOptionId={set.baseline_option_id}
                onChanged={invalidate}
              />
            ))}
          </div>
        )}
      </div>

      {/* Comparison */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
            <GitCompareArrows size={16} className="text-oe-blue" />
            {t('designOptions.comparison', { defaultValue: 'Comparison' })}
            <InfoHint
              text={t('designOptions.comparisonHelp', {
                defaultValue:
                  'Every option is priced into its own bill of quantities and rebased to the set currency, then compared against the baseline on total cost, by-trade quantities and completeness.',
              })}
            />
          </h2>
          {canCompare && (
            <Button variant="ghost" size="sm" icon={<Download size={14} />} onClick={handleExport}>
              {t('designOptions.exportXlsx', { defaultValue: 'Export' })}
            </Button>
          )}
        </div>

        {!canCompare ? (
          <EmptyState
            icon={<GitCompareArrows size={26} strokeWidth={1.5} />}
            title={t('designOptions.compareGateTitle', { defaultValue: 'Price two options to compare' })}
            description={t('designOptions.compareGateDesc', {
              defaultValue:
                'Attach a model to at least two options and generate their priced estimates. The side-by-side comparison appears here.',
            })}
          />
        ) : comparisonQuery.isLoading ? (
          <SkeletonTable rows={4} columns={Math.max(2, pricedCount)} />
        ) : comparisonQuery.isError || !comparisonQuery.data ? (
          <Card className="py-10">
            <EmptyState
              icon={<AlertTriangle size={26} strokeWidth={1.5} />}
              title={t('common.error', { defaultValue: 'Error' })}
              description={t('designOptions.comparisonLoadError', {
                defaultValue: 'Could not load the comparison. Please try again.',
              })}
            />
          </Card>
        ) : (
          <DesignOptionComparisonTable comparison={comparisonQuery.data} />
        )}
      </div>

      {showAddOption && (
        <AddOptionModal
          setId={setId}
          onClose={() => setShowAddOption(false)}
          onCreated={invalidate}
        />
      )}
    </div>
  );
}

/* ── Main page ─────────────────────────────────────────────────────────── */

export function DesignOptionsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { confirm, ...confirmProps } = useConfirm();
  const addToast = useToastStore((s) => s.addToast);
  const { activeProjectId } = useProjectContextStore();
  const projectId = activeProjectId ?? '';

  const [selectedSetId, setSelectedSetId] = useState('');
  const [showCreateSet, setShowCreateSet] = useState(false);

  const setsQuery = useQuery({
    queryKey: ['design-options', 'sets', projectId],
    queryFn: () => listOptionSets(projectId),
    enabled: !!projectId,
  });
  const sets = setsQuery.data ?? [];

  // Keep a valid selection: default to the first set, and drop a stale id if
  // the selected set was deleted elsewhere.
  useEffect(() => {
    if (sets.length === 0) {
      if (selectedSetId) setSelectedSetId('');
      return;
    }
    if (!selectedSetId || !sets.some((s) => s.id === selectedSetId)) {
      setSelectedSetId(sets[0]!.id);
    }
  }, [sets, selectedSetId]);

  const deleteSetMutation = useMutation({
    mutationFn: (setId: string) => deleteOptionSet(setId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['design-options', 'sets', projectId] });
      addToast({ type: 'success', title: t('designOptions.toast.setDeleted', { defaultValue: 'Option set deleted' }) });
    },
    onError: (error: Error) => {
      addToast({ type: 'error', title: t('toasts.error', { defaultValue: 'Error' }), message: error.message });
    },
  });

  const handleSetCreated = useCallback(
    (set: DesignOptionSet) => {
      queryClient.invalidateQueries({ queryKey: ['design-options', 'sets', projectId] });
      setSelectedSetId(set.id);
    },
    [queryClient, projectId],
  );

  return (
    <div className="space-y-5 animate-fade-in">
      <Breadcrumb items={[{ label: t('designOptions.title', { defaultValue: 'Design Options' }) }]} />

      <PageHeader
        srTitle={t('designOptions.title', { defaultValue: 'Design Options' })}
        subtitle={t('designOptions.subtitle', {
          defaultValue: 'Compare competing design options for the project on cost, quantity and completeness',
        })}
        actions={
          <span
            title={
              !projectId
                ? t('designOptions.selectProjectFirst', { defaultValue: 'Select a project first' })
                : undefined
            }
          >
            <Button
              variant="primary"
              icon={<Plus size={16} />}
              disabled={!projectId}
              onClick={() => setShowCreateSet(true)}
            >
              {t('designOptions.newSet', { defaultValue: 'New option set' })}
            </Button>
          </span>
        }
      />

      <DismissibleInfo
        storageKey="design-options"
        title={t('designOptions.introTitle', {
          defaultValue: 'Weigh design options side by side',
        })}
        links={[
          { label: t('nav.bim', { defaultValue: 'BIM' }), onClick: () => navigate('/bim') },
          { label: t('nav.boq', { defaultValue: 'BOQ' }), onClick: () => navigate('/boq') },
        ]}
      >
        {t('designOptions.introBody', {
          defaultValue:
            'Create a set, add each design option, and attach its model. Every option is converted and priced into its own bill of quantities, so you can compare a concrete frame against a steel frame (or any A/B choice) on total cost, by-trade quantities and completeness. Pick a baseline and the others are measured against it.',
        })}
      </DismissibleInfo>

      {/* No project selected */}
      {!projectId && (
        <RequiresProject
          emptyHint={t('designOptions.selectProjectDesc', {
            defaultValue: 'Select a project to start comparing design options.',
          })}
        >
          {null}
        </RequiresProject>
      )}

      {/* Sets loading */}
      {projectId && setsQuery.isLoading && <SkeletonTable rows={2} columns={3} />}

      {/* Sets error */}
      {projectId && setsQuery.isError && (
        <Card className="py-10">
          <EmptyState
            icon={<AlertTriangle size={26} strokeWidth={1.5} />}
            title={t('common.error', { defaultValue: 'Error' })}
            description={t('designOptions.setsLoadError', {
              defaultValue: 'Could not load option sets. Please try again.',
            })}
          />
        </Card>
      )}

      {/* No sets */}
      {projectId && !setsQuery.isLoading && !setsQuery.isError && sets.length === 0 && (
        <EmptyState
          icon={<Layers size={28} strokeWidth={1.5} />}
          title={t('designOptions.noSets', { defaultValue: 'No option sets yet' })}
          description={t('designOptions.noSetsDesc', {
            defaultValue: 'Create an option set to compare competing design options for this project.',
          })}
          action={{
            label: t('designOptions.newSet', { defaultValue: 'New option set' }),
            onClick: () => setShowCreateSet(true),
          }}
        />
      )}

      {/* Set picker + detail */}
      {projectId && sets.length > 0 && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {sets.map((s) => {
              const active = s.id === selectedSetId;
              return (
                <div key={s.id} className="flex items-center">
                  <button
                    type="button"
                    onClick={() => setSelectedSetId(s.id)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                      active
                        ? 'border-oe-blue bg-oe-blue-subtle text-oe-blue-text'
                        : 'border-border bg-surface-primary text-content-secondary hover:border-content-tertiary'
                    }`}
                  >
                    <Layers size={13} />
                    {s.name}
                  </button>
                  {active && (
                    <button
                      type="button"
                      aria-label={t('designOptions.deleteSet', { defaultValue: 'Delete set' })}
                      title={t('designOptions.deleteSet', { defaultValue: 'Delete set' })}
                      className="ml-1 rounded-md p-1 text-content-tertiary transition-colors hover:bg-semantic-error-bg/40 hover:text-semantic-error disabled:opacity-50"
                      disabled={deleteSetMutation.isPending}
                      onClick={async () => {
                        const ok = await confirm({
                          title: t('designOptions.deleteSet', { defaultValue: 'Delete set' }),
                          message: t('designOptions.deleteSetConfirm', {
                            defaultValue: 'Delete "{{name}}" and every option in it? This cannot be undone.',
                            name: s.name,
                          }),
                          variant: 'danger',
                        });
                        if (ok) deleteSetMutation.mutate(s.id);
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {selectedSetId && <OptionSetDetail setId={selectedSetId} />}
        </div>
      )}

      {showCreateSet && projectId && (
        <CreateSetModal
          projectId={projectId}
          onClose={() => setShowCreateSet(false)}
          onCreated={handleSetCreated}
        />
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  );
}

export default DesignOptionsPage;
