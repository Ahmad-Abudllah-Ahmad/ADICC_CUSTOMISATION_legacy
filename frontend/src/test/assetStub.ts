// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// Test-only stub for static asset imports (e.g. `import url from '/brand/x.webp'`).
//
// Under Vite, an absolute public-asset import like `/brand/ddc-logo.webp`
// resolves to a string URL. Vitest's Node resolver has no asset transform,
// so it tries to load the path as a real module and throws
// "The argument 'filename' must be a file URL object ...". Aliasing such
// asset imports to this stub gives the default import a deterministic string
// URL, matching the runtime contract the component relies on.
export default '/test-asset-stub.webp';
