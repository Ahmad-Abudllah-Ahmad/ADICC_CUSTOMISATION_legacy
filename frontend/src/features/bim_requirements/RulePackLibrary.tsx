// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * RulePackLibrary — top-level Rule Library browser.
 *
 * Renders a filterable / searchable grid of the 5 seed `RulePackCard`s
 * shipped in `SEED_PACKS.ts`. A "Paste your own YAML" CTA opens the
 * preview/install modal in custom mode. Selecting a card opens it in
 * seed mode with the YAML pre-loaded.
 *
 * Filtering is purely client-side: the seed packs are inlined so the
 * library functions offline. Search matches against `name + description`
 * case-insensitively; category pills are an exclusive single-select.
 */

import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ClipboardEdit, Search, BookOpenCheck } from 'lucide-react';
import clsx from 'clsx';

import { EmptyState } from '@/shared/ui';
import { useTabKeyboardNav } from '@/shared/hooks/useTabKeyboardNav';
import { RulePackCard } from './RulePackCard';
import { RulePackPreviewModal } from './RulePackPreviewModal';
import { SEED_PACKS, type SeedPack, type SeedPackCategory } from './SEED_PACKS';

export interface RulePackLibraryProps {
  /** Active project id — required to install a pack. */
  projectId: string | null;
  /** data-testid prefix override. */
  testId?: string;
}

type CategoryFilter = 'all' | SeedPackCategory;

const CATEGORY_FILTERS: Array<{
  value: CategoryFilter;
  labelKey: string;
  defaultLabel: string;
}> = [
  { value: 'all', labelKey: 'rulePacks.category_all', defaultLabel: 'All' },
  {
    value: 'Accessibility',
    labelKey: 'rulePacks.category_accessibility',
    defaultLabel: 'Accessibility',
  },
  {
    value: 'Cost Classification',
    labelKey: 'rulePacks.category_cost',
    defaultLabel: 'Cost',
  },
  { value: 'Fire Safety', labelKey: 'rulePacks.category_fire', defaultLabel: 'Fire' },
  { value: 'MEP', labelKey: 'rulePacks.category_mep', defaultLabel: 'MEP' },
  { value: 'Naming', labelKey: 'rulePacks.category_naming', defaultLabel: 'Naming' },
];

type ModalState =
  | { kind: 'closed' }
  | { kind: 'seed'; pack: SeedPack }
  | { kind: 'custom' };

export function RulePackLibrary({ projectId, testId = 'rule-pack-library' }: RulePackLibraryProps) {
  const { t } = useTranslation();
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [query, setQuery] = useState('');
  const [modal, setModal] = useState<ModalState>({ kind: 'closed' });

  const categoryIds = useMemo<readonly CategoryFilter[]>(
    () => CATEGORY_FILTERS.map((f) => f.value),
    [],
  );
  const onCategoryKeyDown = useTabKeyboardNav<CategoryFilter>({
    ids: categoryIds,
    activeId: category,
    onChange: setCategory,
    orientation: 'horizontal',
  });

  const visiblePacks = useMemo(() => {
    const q = query.trim().toLowerCase();
    return SEED_PACKS.filter((pack) => {
      if (category !== 'all' && pack.category !== category) return false;
      if (!q) return true;
      return (
        pack.name.toLowerCase().includes(q) ||
        pack.description.toLowerCase().includes(q)
      );
    });
  }, [category, query]);

  const handleSelectPack = useCallback((pack: SeedPack) => {
    setModal({ kind: 'seed', pack });
  }, []);

  const handleOpenCustom = useCallback(() => {
    setModal({ kind: 'custom' });
  }, []);

  const handleCloseModal = useCallback(() => {
    setModal({ kind: 'closed' });
  }, []);

  return (
    <div className="flex flex-col gap-5" data-testid={testId}>
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-base font-semibold text-content-primary">
            <BookOpenCheck size={18} className="text-oe-blue" />
            {t('rulePacks.title', { defaultValue: 'Rule Library' })}
          </h2>
        </div>
        <button
          type="button"
          onClick={handleOpenCustom}
          data-testid={`${testId}-paste-custom`}
          className="flex items-center gap-1.5 rounded-lg border border-oe-blue/30 bg-oe-blue/5 px-3 py-1.5 text-[12px] font-medium text-oe-blue hover:bg-oe-blue/10"
        >
          <ClipboardEdit size={14} />
          {t('rulePacks.paste_custom', { defaultValue: 'Paste your own YAML' })}
        </button>
      </div>

      {/* Filter pills + search */}
      <div className="flex flex-wrap items-center gap-3">
        <div
          className="flex flex-wrap items-center gap-1.5"
          role="tablist"
          aria-label={t('rulePacks.filter_aria', {
            defaultValue: 'Filter rule packs by category',
          })}
          onKeyDown={onCategoryKeyDown}
          data-testid={`${testId}-filters`}
        >
          {CATEGORY_FILTERS.map((f) => {
            const active = category === f.value;
            const slug = f.value.toLowerCase().replace(/\s+/g, '-');
            return (
              <button
                key={f.value}
                type="button"
                role="tab"
                id={`rule-pack-category-tab-${slug}`}
                aria-selected={active}
                aria-controls={`rule-pack-category-panel-${slug}`}
                tabIndex={active ? 0 : -1}
                onClick={() => setCategory(f.value)}
                data-testid={`${testId}-filter-${slug}`}
                className={clsx(
                  'rounded-full border px-3 py-1 text-[11px] font-medium transition-colors',
                  active
                    ? 'border-oe-blue bg-oe-blue text-white shadow-sm'
                    : 'border-border-light bg-surface-primary text-content-secondary hover:bg-surface-secondary',
                )}
              >
                {t(f.labelKey, { defaultValue: f.defaultLabel })}
              </button>
            );
          })}
        </div>
        <div className="relative ml-auto min-w-[220px] flex-1 max-w-sm">
          <Search
            size={14}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-content-tertiary"
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('rulePacks.search_placeholder', {
              defaultValue: 'Search packs…',
            })}
            data-testid={`${testId}-search`}
            className="h-9 w-full rounded-lg border border-border-light bg-surface-primary pl-8 pr-3 text-[12px] text-content-primary placeholder:text-content-tertiary focus:border-oe-blue focus:outline-none focus:ring-2 focus:ring-oe-blue/30"
          />
        </div>
      </div>

      {/* Grid */}
      {visiblePacks.length === 0 ? (
        <EmptyState
          icon={<Search size={24} strokeWidth={1.5} />}
          title={t('rulePacks.empty_title', { defaultValue: 'No matching rule packs' })}
          description={t('rulePacks.empty_desc', {
            defaultValue: 'Try a different category or clear the search to see all 5 packs.',
          })}
        />
      ) : (
        <div
          className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"
          data-testid={`${testId}-grid`}
        >
          {visiblePacks.map((pack) => (
            <RulePackCard key={pack.id} pack={pack} onSelect={handleSelectPack} />
          ))}
        </div>
      )}

      {/* Preview / install modal */}
      <RulePackPreviewModal
        open={modal.kind !== 'closed'}
        onClose={handleCloseModal}
        seedPack={modal.kind === 'seed' ? modal.pack : null}
        projectId={projectId}
      />
    </div>
  );
}

export default RulePackLibrary;
