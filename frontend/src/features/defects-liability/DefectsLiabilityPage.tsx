// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useState, useEffect, useMemo, useCallback, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import clsx from 'clsx';
import {
  ShieldCheck, ShieldAlert, Clock, AlertTriangle, CircleDollarSign, Plus, X,
  Pencil, Trash2, ChevronDown, CalendarClock, Wrench, FileWarning, Building2,
} from 'lucide-react';
import { Button, Card, Badge, EmptyState, ConfirmDialog } from '@/shared/ui';
import { PageHeader } from '@/shared/ui/PageHeader';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { useConfirm } from '@/shared/hooks/useConfirm';
import { useToastStore } from '@/stores/useToastStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  fetchWarranties, createWarranty, updateWarranty, deleteWarranty,
  fetchDefects, createDefect, updateDefect, fetchRegister, fetchRetentionReadiness,
  WARRANTY_TYPES, WARRANTY_STATUSES, DEFECT_STATUSES, DEFECT_SEVERITIES,
  type Warranty, type WarrantyCreate, type WarrantyType, type WarrantyStatus,
  type Defect, type DefectCreate, type DefectStatus, type DefectSeverity,
  type DlpRegister, type RetentionReleaseReadiness,
} from './api';

type BadgeVariant = 'neutral' | 'blue' | 'success' | 'warning' | 'error';

/* -- Styling + vocab metadata --------------------------------------------- */

const inputCls =
  'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
const textareaCls =
  'w-full rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue resize-none';
const selectCls =
  'h-10 w-full appearance-none rounded-lg border border-border bg-surface-primary pl-3 pr-9 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

const WARRANTY_STATUS_VARIANT: Record<WarrantyStatus, BadgeVariant> = {
  in_dlp: 'blue', expiring: 'warning', expired: 'error', closed: 'success', on_hold: 'neutral',
};
const WARRANTY_TYPE_VARIANT: Record<WarrantyType, BadgeVariant> = {
  workmanship: 'blue', manufacturer: 'success', latent_defect: 'warning', extended: 'neutral', other: 'neutral',
};
const DEFECT_SEVERITY_VARIANT: Record<DefectSeverity, BadgeVariant> = {
  minor: 'neutral', major: 'warning', critical: 'error',
};

const HORIZON_FALLBACK = 30;

/* -- Pure helpers ---------------------------------------------------------- */

const humanize = (v: string): string => v.replace(/_/g, ' ');
const todayIso = (): string => new Date().toISOString().slice(0, 10);

function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Row highlight: past its DLP end, or ending within the horizon (not closed). */
function warrantyFlag(w: Warranty, today: string, horizonEnd: string): 'expired' | 'expiring' | null {
  if (w.status === 'closed' || !w.dlp_end_date) return null;
  if (w.dlp_end_date < today) return 'expired';
  if (w.dlp_end_date <= horizonEnd) return 'expiring';
  return null;
}

/** An open/rectifying defect past its due date. */
function isDefectOverdue(d: Defect, today: string): boolean {
  if (!d.due_date || (d.status !== 'open' && d.status !== 'rectifying')) return false;
  return d.due_date < today;
}

const warrantyStatusVariant = (s: string): BadgeVariant => WARRANTY_STATUS_VARIANT[s as WarrantyStatus] ?? 'neutral';
const warrantyTypeVariant = (ty: string | null): BadgeVariant => (ty ? WARRANTY_TYPE_VARIANT[ty as WarrantyType] ?? 'neutral' : 'neutral');
const defectSeverityVariant = (s: string | null): BadgeVariant => (s ? DEFECT_SEVERITY_VARIANT[s as DefectSeverity] ?? 'neutral' : 'neutral');

/* -- Small shared bits ----------------------------------------------------- */

function Field({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-content-secondary">
        {label}
        {required && <span className="text-semantic-error"> *</span>}
      </span>
      {children}
    </label>
  );
}

function SelectShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative">
      {children}
      <ChevronDown size={14} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-content-tertiary" />
    </div>
  );
}

function ModalShell({ title, onClose, children, footer, wide }: {
  title: string; onClose: () => void; children: ReactNode; footer: ReactNode; wide?: boolean;
}) {
  const { t } = useTranslation();
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-lg animate-fade-in">
      <div role="dialog" aria-modal="true" className={clsx('mx-4 max-h-[90vh] w-full overflow-y-auto rounded-xl border border-border bg-surface-elevated shadow-xl animate-card-in', wide ? 'max-w-2xl' : 'max-w-xl')}>
        <div className="flex items-center justify-between border-b border-border-light px-6 py-4">
          <h2 className="text-lg font-semibold text-content-primary">{title}</h2>
          <button onClick={onClose} aria-label={t('defects_liability.close', { defaultValue: 'Close' })}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-content-tertiary hover:bg-surface-secondary hover:text-content-primary">
            <X size={18} />
          </button>
        </div>
        <div className="space-y-4 px-6 py-5">{children}</div>
        <div className="flex items-center justify-end gap-3 border-t border-border-light px-6 py-4">{footer}</div>
      </div>
    </div>
  );
}

/* -- Warranty modal (create + edit) ---------------------------------------- */

interface WarrantyFormState {
  reference: string; title: string; subcontractor_name: string; warranty_type: WarrantyType | '';
  status: WarrantyStatus; warranty_start_date: string; warranty_end_date: string; dlp_end_date: string;
  element_description: string;
}

function warrantyToForm(w: Warranty | null): WarrantyFormState {
  return {
    reference: w?.reference ?? '', title: w?.title ?? '', subcontractor_name: w?.subcontractor_name ?? '',
    warranty_type: w?.warranty_type ?? '', status: w?.status ?? 'in_dlp',
    warranty_start_date: w?.warranty_start_date ?? '', warranty_end_date: w?.warranty_end_date ?? '',
    dlp_end_date: w?.dlp_end_date ?? '', element_description: w?.element_description ?? '',
  };
}

function buildWarrantyPayload(f: WarrantyFormState): WarrantyCreate {
  return {
    reference: f.reference.trim(), title: f.title.trim(),
    subcontractor_name: f.subcontractor_name.trim() || null,
    warranty_type: f.warranty_type || null, status: f.status,
    warranty_start_date: f.warranty_start_date || null, warranty_end_date: f.warranty_end_date || null,
    dlp_end_date: f.dlp_end_date || null, element_description: f.element_description.trim() || null,
  };
}

function WarrantyModal({ editing, isPending, onClose, onSubmit }: {
  editing: Warranty | null; isPending: boolean; onClose: () => void; onSubmit: (payload: WarrantyCreate) => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<WarrantyFormState>(() => warrantyToForm(editing));
  const [touched, setTouched] = useState(false);
  const set = <K extends keyof WarrantyFormState>(k: K, v: WarrantyFormState[K]) => setForm((p) => ({ ...p, [k]: v }));

  const refError = touched && form.reference.trim().length === 0;
  const titleError = touched && form.title.trim().length === 0;
  const canSubmit = form.reference.trim().length > 0 && form.title.trim().length > 0;
  const submit = () => { setTouched(true); if (canSubmit) onSubmit(buildWarrantyPayload(form)); };

  return (
    <ModalShell
      wide
      onClose={onClose}
      title={editing
        ? t('defects_liability.modal_edit_warranty', { defaultValue: 'Edit warranty' })
        : t('defects_liability.modal_new_warranty', { defaultValue: 'New warranty' })}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>{t('defects_liability.cancel', { defaultValue: 'Cancel' })}</Button>
          <Button variant="primary" onClick={submit} disabled={isPending || !canSubmit} loading={isPending}>
            {editing ? t('defects_liability.save', { defaultValue: 'Save' }) : t('defects_liability.create', { defaultValue: 'Create warranty' })}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label={t('defects_liability.field_reference', { defaultValue: 'Reference' })} required>
          <input value={form.reference} onChange={(e) => set('reference', e.target.value)} autoFocus
            placeholder={t('defects_liability.field_reference_ph', { defaultValue: 'e.g. W-001' })}
            className={clsx(inputCls, refError && 'border-semantic-error')} />
          {refError && <span className="mt-1 block text-xs text-semantic-error">{t('defects_liability.reference_required', { defaultValue: 'Reference is required' })}</span>}
        </Field>
        <Field label={t('defects_liability.field_status', { defaultValue: 'Status' })}>
          <SelectShell>
            <select value={form.status} onChange={(e) => set('status', e.target.value as WarrantyStatus)} className={selectCls}>
              {WARRANTY_STATUSES.map((s) => <option key={s} value={s}>{t(`defects_liability.warranty_status_${s}`, { defaultValue: humanize(s) })}</option>)}
            </select>
          </SelectShell>
        </Field>
      </div>

      <Field label={t('defects_liability.field_item', { defaultValue: 'Item / element' })} required>
        <input value={form.title} onChange={(e) => set('title', e.target.value)}
          placeholder={t('defects_liability.field_item_ph', { defaultValue: 'e.g. Curtain wall, Level 3 to 8' })}
          className={clsx(inputCls, titleError && 'border-semantic-error')} />
        {titleError && <span className="mt-1 block text-xs text-semantic-error">{t('defects_liability.item_required', { defaultValue: 'Item is required' })}</span>}
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label={t('defects_liability.field_subcontractor', { defaultValue: 'Subcontractor' })}>
          <input value={form.subcontractor_name} onChange={(e) => set('subcontractor_name', e.target.value)}
            placeholder={t('defects_liability.field_subcontractor_ph', { defaultValue: 'Responsible firm' })} className={inputCls} />
        </Field>
        <Field label={t('defects_liability.field_type', { defaultValue: 'Cover type' })}>
          <SelectShell>
            <select value={form.warranty_type} onChange={(e) => set('warranty_type', e.target.value as WarrantyType | '')} className={selectCls}>
              <option value="">{t('defects_liability.warranty_type_none', { defaultValue: 'Unspecified' })}</option>
              {WARRANTY_TYPES.map((ty) => <option key={ty} value={ty}>{t(`defects_liability.warranty_type_${ty}`, { defaultValue: humanize(ty) })}</option>)}
            </select>
          </SelectShell>
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Field label={t('defects_liability.field_warranty_start', { defaultValue: 'Warranty start' })}>
          <input type="date" value={form.warranty_start_date} onChange={(e) => set('warranty_start_date', e.target.value)} className={inputCls} />
        </Field>
        <Field label={t('defects_liability.field_warranty_end', { defaultValue: 'Warranty end' })}>
          <input type="date" value={form.warranty_end_date} onChange={(e) => set('warranty_end_date', e.target.value)} className={inputCls} />
        </Field>
        <Field label={t('defects_liability.field_dlp_end', { defaultValue: 'DLP end date' })}>
          <input type="date" value={form.dlp_end_date} onChange={(e) => set('dlp_end_date', e.target.value)} className={inputCls} />
        </Field>
      </div>

      <Field label={t('defects_liability.field_coverage', { defaultValue: 'Coverage / element description' })}>
        <textarea value={form.element_description} onChange={(e) => set('element_description', e.target.value)} rows={2}
          placeholder={t('defects_liability.field_coverage_ph', { defaultValue: 'What this warranty covers' })} className={textareaCls} />
      </Field>
    </ModalShell>
  );
}

/* -- Defect modal (create) ------------------------------------------------- */

interface DefectFormState {
  warranty_id: string; reference: string; description: string; severity: DefectSeverity | '';
  status: DefectStatus; raised_date: string; due_date: string; responsible_party: string;
}

function buildDefectPayload(f: DefectFormState): DefectCreate {
  return {
    reference: f.reference.trim(), description: f.description.trim(), severity: f.severity || null,
    status: f.status, raised_date: f.raised_date || null, due_date: f.due_date || null,
    responsible_party: f.responsible_party.trim() || null,
  };
}

function DefectModal({ warranties, preselectWarrantyId, isPending, onClose, onSubmit }: {
  warranties: Warranty[]; preselectWarrantyId: string | null; isPending: boolean;
  onClose: () => void; onSubmit: (warrantyId: string, payload: DefectCreate) => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<DefectFormState>(() => ({
    warranty_id: preselectWarrantyId ?? warranties[0]?.id ?? '', reference: '', description: '',
    severity: '', status: 'open', raised_date: todayIso(), due_date: '', responsible_party: '',
  }));
  const [touched, setTouched] = useState(false);
  const set = <K extends keyof DefectFormState>(k: K, v: DefectFormState[K]) => setForm((p) => ({ ...p, [k]: v }));

  const warrantyError = touched && form.warranty_id.length === 0;
  const refError = touched && form.reference.trim().length === 0;
  const descError = touched && form.description.trim().length === 0;
  const canSubmit = form.warranty_id.length > 0 && form.reference.trim().length > 0 && form.description.trim().length > 0;
  const submit = () => { setTouched(true); if (canSubmit) onSubmit(form.warranty_id, buildDefectPayload(form)); };

  return (
    <ModalShell
      onClose={onClose}
      title={t('defects_liability.modal_new_defect', { defaultValue: 'New defect notice' })}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>{t('defects_liability.cancel', { defaultValue: 'Cancel' })}</Button>
          <Button variant="primary" onClick={submit} disabled={isPending || !canSubmit} loading={isPending}>
            {t('defects_liability.create_defect', { defaultValue: 'Raise defect' })}
          </Button>
        </>
      }
    >
      <Field label={t('defects_liability.field_warranty', { defaultValue: 'Against warranty' })} required>
        <SelectShell>
          <select value={form.warranty_id} onChange={(e) => set('warranty_id', e.target.value)} className={clsx(selectCls, warrantyError && 'border-semantic-error')}>
            <option value="" disabled>{t('defects_liability.field_warranty_ph', { defaultValue: 'Select a warranty' })}</option>
            {warranties.map((w) => <option key={w.id} value={w.id}>{w.reference} - {w.title}</option>)}
          </select>
        </SelectShell>
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label={t('defects_liability.field_defect_ref', { defaultValue: 'Reference' })} required>
          <input value={form.reference} onChange={(e) => set('reference', e.target.value)}
            placeholder={t('defects_liability.field_defect_ref_ph', { defaultValue: 'e.g. D-001' })}
            className={clsx(inputCls, refError && 'border-semantic-error')} />
        </Field>
        <Field label={t('defects_liability.col_severity', { defaultValue: 'Severity' })}>
          <SelectShell>
            <select value={form.severity} onChange={(e) => set('severity', e.target.value as DefectSeverity | '')} className={selectCls}>
              <option value="">{t('defects_liability.defect_severity_none', { defaultValue: 'Unset' })}</option>
              {DEFECT_SEVERITIES.map((sv) => <option key={sv} value={sv}>{t(`defects_liability.defect_severity_${sv}`, { defaultValue: humanize(sv) })}</option>)}
            </select>
          </SelectShell>
        </Field>
      </div>

      <Field label={t('defects_liability.field_defect_description', { defaultValue: 'Description' })} required>
        <textarea value={form.description} onChange={(e) => set('description', e.target.value)} rows={4}
          placeholder={t('defects_liability.field_defect_description_ph', { defaultValue: 'What is defective, where, and what needs rectifying' })}
          className={clsx(textareaCls, descError && 'border-semantic-error')} />
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label={t('defects_liability.field_status', { defaultValue: 'Status' })}>
          <SelectShell>
            <select value={form.status} onChange={(e) => set('status', e.target.value as DefectStatus)} className={selectCls}>
              {DEFECT_STATUSES.map((s) => <option key={s} value={s}>{t(`defects_liability.defect_status_${s}`, { defaultValue: humanize(s) })}</option>)}
            </select>
          </SelectShell>
        </Field>
        <Field label={t('defects_liability.field_responsible', { defaultValue: 'Responsible party' })}>
          <input value={form.responsible_party} onChange={(e) => set('responsible_party', e.target.value)}
            placeholder={t('defects_liability.field_responsible_ph', { defaultValue: 'Who must rectify it' })} className={inputCls} />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label={t('defects_liability.field_raised_date', { defaultValue: 'Raised date' })}>
          <input type="date" value={form.raised_date} onChange={(e) => set('raised_date', e.target.value)} className={inputCls} />
        </Field>
        <Field label={t('defects_liability.field_due_date', { defaultValue: 'Due date' })}>
          <input type="date" value={form.due_date} onChange={(e) => set('due_date', e.target.value)} className={inputCls} />
        </Field>
      </div>
    </ModalShell>
  );
}

/* -- Retention readiness banner (the money signal) ------------------------- */

function RetentionReadinessBanner({ register, readiness }: { register: DlpRegister; readiness: RetentionReleaseReadiness }) {
  const { t } = useTranslation();
  const readyCount = readiness.ready_count;
  const openDefects = register.total_open_defects;
  const overdue = register.overdue_defects.length;
  const expiring = register.expiring.length;
  const horizon = register.horizon_days || HORIZON_FALLBACK;
  const health = register.overall_health_score;
  const blocked = openDefects > 0 || overdue > 0;

  const tone: 'success' | 'warning' | 'neutral' = readyCount > 0 ? 'success' : blocked ? 'warning' : 'neutral';
  const shell: Record<'success' | 'warning' | 'neutral', string> = {
    success: 'border-semantic-success/40 bg-semantic-success-bg',
    warning: 'border-semantic-warning/40 bg-semantic-warning-bg',
    neutral: 'border-border-light bg-surface-secondary/50',
  };
  const Icon = tone === 'success' ? ShieldCheck : tone === 'warning' ? AlertTriangle : Clock;
  const iconColor = tone === 'success' ? 'text-semantic-success' : tone === 'warning' ? 'text-[#b45309]' : 'text-content-tertiary';

  const title = readyCount > 0
    ? t('defects_liability.banner_ready_title', { defaultValue: 'Clear to release retention' })
    : blocked
      ? t('defects_liability.banner_blocked_title', { defaultValue: 'Retention on hold' })
      : t('defects_liability.banner_running_title', { defaultValue: 'No retention ready to release yet' });
  const subtitle = readyCount > 0
    ? t('defects_liability.banner_ready_sub', { defaultValue: '{{count}} entries have finished their defects liability period with nothing outstanding.', count: readyCount })
    : blocked
      ? t('defects_liability.banner_blocked_sub', { defaultValue: 'Open defects are still holding retention back. Nothing is clear to release yet.' })
      : t('defects_liability.banner_running_sub', { defaultValue: 'Every defects liability period is still running, with nothing outstanding.' });

  const chips: { label: string; value: number | string; strong: boolean }[] = [
    { label: t('defects_liability.banner_chip_ready', { defaultValue: 'Ready to release' }), value: readyCount, strong: readyCount > 0 },
    { label: t('defects_liability.banner_chip_open_defects', { defaultValue: 'Open defects' }), value: openDefects, strong: openDefects > 0 },
    { label: t('defects_liability.banner_chip_overdue', { defaultValue: 'Overdue' }), value: overdue, strong: overdue > 0 },
    { label: t('defects_liability.banner_chip_expiring', { defaultValue: 'Expiring in {{days}}d', days: horizon }), value: expiring, strong: false },
    { label: t('defects_liability.banner_chip_health', { defaultValue: 'Defect-free' }), value: health != null ? `${health}%` : t('defects_liability.health_na', { defaultValue: 'n/a' }), strong: false },
  ];

  return (
    <section className={clsx('rounded-xl border p-4', shell[tone])} aria-label={title}>
      <div className="flex items-start gap-3">
        <Icon size={22} className={clsx('mt-0.5 shrink-0', iconColor)} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <CircleDollarSign size={15} className="text-content-tertiary" />
            <h2 className="text-sm font-semibold text-content-primary">{t('defects_liability.banner_heading', { defaultValue: 'Retention release readiness' })}</h2>
          </div>
          <p className="mt-1 text-base font-semibold text-content-primary">{title}</p>
          <p className="mt-0.5 text-sm text-content-secondary">{subtitle}</p>

          <div className="mt-3 flex flex-wrap gap-2">
            {chips.map((c) => (
              <span key={c.label} className={clsx('inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs',
                c.strong ? 'border-transparent bg-surface-elevated font-semibold text-content-primary shadow-xs' : 'border-border-light bg-surface-elevated/60 text-content-secondary')}>
                <span className="text-content-tertiary">{c.label}</span>
                <span className="tabular-nums">{c.value}</span>
              </span>
            ))}
          </div>

          {readiness.ready.length > 0 && (
            <div className="mt-3 rounded-lg border border-semantic-success/30 bg-surface-elevated/70 p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-semantic-success">
                {t('defects_liability.banner_ready_list_title', { defaultValue: 'Entries clear for retention release' })}
              </p>
              <ul className="space-y-1.5">
                {readiness.ready.map((r) => (
                  <li key={r.warranty_id ?? r.reference} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                    <span className="font-mono text-xs font-semibold text-content-secondary">{r.reference}</span>
                    <span className="min-w-0 flex-1 truncate text-content-primary">{r.title}</span>
                    <span className="text-xs text-content-tertiary">
                      {t('defects_liability.banner_dlp_ended', { defaultValue: 'DLP ended' })} <DateDisplay value={r.dlp_end_date} />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/* -- Subcontractor DLP health (optional view) ------------------------------ */

function SubcontractorHealthCard({ register }: { register: DlpRegister }) {
  const { t } = useTranslation();
  if (register.subcontractors.length === 0) return null;
  return (
    <Card padding="none" className="overflow-x-auto">
      <h3 className="flex items-center gap-1.5 border-b border-border-light px-4 py-2.5 text-sm font-semibold text-content-primary">
        <Building2 size={14} className="text-content-tertiary" />
        {t('defects_liability.health_title', { defaultValue: 'Subcontractor DLP health' })}
      </h3>
      <div className="min-w-[560px]">
        <div className="flex items-center gap-3 border-b border-border-light bg-surface-secondary/30 px-4 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
          <span className="flex-1">{t('defects_liability.health_col_subcontractor', { defaultValue: 'Subcontractor' })}</span>
          <span className="w-20 text-right">{t('defects_liability.health_col_total', { defaultValue: 'Entries' })}</span>
          <span className="w-24 text-right">{t('defects_liability.health_col_open', { defaultValue: 'Open defects' })}</span>
          <span className="w-20 text-right">{t('defects_liability.health_col_overdue', { defaultValue: 'Overdue' })}</span>
          <span className="w-24 text-right">{t('defects_liability.health_col_score', { defaultValue: 'Defect-free' })}</span>
        </div>
        {register.subcontractors.map((s) => (
          <div key={s.subcontractor} className="flex items-center gap-3 border-b border-border-light px-4 py-2 text-sm last:border-b-0">
            <span className="flex-1 truncate text-content-primary">
              {s.subcontractor === 'unassigned' ? t('defects_liability.health_unassigned', { defaultValue: 'Unassigned' }) : s.subcontractor}
            </span>
            <span className="w-20 text-right tabular-nums text-content-secondary">{s.total}</span>
            <span className={clsx('w-24 text-right tabular-nums', s.open_defects > 0 ? 'font-semibold text-semantic-error' : 'text-content-secondary')}>{s.open_defects}</span>
            <span className={clsx('w-20 text-right tabular-nums', s.overdue_defects > 0 ? 'font-semibold text-semantic-error' : 'text-content-secondary')}>{s.overdue_defects}</span>
            <span className="w-24 text-right tabular-nums text-content-secondary">
              {s.health_score != null ? `${s.health_score}%` : t('defects_liability.health_na', { defaultValue: 'n/a' })}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* -- Rows ------------------------------------------------------------------ */

function WarrantyRow({ warranty, flag, openDefectCount, onEdit, onDelete, onAddDefect }: {
  warranty: Warranty; flag: 'expired' | 'expiring' | null; openDefectCount: number;
  onEdit: (w: Warranty) => void; onDelete: (w: Warranty) => void; onAddDefect: (w: Warranty) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={clsx('flex items-center gap-3 border-b border-border-light px-4 py-3 last:border-b-0', flag === 'expired' && 'bg-semantic-error-bg/40')}>
      <span className="w-20 shrink-0 font-mono text-sm font-semibold text-content-secondary">{warranty.reference}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-content-primary">{warranty.title}</p>
        {warranty.subcontractor_name && <p className="truncate text-xs text-content-tertiary">{warranty.subcontractor_name}</p>}
      </div>
      <div className="hidden w-28 shrink-0 md:block">
        {warranty.warranty_type && (
          <Badge variant={warrantyTypeVariant(warranty.warranty_type)} size="sm">
            {t(`defects_liability.warranty_type_${warranty.warranty_type}`, { defaultValue: humanize(warranty.warranty_type) })}
          </Badge>
        )}
      </div>
      <div className="hidden w-28 shrink-0 items-center gap-1 text-xs text-content-tertiary sm:flex">
        <CalendarClock size={12} className="shrink-0" />
        <DateDisplay value={warranty.dlp_end_date} />
      </div>
      <div className="w-16 shrink-0 text-center">
        {openDefectCount > 0
          ? <Badge variant="error" size="sm">{t('defects_liability.warranty_defect_count', { defaultValue: '{{count}} open', count: openDefectCount })}</Badge>
          : <span className="text-xs text-content-tertiary">0</span>}
      </div>
      <div className="flex w-32 shrink-0 items-center justify-end gap-1.5">
        {flag === 'expired' && <Badge variant="error" size="sm">{t('defects_liability.badge_expired', { defaultValue: 'Expired' })}</Badge>}
        {flag === 'expiring' && <Badge variant="warning" size="sm">{t('defects_liability.badge_expiring', { defaultValue: 'Expiring soon' })}</Badge>}
        <Badge variant={warrantyStatusVariant(warranty.status)} size="sm">{t(`defects_liability.warranty_status_${warranty.status}`, { defaultValue: humanize(warranty.status) })}</Badge>
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        <IconBtn label={t('defects_liability.action_add_defect', { defaultValue: 'Add defect' })} onClick={() => onAddDefect(warranty)}><FileWarning size={15} /></IconBtn>
        <IconBtn label={t('defects_liability.action_edit', { defaultValue: 'Edit' })} onClick={() => onEdit(warranty)}><Pencil size={15} /></IconBtn>
        <IconBtn label={t('defects_liability.action_delete', { defaultValue: 'Delete' })} danger onClick={() => onDelete(warranty)}><Trash2 size={15} /></IconBtn>
      </div>
    </div>
  );
}

function IconBtn({ label, onClick, danger, children }: { label: string; onClick: () => void; danger?: boolean; children: ReactNode }) {
  return (
    <button onClick={onClick} title={label} aria-label={label}
      className={clsx('flex h-8 w-8 items-center justify-center rounded-lg text-content-tertiary',
        danger ? 'hover:bg-semantic-error-bg hover:text-semantic-error' : 'hover:bg-surface-secondary hover:text-content-primary')}>
      {children}
    </button>
  );
}

function DefectRow({ defect, warrantyReference, overdue, onStatusChange }: {
  defect: Defect; warrantyReference: string; overdue: boolean; onStatusChange: (d: Defect, status: DefectStatus) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={clsx('flex items-center gap-3 border-b border-border-light px-4 py-3 last:border-b-0', overdue && 'bg-semantic-error-bg/40')}>
      <span className="w-16 shrink-0 font-mono text-sm font-semibold text-content-secondary">{defect.reference}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-content-primary">{defect.description}</p>
        <p className="truncate text-xs text-content-tertiary">{warrantyReference}{defect.responsible_party ? ` - ${defect.responsible_party}` : ''}</p>
      </div>
      <div className="hidden w-20 shrink-0 text-center sm:block">
        {defect.severity && <Badge variant={defectSeverityVariant(defect.severity)} size="sm">{t(`defects_liability.defect_severity_${defect.severity}`, { defaultValue: humanize(defect.severity) })}</Badge>}
      </div>
      <div className="hidden w-24 shrink-0 text-xs text-content-tertiary lg:block"><DateDisplay value={defect.raised_date} /></div>
      <div className="hidden w-24 shrink-0 text-xs text-content-tertiary md:block"><DateDisplay value={defect.due_date} /></div>
      <div className="w-16 shrink-0 text-center">{overdue && <Badge variant="error" size="sm">{t('defects_liability.badge_overdue', { defaultValue: 'Overdue' })}</Badge>}</div>
      <div className="w-36 shrink-0">
        <SelectShell>
          <select value={defect.status} onChange={(e) => onStatusChange(defect, e.target.value as DefectStatus)}
            aria-label={t('defects_liability.col_status', { defaultValue: 'Status' })} className={clsx(selectCls, 'h-8 text-xs')}>
            {DEFECT_STATUSES.map((s) => <option key={s} value={s}>{t(`defects_liability.defect_status_${s}`, { defaultValue: humanize(s) })}</option>)}
          </select>
        </SelectShell>
      </div>
    </div>
  );
}

/* -- Filter select --------------------------------------------------------- */

function StatusFilter<T extends string>({ value, onChange, options, labelFor }: {
  value: T | ''; onChange: (v: T | '') => void; options: readonly T[]; labelFor: (v: T) => string;
}) {
  const { t } = useTranslation();
  return (
    <SelectShell>
      <select value={value} onChange={(e) => onChange(e.target.value as T | '')}
        aria-label={t('defects_liability.filter_all_statuses', { defaultValue: 'All statuses' })} className={clsx(selectCls, 'sm:w-44')}>
        <option value="">{t('defects_liability.filter_all_statuses', { defaultValue: 'All statuses' })}</option>
        {options.map((o) => <option key={o} value={o}>{labelFor(o)}</option>)}
      </select>
    </SelectShell>
  );
}

/* -- Main page ------------------------------------------------------------- */

export function DefectsLiabilityPage() {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams<{ projectId: string }>();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const projectId = routeProjectId || activeProjectId || '';
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const { confirm, ...confirmProps } = useConfirm();

  const [view, setView] = useState<'warranties' | 'defects'>('warranties');
  const [warrantyStatusFilter, setWarrantyStatusFilter] = useState<WarrantyStatus | ''>('');
  const [defectStatusFilter, setDefectStatusFilter] = useState<DefectStatus | ''>('');
  const [warrantyModalOpen, setWarrantyModalOpen] = useState(false);
  const [editingWarranty, setEditingWarranty] = useState<Warranty | null>(null);
  const [defectModalOpen, setDefectModalOpen] = useState(false);
  const [defectPreselect, setDefectPreselect] = useState<string | null>(null);

  const registerQ = useQuery({ queryKey: ['dlp', 'register', projectId], queryFn: () => fetchRegister(projectId), enabled: !!projectId });
  const readinessQ = useQuery({ queryKey: ['dlp', 'readiness', projectId], queryFn: () => fetchRetentionReadiness(projectId), enabled: !!projectId });
  const warrantiesQ = useQuery({ queryKey: ['dlp', 'warranties', projectId], queryFn: () => fetchWarranties(projectId), enabled: !!projectId });
  const defectsQ = useQuery({ queryKey: ['dlp', 'defects', projectId], queryFn: () => fetchDefects(projectId), enabled: !!projectId });

  const warranties = useMemo(() => warrantiesQ.data ?? [], [warrantiesQ.data]);
  const defects = useMemo(() => defectsQ.data ?? [], [defectsQ.data]);

  const invalidate = useCallback(() => { qc.invalidateQueries({ queryKey: ['dlp'] }); }, [qc]);
  const onMutationError = useCallback(
    (err: unknown) => addToast({ type: 'error', title: t('defects_liability.error', { defaultValue: 'Error' }), message: getErrorMessage(err) }),
    [addToast, t],
  );

  const createWarrantyMut = useMutation({
    mutationFn: (payload: WarrantyCreate) => createWarranty(projectId, payload),
    onSuccess: () => { invalidate(); setWarrantyModalOpen(false); addToast({ type: 'success', title: t('defects_liability.warranty_created', { defaultValue: 'Warranty created' }) }); },
    onError: onMutationError,
  });
  const updateWarrantyMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: WarrantyCreate }) => updateWarranty(projectId, id, payload),
    onSuccess: () => { invalidate(); setWarrantyModalOpen(false); setEditingWarranty(null); addToast({ type: 'success', title: t('defects_liability.warranty_updated', { defaultValue: 'Warranty updated' }) }); },
    onError: onMutationError,
  });
  const deleteWarrantyMut = useMutation({
    mutationFn: (id: string) => deleteWarranty(projectId, id),
    onSuccess: () => { invalidate(); addToast({ type: 'success', title: t('defects_liability.warranty_deleted', { defaultValue: 'Warranty deleted' }) }); },
    onError: onMutationError,
  });
  const createDefectMut = useMutation({
    mutationFn: ({ warrantyId, payload }: { warrantyId: string; payload: DefectCreate }) => createDefect(projectId, warrantyId, payload),
    onSuccess: () => { invalidate(); setDefectModalOpen(false); setDefectPreselect(null); addToast({ type: 'success', title: t('defects_liability.defect_created', { defaultValue: 'Defect notice raised' }) }); },
    onError: onMutationError,
  });
  const updateDefectMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: DefectStatus }) => updateDefect(projectId, id, { status }),
    onSuccess: () => { invalidate(); addToast({ type: 'success', title: t('defects_liability.defect_updated', { defaultValue: 'Defect updated' }) }); },
    onError: onMutationError,
  });

  const handleWarrantySubmit = useCallback((payload: WarrantyCreate) => {
    if (editingWarranty) updateWarrantyMut.mutate({ id: editingWarranty.id, payload });
    else createWarrantyMut.mutate(payload);
  }, [editingWarranty, createWarrantyMut, updateWarrantyMut]);

  const handleDeleteWarranty = useCallback(async (w: Warranty) => {
    const ok = await confirm({
      title: t('defects_liability.confirm_delete_title', { defaultValue: 'Delete warranty?' }),
      message: t('defects_liability.confirm_delete_msg', { defaultValue: 'This warranty and all its defect notices will be permanently deleted.' }),
      confirmLabel: t('defects_liability.confirm_delete_label', { defaultValue: 'Delete' }),
      variant: 'danger',
    });
    if (ok) deleteWarrantyMut.mutate(w.id);
  }, [confirm, deleteWarrantyMut, t]);

  const openCreateWarranty = () => { setEditingWarranty(null); setWarrantyModalOpen(true); };
  const openEditWarranty = (w: Warranty) => { setEditingWarranty(w); setWarrantyModalOpen(true); };
  const openAddDefect = (w: Warranty) => { setDefectPreselect(w.id); setDefectModalOpen(true); };

  const today = todayIso();
  const horizonEnd = addDaysIso(today, registerQ.data?.horizon_days || HORIZON_FALLBACK);

  const openDefectByWarranty = useMemo(() => {
    const counts = new Map<string, number>();
    for (const d of defects) if (d.status === 'open' || d.status === 'rectifying') counts.set(d.warranty_id, (counts.get(d.warranty_id) ?? 0) + 1);
    return counts;
  }, [defects]);
  const warrantyRefById = useMemo(() => new Map(warranties.map((w) => [w.id, w.reference] as const)), [warranties]);
  const filteredWarranties = useMemo(
    () => (warrantyStatusFilter ? warranties.filter((w) => w.status === warrantyStatusFilter) : warranties),
    [warranties, warrantyStatusFilter],
  );
  const filteredDefects = useMemo(
    () => (defectStatusFilter ? defects.filter((d) => d.status === defectStatusFilter) : defects),
    [defects, defectStatusFilter],
  );

  const signalReady = !!registerQ.data && !!readinessQ.data && registerQ.data.total > 0;

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        srTitle={t('defects_liability.title', { defaultValue: 'Warranties & Defects Liability' })}
        subtitle={t('defects_liability.subtitle', { defaultValue: 'Post-handover warranties, defect notices and retention release readiness' })}
        actions={<Button variant="primary" size="sm" onClick={openCreateWarranty} disabled={!projectId} icon={<Plus size={14} />}>{t('defects_liability.new_warranty', { defaultValue: 'New warranty' })}</Button>}
      />

      <RequiresProject emptyHint={t('defects_liability.select_project', { defaultValue: 'Open a project first to manage warranties and the defects liability period.' })}>
        <div className="space-y-5">
          {/* SIGNAL FIRST: retention release readiness */}
          {signalReady && registerQ.data && readinessQ.data && <RetentionReadinessBanner register={registerQ.data} readiness={readinessQ.data} />}
          {registerQ.data && <SubcontractorHealthCard register={registerQ.data} />}

          {/* Register switch + status filter */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex rounded-lg border border-border bg-surface-secondary p-0.5">
              {(['warranties', 'defects'] as const).map((v) => (
                <button key={v} onClick={() => setView(v)}
                  className={clsx('flex h-8 items-center gap-1.5 rounded-md px-3 text-sm font-medium transition-colors',
                    view === v ? 'bg-surface-elevated text-content-primary shadow-xs' : 'text-content-tertiary hover:text-content-primary')}>
                  {v === 'warranties' ? <ShieldAlert size={14} /> : <Wrench size={14} />}
                  {v === 'warranties' ? t('defects_liability.tab_warranties', { defaultValue: 'Warranties' }) : t('defects_liability.tab_defects', { defaultValue: 'Defect notices' })}
                </button>
              ))}
            </div>

            {view === 'warranties' ? (
              <StatusFilter value={warrantyStatusFilter} onChange={(v) => setWarrantyStatusFilter(v)} options={WARRANTY_STATUSES}
                labelFor={(s) => t(`defects_liability.warranty_status_${s}`, { defaultValue: humanize(s) })} />
            ) : (
              <div className="flex items-center gap-2">
                <StatusFilter value={defectStatusFilter} onChange={(v) => setDefectStatusFilter(v)} options={DEFECT_STATUSES}
                  labelFor={(s) => t(`defects_liability.defect_status_${s}`, { defaultValue: humanize(s) })} />
                <Button variant="secondary" size="sm" onClick={() => { setDefectPreselect(null); setDefectModalOpen(true); }}
                  disabled={warranties.length === 0} icon={<Plus size={14} />}
                  title={warranties.length === 0 ? t('defects_liability.no_warranty_for_defect', { defaultValue: 'Add a warranty first before raising a defect notice.' }) : undefined}>
                  {t('defects_liability.new_defect', { defaultValue: 'New defect' })}
                </Button>
              </div>
            )}
          </div>

          {/* Warranties register */}
          {view === 'warranties' && (
            warrantiesQ.isLoading ? (
              <Card padding="lg" className="text-center text-sm text-content-tertiary">{t('defects_liability.loading', { defaultValue: 'Loading...' })}</Card>
            ) : filteredWarranties.length === 0 ? (
              <EmptyState icon={<ShieldAlert size={28} strokeWidth={1.5} />}
                title={warrantyStatusFilter ? t('defects_liability.no_warranties_filtered', { defaultValue: 'No warranties match this filter' }) : t('defects_liability.no_warranties', { defaultValue: 'No warranties yet' })}
                description={warrantyStatusFilter ? undefined : t('defects_liability.no_warranties_hint', { defaultValue: 'Register the first warranty or defects liability entry for this project.' })}
                action={warrantyStatusFilter ? undefined : { label: t('defects_liability.new_warranty', { defaultValue: 'New warranty' }), onClick: openCreateWarranty }} />
            ) : (
              <>
                <p className="text-sm text-content-tertiary">{t('defects_liability.showing_warranties', { defaultValue: '{{count}} warranties', count: filteredWarranties.length })}</p>
                <Card padding="none" className="overflow-x-auto">
                  <div className="min-w-[720px]">
                    {filteredWarranties.map((w) => (
                      <WarrantyRow key={w.id} warranty={w} flag={warrantyFlag(w, today, horizonEnd)} openDefectCount={openDefectByWarranty.get(w.id) ?? 0}
                        onEdit={openEditWarranty} onDelete={handleDeleteWarranty} onAddDefect={openAddDefect} />
                    ))}
                  </div>
                </Card>
              </>
            )
          )}

          {/* Defects register */}
          {view === 'defects' && (
            defectsQ.isLoading ? (
              <Card padding="lg" className="text-center text-sm text-content-tertiary">{t('defects_liability.loading', { defaultValue: 'Loading...' })}</Card>
            ) : filteredDefects.length === 0 ? (
              <EmptyState icon={<Wrench size={28} strokeWidth={1.5} />}
                title={defectStatusFilter ? t('defects_liability.no_defects_filtered', { defaultValue: 'No defect notices match this filter' }) : t('defects_liability.no_defects', { defaultValue: 'No defect notices yet' })}
                description={defectStatusFilter ? undefined : t('defects_liability.no_defects_hint', { defaultValue: 'Raise a defect notice against a warranty during its defects liability period.' })} />
            ) : (
              <>
                <p className="text-sm text-content-tertiary">{t('defects_liability.showing_defects', { defaultValue: '{{count}} defect notices', count: filteredDefects.length })}</p>
                <Card padding="none" className="overflow-x-auto">
                  <div className="min-w-[760px]">
                    {filteredDefects.map((d) => (
                      <DefectRow key={d.id} defect={d} warrantyReference={warrantyRefById.get(d.warranty_id) ?? d.warranty_id.slice(0, 8)}
                        overdue={isDefectOverdue(d, today)} onStatusChange={(defect, status) => updateDefectMut.mutate({ id: defect.id, status })} />
                    ))}
                  </div>
                </Card>
              </>
            )
          )}
        </div>
      </RequiresProject>

      {warrantyModalOpen && (
        <WarrantyModal editing={editingWarranty} isPending={createWarrantyMut.isPending || updateWarrantyMut.isPending}
          onClose={() => { setWarrantyModalOpen(false); setEditingWarranty(null); }} onSubmit={handleWarrantySubmit} />
      )}
      {defectModalOpen && (
        <DefectModal warranties={warranties} preselectWarrantyId={defectPreselect} isPending={createDefectMut.isPending}
          onClose={() => { setDefectModalOpen(false); setDefectPreselect(null); }}
          onSubmit={(warrantyId, payload) => createDefectMut.mutate({ warrantyId, payload })} />
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  );
}
