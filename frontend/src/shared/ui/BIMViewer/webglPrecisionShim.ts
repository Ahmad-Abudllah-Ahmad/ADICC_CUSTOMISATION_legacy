// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Patch WebGL ``getShaderPrecisionFormat`` so Three.js never crashes with
 * ``Cannot read properties of null (reading 'precision')``.
 *
 * Some Mac / remote-desktop / driver setups return ``null`` from
 * ``getShaderPrecisionFormat`` for HIGH_FLOAT (and occasionally MEDIUM_FLOAT).
 * Three.js reads ``.precision`` unconditionally while building
 * ``WebGLCapabilities``, which turns a soft GPU limitation into a hard
 * page-level crash of the BIM 3D viewer.
 *
 * The shim is idempotent and safe to call before every ``WebGLRenderer``
 * construction. When the browser returns null we substitute highp-float
 * defaults so the renderer can continue; Three.js still downgrades via its
 * own max-precision path when the GPU truly cannot do highp.
 */

export type ShaderPrecisionFormatLike = {
  rangeMin: number;
  rangeMax: number;
  precision: number;
};

/** Highp float defaults from the WebGL / GLSL ES specs. */
const HIGHP_FLOAT_FALLBACK: ShaderPrecisionFormatLike = {
  rangeMin: 127,
  rangeMax: 127,
  precision: 23,
};

let installed = false;

type PrecisionGetter = (
  shaderType: number,
  precisionType: number,
) => ShaderPrecisionFormatLike | null;

function patchPrototype(proto: { getShaderPrecisionFormat?: PrecisionGetter } | null | undefined) {
  if (!proto || typeof proto.getShaderPrecisionFormat !== 'function') return;
  const original = proto.getShaderPrecisionFormat;
  // Avoid double-wrapping across HMR / StrictMode remounts.
  if ((original as { __oePatched?: boolean }).__oePatched) return;

  function patched(
    this: unknown,
    shaderType: number,
    precisionType: number,
  ): ShaderPrecisionFormatLike {
    const result = original.call(this, shaderType, precisionType);
    if (result && typeof result.precision === 'number') {
      return result;
    }
    return HIGHP_FLOAT_FALLBACK;
  }
  (patched as { __oePatched?: boolean }).__oePatched = true;
  proto.getShaderPrecisionFormat = patched as PrecisionGetter;
}

/**
 * Install the null-safe ``getShaderPrecisionFormat`` shim once per page.
 * No-op outside a browser (SSR / unit tests without WebGL globals).
 */
export function installWebGLPrecisionShim(): void {
  if (installed) return;
  if (typeof window === 'undefined') return;

  patchPrototype(
    typeof WebGLRenderingContext !== 'undefined'
      ? WebGLRenderingContext.prototype
      : null,
  );
  patchPrototype(
    typeof WebGL2RenderingContext !== 'undefined'
      ? WebGL2RenderingContext.prototype
      : null,
  );
  installed = true;
}

/** Test helper — reset the install flag between vitest cases. */
export function __resetWebGLPrecisionShimForTests(): void {
  installed = false;
}
