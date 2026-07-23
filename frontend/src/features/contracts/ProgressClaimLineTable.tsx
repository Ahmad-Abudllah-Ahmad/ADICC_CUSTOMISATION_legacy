// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// ProgressClaimLineTable — line-item breakdown of a progress claim.
//
// Read-only by default. When the claim is draft/submitted (editable) each
// row exposes an inline Edit → Save flow that PATCHes a single claim line
// and refetches. Money values are Decimal-as-string from the API and are
// rendered via the shared MoneyDisplay so currency formatting stays
// consistent (and we never blend currencies — every line is in the claim
// currency).

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Pencil, Check, X } from 'lucide-react';

import { Button, EmptyState } from '@/shared/ui';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import { updateClaimLine, type ProgressClaimLine } from './api';

function toNum(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === 'string' ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}

const inputCls =
  'h-8 w-full rounded-md border border-border bg-surface-primary px-2 text-right text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

export interface ProgressClaimLineTableProps {
  claimId: string;
  lines: ProgressClaimLine[];
  currency: string;
  /** When false the table is strictly read-only (no edit affordances). */
  editable: boolean;
  isLoading?: boolean;
}

export function ProgressClaimLineTable({
  claimId,
  lines,
  currency,
  editable,
  isLoading = false,
}: ProgressClaimLineTableProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <p className="py-4 text-sm text-content-tertiary">
        {t('common.loading', { defaultValue: 'Loading…' })}
      </p>
    );
  }

  if (lines.length === 0) {
    return (
      <EmptyState
        title={t('contracts.claim_no_lines', { defaultValue: 'No claim lines yet' })}
        description={t('contracts.claim_no_lines_desc', {
          defaultValue:
            'Populate this claim from progress observations to bill completed work.',
        })}
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="claim-line-table">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-3 py-2 text-left">
              {t('contracts.line', { defaultValue: 'Line' })}
            </th>
            <th className="px-3 py-2 text-right">
              {t('contracts.qty', { defaultValue: 'Qty' })}
            </th>
            <th className="px-3 py-2 text-right">
              {t('contracts.pct_complete', { defaultValue: '% complete' })}
            </th>
            <th className="px-3 py-2 text-right">
              {t('contracts.period_value', { defaultValue: 'Period value' })}
            </th>
            {editable && <th className="px-3 py-2 text-right" />}
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <ClaimLineRow
              key={line.id}
              claimId={claimId}
              line={line}
              currency={currency}
              editable={editable}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClaimLineRow({
  claimId,
  line,
  currency,
  editable,
}: {
  claimId: string;
  line: ProgressClaimLine;
  currency: string;
  editable: boolean;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [editing, setEditing] = useState(false);
  const [pct, setPct] = useState(String(toNum(line.period_completed_pct)));
  const [value, setValue] = useState(String(toNum(line.period_completed_value)));

  const saveMut = useMutation({
    mutationFn: () =>
      updateClaimLine(line.id, {
        period_completed_pct: Number(pct) || 0,
        period_completed_value: Number(value) || 0,
        // cumulative_completed_value is cumulative-to-date and is recomputed
        // server-side from prior non-rejected periods; the client must not
        // author it (sending the period value here corrupted earned-value and
        // the AIA 'previous' column).
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts', 'claim-lines', claimId] });
      qc.invalidateQueries({ queryKey: ['contracts', 'claim', claimId] });
      addToast({
        type: 'success',
        title: t('contracts.claim_line_saved', { defaultValue: 'Line saved' }),
      });
      setEditing(false);
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const startEdit = () => {
    setPct(String(toNum(line.period_completed_pct)));
    setValue(String(toNum(line.period_completed_value)));
    setEditing(true);
  };

  return (
    <tr className="border-t border-border-light hover:bg-surface-secondary">
      <td className="px-3 py-2 font-mono text-xs text-content-secondary">
        {line.contract_line_id.slice(0, 8)}
      </td>
      <td className="px-3 py-2 text-right text-content-secondary">
        {toNum(line.period_completed_qty).toLocaleString()}
      </td>
      <td className="px-3 py-2 text-right">
        {editing ? (
          <input
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={pct}
            onChange={(e) => setPct(e.target.value)}
            className={inputCls}
            aria-label={t('contracts.pct_complete', { defaultValue: '% complete' })}
          />
        ) : (
          `${toNum(line.period_completed_pct).toFixed(2)} %`
        )}
      </td>
      <td className="px-3 py-2 text-right font-medium">
        {editing ? (
          <input
            type="number"
            min={0}
            step="0.01"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className={inputCls}
            aria-label={t('contracts.period_value', { defaultValue: 'Period value' })}
          />
        ) : (
          <MoneyDisplay
            amount={toNum(line.period_completed_value)}
            currency={currency || undefined}
          />
        )}
      </td>
      {editable && (
        <td className="px-3 py-2 text-right">
          {editing ? (
            <div className="flex justify-end gap-1">
              <Button
                size="sm"
                variant="primary"
                icon={<Check size={12} />}
                onClick={() => saveMut.mutate()}
                loading={saveMut.isPending}
              >
                {t('common.save', { defaultValue: 'Save' })}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                icon={<X size={12} />}
                onClick={() => setEditing(false)}
                disabled={saveMut.isPending}
              >
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              icon={<Pencil size={12} />}
              onClick={startEdit}
            >
              {t('common.edit', { defaultValue: 'Edit' })}
            </Button>
          )}
        </td>
      )}
    </tr>
  );
}
