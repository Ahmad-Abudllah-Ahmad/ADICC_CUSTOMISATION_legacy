// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import {
  VALIDATION_EXPORT_MEDIA,
  validationExportFilename,
  validationExportPath,
} from './validationExport';

describe('validationExportPath', () => {
  it('builds the csv export path', () => {
    expect(validationExportPath('abc-123', 'csv')).toBe(
      '/api/v1/validation/reports/abc-123/export.csv',
    );
  });

  it('builds the xlsx export path', () => {
    expect(validationExportPath('abc-123', 'xlsx')).toBe(
      '/api/v1/validation/reports/abc-123/export.xlsx',
    );
  });

  it('url-encodes the report id', () => {
    expect(validationExportPath('a/b 1', 'csv')).toBe(
      '/api/v1/validation/reports/a%2Fb%201/export.csv',
    );
  });
});

describe('validationExportFilename', () => {
  it('uses a shortened boq id when present', () => {
    expect(validationExportFilename('csv', { boqId: '0123456789abcdef-extra' })).toBe(
      'validation_findings_0123456789ab.csv',
    );
  });

  it('falls back to the report id when no boq id', () => {
    expect(validationExportFilename('xlsx', { reportId: 'rep-7' })).toBe(
      'validation_findings_rep-7.xlsx',
    );
  });

  it('falls back to a constant when nothing is given', () => {
    expect(validationExportFilename('csv')).toBe('validation_findings_report.csv');
  });

  it('strips unsafe filename characters', () => {
    expect(validationExportFilename('csv', { boqId: 'a/b\\c:d*e' })).toBe(
      'validation_findings_abcde.csv',
    );
  });

  it('does not produce path separators in the name', () => {
    const name = validationExportFilename('xlsx', { boqId: '../../etc/passwd' });
    expect(name).not.toContain('/');
    expect(name).not.toContain('\\');
    expect(name).not.toContain('..');
  });
});

describe('VALIDATION_EXPORT_MEDIA', () => {
  it('maps each format to a mime type', () => {
    expect(VALIDATION_EXPORT_MEDIA.csv).toContain('text/csv');
    expect(VALIDATION_EXPORT_MEDIA.xlsx).toContain('spreadsheetml.sheet');
  });
});
