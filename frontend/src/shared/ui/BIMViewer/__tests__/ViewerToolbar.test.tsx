/**
 * ViewerToolbar tests — exercise the UI surface without booting WebGL
 * or any of the three helper classes' real behaviour. We pass stub
 * helpers that expose just the methods the toolbar invokes, so we can
 * spy on the wiring (mutex, speed slider, clear button, position class,
 * a11y) deterministically.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

import { ViewerToolbar } from '../ViewerToolbar';
import type { SectionBox } from '../SectionBox';
import type { WalkMode } from '../WalkMode';
import type { MeasureTool, Measurement } from '../MeasureTool';

function makeStubs(): {
  sectionBox: SectionBox;
  walkMode: WalkMode;
  measureTool: MeasureTool;
  emitMeasurement: (m: Measurement) => void;
  spies: {
    sectionEnable: ReturnType<typeof vi.fn>;
    sectionDisable: ReturnType<typeof vi.fn>;
    walkEnable: ReturnType<typeof vi.fn>;
    walkDisable: ReturnType<typeof vi.fn>;
    measureEnable: ReturnType<typeof vi.fn>;
    measureDisable: ReturnType<typeof vi.fn>;
    setFlightSpeed: ReturnType<typeof vi.fn>;
    clearAll: ReturnType<typeof vi.fn>;
  };
} {
  let sectionEnabled = false;
  let walkEnabled = false;
  let measureEnabled = false;
  let count = 0;
  let measurementHandler: ((m: Measurement) => void) | null = null;

  const spies = {
    sectionEnable: vi.fn(() => {
      sectionEnabled = true;
    }),
    sectionDisable: vi.fn(() => {
      sectionEnabled = false;
    }),
    walkEnable: vi.fn(() => {
      walkEnabled = true;
    }),
    walkDisable: vi.fn(() => {
      walkEnabled = false;
    }),
    measureEnable: vi.fn(() => {
      measureEnabled = true;
    }),
    measureDisable: vi.fn(() => {
      measureEnabled = false;
    }),
    setFlightSpeed: vi.fn(),
    clearAll: vi.fn(() => {
      count = 0;
    }),
  };

  const bounds = {
    min: { x: 0, y: 0, z: 0 },
    max: { x: 1, y: 1, z: 1 },
  };

  const sectionBox = {
    enable: spies.sectionEnable,
    disable: spies.sectionDisable,
    isEnabled: () => sectionEnabled,
    getBounds: () => bounds,
  } as unknown as SectionBox;

  const walkMode = {
    enable: spies.walkEnable,
    disable: spies.walkDisable,
    isEnabled: () => walkEnabled,
    setFlightSpeed: spies.setFlightSpeed,
    getFlightSpeed: () => 2,
  } as unknown as WalkMode;

  const measureTool = {
    enable: spies.measureEnable,
    disable: spies.measureDisable,
    isEnabled: () => measureEnabled,
    clearAll: spies.clearAll,
    count: () => count,
    onMeasurement: (handler: (m: Measurement) => void) => {
      measurementHandler = handler;
      return () => {
        measurementHandler = null;
      };
    },
  } as unknown as MeasureTool;

  return {
    sectionBox,
    walkMode,
    measureTool,
    emitMeasurement: (m) => {
      count += 1;
      measurementHandler?.(m);
    },
    spies,
  };
}

describe('ViewerToolbar', () => {
  let stubs: ReturnType<typeof makeStubs>;

  beforeEach(() => {
    stubs = makeStubs();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the three tool buttons with their default labels', () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    expect(screen.getByTestId('viewer-tool-section')).toBeInTheDocument();
    expect(screen.getByTestId('viewer-tool-walk')).toBeInTheDocument();
    expect(screen.getByTestId('viewer-tool-measure')).toBeInTheDocument();
    expect(screen.getByLabelText('Section box')).toBeInTheDocument();
    expect(screen.getByLabelText('Walk')).toBeInTheDocument();
    expect(screen.getByLabelText('Measure')).toBeInTheDocument();
  });

  it('mutual exclusion: enabling section turns off walk if walk was active', () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    fireEvent.click(screen.getByTestId('viewer-tool-walk'));
    expect(stubs.spies.walkEnable).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('viewer-tool-section'));
    expect(stubs.spies.walkDisable).toHaveBeenCalledTimes(1);
    expect(stubs.spies.sectionEnable).toHaveBeenCalledTimes(1);
  });

  it('clicking the active tool disables it (no tool is active)', () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    fireEvent.click(screen.getByTestId('viewer-tool-measure'));
    fireEvent.click(screen.getByTestId('viewer-tool-measure'));
    expect(stubs.spies.measureEnable).toHaveBeenCalledTimes(1);
    expect(stubs.spies.measureDisable).toHaveBeenCalledTimes(1);
  });

  it('speed slider drives walkMode.setFlightSpeed', () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    fireEvent.click(screen.getByTestId('viewer-tool-walk'));
    const slider = screen.getByTestId('viewer-walk-speed') as HTMLInputElement;
    fireEvent.change(slider, { target: { value: '7.5' } });
    expect(stubs.spies.setFlightSpeed).toHaveBeenCalledWith(7.5);
  });

  it('"Clear all measurements" calls measureTool.clearAll()', () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    fireEvent.click(screen.getByTestId('viewer-tool-measure'));
    fireEvent.click(screen.getByTestId('viewer-measure-clear'));
    expect(stubs.spies.clearAll).toHaveBeenCalledTimes(1);
  });

  it('i18n: labels render in EN (and via the mocked t() use the same defaultValue across locales)', () => {
    // The test setup mocks react-i18next to return defaultValue regardless
    // of the active language, so we exercise EN here. The keys themselves
    // (`viewerTools.section_box` etc) are added to en/de/ru locale files
    // for production rendering — verified by the import in BIMViewer.tsx.
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    expect(screen.getByLabelText('Section box')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('viewer-tool-section'));
    expect(screen.getByText('Fit to selection')).toBeInTheDocument();
    expect(screen.getByText('Fit to all')).toBeInTheDocument();
    expect(screen.getByText('Reset')).toBeInTheDocument();
  });

  it('shows "No geometry to clip" hint when a fit action reports no usable bounds', () => {
    const onSectionAction = vi.fn(() => false); // host: nothing to clip
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
        onSectionAction={onSectionAction}
      />,
    );
    fireEvent.click(screen.getByTestId('viewer-tool-section'));
    expect(screen.queryByTestId('viewer-section-no-geometry')).toBeNull();
    fireEvent.click(screen.getByTestId('viewer-section-fit-selection'));
    expect(onSectionAction).toHaveBeenCalledWith('fit_selection');
    expect(screen.getByTestId('viewer-section-no-geometry')).toBeInTheDocument();
  });

  it('hides the hint again once a fit action succeeds', () => {
    let usable = false;
    const onSectionAction = vi.fn(() => usable);
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
        onSectionAction={onSectionAction}
      />,
    );
    fireEvent.click(screen.getByTestId('viewer-tool-section'));
    fireEvent.click(screen.getByTestId('viewer-section-fit-all'));
    expect(screen.getByTestId('viewer-section-no-geometry')).toBeInTheDocument();
    usable = true;
    fireEvent.click(screen.getByTestId('viewer-section-fit-all'));
    expect(screen.queryByTestId('viewer-section-no-geometry')).toBeNull();
  });

  it('Reset always disables the section box even without a host handler', () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    // Activate section (enable() flips the stub's isEnabled() to true).
    fireEvent.click(screen.getByTestId('viewer-tool-section'));
    expect(stubs.spies.sectionEnable).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('viewer-section-reset'));
    expect(stubs.spies.sectionDisable).toHaveBeenCalled();
  });

  it('a11y: each tool button exposes aria-pressed reflecting its active state', () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    const sectionBtn = screen.getByTestId('viewer-tool-section');
    expect(sectionBtn).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(sectionBtn);
    expect(sectionBtn).toHaveAttribute('aria-pressed', 'true');
    const walkBtn = screen.getByTestId('viewer-tool-walk');
    expect(walkBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('sub-panel only renders when its tool is active', () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    // Nothing active → no sub-panels.
    expect(screen.queryByTestId('viewer-tool-section-panel')).toBeNull();
    expect(screen.queryByTestId('viewer-tool-walk-panel')).toBeNull();
    expect(screen.queryByTestId('viewer-tool-measure-panel')).toBeNull();
    // Activate section → only its panel renders.
    fireEvent.click(screen.getByTestId('viewer-tool-section'));
    expect(screen.getByTestId('viewer-tool-section-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('viewer-tool-walk-panel')).toBeNull();
  });

  it('position prop toggles the tailwind anchor class', () => {
    const { unmount } = render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
        position="top-right"
      />,
    );
    expect(screen.getByTestId('viewer-toolbar')).toHaveAttribute(
      'data-position',
      'top-right',
    );
    unmount();
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
        position="bottom-center"
      />,
    );
    expect(screen.getByTestId('viewer-toolbar')).toHaveAttribute(
      'data-position',
      'bottom-center',
    );
  });

  it('onToolChange fires whenever the active tool changes', () => {
    const onToolChange = vi.fn();
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
        onToolChange={onToolChange}
      />,
    );
    fireEvent.click(screen.getByTestId('viewer-tool-measure'));
    expect(onToolChange).toHaveBeenCalledWith('measure');
    fireEvent.click(screen.getByTestId('viewer-tool-section'));
    expect(onToolChange).toHaveBeenCalledWith('section');
    fireEvent.click(screen.getByTestId('viewer-tool-section'));
    expect(onToolChange).toHaveBeenCalledWith(null);
  });

  it('measurement count updates when MeasureTool emits a completion', async () => {
    render(
      <ViewerToolbar
        sectionBox={stubs.sectionBox}
        walkMode={stubs.walkMode}
        measureTool={stubs.measureTool}
      />,
    );
    fireEvent.click(screen.getByTestId('viewer-tool-measure'));
    expect(screen.getByTestId('viewer-measure-count').textContent).toContain('0');
    act(() => {
      stubs.emitMeasurement({
        id: 'm1',
        pointA: { x: 0, y: 0, z: 0 },
        pointB: { x: 1, y: 0, z: 0 },
        distance: 1,
        axisProjections: { dx: 1, dy: 0, dz: 0 },
      });
    });
    expect(await screen.findByText('1')).toBeInTheDocument();
  });
});
