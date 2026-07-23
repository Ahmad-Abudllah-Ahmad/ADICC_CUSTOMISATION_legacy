// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// PopulatePreviewModal — preview + commit the claim lines derived from the
// latest progress observations (Gap I bridge).
//
// Flow:
//   1. On open, GET /populate-from-progress returns the populatable lines
//      (SoV lines linked to a BOQ position that has an observation).
//   2. The user reviews, deselects rows they don't want, and sees a live
//      selected-count + selected-gross.
//   3. Commit PUTs /commit-populated-lines with only the selected rows; the
//      server re-rolls the claim totals and the parent refetches.
//
// Currency safety: every previewed value is in the claim currency. Lines in a
// different currency are skipped server-side and surfaced as a hint count, so
// the modal never blends currencies into one total.

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Download, AlertTriangle, Info } from 'lucide-react';

import { Button } from '@/shared/ui';
import {
  WideModal,
  WideModalSection,
} from '@/shared/ui/WideModal';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  populateClaimPreview,
  commitClaimLines,
  type ProgressClaimPopulatePreviewItem,
} from './api';

function toNum(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === 'string' ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}

export interface PopulatePreviewModalProps {
  claimId: string;
  currency: string;
  onClose: () => void;
  onCommitted?: () => void;
}

export function PopulatePreviewModal({
  claimId,
  currency,
  onClose,
  onCommitted,
}: PopulatePreviewModalProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const previewQ = useQuery({
    queryKey: ['contracts', 'populate-preview', claimId],
    queryFn: () => populateClaimPreview(claimId),
  });

  // contract_line_id set of the rows the user wants to commit. Defaults to
  // "all previewed rows selected" once the preview arrives.
  const [deselected, setDeselected] = useState<Set<string>>(new Set());

  const items = previewQ.data?.items ?? [];
  const previewCurrency = previewQ.data?.currency || currency;

  const selectedItems = useMemo(
    () => items.filter((it) => !deselected.has(it.contract_line_id)),
    [items, deselected],
  );

  const selectedGross = useMemo(
    () =>
      selectedItems.reduce(
        (acc, it) => acc + toNum(it.period_completed_value),
        0,
      ),
    [selectedItems],
  );

  const toggle = (id: string) => {
    setDeselected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const commitMut = useMutation({
    mutationFn: () =>
      commitClaimLines(
        claimId,
        selectedItems.map((it) => ({
          contract_line_id: it.contract_line_id,
          period_completed_pct: toNum(it.observed_pct),
          period_completed_value: toNum(it.period_completed_value),
        })),
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts', 'claim', claimId] });
      qc.invalidateQueries({ queryKey: ['contracts', 'claim-lines', claimId] });
      addToast({
        type: 'success',
        title: t('contracts.populate_committed', {
          defaultValue: 'Claim populated from progress',
        }),
      });
      onCommitted?.();
      onClose();
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const skippedHints: string[] = [];
  if (previewQ.data) {
    if (previewQ.data.skipped_unlinked > 0) {
      skippedHints.push(
        t('contracts.populate_skipped_unlinked', {
          count: previewQ.data.skipped_unlinked,
          defaultValue:
            '{{count}} schedule-of-values line(s) skipped: not linked to a BOQ position.',
        }),
      );
    }
    if (previewQ.data.skipped_no_progress > 0) {
      skippedHints.push(
        t('contracts.populate_skipped_no_progress', {
          count: previewQ.data.skipped_no_progress,
          defaultValue:
            '{{count}} linked line(s) skipped: no progress observation recorded yet.',
        }),
      );
    }
    if (previewQ.data.skipped_foreign_currency > 0) {
      skippedHints.push(
        t('contracts.populate_skipped_currency', {
          count: previewQ.data.skipped_foreign_currency,
          defaultValue:
            '{{count}} line(s) skipped: a different currency than this claim (never blended).',
        }),
      );
    }
  }

  const emptyPreview = !previewQ.isLoading && items.length === 0;

  return (
    <WideModal
      open
      onClose={onClose}
      title={t('contracts.populate_title', {
        defaultValue: 'Populate from progress observations',
      })}
      subtitle={t('contracts.populate_subtitle', {
        defaultValue:
          'Review the values derived from the latest field observations, deselect any you do not want, then commit.',
      })}
      size="xl"
      busy={commitMut.isPending}
      footer={
        <>
          <div className="mr-auto text-sm text-content-secondary" data-testid="populate-selected-summary">
            {t('contracts.populate_selected', {
              count: selectedItems.length,
              defaultValue: '{{count}} selected',
            })}
            {' · '}
            <MoneyDisplay amount={selectedGross} currency={previewCurrency || undefined} />
          </div>
          <Button variant="ghost" onClick={onClose} disabled={commitMut.isPending}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            onClick={() => commitMut.mutate()}
            loading={commitMut.isPending}
            disabled={selectedItems.length === 0 || previewQ.isLoading}
            icon={commitMut.isPending ? <Loader2 size={14} /> : <Download size={14} />}
          >
            {t('contracts.populate_commit', { defaultValue: 'Commit lines' })}
          </Button>
        </>
      }
    >
      <WideModalSection>
        {skippedHints.length > 0 && (
          <div
            className="mb-3 flex flex-col gap-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
            role="status"
          >
            {skippedHints.map((h) => (
              <span key={h} className="flex items-center gap-1.5">
                <Info size={12} aria-hidden />
                {h}
              </span>
            ))}
          </div>
        )}

        {previewQ.isLoading ? (
          <p className="py-6 text-center text-sm text-content-tertiary">
            <Loader2 size={16} className="mr-2 inline animate-spin" />
            {t('common.loading', { defaultValue: 'Loading…' })}
          </p>
        ) : emptyPreview ? (
          <div
            className="flex items-center gap-2 rounded-lg border border-border-light bg-surface-secondary px-3 py-4 text-sm text-content-secondary"
            role="alert"
            data-testid="populate-empty"
          >
            <AlertTriangle size={16} className="text-amber-500" aria-hidden />
            {t('contracts.populate_empty', {
              defaultValue:
                'No progress observations are available for this contract in the current period. Record field progress against BOQ-linked schedule-of-values lines, then try again.',
            })}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="populate-preview-table">
              <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-3 py-2 text-left">
                    <span className="sr-only">
                      {t('contracts.populate_include', { defaultValue: 'Include' })}
                    </span>
                  </th>
                  <th className="px-3 py-2 text-left">
                    {t('contracts.line', { defaultValue: 'Line' })}
                  </th>
                  <th className="px-3 py-2 text-right">
                    {t('contracts.pct_complete', { defaultValue: '% complete' })}
                  </th>
                  <th className="px-3 py-2 text-right">
                    {t('contracts.line_value', { defaultValue: 'Line value' })}
                  </th>
                  <th className="px-3 py-2 text-right">
                    {t('contracts.period_value', { defaultValue: 'Period value' })}
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <PreviewRow
                    key={it.contract_line_id}
                    item={it}
                    currency={previewCurrency}
                    selected={!deselected.has(it.contract_line_id)}
                    onToggle={() => toggle(it.contract_line_id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </WideModalSection>
    </WideModal>
  );
}

function PreviewRow({
  item,
  currency,
  selected,
  onToggle,
}: {
  item: ProgressClaimPopulatePreviewItem;
  currency: string;
  selected: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  return (
    <tr className="border-t border-border-light hover:bg-surface-secondary">
      <td className="px-3 py-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={t('contracts.populate_include_line', {
            code: item.contract_line_code || item.contract_line_id.slice(0, 8),
            defaultValue: 'Include line {{code}}',
          })}
          className="h-4 w-4 rounded border-border accent-oe-blue"
        />
      </td>
      <td className="px-3 py-2">
        <div className="font-mono text-xs text-content-secondary">
          {item.contract_line_code || item.contract_line_id.slice(0, 8)}
        </div>
        {item.contract_line_description && (
          <div className="max-w-[280px] truncate text-content-primary">
            {item.contract_line_description}
          </div>
        )}
      </td>
      <td className="px-3 py-2 text-right">
        {toNum(item.observed_pct).toFixed(2)} %
      </td>
      <td className="px-3 py-2 text-right text-content-secondary">
        <MoneyDisplay
          amount={toNum(item.contract_line_value)}
          currency={currency || undefined}
        />
      </td>
      <td className="px-3 py-2 text-right font-medium">
        <MoneyDisplay
          amount={toNum(item.period_completed_value)}
          currency={currency || undefined}
        />
      </td>
    </tr>
  );
}
