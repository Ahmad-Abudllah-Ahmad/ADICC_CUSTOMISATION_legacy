// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Field Time - the foreman's end-of-day record of who and which machine
 * worked, how long, and against which cost code. Scoped to the active
 * project: a summary, a filterable list of timesheets, and a full editor
 * (opened per timesheet) for adding cost-coded labour and plant lines and
 * running them through the submit / approve / reverse flow.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Clock, HardHat, Wrench, ChevronRight, Loader2 } from 'lucide-react';
import { Button, Badge, EmptyState, ErrorState, KpiBand, PageHeader } from '@/shared/ui';
import type { KpiBandItem } from '@/shared/ui';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import { todayLocalISO } from '@/shared/lib/dates';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { TimesheetEditor } from './TimesheetEditor';
import {
  listTimesheets,
  fetchTimesheetSummary,
  createTimesheet,
  formatHours,
  type FieldTimesheet,
  type TimesheetStatus,
} from './api';

type BadgeVariant = 'neutral' | 'blue' | 'success' | 'warning' | 'error';

const STATUS_BADGE: Record<TimesheetStatus, BadgeVariant> = {
  draft: 'neutral',
  submitted: 'warning',
  approved: 'success',
  reversed: 'error',
};

const STATUS_ORDER: TimesheetStatus[] = ['draft', 'submitted', 'approved', 'reversed'];

export function FieldTimePage() {
  const { t } = useTranslation();

  return (
    <div className="space-y-5">
      <PageHeader
        srTitle={t('field_time.title', { defaultValue: 'Field Time' })}
        subtitle={t('field_time.subtitle', {
          defaultValue:
            'Cost-coded, signed timesheets for the labour and plant that worked on site each day.',
        })}
      />
      <RequiresProject>
        <FieldTimeContent />
      </RequiresProject>
    </div>
  );
}

function FieldTimeContent() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const projectId = useProjectContextStore((s) => s.activeProjectId) ?? '';

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<TimesheetStatus | ''>('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const listQ = useQuery({
    queryKey: ['field-time', 'list', projectId, statusFilter, dateFrom, dateTo],
    queryFn: () =>
      listTimesheets(projectId, {
        status: statusFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: 200,
      }),
    enabled: !!projectId,
  });

  const summaryQ = useQuery({
    queryKey: ['field-time', 'summary', projectId],
    queryFn: () => fetchTimesheetSummary(projectId),
    enabled: !!projectId,
  });

  const createMut = useMutation({
    mutationFn: () => createTimesheet({ project_id: projectId, date: todayLocalISO() }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['field-time', 'list'] });
      queryClient.invalidateQueries({ queryKey: ['field-time', 'summary'] });
      setSelectedId(created.id);
    },
    onError: (e) =>
      addToast({ type: 'error', title: t('common.error', { defaultValue: 'Error' }), message: getErrorMessage(e) }),
  });

  const summary = summaryQ.data;
  const kpiItems = useMemo<KpiBandItem[]>(() => {
    if (!summary) return [];
    return [
      {
        key: 'total',
        label: t('field_time.kpi_total', { defaultValue: 'Timesheets' }),
        value: summary.total,
        icon: Clock,
      },
      {
        key: 'labour',
        label: t('field_time.labour_hours', { defaultValue: 'Labour hours' }),
        value: formatHours(summary.labour_hours),
        icon: HardHat,
        tone: 'blue' as const,
      },
      {
        key: 'plant',
        label: t('field_time.plant_hours', { defaultValue: 'Plant hours' }),
        value: formatHours(summary.plant_hours),
        icon: Wrench,
      },
      {
        key: 'submitted',
        label: t('field_time.kpi_awaiting', { defaultValue: 'Awaiting approval' }),
        value: summary.by_status.submitted ?? 0,
        tone: 'warning' as const,
      },
    ];
  }, [summary, t]);

  const timesheets = listQ.data ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as TimesheetStatus | '')}
            aria-label={t('field_time.filter_status', { defaultValue: 'Filter by status' })}
            className="h-9 rounded-lg border border-border-light bg-surface-primary px-3 text-sm text-content-primary"
          >
            <option value="">{t('field_time.all_statuses', { defaultValue: 'All statuses' })}</option>
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {t(`field_time.status_${s}`, { defaultValue: s })}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            aria-label={t('field_time.date_from', { defaultValue: 'From date' })}
            className="h-9 rounded-lg border border-border-light bg-surface-primary px-3 text-sm text-content-primary"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            aria-label={t('field_time.date_to', { defaultValue: 'To date' })}
            className="h-9 rounded-lg border border-border-light bg-surface-primary px-3 text-sm text-content-primary"
          />
        </div>
        <Button
          variant="primary"
          size="md"
          icon={<Plus size={16} />}
          loading={createMut.isPending}
          onClick={() => createMut.mutate()}
        >
          {t('field_time.new_timesheet', { defaultValue: 'New timesheet' })}
        </Button>
      </div>

      {kpiItems.length > 0 && <KpiBand items={kpiItems} />}

      {listQ.isLoading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-content-tertiary">
          <Loader2 size={16} className="animate-spin" />
          {t('common.loading', { defaultValue: 'Loading...' })}
        </div>
      ) : listQ.isError ? (
        <ErrorState
          title={t('field_time.list_failed', { defaultValue: 'Could not load timesheets' })}
          hint={getErrorMessage(listQ.error)}
          onRetry={() => listQ.refetch()}
        />
      ) : timesheets.length === 0 ? (
        <EmptyState
          icon={<Clock size={28} strokeWidth={1.5} />}
          title={t('field_time.empty_title', { defaultValue: 'No timesheets yet' })}
          description={t('field_time.empty_description', {
            defaultValue: 'Start a new timesheet to record the labour and plant that worked today.',
          })}
          action={{
            label: t('field_time.new_timesheet', { defaultValue: 'New timesheet' }),
            onClick: () => createMut.mutate(),
          }}
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {timesheets.map((ts) => (
            <li key={ts.id}>
              <TimesheetRow timesheet={ts} onOpen={() => setSelectedId(ts.id)} />
            </li>
          ))}
        </ul>
      )}

      {selectedId && (
        <TimesheetEditor
          timesheetId={selectedId}
          projectId={projectId}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}

function TimesheetRow({
  timesheet,
  onOpen,
}: {
  timesheet: FieldTimesheet;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-lg border border-border-light bg-surface-primary px-4 py-3 text-left transition-colors hover:bg-surface-secondary"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold text-content-primary">
            {timesheet.reference || t('field_time.untitled', { defaultValue: 'Draft timesheet' })}
          </span>
          <Badge variant={STATUS_BADGE[timesheet.status]} size="sm">
            {t(`field_time.status_${timesheet.status}`, { defaultValue: timesheet.status })}
          </Badge>
        </div>
        <div className="mt-0.5 text-xs text-content-tertiary">
          <DateDisplay value={timesheet.date} />
        </div>
      </div>
      <div className="hidden shrink-0 items-center gap-4 text-xs text-content-secondary sm:flex">
        <span className="inline-flex items-center gap-1 tabular-nums">
          <HardHat size={13} className="text-oe-blue" />
          {t('field_time.hours_value', {
            defaultValue: '{{hours}} h',
            hours: formatHours(timesheet.labour_hours),
          })}
        </span>
        <span className="inline-flex items-center gap-1 tabular-nums">
          <Wrench size={13} />
          {t('field_time.hours_value', {
            defaultValue: '{{hours}} h',
            hours: formatHours(timesheet.plant_hours),
          })}
        </span>
        <span className="tabular-nums">
          {t('field_time.lines_count', {
            defaultValue: '{{count}} lines',
            count: timesheet.lines.length,
          })}
        </span>
      </div>
      <ChevronRight size={16} className="shrink-0 text-content-tertiary" />
    </button>
  );
}
