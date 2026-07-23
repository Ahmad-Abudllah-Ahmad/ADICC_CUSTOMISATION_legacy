// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Regression suite for /match-elements pipeline UX bugs.
//
// P0-1 — Stale-stage skip in run-all loop. When the user adjusts an
// upstream stage's inputs (say, stage 2 group_by) after a downstream
// stage already completed, the backend marks the downstream stages
// `stale` — but the FE's "Run all" used to early-exit on any non-`error`
// status because the loop's contract was unclear. The contract must be:
// every stage runs unconditionally on Run-all; only a backend-reported
// `error` (or a transport throw) breaks the loop. Stale stages MUST
// re-execute so the downstream output reflects the latest upstream
// inputs.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
  act,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { StageListResponse, StageState, StageName } from '../api';

// Stub api so we control listStages + runStage call-by-call. The stage
// fixture mirrors the backend ``MatchStageState`` row shape.
vi.mock('../api', () => ({
  matchElementsApi: {
    listStages: vi.fn(),
    runStage: vi.fn(),
  },
}));

// StageCard pulls in the visual stack we don't need here — only the
// data flow matters. Stub it down to a marker element that exposes
// status + a Run button.
vi.mock('../StageCard', () => ({
  StageCard: ({ stage, onRun }: { stage: StageState; onRun: () => void }) => (
    <div data-testid={`stage-card-${stage.stage_name}`} data-status={stage.status}>
      <button data-testid={`stage-run-${stage.stage_name}`} onClick={onRun}>
        Run {stage.stage_name}
      </button>
    </div>
  ),
}));

vi.mock('../StageAdjustSheet', () => ({
  StageAdjustSheet: () => null,
}));

import { matchElementsApi } from '../api';
import { MatchPipeline } from '../MatchPipeline';

const listStagesSpy = matchElementsApi.listStages as ReturnType<typeof vi.fn>;
const runStageSpy = matchElementsApi.runStage as ReturnType<typeof vi.fn>;

const STAGE_ORDER: StageName[] = [
  'convert',
  'load',
  'schema',
  'filter',
  'group',
  'match',
  'rollup',
];

function makeStage(name: StageName, status: StageState['status']): StageState {
  return {
    stage_name: name,
    title: name,
    subtitle: '',
    explainer: '',
    uses_llm: false,
    prompt_key: null,
    status,
    inputs: {},
    output: {},
    error: null,
    took_ms: null,
    prompt_template_id: null,
    llm_provider: null,
    started_at: null,
    finished_at: null,
    updated_at: null,
  };
}

function stageList(
  statusFor: Partial<Record<StageName, StageState['status']>>,
): StageListResponse {
  return {
    session_id: 'sess-1',
    stages: STAGE_ORDER.map((n) => makeStage(n, statusFor[n] ?? 'pending')),
  };
}

function renderPipeline() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MatchPipeline sessionId="sess-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listStagesSpy.mockReset();
  runStageSpy.mockReset();
  // jsdom doesn't implement scrollIntoView; MatchPipeline calls it on
  // mount to bring the headline pipeline into view. Stub it so the
  // mount effect doesn't throw.
  if (!('scrollIntoView' in HTMLElement.prototype)) {
    // @ts-expect-error — jsdom prototype patch
    HTMLElement.prototype.scrollIntoView = () => {};
  } else {
    vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(() => {});
  }
  // Default: every runStage call returns 'done' for the requested stage.
  runStageSpy.mockImplementation(async (_sid: string, name: StageName) => ({
    stage_name: name,
    status: 'done',
    output: {},
    error: null,
    took_ms: 1,
  }));
});

afterEach(() => {
  cleanup();
});

describe('MatchPipeline - P0-1 stale-stage skip regression', () => {
  it('Run-all re-executes every stage in ORDER, including stale ones', async () => {
    // Simulates the post-edit state: stages 1-2 are done with fresh
    // inputs, 3-7 carry stale outputs from a prior run that no longer
    // reflect the upstream change. Run-all must hit all seven.
    listStagesSpy.mockResolvedValue(
      stageList({
        convert: 'done',
        load: 'done',
        schema: 'stale',
        filter: 'stale',
        group: 'stale',
        match: 'stale',
        rollup: 'stale',
      }),
    );

    renderPipeline();

    // Wait for the "Run all stages" button to mount (driven by stagesQ).
    // The test setup's i18n mock returns the *key* (not the
    // ``defaultValue`` positional arg) when t() is called with the
    // two-string positional signature, so we locate the Run-all button
    // by its translation key. Production code locales swap this for the
    // localised label without affecting the test contract.
    const runAllBtn = await screen.findByText(/match_elements\.pipeline\.run_all\b/);
    await act(async () => {
      fireEvent.click(runAllBtn);
    });

    await waitFor(() => {
      // Every stage in ORDER must have been called exactly once.
      expect(runStageSpy).toHaveBeenCalledTimes(STAGE_ORDER.length);
    });

    // Verify call order matches ORDER — a regression that "skipped"
    // stale stages would either drop calls or reorder them.
    const calledNames = runStageSpy.mock.calls.map((c) => c[1]);
    expect(calledNames).toEqual(STAGE_ORDER);
  });

  it('Run-all stops at the first stage that reports status=error', async () => {
    // The OTHER half of the contract: a real error must halt the loop
    // so the user can fix the failing stage instead of cascading
    // garbage forward. Schema (stage 3) blows up here.
    listStagesSpy.mockResolvedValue(stageList({}));

    runStageSpy.mockImplementation(async (_sid: string, name: StageName) => ({
      stage_name: name,
      status: name === 'schema' ? 'error' : 'done',
      output: {},
      error: name === 'schema' ? 'boom' : null,
      took_ms: 1,
    }));

    renderPipeline();

    // The test setup's i18n mock returns the *key* (not the
    // ``defaultValue`` positional arg) when t() is called with the
    // two-string positional signature, so we locate the Run-all button
    // by its translation key. Production code locales swap this for the
    // localised label without affecting the test contract.
    const runAllBtn = await screen.findByText(/match_elements\.pipeline\.run_all\b/);
    await act(async () => {
      fireEvent.click(runAllBtn);
    });

    await waitFor(() => {
      // convert, load, schema — then the break fires.
      expect(runStageSpy).toHaveBeenCalledTimes(3);
    });
    const calledNames = runStageSpy.mock.calls.map((c) => c[1]);
    expect(calledNames).toEqual(['convert', 'load', 'schema']);
  });
});
