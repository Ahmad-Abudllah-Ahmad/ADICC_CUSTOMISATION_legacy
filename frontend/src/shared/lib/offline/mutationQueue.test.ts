import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  MutationQueue,
  createMemoryQueueStorage,
  newClientOpId,
  sortByFifo,
  type OpSender,
  type QueuedOp,
  type ReplayOutcome,
} from './mutationQueue';

/** A controllable sender: maps clientOpId -> outcome, records call order. */
function recordingSender(
  outcomes: Record<string, ReplayOutcome> = {},
  fallback: ReplayOutcome = { kind: 'applied', httpStatus: 200 },
): { sender: OpSender; calls: string[] } {
  const calls: string[] = [];
  const sender: OpSender = (op: QueuedOp) => {
    calls.push(op.clientOpId);
    return Promise.resolve(outcomes[op.clientOpId] ?? fallback);
  };
  return { sender, calls };
}

describe('MutationQueue - enqueue', () => {
  let storage = createMemoryQueueStorage();

  beforeEach(() => {
    storage = createMemoryQueueStorage();
  });

  it('enqueues a mutation and reports the pending count', async () => {
    const { sender } = recordingSender();
    const q = new MutationQueue(storage, sender);

    await q.enqueue({ method: 'POST', path: '/v1/field/report/', body: { x: 1 }, kind: 'field_report' });

    expect(await q.pendingCount()).toBe(1);
    const pending = await q.pending();
    expect(pending[0]?.path).toBe('/v1/field/report/');
    expect(pending[0]?.kind).toBe('field_report');
    expect(pending[0]?.retries).toBe(0);
  });

  it('assigns a clientOpId when one is not supplied', async () => {
    const { sender } = recordingSender();
    const q = new MutationQueue(storage, sender);
    const op = await q.enqueue({ method: 'POST', path: '/v1/a/', kind: 'diary' });
    expect(op.clientOpId).toBeTruthy();
    expect(typeof op.clientOpId).toBe('string');
  });

  it('preserves a caller-supplied clientOpId', async () => {
    const { sender } = recordingSender();
    const q = new MutationQueue(storage, sender);
    const op = await q.enqueue({
      clientOpId: 'fixed-id-123',
      method: 'POST',
      path: '/v1/a/',
      kind: 'diary',
    });
    expect(op.clientOpId).toBe('fixed-id-123');
  });

  it('notifies onChange subscribers when enqueuing', async () => {
    const { sender } = recordingSender();
    const q = new MutationQueue(storage, sender);
    const onChange = vi.fn();
    q.onChange(onChange);
    await q.enqueue({ method: 'POST', path: '/v1/a/', kind: 'diary' });
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe('MutationQueue - dedupe', () => {
  it('collapses a duplicate clientOpId into one entry', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender();
    const q = new MutationQueue(storage, sender);

    const first = await q.enqueue({
      clientOpId: 'dupe-1',
      method: 'POST',
      path: '/v1/a/',
      body: { v: 1 },
      kind: 'diary',
    });
    const second = await q.enqueue({
      clientOpId: 'dupe-1',
      method: 'POST',
      path: '/v1/a/',
      body: { v: 2 },
      kind: 'diary',
    });

    expect(await q.pendingCount()).toBe(1);
    // The second enqueue returns the original op unchanged (first write wins).
    expect(second.seq).toBe(first.seq);
    const pending = await q.pending();
    expect((pending[0]?.body as { v: number }).v).toBe(1);
  });

  it('does not re-notify on a duplicate enqueue beyond the first write', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender();
    const q = new MutationQueue(storage, sender);
    const onChange = vi.fn();
    q.onChange(onChange);
    await q.enqueue({ clientOpId: 'd', method: 'POST', path: '/v1/a/', kind: 'k' });
    await q.enqueue({ clientOpId: 'd', method: 'POST', path: '/v1/a/', kind: 'k' });
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe('MutationQueue - ordered replay', () => {
  it('drains ops strictly in FIFO enqueue order', async () => {
    const storage = createMemoryQueueStorage();
    const { sender, calls } = recordingSender();
    const q = new MutationQueue(storage, sender);

    await q.enqueue({ clientOpId: 'a', method: 'POST', path: '/v1/1/', kind: 'k' });
    await q.enqueue({ clientOpId: 'b', method: 'POST', path: '/v1/2/', kind: 'k' });
    await q.enqueue({ clientOpId: 'c', method: 'POST', path: '/v1/3/', kind: 'k' });

    const summary = await q.drain();

    expect(calls).toEqual(['a', 'b', 'c']);
    expect(summary.applied).toBe(3);
    expect(await q.pendingCount()).toBe(0);
  });

  it('reports per-item success and removes applied ops', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender(
      {
        ok: { kind: 'applied', httpStatus: 201, resultId: 'row-9' },
      },
      { kind: 'applied', httpStatus: 200 },
    );
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'ok', method: 'POST', path: '/v1/1/', kind: 'field_report' });

    const summary = await q.drain();

    expect(summary.results).toHaveLength(1);
    expect(summary.results[0]).toMatchObject({
      clientOpId: 'ok',
      status: 'applied',
      httpStatus: 201,
      resultId: 'row-9',
    });
    expect(await q.pendingCount()).toBe(0);
  });

  it('treats a 409 conflict as resolved and drops it from the queue', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender({
      conf: { kind: 'conflict', httpStatus: 409, detail: 'already exists' },
    });
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'conf', method: 'POST', path: '/v1/1/', kind: 'k' });

    const summary = await q.drain();

    expect(summary.conflict).toBe(1);
    expect(summary.results[0]?.detail).toBe('already exists');
    expect(await q.pendingCount()).toBe(0);
  });

  it('does not double-apply across two drains (idempotent replay)', async () => {
    const storage = createMemoryQueueStorage();
    const { sender, calls } = recordingSender();
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'x', method: 'POST', path: '/v1/1/', kind: 'k' });

    await q.drain();
    await q.drain(); // queue is empty now; second drain is a no-op

    expect(calls).toEqual(['x']); // sent exactly once
    expect(await q.pendingCount()).toBe(0);
  });

  it('a concurrent drain short-circuits (no interleave)', async () => {
    const storage = createMemoryQueueStorage();
    // Held in an object so control-flow analysis does not narrow the deferred
    // resolver to `never` at the use site (it is assigned inside a callback).
    const gate: { resolve?: () => void } = {};
    const calls: string[] = [];
    const sender: OpSender = (op) =>
      new Promise<ReplayOutcome>((resolve) => {
        calls.push(op.clientOpId);
        if (op.clientOpId === 'slow') {
          gate.resolve = () => resolve({ kind: 'applied', httpStatus: 200 });
        } else {
          resolve({ kind: 'applied', httpStatus: 200 });
        }
      });
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'slow', method: 'POST', path: '/v1/1/', kind: 'k' });

    const firstDrain = q.drain();
    const secondDrain = await q.drain(); // runs while first is mid-flight

    // The second drain finds a drain in progress and returns an empty summary.
    expect(secondDrain.results).toHaveLength(0);

    gate.resolve?.();
    const firstSummary = await firstDrain;
    expect(firstSummary.applied).toBe(1);
    expect(calls).toEqual(['slow']); // sent once, not twice
  });
});

describe('MutationQueue - retry on failure', () => {
  it('keeps an op and increments retries on a transient (5xx) outcome', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender({
      flaky: { kind: 'retry', httpStatus: 503 },
    });
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'flaky', method: 'POST', path: '/v1/1/', kind: 'k' });

    const summary = await q.drain();

    expect(summary.retry).toBe(1);
    expect(await q.pendingCount()).toBe(1);
    const pending = await q.pending();
    expect(pending[0]?.retries).toBe(1);
  });

  it('keeps an op when the sender throws (true network failure)', async () => {
    const storage = createMemoryQueueStorage();
    const sender: OpSender = () => Promise.reject(new Error('network down'));
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'net', method: 'POST', path: '/v1/1/', kind: 'k' });

    const summary = await q.drain();

    expect(summary.retry).toBe(1);
    expect(await q.pendingCount()).toBe(1);
  });

  it('eventually succeeds: a flaky op retries then applies on a later drain', async () => {
    const storage = createMemoryQueueStorage();
    let attempt = 0;
    const sender: OpSender = () => {
      attempt += 1;
      return Promise.resolve(
        attempt < 3
          ? { kind: 'retry', httpStatus: 503 }
          : { kind: 'applied', httpStatus: 200 },
      );
    };
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'eventual', method: 'POST', path: '/v1/1/', kind: 'k' });

    await q.drain(); // retry (1)
    await q.drain(); // retry (2)
    const third = await q.drain(); // applied

    expect(third.applied).toBe(1);
    expect(await q.pendingCount()).toBe(0);
    expect(attempt).toBe(3);
  });

  it('drops a permanently-rejected (non-409 4xx) op so it stops retrying', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender({
      bad: { kind: 'rejected', httpStatus: 422, detail: 'validation failed' },
    });
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'bad', method: 'POST', path: '/v1/1/', kind: 'k' });

    const summary = await q.drain();

    expect(summary.rejected).toBe(1);
    expect(summary.results[0]?.detail).toBe('validation failed');
    expect(await q.pendingCount()).toBe(0);
  });

  it('gives up after maxRetries and marks the op rejected', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender({
      stuck: { kind: 'retry', httpStatus: 500 },
    });
    const q = new MutationQueue(storage, sender, { maxRetries: 3 });
    await q.enqueue({ clientOpId: 'stuck', method: 'POST', path: '/v1/1/', kind: 'k' });

    await q.drain(); // retries -> 1
    await q.drain(); // retries -> 2
    const third = await q.drain(); // retries -> 3 == max -> rejected, removed

    expect(third.rejected).toBe(1);
    expect(third.results[0]?.detail).toContain('max retries');
    expect(await q.pendingCount()).toBe(0);
  });

  it('does not exceed maxPerDrain in one pass', async () => {
    const storage = createMemoryQueueStorage();
    const { sender, calls } = recordingSender();
    const q = new MutationQueue(storage, sender, { maxPerDrain: 2 });
    await q.enqueue({ clientOpId: 'a', method: 'POST', path: '/v1/1/', kind: 'k' });
    await q.enqueue({ clientOpId: 'b', method: 'POST', path: '/v1/2/', kind: 'k' });
    await q.enqueue({ clientOpId: 'c', method: 'POST', path: '/v1/3/', kind: 'k' });

    await q.drain();

    expect(calls).toEqual(['a', 'b']);
    expect(await q.pendingCount()).toBe(1); // 'c' left for the next pass
  });
});

describe('MutationQueue - discard / clear', () => {
  it('discards a single op', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender();
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'a', method: 'POST', path: '/v1/1/', kind: 'k' });
    await q.enqueue({ clientOpId: 'b', method: 'POST', path: '/v1/2/', kind: 'k' });

    await q.discard('a');

    const pending = await q.pending();
    expect(pending).toHaveLength(1);
    expect(pending[0]?.clientOpId).toBe('b');
  });

  it('clears the whole queue', async () => {
    const storage = createMemoryQueueStorage();
    const { sender } = recordingSender();
    const q = new MutationQueue(storage, sender);
    await q.enqueue({ clientOpId: 'a', method: 'POST', path: '/v1/1/', kind: 'k' });
    await q.clear();
    expect(await q.pendingCount()).toBe(0);
  });
});

describe('helpers', () => {
  it('sortByFifo orders by seq without mutating the input', () => {
    const ops: QueuedOp[] = [
      { seq: 30, clientOpId: 'c', method: 'POST', path: '/c', kind: 'k', queuedAt: 0, retries: 0 },
      { seq: 10, clientOpId: 'a', method: 'POST', path: '/a', kind: 'k', queuedAt: 0, retries: 0 },
      { seq: 20, clientOpId: 'b', method: 'POST', path: '/b', kind: 'k', queuedAt: 0, retries: 0 },
    ];
    const sorted = sortByFifo(ops);
    expect(sorted.map((o) => o.clientOpId)).toEqual(['a', 'b', 'c']);
    // input untouched
    expect(ops.map((o) => o.clientOpId)).toEqual(['c', 'a', 'b']);
  });

  it('newClientOpId returns unique non-empty strings', () => {
    const a = newClientOpId();
    const b = newClientOpId();
    expect(a).toBeTruthy();
    expect(b).toBeTruthy();
    expect(a).not.toBe(b);
  });
});
