// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// TemplateBuilder - compose (or edit) a reusable form / checklist template from
// ordered fields. Client-side integrity mirrors the backend so problems show
// live; the backend re-validates on save and is the source of truth.

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Trash2,
  ArrowUp,
  ArrowDown,
  GripVertical,
  X,
  AlertTriangle,
  Asterisk,
} from 'lucide-react';
import clsx from 'clsx';
import { Button, Badge, WideModal } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { ApiError, getErrorMessage } from '@/shared/lib/api';
import {
  createTemplate,
  updateTemplate,
  type FieldIssue,
  type FormFieldDef,
  type TemplateCategory,
  type TemplateDetail,
} from './api';
import {
  FIELD_TYPES,
  fieldMeta,
  CHOICE_TYPES,
  LAYOUT_TYPES,
  CATEGORY_ORDER,
  CATEGORY_LABELS,
  DEFAULT_RATING_SCALE,
  ensureFieldKeys,
  validateTemplateFields,
  type FieldTypeMeta,
} from './fieldTypes';

const inputCls =
  'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

type EditableField = FormFieldDef & { _id: string };

let _seq = 0;
function nextId(): string {
  _seq += 1;
  return `f${_seq}_${Math.random().toString(36).slice(2, 7)}`;
}

function blankField(type: FormFieldDef['type']): EditableField {
  const meta = fieldMeta(type);
  return {
    _id: nextId(),
    key: '',
    type,
    label: '',
    required: false,
    help_text: '',
    options: meta.hasOptions ? ['Option 1', 'Option 2'] : [],
    unit: null,
    max_rating: meta.hasRating ? DEFAULT_RATING_SCALE : null,
  };
}

function toEditable(fields: FormFieldDef[]): EditableField[] {
  return fields.map((f) => ({
    _id: nextId(),
    key: f.key,
    type: f.type,
    label: f.label,
    required: f.required,
    help_text: f.help_text ?? '',
    options: f.options ?? [],
    unit: f.unit ?? null,
    max_rating: f.max_rating ?? (fieldMeta(f.type).hasRating ? DEFAULT_RATING_SCALE : null),
  }));
}

export interface TemplateBuilderProps {
  open: boolean;
  onClose: () => void;
  /** When set, edit this template; otherwise create a new one. */
  initial?: TemplateDetail | null;
  /** Active project - a new template can be pinned to it or kept global. */
  projectId?: string | null;
  onSaved: (template: TemplateDetail) => void;
}

export function TemplateBuilder({ open, onClose, initial, projectId, onSaved }: TemplateBuilderProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [category, setCategory] = useState<TemplateCategory>(initial?.category ?? 'custom');
  const [scope, setScope] = useState<'global' | 'project'>(
    initial ? (initial.project_id ? 'project' : 'global') : 'global',
  );
  const [tagsText, setTagsText] = useState((initial?.tags ?? []).join(', '));
  const [fields, setFields] = useState<EditableField[]>(initial ? toEditable(initial.fields) : []);
  const [showPalette, setShowPalette] = useState(false);

  const issues = useMemo(() => validateTemplateFields(fields), [fields]);
  const isEdit = !!initial;

  const patch = (id: string, changes: Partial<EditableField>) =>
    setFields((prev) => prev.map((f) => (f._id === id ? { ...f, ...changes } : f)));

  const addField = (type: FormFieldDef['type']) => {
    setFields((prev) => [...prev, blankField(type)]);
    setShowPalette(false);
  };

  const removeField = (id: string) => setFields((prev) => prev.filter((f) => f._id !== id));

  const move = (id: string, dir: -1 | 1) =>
    setFields((prev) => {
      const idx = prev.findIndex((f) => f._id === id);
      const target = idx + dir;
      if (idx < 0 || target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      const a = next[idx];
      const b = next[target];
      if (!a || !b) return prev;
      next[idx] = b;
      next[target] = a;
      return next;
    });

  const buildPayload = () => {
    const cleaned = ensureFieldKeys(
      fields.map((f) => ({
        key: f.key,
        type: f.type,
        label: f.label.trim(),
        required: LAYOUT_TYPES.has(f.type) ? false : f.required,
        help_text: (f.help_text ?? '').trim() || null,
        options: CHOICE_TYPES.has(f.type) ? (f.options ?? []).map((o) => o.trim()).filter(Boolean) : [],
        unit: f.type === 'number' ? (f.unit ?? null) : null,
        max_rating: f.type === 'rating' ? (f.max_rating ?? DEFAULT_RATING_SCALE) : null,
      })),
    );
    const tags = tagsText
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    return { cleaned, tags };
  };

  const saveMut = useMutation({
    mutationFn: async (): Promise<TemplateDetail> => {
      const { cleaned, tags } = buildPayload();
      if (isEdit && initial) {
        return updateTemplate(initial.id, {
          name: name.trim(),
          description: description.trim() || null,
          category,
          fields: cleaned,
          tags,
        });
      }
      return createTemplate({
        project_id: scope === 'project' ? (projectId ?? null) : null,
        name: name.trim(),
        description: description.trim() || null,
        category,
        status: 'published',
        fields: cleaned,
        tags,
      });
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ['forms', 'templates'] });
      qc.invalidateQueries({ queryKey: ['forms', 'categories'] });
      addToast({
        type: 'success',
        title: isEdit
          ? t('forms.template_updated', { defaultValue: 'Template updated' })
          : t('forms.template_created', { defaultValue: 'Template created' }),
      });
      onSaved(saved);
    },
    onError: (e: unknown) => {
      // Surface backend field issues when present (422 with detail.issues).
      const serverIssues = extractIssues(e);
      addToast({
        type: 'error',
        title: t('common.error', { defaultValue: 'Error' }),
        message: serverIssues.length ? serverIssues[0]!.message : getErrorMessage(e),
      });
    },
  });

  const canSave = name.trim().length > 0 && issues.length === 0 && !saveMut.isPending;

  return (
    <WideModal
      open={open}
      onClose={onClose}
      size="xl"
      busy={saveMut.isPending}
      title={
        isEdit
          ? t('forms.edit_template', { defaultValue: 'Edit template' })
          : t('forms.new_template', { defaultValue: 'New template' })
      }
      subtitle={t('forms.builder_subtitle', {
        defaultValue: 'Compose a reusable form or checklist from ordered fields.',
      })}
      footer={
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 text-xs text-content-tertiary">
            {issues.length > 0 ? (
              <span className="inline-flex items-center gap-1.5 text-semantic-warning">
                <AlertTriangle size={14} />
                {t('forms.issues_count', {
                  defaultValue: '{{count}} issue(s) to fix',
                  count: issues.length,
                })}
              </span>
            ) : (
              <span>
                {t('forms.field_count', { defaultValue: '{{count}} field(s)', count: fields.length })}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="secondary" onClick={onClose} disabled={saveMut.isPending}>
              {t('common.cancel', { defaultValue: 'Cancel' })}
            </Button>
            <Button onClick={() => saveMut.mutate()} loading={saveMut.isPending} disabled={!canSave}>
              {isEdit
                ? t('common.save', { defaultValue: 'Save' })
                : t('forms.create_template', { defaultValue: 'Create template' })}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Template meta */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-content-secondary">
              {t('forms.template_name', { defaultValue: 'Template name' })}
            </span>
            <input
              className={inputCls}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('forms.template_name_ph', { defaultValue: 'e.g. Site safety induction' })}
              autoFocus
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-content-secondary">
              {t('forms.category', { defaultValue: 'Category' })}
            </span>
            <select
              className={inputCls}
              value={category}
              onChange={(e) => setCategory(e.target.value as TemplateCategory)}
            >
              {CATEGORY_ORDER.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABELS[c]}
                </option>
              ))}
            </select>
          </label>
          <label className="block sm:col-span-2">
            <span className="mb-1 block text-xs font-medium text-content-secondary">
              {t('forms.description', { defaultValue: 'Description' })}
            </span>
            <input
              className={inputCls}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('forms.description_ph', { defaultValue: 'What is this form for?' })}
            />
          </label>
          <label className="block sm:col-span-2">
            <span className="mb-1 block text-xs font-medium text-content-secondary">
              {t('forms.tags', { defaultValue: 'Tags (comma separated)' })}
            </span>
            <input
              className={inputCls}
              value={tagsText}
              onChange={(e) => setTagsText(e.target.value)}
              placeholder="safety, induction"
            />
          </label>
          {!isEdit && projectId && (
            <div className="sm:col-span-2">
              <span className="mb-1 block text-xs font-medium text-content-secondary">
                {t('forms.availability', { defaultValue: 'Availability' })}
              </span>
              <div className="flex flex-wrap gap-2">
                <ScopeChip
                  active={scope === 'global'}
                  onClick={() => setScope('global')}
                  label={t('forms.scope_global', { defaultValue: 'All projects (library)' })}
                />
                <ScopeChip
                  active={scope === 'project'}
                  onClick={() => setScope('project')}
                  label={t('forms.scope_project', { defaultValue: 'This project only' })}
                />
              </div>
            </div>
          )}
        </div>

        {/* Fields */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-content-primary">
              {t('forms.fields', { defaultValue: 'Fields' })}
            </h3>
          </div>

          {fields.length === 0 && (
            <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-content-tertiary">
              {t('forms.no_fields_yet', { defaultValue: 'No fields yet. Add your first field below.' })}
            </div>
          )}

          {fields.map((field, idx) => (
            <FieldCard
              key={field._id}
              field={field}
              index={idx}
              total={fields.length}
              onPatch={(changes) => patch(field._id, changes)}
              onRemove={() => removeField(field._id)}
              onMove={(dir) => move(field._id, dir)}
            />
          ))}

          {/* Add-field palette */}
          <div className="relative">
            <Button
              variant="secondary"
              icon={<Plus size={15} />}
              onClick={() => setShowPalette((v) => !v)}
            >
              {t('forms.add_field', { defaultValue: 'Add field' })}
            </Button>
            {showPalette && (
              <div className="absolute z-10 mt-2 grid w-full max-w-2xl grid-cols-2 gap-1 rounded-xl border border-border bg-surface-elevated p-2 shadow-xl sm:grid-cols-3">
                {FIELD_TYPES.map((m) => (
                  <PaletteButton key={m.type} meta={m} onClick={() => addField(m.type)} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </WideModal>
  );
}

/* -- Sub-components -------------------------------------------------------- */

function ScopeChip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'inline-flex h-8 items-center rounded-full border px-3 text-xs font-medium transition-colors',
        active
          ? 'border-oe-blue bg-oe-blue-subtle text-oe-blue-text'
          : 'border-border text-content-secondary hover:bg-surface-secondary',
      )}
    >
      {label}
    </button>
  );
}

function PaletteButton({ meta, onClick }: { meta: FieldTypeMeta; onClick: () => void }) {
  const Icon = meta.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-start gap-2 rounded-lg border border-transparent p-2 text-left hover:border-border hover:bg-surface-secondary"
    >
      <Icon size={16} className="mt-0.5 shrink-0 text-oe-blue" />
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium text-content-primary">{meta.label}</span>
        <span className="block truncate text-xs text-content-tertiary">{meta.hint}</span>
      </span>
    </button>
  );
}

interface FieldCardProps {
  field: EditableField;
  index: number;
  total: number;
  onPatch: (changes: Partial<EditableField>) => void;
  onRemove: () => void;
  onMove: (dir: -1 | 1) => void;
}

function FieldCard({ field, index, total, onPatch, onRemove, onMove }: FieldCardProps) {
  const { t } = useTranslation();
  const meta = fieldMeta(field.type);
  const Icon = meta.icon;
  const isLayout = LAYOUT_TYPES.has(field.type);

  return (
    <div
      className={clsx(
        'rounded-xl border border-border bg-surface-primary p-3',
        isLayout && 'bg-surface-secondary',
      )}
    >
      <div className="flex items-start gap-2">
        <GripVertical size={16} className="mt-2.5 shrink-0 text-content-quaternary" aria-hidden />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="neutral" size="sm">
              <Icon size={12} className="mr-1" />
              {meta.label}
            </Badge>
            {!isLayout && (
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-content-secondary">
                <input
                  type="checkbox"
                  checked={field.required}
                  onChange={(e) => onPatch({ required: e.target.checked })}
                  className="h-3.5 w-3.5 rounded border-border text-oe-blue focus:ring-oe-blue/30"
                />
                <Asterisk size={11} className="text-semantic-error" />
                {t('forms.required', { defaultValue: 'Required' })}
              </label>
            )}
          </div>

          <input
            className={inputCls}
            value={field.label}
            onChange={(e) => onPatch({ label: e.target.value })}
            placeholder={
              isLayout
                ? t('forms.section_title_ph', { defaultValue: 'Section title' })
                : t('forms.question_ph', { defaultValue: 'Question / label' })
            }
          />

          {!isLayout && (
            <input
              className={clsx(inputCls, 'h-8 text-xs')}
              value={field.help_text ?? ''}
              onChange={(e) => onPatch({ help_text: e.target.value })}
              placeholder={t('forms.help_text_ph', { defaultValue: 'Help text (optional)' })}
            />
          )}

          {CHOICE_TYPES.has(field.type) && (
            <OptionsEditor
              options={field.options ?? []}
              onChange={(options) => onPatch({ options })}
            />
          )}

          {field.type === 'number' && (
            <input
              className={clsx(inputCls, 'h-8 max-w-[12rem] text-xs')}
              value={field.unit ?? ''}
              onChange={(e) => onPatch({ unit: e.target.value || null })}
              placeholder={t('forms.unit_ph', { defaultValue: 'Unit (e.g. mm, m3)' })}
            />
          )}

          {field.type === 'rating' && (
            <label className="inline-flex items-center gap-2 text-xs text-content-secondary">
              {t('forms.rating_scale', { defaultValue: 'Scale 1 to' })}
              <input
                type="number"
                min={2}
                max={10}
                className={clsx(inputCls, 'h-8 w-20 text-xs')}
                value={field.max_rating ?? DEFAULT_RATING_SCALE}
                onChange={(e) => onPatch({ max_rating: Number(e.target.value) || DEFAULT_RATING_SCALE })}
              />
            </label>
          )}
        </div>

        <div className="flex shrink-0 flex-col items-center gap-0.5">
          <IconBtn label="Move up" disabled={index === 0} onClick={() => onMove(-1)}>
            <ArrowUp size={14} />
          </IconBtn>
          <IconBtn label="Move down" disabled={index === total - 1} onClick={() => onMove(1)}>
            <ArrowDown size={14} />
          </IconBtn>
          <IconBtn label="Remove field" danger onClick={onRemove}>
            <Trash2 size={14} />
          </IconBtn>
        </div>
      </div>
    </div>
  );
}

function OptionsEditor({ options, onChange }: { options: string[]; onChange: (next: string[]) => void }) {
  const { t } = useTranslation();
  const set = (i: number, value: string) => onChange(options.map((o, idx) => (idx === i ? value : o)));
  const remove = (i: number) => onChange(options.filter((_, idx) => idx !== i));
  const add = () => onChange([...options, `Option ${options.length + 1}`]);
  return (
    <div className="space-y-1.5">
      {options.map((opt, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <input
            className={clsx(inputCls, 'h-8 text-xs')}
            value={opt}
            onChange={(e) => set(i, e.target.value)}
            placeholder={t('forms.option_ph', { defaultValue: 'Option label' })}
          />
          <IconBtn label="Remove option" onClick={() => remove(i)} disabled={options.length <= 1}>
            <X size={13} />
          </IconBtn>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="inline-flex items-center gap-1 text-xs font-medium text-oe-blue hover:underline"
      >
        <Plus size={12} />
        {t('forms.add_option', { defaultValue: 'Add option' })}
      </button>
    </div>
  );
}

function IconBtn({
  children,
  label,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        'inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors',
        'disabled:opacity-30 disabled:pointer-events-none',
        danger
          ? 'text-semantic-error hover:bg-semantic-error-bg'
          : 'text-content-secondary hover:bg-surface-secondary hover:text-content-primary',
      )}
    >
      {children}
    </button>
  );
}

/* -- Helpers --------------------------------------------------------------- */

function extractIssues(err: unknown): FieldIssue[] {
  if (err instanceof ApiError && err.body && typeof err.body === 'object') {
    const detail = (err.body as { detail?: unknown }).detail;
    if (detail && typeof detail === 'object' && Array.isArray((detail as { issues?: unknown }).issues)) {
      return (detail as { issues: FieldIssue[] }).issues;
    }
  }
  return [];
}
