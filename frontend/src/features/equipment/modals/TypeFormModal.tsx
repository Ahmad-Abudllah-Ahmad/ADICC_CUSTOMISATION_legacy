// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Plus, Save, Loader2 } from 'lucide-react';
import { Button } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  createType,
  updateType,
  type EquipmentType,
  type CreateEquipmentTypePayload,
  type UpdateEquipmentTypePayload,
} from '../api';

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
const labelCls = 'block text-xs font-medium text-content-secondary mb-1';

interface TypeFormModalProps {
  mode: 'create' | 'edit';
  existing?: EquipmentType;
  onClose: () => void;
  onSaved?: () => void;
}

export function TypeFormModal({
  mode,
  existing,
  onClose,
  onSaved,
}: TypeFormModalProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState(existing?.code ?? '');
  const [name, setName] = useState(existing?.name ?? '');
  const [category, setCategory] = useState(existing?.category ?? 'other');
  const [error, setError] = useState<string | null>(null);

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

  const isEdit = mode === 'edit';

  const submit = async () => {
    if (!code.trim() || !name.trim()) {
      setError(
        t('equipment.type.code_name_required', {
          defaultValue: 'Code and name are required',
        }),
      );
      return;
    }
    setError(null);
    setBusy(true);
    try {
      if (isEdit && existing) {
        const payload: UpdateEquipmentTypePayload = {
          name: name.trim(),
          category: category.trim() || 'other',
        };
        await updateType(existing.id, payload);
        addToast({
          type: 'success',
          title: t('equipment.type.updated', {
            defaultValue: 'Type updated',
          }),
        });
      } else {
        const payload: CreateEquipmentTypePayload = {
          code: code.trim(),
          name: name.trim(),
          category: category.trim() || 'other',
        };
        await createType(payload);
        addToast({
          type: 'success',
          title: t('equipment.type.created', {
            defaultValue: 'Type created',
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
      aria-labelledby="type-form-title"
    >
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div
        className="relative w-full max-w-md rounded-xl bg-surface-elevated p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2
            id="type-form-title"
            className="text-lg font-semibold text-content-primary"
          >
            {isEdit
              ? t('equipment.type.edit_title', {
                  defaultValue: 'Edit equipment type',
                })
              : t('equipment.type.new_title', {
                  defaultValue: 'New equipment type',
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

        <div className="space-y-3">
          <div>
            <label className={labelCls}>
              {t('equipment.type.code', { defaultValue: 'Code' })}{' '}
              <span className="text-rose-500">*</span>
            </label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className={inputCls}
              placeholder="excavator"
              disabled={isEdit}
              title={
                isEdit
                  ? t('equipment.type.code_immutable', {
                      defaultValue:
                        'Type code is immutable once equipment references it.',
                    })
                  : undefined
              }
            />
          </div>
          <div>
            <label className={labelCls}>
              {t('equipment.type.name', { defaultValue: 'Name' })}{' '}
              <span className="text-rose-500">*</span>
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputCls}
              placeholder={t('equipment.type.name_placeholder', {
                defaultValue: 'Tracked excavator',
              })}
            />
          </div>
          <div>
            <label className={labelCls}>
              {t('equipment.type.category', { defaultValue: 'Category' })}
            </label>
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className={inputCls}
              placeholder="earthworks, lifting, hauling…"
            />
          </div>
          {error && (
            <p className="text-xs text-status-error" role="alert">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-5">
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
