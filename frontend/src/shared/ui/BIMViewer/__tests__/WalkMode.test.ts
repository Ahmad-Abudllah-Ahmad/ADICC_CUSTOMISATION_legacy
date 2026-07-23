/**
 * WalkMode tests — exercise the keyboard-driven first-person controller
 * without booting WebGL or a real PointerLock.
 *
 * Strategy: mock the entire `PointerLockControls` module. jsdom doesn't
 * implement `Element.requestPointerLock`, so we replace the class with
 * a stub that records `lock()` / `unlock()` calls and exposes
 * `moveForward` / `moveRight` against a passed-in camera.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';

const lockSpy = vi.fn();
const unlockSpy = vi.fn();
const moveForwardSpy = vi.fn();
const moveRightSpy = vi.fn();

vi.mock('three/examples/jsm/controls/PointerLockControls.js', () => {
  class FakePointerLockControls {
    private listeners: Record<string, ((e: unknown) => void)[]> = {};
    constructor(public camera: THREE.Camera, public domElement: HTMLElement) {}
    lock(): void {
      lockSpy();
      this.dispatch('lock');
    }
    unlock(): void {
      unlockSpy();
      this.dispatch('unlock');
    }
    moveForward(d: number): void {
      moveForwardSpy(d);
      // Mirror real PointerLockControls behaviour against the camera so
      // our integration test can assert position delta.
      const dir = new THREE.Vector3();
      this.camera.getWorldDirection(dir);
      dir.y = 0;
      dir.normalize();
      this.camera.position.addScaledVector(dir, d);
    }
    moveRight(d: number): void {
      moveRightSpy(d);
      const dir = new THREE.Vector3();
      this.camera.getWorldDirection(dir);
      const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0));
      right.normalize();
      this.camera.position.addScaledVector(right, d);
    }
    addEventListener(type: string, fn: (e: unknown) => void): void {
      (this.listeners[type] ??= []).push(fn);
    }
    removeEventListener(type: string, fn: (e: unknown) => void): void {
      const list = this.listeners[type];
      if (!list) return;
      const i = list.indexOf(fn);
      if (i >= 0) list.splice(i, 1);
    }
    private dispatch(type: string): void {
      const list = this.listeners[type];
      if (list) for (const fn of list) fn({ type });
    }
    dispose(): void {
      this.listeners = {};
    }
  }
  return { PointerLockControls: FakePointerLockControls };
});

import { WalkMode } from '../WalkMode';

function pressKey(code: string): void {
  window.dispatchEvent(new KeyboardEvent('keydown', { code }));
}
function releaseKey(code: string): void {
  window.dispatchEvent(new KeyboardEvent('keyup', { code }));
}

describe('WalkMode', () => {
  let camera: THREE.PerspectiveCamera;
  let renderer: THREE.WebGLRenderer;
  let dom: HTMLElement;
  let wm: WalkMode;

  beforeEach(() => {
    lockSpy.mockClear();
    unlockSpy.mockClear();
    moveForwardSpy.mockClear();
    moveRightSpy.mockClear();
    camera = new THREE.PerspectiveCamera();
    // Make sure camera looks down -Z so moveForward translates along -Z.
    camera.position.set(0, 0, 5);
    camera.lookAt(0, 0, 0);
    renderer = { domElement: document.createElement('canvas') } as unknown as THREE.WebGLRenderer;
    dom = document.createElement('div');
    // These tests exercise the FPS / pointer-lock path (they mock
    // PointerLockControls and assert lock/unlock/moveForward). The viewer's
    // DEFAULT is now drag-to-look (lockCursor:false, cursor stays visible);
    // opt into pointer-lock here so the FPS-specific assertions stay valid.
    // Drag-to-look has its own dedicated describe block below.
    wm = new WalkMode({ camera, renderer, domElement: dom, lockCursor: true });
  });

  afterEach(() => {
    wm.dispose();
  });

  it('enable() requests pointer lock and reports isEnabled=true', () => {
    wm.enable();
    expect(wm.isEnabled()).toBe(true);
    expect(lockSpy).toHaveBeenCalledTimes(1);
  });

  it('disable() releases pointer lock', () => {
    wm.enable();
    wm.disable();
    expect(wm.isEnabled()).toBe(false);
    expect(unlockSpy).toHaveBeenCalled();
  });

  it('WASD keydown integrates into camera position over time', () => {
    wm.enable();
    const startZ = camera.position.z;
    pressKey('KeyW');
    // 0.5 s at the default 2 m/s should translate ~1 m along -Z.
    wm.tick(0.5);
    expect(moveForwardSpy).toHaveBeenCalledWith(1);
    expect(camera.position.z).toBeLessThan(startZ);
    releaseKey('KeyW');
    // After key-up, further ticks should NOT call moveForward.
    moveForwardSpy.mockClear();
    wm.tick(0.5);
    expect(moveForwardSpy).not.toHaveBeenCalled();
  });

  it('setFlightSpeed scales the per-tick movement', () => {
    wm.enable();
    wm.setFlightSpeed(10); // 10 m/s
    pressKey('KeyD');
    wm.tick(0.5);
    expect(moveRightSpy).toHaveBeenCalledWith(5); // 10 × 0.5
    releaseKey('KeyD');
    expect(wm.getFlightSpeed()).toBe(10);
  });

  it('throws if OrbitControls is still enabled when enable() is called', () => {
    const orbit = { enabled: true };
    const wmGuarded = new WalkMode({ camera, renderer, domElement: dom, orbitControls: orbit });
    expect(() => wmGuarded.enable()).toThrow(/OrbitControls/);
    expect(wmGuarded.isEnabled()).toBe(false);
    wmGuarded.dispose();
  });

  it('does NOT throw if OrbitControls reference is disabled', () => {
    const orbit = { enabled: false };
    const wmGuarded = new WalkMode({ camera, renderer, domElement: dom, orbitControls: orbit });
    expect(() => wmGuarded.enable()).not.toThrow();
    expect(wmGuarded.isEnabled()).toBe(true);
    wmGuarded.dispose();
  });

  it('dispose() removes window keydown/keyup listeners', () => {
    wm.enable();
    wm.dispose();
    // After dispose, pressing keys + ticking does nothing.
    pressKey('KeyW');
    moveForwardSpy.mockClear();
    wm.tick(0.5);
    expect(moveForwardSpy).not.toHaveBeenCalled();
    releaseKey('KeyW');
  });

  it('Space/E/PageUp move the camera up, Q/PageDown/Ctrl move it down', () => {
    wm.enable();
    const startY = camera.position.y;
    pressKey('Space');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY + 1, 6);
    releaseKey('Space');
    pressKey('KeyQ');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY, 6);
    releaseKey('KeyQ');
    // E mirrors Space, PageDown mirrors Q.
    pressKey('KeyE');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY + 1, 6);
    releaseKey('KeyE');
    pressKey('PageDown');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY, 6);
    releaseKey('PageDown');
  });

  it('onExitRequest fires when pointer-lock is lost unexpectedly while still enabled', () => {
    const onExitRequest = vi.fn();
    const wm2 = new WalkMode({ camera, renderer, domElement: dom, onExitRequest, lockCursor: true });
    wm2.enable(); // enable() -> controls.lock() -> 'lock' event => _locked = true
    expect(wm2.isLocked()).toBe(true);
    // Simulate the browser dropping the lock (alt-tab) WITHOUT calling
    // disable(): dispatch the controls' own 'unlock' event.
    const controls = (wm2 as unknown as { controls: { unlock: () => void } })
      .controls;
    controls.unlock();
    expect(onExitRequest).toHaveBeenCalledTimes(1);
    expect(wm2.isLocked()).toBe(false);
    wm2.dispose();
  });

  it('does NOT fire onExitRequest during an intentional disable()', () => {
    const onExitRequest = vi.fn();
    const wm2 = new WalkMode({ camera, renderer, domElement: dom, onExitRequest, lockCursor: true });
    wm2.enable();
    wm2.disable(); // intentional teardown — must not trigger the auto-exit
    expect(onExitRequest).not.toHaveBeenCalled();
    wm2.dispose();
  });

  it('Shift acts as a sprint modifier (3× speed) instead of moving down', () => {
    wm.enable();
    wm.setFlightSpeed(2);
    pressKey('KeyW');
    pressKey('ShiftLeft');
    wm.tick(0.5);
    // 2 m/s * 3 (sprint) * 0.5 s = 3 m
    expect(moveForwardSpy).toHaveBeenLastCalledWith(3);
    releaseKey('ShiftLeft');
    moveForwardSpy.mockClear();
    wm.tick(0.5);
    // Without sprint: 2 * 0.5 = 1 m
    expect(moveForwardSpy).toHaveBeenLastCalledWith(1);
    releaseKey('KeyW');
  });
});

describe('WalkMode - drag-to-look (default)', () => {
  let camera: THREE.PerspectiveCamera;
  let renderer: THREE.WebGLRenderer;
  let dom: HTMLElement;
  let wm: WalkMode;

  beforeEach(() => {
    lockSpy.mockClear();
    unlockSpy.mockClear();
    moveForwardSpy.mockClear();
    moveRightSpy.mockClear();
    camera = new THREE.PerspectiveCamera();
    camera.position.set(0, 0, 5);
    camera.lookAt(0, 0, 0);
    renderer = { domElement: document.createElement('canvas') } as unknown as THREE.WebGLRenderer;
    dom = document.createElement('div');
    // No lockCursor → default drag-to-look.
    wm = new WalkMode({ camera, renderer, domElement: dom });
  });

  afterEach(() => {
    wm.dispose();
  });

  it('default mode never constructs PointerLockControls / requests lock', () => {
    wm.enable();
    expect(wm.isEnabled()).toBe(true);
    expect(wm.isPointerLockMode()).toBe(false);
    // The whole point of the fix: no requestPointerLock, no native banner.
    expect(lockSpy).not.toHaveBeenCalled();
  });

  it('shows a grab cursor on the dom element while enabled', () => {
    wm.enable();
    expect(dom.style.cursor).toBe('grab');
    wm.disable();
    expect(dom.style.cursor).toBe('');
  });

  it('WASD still moves the camera without PointerLockControls', () => {
    wm.enable();
    const startZ = camera.position.z;
    pressKey('KeyW');
    wm.tick(0.5); // 2 m/s * 0.5 s = 1 m forward (camera looks -Z)
    expect(camera.position.z).toBeLessThan(startZ);
    // Movement does NOT go through PointerLockControls in drag mode.
    expect(moveForwardSpy).not.toHaveBeenCalled();
    releaseKey('KeyW');
  });

  it('Space/Q move the camera up/down in drag mode', () => {
    wm.enable();
    const startY = camera.position.y;
    pressKey('Space');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY + 1, 6);
    releaseKey('Space');
    pressKey('KeyQ');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY, 6);
    releaseKey('KeyQ');
  });

  it('dragging the primary button rotates the camera and flips lock state', () => {
    const lockStates: boolean[] = [];
    const unsub = wm.onLockChange((locked) => lockStates.push(locked));
    wm.enable();
    const q0 = camera.quaternion.clone();
    // jsdom does not implement PointerEvent — dispatch a plain Event and
    // stamp the fields the handlers read. The handlers only access
    // button / movementX / movementY / pointerId + preventDefault.
    const fire = (
      type: string,
      props: { button?: number; movementX?: number; movementY?: number },
    ): void => {
      const ev = new Event(type, { bubbles: true, cancelable: true });
      Object.assign(ev, { pointerId: 1, button: 0, movementX: 0, movementY: 0, ...props });
      dom.dispatchEvent(ev);
    };
    fire('pointerdown', { button: 0 });
    fire('pointermove', { movementX: 100, movementY: 0 });
    // Camera orientation changed from the drag.
    expect(camera.quaternion.equals(q0)).toBe(false);
    // Lock mirror toggled true during the drag…
    expect(lockStates).toContain(true);
    fire('pointerup', { button: 0 });
    // …and back to false on release.
    expect(lockStates[lockStates.length - 1]).toBe(false);
    unsub();
  });
});

describe('WalkMode - setLockCursor (runtime FPS toggle)', () => {
  let camera: THREE.PerspectiveCamera;
  let renderer: THREE.WebGLRenderer;
  let dom: HTMLElement;
  let wm: WalkMode;

  beforeEach(() => {
    lockSpy.mockClear();
    unlockSpy.mockClear();
    camera = new THREE.PerspectiveCamera();
    camera.position.set(0, 0, 5);
    camera.lookAt(0, 0, 0);
    renderer = { domElement: document.createElement('canvas') } as unknown as THREE.WebGLRenderer;
    dom = document.createElement('div');
    wm = new WalkMode({ camera, renderer, domElement: dom }); // drag-to-look default
  });

  afterEach(() => {
    wm.dispose();
  });

  it('switches a live drag session into FPS pointer-lock and back', () => {
    wm.enable();
    expect(wm.isPointerLockMode()).toBe(false);
    expect(dom.style.cursor).toBe('grab');

    wm.setLockCursor(true);
    expect(wm.isEnabled()).toBe(true);
    expect(wm.isPointerLockMode()).toBe(true);
    expect(lockSpy).toHaveBeenCalledTimes(1);

    wm.setLockCursor(false);
    expect(wm.isPointerLockMode()).toBe(false);
    expect(dom.style.cursor).toBe('grab');
  });

  it('is a no-op when the requested mode already matches', () => {
    wm.enable();
    wm.setLockCursor(false);
    expect(lockSpy).not.toHaveBeenCalled();
    expect(wm.isEnabled()).toBe(true);
  });

  it('only sets the mode (no re-arm) when called before enable()', () => {
    wm.setLockCursor(true);
    expect(wm.isEnabled()).toBe(false);
    expect(lockSpy).not.toHaveBeenCalled();
    wm.enable();
    expect(wm.isPointerLockMode()).toBe(true);
    expect(lockSpy).toHaveBeenCalledTimes(1);
  });
});

describe('WalkMode - placeAtEyeLevel', () => {
  let camera: THREE.PerspectiveCamera;
  let renderer: THREE.WebGLRenderer;
  let dom: HTMLElement;
  let wm: WalkMode;

  beforeEach(() => {
    camera = new THREE.PerspectiveCamera();
    renderer = { domElement: document.createElement('canvas') } as unknown as THREE.WebGLRenderer;
    dom = document.createElement('div');
    wm = new WalkMode({ camera, renderer, domElement: dom });
  });

  afterEach(() => {
    wm.dispose();
  });

  it('stands the camera at the model centre, above the floor', () => {
    const bbox = new THREE.Box3(
      new THREE.Vector3(-10, 0, -4),
      new THREE.Vector3(10, 30, 4),
    );
    wm.placeAtEyeLevel(bbox);
    expect(camera.position.x).toBeCloseTo(0, 6);
    expect(camera.position.z).toBeCloseTo(0, 6);
    // 10% of the 30-unit height above the floor.
    expect(camera.position.y).toBeCloseTo(3, 6);
  });

  it('ignores an empty bounding box', () => {
    camera.position.set(1, 2, 3);
    wm.placeAtEyeLevel(new THREE.Box3());
    expect(camera.position.x).toBe(1);
    expect(camera.position.y).toBe(2);
    expect(camera.position.z).toBe(3);
  });
});

describe('WalkMode - analog joystick axis (touch site mode)', () => {
  let camera: THREE.PerspectiveCamera;
  let renderer: THREE.WebGLRenderer;
  let dom: HTMLElement;
  let wm: WalkMode;

  beforeEach(() => {
    camera = new THREE.PerspectiveCamera();
    camera.position.set(0, 0, 5);
    camera.lookAt(0, 0, 0);
    renderer = { domElement: document.createElement('canvas') } as unknown as THREE.WebGLRenderer;
    dom = document.createElement('div');
    wm = new WalkMode({ camera, renderer, domElement: dom }); // drag-to-look default
    wm.enable();
  });

  afterEach(() => {
    wm.dispose();
  });

  it('drives forward movement with no keys pressed', () => {
    wm.setMoveAxis(0, 1); // full forward
    wm.tick(0.5); // 2 m/s * 0.5 s = 1 m along -Z
    expect(camera.position.z).toBeCloseTo(4, 5);
  });

  it('drives strafe movement to the right', () => {
    wm.setMoveAxis(1, 0);
    wm.tick(0.5);
    expect(camera.position.x).toBeCloseTo(1, 5);
  });

  it('stops when the axis is released to zero', () => {
    wm.setMoveAxis(0, 1);
    wm.tick(0.5);
    const z1 = camera.position.z;
    wm.setMoveAxis(0, 0);
    wm.tick(0.5);
    expect(camera.position.z).toBeCloseTo(z1, 5);
  });

  it('clamps key + stick so combined input never exceeds full speed', () => {
    pressKey('KeyW'); // key forward = 1
    wm.setMoveAxis(0, 1); // stick forward = 1; sum clamps to 1, not 2
    wm.tick(0.5);
    // Full speed only: 1 m, so z = 4 (not 3).
    expect(camera.position.z).toBeCloseTo(4, 5);
    releaseKey('KeyW');
  });

  it('resets the axis on disable so a deflected stick does not persist', () => {
    wm.setMoveAxis(0, 1);
    wm.disable();
    wm.enable();
    const z0 = camera.position.z;
    wm.tick(0.5);
    expect(camera.position.z).toBeCloseTo(z0, 5);
  });
});
