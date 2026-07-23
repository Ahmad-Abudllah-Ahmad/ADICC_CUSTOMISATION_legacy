// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * useBIMViewerStore — per-viewer UI state that needs to survive re-renders.
 *
 * Currently tracks per-category opacity (RFC 19 §4.2) and whether the Tools
 * tab is active on the right panel. The store is intentionally tiny; model
 * data itself lives in React Query + ElementManager.
 */
import { create } from 'zustand';

export type BIMRightPanelTab =
  | 'properties'
  | 'structure'
  | 'layers'
  | 'tools'
  | 'trait-lens'
  | 'bundles'
  | 'groups'
  | 'match';

/** Which quantity the measure tool captures on the next clicks. */
export type BIMMeasureKind = 'distance' | 'area' | 'angle';

/** Active section/clip mode. `none` = no cut applied. */
export type BIMClipMode = 'none' | 'box' | 'plane';

/**
 * Render-quality preset. Controls renderer pixel ratio, lighting, tone-mapping
 * and per-material transparency. Persisted to localStorage so the choice
 * survives reloads.
 *
 *  fast    — opaque non-glass + dim ambient + 0.75 pixelRatio. Best fps on
 *            large federations or weak laptops.
 *  default — current behaviour (translucent everything, full 4-light setup).
 *            Migration-safe default.
 *  visual  — opaque non-glass, glass stays transparent, boosted exposure +
 *            up to 1.5× pixelRatio. Cleaner picture *and* fewer alpha-sort
 *            draws than `default`.
 *  walk    — most aggressive cut (pixelRatio 0.5, two lights at zero) for
 *            smooth first-person walk-mode navigation on phones / low-spec
 *            machines.
 */
export type BIMQualityMode = 'fast' | 'default' | 'visual' | 'walk';

const ASSET_CARD_KEY = 'oe_bim_asset_card_enabled';
const QUALITY_MODE_KEY = 'oe_bim_quality_mode';

function readAssetCardEnabled(): boolean {
  try {
    const raw = localStorage.getItem(ASSET_CARD_KEY);
    if (raw === null) return true;
    return raw === '1';
  } catch {
    return true;
  }
}

function writeAssetCardEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(ASSET_CARD_KEY, enabled ? '1' : '0');
  } catch {
    /* ignore quota errors */
  }
}

function readQualityMode(): BIMQualityMode {
  try {
    const raw = localStorage.getItem(QUALITY_MODE_KEY);
    if (raw === 'fast' || raw === 'default' || raw === 'visual' || raw === 'walk') {
      return raw;
    }
  } catch {
    /* fall through to default */
  }
  return 'default';
}

function writeQualityMode(mode: BIMQualityMode): void {
  try {
    localStorage.setItem(QUALITY_MODE_KEY, mode);
  } catch {
    /* ignore quota errors */
  }
}

interface BIMViewerState {
  /** Per-category opacity (0..1). 1 means fully opaque (default). */
  categoryOpacity: Record<string, number>;
  /** Categories the user explicitly hid from the Layers tab. */
  hiddenCategories: Record<string, boolean>;
  /** Active right-panel tab. */
  rightPanelTab: BIMRightPanelTab;
  /** Whether the right-panel (with the 4 tabs) is currently open. */
  rightPanelOpen: boolean;
  /** Whether the measure tool is enabled. */
  measureActive: boolean;
  /** Which quantity the measure tool captures (distance / area / angle). */
  measureKind: BIMMeasureKind;
  /** Whether the measure tool snaps clicks to the nearest geometry vertex. */
  measureSnap: boolean;
  /** Active section / clipping mode. */
  clipMode: BIMClipMode;
  /** Whether the clip-controls popover is open. */
  clipPanelOpen: boolean;
  /** Whether selection-driven ghost mode is on (non-selected = translucent). */
  ghostActive: boolean;
  /** Whether the floating "Model / Filtered / Selection summary" panel
   *  is visible. Toggled from the top toolbar or the panel's own X. */
  summaryPanelOpen: boolean;
  /** Whether the bounding-box dimension card is shown when an element
   *  is selected. Toggled from the top toolbar. */
  dimensionsVisible: boolean;
  /** Whether the floating Asset-info card is shown when an element is
   *  selected. Persisted to localStorage so the preference survives
   *  page reloads. */
  assetCardEnabled: boolean;
  /** Active render-quality preset. Persisted to localStorage. */
  qualityMode: BIMQualityMode;

  setCategoryOpacity: (category: string, opacity: number) => void;
  setCategoryHidden: (category: string, hidden: boolean) => void;
  resetCategoryOverrides: () => void;
  /** Clear only the per-category visibility hides, leaving opacity
   *  overrides intact. Called by the viewer's "Show all" affordance so
   *  un-hiding everything doesn't also reset transparency tuning. */
  resetHiddenCategories: () => void;
  setRightPanelTab: (tab: BIMRightPanelTab) => void;
  setRightPanelOpen: (open: boolean) => void;
  setMeasureActive: (active: boolean) => void;
  setMeasureKind: (kind: BIMMeasureKind) => void;
  setMeasureSnap: (snap: boolean) => void;
  setClipMode: (mode: BIMClipMode) => void;
  setClipPanelOpen: (open: boolean) => void;
  setGhostActive: (active: boolean) => void;
  setSummaryPanelOpen: (open: boolean) => void;
  setDimensionsVisible: (visible: boolean) => void;
  setAssetCardEnabled: (enabled: boolean) => void;
  setQualityMode: (mode: BIMQualityMode) => void;
}

export const useBIMViewerStore = create<BIMViewerState>((set) => ({
  categoryOpacity: {},
  hiddenCategories: {},
  rightPanelTab: 'properties',
  rightPanelOpen: false,
  measureActive: false,
  measureKind: 'distance',
  measureSnap: true,
  clipMode: 'none',
  clipPanelOpen: false,
  ghostActive: false,
  summaryPanelOpen: true,
  dimensionsVisible: true,
  assetCardEnabled: readAssetCardEnabled(),
  qualityMode: readQualityMode(),

  setCategoryOpacity: (category, opacity) =>
    set((state) => ({
      categoryOpacity: {
        ...state.categoryOpacity,
        [category]: Math.max(0, Math.min(1, opacity)),
      },
    })),

  setCategoryHidden: (category, hidden) =>
    set((state) => ({
      hiddenCategories: { ...state.hiddenCategories, [category]: hidden },
    })),

  resetCategoryOverrides: () => set({ categoryOpacity: {}, hiddenCategories: {} }),

  resetHiddenCategories: () => set({ hiddenCategories: {} }),

  setRightPanelTab: (tab) => set({ rightPanelTab: tab, rightPanelOpen: true }),
  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
  setMeasureActive: (active) => set({ measureActive: active }),
  setMeasureKind: (kind) => set({ measureKind: kind }),
  setMeasureSnap: (snap) => set({ measureSnap: snap }),
  setClipMode: (mode) => set({ clipMode: mode }),
  setClipPanelOpen: (open) => set({ clipPanelOpen: open }),
  setGhostActive: (active) => set({ ghostActive: active }),
  setSummaryPanelOpen: (open) => set({ summaryPanelOpen: open }),
  setDimensionsVisible: (visible) => set({ dimensionsVisible: visible }),
  setAssetCardEnabled: (enabled) => {
    writeAssetCardEnabled(enabled);
    set({ assetCardEnabled: enabled });
  },
  setQualityMode: (mode) => {
    writeQualityMode(mode);
    set({ qualityMode: mode });
  },
}));
