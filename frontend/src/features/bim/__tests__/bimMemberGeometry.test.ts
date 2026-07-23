// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the federated member geometry format detector. The detector is
 * the gate that decides which loader runs first, so it has to agree with the
 * single-model viewer on what a blob is - GLB vs DAE/COLLADA vs neither.
 */
import { describe, it, expect } from 'vitest';

import { detectGeometryKind } from '../bimMemberGeometry';

/** A buffer whose first four bytes are the GLB magic ``glTF`` plus padding so
 *  it clears the 12-byte minimum. */
function glbBuffer(): ArrayBuffer {
  const b = new Uint8Array(16);
  b[0] = 0x67; // g
  b[1] = 0x6c; // l
  b[2] = 0x54; // T
  b[3] = 0x46; // F
  return b.buffer;
}

function encode(text: string, withBom = false): ArrayBuffer {
  const body = new TextEncoder().encode(text);
  if (!withBom) return body.buffer;
  const out = new Uint8Array(body.byteLength + 3);
  out[0] = 0xef;
  out[1] = 0xbb;
  out[2] = 0xbf; // UTF-8 BOM
  out.set(body, 3);
  return out.buffer;
}

const PLAIN_DAE =
  '<?xml version="1.0" encoding="utf-8"?>\n<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">\n</COLLADA>';
const PREFIXED_DAE =
  '<?xml version="1.0"?>\n<ns0:COLLADA xmlns:ns0="http://www.collada.org/2005/11/COLLADASchema">\n</ns0:COLLADA>';

describe('detectGeometryKind', () => {
  it('detects a GLB by its glTF magic', () => {
    expect(detectGeometryKind(glbBuffer())).toBe('glb');
  });

  it('detects a plain COLLADA document', () => {
    expect(detectGeometryKind(encode(PLAIN_DAE))).toBe('dae');
  });

  it('detects a namespace-prefixed COLLADA document', () => {
    expect(detectGeometryKind(encode(PREFIXED_DAE))).toBe('dae');
  });

  it('detects COLLADA even with a leading UTF-8 BOM', () => {
    expect(detectGeometryKind(encode(PLAIN_DAE, true))).toBe('dae');
  });

  it('returns null for a buffer shorter than 12 bytes', () => {
    expect(detectGeometryKind(new ArrayBuffer(4))).toBeNull();
  });

  it('returns null for bytes that are neither GLB nor COLLADA', () => {
    // Generic XML that is not COLLADA (e.g. an ifcXML wrapper) must not be
    // mistaken for geometry the GLTF/Collada loaders can read.
    expect(detectGeometryKind(encode('<?xml version="1.0"?><ifcXML></ifcXML>'))).toBeNull();
    expect(detectGeometryKind(encode('just some plain text padding bytes'))).toBeNull();
  });
});
