// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Table view of files — alternative to FileGrid. */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, ExternalLink, FileText, Image as ImageIcon, Layout, Box, Pencil, File, PenTool, FileBarChart, Tag, Star } from 'lucide-react';
import clsx from 'clsx';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { primaryModule } from '../kindModule';
import { CDEBadge } from './CDEBadge';
import { favoriteKey, type FileRow, type FileKind, type FileFilters } from '../types';

const KIND_ICON: Record<FileKind, typeof FileText> = {
  document: FileText,
  photo: ImageIcon,
  sheet: Layout,
  bim_model: Box,
  dwg_drawing: Pencil,
  takeoff: Tag,
  report: FileBarChart,
  markup: PenTool,
};

interface FileListProps {
  items: FileRow[];
  selectedIds: Set<string>;
  onSelect: (id: string, additive: boolean, shift?: boolean) => void;
  onOpen: (row: FileRow) => void;
  sort: NonNullable<FileFilters['sort']>;
  onSortChange: (sort: NonNullable<FileFilters['sort']>) => void;
  isLoading?: boolean;
  /** ``favoriteKey(kind, id)`` membership set for the current user. */
  favoriteKeys?: Set<string>;
  /** Toggle a row's favourite state. Omit to hide the star column. */
  onToggleFavorite?: (row: FileRow, isFavorite: boolean) => void;
  /** Right-click a row — opens the shared FileContextMenu at the cursor. */
  onContextMenu?: (row: FileRow, x: number, y: number) => void;
}

function fmtBytes(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/* Render the document version as ``V01`` / ``V12``. ``extra.version`` is the
   integer the documents table stores (1-based). Coerces stringified ints
   that may arrive through the JSONB ``extra`` blob and falls back to a dash
   placeholder when there is nothing meaningful to show. */
function versionLabel(raw: unknown): string {
  const n =
    typeof raw === 'number'
      ? raw
      : typeof raw === 'string' && raw.trim() !== ''
        ? Number(raw)
        : NaN;
  if (!Number.isFinite(n) || n < 1) return '—';
  return `V${String(Math.trunc(n)).padStart(2, '0')}`;
}


type SortKey = NonNullable<FileFilters['sort']>;

export function FileList({
  items,
  selectedIds,
  onSelect,
  onOpen,
  sort,
  onSortChange,
  isLoading,
  favoriteKeys,
  onToggleFavorite,
  onContextMenu,
}: FileListProps) {
  const { t } = useTranslation();
  const showStar = Boolean(onToggleFavorite);

  // ── Keyboard roving navigation ──────────────────────────────────────
  // One row carries ``tabIndex={0}``; Up/Down move focus, Enter opens,
  // Space toggles selection, Shift+Arrow extends. Mirrors the grid.
  const [focusIndex, setFocusIndex] = useState(0);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  useEffect(() => {
    if (focusIndex > items.length - 1) {
      setFocusIndex(Math.max(0, items.length - 1));
    }
  }, [items.length, focusIndex]);

  const stepRow = (nextIndex: number, shift: boolean) => {
    const clamped = Math.max(0, Math.min(items.length - 1, nextIndex));
    const targetRow = items[clamped];
    if (shift && targetRow) onSelect(targetRow.id, true, true);
    setFocusIndex(clamped);
    rowRefs.current[clamped]?.focus();
  };

  const handleRowKeyDown = (e: React.KeyboardEvent, idx: number, row: FileRow) => {
    // Ignore keys bubbling up from the inner star / open-in buttons so their
    // own Enter/Space activation doesn't also trigger row open/select.
    if (e.target !== e.currentTarget) return;
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        stepRow(idx + 1, e.shiftKey);
        break;
      case 'ArrowUp':
        e.preventDefault();
        stepRow(idx - 1, e.shiftKey);
        break;
      case 'Home':
        e.preventDefault();
        stepRow(0, e.shiftKey);
        break;
      case 'End':
        e.preventDefault();
        stepRow(items.length - 1, e.shiftKey);
        break;
      case 'Enter':
        e.preventDefault();
        onOpen(row);
        break;
      case ' ':
      case 'Spacebar':
        e.preventDefault();
        onSelect(row.id, true);
        break;
      default:
        break;
    }
  };

  const Header = ({ field, label, align = 'left' }: { field: SortKey; label: string; align?: 'left' | 'right' }) => {
    const active = sort === field;
    return (
      <th
        className={clsx(
          'px-3 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary',
          align === 'right' && 'text-right',
          'cursor-pointer select-none hover:text-content-primary',
        )}
        onClick={() => onSortChange(field)}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {active && <ArrowDown size={10} />}
          {!active && <ArrowUp size={10} className="opacity-0" />}
        </span>
      </th>
    );
  };

  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-surface-elevated border-b border-border-light">
          <tr>
            {showStar && <th className="w-9 px-2 py-2" aria-hidden="true" />}
            <Header field="name" label={t('files.col.name', { defaultValue: 'Name' })} />
            <Header field="kind" label={t('files.col.kind', { defaultValue: 'Type' })} />
            <th className="px-3 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary text-center">
              {t('files.col.status', { defaultValue: 'Status' })}
            </th>
            <th className="px-3 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary text-center">
              {t('files.col.version', { defaultValue: 'Ver.' })}
            </th>
            <Header field="size" label={t('files.col.size', { defaultValue: 'Size' })} align="right" />
            <Header field="modified" label={t('files.col.modified', { defaultValue: 'Modified' })} align="right" />
            <th className="px-3 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
              {t('files.col.discipline', { defaultValue: 'Discipline' })}
            </th>
            <th className="px-3 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
              {t('files.col.open_in', { defaultValue: 'Open in' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {isLoading && items.length === 0 ? (
            Array.from({ length: 6 }).map((_, i) => (
              <tr key={i} className="border-b border-border-light">
                {Array.from({ length: showStar ? 9 : 8 }).map((_, j) => (
                  <td key={j} className="px-3 py-2">
                    <div className="h-3 rounded bg-surface-secondary animate-pulse" />
                  </td>
                ))}
              </tr>
            ))
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={showStar ? 9 : 8} className="px-3 py-12 text-center text-sm text-content-tertiary">
                {t('files.empty', { defaultValue: 'No files match your filters.' })}
              </td>
            </tr>
          ) : (
            items.map((row, idx) => {
              const Icon = KIND_ICON[row.kind] ?? File;
              const isSelected = selectedIds.has(row.id);
              const target = primaryModule(row.kind, row.extension);
              const TargetIcon = target.icon;
              // #284 - a PDF document reads inline; show "View" in the Open-in
              // column rather than "Open in <module>". ITEM 10 - an image /
              // video shows its target label ("View" / "Play") for the same
              // in-place reason.
              const moduleLabel = target.inlinePreview
                ? t('files.actions.view_file', { defaultValue: 'View' })
                : t(target.i18nKey, { defaultValue: target.label });
              const isFavorite = favoriteKeys?.has(favoriteKey(row.kind, row.id)) ?? false;
              return (
                <tr
                  key={row.id}
                  ref={(el) => {
                    rowRefs.current[idx] = el;
                  }}
                  tabIndex={idx === focusIndex ? 0 : -1}
                  className={clsx(
                    'border-b border-border-light cursor-pointer transition-colors',
                    'focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-oe-blue/40',
                    isSelected
                      ? 'bg-oe-blue/10'
                      : 'hover:bg-surface-secondary/60',
                  )}
                  onClick={(e) => {
                    setFocusIndex(idx);
                    onSelect(row.id, e.metaKey || e.ctrlKey, e.shiftKey);
                  }}
                  onDoubleClick={() => onOpen(row)}
                  onKeyDown={(e) => handleRowKeyDown(e, idx, row)}
                  onContextMenu={
                    onContextMenu
                      ? (e) => {
                          e.preventDefault();
                          onContextMenu(row, e.clientX, e.clientY);
                        }
                      : undefined
                  }
                >
                  {showStar && (
                    <td className="px-2 py-2 text-center">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onToggleFavorite?.(row, isFavorite);
                        }}
                        aria-pressed={isFavorite}
                        className={clsx(
                          'inline-flex items-center justify-center h-6 w-6 rounded-md transition-colors',
                          'focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40',
                          isFavorite
                            ? 'text-amber-500 hover:text-amber-600'
                            : 'text-content-tertiary/40 hover:text-amber-500',
                        )}
                        title={
                          isFavorite
                            ? t('files.favorites.remove', { defaultValue: 'Remove from favourites' })
                            : t('files.favorites.add', { defaultValue: 'Add to favourites' })
                        }
                      >
                        <Star size={13} strokeWidth={2} fill={isFavorite ? 'currentColor' : 'none'} />
                      </button>
                    </td>
                  )}
                  <td className="px-3 py-2 max-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <Icon size={14} strokeWidth={1.75} className="shrink-0 text-content-tertiary" />
                      {typeof row.extra?.drawing_number === 'string' && row.extra.drawing_number && (
                        <span
                          className="font-mono text-[11px] text-content-tertiary shrink-0"
                          title="Drawing number"
                        >
                          {row.extra.drawing_number}
                        </span>
                      )}
                      <span className="truncate text-content-primary" title={row.name}>
                        {row.name}
                      </span>
                      {typeof row.extra?.revision_code === 'string' && row.extra.revision_code && (
                        <span
                          className="inline-flex items-center rounded-md border border-border-light px-1.5 py-0.5 text-[10px] font-medium text-content-secondary shrink-0"
                          title="Revision"
                        >
                          Rev {row.extra.revision_code}
                        </span>
                      )}
                      {/* CDE state moved to its own dedicated Status column. */}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-content-secondary text-xs">
                    {t(`files.category.${row.kind}`, { defaultValue: row.kind })}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {typeof row.extra?.cde_state === 'string' && row.extra.cde_state ? (
                      <CDEBadge state={row.extra.cde_state} />
                    ) : (
                      <span className="text-content-quaternary text-xs">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center text-content-secondary tabular-nums text-xs">
                    {versionLabel(row.extra?.version)}
                  </td>
                  <td className="px-3 py-2 text-right text-content-secondary tabular-nums text-xs">
                    {fmtBytes(row.size_bytes)}
                  </td>
                  <td className="px-3 py-2 text-right text-content-secondary text-xs">
                    {row.modified_at ? <DateDisplay value={row.modified_at} format="relative" /> : '—'}
                  </td>
                  <td className="px-3 py-2 text-content-tertiary text-xs truncate">
                    {row.discipline ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpen(row);
                      }}
                      className={clsx(
                        'inline-flex items-center gap-1 h-6 px-2 rounded-md text-[10.5px] font-medium transition-colors',
                        'border border-border-light text-content-secondary',
                        'hover:border-oe-blue/40 hover:text-oe-blue hover:bg-oe-blue/5',
                      )}
                      title={t(target.descriptionI18nKey, { defaultValue: target.description })}
                    >
                      <TargetIcon size={10} strokeWidth={2} className="shrink-0" />
                      <span className="truncate max-w-[160px]">{moduleLabel}</span>
                      <ExternalLink size={9} className="shrink-0 opacity-60" />
                    </button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
