// @ts-nocheck
/**
 * FederatedViewer tests — BIM Federations Slice 3.
 *
 * Counter-intuitive design notes
 * ------------------------------
 * 1) We mock the hook ``useFederatedGeometryLoader`` instead of mocking
 *    fetch/MSW so we control the exact set of LoadedMember payloads
 *    that flow into ``scene.addMember``. The hook itself has its own
 *    integration test (useFederatedGeometryLoader.test.tsx).
 * 2) We swap the scene constructor via the public test seam
 *    ``__setFederatedSceneFactoryForTests`` — the seam exists precisely
 *    to keep these tests JSDOM-safe (no WebGL context required).
 * 3) ``forwardRef`` + ``useImperativeHandle`` is ALREADY present on the
 *    production component; we exercise the handle through a child ref
 *    rather than re-introducing one.
 */
import {
  describe,
  expect,
  it,
  vi,
  beforeEach,
  afterEach,
} from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import { createRef } from 'react';

import {
  FederatedViewer,
  __setFederatedSceneFactoryForTests,
  type FederatedViewerHandle,
} from '../FederatedViewer';
import { usePreferencesStore } from '@/stores/usePreferencesStore';

/* ── Fake scene implementation ──────────────────────────────────────── */

interface FakeScene {
  addMember: ReturnType<typeof vi.fn>;
  removeMember: ReturnType<typeof vi.fn>;
  frameAll: ReturnType<typeof vi.fn>;
  resetView: ReturnType<typeof vi.fn>;
  isolateClass: ReturnType<typeof vi.fn>;
  setDisciplineColoringEnabled: ReturnType<typeof vi.fn>;
  setMemberVisible: ReturnType<typeof vi.fn>;
  setDarkMode: ReturnType<typeof vi.fn>;
  setOnPick: ReturnType<typeof vi.fn>;
  setOnMeasure: ReturnType<typeof vi.fn>;
  setMeasureMode: ReturnType<typeof vi.fn>;
  clearSelection: ReturnType<typeof vi.fn>;
  clearMeasurements: ReturnType<typeof vi.fn>;
  dispose: ReturnType<typeof vi.fn>;
}

let lastFakeScene: FakeScene | null = null;
// Captured B1 callbacks so tests can drive pick / measure events that would
// normally originate from a real raycast.
let lastOnPick: ((r: unknown) => void) | null = null;
let lastOnMeasure: ((m: unknown) => void) | null = null;
function makeFakeScene(): FakeScene {
  const f: FakeScene = {
    addMember: vi.fn().mockResolvedValue(undefined),
    removeMember: vi.fn(),
    frameAll: vi.fn(),
    resetView: vi.fn(),
    isolateClass: vi.fn(),
    setDisciplineColoringEnabled: vi.fn(),
    setMemberVisible: vi.fn(),
    setDarkMode: vi.fn(),
    setOnPick: vi.fn((cb) => {
      lastOnPick = cb;
    }),
    setOnMeasure: vi.fn((cb) => {
      lastOnMeasure = cb;
    }),
    setMeasureMode: vi.fn(),
    clearSelection: vi.fn(),
    clearMeasurements: vi.fn(),
    dispose: vi.fn(),
  };
  lastFakeScene = f;
  return f;
}

/* ── Hook mock ──────────────────────────────────────────────────────── */

let hookValue: any;
vi.mock('../useFederatedGeometryLoader', () => ({
  useFederatedGeometryLoader: () => hookValue,
}));

/* ── Helpers ────────────────────────────────────────────────────────── */

function loadedMember(modelId: string, discipline = 'arch') {
  return {
    modelId,
    discipline,
    buffer: new ArrayBuffer(8),
    originOffset: { x: 0, y: 0, z: 0 },
    modelName: modelId.slice(0, 8),
  };
}

function detailWith(memberIds: string[]) {
  return {
    id: 'fed-1',
    project_id: 'proj-1',
    name: 'Fed 1',
    description: null,
    origin_offset: { x: 0, y: 0, z: 0 },
    shared_units: 'm',
    member_count: memberIds.length,
    members: memberIds.map((id, i) => ({
      id: `mem-${i}`,
      federation_id: 'fed-1',
      bim_model_id: id,
      discipline: 'arch',
      visible: true,
      z_order: i,
      color_hint: null,
    })),
  };
}

beforeEach(() => {
  hookValue = {
    detail: undefined,
    members: [],
    errors: [],
    isLoading: true,
    isDetailLoading: true,
    detailError: null,
  };
  __setFederatedSceneFactoryForTests(() => makeFakeScene() as unknown as never);
});

afterEach(() => {
  __setFederatedSceneFactoryForTests(null);
  lastFakeScene = null;
  lastOnPick = null;
  lastOnMeasure = null;
  // Reset measurement-system preference so an imperial test never leaks into
  // the metric-default expectations of the others.
  usePreferencesStore.getState().resetPreferences();
  cleanup();
});

/* ── Tests ──────────────────────────────────────────────────────────── */

describe('FederatedViewer', () => {
  it('renders the loading overlay while geometry is loading', () => {
    hookValue = {
      detail: undefined,
      members: [],
      errors: [],
      isLoading: true,
      isDetailLoading: true,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    expect(
      screen.getByTestId('federated-viewer-loading'),
    ).toBeInTheDocument();
  });

  it('renders the detail error overlay on federation fetch failure', () => {
    hookValue = {
      detail: undefined,
      members: [],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: new Error('Federation not found'),
    };
    render(<FederatedViewer federationId="fed-1" />);
    const err = screen.getByTestId('federated-viewer-detail-error');
    expect(err).toBeInTheDocument();
    expect(err).toHaveTextContent('Federation not found');
  });

  it('renders per-member error toast when geometry fetch fails for a member', () => {
    hookValue = {
      detail: detailWith(['ok-id']),
      members: [loadedMember('ok-id')],
      errors: [{ modelId: 'bad-id', error: new Error('404') }],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    expect(
      screen.getByTestId('federated-viewer-member-errors'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('federated-viewer-member-error-bad-id'),
    ).toHaveTextContent('404');
  });

  it('calls scene.addMember once per loaded member', async () => {
    hookValue = {
      detail: detailWith(['m1', 'm2', 'm3']),
      members: [loadedMember('m1'), loadedMember('m2'), loadedMember('m3')],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    await waitFor(() => {
      expect(lastFakeScene).not.toBeNull();
      expect(lastFakeScene!.addMember).toHaveBeenCalledTimes(3);
    });
    const calledIds = lastFakeScene!.addMember.mock.calls.map(
      (c) => (c[0] as { modelId: string }).modelId,
    );
    expect(new Set(calledIds)).toEqual(new Set(['m1', 'm2', 'm3']));
  });

  it('clicking "Frame all" invokes scene.frameAll()', async () => {
    hookValue = {
      detail: detailWith(['m1']),
      members: [loadedMember('m1')],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    await waitFor(() => expect(lastFakeScene).not.toBeNull());
    // Reset the auto-frame-all call from the load-effect so we count only
    // the user-driven click.
    lastFakeScene!.frameAll.mockClear();
    fireEvent.click(screen.getByTestId('federated-viewer-frame-all'));
    expect(lastFakeScene!.frameAll).toHaveBeenCalledTimes(1);
  });

  it('toggling "Discipline color" calls setDisciplineColoringEnabled(true)', async () => {
    hookValue = {
      detail: detailWith(['m1']),
      members: [loadedMember('m1')],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    await waitFor(() => expect(lastFakeScene).not.toBeNull());
    fireEvent.click(screen.getByTestId('federated-viewer-color-toggle'));
    expect(lastFakeScene!.setDisciplineColoringEnabled).toHaveBeenCalledWith(
      true,
    );
    // Toggling again flips back.
    fireEvent.click(screen.getByTestId('federated-viewer-color-toggle'));
    expect(lastFakeScene!.setDisciplineColoringEnabled).toHaveBeenLastCalledWith(
      false,
    );
  });

  it('imperative ref forwards isolateClass + frameAll + resetView to scene', async () => {
    hookValue = {
      detail: detailWith(['m1']),
      members: [loadedMember('m1')],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    const ref = createRef<FederatedViewerHandle>();
    render(<FederatedViewer ref={ref} federationId="fed-1" />);
    await waitFor(() => expect(lastFakeScene).not.toBeNull());
    expect(ref.current).not.toBeNull();
    ref.current!.isolateClass('IfcWall');
    expect(lastFakeScene!.isolateClass).toHaveBeenCalledWith('IfcWall');
    ref.current!.isolateClass(null);
    expect(lastFakeScene!.isolateClass).toHaveBeenLastCalledWith(null);
    ref.current!.frameAll();
    expect(lastFakeScene!.frameAll).toHaveBeenCalled();
    ref.current!.resetView();
    expect(lastFakeScene!.resetView).toHaveBeenCalled();
  });

  /* ── B1 - full interactive viewer ─────────────────────────────── */

  it('toggling "Measure" drives scene.setMeasureMode on and off', async () => {
    hookValue = {
      detail: detailWith(['m1']),
      members: [loadedMember('m1')],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    await waitFor(() => expect(lastFakeScene).not.toBeNull());
    fireEvent.click(screen.getByTestId('federated-viewer-measure-toggle'));
    expect(lastFakeScene!.setMeasureMode).toHaveBeenCalledWith(true);
    expect(
      screen.getByTestId('federated-viewer-measure-readout'),
    ).toHaveTextContent(/measure/i);
    fireEvent.click(screen.getByTestId('federated-viewer-measure-toggle'));
    expect(lastFakeScene!.setMeasureMode).toHaveBeenLastCalledWith(false);
  });

  it('a pick event renders the selected-element info overlay', async () => {
    hookValue = {
      detail: detailWith(['m1']),
      members: [loadedMember('m1')],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    await waitFor(() => expect(lastOnPick).not.toBeNull());
    act(() => {
      lastOnPick!({
        modelId: 'm1',
        discipline: 'arch',
        ifcClass: 'IfcWall',
        objectName: 'IfcWall_abc',
        point: { x: 1, y: 2, z: 3 },
      });
    });
    const info = screen.getByTestId('federated-viewer-pick-info');
    expect(info).toHaveTextContent('IfcWall');
    expect(info).toHaveTextContent('arch');
    expect(info).toHaveTextContent('IfcWall_abc');
    fireEvent.click(screen.getByTestId('federated-viewer-pick-clear'));
    expect(lastFakeScene!.clearSelection).toHaveBeenCalled();
    expect(screen.queryByTestId('federated-viewer-pick-info')).toBeNull();
  });

  it('a completed measurement renders the distance readout', async () => {
    hookValue = {
      detail: detailWith(['m1']),
      members: [loadedMember('m1')],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    await waitFor(() => expect(lastOnMeasure).not.toBeNull());
    fireEvent.click(screen.getByTestId('federated-viewer-measure-toggle'));
    act(() => {
      lastOnMeasure!({ distance: 12.345, pointCount: 2 });
    });
    expect(
      screen.getByTestId('federated-viewer-measure-readout'),
    ).toHaveTextContent('12.345');
  });

  it('converts the measured distance to feet for an imperial user (#270)', async () => {
    // shared_units is metric ("m" via detailWith); an imperial preference must
    // scale the readout to feet rather than printing raw metres.
    usePreferencesStore.getState().setPreference('measurementSystem', 'imperial');
    hookValue = {
      detail: detailWith(['m1']),
      members: [loadedMember('m1')],
      errors: [],
      isLoading: false,
      isDetailLoading: false,
      detailError: null,
    };
    render(<FederatedViewer federationId="fed-1" />);
    await waitFor(() => expect(lastOnMeasure).not.toBeNull());
    fireEvent.click(screen.getByTestId('federated-viewer-measure-toggle'));
    act(() => {
      // 10 m -> 32.808 ft (factor 3.2808399).
      lastOnMeasure!({ distance: 10, pointCount: 2 });
    });
    const readout = screen.getByTestId('federated-viewer-measure-readout');
    expect(readout).toHaveTextContent('32.808');
    expect(readout).toHaveTextContent('ft');
    // The raw metric value must NOT be shown.
    expect(readout).not.toHaveTextContent('10 m');
  });

  it('the full-screen button requests fullscreen on the container', async () => {
    const reqSpy = vi.fn();
    const origReq = Element.prototype.requestFullscreen;
    Element.prototype.requestFullscreen = reqSpy;
    try {
      hookValue = {
        detail: detailWith(['m1']),
        members: [loadedMember('m1')],
        errors: [],
        isLoading: false,
        isDetailLoading: false,
        detailError: null,
      };
      render(<FederatedViewer federationId="fed-1" />);
      await waitFor(() => expect(lastFakeScene).not.toBeNull());
      fireEvent.click(screen.getByTestId('federated-viewer-fullscreen'));
      expect(reqSpy).toHaveBeenCalledTimes(1);
    } finally {
      Element.prototype.requestFullscreen = origReq;
    }
  });
});
