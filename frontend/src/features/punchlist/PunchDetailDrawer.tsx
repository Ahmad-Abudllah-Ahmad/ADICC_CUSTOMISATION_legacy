// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Punch item detail drawer.
 *
 * A right-side slide-over that surfaces one snag end to end: the full status
 * lifecycle (closure stepper), the photo capture + gallery, the sheet-pin
 * location, and the core fields. Opened from the list rows, the kanban cards,
 * and the pin board.
 *
 * The item is (re)fetched by id so the drawer always reflects the latest state
 * after a transition or a photo change, seeded with whatever the caller already
 * had so the panel paints instantly.
 */

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Calendar, MapPin, RotateCcw, Tag, User } from 'lucide-react';
import clsx from 'clsx';
import { Badge, SideDrawer } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import {
  fetchPunchItem,
  transitionPunchStatus,
  type PunchItem,
  type PunchPriority,
  type PunchStatus,
} from './api';
import { PunchClosureStepper } from './PunchClosureStepper';
import { PunchPhotoGallery } from './PunchPhotoGallery';

const STATUS_VARIANT: Record<PunchStatus, 'error' | 'warning' | 'blue' | 'success' | 'neutral'> = {
  open: 'error',
  assigned: 'blue',
  in_progress: 'warning',
  resolved: 'blue',
  verified: 'success',
  closed: 'neutral',
};

const PRIORITY_VARIANT: Record<PunchPriority, 'neutral' | 'blue' | 'warning' | 'error'> = {
  low: 'neutral',
  medium: 'warning',
  high: 'error',
  critical: 'error',
};

/** Human title-case fallback for an enum-ish token (open_x -> Open X). */
function titleCase(value: string): string {
  return value
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-';
  try {
    return new Date(value).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return value;
  }
}

function Field({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ElementType;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0">
      <div className="mb-0.5 flex items-center gap-1 text-2xs font-semibold uppercase tracking-wider text-content-quaternary">
        <Icon size={12} className="shrink-0" />
        {label}
      </div>
      <div className="truncate text-sm text-content-secondary">{children}</div>
    </div>
  );
}

export function PunchDetailDrawer({
  itemId,
  projectId,
  initialItem,
  onClose,
  onOpenPinBoard,
}: {
  itemId: string;
  projectId: string;
  /** Item from the list, used as instant seed data while the fresh copy loads. */
  initialItem?: PunchItem;
  onClose: () => void;
  /** Jump to the pin board focused on this item's drawing (optional). */
  onOpenPinBoard?: (item: PunchItem) => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const { data: item } = useQuery({
    queryKey: ['punchlist', 'item', itemId],
    queryFn: () => fetchPunchItem(itemId),
    initialData: initialItem,
    enabled: Boolean(itemId),
  });

  const refresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['punchlist'] });
    qc.invalidateQueries({ queryKey: ['punchlist', 'item', itemId] });
    qc.invalidateQueries({ queryKey: ['punchlist-summary'] });
  }, [qc, itemId]);

  const transitionMut = useMutation({
    mutationFn: ({ next, notes }: { next: PunchStatus; notes?: string }) =>
      transitionPunchStatus(itemId, next, notes),
    onSuccess: (_data, vars) => {
      refresh();
      addToast({
        type: 'success',
        title: t('punch.status_updated', {
          defaultValue: 'Status updated to {{status}}',
          status: t(`punch.status_${vars.next}`, { defaultValue: titleCase(vars.next) }),
        }),
      });
    },
    onError: (e: Error) =>
      addToast({
        type: 'error',
        title: t('common.error', { defaultValue: 'Error' }),
        message: e.message,
      }),
  });

  if (!item) {
    return (
      <SideDrawer open onClose={onClose} title={t('punch.item_detail', { defaultValue: 'Punch item' })}>
        <div className="p-5 text-sm text-content-tertiary">
          {t('common.loading', { defaultValue: 'Loading...' })}
        </div>
      </SideDrawer>
    );
  }

  const assignee = item.assigned_to?.trim();
  const category = item.category;
  const hasPin =
    Boolean(item.document_id) && item.location_x != null && item.location_y != null;
  const history = item.reopen_history ?? [];

  return (
    <SideDrawer
      open
      onClose={onClose}
      busy={transitionMut.isPending}
      widthClass="max-w-2xl"
      title={item.title}
      subtitle={
        <span className="flex items-center gap-1.5">
          <Badge variant={STATUS_VARIANT[item.status]} size="sm">
            {t(`punch.status_${item.status}`, { defaultValue: titleCase(item.status) })}
          </Badge>
          <Badge variant={PRIORITY_VARIANT[item.priority]} size="sm">
            {t(`punch.priority_${item.priority}`, { defaultValue: titleCase(item.priority) })}
          </Badge>
        </span>
      }
    >
      <div className="space-y-6 p-5">
        {/* ── Closure stepper ─────────────────────────────────────────── */}
        <section>
          <PunchClosureStepper
            item={item}
            isPending={transitionMut.isPending}
            onTransition={(next, notes) => transitionMut.mutate({ next, notes })}
          />
        </section>

        {/* ── Core fields ─────────────────────────────────────────────── */}
        <section className="grid grid-cols-2 gap-4">
          <Field icon={Tag} label={t('punch.col_category', { defaultValue: 'Category' })}>
            {category
              ? t(`punch.category_${category}`, { defaultValue: titleCase(category) })
              : '-'}
          </Field>
          <Field icon={User} label={t('punch.field_assigned_to', { defaultValue: 'Assigned To' })}>
            {assignee || (
              <span className="text-content-quaternary">
                {t('punch.unassigned', { defaultValue: 'Unassigned' })}
              </span>
            )}
          </Field>
          <Field icon={Calendar} label={t('punch.field_due_date', { defaultValue: 'Due Date' })}>
            {formatDate(item.due_date)}
          </Field>
          <Field icon={Calendar} label={t('punch.created', { defaultValue: 'Created' })}>
            {formatDate(item.created_at)}
          </Field>
        </section>

        {/* ── Description ──────────────────────────────────────────────── */}
        {item.description?.trim() && (
          <section>
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-content-tertiary">
              {t('punch.field_description', { defaultValue: 'Description' })}
            </h4>
            <p className="whitespace-pre-wrap text-sm text-content-secondary">{item.description}</p>
          </section>
        )}

        {/* ── Resolution notes ────────────────────────────────────────── */}
        {item.resolution_notes?.trim() && (
          <section>
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-content-tertiary">
              {t('punch.resolution_notes', { defaultValue: 'Resolution notes' })}
            </h4>
            <p className="whitespace-pre-wrap text-sm text-content-secondary">
              {item.resolution_notes}
            </p>
          </section>
        )}

        {/* ── Sheet pin ───────────────────────────────────────────────── */}
        <section>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-content-tertiary">
            {t('punch.pin_section', { defaultValue: 'Drawing pin' })}
          </h4>
          {hasPin ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 text-sm text-content-secondary">
                <MapPin size={14} className="text-oe-blue" />
                {t('punch.pinned_at', {
                  defaultValue: 'Page {{page}} at ({{x}}, {{y}})',
                  page: item.page ?? 1,
                  x: (item.location_x ?? 0).toFixed(3),
                  y: (item.location_y ?? 0).toFixed(3),
                })}
              </span>
              {onOpenPinBoard && (
                <button
                  type="button"
                  onClick={() => onOpenPinBoard(item)}
                  className="inline-flex items-center gap-1 rounded-md text-xs font-medium text-oe-blue hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
                >
                  <MapPin size={12} />
                  {t('punch.open_pin_board', { defaultValue: 'Open on pin board' })}
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-content-tertiary">
                {t('punch.not_pinned', { defaultValue: 'Not pinned to a drawing yet.' })}
              </span>
              {onOpenPinBoard && (
                <button
                  type="button"
                  onClick={() => onOpenPinBoard(item)}
                  className="inline-flex items-center gap-1 rounded-md text-xs font-medium text-oe-blue hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
                >
                  <MapPin size={12} />
                  {t('punch.pin_on_board', { defaultValue: 'Pin on a drawing' })}
                </button>
              )}
            </div>
          )}
        </section>

        {/* ── Photos ──────────────────────────────────────────────────── */}
        <section>
          <PunchPhotoGallery item={item} projectId={projectId} onChanged={refresh} />
        </section>

        {/* ── Reopen history ──────────────────────────────────────────── */}
        {history.length > 0 && (
          <section>
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-content-tertiary">
              {t('punch.reopen_history', { defaultValue: 'Reopen history' })}
            </h4>
            <ul className="space-y-1.5">
              {history.map((entry, idx) => (
                <li
                  key={`${entry.reopened_at}-${idx}`}
                  className={clsx(
                    'flex items-start gap-2 rounded-md bg-surface-secondary/50 px-2.5 py-1.5 text-xs',
                    'text-content-secondary',
                  )}
                >
                  <RotateCcw size={13} className="mt-0.5 shrink-0 text-content-tertiary" />
                  <span className="min-w-0">
                    {t('punch.reopened_from', {
                      defaultValue: 'Reopened from {{status}} on {{date}}',
                      status: t(`punch.status_${entry.previous_status}`, {
                        defaultValue: titleCase(entry.previous_status),
                      }),
                      date: formatDate(entry.reopened_at),
                    })}
                    {entry.reason ? <span className="text-content-tertiary"> - {entry.reason}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </SideDrawer>
  );
}
