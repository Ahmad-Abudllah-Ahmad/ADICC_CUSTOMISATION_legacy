// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the File Manager "open in module" routing resolver.
 *
 * The critical invariant (issue #273): a BIM source file (IFC/RVT/...) that
 * lives under the ``document`` kind carries the *Document* id, so opening it
 * must route through the on-demand converter via ``?docId=`` - NOT the
 * ``/bim/<id>`` path that BIMPage reads as a *model* id (which 404s, because
 * no model exists yet, and the file is never converted). A real ``bim_model``
 * row carries its own model id and must keep the path route.
 */

import { describe, it, expect } from 'vitest';
import {
  primaryModule,
  modulesForKind,
  isInlinePreviewRow,
  pdfTakeoffTargetFor,
  isImageRow,
  isVideoRow,
  isLightboxRow,
} from './kindModule';
import type { FileRow } from './types';

describe('primaryModule - BIM documents convert on demand (#273)', () => {
  it('routes a document-kind IFC through ?docId= (not a model-id path)', () => {
    const route = primaryModule('document', '.ifc').route('PROJ1', 'DOC-123');
    expect(route).toBe('/projects/PROJ1/bim?docId=DOC-123');
    // Must NOT treat the document id as a model id in the path.
    expect(route).not.toContain('/bim/DOC-123');
  });

  it('routes a document-kind RVT through ?docId= too', () => {
    expect(primaryModule('document', '.rvt').route('PROJ1', 'DOC-9')).toBe(
      '/projects/PROJ1/bim?docId=DOC-9',
    );
  });

  it('keeps a real bim_model row on the /bim/<modelId> path route', () => {
    // Regression guard: a converted model must open by its model id, never
    // be mis-sent as a ?docId= document import.
    const route = primaryModule('bim_model', '.ifc').route('PROJ1', 'MODEL-7');
    expect(route).toBe('/projects/PROJ1/bim/MODEL-7');
    expect(route).not.toContain('docId=');
  });
});

describe('primaryModule - other kinds unaffected', () => {
  it('document-kind DWG still imports on demand via ?docId=', () => {
    expect(primaryModule('document', '.dwg').route('PROJ1', 'DOC-5')).toBe(
      '/dwg-takeoff?docId=DOC-5',
    );
  });

  it('a real dwg_drawing row keeps its native ?drawingId= route', () => {
    const route = primaryModule('dwg_drawing', '.dwg').route('PROJ1', 'DRAW-2');
    expect(route).toBe('/dwg-takeoff?drawingId=DRAW-2');
    expect(route).not.toContain('docId=');
  });

  it('document-kind PDF now reads inline by default (#284), not PDF Takeoff', () => {
    const primary = primaryModule('document', '.pdf');
    // The default open action is the inline reader, flagged so consumers open
    // the overlay instead of navigating to the takeoff tool.
    expect(primary.inlinePreview).toBe(true);
    // The route is a harmless fallback that keeps the file selected in /files.
    expect(primary.route('PROJ1', 'DOC-1')).toBe('/projects/PROJ1/files?file=DOC-1');
    // It must NOT route into PDF Takeoff anymore.
    expect(primary.route('PROJ1', 'DOC-1')).not.toContain('/takeoff');
  });
});

describe('PDF documents read inline by default; Takeoff is opt-in (#284)', () => {
  function pdfRow(over: Partial<FileRow> = {}): FileRow {
    return {
      id: 'DOC-1',
      kind: 'document',
      name: 'contract.pdf',
      project_id: 'PROJ1',
      size_bytes: 1,
      mime_type: 'application/pdf',
      extension: '.pdf',
      modified_at: null,
      physical_path: '',
      relative_path: '',
      storage_backend: 'local',
      download_url: '/api/v1/documents/DOC-1/download/',
      preview_url: null,
      thumbnail_url: null,
      discipline: null,
      category: null,
      extra: {},
      ...over,
    };
  }

  it('isInlinePreviewRow is true for a PDF document with a download URL', () => {
    expect(isInlinePreviewRow(pdfRow())).toBe(true);
  });

  it('isInlinePreviewRow sniffs the mime type when the extension is missing', () => {
    expect(isInlinePreviewRow(pdfRow({ extension: null }))).toBe(true);
  });

  it('isInlinePreviewRow is false without a download URL (nothing to fetch)', () => {
    expect(isInlinePreviewRow(pdfRow({ download_url: null }))).toBe(false);
  });

  it('isInlinePreviewRow is false for a non-PDF document (e.g. an image)', () => {
    expect(
      isInlinePreviewRow(
        pdfRow({ name: 'site.jpg', extension: '.jpg', mime_type: 'image/jpeg' }),
      ),
    ).toBe(false);
  });

  it('isInlinePreviewRow is false for a DWG/IFC document (those route to a module)', () => {
    expect(
      isInlinePreviewRow(
        pdfRow({ name: 'plan.dwg', extension: '.dwg', mime_type: null }),
      ),
    ).toBe(false);
  });

  it('pdfTakeoffTargetFor offers the takeoff route for a PDF document', () => {
    const target = pdfTakeoffTargetFor(pdfRow());
    expect(target).not.toBeNull();
    expect(target!.route('PROJ1', 'DOC-1')).toBe(
      '/takeoff?doc=DOC-1&source=document&tab=measurements',
    );
  });

  it('pdfTakeoffTargetFor returns null for a non-PDF row', () => {
    expect(pdfTakeoffTargetFor(pdfRow({ extension: '.jpg', mime_type: 'image/jpeg' }))).toBeNull();
  });

  it('modulesForKind for a PDF document offers inline View first, then PDF Takeoff', () => {
    const mods = modulesForKind('document', '.pdf');
    expect(mods.length).toBeGreaterThanOrEqual(2);
    // Primary is the inline reader.
    expect(mods[0]!.inlinePreview).toBe(true);
    // PDF Takeoff is present as an explicit, non-default choice.
    const takeoff = mods.find((m) => m.label === 'PDF Takeoff');
    expect(takeoff).toBeDefined();
    expect(takeoff!.route('PROJ1', 'DOC-1')).toBe(
      '/takeoff?doc=DOC-1&source=document&tab=measurements',
    );
  });
});

describe('primaryModule - a sheet opens its PARENT document, not the sheet id (Sirega 404)', () => {
  it('routes a sheet through its parent document_id from extra', () => {
    const route = primaryModule('sheet', '.pdf').route('PROJ1', 'SHEET-1', {
      document_id: 'DOC-PARENT',
    });
    expect(route).toBe('/takeoff?doc=DOC-PARENT&source=document&tab=measurements');
    // The Sheet PK must never be sent as the doc id — that 404s the viewer.
    expect(route).not.toContain('SHEET-1');
  });

  it('falls back to the sheet id when no parent document_id is present', () => {
    expect(primaryModule('sheet', '.pdf').route('PROJ1', 'SHEET-1')).toBe(
      '/takeoff?doc=SHEET-1&source=document&tab=measurements',
    );
  });

  it('ignores an empty-string or null document_id and falls back to the id', () => {
    expect(
      primaryModule('sheet', '.pdf').route('PROJ1', 'SHEET-1', { document_id: '' }),
    ).toBe('/takeoff?doc=SHEET-1&source=document&tab=measurements');
    expect(
      primaryModule('sheet', '.pdf').route('PROJ1', 'SHEET-1', { document_id: null }),
    ).toBe('/takeoff?doc=SHEET-1&source=document&tab=measurements');
  });
});

describe('modulesForKind - document-kind BIM offers the convert-on-demand viewer', () => {
  it('returns only the ?docId= BIM viewer for a document-kind IFC', () => {
    const mods = modulesForKind('document', '.ifc');
    expect(mods).toHaveLength(1);
    expect(mods[0]!.route('PROJ1', 'DOC-123')).toBe('/projects/PROJ1/bim?docId=DOC-123');
  });

  it('a real bim_model row keeps its full module menu (viewer + explorer + clash)', () => {
    const mods = modulesForKind('bim_model', '.ifc');
    expect(mods.length).toBeGreaterThan(1);
    expect(mods[0]!.route('PROJ1', 'MODEL-7')).toBe('/projects/PROJ1/bim/MODEL-7');
  });
});

describe('images & videos open in a viewer/player, NOT PDF Takeoff (ITEM 10)', () => {
  function mediaRow(over: Partial<FileRow> = {}): FileRow {
    return {
      id: 'DOC-IMG-1',
      kind: 'document',
      name: 'site.jpg',
      project_id: 'PROJ1',
      size_bytes: 1,
      mime_type: 'image/jpeg',
      extension: '.jpg',
      modified_at: null,
      physical_path: '',
      relative_path: '',
      storage_backend: 'local',
      download_url: '/api/v1/documents/DOC-IMG-1/download/',
      preview_url: null,
      thumbnail_url: null,
      discipline: null,
      category: null,
      extra: {},
      ...over,
    };
  }

  // ── Predicates ───────────────────────────────────────────────────────
  it('isImageRow is true for common image extensions (case / dot insensitive)', () => {
    for (const ext of ['.jpg', 'JPEG', '.png', 'gif', '.webp', '.heic', '.svg', '.tiff']) {
      expect(isImageRow({ kind: 'document', extension: ext })).toBe(true);
    }
  });

  it('isImageRow falls back to the image/* mime type when the extension is unknown', () => {
    expect(
      isImageRow({ kind: 'document', extension: '.bin', mime_type: 'image/png' }),
    ).toBe(true);
  });

  it('isVideoRow is true for common video extensions and the video/* mime', () => {
    for (const ext of ['.mp4', 'MOV', '.webm', 'avi', '.mkv', '.m4v']) {
      expect(isVideoRow({ kind: 'document', extension: ext })).toBe(true);
    }
    expect(
      isVideoRow({ kind: 'document', extension: '.bin', mime_type: 'video/mp4' }),
    ).toBe(true);
  });

  it('an image is neither a video nor a PDF, and vice-versa', () => {
    expect(isVideoRow(mediaRow())).toBe(false);
    expect(isImageRow(mediaRow({ name: 'c.pdf', extension: '.pdf', mime_type: 'application/pdf' }))).toBe(false);
    expect(isVideoRow(mediaRow({ name: 'clip.mp4', extension: '.mp4', mime_type: 'video/mp4' }))).toBe(true);
  });

  // ── isLightboxRow gating ─────────────────────────────────────────────
  it('isLightboxRow is true for an image / video document with a download URL', () => {
    expect(isLightboxRow(mediaRow())).toBe(true);
    expect(
      isLightboxRow(mediaRow({ name: 'clip.mp4', extension: '.mp4', mime_type: 'video/mp4' })),
    ).toBe(true);
  });

  it('isLightboxRow is false without a download URL (nothing to fetch)', () => {
    expect(isLightboxRow(mediaRow({ download_url: null }))).toBe(false);
  });

  it('isLightboxRow excludes the photo kind (it has its own Site Photos viewer)', () => {
    expect(isLightboxRow(mediaRow({ kind: 'photo' }))).toBe(false);
  });

  it('isLightboxRow is false for a PDF (that has its own inline reader path)', () => {
    expect(
      isLightboxRow(mediaRow({ name: 'c.pdf', extension: '.pdf', mime_type: 'application/pdf' })),
    ).toBe(false);
  });

  // ── Primary action / module list never route to takeoff ──────────────
  it('the primary action for an image is the in-place media viewer, not takeoff', () => {
    const primary = primaryModule('document', '.png');
    expect(primary.mediaPreview).toBe(true);
    expect(primary.inlinePreview).toBeUndefined();
    // The fallback route keeps the file selected in /files and must NOT
    // navigate to the takeoff tool.
    const route = primary.route('PROJ1', 'DOC-IMG-1');
    expect(route).toBe('/projects/PROJ1/files?file=DOC-IMG-1');
    expect(route).not.toContain('/takeoff');
  });

  it('the primary action for a video is the in-place player, not takeoff', () => {
    const primary = primaryModule('document', '.mp4');
    expect(primary.mediaPreview).toBe(true);
    expect(primary.route('PROJ1', 'DOC-V-1')).not.toContain('/takeoff');
  });

  it('the image module list is the viewer only - PDF Takeoff is removed', () => {
    const mods = modulesForKind('document', '.jpg');
    expect(mods).toHaveLength(1);
    expect(mods[0]!.mediaPreview).toBe(true);
    expect(mods.some((m) => m.label === 'PDF Takeoff')).toBe(false);
  });

  it('the video module list is the player only - PDF Takeoff is removed', () => {
    const mods = modulesForKind('document', '.mov');
    expect(mods).toHaveLength(1);
    expect(mods[0]!.mediaPreview).toBe(true);
    expect(mods.some((m) => m.label === 'PDF Takeoff')).toBe(false);
  });

  it('pdfTakeoffTargetFor returns null for an image / video (no takeoff offer)', () => {
    expect(pdfTakeoffTargetFor(mediaRow())).toBeNull();
    expect(
      pdfTakeoffTargetFor(mediaRow({ name: 'clip.mp4', extension: '.mp4', mime_type: 'video/mp4' })),
    ).toBeNull();
  });

  it('isInlinePreviewRow is false for media (they take the lightbox path, not the PDF reader)', () => {
    expect(isInlinePreviewRow(mediaRow())).toBe(false);
    expect(
      isInlinePreviewRow(mediaRow({ name: 'clip.mp4', extension: '.mp4', mime_type: 'video/mp4' })),
    ).toBe(false);
  });
});
