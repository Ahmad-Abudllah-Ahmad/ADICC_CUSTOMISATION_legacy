import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  __resetWebGLPrecisionShimForTests,
  installWebGLPrecisionShim,
} from './webglPrecisionShim';

describe('installWebGLPrecisionShim', () => {
  afterEach(() => {
    __resetWebGLPrecisionShimForTests();
    vi.unstubAllGlobals();
  });

  it('replaces a null getShaderPrecisionFormat result with a usable fallback', () => {
    const proto = {
      getShaderPrecisionFormat: vi.fn(() => null),
    };
    vi.stubGlobal('WebGLRenderingContext', { prototype: proto });
    vi.stubGlobal('WebGL2RenderingContext', undefined);

    installWebGLPrecisionShim();
    const result = proto.getShaderPrecisionFormat(0, 0);
    expect(result).toEqual({ rangeMin: 127, rangeMax: 127, precision: 23 });
    // Second install must not wrap again.
    installWebGLPrecisionShim();
    expect(proto.getShaderPrecisionFormat(0, 0).precision).toBe(23);
  });

  it('passes through a valid precision format unchanged', () => {
    const real = { rangeMin: 127, rangeMax: 127, precision: 23 };
    const proto = {
      getShaderPrecisionFormat: vi.fn(() => real),
    };
    vi.stubGlobal('WebGLRenderingContext', { prototype: proto });
    vi.stubGlobal('WebGL2RenderingContext', undefined);

    installWebGLPrecisionShim();
    expect(proto.getShaderPrecisionFormat(1, 2)).toBe(real);
  });
});
