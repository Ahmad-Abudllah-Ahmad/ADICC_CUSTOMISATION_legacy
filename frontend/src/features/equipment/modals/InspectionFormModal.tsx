// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Plus, Save, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { Button } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  createInspection,
  updateInspection,
  type Inspection,
  type InspectionType,
  type InspectionResult,
  type CreateInspectionPayload,
  type UpdateInspectionPayload,
} from '../api';

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
const labelCls = 'block text-xs font-medium text-content-secondary mb-1';

interface InspectionFormModalProps {
  mode: 'create' | 'edit';
  equipmentId: string;
  existing?: Inspection;
  onClose: () => void;
  onSaved?: () => void;
}

export function InspectionFormModal({
  mode,
  equipmentId,
  existing,
  onClose,
  onSaved,
}: InspectionFormModalProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);
  const [inspectionType, setInspectionType] = useState<InspectionType>(
    (existing?.inspection_type as InspectionType) ?? 'annual',
  );
  const [inspectedAt, setInspectedAt] = useState<string>(
    existing?.inspected_at ?? new Date().toISOString().slice(0, 10),
  );
  const [validUntil, setValidUntil] = useState<string>(existing?.valid_until ?? '');
  const [inspectorName, setInspectorName] = useState<string>(
    existing?.inspector_name ?? '',
  );
  const [result, setResult] = useState<InspectionResult>(
    (existing?.result as InspectionResult) ?? 'pass',
  );
  const [notes, setNotes] = useState<string>(existing?.notes ?? '');
  const [certificateUrl, setCertificateUrl] = useState<string>(
    existing?.certificate_url ?? '',
  );
  const [error, setError] = useState<string | null>(null);

  const isEdit = mode === 'edit';

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', h, { capture: true });
    return () =>
      document.removeEventListener('keydown', h, { capture: true });
  }, [busy, onClose]);

  const submit = async () => {
    if (!inspectedAt || !validUntil) {
      setError(
        t('equipment.inspection.dates_required', {
          defaultValue: 'Inspected-at and valid-until dates are required.',
        }),
      );
      return;
    }
    if (validUntil < inspectedAt) {
      setError(
        t('equipment.inspection.valid_after_inspected', {
          defaultValue: 'Valid-until must be on or after inspected-at.',
        }),
      );
      return;
    }
    setError(null);
    setBusy(true);
    try {
      if (isEdit && existing) {
        const payload: UpdateInspectionPayload = {
          inspection_type: inspectionType,
          inspected_at: inspectedAt,
          valid_until: validUntil,
          inspector_name: inspectorName.trim() || null,
          result,
          notes: notes.trim() || null,
          certificate_url: certificateUrl.trim() || null,
        };
        await updateInspection(existing.id, payload);
        addToast({
          type: 'success',
          title: t('equipment.inspection.updated', {
            defaultValue: 'Inspection updated',
          }),
        });
      } else {
        const payload: CreateInspectionPayload = {
          equipment_id: equipmentId,
          inspection_type: inspectionType,
          inspected_at: inspectedAt,
          valid_until: validUntil,
          inspector_name: inspectorName.trim() || null,
          result,
          notes: notes.trim() || null,
          certificate_url: certificateUrl.trim() || null,
        };
        await createInspection(payload);
        addToast({
          type: 'success',
          title: t('equipment.inspection.created', {
            defaultValue: 'Inspection recorded',
          }),
        });
      }
      onSaved?.();
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-3"
      onClick={() => !busy && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="inspection-form-title"
    >
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div
        className="relative w-full max-w-xl max-h-[92vh] overflow-y-auto rounded-xl bg-surface-elevated p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2
            id="inspection-form-title"
            className="text-lg font-semibold text-content-primary"
          >
            {isEdit
              ? t('equipment.inspection.edit_title', {
                  defaultValue: 'Edit inspection',
                })
              : t('equipment.inspection.new_title', {
                  defaultValue: 'New inspection',
                })}
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded p-1 hover:bg-surface-secondary disabled:opacity-50"
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4">
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
              {t('equipment.inspection.section_when', {
                defaultValue: 'When & what',
              })}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>
                  {t('equipment.inspection.type', { defaultValue: 'Type' })}
                </label>
                <select
                  value={inspectionType}
                  onChange={(e) =>
                    setInspectionType(e.target.value as InspectionType)
                  }
                  className={inputCls}
                >
                  {(
                    ['annual', 'quarterly', 'monthly', 'weekly', 'pre_use'] as InspectionType[]
                  ).map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.inspection.result', { defaultValue: 'Result' })}
                </label>
                <select
                  value={result}
                  onChange={(e) => setResult(e.target.value as InspectionResult)}
                  className={inputCls}
                >
                  {(['pass', 'conditional', 'fail'] as InspectionResult[]).map(
                    (s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ),
                  )}
                </select>
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.inspection.performed_at', {
                    defaultValue: 'Performed at',
                  })}{' '}
                  <span className="text-rose-500">*</span>
                </label>
                <input
                  type="date"
                  value={inspectedAt}
                  onChange={(e) => setInspectedAt(e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.inspection.expiry_date', {
                    defaultValue: 'Expiry date',
                  })}{' '}
                  <span className="text-rose-500">*</span>
                </label>
                <input
                  type="date"
                  value={validUntil}
                  onChange={(e) => setValidUntil(e.target.value)}
                  className={inputCls}
                />
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
              {t('equipment.inspection.section_who', {
                defaultValue: 'Who & evidence',
              })}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>
                  {t('equipment.inspection.performed_by', {
                    defaultValue: 'Performed by',
                  })}
                </label>
                <input
                  value={inspectorName}
                  onChange={(e) => setInspectorName(e.target.value)}
                  className={inputCls}
                  placeholder={t('equipment.inspection.performed_by_ph', {
                    defaultValue: 'Inspector name',
                  })}
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.inspection.certificate_url', {
                    defaultValue: 'Certificate URL',
                  })}
                </label>
                <input
                  type="url"
                  value={certificateUrl}
                  onChange={(e) => setCertificateUrl(e.target.value)}
                  className={inputCls}
                  placeholder="https://…"
                />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>
                  {t('equipment.inspection.notes', { defaultValue: 'Notes' })}
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className={clsx(inputCls, 'min-h-[72px] py-2 leading-snug')}
                  rows={3}
                />
              </div>
            </div>
          </section>

          {error && (
            <p className="text-xs text-status-error" role="alert">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-5 sticky bottom-0 pt-3 -mx-5 -mb-5 px-5 pb-3 bg-surface-elevated border-t border-border-light">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            loading={busy}
            icon={
              busy ? <Loader2 size={14} /> : isEdit ? <Save size={14} /> : <Plus size={14} />
            }
          >
            {isEdit
              ? t('common.save', { defaultValue: 'Save changes' })
              : t('common.create', { defaultValue: 'Create' })}
          </Button>
        </div>
      </div>
    </div>
  );
}
