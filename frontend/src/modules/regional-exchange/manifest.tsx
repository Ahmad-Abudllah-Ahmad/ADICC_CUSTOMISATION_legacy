// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Wave 5 Epic I — Regional Exchange module manifest.
 *
 * Replaces the 20 standalone country manifests (au-boq, br-sinapi, ca-boq,
 * cn-boq, cz-boq, de-din276, es-pbc, fr-dpgf, in-boq, it-computo, jp-sekisan,
 * kr-boq, nl-stabu, nordic-ns3420, pl-knr, ru-gesn, tr-birimfiyat, uae-boq,
 * uk-nrm, us-masterformat) with ONE manifest that registers a route per
 * country pack.
 *
 * Each route maps an old deep-link URL (e.g. `/es-pbc-exchange`) to the
 * polymorphic `RegionalExchangePage` with the matching template prop, so
 * bookmarks, sidebar links and search results from previous versions all
 * keep working.
 */

import { lazy, type ComponentType } from 'react';
import { Globe2 } from 'lucide-react';
import type { ModuleManifest } from '../_types';
import { COUNTRY_TEMPLATES } from './regionalRegistry';

/**
 * Lazy-loaded page component. React.lazy needs a `default`-shaped
 * import, so the page file uses a default export. We wrap with the
 * template-prop at route-render time using a closure factory.
 */
const RegionalExchangePage = lazy(() => import('./RegionalExchangePage'));

/**
 * One-time factory that returns a *new* React component bound to a
 * specific template. We do this so each old route mounts the same
 * underlying page but with its own template prop — without making
 * the user touch URL parameters or the registry plumbing.
 */
function makeBoundComponent(templateId: string): ComponentType<unknown> {
  const Bound: ComponentType<unknown> = () => {
    // Resolve fresh on every render so HMR + lazy template edits work.
    const template = COUNTRY_TEMPLATES.find((t) => t.id === templateId);
    if (!template) {
      // Should never happen — manifest is generated from the registry.
      return null;
    }
    // RegionalExchangePage is itself wrapped in React.lazy, so it's
    // already a LazyExoticComponent; rendering it directly is fine.
    return <RegionalExchangePage template={template} />;
  };
  Bound.displayName = `RegionalExchangePage[${templateId}]`;
  return Bound;
}

/**
 * Build per-country routes + search entries from the registry. One
 * source of truth: add a new entry to COUNTRY_TEMPLATES and the route,
 * the sidebar search hit, and the i18n bundle pick it up automatically.
 *
 * Each per-country route mounts the SAME polymorphic page, but each
 * goes through its own `React.lazy(...)` boundary so the route has a
 * stable component identity in DevTools and React Router cache.
 */
const routes = COUNTRY_TEMPLATES.map((tpl) => ({
  path: `/${tpl.routeSlug}`,
  title: tpl.label,
  component: lazy<ComponentType<unknown>>(async () => ({
    default: makeBoundComponent(tpl.id),
  })),
}));

const searchEntries = COUNTRY_TEMPLATES.map((tpl) => ({
  label: `${tpl.label} - Import / Export`,
  path: `/${tpl.routeSlug}`,
  keywords: [
    tpl.countryCode.toLowerCase(),
    tpl.id,
    tpl.label.toLowerCase(),
    tpl.excelTemplate.classification.toLowerCase(),
    'boq',
    'import',
    'export',
    'regional',
  ],
}));

export const manifest: ModuleManifest = {
  id: 'regional-exchange',
  name: 'Regional BOQ Exchange',
  description:
    'Polymorphic BOQ import / export across 20 regional cost standards (NRM, MasterFormat, DIN 276, PBC, GESN, …).',
  version: '1.0.0',
  icon: Globe2,
  category: 'regional',
  defaultEnabled: false,
  depends: ['boq'],
  routes,
  // Reached from /boq (regional import/export) — no per-country sidebar items.
  navItems: [],
  searchEntries,
  translations: {
    en: {
      'nav.regional_exchange': 'Regional BOQ Exchange',
      'regional.intro_title': "Speak your country's tender format",
      'regional.intro_body':
        "Import and export BOQ data in your region's native structure (NRM in the UK, MasterFormat in the US, DPGF in France and others), with the right trade-section breakdown applied. The data lands in or comes from a normal BOQ, so the same estimate moves across markets without re-keying.",
      'regional.tab_import': 'Import',
      'regional.tab_export': 'Export',
      'regional.import_complete': 'Import complete',
      'regional.export_complete': 'Export complete',
      'regional.import_failed': 'Import failed',
      'regional.export_failed': 'Export failed',
      'regional.drop_file': 'Drop a file here, or',
      'regional.browse': 'Browse files',
      'regional.formats_hint': 'Supported: {{exts}}',
      'regional.classification': 'Classification',
      'regional.preview': 'Preview',
      'regional.positions': 'positions',
      'regional.positions_found': 'positions found',
      'regional.positions_imported': 'positions imported',
      'regional.show_less': 'Show less',
      'regional.show_all': 'Show all',
      'regional.target_boq': 'Import Target',
      'regional.select_project': 'Select project',
      'regional.select_boq': 'Select BOQ',
      'regional.importing': 'Importing…',
      'regional.import_btn': 'Import positions',
      'regional.export_btn': 'Export as CSV',
      'regional.print_btn': 'Print / PDF',
      'regional.parsed_ok': 'File parsed successfully',
      'regional.parse_error':
        'No positions found in the file. Ensure the file matches the expected layout.',
      'regional.parse_error_generic': 'Failed to parse the file.',
      'regional.source_boq': '1. Select BOQ to Export',
      'regional.export_summary': '2. Export Summary',
      'regional.hide_preview': 'Hide preview',
      'regional.show_preview': 'Show preview',
      'regional.sections': 'Sections',
      'regional.format_label': 'Format',
      'regional.prices_label': 'Prices',
      'regional.format_detailed': 'Detailed (with prices)',
      'regional.format_summary': 'Summary (quantities only)',
      'regional.detailed_short': 'Detailed',
      'regional.summary_short': 'Summary',
      'regional.no_positions': 'No positions to export',
      'regional.no_positions_msg': 'This BOQ has no positions to export.',
      'regional.trades_ref': '{{standard}} Reference',
      'regional.download_sample': 'Download a sample file to try it',
      'regional.clear_file': 'Clear file',
      'regional.open_boq': 'Open in BOQ editor to review & validate →',
      'regional.info':
        '{{label}} is the standard cost reference / measurement framework for this region. Imports are validated against the {{packs}} rule packs before positions are added to the BOQ.',
    },
    de: {
      'nav.regional_exchange': 'Regionaler LV-Austausch',
      'regional.tab_import': 'Importieren',
      'regional.tab_export': 'Exportieren',
      'regional.import_complete': 'Import abgeschlossen',
      'regional.export_complete': 'Export abgeschlossen',
      'regional.drop_file': 'Datei hier ablegen, oder',
      'regional.browse': 'Datei wählen',
    },
    ru: {
      'nav.regional_exchange': 'Региональный обмен сметами',
      'regional.tab_import': 'Импорт',
      'regional.tab_export': 'Экспорт',
      'regional.import_complete': 'Импорт завершён',
      'regional.export_complete': 'Экспорт завершён',
      'regional.drop_file': 'Перетащите файл сюда, или',
      'regional.browse': 'Выбрать файл',
    },
    es: {
      'nav.regional_exchange': 'Intercambio Regional de BOQ',
      'regional.tab_import': 'Importar',
      'regional.tab_export': 'Exportar',
      'regional.drop_file': 'Suelte un archivo aquí, o',
      'regional.browse': 'Examinar archivos',
    },
    fr: {
      'nav.regional_exchange': 'Échange BOQ Régional',
      'regional.tab_import': 'Importer',
      'regional.tab_export': 'Exporter',
      'regional.drop_file': 'Déposez un fichier ici, ou',
      'regional.browse': 'Parcourir',
    },
    it: {
      'nav.regional_exchange': 'Scambio BOQ Regionale',
      'regional.tab_import': 'Importa',
      'regional.tab_export': 'Esporta',
      'regional.drop_file': 'Rilascia un file qui, oppure',
      'regional.browse': 'Sfoglia file',
    },
    pl: {
      'nav.regional_exchange': 'Regionalna Wymiana BOQ',
      'regional.tab_import': 'Importuj',
      'regional.tab_export': 'Eksportuj',
      'regional.drop_file': 'Upuść plik tutaj lub',
      'regional.browse': 'Przeglądaj',
    },
    cs: {
      'nav.regional_exchange': 'Regionální výměna BOQ',
      'regional.tab_import': 'Importovat',
      'regional.tab_export': 'Exportovat',
    },
    nl: {
      'nav.regional_exchange': 'Regionale BOQ-uitwisseling',
      'regional.tab_import': 'Importeren',
      'regional.tab_export': 'Exporteren',
    },
    pt: {
      'nav.regional_exchange': 'Intercâmbio Regional de BOQ',
      'regional.tab_import': 'Importar',
      'regional.tab_export': 'Exportar',
    },
    tr: {
      'nav.regional_exchange': 'Bölgesel BOQ Değişimi',
      'regional.tab_import': 'İçeri Aktar',
      'regional.tab_export': 'Dışarı Aktar',
    },
    ja: {
      'nav.regional_exchange': '地域BOQ交換',
      'regional.tab_import': 'インポート',
      'regional.tab_export': 'エクスポート',
    },
    ko: {
      'nav.regional_exchange': '지역 BOQ 교환',
      'regional.tab_import': '가져오기',
      'regional.tab_export': '내보내기',
    },
    zh: {
      'nav.regional_exchange': '区域工程量交换',
      'regional.tab_import': '导入',
      'regional.tab_export': '导出',
    },
    ar: {
      'nav.regional_exchange': 'تبادل BOQ الإقليمي',
      'regional.tab_import': 'استيراد',
      'regional.tab_export': 'تصدير',
    },
    hi: {
      'nav.regional_exchange': 'क्षेत्रीय BOQ विनिमय',
      'regional.tab_import': 'आयात',
      'regional.tab_export': 'निर्यात',
    },
  },
};
