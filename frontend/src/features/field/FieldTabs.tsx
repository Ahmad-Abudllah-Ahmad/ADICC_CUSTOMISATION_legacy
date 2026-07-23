// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Field shell tab bodies — Today / Capture / Crew.
 *
 * All three are thumb-zone, large-target (>=48px) mobile surfaces. Writes are
 * captured through the offline mutation queue (`enqueue`) so they survive a
 * dropped site connection; reads use the authenticated field API client. There
 * is no second queue here: this reuses the v6.8 offline slice.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, Plus, Play, Square, RefreshCw } from 'lucide-react';
import { newClientOpId, type EnqueueInput } from '@/shared/lib/offline';
import {
  listEntries,
  todayIso,
  type DiaryEntry,
  type FieldSession,
} from './fieldApi';

type Enqueue = (input: EnqueueInput) => Promise<void>;

/** Tasks a field worker can tag time against (free pilot set; extend per-project). */
const TASKS = ['general', 'concrete', 'formwork', 'rebar', 'masonry', 'mep', 'finishes'] as const;

/* ── Today ─────────────────────────────────────────────────────────────── */

export function TodayTab({ session }: { session: FieldSession | null }) {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    try {
      setEntries(await listEntries(session, todayIso()));
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!session) {
    return (
      <p className="px-4 py-8 text-center text-slate-400">
        {t('field.no_session', { defaultValue: 'Open the link from your SMS to start.' })}
      </p>
    );
  }

  return (
    <div className="flex w-full flex-col gap-3 px-4 py-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">
          {t('field.today_title', { defaultValue: "Today's diary" })}
        </h2>
        <button
          type="button"
          aria-label={t('field.refresh', { defaultValue: 'Refresh' })}
          onClick={() => void refresh()}
          className="flex h-11 w-11 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100"
        >
          <RefreshCw size={20} className={loading ? 'animate-spin' : ''} aria-hidden="true" />
        </button>
      </div>
      {entries.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">
          {t('field.today_empty', { defaultValue: 'No entry yet today. Use Capture to log your time.' })}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {entries.map((e) => (
            <li key={e.id} className="rounded-xl border border-slate-200 p-3">
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-900">{e.entry_date}</span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {t(`field.status.${e.status}`, { defaultValue: e.status })}
                </span>
              </div>
              {e.notes_md && <p className="mt-1 text-sm text-slate-500">{e.notes_md}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ── Capture (start/end time + task) ───────────────────────────────────── */

export function CaptureTab({
  session,
  enqueue,
}: {
  session: FieldSession | null;
  enqueue: Enqueue;
}) {
  const { t } = useTranslation();
  const [task, setTask] = useState<string>('general');
  const [start, setStart] = useState('07:00');
  const [end, setEnd] = useState('16:00');
  const [note, setNote] = useState('');
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const hoursBetween = (s: string, e: string): number => {
    const [sh = 0, sm = 0] = s.split(':').map(Number);
    const [eh = 0, em = 0] = e.split(':').map(Number);
    const mins = eh * 60 + em - (sh * 60 + sm);
    return mins > 0 ? Math.round((mins / 60) * 100) / 100 : 0;
  };

  const submit = useCallback(async () => {
    if (!session) return;
    const date = todayIso();
    const hours = hoursBetween(start, end);
    // 1) Ensure today's diary entry exists (idempotent server-side on
    //    (project, author, date) via its unique constraint; a 409 on replay is
    //    treated as already-applied by the queue).
    const entryOpId = newClientOpId();
    await enqueue({
      clientOpId: entryOpId,
      method: 'POST',
      path: `/v1/field-diary/entries/`,
      kind: 'field.diary.entry',
      body: { project_id: session.projectId, entry_date: date },
    });
    // 2) Append the time activity. The entry id is resolved server-side from the
    //    session+date, so the activity carries the date and the queue replays it
    //    after the entry create (FIFO ordering is guaranteed by the queue).
    await enqueue({
      method: 'POST',
      path: `/v1/field-diary/entries/by-date/${date}/activities/`,
      kind: 'field.diary.activity',
      body: {
        activity_type: 'work',
        description: note || task,
        hours: String(hours),
        started_at: `${date}T${start}:00`,
        ended_at: `${date}T${end}:00`,
        metadata: { task },
      },
    });
    setSavedAt(Date.now());
    setNote('');
  }, [session, start, end, note, task, enqueue]);

  if (!session) {
    return (
      <p className="px-4 py-8 text-center text-slate-400">
        {t('field.no_session', { defaultValue: 'Open the link from your SMS to start.' })}
      </p>
    );
  }

  const hours = hoursBetween(start, end);

  return (
    <div className="flex w-full flex-col gap-4 px-4 py-4">
      <h2 className="text-base font-semibold text-slate-900">
        {t('field.capture_title', { defaultValue: 'Log my time' })}
      </h2>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-slate-600">{t('field.task', { defaultValue: 'Task' })}</span>
        <select
          value={task}
          onChange={(e) => setTask(e.target.value)}
          className="h-12 rounded-xl border border-slate-300 px-3 text-base"
        >
          {TASKS.map((tk) => (
            <option key={tk} value={tk}>
              {t(`field.task_opt.${tk}`, { defaultValue: tk })}
            </option>
          ))}
        </select>
      </label>

      <div className="flex gap-3">
        <label className="flex flex-1 flex-col gap-1 text-sm">
          <span className="text-slate-600">{t('field.start', { defaultValue: 'Start' })}</span>
          <input
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="h-12 rounded-xl border border-slate-300 px-3 text-base"
          />
        </label>
        <label className="flex flex-1 flex-col gap-1 text-sm">
          <span className="text-slate-600">{t('field.end', { defaultValue: 'End' })}</span>
          <input
            type="time"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="h-12 rounded-xl border border-slate-300 px-3 text-base"
          />
        </label>
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-slate-600">{t('field.note', { defaultValue: 'Note (optional)' })}</span>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="h-12 rounded-xl border border-slate-300 px-3 text-base"
        />
      </label>

      <p className="text-sm text-slate-500">
        {t('field.hours_total', { defaultValue: '{{hours}} h', hours })}
      </p>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={hours <= 0}
        className="flex h-14 items-center justify-center gap-2 rounded-xl bg-sky-600 text-base font-semibold text-white disabled:opacity-50"
      >
        <Plus size={20} aria-hidden="true" />
        {t('field.save_time', { defaultValue: 'Save time' })}
      </button>
      {savedAt && (
        <p className="text-center text-sm text-emerald-600">
          {t('field.saved_offline', {
            defaultValue: 'Saved. Will sync when online.',
          })}
        </p>
      )}
    </div>
  );
}

/* ── Crew (punch in / out) ─────────────────────────────────────────────── */

interface CrewMember {
  id: string;
  name: string;
  task: string;
  /** ISO time when the punch-in started, or null when not punched in. */
  startedAt: string | null;
}

export function CrewTab({
  session,
  enqueue,
}: {
  session: FieldSession | null;
  enqueue: Enqueue;
}) {
  const { t } = useTranslation();
  const [crew, setCrew] = useState<CrewMember[]>([]);
  const [name, setName] = useState('');

  const addMember = useCallback(() => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setCrew((c) => [...c, { id: newClientOpId(), name: trimmed, task: 'general', startedAt: null }]);
    setName('');
  }, [name]);

  const punchIn = useCallback((id: string) => {
    setCrew((c) =>
      c.map((m) => (m.id === id ? { ...m, startedAt: new Date().toISOString() } : m)),
    );
  }, []);

  const punchOut = useCallback(
    async (id: string) => {
      const member = crew.find((m) => m.id === id);
      if (!member || !member.startedAt || !session) return;
      const date = todayIso();
      const startedAt = member.startedAt;
      const endedAt = new Date().toISOString();
      const hours =
        Math.round(((Date.parse(endedAt) - Date.parse(startedAt)) / 3_600_000) * 100) / 100;

      // Reuse the diary pipeline: ensure today's entry, then append the crew
      // member's punch as a work activity. Captured through the offline queue.
      await enqueue({
        clientOpId: newClientOpId(),
        method: 'POST',
        path: `/v1/field-diary/entries/`,
        kind: 'field.diary.entry',
        body: { project_id: session.projectId, entry_date: date },
      });
      await enqueue({
        method: 'POST',
        path: `/v1/field-diary/entries/by-date/${date}/activities/`,
        kind: 'field.crew.punch',
        body: {
          activity_type: 'work',
          description: `${member.name} - ${member.task}`,
          hours: String(hours > 0 ? hours : 0),
          started_at: startedAt,
          ended_at: endedAt,
          metadata: { task: member.task, crew_member: member.name },
        },
      });
      setCrew((c) => c.map((m) => (m.id === id ? { ...m, startedAt: null } : m)));
    },
    [crew, session, enqueue],
  );

  if (!session) {
    return (
      <p className="px-4 py-8 text-center text-slate-400">
        {t('field.no_session', { defaultValue: 'Open the link from your SMS to start.' })}
      </p>
    );
  }

  return (
    <div className="flex w-full flex-col gap-4 px-4 py-4">
      <h2 className="text-base font-semibold text-slate-900">
        {t('field.crew_title', { defaultValue: 'Crew time' })}
      </h2>

      <div className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('field.crew_name', { defaultValue: 'Crew member name' })}
          className="h-12 flex-1 rounded-xl border border-slate-300 px-3 text-base"
        />
        <button
          type="button"
          onClick={addMember}
          aria-label={t('field.crew_add', { defaultValue: 'Add crew member' })}
          className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-700"
        >
          <Plus size={22} aria-hidden="true" />
        </button>
      </div>

      {crew.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">
          {t('field.crew_empty', { defaultValue: 'Add a crew member to punch them in.' })}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {crew.map((m) => (
            <li key={m.id} className="rounded-xl border border-slate-200 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-900">{m.name}</p>
                  <select
                    value={m.task}
                    onChange={(e) =>
                      setCrew((c) =>
                        c.map((x) => (x.id === m.id ? { ...x, task: e.target.value } : x)),
                      )
                    }
                    className="mt-1 h-10 w-full rounded-lg border border-slate-200 px-2 text-sm"
                  >
                    {TASKS.map((tk) => (
                      <option key={tk} value={tk}>
                        {t(`field.task_opt.${tk}`, { defaultValue: tk })}
                      </option>
                    ))}
                  </select>
                </div>
                {m.startedAt ? (
                  <button
                    type="button"
                    onClick={() => void punchOut(m.id)}
                    className="flex h-12 items-center gap-1 rounded-xl bg-rose-600 px-4 font-semibold text-white"
                  >
                    <Square size={18} aria-hidden="true" />
                    {t('field.punch_out', { defaultValue: 'Out' })}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => punchIn(m.id)}
                    className="flex h-12 items-center gap-1 rounded-xl bg-emerald-600 px-4 font-semibold text-white"
                  >
                    <Play size={18} aria-hidden="true" />
                    {t('field.punch_in', { defaultValue: 'In' })}
                  </button>
                )}
              </div>
              {m.startedAt && (
                <p className="mt-2 flex items-center gap-1 text-xs text-emerald-600">
                  <Clock size={14} aria-hidden="true" />
                  {t('field.punched_in_since', {
                    defaultValue: 'In since {{time}}',
                    time: new Date(m.startedAt).toLocaleTimeString(),
                  })}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
