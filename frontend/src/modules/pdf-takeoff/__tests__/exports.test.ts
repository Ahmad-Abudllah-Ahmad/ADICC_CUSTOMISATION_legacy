// OpenConstructionERP — DataDrivenConstruction (DDC)
// CAD2DATA Pipeline · PDF Takeoff exports — unit tests
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// DDC-CWICR-OE-2026
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { Measurement } from '../../../features/takeoff/lib/takeoff-types';
import {
  buildExportFilename,
  buildTakeoffPdf,
  buildTakeoffWorkbook,
  EXCEL_COLUMNS,
  selectAnnotatedPages,
  summariseByGroupType,
} from '../../../features/takeoff/lib/takeoff-export';

/**
 * jsdom omits the `canvas` package by default, so `<canvas>.getContext('2d')`
 * returns `null`.  The PDF exporter uses an offscreen canvas to bake
 * annotations — stub a minimal 2D context surface with the methods the
 * renderer touches.  No pixel correctness needed for unit tests; we only
 * care that the exporter wires page-count, page-order and DOM round-tripping.
 */
beforeAll(() => {
  const makeCtxStub = (): Partial<CanvasRenderingContext2D> => ({
    lineWidth: 0,
    font: '',
    strokeStyle: '#000000',
    fillStyle: '#000000',
    globalAlpha: 1,
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    beginPath: vi.fn(),
    closePath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    arc: vi.fn(),
    quadraticCurveTo: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    fillText: vi.fn(),
    measureText: () => ({ width: 50 } as TextMetrics),
    setLineDash: vi.fn(),
    setTransform: vi.fn(),
  });
  HTMLCanvasElement.prototype.getContext = function getContext(
    this: HTMLCanvasElement,
    contextId: string,
  ): RenderingContext | null {
    if (contextId === '2d') return makeCtxStub() as unknown as CanvasRenderingContext2D;
    return null;
  } as typeof HTMLCanvasElement.prototype.getContext;
  // A 1×1 JPEG (red pixel) — gives jsPDF a valid bitstream to embed
  // without triggering filesystem fallback.
  const TINY_JPEG_DATA_URL =
    'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAr/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AL+AH//Z';
  HTMLCanvasElement.prototype.toDataURL = function toDataURL(): string {
    return TINY_JPEG_DATA_URL;
  };
});

/* ── Fixtures ────────────────────────────────────────────────────── */

const GROUP_COLORS: Readonly<Record<string, string>> = {
  General: '#3B82F6',
  Structural: '#EF4444',
  Electrical: '#F59E0B',
};

const SAMPLE_MEASUREMENTS: Measurement[] = [
  {
    id: 'm1',
    type: 'distance',
    points: [
      { x: 10, y: 10 },
      { x: 110, y: 10 },
    ],
    value: 5.5,
    unit: 'm',
    label: '5.50 m',
    annotation: 'Wall run',
    page: 1,
    group: 'General',
  },
  {
    id: 'm2',
    type: 'distance',
    points: [
      { x: 0, y: 0 },
      { x: 100, y: 100 },
    ],
    value: 2.25,
    unit: 'm',
    label: '2.25 m',
    annotation: 'Door width',
    page: 1,
    group: 'General',
  },
  {
    id: 'm3',
    type: 'area',
    points: [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 100 },
      { x: 0, y: 100 },
    ],
    value: 12.5,
    unit: 'm²',
    label: '12.50 m²',
    annotation: 'Living room',
    page: 2,
    group: 'Structural',
  },
  // Annotation-only — has no numeric value, should not feed totals.
  {
    id: 'm4',
    type: 'cloud',
    points: [
      { x: 5, y: 5 },
      { x: 95, y: 5 },
      { x: 95, y: 95 },
      { x: 5, y: 95 },
    ],
    value: 0,
    unit: '',
    label: '',
    annotation: 'Revision A',
    page: 3,
    group: 'General',
  },
];

/* ── 1. Filename format ──────────────────────────────────────────── */

describe('buildExportFilename', () => {
  it('produces takeoff-{slug}-{YYYY-MM-DD}.{ext}', () => {
    // buildExportFilename formats with local-time getters (getFullYear /
    // getMonth / getDate), so construct the fixture in local time too. A UTC
    // instant ("...Z") would roll back a calendar day west of UTC and break
    // the asserted date. Month is 0-indexed: 4 = May.
    const date = new Date(2026, 4, 20, 10, 30);
    expect(buildExportFilename('Berlin · Wohnpark Lichtenberg', 'pdf', date)).toBe(
      'takeoff-berlin_wohnpark_lichtenberg-2026-05-20.pdf',
    );
    expect(buildExportFilename('São Paulo / Vila Madalena', 'xlsx', date)).toBe(
      'takeoff-são_paulo_vila_madalena-2026-05-20.xlsx',
    );
  });

  it('falls back to "untitled" on empty project name', () => {
    // Local-time construction (see note above) so the date is stable in any
    // timezone. Month is 0-indexed: 0 = January.
    const date = new Date(2026, 0, 2);
    expect(buildExportFilename('', 'pdf', date)).toBe('takeoff-untitled-2026-01-02.pdf');
    expect(buildExportFilename('   !!!   ', 'xlsx', date)).toBe(
      'takeoff-untitled-2026-01-02.xlsx',
    );
  });
});

/* ── 2. Summary aggregation math ─────────────────────────────────── */

describe('summariseByGroupType', () => {
  it('sums numeric totals per (group, type) and ignores annotations', () => {
    const rows = summariseByGroupType(SAMPLE_MEASUREMENTS, GROUP_COLORS);
    // 1× General/cloud, 1× General/distance pair, 1× Structural/area.
    expect(rows).toHaveLength(3);

    const generalDistance = rows.find((r) => r.group === 'General' && r.type === 'distance');
    expect(generalDistance).toBeDefined();
    expect(generalDistance!.count).toBe(2);
    expect(generalDistance!.total).toBeCloseTo(7.75, 5);
    expect(generalDistance!.unit).toBe('m');
    expect(generalDistance!.color).toBe('#3B82F6');

    const structuralArea = rows.find((r) => r.group === 'Structural' && r.type === 'area');
    expect(structuralArea).toBeDefined();
    expect(structuralArea!.count).toBe(1);
    expect(structuralArea!.total).toBeCloseTo(12.5, 5);

    const generalCloud = rows.find((r) => r.group === 'General' && r.type === 'cloud');
    expect(generalCloud).toBeDefined();
    expect(generalCloud!.count).toBe(1);
    // Annotation types do not contribute to numeric total.
    expect(generalCloud!.total).toBe(0);
  });

  it('orders rows by group then type for deterministic output', () => {
    const rows = summariseByGroupType(SAMPLE_MEASUREMENTS, GROUP_COLORS);
    const order = rows.map((r) => `${r.group}::${r.type}`);
    expect(order).toEqual([
      'General::cloud',
      'General::distance',
      'Structural::area',
    ]);
  });
});

/* ── 3. PDF page selection (count of visible-annotated pages) ────── */

describe('selectAnnotatedPages + buildTakeoffPdf page count', () => {
  it('returns only pages with at least one visible measurement', () => {
    // Hide "General" → only Structural/area on page 2 should remain.
    const hidden = new Set(['General']);
    expect(selectAnnotatedPages(SAMPLE_MEASUREMENTS, hidden)).toEqual([2]);
    // All visible → pages 1, 2, 3.
    expect(selectAnnotatedPages(SAMPLE_MEASUREMENTS, new Set())).toEqual([1, 2, 3]);
  });

  it('drops a page whose only measurement is hidden by id (#359)', () => {
    // m3 is the only measurement on page 2, so hiding it by id (no group
    // hidden) drops page 2 while leaving pages 1 and 3.
    expect(
      selectAnnotatedPages(SAMPLE_MEASUREMENTS, new Set(), new Set(['m3'])),
    ).toEqual([1, 3]);
    // Per-measurement hiding composes with group hiding: hide General and m3
    // and nothing visible remains anywhere.
    expect(
      selectAnnotatedPages(SAMPLE_MEASUREMENTS, new Set(['General']), new Set(['m3'])),
    ).toEqual([]);
  });

  it('produces a PDF with one page per visible-annotated page + 1 summary page', async () => {
    // Mock pdfDoc: 3 native pages, each renders a viewport of 100x100 px.
    const fakePage = {
      getViewport: ({ scale }: { scale: number }) => ({
        width: 100 * scale,
        height: 100 * scale,
      }),
      // Lazily resolve render() — exporter awaits .promise.
      render: () => ({ promise: Promise.resolve() }),
    };
    const fakeDoc = {
      numPages: 3,
      getPage: vi.fn(async () => fakePage),
    } as unknown as import('pdfjs-dist').PDFDocumentProxy;

    const pdf = await buildTakeoffPdf({
      pdfDoc: fakeDoc,
      measurements: SAMPLE_MEASUREMENTS,
      hiddenGroups: new Set(),
      scale: { pixelsPerUnit: 100, unitLabel: 'm' },
      groupColorMap: GROUP_COLORS,
      projectName: 'Test Project',
    });

    // 3 annotated source pages + 1 summary page = 4.
    expect(pdf.getNumberOfPages()).toBe(4);
    expect(fakeDoc.getPage).toHaveBeenCalledTimes(3);
  });
});

/* ── 4. Excel workbook structure ─────────────────────────────────── */

describe('buildTakeoffWorkbook', () => {
  it('emits the documented column layout on the Measurements sheet', async () => {
    const wb = await buildTakeoffWorkbook({
      measurements: SAMPLE_MEASUREMENTS,
      scale: { pixelsPerUnit: 100, unitLabel: 'm' },
      groupColorMap: GROUP_COLORS,
      projectName: 'Test Project',
    });
    const ws = wb.getWorksheet('Measurements');
    expect(ws).toBeDefined();
    const headerRow = ws!.getRow(1).values as unknown as Array<string | undefined>;
    // exceljs row.values is 1-indexed; drop the leading hole.
    const headers = headerRow.slice(1).map((v) => String(v ?? ''));
    expect(headers).toEqual(EXCEL_COLUMNS.map((c) => c.header));
  });

  it('writes a Summary sheet with grand total row matching count semantics', async () => {
    const wb = await buildTakeoffWorkbook({
      measurements: SAMPLE_MEASUREMENTS,
      scale: { pixelsPerUnit: 100, unitLabel: 'm' },
      groupColorMap: GROUP_COLORS,
      projectName: 'Test Project',
    });
    const summary = wb.getWorksheet('Summary');
    expect(summary).toBeDefined();
    // Header row.
    const headers = (summary!.getRow(1).values as unknown as Array<string | undefined>)
      .slice(1)
      .map((v) => String(v ?? ''));
    expect(headers).toEqual(['Group', 'Type', 'Count', 'Total', 'Unit']);

    // Find the TOTAL row.
    let totalRowCount: number | null = null;
    summary!.eachRow((row) => {
      const groupCell = row.getCell(1).value;
      if (groupCell === 'TOTAL') {
        totalRowCount = Number(row.getCell(3).value);
      }
    });
    // 3 buckets: 2× general distance + 1× general cloud + 1× structural area
    // → count = 2 + 1 + 1 = 4.
    expect(totalRowCount).toBe(4);
  });

  /* ── Imperial measurement system (issue #270) ─────────────────────
   * Stored quantities are metric-canonical (D-TKC-016); the workbook must
   * convert values + unit labels when the user prefers imperial, and stay
   * byte-identical to the metric output when the system is metric / unset. */

  /** Read a worksheet into a plain matrix of cell values (1-based -> 0-based). */
  function sheetMatrix(ws: import('exceljs').Worksheet): unknown[][] {
    const out: unknown[][] = [];
    ws.eachRow((row) => {
      const vals = row.values as unknown as unknown[];
      out.push(vals.slice(1)); // drop the 1-based leading hole
    });
    return out;
  }

  it('metric (default) leaves the Measurements sheet in metres', async () => {
    const wb = await buildTakeoffWorkbook({
      measurements: SAMPLE_MEASUREMENTS,
      scale: { pixelsPerUnit: 100, unitLabel: 'm' },
      groupColorMap: GROUP_COLORS,
      projectName: 'Test Project',
    });
    const text = JSON.stringify(sheetMatrix(wb.getWorksheet('Measurements')!));
    expect(text).toContain('m²'); // m² present
    expect(text).not.toContain('ft');
  });

  it('imperial converts Summary totals + unit labels (m -> ft, m² -> ft²)', async () => {
    const wb = await buildTakeoffWorkbook({
      measurements: SAMPLE_MEASUREMENTS,
      scale: { pixelsPerUnit: 100, unitLabel: 'm' },
      groupColorMap: GROUP_COLORS,
      projectName: 'Test Project',
      measurementSystem: 'imperial',
    });
    const summary = wb.getWorksheet('Summary')!;

    const rows: Record<string, { total: number; unit: string }> = {};
    summary.eachRow((row) => {
      const group = row.getCell(1).value;
      const type = row.getCell(2).value;
      if (typeof group === 'string' && typeof type === 'string' && type) {
        rows[`${group}::${type}`] = {
          total: Number(row.getCell(4).value),
          unit: String(row.getCell(5).value ?? ''),
        };
      }
    });

    // General/distance: 5.5 + 2.25 = 7.75 m -> 25.426 ft.
    const dist = rows['General::distance'];
    expect(dist).toBeDefined();
    expect(dist!.unit).toBe('ft');
    expect(dist!.total).toBeCloseTo(25.426, 2);

    // Structural/area: 12.5 m² -> 134.549 ft².
    const area = rows['Structural::area'];
    expect(area).toBeDefined();
    expect(area!.unit).toBe('ft²');
    expect(area!.total).toBeCloseTo(134.549, 2);
  });

  it('imperial converts the Measurements data + subtotal rows', async () => {
    const wb = await buildTakeoffWorkbook({
      measurements: SAMPLE_MEASUREMENTS,
      scale: { pixelsPerUnit: 100, unitLabel: 'm' },
      groupColorMap: GROUP_COLORS,
      projectName: 'Test Project',
      measurementSystem: 'imperial',
    });
    const text = JSON.stringify(sheetMatrix(wb.getWorksheet('Measurements')!));
    // No metric length / area unit labels remain.
    expect(text).toContain('ft');
    expect(text).not.toContain('"m"');
    expect(text).not.toContain('m²');
  });
});
