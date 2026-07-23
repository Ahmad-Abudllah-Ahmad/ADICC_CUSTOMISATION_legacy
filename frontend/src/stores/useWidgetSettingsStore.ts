// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * useWidgetSettingsStore — client-side feature toggles for UI widgets.
 *
 * Separate from `useModulesStore` (which tracks backend module install
 * state) because these flags are purely about presentation — whether the
 * project cards embed a map thumbnail, whether the detail page shows a
 * weather forecast, etc.  No server round-trip; persisted to localStorage
 * so the user's choice sticks across reloads.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface WidgetSettingsState {
  /**
   * Show a map on project cards + the detail page.
   *
   * Cards always render a lightweight STATIC raster thumbnail (one cached
   * <img>, no MapLibre / WebGL / live tile streaming) — the interactive
   * MapLibre map is reserved for the project detail page. This flag only
   * toggles whether that card thumbnail is shown at all; it never opts a
   * card into the heavy live-map path. Defaults on.
   */
  projectMapEnabled: boolean;
  /** Show an 18-day weather forecast on the project detail page. */
  projectWeatherEnabled: boolean;

  toggleProjectMap: () => void;
  toggleProjectWeather: () => void;
  setProjectMap: (v: boolean) => void;
  setProjectWeather: (v: boolean) => void;
}

export const useWidgetSettingsStore = create<WidgetSettingsState>()(
  persist(
    (set) => ({
      projectMapEnabled: true,
      // Weather is an opt-in widget chosen via dashboard Customize, not a
      // default — off until the user explicitly enables it.
      projectWeatherEnabled: false,

      toggleProjectMap: () =>
        set((s) => ({ projectMapEnabled: !s.projectMapEnabled })),
      toggleProjectWeather: () =>
        set((s) => ({ projectWeatherEnabled: !s.projectWeatherEnabled })),
      setProjectMap: (v) => set({ projectMapEnabled: v }),
      setProjectWeather: (v) => set({ projectWeatherEnabled: v }),
    }),
    { name: 'oe.widget-settings' },
  ),
);
