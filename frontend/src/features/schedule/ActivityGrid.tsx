// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, RotateCcw, GitBranch, Diamond, Minus } from 'lucide-react';
import { Button, Badge, Card } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { listCalendars } from '@/features/schedule-advanced/api';
import { scheduleApi, type Activity } from './api';

const TYPES = ['task', 'milestone', 'summary'] as const;

const CELL_INPUT_CLS =
  'w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-sm text-content-primary ' +
  'hover:border-border-light focus:border-oe-blue focus:bg-surface-primary focus:outline-none disabled:opacity-60';

const DATE_INPUT_CLS =
  'rounded-md border border-transparent bg-transparent px-1.5 py-1 text-sm tabular-nums text-content-primary ' +
  'hover:border-border-light focus:border-oe-blue focus:bg-surface-primary focus:outline-none disabled:opacity-60';

/** Whole calendar-day count from ISO ``a`` to ISO ``b`` (b - a); may be negative. */
function isoDeltaDays(a: string, b: string): number {
  const ms = new Date(b).getTime() - new Date(a).getTime();
  if (Number.isNaN(ms)) return 0;
  return Math.round(ms / 86_400_000);
}

/** Add ``days`` calendar days to an ISO ``YYYY-MM-DD`` date (UTC, stays YYYY-MM-DD). */
function addDaysIso(iso: string, days: number): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/**
 * Editable activity grid - the schedule "Table" view.
 *
 * A spreadsheet-style table of every activity with inline-editable name, type,
 * start and end. Duration is shown read-only because it is *working* days:
 * the backend recomputes ``duration_days`` from the dates on every update using
 * the project's regional work calendar (skipping weekends / holidays), so it
 * cannot be honestly derived from a calendar-day span on the client. Editing the
 * start moves the whole bar (the end shifts by the same number of calendar days
 * so the span is preserved); editing the end changes the span.
 *
 * Each cell commit writes through the existing ``updateActivity`` PATCH (which
 * recomputes the working-day duration server-side) and refetches the Gantt. The
 * predecessors cell opens the shared #348 dependency editor via ``onEditDependencies``.
 * The explicit Reschedule button recomputes dates from the dependency network
 * (CPM) - activities with predecessors move, roots keep their manual start - so
 * a bulk edit does not silently overwrite typed dates mid-flight.
 */
export function ActivityGrid({
  scheduleId,
  projectId,
  activities,
  criticalActivityIds,
  onEditDependencies,
  onAddActivity,
}: {
  scheduleId: string;
  projectId: string;
  activities: Activity[];
  criticalActivityIds?: Set<string>;
  onEditDependencies: (activityId: string) => void;
  onAddActivity: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const invalidateGantt = () =>
    queryClient.invalidateQueries({ queryKey: ['gantt', scheduleId] });

  // #348: the project's named work calendars, for the per-row calendar picker.
  // Keyed by projectId so the picker and the WorkCalendarManager share a cache.
  const { data: calendars = [] } = useQuery({
    queryKey: ['schedule-calendars', projectId],
    queryFn: () => listCalendars(projectId),
    enabled: !!projectId,
  });

  // Optimistic value for the per-row calendar picker while its change is in
  // flight, keyed by activity id (value is the calendar id, or null for the
  // project default). The <select> is controlled off this map layered over the
  // stored calendar_id, so it shows the picked calendar immediately, reflects
  // the real calendar once the async calendar list loads, and reverts to the
  // stored value if the save fails.
  const [pendingCal, setPendingCal] = useState<Record<string, string | null>>({});
  const calendarValue = (a: Activity) =>
    a.id in pendingCal ? (pendingCal[a.id] ?? '') : (a.calendar_id ?? '');

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Activity> }) =>
      scheduleApi.updateActivity(id, body),
    onSuccess: invalidateGantt,
    onError: (error: Error) => {
      addToast({
        type: 'error',
        title: t('toasts.update_failed', { defaultValue: 'Update failed' }),
        message: error.message,
      });
      // Refetch so a rejected cell reverts to the stored value.
      invalidateGantt();
    },
  });

  const rescheduleMutation = useMutation({
    mutationFn: () => scheduleApi.reschedule(scheduleId),
    onSuccess: async () => {
      await invalidateGantt();
      addToast({
        type: 'success',
        title: t('schedule.rescheduled', { defaultValue: 'Schedule recalculated' }),
      });
    },
    onError: (error: Error) =>
      addToast({
        type: 'error',
        title: t('toasts.error', { defaultValue: 'Error' }),
        message: error.message,
      }),
  });

  // #348: assign (calendarId) or clear (null) an activity's work calendar, then
  // recompute dates from the network - working-day durations depend on the
  // calendar - and refetch the edges + bars. Mirrors DependencyEditor.afterChange().
  const setCalendarMutation = useMutation({
    mutationFn: ({ id, calendarId }: { id: string; calendarId: string | null }) =>
      scheduleApi.setActivityCalendar(id, calendarId),
    onSuccess: async () => {
      await scheduleApi.reschedule(scheduleId);
      await queryClient.invalidateQueries({ queryKey: ['schedule-relationships', scheduleId] });
      await queryClient.invalidateQueries({ queryKey: ['gantt', scheduleId] });
      addToast({
        type: 'success',
        title: t('schedule.calendar.assigned', { defaultValue: 'Calendar updated' }),
      });
    },
    onError: (error: Error) => {
      addToast({
        type: 'error',
        title: t('toasts.error', { defaultValue: 'Error' }),
        message: error.message,
      });
      invalidateGantt();
    },
    // Drop the optimistic value once the change settles: on success the gantt
    // has been refetched so the stored calendar_id now matches; on failure the
    // select falls back to the unchanged stored value.
    onSettled: (_data, _err, variables) => {
      setPendingCal((m) => {
        const next = { ...m };
        delete next[variables.id];
        return next;
      });
    },
  });

  const busy =
    updateMutation.isPending || rescheduleMutation.isPending || setCalendarMutation.isPending;
  // Only an operation that moves rows (a full reschedule, or a calendar change
  // that reschedules) locks editing; per-cell PATCHes leave the grid editable.
  const cellsDisabled = rescheduleMutation.isPending || setCalendarMutation.isPending;

  // ── Cell commit handlers ────────────────────────────────────────────────
  const commitName = (a: Activity, raw: string) => {
    const name = raw.trim();
    if (!name || name === a.name) return;
    updateMutation.mutate({ id: a.id, body: { name } });
  };

  const commitType = (a: Activity, type: string) => {
    if (type === a.activity_type) return;
    updateMutation.mutate({ id: a.id, body: { activity_type: type } });
  };

  const commitStart = (a: Activity, raw: string) => {
    const start = raw.slice(0, 10);
    const current = a.start_date.slice(0, 10);
    if (!start || start === current) return;
    if (Number.isNaN(new Date(start).getTime())) {
      invalidateGantt();
      return;
    }
    // Preserve the calendar span: shift the end by the same delta as the start.
    const delta = isoDeltaDays(current, start);
    const end = addDaysIso(a.end_date.slice(0, 10), delta);
    updateMutation.mutate({ id: a.id, body: { start_date: start, end_date: end } });
  };

  const commitEnd = (a: Activity, raw: string) => {
    const end = raw.slice(0, 10);
    const current = a.end_date.slice(0, 10);
    if (!end || end === current) return;
    const start = a.start_date.slice(0, 10);
    // Reject an end before the start (the backend would 422); refetch to revert.
    if (Number.isNaN(new Date(end).getTime()) || isoDeltaDays(start, end) < 0) {
      invalidateGantt();
      return;
    }
    updateMutation.mutate({ id: a.id, body: { end_date: end } });
  };

  const commitCalendar = (a: Activity, raw: string) => {
    // Empty value -> clear (fall back to the project default). No-op if unchanged.
    const next = raw || null;
    if ((a.calendar_id ?? null) === next) return;
    setPendingCal((m) => ({ ...m, [a.id]: next }));
    setCalendarMutation.mutate({ id: a.id, calendarId: next });
  };

  const columns = useMemo(
    () => [
      { key: 'wbs', label: t('schedule.wbs_code', { defaultValue: 'WBS' }), align: 'left' as const },
      { key: 'name', label: t('schedule.activity_name', { defaultValue: 'Activity' }), align: 'left' as const },
      { key: 'type', label: t('schedule.activity_type', { defaultValue: 'Type' }), align: 'left' as const },
      { key: 'start', label: t('schedule.start_date', { defaultValue: 'Start' }), align: 'left' as const },
      { key: 'end', label: t('schedule.end_date', { defaultValue: 'End' }), align: 'left' as const },
      { key: 'duration', label: t('schedule.duration', { defaultValue: 'Duration' }), align: 'right' as const },
      { key: 'progress', label: t('schedule.progress', { defaultValue: 'Progress' }), align: 'right' as const },
      { key: 'calendar', label: t('schedule.calendar.column', { defaultValue: 'Calendar' }), align: 'left' as const },
      { key: 'deps', label: t('schedule.predecessors', { defaultValue: 'Predecessors' }), align: 'left' as const },
    ],
    [t],
  );

  return (
    <Card padding="none" className="overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-light bg-surface-secondary/40 px-3 py-2">
        <span className="text-xs text-content-tertiary">
          {t('schedule.grid_hint', {
            defaultValue:
              'Edit names, dates and types inline. Duration is working days and updates automatically.',
          })}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus size={15} />}
            data-testid="grid-add-activity"
            disabled={busy}
            onClick={onAddActivity}
          >
            {t('schedule.add_activity', { defaultValue: 'Add activity' })}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={<RotateCcw size={15} />}
            data-testid="grid-reschedule"
            loading={rescheduleMutation.isPending}
            disabled={busy}
            onClick={() => rescheduleMutation.mutate()}
            title={t('schedule.reschedule_tooltip', {
              defaultValue:
                'Recompute dates from the dependency network (CPM). Activities with predecessors move; roots keep their manual start.',
            })}
          >
            {t('schedule.reschedule', { defaultValue: 'Reschedule' })}
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table
          data-testid="activity-grid"
          className="w-full min-w-[900px] border-collapse text-sm"
        >
          <thead>
            <tr className="border-b border-border-light bg-surface-secondary/30 text-2xs font-semibold uppercase tracking-wider text-content-tertiary">
              {columns.map((c) => (
                <th
                  key={c.key}
                  className={`px-3 py-2 font-semibold ${c.align === 'right' ? 'text-right' : 'text-left'}`}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {activities.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-3 py-6 text-center text-sm text-content-tertiary"
                >
                  {t('schedule.grid_empty', {
                    defaultValue: 'No activities match the current filter.',
                  })}
                </td>
              </tr>
            ) : (
              activities.map((a) => {
                const isCritical = criticalActivityIds?.has(a.id) ?? false;
                const depCount = a.dependencies?.length ?? 0;
                const isMilestone = a.activity_type === 'milestone';
                const isSummary = a.activity_type === 'summary';
                return (
                  <tr
                    key={a.id}
                    data-testid={`grid-row-${a.id}`}
                    className={`border-b border-border-light transition-colors hover:bg-surface-secondary/20${
                      isCritical ? ' bg-semantic-error/5' : ''
                    }`}
                  >
                    <td className="px-3 py-1.5 align-middle tabular-nums text-content-tertiary">
                      {a.wbs_code || '-'}
                    </td>
                    <td className="px-2 py-1.5 align-middle">
                      <div className="flex items-center gap-1.5">
                        {isCritical && (
                          <span className="shrink-0 rounded bg-semantic-error px-1 py-0.5 text-[9px] font-bold leading-none text-white">
                            CP
                          </span>
                        )}
                        {isMilestone && (
                          <Diamond size={11} className="shrink-0 text-oe-blue" fill="currentColor" />
                        )}
                        {isSummary && <Minus size={11} className="shrink-0 text-content-tertiary" />}
                        <input
                          key={`name-${a.id}-${a.name}`}
                          data-testid={`grid-name-${a.id}`}
                          aria-label={t('schedule.activity_name', { defaultValue: 'Activity name' })}
                          className={CELL_INPUT_CLS}
                          defaultValue={a.name}
                          disabled={cellsDisabled}
                          onBlur={(e) => commitName(a, e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') e.currentTarget.blur();
                          }}
                        />
                      </div>
                    </td>
                    <td className="px-2 py-1.5 align-middle">
                      <select
                        key={`type-${a.id}-${a.activity_type}`}
                        data-testid={`grid-type-${a.id}`}
                        aria-label={t('schedule.activity_type', { defaultValue: 'Type' })}
                        className={CELL_INPUT_CLS}
                        defaultValue={a.activity_type}
                        disabled={cellsDisabled}
                        onChange={(e) => commitType(a, e.target.value)}
                      >
                        {TYPES.map((tp) => (
                          <option key={tp} value={tp}>
                            {t(`schedule.type_${tp}`, { defaultValue: tp })}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-1.5 align-middle">
                      <input
                        type="date"
                        key={`start-${a.id}-${a.start_date}`}
                        data-testid={`grid-start-${a.id}`}
                        aria-label={t('schedule.start_date', { defaultValue: 'Start date' })}
                        className={DATE_INPUT_CLS}
                        defaultValue={a.start_date.slice(0, 10)}
                        disabled={cellsDisabled}
                        onBlur={(e) => commitStart(a, e.target.value)}
                      />
                    </td>
                    <td className="px-2 py-1.5 align-middle">
                      <input
                        type="date"
                        key={`end-${a.id}-${a.end_date}`}
                        data-testid={`grid-end-${a.id}`}
                        aria-label={t('schedule.end_date', { defaultValue: 'End date' })}
                        className={DATE_INPUT_CLS}
                        defaultValue={a.end_date.slice(0, 10)}
                        disabled={cellsDisabled}
                        onBlur={(e) => commitEnd(a, e.target.value)}
                      />
                    </td>
                    <td
                      data-testid={`grid-duration-${a.id}`}
                      className="px-3 py-1.5 text-right align-middle tabular-nums text-content-secondary"
                    >
                      {a.duration_days} {t('schedule.days_short', { defaultValue: 'd' })}
                    </td>
                    <td className="px-3 py-1.5 text-right align-middle">
                      <Badge variant={isCritical ? 'error' : 'neutral'} size="sm">
                        {a.progress_pct}%
                      </Badge>
                    </td>
                    <td className="px-2 py-1.5 align-middle">
                      <select
                        data-testid={`grid-calendar-${a.id}`}
                        aria-label={t('schedule.calendar.column', { defaultValue: 'Calendar' })}
                        className={CELL_INPUT_CLS}
                        value={calendarValue(a)}
                        disabled={cellsDisabled}
                        onChange={(e) => commitCalendar(a, e.target.value)}
                      >
                        <option value="">
                          {t('schedule.calendar.default_option', { defaultValue: 'Default' })}
                        </option>
                        {calendars.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-1.5 align-middle">
                      <button
                        type="button"
                        data-testid={`grid-deps-${a.id}`}
                        onClick={() => onEditDependencies(a.id)}
                        title={t('schedule.edit_predecessors', { defaultValue: 'Edit predecessors' })}
                        className="inline-flex items-center gap-1 rounded-md border border-border-light px-2 py-1 text-xs font-medium text-content-secondary transition-colors hover:border-oe-blue/40 hover:text-oe-blue"
                      >
                        <GitBranch size={13} className="shrink-0" />
                        {depCount > 0
                          ? String(depCount)
                          : t('schedule.add_predecessor', { defaultValue: 'Add predecessor' })}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
