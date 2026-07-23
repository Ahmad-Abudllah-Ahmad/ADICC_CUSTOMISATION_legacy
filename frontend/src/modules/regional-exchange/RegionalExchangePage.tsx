// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * RegionalExchangePage - polymorphic BOQ exchange page (Wave 5 Epic I).
 *
 * Replaces 20 near-identical country modules with one component driven
 * by a `RegionalTemplate` from `regionalRegistry.ts`. The country pack
 * provides the flag, label, format hint, column mapping, trade-section
 * reference, and import endpoint; everything else (file drop, parse,
 * preview, target-BOQ selector, export, print) is shared logic.
 *
 * All UI strings flow through i18next so locales drop into ONE keyspace
 * (`regional.*`) rather than 20 (`au.*`, `br.*`, `ca.*`, ...).
 */

import { useState, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Upload,
  Download,
  FileUp,
  FileDown,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Eye,
  X,
  Info,
  Printer,
} from 'lucide-react';
import { Button, Badge, DismissibleInfo, IntroRichText } from '@/shared/ui';
import { PageHeader } from '@/shared/ui/PageHeader';
import { apiGet, apiPost } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import { parseExcelFile } from '../_shared/excelImport';
import { exportToCSV, downloadBlob } from '../_shared/excelExport';
import { printBOQReport } from '../_shared/pdfBOQExport';
import { SampleTemplateButton } from '../_shared/SampleTemplateButton';
import type { ExchangePosition, ImportParseResult } from '../_shared/templateTypes';
import type { RegionalTemplate } from './regionalRegistry';
import { importDispatcher } from './regionalRegistry';

/* ── Types from the BOQ module ──────────────────────────────────────── */

interface Project {
  id: string;
  name: string;
}
interface BOQ {
  id: string;
  name: string;
  project_id: string;
}
interface BOQPosition {
  id: string;
  ordinal: string;
  description: string;
  unit: string;
  quantity: number;
  unit_rate: number;
  total?: number;
  parent_id?: string | null;
  is_section?: boolean;
  section?: string;
  classification?: Record<string, string>;
}

type ExportFormatChoice = 'detailed' | 'summary';

/* ── Import preview table ───────────────────────────────────────────── */

function ImportPreview({
  positions,
  template,
  t,
}: {
  positions: ExchangePosition[];
  template: RegionalTemplate;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const [showAll, setShowAll] = useState(false);
  const displayed = showAll ? positions : positions.slice(0, 20);

  return (
    <div className="border border-border-light rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-surface-tertiary/50 flex items-center justify-between">
        <span className="text-xs font-medium text-content-secondary">
          {t('regional.preview', { defaultValue: 'Preview' })}: {positions.length}{' '}
          {t('regional.positions', { defaultValue: 'positions' })}
        </span>
        {positions.length > 20 && (
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="text-2xs text-oe-blue hover:underline"
          >
            {showAll
              ? t('regional.show_less', { defaultValue: 'Show less' })
              : t('regional.show_all', { defaultValue: 'Show all', count: positions.length })}
          </button>
        )}
      </div>
      <div className="overflow-x-auto max-h-80">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-surface-secondary/50 sticky top-0">
              <th className="px-3 py-1.5 text-left font-medium text-content-secondary w-24">
                {t('boq.ordinal', { defaultValue: 'Ordinal' })}
              </th>
              <th className="px-3 py-1.5 text-left font-medium text-content-secondary">
                {t('boq.description', { defaultValue: 'Description' })}
              </th>
              <th className="px-3 py-1.5 text-center font-medium text-content-secondary w-16">
                {t('boq.unit', { defaultValue: 'Unit' })}
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-content-secondary w-20">
                {t('boq.quantity', { defaultValue: 'Qty' })}
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-content-secondary w-20">
                {t('boq.unit_rate', { defaultValue: 'Rate' })}
              </th>
              <th className="px-3 py-1.5 text-left font-medium text-content-secondary w-32">
                {template.excelTemplate.classification ||
                  t('regional.classification', { defaultValue: 'Classification' })}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-light">
            {displayed.map((pos, idx) => {
              const code = pos.classification ? Object.values(pos.classification)[0] : '';
              const info = code
                ? template.tradeSections.find((s) => code.startsWith(s.code))
                : undefined;
              return (
                <tr
                  key={pos.ordinal || `pos-${idx}`}
                  className={`hover:bg-surface-secondary/30 ${
                    idx % 2 === 0 ? 'bg-surface-primary/50' : ''
                  }`}
                >
                  <td className="px-3 py-1.5 font-mono text-content-tertiary">{pos.ordinal}</td>
                  <td
                    className="px-3 py-1.5 text-content-primary max-w-[300px] truncate"
                    title={pos.description}
                  >
                    {pos.description || '-'}
                  </td>
                  <td className="px-3 py-1.5 text-center text-content-secondary">
                    {pos.unit || '-'}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {pos.quantity > 0 ? pos.quantity.toFixed(3) : '-'}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {pos.unitRate > 0 ? pos.unitRate.toFixed(2) : '-'}
                  </td>
                  <td
                    className="px-3 py-1.5 text-content-tertiary text-2xs truncate"
                    title={info ? `${info.code} - ${info.label}` : code}
                  >
                    {code || '-'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Main polymorphic component ─────────────────────────────────────── */

export interface RegionalExchangePageProps {
  /** The country pack driving this page. */
  template: RegionalTemplate;
}

export default function RegionalExchangePage({ template }: RegionalExchangePageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const addToast = useToastStore((s) => s.addToast);
  const queryClient = useQueryClient();

  /* Import state */
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [parsedResult, setParsedResult] = useState<ImportParseResult | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [importTargetBoqId, setImportTargetBoqId] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importResult, setImportResult] = useState<{
    imported: number;
    errors: string[];
  } | null>(null);

  /* Export state */
  const [exportProjectId, setExportProjectId] = useState('');
  const [exportBoqId, setExportBoqId] = useState('');
  const [exportFormat, setExportFormat] = useState<ExportFormatChoice>('detailed');
  const [isExporting, setIsExporting] = useState(false);
  const [showExportPreview, setShowExportPreview] = useState(false);

  /* Tab state */
  const [activeTab, setActiveTab] = useState<'import' | 'export'>('import');

  /* Project + BOQ queries */
  const { data: projects = [] } = useQuery<Project[]>({
    queryKey: ['projects-list'],
    queryFn: () => apiGet<Project[]>('/v1/projects/'),
  });

  const [importProjectId, setImportProjectId] = useState('');
  const { data: importBoqs = [] } = useQuery<BOQ[]>({
    queryKey: ['boqs-for-import', importProjectId],
    queryFn: () => apiGet<BOQ[]>(`/v1/boq/boqs/?project_id=${importProjectId}`),
    enabled: !!importProjectId,
  });

  const { data: exportBoqs = [] } = useQuery<BOQ[]>({
    queryKey: ['boqs-for-export', exportProjectId],
    queryFn: () => apiGet<BOQ[]>(`/v1/boq/boqs/?project_id=${exportProjectId}`),
    enabled: !!exportProjectId,
  });

  const { data: exportPositions = [] } = useQuery<BOQPosition[]>({
    queryKey: ['boq-positions-export', exportBoqId],
    queryFn: async () => {
      const boq = await apiGet<{ positions?: BOQPosition[] }>(
        `/v1/boq/boqs/${exportBoqId}`,
      );
      return boq.positions ?? [];
    },
    enabled: !!exportBoqId,
  });

  /* ── Import handlers ────────────────────────────────────────────── */

  const handleFileSelect = useCallback(
    async (file: File) => {
      setImportFile(file);
      setParsedResult(null);
      setParseError(null);
      setImportResult(null);

      try {
        const result = await parseExcelFile(file, template.excelTemplate.defaultColumns);

        if (result.errors.length > 0) {
          setParseError(result.errors.join('; '));
        } else if (result.positions.length === 0) {
          setParseError(
            t('regional.parse_error', {
              defaultValue:
                'No positions found in the file. Ensure the file matches the expected layout.',
            }),
          );
        } else {
          setParsedResult(result);
          addToast({
            type: 'success',
            title: t('regional.parsed_ok', { defaultValue: 'File parsed successfully' }),
            message: `${result.positions.length} positions found`,
          });
        }
      } catch {
        setParseError(
          t('regional.parse_error_generic', {
            defaultValue: 'Failed to parse the file.',
          }),
        );
      }
    },
    [template, addToast, t],
  );

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFileSelect(file);
      e.target.value = '';
    },
    [handleFileSelect],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect],
  );

  const handleImport = useCallback(async () => {
    if (!parsedResult || !importTargetBoqId) return;
    setIsImporting(true);
    try {
      const positions = parsedResult.positions.map((pos) => ({
        ordinal: pos.ordinal,
        description: pos.description,
        unit: pos.unit,
        quantity: pos.quantity,
        // Money fields travel as strings (Decimal-safe) - backend re-parses.
        unit_rate: String(pos.unitRate ?? 0),
        total: String(pos.total ?? pos.quantity * (pos.unitRate ?? 0)),
        section: pos.section || undefined,
        classification: pos.classification,
      }));

      // POST to the new dispatcher endpoint (Epic I-A backend). The
      // backend auto-detects format from magic bytes / extension and
      // applies the country-specific validator pack.
      const url = importDispatcher(importTargetBoqId);
      const response = await apiPost<{ imported: number; errors?: string[] }>(url, {
        positions,
        source: `${template.id}_import`,
        country_code: template.countryCode,
        validator_packs: template.validatorPacks,
      });

      const imported = response?.imported ?? positions.length;
      const errors = response?.errors ?? [];
      setImportResult({ imported, errors });
      queryClient.invalidateQueries({ queryKey: ['boq-positions'] });
      addToast({
        type: imported > 0 ? 'success' : 'warning',
        title: t('regional.import_complete', { defaultValue: 'Import complete' }),
        message: `${imported} positions imported${
          errors.length > 0 ? `, ${errors.length} errors` : ''
        }`,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setImportResult({ imported: 0, errors: [msg] });
      addToast({
        type: 'error',
        title: t('regional.import_failed', { defaultValue: 'Import failed' }),
        message: msg,
      });
    } finally {
      setIsImporting(false);
    }
  }, [parsedResult, importTargetBoqId, template, queryClient, addToast, t]);

  const handleClearImport = useCallback(() => {
    setImportFile(null);
    setParsedResult(null);
    setParseError(null);
    setImportResult(null);
  }, []);

  /* ── Export handlers ────────────────────────────────────────────── */

  // NOTE: quantities/units here stay metric-canonical on purpose. The CSV
  // export (exportToCSV) and the import parser share one column layout, so
  // this is a round-trippable interchange format - converting to imperial
  // would corrupt the data on re-import. Left canonical like GAEB. (#270)
  const exportablePositions: ExchangePosition[] = useMemo(
    () =>
      exportPositions.map((p) => ({
        ordinal: p.ordinal,
        description: p.description,
        unit: p.unit,
        quantity: p.quantity,
        unitRate: p.unit_rate,
        total: p.total ?? p.quantity * p.unit_rate,
        section: p.section,
        parentId: p.parent_id,
        isSection: p.is_section,
        classification: p.classification,
      })),
    [exportPositions],
  );

  const selectedExportBoq = exportBoqs.find((b) => b.id === exportBoqId);
  const selectedExportProject = projects.find((p) => p.id === exportProjectId);
  const includePrices = exportFormat === 'detailed';

  const handleExport = useCallback(() => {
    if (exportablePositions.length === 0) {
      addToast({
        type: 'warning',
        title: t('regional.no_positions', { defaultValue: 'No positions to export' }),
      });
      return;
    }
    setIsExporting(true);
    try {
      const projectName = selectedExportProject?.name ?? 'Project';
      const boqName = selectedExportBoq?.name ?? 'BOQ';
      const suffix = exportFormat === 'detailed' ? 'Detailed' : 'Summary';
      const filename = `${projectName}_${boqName}_${template.countryCode}_${suffix}.csv`;

      const result = exportToCSV(exportablePositions, template.excelTemplate, filename, {
        includePrices,
      });
      downloadBlob(result.blob, result.filename);

      addToast({
        type: 'success',
        title: t('regional.export_complete', { defaultValue: 'Export complete' }),
        message: `${result.positionCount} positions exported to ${result.filename}`,
      });
    } catch (err) {
      addToast({
        type: 'error',
        title: t('regional.export_failed', { defaultValue: 'Export failed' }),
        message: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setIsExporting(false);
    }
  }, [
    exportablePositions,
    exportFormat,
    selectedExportProject,
    selectedExportBoq,
    includePrices,
    template,
    addToast,
    t,
  ]);

  const handlePrint = useCallback(() => {
    if (exportablePositions.length === 0) return;
    printBOQReport(exportablePositions, template.excelTemplate, {
      projectName: selectedExportProject?.name,
      boqName: selectedExportBoq?.name,
      includePrices,
    });
  }, [exportablePositions, selectedExportProject, selectedExportBoq, includePrices, template]);

  /* ── Render ────────────────────────────────────────────────────── */

  const parsedPositions = parsedResult?.positions ?? null;

  return (
    <div
      className="space-y-5 animate-fade-in"
      data-testid="regional-exchange-page"
      data-template-id={template.id}
    >
      <PageHeader
        srTitle={template.label}
        subtitle={
          <span data-testid="regional-format-hint">
            <span aria-hidden="true" className="mr-1.5" data-testid="regional-flag">
              {template.flag}
            </span>
            <span data-testid="regional-label">{template.label}</span>
            {template.formatHint ? <> · {template.formatHint}</> : null}
          </span>
        }
      />

      <DismissibleInfo
        storageKey={`regional-exchange-${template.id}`}
        title={t('regional.intro_title', {
          defaultValue: "Speak your country's tender format",
        })}
        more={
          t('regional.intro_more', { defaultValue: '' })
            ? <IntroRichText text={t('regional.intro_more')} />
            : undefined
        }
        links={[
          {
            label: t('nav.boq', { defaultValue: 'Bill of Quantities' }),
            onClick: () => navigate('/boq'),
          },
          {
            label: t('nav.validation', { defaultValue: 'Validation' }),
            onClick: () => navigate('/validation'),
          },
        ]}
      >
        {t('regional.intro_body', {
          defaultValue:
            "Import and export BOQ data in your region's native structure (NRM in the UK, MasterFormat in the US, DPGF in France and others), with the right trade-section breakdown applied. The data lands in or comes from a normal BOQ, so the same estimate moves across markets without re-keying.",
        })}
      </DismissibleInfo>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        <button
          type="button"
          onClick={() => setActiveTab('import')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'import'
              ? 'border-oe-blue text-oe-blue'
              : 'border-transparent text-content-tertiary hover:text-content-secondary'
          }`}
        >
          <Upload size={15} />
          {t('regional.tab_import', { defaultValue: 'Import' })}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('export')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'export'
              ? 'border-oe-blue text-oe-blue'
              : 'border-transparent text-content-tertiary hover:text-content-secondary'
          }`}
        >
          <Download size={15} />
          {t('regional.tab_export', { defaultValue: 'Export' })}
        </button>
      </div>

      {/* Import tab */}
      {activeTab === 'import' && (
        <div className="space-y-5">
          {/* File upload */}
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            className={`rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
              importFile
                ? 'border-oe-blue/50 bg-oe-blue/5'
                : 'border-border hover:border-oe-blue/30 hover:bg-surface-secondary/30'
            }`}
          >
            {importFile ? (
              <div className="space-y-3">
                <div className="flex items-center justify-center gap-2 text-sm text-content-primary">
                  <FileUp size={18} className="text-oe-blue" />
                  <span className="font-medium">{importFile.name}</span>
                  <span className="text-content-tertiary">
                    ({(importFile.size / 1024).toFixed(1)} KB)
                  </span>
                  <button
                    type="button"
                    onClick={handleClearImport}
                    className="ml-2 p-1 rounded hover:bg-surface-secondary"
                    aria-label={t('regional.clear_file', { defaultValue: 'Clear file' })}
                  >
                    <X size={14} className="text-content-tertiary" />
                  </button>
                </div>
                {parsedPositions && (
                  <div className="flex items-center justify-center gap-1.5 text-xs text-emerald-600">
                    <CheckCircle2 size={14} />
                    {parsedPositions.length}{' '}
                    {t('regional.positions_found', { defaultValue: 'positions found' })}
                    <Badge variant="blue" className="ml-2">
                      {template.excelTemplate.classification}
                    </Badge>
                  </div>
                )}
                {parseError && (
                  <div className="flex items-center justify-center gap-1.5 text-xs text-rose-600">
                    <AlertTriangle size={14} />
                    {parseError}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <FileUp size={32} className="mx-auto text-content-quaternary" />
                <p className="text-sm text-content-secondary">
                  {t('regional.drop_file', { defaultValue: 'Drop a file here, or' })}
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                >
                  {t('regional.browse', { defaultValue: 'Browse files' })}
                </Button>
                <p className="text-2xs text-content-quaternary">
                  {t('regional.formats_hint', {
                    defaultValue: 'Supported: {{exts}}',
                    exts: template.excelTemplate.acceptedExtensions.join(', '),
                  })}
                </p>
                {template.sampleFile && (
                  <a
                    href={template.sampleFile}
                    download
                    data-testid="regional-sample-link"
                    className="mt-1 inline-flex items-center gap-1.5 text-2xs font-medium text-oe-blue hover:underline"
                  >
                    <Download size={12} />
                    {t('regional.download_sample', {
                      defaultValue: 'Download a sample file to try it',
                    })}
                  </a>
                )}
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept={template.excelTemplate.acceptedExtensions.join(',')}
              className="hidden"
              onChange={handleFileInputChange}
            />
          </div>

          {/* Expected layout + ready-to-fill sample CSV */}
          {!importFile && <SampleTemplateButton template={template.excelTemplate} />}

          {/* Trade sections reference */}
          {parsedPositions && parsedPositions.length > 0 && template.tradeSections.length > 0 && (
            <div className="rounded-lg border border-border-light bg-surface-secondary/30 p-3">
              <div className="flex items-center gap-1.5 text-xs font-medium text-content-secondary mb-2">
                <Info size={13} />
                {t('regional.trades_ref', {
                  defaultValue: '{{standard}} Reference',
                  standard: template.excelTemplate.classification,
                })}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {template.tradeSections.map((sec) => (
                  <span
                    key={sec.code}
                    className="inline-flex items-center gap-1 rounded bg-surface-tertiary/50 px-2 py-0.5 text-2xs text-content-tertiary"
                  >
                    <span className="font-mono font-medium">{sec.code}</span>
                    <span>{sec.label}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Preview */}
          {parsedPositions && parsedPositions.length > 0 && (
            <ImportPreview positions={parsedPositions} template={template} t={t} />
          )}

          {/* Target BOQ selection + Import button */}
          {parsedPositions && parsedPositions.length > 0 && (
            <div className="rounded-xl border border-border bg-surface-primary p-5">
              <h3 className="text-sm font-semibold text-content-primary mb-3">
                {t('regional.target_boq', { defaultValue: 'Import Target' })}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-medium text-content-tertiary mb-1">
                    {t('common.project', { defaultValue: 'Project' })}
                  </label>
                  <select
                    value={importProjectId}
                    onChange={(e) => {
                      setImportProjectId(e.target.value);
                      setImportTargetBoqId('');
                    }}
                    className="w-full rounded-lg border border-border bg-surface-secondary px-3 py-2 text-sm"
                  >
                    <option value="">
                      — {t('regional.select_project', { defaultValue: 'Select project' })} —
                    </option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-content-tertiary mb-1">
                    {t('boq.title', { defaultValue: 'BOQ' })}
                  </label>
                  <select
                    value={importTargetBoqId}
                    onChange={(e) => setImportTargetBoqId(e.target.value)}
                    disabled={!importProjectId}
                    className="w-full rounded-lg border border-border bg-surface-secondary px-3 py-2 text-sm disabled:opacity-50"
                  >
                    <option value="">
                      — {t('regional.select_boq', { defaultValue: 'Select BOQ' })} —
                    </option>
                    {importBoqs.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-end">
                  <Button
                    variant="primary"
                    className="w-full"
                    icon={
                      isImporting ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <Upload size={15} />
                      )
                    }
                    onClick={handleImport}
                    disabled={!importTargetBoqId || isImporting}
                  >
                    {isImporting
                      ? t('regional.importing', { defaultValue: 'Importing…' })
                      : t('regional.import_btn', {
                          defaultValue: 'Import {{count}} positions',
                          count: parsedPositions.length,
                        })}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Import result */}
          {importResult && (
            <div
              className={`rounded-xl border p-4 ${
                importResult.errors.length > 0
                  ? 'border-amber-300 bg-amber-50/50 dark:bg-amber-950/20'
                  : 'border-emerald-300 bg-emerald-50/50 dark:bg-emerald-950/20'
              }`}
            >
              <div className="flex items-center gap-2 text-sm font-medium">
                {importResult.errors.length > 0 ? (
                  <AlertTriangle size={16} className="text-amber-600" />
                ) : (
                  <CheckCircle2 size={16} className="text-emerald-600" />
                )}
                <span className="text-content-primary">
                  {importResult.imported}{' '}
                  {t('regional.positions_imported', { defaultValue: 'positions imported' })}
                </span>
              </div>
              {importResult.errors.length > 0 && (
                <ul className="mt-2 space-y-1 text-xs text-content-secondary">
                  {importResult.errors.map((err, idx) => (
                    <li key={`err-${err.slice(0, 40)}-${idx}`}>• {err}</li>
                  ))}
                </ul>
              )}
              {importResult.imported > 0 && (
                <Link
                  data-testid="regional-open-boq"
                  to={importTargetBoqId ? `/boq?boq=${importTargetBoqId}` : '/boq'}
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-oe-blue hover:underline"
                >
                  {t('regional.open_boq', {
                    defaultValue: 'Open in BOQ editor to review & validate →',
                  })}
                </Link>
              )}
            </div>
          )}
        </div>
      )}

      {/* Export tab */}
      {activeTab === 'export' && (
        <div className="space-y-5">
          <div className="rounded-xl border border-border bg-surface-primary p-5">
            <h3 className="text-sm font-semibold text-content-primary mb-3">
              {t('regional.source_boq', { defaultValue: '1. Select BOQ to Export' })}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-content-tertiary mb-1">
                  {t('common.project', { defaultValue: 'Project' })}
                </label>
                <select
                  value={exportProjectId}
                  onChange={(e) => {
                    setExportProjectId(e.target.value);
                    setExportBoqId('');
                  }}
                  className="w-full rounded-lg border border-border bg-surface-secondary px-3 py-2 text-sm"
                >
                  <option value="">
                    — {t('regional.select_project', { defaultValue: 'Select project' })} —
                  </option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-content-tertiary mb-1">
                  {t('boq.title', { defaultValue: 'BOQ' })}
                </label>
                <select
                  value={exportBoqId}
                  onChange={(e) => setExportBoqId(e.target.value)}
                  disabled={!exportProjectId}
                  className="w-full rounded-lg border border-border bg-surface-secondary px-3 py-2 text-sm disabled:opacity-50"
                >
                  <option value="">
                    — {t('regional.select_boq', { defaultValue: 'Select BOQ' })} —
                  </option>
                  {exportBoqs.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-content-tertiary mb-1">
                  {t('regional.export_format', { defaultValue: 'Format' })}
                </label>
                <select
                  value={exportFormat}
                  onChange={(e) => setExportFormat(e.target.value as ExportFormatChoice)}
                  className="w-full rounded-lg border border-border bg-surface-secondary px-3 py-2 text-sm"
                >
                  <option value="detailed">
                    {t('regional.format_detailed', { defaultValue: 'Detailed (with prices)' })}
                  </option>
                  <option value="summary">
                    {t('regional.format_summary', { defaultValue: 'Summary (quantities only)' })}
                  </option>
                </select>
              </div>
            </div>
          </div>

          {exportBoqId && exportablePositions.length > 0 && (
            <div className="rounded-xl border border-border bg-surface-primary p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-content-primary">
                  {t('regional.export_summary', { defaultValue: '2. Export Summary' })}
                </h3>
                <button
                  type="button"
                  onClick={() => setShowExportPreview((v) => !v)}
                  className="flex items-center gap-1 text-xs text-oe-blue hover:underline"
                >
                  <Eye size={13} />
                  {showExportPreview
                    ? t('regional.hide_preview', { defaultValue: 'Hide preview' })
                    : t('regional.show_preview', { defaultValue: 'Show preview' })}
                </button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-lg bg-surface-secondary/50 p-3 text-center">
                  <div className="text-2xs text-content-tertiary uppercase">
                    {t('regional.positions', { defaultValue: 'Positions' })}
                  </div>
                  <div className="text-lg font-bold text-content-primary">
                    {exportablePositions.filter((p) => !p.isSection).length}
                  </div>
                </div>
                <div className="rounded-lg bg-surface-secondary/50 p-3 text-center">
                  <div className="text-2xs text-content-tertiary uppercase">
                    {t('regional.sections', { defaultValue: 'Sections' })}
                  </div>
                  <div className="text-lg font-bold text-content-primary">
                    {exportablePositions.filter((p) => p.isSection).length}
                  </div>
                </div>
                <div className="rounded-lg bg-surface-secondary/50 p-3 text-center">
                  <div className="text-2xs text-content-tertiary uppercase">
                    {t('regional.format_label', { defaultValue: 'Format' })}
                  </div>
                  <div className="text-lg font-bold text-content-primary">
                    {exportFormat === 'detailed'
                      ? t('regional.detailed_short', { defaultValue: 'Detailed' })
                      : t('regional.summary_short', { defaultValue: 'Summary' })}
                  </div>
                </div>
                <div className="rounded-lg bg-surface-secondary/50 p-3 text-center">
                  <div className="text-2xs text-content-tertiary uppercase">
                    {t('regional.prices_label', { defaultValue: 'Prices' })}
                  </div>
                  <div className="text-lg font-bold text-content-primary">
                    {includePrices
                      ? t('common.yes', { defaultValue: 'Yes' })
                      : t('common.no', { defaultValue: 'No' })}
                  </div>
                </div>
              </div>

              {showExportPreview && (
                <div className="border border-border-light rounded-lg overflow-x-auto max-h-60">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-surface-tertiary/50 sticky top-0">
                        <th className="px-3 py-1.5 text-left font-medium text-content-secondary">
                          {t('boq.ordinal', { defaultValue: 'Ordinal' })}
                        </th>
                        <th className="px-3 py-1.5 text-left font-medium text-content-secondary">
                          {t('boq.description', { defaultValue: 'Description' })}
                        </th>
                        <th className="px-3 py-1.5 text-center font-medium text-content-secondary">
                          {t('boq.unit', { defaultValue: 'Unit' })}
                        </th>
                        <th className="px-3 py-1.5 text-right font-medium text-content-secondary">
                          {t('boq.quantity', { defaultValue: 'Qty' })}
                        </th>
                        {includePrices && (
                          <th className="px-3 py-1.5 text-right font-medium text-content-secondary">
                            {t('boq.unit_rate', { defaultValue: 'Rate' })}
                          </th>
                        )}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-light">
                      {exportablePositions
                        .filter((p) => !p.isSection)
                        .slice(0, 30)
                        .map((pos, idx) => (
                          <tr
                            key={pos.ordinal || `export-${idx}`}
                            className="hover:bg-surface-secondary/30"
                          >
                            <td className="px-3 py-1.5 font-mono text-content-tertiary">
                              {pos.ordinal}
                            </td>
                            <td className="px-3 py-1.5 text-content-primary max-w-[280px] truncate">
                              {pos.description}
                            </td>
                            <td className="px-3 py-1.5 text-center text-content-secondary">
                              {pos.unit}
                            </td>
                            <td className="px-3 py-1.5 text-right tabular-nums">
                              {pos.quantity.toFixed(3)}
                            </td>
                            {includePrices && (
                              <td className="px-3 py-1.5 text-right tabular-nums">
                                {pos.unitRate.toFixed(2)}
                              </td>
                            )}
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex gap-3">
                <Button
                  variant="primary"
                  icon={
                    isExporting ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : (
                      <FileDown size={15} />
                    )
                  }
                  onClick={handleExport}
                  disabled={isExporting}
                >
                  {t('regional.export_btn', { defaultValue: 'Export as CSV' })}
                </Button>
                <Button variant="secondary" icon={<Printer size={15} />} onClick={handlePrint}>
                  {t('regional.print_btn', { defaultValue: 'Print / PDF' })}
                </Button>
              </div>
            </div>
          )}

          {exportBoqId && exportablePositions.length === 0 && (
            <div className="rounded-xl border border-border bg-surface-primary p-8 text-center">
              <FileText32 />
              <p className="text-sm text-content-tertiary">
                {t('regional.no_positions_msg', {
                  defaultValue: 'This BOQ has no positions to export.',
                })}
              </p>
            </div>
          )}
        </div>
      )}

    </div>
  );
}

/* Tiny inline icon - keeps lucide imports tight and saves a re-export. */
function FileText32() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="32"
      height="32"
      className="mx-auto mb-2 text-content-quaternary"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}
