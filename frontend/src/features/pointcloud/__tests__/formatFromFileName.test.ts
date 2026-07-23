// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';
import { formatFromFileName } from '../api';

describe('formatFromFileName', () => {
  it('detects the conventional COPC double extension as copc', () => {
    expect(formatFromFileName('scan.copc.laz')).toBe('copc');
    expect(formatFromFileName('SCAN.COPC.LAZ')).toBe('copc');
    expect(formatFromFileName('site.copc')).toBe('copc');
  });

  it('detects plain LAS/LAZ without misreading them as copc', () => {
    expect(formatFromFileName('scan.laz')).toBe('laz');
    expect(formatFromFileName('scan.las')).toBe('las');
  });

  it('returns null for unsupported or extensionless names', () => {
    expect(formatFromFileName('notes.txt')).toBeNull();
    expect(formatFromFileName('noextension')).toBeNull();
  });
});
