// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Canvas2D rendering functions for DXF/DWG entities.
 *
 * Each entity type is rendered via a dedicated function that receives the
 * 2D context, the entity data, and the current viewport state.
 */

import type { DxfEntity } from '../api';
import type { ViewportState } from './viewport';
import { worldToScreen } from './viewport';

/* ── CAD Color Index → CSS hex ─────────────────────────────────────── */

const ACI_TABLE: Record<number, string> = {
  0: '#000000', // ByBlock
  1: '#FF0000', // Red
  2: '#FFFF00', // Yellow
  3: '#00FF00', // Green
  4: '#00FFFF', // Cyan
  5: '#0000FF', // Blue
  6: '#FF00FF', // Magenta
  7: '#FFFFFF', // White / Black (display-dependent)
  8: '#808080', // Dark grey
  9: '#C0C0C0', // Light grey
};

/** Convert an entity color (ACI number or hex string) to a CSS hex color. */
export function resolveColor(color: string | number): string {
  if (typeof color === 'string') {
    // Already a hex color string
    if (color.startsWith('#')) return color;
    return '#CCCCCC';
  }
  return ACI_TABLE[color] ?? '#CCCCCC';
}

/** @deprecated Use resolveColor instead */
export function aciToHex(colorIndex: number | string): string {
  return resolveColor(colorIndex);
}

/* ── Viewport culling ─────────────────────────────────────────────────── */

/** Quick check whether an entity is likely within the visible canvas area. */
function isInViewport(
  entity: DxfEntity,
  vp: ViewportState,
  canvasW: number,
  canvasH: number,
): boolean {
  // Get a representative point for the entity
  let cx = 0;
  let cy = 0;
  let radius = 0;

  if (entity.start) {
    cx = entity.start.x;
    cy = entity.start.y;
    radius = entity.radius ?? 0;
  } else if (entity.vertices?.length) {
    cx = entity.vertices[0]!.x;
    cy = entity.vertices[0]!.y;
  } else if ((entity as any).points?.length) {
    cx = (entity as any).points[0]!.x;
    cy = (entity as any).points[0]!.y;
  } else {
    // Can't determine position — render to be safe
    return true;
  }

  const screen = worldToScreen(cx, cy, vp);
  const radiusPx = radius * vp.scale;
  const margin = 200 + radiusPx; // pixels margin

  // For polylines/hatches with many vertices, also check if any vertex is visible
  if (
    screen.x < -margin ||
    screen.x > canvasW + margin ||
    screen.y < -margin ||
    screen.y > canvasH + margin
  ) {
    // First vertex is off-screen; for multi-vertex entities check a few more
    if (entity.vertices && entity.vertices.length > 1) {
      // Check last vertex and a midpoint vertex for large polylines
      const checkIndices = [
        entity.vertices.length - 1,
        Math.floor(entity.vertices.length / 2),
      ];
      for (const idx of checkIndices) {
        const v = entity.vertices[idx]!;
        const s = worldToScreen(v.x, v.y, vp);
        if (s.x > -margin && s.x < canvasW + margin && s.y > -margin && s.y < canvasH + margin) {
          return true;
        }
      }
      // For LINE entities, also check end point
    } else if (entity.end) {
      const s = worldToScreen(entity.end.x, entity.end.y, vp);
      if (s.x > -margin && s.x < canvasW + margin && s.y > -margin && s.y < canvasH + margin) {
        return true;
      }
    }
    return false;
  }

  return true;
}

/* ── Entity rendering ──────────────────────────────────────────────────── */

export function renderEntities(
  ctx: CanvasRenderingContext2D,
  entities: DxfEntity[],
  vp: ViewportState,
  visibleLayers: Set<string>,
  selectedId?: string | null,
  canvasWidth?: number,
  canvasHeight?: number,
): void {
  const cw = canvasWidth ?? ctx.canvas.width / (window.devicePixelRatio || 1);
  const ch = canvasHeight ?? ctx.canvas.height / (window.devicePixelRatio || 1);

  // Render hatches first (background fill)
  for (const entity of entities) {
    if (entity.type === 'HATCH' && visibleLayers.has(entity.layer)) {
      if (!isInViewport(entity, vp, cw, ch)) continue;
      applyStyle(ctx, entity, selectedId);
      renderHatch(ctx, entity, vp);
    }
  }

  // Render geometry entities
  for (const entity of entities) {
    if (!visibleLayers.has(entity.layer)) continue;
    if (entity.type === 'HATCH') continue; // already rendered
    if (!isInViewport(entity, vp, cw, ch)) continue;

    applyStyle(ctx, entity, selectedId);

    switch (entity.type) {
      case 'SOLID':
      case 'TRACE':
      case '3DFACE':
        renderSolid(ctx, entity, vp);
        break;
      case 'LINE':
        renderLine(ctx, entity, vp);
        break;
      case 'LWPOLYLINE':
        renderPolyline(ctx, entity, vp);
        break;
      case 'ARC':
        renderArc(ctx, entity, vp);
        break;
      case 'CIRCLE':
        renderCircle(ctx, entity, vp);
        break;
      case 'ELLIPSE':
        renderEllipse(ctx, entity, vp);
        break;
      case 'TEXT':
        renderText(ctx, entity, vp);
        break;
      case 'POINT':
        renderPoint(ctx, entity, vp);
        break;
      case 'INSERT':
        renderInsert(ctx, entity, vp);
        break;
    }
  }
}

function applyStyle(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  selectedId?: string | null,
): void {
  const isSelected = entity.id === selectedId;
  if (isSelected) {
    ctx.strokeStyle = '#60a5fa';
    ctx.fillStyle = '#60a5fa';
    ctx.lineWidth = 2.5;
    // Glow effect via shadow
    ctx.shadowColor = 'rgba(96, 165, 250, 0.5)';
    ctx.shadowBlur = 8;
  } else {
    const color = resolveColor(entity.color);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1;
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
  }
}

export function renderLine(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  if (!entity.start || !entity.end) return;
  const s = worldToScreen(entity.start.x, entity.start.y, vp);
  const e = worldToScreen(entity.end.x, entity.end.y, vp);
  ctx.beginPath();
  ctx.moveTo(s.x, s.y);
  ctx.lineTo(e.x, e.y);
  ctx.stroke();
}

export function renderPolyline(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  if (!entity.vertices || entity.vertices.length < 2) return;
  ctx.beginPath();
  const v0 = entity.vertices[0]!;
  const first = worldToScreen(v0.x, v0.y, vp);
  ctx.moveTo(first.x, first.y);
  for (let i = 1; i < entity.vertices.length; i++) {
    const v = entity.vertices[i]!;
    const p = worldToScreen(v.x, v.y, vp);
    ctx.lineTo(p.x, p.y);
  }
  if (entity.closed) {
    ctx.closePath();
    if (entity.is_solid || (entity.pattern_name && entity.pattern_name.toUpperCase() === 'SOLID')) {
      ctx.save();
      ctx.globalAlpha = 0.75;
      ctx.fill();
      ctx.restore();
    }
  }
  ctx.stroke();
}

export function renderArc(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  if (!entity.start || entity.radius == null) return;
  const center = worldToScreen(entity.start.x, entity.start.y, vp);
  const r = entity.radius * vp.scale;
  const startAngle = entity.start_angle ?? 0;
  const endAngle = entity.end_angle ?? Math.PI * 2;
  ctx.beginPath();
  // DXF arcs are CCW in Cartesian space; with Y-axis flipped in worldToScreen,
  // negate angles and sweep counter-clockwise in Canvas screen space (anticlockwise = true)
  ctx.arc(center.x, center.y, r, -startAngle, -endAngle, true);
  ctx.stroke();
}

export function renderCircle(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  if (!entity.start || entity.radius == null) return;
  const center = worldToScreen(entity.start.x, entity.start.y, vp);
  const r = entity.radius * vp.scale;
  ctx.beginPath();
  ctx.arc(center.x, center.y, r, 0, Math.PI * 2);
  ctx.stroke();
}

export function renderEllipse(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  if (!entity.start) return;
  const center = worldToScreen(entity.start.x, entity.start.y, vp);

  let majorR: number;
  let minorR: number;
  let rotation: number;

  if (entity.major_radius != null && entity.minor_radius != null) {
    // DDC format: explicit radii
    majorR = entity.major_radius * vp.scale;
    minorR = entity.minor_radius * vp.scale;
    rotation = -(entity.rotation ?? 0); // negate for screen Y-flip
  } else if (entity.major_axis && entity.ratio != null) {
    // ezdxf format: major_axis vector + ratio
    const ax = entity.major_axis;
    majorR = Math.sqrt(ax.x * ax.x + ax.y * ax.y) * vp.scale;
    minorR = majorR * entity.ratio;
    rotation = -Math.atan2(ax.y, ax.x); // negate for screen Y-flip
  } else {
    return;
  }

  if (majorR < 0.5 || minorR < 0.5) return; // too small to draw

  ctx.beginPath();
  ctx.ellipse(center.x, center.y, majorR, minorR, rotation, 0, Math.PI * 2);
  ctx.stroke();
}

/** Cache for hatch line patterns to avoid recreating each frame. */
const hatchPatternCache = new Map<string, CanvasPattern | null>();

/** Create a diagonal line pattern (ANSI31-style, 45-degree lines). */
function createDiagonalPattern(
  ctx: CanvasRenderingContext2D,
  color: string,
  spacing = 8,
): CanvasPattern | null {
  const cacheKey = `diagonal_${color}_${spacing}`;
  if (hatchPatternCache.has(cacheKey)) return hatchPatternCache.get(cacheKey)!;

  const size = spacing;
  const offscreen = document.createElement('canvas');
  offscreen.width = size;
  offscreen.height = size;
  const pctx = offscreen.getContext('2d');
  if (!pctx) return null;

  pctx.strokeStyle = color;
  pctx.lineWidth = 1;
  pctx.beginPath();
  // Draw diagonal line from bottom-left to top-right
  pctx.moveTo(0, size);
  pctx.lineTo(size, 0);
  // Extend for seamless tiling
  pctx.moveTo(-size, size);
  pctx.lineTo(size, -size);
  pctx.moveTo(0, size * 2);
  pctx.lineTo(size * 2, 0);
  pctx.stroke();

  const pattern = ctx.createPattern(offscreen, 'repeat');
  hatchPatternCache.set(cacheKey, pattern);
  return pattern;
}

export function renderHatch(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  const pts = entity.vertices ?? (entity as any).points;
  if (!pts || pts.length < 3) return;

  ctx.beginPath();
  const first = worldToScreen(pts[0]!.x, pts[0]!.y, vp);
  ctx.moveTo(first.x, first.y);
  for (let i = 1; i < pts.length; i++) {
    const v = pts[i]!;
    const p = worldToScreen(v.x, v.y, vp);
    ctx.lineTo(p.x, p.y);
  }
  ctx.closePath();

  ctx.save();

  const patternName = (entity.pattern_name ?? '').toUpperCase();

  if (entity.is_solid || patternName === 'SOLID' || patternName === '') {
    // Solid fill (columns, wall core fills, filled blocks)
    ctx.globalAlpha = 0.75;
    ctx.fill();
  } else if (patternName === 'ANSI31' || patternName === 'ANSI32' || patternName === 'ANSI37') {
    // Diagonal line patterns
    const color = ctx.fillStyle as string;
    const pattern = createDiagonalPattern(ctx, color, 8);
    if (pattern) {
      ctx.globalAlpha = 0.6;
      ctx.fillStyle = pattern;
      ctx.fill();
    } else {
      ctx.globalAlpha = 0.35;
      ctx.fill();
    }
  } else {
    // Other named patterns
    ctx.globalAlpha = 0.5;
    ctx.fill();
  }

  // Always stroke the boundary
  ctx.globalAlpha = 0.9;
  ctx.stroke();
  ctx.restore();
}

export function renderSolid(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  const pts = entity.vertices ?? (entity as any).points;
  if (!pts || pts.length < 3) return;

  ctx.beginPath();
  const first = worldToScreen(pts[0]!.x, pts[0]!.y, vp);
  ctx.moveTo(first.x, first.y);
  for (let i = 1; i < pts.length; i++) {
    const p = worldToScreen(pts[i]!.x, pts[i]!.y, vp);
    ctx.lineTo(p.x, p.y);
  }
  ctx.closePath();

  ctx.save();
  ctx.globalAlpha = 0.85;
  ctx.fill();
  ctx.globalAlpha = 1.0;
  ctx.stroke();
  ctx.restore();
}

const SANS_STACK = 'Arial, Helvetica, sans-serif';

/**
 * Map a DXF text entity's SHX font / style name to a CSS font family.
 *
 * CAD annotation text is authored in single-stroke SHX fonts (romans, simplex,
 * isocp, txt, …) that have no direct web equivalent. The renderer used to draw
 * every string in `monospace`, which makes annotations look nothing like the
 * source sheet - the vast majority of CAD text is a proportional SANS face.
 * So we map the common technical fonts to a sans stack, keep a monospace
 * fallback only for the genuinely fixed-width / GD&T / symbol fonts, and treat
 * the script families as cursive. Anything empty or unrecognised falls back to
 * SANS on purpose: defaulting to sans (not monospace) is what fixes the common
 * "wrong font" complaint on its own.
 *
 * The name is lower-cased and any trailing `.shx` is stripped before matching,
 * and `entity.font` (the resolved file) is preferred over `entity.style` (the
 * style-table name). Fully defensive: `undefined` -> sans.
 */
export function resolveFontFamily(entity: DxfEntity): string {
  const raw = (entity.font || entity.style || '')
    .toLowerCase()
    .replace(/\.shx$/, '')
    .trim();
  if (!raw) return SANS_STACK;
  // Symbol / GD&T fonts: no sane proportional fallback, keep monospace so the
  // glyph cells stay aligned.
  if (raw.includes('gdt') || raw.includes('symap') || raw.includes('symbol')) {
    return 'monospace';
  }
  // Script / handwriting / slanted styles.
  if (raw.includes('script') || raw.includes('italic')) return 'cursive';
  // Fixed-width CAD faces (monotxt and any explicitly "mono" family). Checked
  // before the sans default so "monotxt" is not mistaken for the "txt" sans.
  if (raw.includes('mono')) return 'monospace';
  // Everything else - romans, simplex, romant, romand, isocp, iso, txt, … -
  // is a proportional sans face.
  return SANS_STACK;
}

export function renderText(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  if (!entity.start || !entity.text) return;
  // Use true world height × scale. Do NOT clamp up to 8px — that turns
  // thousands of sheet labels into an unreadable smudge at Fit/overview zoom.
  // Keep the cull low enough that room names (height ≈ 5) and door/window
  // tags (height ≈ 8–12) still appear when a single floor sheet is fitted.
  const fontSize = (entity.height ?? 2.5) * vp.scale;
  if (fontSize < 1.0) return;
  const pos = worldToScreen(entity.start.x, entity.start.y, vp);
  const drawSize = Math.min(64, fontSize);
  // MTEXT keeps its newlines (the backend maps MTEXT -> TEXT but preserves the
  // string), and canvas fillText ignores "\n", so render each line stacked.
  const lines = entity.text.split('\n');
  const lineH = drawSize * 1.25;
  // AutoCAD MTEXT attachment 1–3 = top, 4–6 = middle, 7–9 = bottom.
  // Using 'bottom' for top-left inserts stacks schedule rows into each other.
  const ap = entity.attachment_point;
  const baseline: CanvasTextBaseline =
    ap == null ? 'alphabetic' : ap <= 3 ? 'top' : ap <= 6 ? 'middle' : 'bottom';
  const align: CanvasTextAlign =
    ap == null ? 'left' : ap % 3 === 2 ? 'center' : ap % 3 === 0 ? 'right' : 'left';

  ctx.save();
  ctx.font = `${drawSize}px ${resolveFontFamily(entity)}`;
  ctx.textBaseline = baseline;
  ctx.textAlign = align;
  if (entity.rotation) {
    ctx.translate(pos.x, pos.y);
    ctx.rotate(-entity.rotation); // negate for screen Y-flip
    lines.forEach((ln, i) => ctx.fillText(ln, 0, i * lineH));
  } else {
    lines.forEach((ln, i) => ctx.fillText(ln, pos.x, pos.y + i * lineH));
  }
  ctx.restore();
}

function renderPoint(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  if (!entity.start) return;
  const pos = worldToScreen(entity.start.x, entity.start.y, vp);
  ctx.beginPath();
  ctx.arc(pos.x, pos.y, 2, 0, Math.PI * 2);
  ctx.fill();
}

function renderInsert(
  ctx: CanvasRenderingContext2D,
  entity: DxfEntity,
  vp: ViewportState,
): void {
  if (!entity.start) return;
  const pos = worldToScreen(entity.start.x, entity.start.y, vp);
  // Render block insert as a small diamond marker
  const s = 5;
  ctx.beginPath();
  ctx.moveTo(pos.x, pos.y - s);
  ctx.lineTo(pos.x + s, pos.y);
  ctx.lineTo(pos.x, pos.y + s);
  ctx.lineTo(pos.x - s, pos.y);
  ctx.closePath();
  ctx.stroke();
  if (entity.block_name) {
    ctx.font = '9px monospace';
    ctx.textBaseline = 'top';
    ctx.fillText(entity.block_name, pos.x + s + 2, pos.y - s);
  }
}
