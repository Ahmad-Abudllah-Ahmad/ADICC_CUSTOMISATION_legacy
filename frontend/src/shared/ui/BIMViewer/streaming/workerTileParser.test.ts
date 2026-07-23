// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { WorkerTileParser, type ParseRequest, type ParseResponse } from './workerTileParser';

/**
 * Covers the worker message protocol and, above all, the robust fallback: the
 * parser must resolve null (never reject) on a worker error, a timeout, or a
 * worker that cannot be constructed, so the streamer can drop to a main-thread
 * parse. The success path must round-trip node NAMES + hierarchy, since that is
 * what the viewer keys mesh -> element off. jsdom has no Worker, so we inject a
 * fake one.
 */

type Responder = (req: ParseRequest) => ParseResponse | null;

/**
 * Minimal stand-in for a dedicated Worker. Replies asynchronously like a real
 * worker via the injected responder; returning null keeps it silent so the
 * timeout path can be exercised.
 */
class FakeWorker {
  onmessage: ((event: MessageEvent<ParseResponse>) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  readonly posted: ParseRequest[] = [];
  terminated = false;

  constructor(private readonly responder: Responder) {}

  postMessage(message: ParseRequest): void {
    this.posted.push(message);
    queueMicrotask(() => {
      const reply = this.responder(message);
      if (reply !== null) {
        this.onmessage?.({ data: reply } as MessageEvent<ParseResponse>);
      }
    });
  }

  terminate(): void {
    this.terminated = true;
  }

  /** Simulate a worker-level crash (bad bundle, OOM). */
  crash(): void {
    this.onerror?.({});
  }
}

function nodeNames(root: THREE.Object3D): string[] {
  const names: string[] = [];
  root.traverse((o) => {
    if (o.name) names.push(o.name);
  });
  return names;
}

function namedTile(): { json: unknown; names: string[] } {
  const root = new THREE.Group();
  root.name = 'tile-root';
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({ color: 0x336699 }),
  );
  mesh.name = '105545'; // mimics an RVT ElementId node name (the match key)
  root.add(mesh);
  return { json: root.toJSON(), names: nodeNames(root) };
}

describe('WorkerTileParser', () => {
  it('parses a tile off-thread and round-trips node names + hierarchy', async () => {
    const { json, names } = namedTile();
    const parser = new WorkerTileParser({
      workerFactory: () =>
        new FakeWorker((req) => ({ id: req.id, ok: true, json, names })) as unknown as Worker,
    });
    const obj = await parser.parse(new ArrayBuffer(16));
    expect(obj).not.toBeNull();
    expect(obj!.name).toBe('tile-root');
    // The name that keys mesh -> element must survive the round-trip.
    const child = obj!.children.find((c) => c.name === '105545');
    expect(child).toBeDefined();
    expect((child as THREE.Mesh).geometry).toBeTruthy();
    parser.dispose();
  });

  it('discards the worker scene when the round-trip drops a node name', async () => {
    // The reconstruction of this json carries names [105545, tile-root]. The
    // worker claims an extra name, standing in for a round-trip that lost a
    // node - the mesh -> element match would degrade, so it must be discarded
    // and resolve null (caller then falls back to the main-thread parse).
    const { json } = namedTile();
    const parser = new WorkerTileParser({
      workerFactory: () =>
        new FakeWorker((req) => ({
          id: req.id,
          ok: true,
          json,
          names: ['105545', 'tile-root', 'LOST-NODE'],
        })) as unknown as Worker,
    });
    expect(await parser.parse(new ArrayBuffer(16))).toBeNull();
    parser.dispose();
  });

  it('resolves null when the worker reports a parse failure', async () => {
    const parser = new WorkerTileParser({
      workerFactory: () =>
        new FakeWorker((req) => ({ id: req.id, ok: false })) as unknown as Worker,
    });
    expect(await parser.parse(new ArrayBuffer(16))).toBeNull();
    parser.dispose();
  });

  it('resolves null when the worker never replies (timeout)', async () => {
    const parser = new WorkerTileParser({
      timeoutMs: 20,
      workerFactory: () => new FakeWorker(() => null) as unknown as Worker,
    });
    const started = Date.now();
    expect(await parser.parse(new ArrayBuffer(16))).toBeNull();
    expect(Date.now() - started).toBeGreaterThanOrEqual(15);
    parser.dispose();
  });

  it('resolves null when the worker cannot be constructed', async () => {
    const parser = new WorkerTileParser({
      workerFactory: () => {
        throw new Error('no worker here');
      },
    });
    expect(await parser.parse(new ArrayBuffer(16))).toBeNull();
    // Stays broken: a second call is also a clean null, no throw.
    expect(await parser.parse(new ArrayBuffer(16))).toBeNull();
    parser.dispose();
  });

  it('resolves null and stops using a worker that crashed', async () => {
    let fake: FakeWorker | null = null;
    const parser = new WorkerTileParser({
      timeoutMs: 1000,
      workerFactory: () => {
        fake = new FakeWorker(() => null); // never replies on its own
        return fake as unknown as Worker;
      },
    });
    const pending = parser.parse(new ArrayBuffer(16));
    // ensureWorker() ran synchronously inside parse(), so the fake exists now.
    expect(fake).not.toBeNull();
    (fake as unknown as FakeWorker).crash();
    expect(await pending).toBeNull();
    parser.dispose();
  });

  it('correlates concurrent parses by id', async () => {
    // Reply an id-specific payload so a mismatch would surface as a wrong name.
    const parser = new WorkerTileParser({
      workerFactory: () =>
        new FakeWorker((req) => {
          const root = new THREE.Group();
          root.name = `tile-${req.id}`;
          return { id: req.id, ok: true, json: root.toJSON(), names: [`tile-${req.id}`] };
        }) as unknown as Worker,
    });
    const [a, b, c] = await Promise.all([
      parser.parse(new ArrayBuffer(16)),
      parser.parse(new ArrayBuffer(16)),
      parser.parse(new ArrayBuffer(16)),
    ]);
    const names = [a?.name, b?.name, c?.name].sort();
    expect(names).toEqual(['tile-1', 'tile-2', 'tile-3']);
    parser.dispose();
  });

  it('reports Worker support as a boolean', () => {
    expect(typeof WorkerTileParser.isSupported()).toBe('boolean');
  });
});
