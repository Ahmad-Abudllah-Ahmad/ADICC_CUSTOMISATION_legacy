// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * SendToTenderDialog — turn BOQ sections into a tender package.
 *
 * Creates a draft package on the tendering module straight from this estimate.
 * When the user has top-level sections selected in the grid, only those (and
 * their descendants) are packaged; otherwise the whole BOQ goes in. The server
 * copies a line-item template onto the package so bids can be seeded later, and
 * keeps the link back to the source BOQ for bid-vs-budget levelling.
 */

import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Send, X } from 'lucide-react';
import { boqApi, type TenderPackageRef } from './api';
import { useToastStore } from '@/stores/useToastStore';
import { useFocusTrap } from '@/shared/hooks/useFocusTrap';

export interface SendToTenderDialogProps {
  boqId: string;
  projectId: string;
  /** Source estimate name, used to seed the package name. */
  baseName: string;
  /**
   * Top-level section ids the user has selected. Empty means "all sections of
   * the BOQ" (the backend treats an empty list as every top-level section).
   */
  sectionIds: string[];
  isOpen: boolean;
  onClose: () => void;
  /** Called with the new package once it is created. */
  onCreated: (pkg: TenderPackageRef) => void;
}

export function SendToTenderDialog({
  boqId,
  projectId,
  baseName,
  sectionIds,
  isOpen,
  onClose,
  onCreated,
}: SendToTenderDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(panelRef, isOpen);

  const [name, setName] = useState('');
  const [deadline, setDeadline] = useState('');
  const scoped = sectionIds.length > 0;

  useEffect(() => {
    if (isOpen) {
      setName(
        t('boq.tender_default_name', {
          defaultValue: 'Tender - {{name}}',
          name: baseName || t('boq.untitled_estimate', { defaultValue: 'Estimate' }),
        }),
      );
      setDeadline('');
    }
  }, [isOpen, baseName, t]);

  useEffect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    }
    document.addEventListener('keydown', onKey, { capture: true });
    return () => document.removeEventListener('keydown', onKey, { capture: true });
  }, [isOpen, onClose]);

  const mutation = useMutation({
    mutationFn: () =>
      boqApi.createTenderFromBoq({
        project_id: projectId,
        boq_id: boqId,
        section_ids: sectionIds,
        package_name: name.trim() || baseName,
        deadline: deadline || undefined,
      }),
    onSuccess: (pkg) => {
      queryClient.invalidateQueries({ queryKey: ['tender-packages'] });
      addToast({
        type: 'success',
        title: t('boq.tender_created', { defaultValue: 'Tender package created' }),
      });
      onCreated(pkg);
    },
    onError: (err: Error) => {
      addToast({
        type: 'error',
        title: t('boq.tender_failed', { defaultValue: 'Could not create tender package' }),
        message: err.message,
      });
    },
  });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-lg animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        aria-label={t('boq.tender_title', { defaultValue: 'Send to tender' })}
        className="relative z-10 w-full max-w-md mx-4 rounded-2xl border border-border-light bg-surface-elevated shadow-xl animate-scale-in focus:outline-none"
      >
        <div className="flex items-center justify-between border-b border-border-light px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-oe-blue-subtle text-oe-blue-text">
              <Send size={15} />
            </span>
            <h2 className="text-base font-semibold text-content-primary">
              {t('boq.tender_title', { defaultValue: 'Send to tender' })}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="flex h-7 w-7 items-center justify-center rounded-md text-content-tertiary hover:text-content-primary hover:bg-surface-secondary transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-6 pt-4 pb-2 space-y-4">
          <div className="rounded-lg border border-border-light bg-surface-secondary/40 px-3 py-2.5 text-xs text-content-secondary">
            {scoped
              ? t('boq.tender_scope_selected', {
                  defaultValue:
                    'Selected sections ({{count}}) and their items will be packaged.',
                  count: sectionIds.length,
                })
              : t('boq.tender_scope_all', {
                  defaultValue:
                    'All sections of this estimate will be packaged. Select sections first to send only part of it.',
                })}
          </div>

          <label className="block">
            <span className="text-xs font-medium text-content-secondary">
              {t('boq.tender_name_label', { defaultValue: 'Package name' })}
            </span>
            <input
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full h-9 rounded-md border border-border bg-surface-primary px-3 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/30"
              aria-label={t('boq.tender_name_label', { defaultValue: 'Package name' })}
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-content-secondary">
              {t('boq.tender_deadline_label', { defaultValue: 'Bid deadline (optional)' })}
            </span>
            <input
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="mt-1 w-full h-9 rounded-md border border-border bg-surface-primary px-3 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/30"
              aria-label={t('boq.tender_deadline_label', { defaultValue: 'Bid deadline (optional)' })}
            />
          </label>
        </div>

        <div className="flex gap-3 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg px-4 py-2.5 text-sm font-medium bg-surface-primary text-content-primary border border-border hover:bg-surface-secondary transition-all"
          >
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </button>
          <button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !name.trim()}
            className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-white bg-oe-blue hover:bg-oe-blue-hover transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send size={14} />
            {mutation.isPending
              ? t('boq.tender_creating', { defaultValue: 'Creating...' })
              : t('boq.tender_create', { defaultValue: 'Create package' })}
          </button>
        </div>
      </div>
    </div>
  );
}
