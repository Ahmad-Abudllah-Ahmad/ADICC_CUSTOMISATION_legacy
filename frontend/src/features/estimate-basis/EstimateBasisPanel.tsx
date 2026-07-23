// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Basis-of-estimate panel. Drafts the inclusions, exclusions and assumptions
// from the finished estimate (which trades are present, absent or flagged by the
// coverage check), lets the estimator edit and toggle each line, and exports the
// result as Markdown to attach to a proposal.

import { Fragment, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ClipboardList,
  Download,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { Badge, Button, Card, CardContent, CardHeader, EmptyState, ErrorState } from '@/shared/ui';
import { getErrorMessage, triggerDownload } from '@/shared/lib/api';
import { formatCurrency } from '@/shared/lib/money';
import {
  generateBasis,
  getBasis,
  listBasis,
  updateBasis,
  type CoverageSummary,
  type EstimateBasisDocument,
  type QualificationCategory,
  type QualificationItem,
} from './api';
import {
  basisFilename,
  makeItemId,
  newManualItem,
  renderBasisMarkdown,
  type MarkdownLabels,
} from './parts';

export interface EstimateBasisPanelProps {
  /** Project whose estimate the basis is drafted from. */
  projectId: string;
  /** Optionally scope the derivation to a single BOQ. */
  boqId?: string | null;
  /** ISO currency code, woven into the money assumption and used for display. */
  currency?: string;
  /** Optional base date, woven into the escalation assumption. */
  baseDate?: string | null;
}

interface Draft {
  title: string;
  status: string;
  notes: string;
  inclusions: QualificationItem[];
  exclusions: QualificationItem[];
  assumptions: QualificationItem[];
}

function draftFromDoc(doc: EstimateBasisDocument): Draft {
  return {
    title: doc.title,
    status: doc.status,
    notes: doc.notes ?? '',
    inclusions: doc.inclusions ?? [],
    exclusions: doc.exclusions ?? [],
    assumptions: doc.assumptions ?? [],
  };
}

const CATEGORY_KEYS = ['inclusions', 'exclusions', 'assumptions'] as const;
type CategoryKey = (typeof CATEGORY_KEYS)[number];

const CATEGORY_OF: Record<CategoryKey, QualificationCategory> = {
  inclusions: 'inclusion',
  exclusions: 'exclusion',
  assumptions: 'assumption',
};

export function EstimateBasisPanel({ projectId, boqId, currency, baseDate }: EstimateBasisPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [dirty, setDirty] = useState(false);

  const listQuery = useQuery({
    queryKey: ['estimate-basis', 'list', projectId],
    queryFn: () => listBasis(projectId),
    enabled: projectId.length > 0,
  });

  // Default the selection to the newest document once the list arrives.
  const newestId = listQuery.data?.items[0]?.id ?? null;
  useEffect(() => {
    if (selectedId === null && newestId) setSelectedId(newestId);
  }, [newestId, selectedId]);

  const docQuery = useQuery({
    queryKey: ['estimate-basis', 'doc', selectedId],
    queryFn: () => getBasis(selectedId as string),
    enabled: !!selectedId,
  });

  const loaded = docQuery.data;
  // Re-seed the editable draft whenever a different revision loads.
  useEffect(() => {
    if (loaded) {
      setDraft(draftFromDoc(loaded));
      setDirty(false);
    }
  }, [loaded?.id, loaded?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const generateMutation = useMutation({
    mutationFn: () =>
      generateBasis({
        project_id: projectId,
        boq_id: boqId ?? null,
        currency: currency ?? '',
        base_date: baseDate ?? null,
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['estimate-basis', 'list', projectId] });
      queryClient.setQueryData(['estimate-basis', 'doc', created.id], created);
      setSelectedId(created.id);
      setDraft(draftFromDoc(created));
      setDirty(false);
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!selectedId || !draft) throw new Error('nothing to save');
      return updateBasis(selectedId, {
        title: draft.title,
        status: draft.status === 'final' ? 'final' : 'draft',
        notes: draft.notes,
        inclusions: draft.inclusions,
        exclusions: draft.exclusions,
        assumptions: draft.assumptions,
      });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(['estimate-basis', 'doc', updated.id], updated);
      queryClient.invalidateQueries({ queryKey: ['estimate-basis', 'list', projectId] });
      setDraft(draftFromDoc(updated));
      setDirty(false);
    },
  });

  // ── Draft mutations ────────────────────────────────────────────────────────

  function patchItems(key: CategoryKey, next: QualificationItem[]) {
    setDraft((prev) => (prev ? { ...prev, [key]: next } : prev));
    setDirty(true);
  }

  function updateItemText(key: CategoryKey, id: string, text: string) {
    if (!draft) return;
    patchItems(
      key,
      draft[key].map((it) => (it.id === id ? { ...it, text } : it)),
    );
  }

  function toggleItem(key: CategoryKey, id: string) {
    if (!draft) return;
    patchItems(
      key,
      draft[key].map((it) => (it.id === id ? { ...it, enabled: !it.enabled } : it)),
    );
  }

  function removeItem(key: CategoryKey, id: string) {
    if (!draft) return;
    patchItems(
      key,
      draft[key].filter((it) => it.id !== id),
    );
  }

  function addItem(key: CategoryKey) {
    if (!draft) return;
    patchItems(key, [...draft[key], newManualItem(CATEGORY_OF[key], makeItemId())]);
  }

  function setTitle(title: string) {
    setDraft((prev) => (prev ? { ...prev, title } : prev));
    setDirty(true);
  }

  function setNotes(notes: string) {
    setDraft((prev) => (prev ? { ...prev, notes } : prev));
    setDirty(true);
  }

  function toggleFinal() {
    setDraft((prev) => (prev ? { ...prev, status: prev.status === 'final' ? 'draft' : 'final' } : prev));
    setDirty(true);
  }

  function onExport() {
    if (!loaded || !draft) return;
    const labels: MarkdownLabels = {
      inclusions: t('estimateBasis.section.inclusions', { defaultValue: 'Inclusions' }),
      exclusions: t('estimateBasis.section.exclusions', { defaultValue: 'Exclusions' }),
      assumptions: t('estimateBasis.section.assumptions', { defaultValue: 'Assumptions' }),
      notes: t('estimateBasis.section.notes', { defaultValue: 'Notes' }),
      none: t('estimateBasis.none', { defaultValue: 'None.' }),
      status: t('estimateBasis.meta.status', { defaultValue: 'Status' }),
      generated: t('estimateBasis.meta.generated', { defaultValue: 'Generated' }),
    };
    // Export exactly what the estimator is looking at (their unsaved edits too).
    const forExport: EstimateBasisDocument = { ...loaded, ...draft };
    const md = renderBasisMarkdown(forExport, labels);
    triggerDownload(new Blob([md], { type: 'text/markdown;charset=utf-8;' }), basisFilename(draft.title));
  }

  const generating = generateMutation.isPending;
  const hasDocuments = (listQuery.data?.items.length ?? 0) > 0;

  // ── Render ───────────────────────────────────────────────────────────────

  if (listQuery.isError) {
    return <ErrorState title={getErrorMessage(listQuery.error)} onRetry={() => listQuery.refetch()} />;
  }

  // Initial fetch: show a loader so the panel is never a bare header with
  // disabled buttons while the document list is still on the wire.
  if (listQuery.isLoading && !hasDocuments) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border-light px-3 py-4 text-sm text-content-tertiary">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        {t('estimateBasis.loadingList', { defaultValue: 'Loading basis of estimate...' })}
      </div>
    );
  }

  if (!hasDocuments && !generating && !listQuery.isLoading) {
    return (
      <EmptyState
        icon={<FileText className="h-6 w-6" aria-hidden />}
        title={t('estimateBasis.empty.title', { defaultValue: 'No basis of estimate yet' })}
        description={t('estimateBasis.empty.body', {
          defaultValue:
            'Draft the inclusions, exclusions and assumptions automatically from the estimate contents.',
        })}
        action={
          <Button onClick={() => generateMutation.mutate()} disabled={generating}>
            {t('estimateBasis.generate', { defaultValue: 'Draft basis of estimate' })}
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-content-tertiary" aria-hidden />
          <h2 className="text-lg font-semibold text-content-primary">
            {t('estimateBasis.heading', { defaultValue: 'Basis of estimate' })}
          </h2>
          {draft && (
            <Badge variant={draft.status === 'final' ? 'success' : 'neutral'}>
              {draft.status === 'final'
                ? t('estimateBasis.status.final', { defaultValue: 'Final' })
                : t('estimateBasis.status.draft', { defaultValue: 'Draft' })}
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => generateMutation.mutate()}
            disabled={generating}
            icon={
              generating ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <RefreshCw className="h-4 w-4" aria-hidden />
              )
            }
          >
            {hasDocuments
              ? t('estimateBasis.regenerate', { defaultValue: 'Regenerate' })
              : t('estimateBasis.generate', { defaultValue: 'Draft basis of estimate' })}
          </Button>
          <Button
            variant="secondary"
            onClick={onExport}
            disabled={!draft}
            icon={<Download className="h-4 w-4" aria-hidden />}
          >
            {t('estimateBasis.export', { defaultValue: 'Export' })}
          </Button>
          <Button
            variant="secondary"
            onClick={() => navigate('/tendering')}
            icon={<Send className="h-4 w-4" aria-hidden />}
          >
            {t('estimateBasis.openTendering', { defaultValue: 'Open Tendering' })}
          </Button>
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={!dirty || saveMutation.isPending}
            icon={
              saveMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Save className="h-4 w-4" aria-hidden />
              )
            }
          >
            {t('estimateBasis.save', { defaultValue: 'Save' })}
          </Button>
        </div>
      </div>

      {generateMutation.isError && (
        <ErrorState title={getErrorMessage(generateMutation.error)} onRetry={() => generateMutation.mutate()} />
      )}
      {saveMutation.isError && <ErrorState title={getErrorMessage(saveMutation.error)} />}

      {(docQuery.isLoading || (generating && !draft)) && (
        <div className="flex items-center gap-2 rounded-lg border border-border-light px-3 py-4 text-sm text-content-tertiary">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {generating
            ? t('estimateBasis.drafting', { defaultValue: 'Drafting basis of estimate...' })
            : t('estimateBasis.loading', { defaultValue: 'Loading basis of estimate...' })}
        </div>
      )}
      {docQuery.isError && (
        <ErrorState title={getErrorMessage(docQuery.error)} onRetry={() => docQuery.refetch()} />
      )}

      {loaded && draft && (
        <div className="space-y-4">
          <input
            aria-label={t('estimateBasis.titleLabel', { defaultValue: 'Document title' })}
            value={draft.title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-lg border border-border-light bg-surface-primary px-3 py-2 text-sm font-medium text-content-primary"
          />

          <CoverageStrip coverage={loaded.coverage} currency={currency} boqId={boqId} />

          {CATEGORY_KEYS.map((key) => (
            <Section
              key={key}
              heading={t(`estimateBasis.section.${CATEGORY_OF[key]}s`, {
                defaultValue:
                  key === 'inclusions' ? 'Inclusions' : key === 'exclusions' ? 'Exclusions' : 'Assumptions',
              })}
              items={draft[key]}
              onToggle={(id) => toggleItem(key, id)}
              onText={(id, text) => updateItemText(key, id, text)}
              onRemove={(id) => removeItem(key, id)}
              onAdd={() => addItem(key)}
              addLabel={t('estimateBasis.addLine', { defaultValue: 'Add line' })}
              emptyLabel={t('estimateBasis.sectionEmpty', { defaultValue: 'No lines yet.' })}
            />
          ))}

          <div>
            <label
              htmlFor="estimate-basis-notes"
              className="mb-1.5 block text-sm font-medium text-content-primary"
            >
              {t('estimateBasis.section.notes', { defaultValue: 'Notes' })}
            </label>
            <textarea
              id="estimate-basis-notes"
              value={draft.notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder={t('estimateBasis.notesPlaceholder', {
                defaultValue: 'Any additional qualification for the client...',
              })}
              className="w-full rounded-lg border border-border-light bg-surface-primary px-3 py-2 text-sm text-content-primary"
            />
          </div>

          <div className="flex items-center justify-between">
            <Button variant="ghost" onClick={toggleFinal}>
              {draft.status === 'final'
                ? t('estimateBasis.reopen', { defaultValue: 'Reopen as draft' })
                : t('estimateBasis.markFinal', { defaultValue: 'Mark as final' })}
            </Button>
            {dirty && (
              <span className="text-xs text-content-tertiary">
                {t('estimateBasis.unsaved', { defaultValue: 'Unsaved changes' })}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Coverage strip ───────────────────────────────────────────────────────────

function CoverageStrip({
  coverage,
  currency,
  boqId,
}: {
  coverage: CoverageSummary;
  currency?: string;
  boqId?: string | null;
}) {
  const { t } = useTranslation();
  // A coverage gap should be one click from where it gets fixed: the bill of
  // quantities. Deep-link to the scoped BOQ when we have its id, else the list.
  const boqHref = boqId ? `/boq/${boqId}` : '/boq';
  const openBoqTitle = t('estimateBasis.coverage.openBoq', {
    defaultValue: 'Open in the bill of quantities',
  });
  const flags = useMemo(() => {
    const parts: string[] = [];
    if (coverage.zero_rate_positions > 0)
      parts.push(t('estimateBasis.flag.unpriced', { defaultValue: '{{n}} unpriced', n: coverage.zero_rate_positions }));
    if (coverage.missing_quantity_positions > 0)
      parts.push(
        t('estimateBasis.flag.missingQty', {
          defaultValue: '{{n}} missing qty',
          n: coverage.missing_quantity_positions,
        }),
      );
    if (coverage.provisional_positions > 0)
      parts.push(
        t('estimateBasis.flag.provisional', {
          defaultValue: '{{n}} provisional',
          n: coverage.provisional_positions,
        }),
      );
    if (coverage.unclassified_positions > 0)
      parts.push(
        t('estimateBasis.flag.unclassified', {
          defaultValue: '{{n}} unclassified',
          n: coverage.unclassified_positions,
        }),
      );
    return parts;
  }, [coverage, t]);

  return (
    <Card>
      <CardHeader
        title={t('estimateBasis.coverage.title', {
          defaultValue: 'Coverage · {{count}} items',
          count: coverage.total_positions,
        })}
      />
      <CardContent className="space-y-3">
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-content-tertiary">
            {t('estimateBasis.coverage.present', { defaultValue: 'Trades present' })}
          </div>
          {coverage.present_trades.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {coverage.present_trades.map((tr) => (
                <Link
                  key={tr.code}
                  to={boqHref}
                  title={openBoqTitle}
                  className="inline-flex items-center gap-1 rounded-full border border-border-light bg-surface-secondary px-2 py-0.5 text-xs text-content-secondary transition-colors hover:border-oe-blue hover:bg-oe-blue-subtle hover:text-oe-blue-text"
                >
                  <span className="font-medium text-content-primary">{tr.label}</span>
                  <span className="text-content-tertiary">· {tr.position_count}</span>
                  <span className="tabular-nums">· {formatCurrency(tr.total, currency)}</span>
                </Link>
              ))}
            </div>
          ) : (
            <span className="text-xs text-content-tertiary">
              {t('estimateBasis.coverage.noTrades', { defaultValue: 'No classified trades' })}
            </span>
          )}
        </div>

        {coverage.absent_trades.length > 0 && (
          <div>
            <div className="mb-1 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-content-tertiary">
              <AlertTriangle className="h-3.5 w-3.5 text-semantic-warning" aria-hidden />
              {t('estimateBasis.coverage.absent', { defaultValue: 'Expected trades not found' })}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {coverage.absent_trades.map((tr) => (
                <Link
                  key={tr.code}
                  to={boqHref}
                  title={openBoqTitle}
                  className="rounded-full border border-semantic-warning/30 bg-semantic-warning/10 px-2 py-0.5 text-xs text-content-secondary transition-colors hover:border-semantic-warning hover:bg-semantic-warning/20"
                >
                  {tr.label}
                </Link>
              ))}
            </div>
          </div>
        )}

        {flags.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-content-tertiary">
            <span>{t('estimateBasis.coverage.flags', { defaultValue: 'Flags' })}:</span>
            {flags.map((f, i) => (
              <Fragment key={f}>
                {i > 0 && (
                  <span aria-hidden className="text-content-quaternary">
                    ·
                  </span>
                )}
                <Link
                  to={boqHref}
                  title={openBoqTitle}
                  className="rounded text-oe-blue-text underline-offset-2 hover:underline"
                >
                  {f}
                </Link>
              </Fragment>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border-light pt-3 text-xs">
          <Link
            to={boqHref}
            className="inline-flex items-center gap-1 font-medium text-oe-blue-text hover:underline"
          >
            <ClipboardList className="h-3.5 w-3.5" aria-hidden />
            {openBoqTitle}
          </Link>
          <Link
            to="/validation"
            className="inline-flex items-center gap-1 font-medium text-oe-blue-text hover:underline"
          >
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
            {t('estimateBasis.coverage.reviewValidation', { defaultValue: 'Review in Validation' })}
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Section editor ───────────────────────────────────────────────────────────

interface SectionProps {
  heading: string;
  items: QualificationItem[];
  onToggle: (id: string) => void;
  onText: (id: string, text: string) => void;
  onRemove: (id: string) => void;
  onAdd: () => void;
  addLabel: string;
  emptyLabel: string;
}

function Section({
  heading,
  items,
  onToggle,
  onText,
  onRemove,
  onAdd,
  addLabel,
  emptyLabel,
}: SectionProps) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader
        title={
          <span className="text-sm font-semibold text-content-primary">
            {heading} <span className="text-content-tertiary">({items.length})</span>
          </span>
        }
        action={
          <Button variant="ghost" size="sm" onClick={onAdd} icon={<Plus className="h-4 w-4" aria-hidden />}>
            {addLabel}
          </Button>
        }
      />
      <CardContent className="space-y-2">
        {items.length === 0 && <p className="text-sm text-content-tertiary">{emptyLabel}</p>}
        {items.map((it) => (
          <div key={it.id} className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={it.enabled}
              onChange={() => onToggle(it.id)}
              className="mt-2 h-4 w-4 shrink-0 rounded border-border-light"
              aria-label={t('estimateBasis.includeLine', {
                defaultValue: 'Include this line in the export',
              })}
            />
            <textarea
              value={it.text}
              onChange={(e) => onText(it.id, e.target.value)}
              rows={1}
              aria-label={t('estimateBasis.lineText', { defaultValue: 'Line text' })}
              className={`min-h-[2.25rem] flex-1 rounded-lg border border-border-light bg-surface-primary px-2.5 py-1.5 text-sm text-content-primary ${
                it.enabled ? '' : 'text-content-tertiary line-through'
              }`}
            />
            {it.trade_label && (
              <span className="mt-1.5 hidden shrink-0 rounded bg-surface-secondary px-1.5 py-0.5 text-xs text-content-tertiary sm:inline">
                {it.trade_label}
              </span>
            )}
            <button
              type="button"
              onClick={() => onRemove(it.id)}
              className="mt-1.5 shrink-0 rounded p-1 text-content-tertiary hover:text-semantic-error"
              aria-label={t('estimateBasis.removeLine', { defaultValue: 'Remove line' })}
            >
              <Trash2 className="h-4 w-4" aria-hidden />
            </button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
