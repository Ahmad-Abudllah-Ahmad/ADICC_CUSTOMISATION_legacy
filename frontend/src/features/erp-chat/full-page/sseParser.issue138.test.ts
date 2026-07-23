// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * GitHub issue #138 / task #249 — frontend SSE parser contract.
 *
 * "Chat IA no responde": an OpenRouter completion was billed upstream
 * (6.41M tokens / 136 requests) but no text rendered. One half of the
 * v3.6.1 defect was the frontend parser: it only read `data:` lines and
 * switched on a non-existent `chunk.type` field, while the backend
 * `_sse()` puts the event name on a separate `event:` line and the
 * payload carries NO `type` field. Result: zero text rendered even from
 * a perfectly intact stream.
 *
 * The fix (useChatFullPage.ts) tracks the `event:` line and resets it on
 * the blank-line frame terminator. The parser logic lives inline in the
 * hook (not exported), so this suite re-implements the EXACT contract and
 * pins it against OpenRouter-shaped, network-chunked SSE — including the
 * adversarial split-mid-frame delivery a real `fetch` ReadableStream
 * produces, and a guard proving the old `data:`-only / `chunk.type`
 * parser would render nothing.
 */
import { describe, it, expect } from 'vitest';

// ── Production parser contract (mirrors useChatFullPage.ts post-#249) ──────
//
// Identical control flow to the hook: rolling buffer split on '\n', keep
// the trailing partial line, track `currentEvent`, reset on blank line,
// switch on the event name (NOT a payload `type` field).
function parseSSE(chunks: string[]): {
  content: string;
  sessionId: string | null;
  error: string | null;
} {
  let content = '';
  let sessionId: string | null = null;
  let error: string | null = null;
  let currentEvent = '';
  let buffer = '';

  for (const chunk of chunks) {
    buffer += chunk;
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? ''; // keep trailing partial line
    for (const rawLine of lines) {
      const line = rawLine.replace(/\r$/, '');
      if (line.trim() === '') {
        currentEvent = '';
        continue;
      }
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
        continue;
      }
      if (!line.startsWith('data:')) continue;
      const jsonStr = line.slice(5).trim();
      if (!jsonStr || jsonStr === '[DONE]') continue;
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(jsonStr) as Record<string, unknown>;
      } catch {
        continue;
      }
      switch (currentEvent) {
        case 'session_id':
          sessionId = (payload.session_id as string) ?? sessionId;
          break;
        case 'text': {
          const c = payload.content as string | undefined;
          if (c) content += c;
          break;
        }
        case 'error':
          error = (payload.message as string) ?? 'Unknown error';
          break;
      }
    }
  }
  return { content, sessionId, error };
}

// The v3.6.1 (pre-#249) parser: `data:`-only, switches on chunk.type.
// Kept here purely to PROVE the new contract is what fixes #138.
function parseSSE_v361(chunks: string[]): { content: string } {
  let content = '';
  let buffer = '';
  for (const chunk of chunks) {
    buffer += chunk;
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const rawLine of lines) {
      const trimmed = rawLine.trim();
      if (!trimmed || !trimmed.startsWith('data:')) continue;
      let chunkObj: Record<string, unknown>;
      try {
        chunkObj = JSON.parse(trimmed.slice(5).trim()) as Record<string, unknown>;
      } catch {
        continue;
      }
      switch (chunkObj.type) {
        case 'text':
          content += (chunkObj.content as string) ?? '';
          break;
      }
    }
  }
  return { content };
}

/**
 * The EXACT wire format the live backend emits (verified by hitting
 * /api/v1/erp_chat/stream/ — `event: <name>\ndata: <json>\n\n`). The
 * backend re-chunks the OpenRouter completion into 50-char `text` frames.
 */
function backendSSEForOpenRouter(answer: string, sessionId: string): string {
  let out = `event: session_id\ndata: ${JSON.stringify({ session_id: sessionId })}\n\n`;
  for (let i = 0; i < answer.length; i += 50) {
    out += `event: text\ndata: ${JSON.stringify({ content: answer.slice(i, i + 50) })}\n\n`;
  }
  out += `event: done\ndata: ${JSON.stringify({ session_id: sessionId, tokens: 1540 })}\n\n`;
  return out;
}

// Split a string into network-realistic chunks (fetch never respects
// frame boundaries — chunks land mid-`data:`, mid-JSON, mid-unicode-byte).
function networkChunks(s: string, size: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < s.length; i += size) out.push(s.slice(i, i + size));
  return out;
}

describe('issue #138 - OpenRouter chat SSE rendering', () => {
  const SID = '2acf082e-da7f-471d-97be-e4fe3a289ade';
  const ANSWER =
    'Here is your construction estimate.\n\n' +
    '- Concrete C30/37: 12.5 m³\n' +
    'Quote: "two layers" of rebar. Unicode: €1.234,56 - π≈3.14';

  it('renders the full OpenRouter answer (single chunk)', () => {
    const wire = backendSSEForOpenRouter(ANSWER, SID);
    const r = parseSSE([wire]);
    expect(r.error).toBeNull();
    expect(r.sessionId).toBe(SID);
    expect(r.content).toBe(ANSWER);
  });

  it('renders correctly when the network splits frames at every boundary', () => {
    const wire = backendSSEForOpenRouter(ANSWER, SID);
    for (const size of [1, 3, 7, 13, 64, 4096]) {
      const r = parseSSE(networkChunks(wire, size));
      expect(r.content, `chunk size ${size}`).toBe(ANSWER);
      expect(r.sessionId, `chunk size ${size}`).toBe(SID);
    }
  });

  it('surfaces a backend error frame instead of rendering empty', () => {
    const wire =
      `event: session_id\ndata: ${JSON.stringify({ session_id: SID })}\n\n` +
      `event: error\ndata: ${JSON.stringify({ message: 'No AI API key configured.' })}\n\n` +
      `event: done\ndata: {}\n\n`;
    const r = parseSSE([wire]);
    expect(r.error).toBe('No AI API key configured.');
    expect(r.content).toBe('');
  });

  it('REGRESSION GUARD: the v3.6.1 data-only/chunk.type parser renders NOTHING', () => {
    // Same intact backend stream. The old parser produces empty output —
    // this is precisely why the user saw "Chat IA no responde" even when
    // the stream was delivered. The new parser MUST render it.
    const wire = backendSSEForOpenRouter(ANSWER, SID);
    expect(parseSSE_v361([wire]).content).toBe(''); // the bug
    expect(parseSSE([wire]).content).toBe(ANSWER); // the fix
  });

  it('does not leak event state across frames (event resets on blank line)', () => {
    // A stray data: line AFTER the frame's blank terminator must be
    // ignored, not appended as text under a stale event name.
    const wire =
      `event: text\ndata: ${JSON.stringify({ content: 'real ' })}\n\n` +
      `data: ${JSON.stringify({ content: 'LEAKED' })}\n\n` +
      `event: text\ndata: ${JSON.stringify({ content: 'answer' })}\n\n`;
    expect(parseSSE([wire]).content).toBe('real answer');
  });
});
