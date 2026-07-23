// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Pure helpers for the progress-rigor panel (T3.2). Kept out of the .tsx so
// they can be unit-tested without a DOM. The authoritative math lives in the
// backend engine (progress_math.py); the client-side step roll-up here only
// drives the live footer preview and must agree with the server (weighted
// average; plain mean when total weight is 0; milestone-below-100 caps the
// roll-up below complete).

import { toNum } from '@/shared/lib/money';
import type { EvmWarningKey, PercentCompleteType } from './api';

export interface StepLike {
  weight: string | number;
  percent_complete: string | number;
  is_milestone?: boolean;
}

/** Sum of step weights. */
export function totalWeight(steps: StepLike[]): number {
  return steps.reduce((sum, s) => sum + toNum(s.weight), 0);
}

/**
 * Client mirror of the server step roll-up. Returns a 0..100 percent.
 *
 * - no steps -> 0
 * - total weight 0 -> plain mean of the step percents
 * - otherwise -> weighted average
 * - any milestone step below 100 caps the result at 99.999
 */
export function rollupSteps(steps: StepLike[]): number {
  if (!steps.length) return 0;
  const tw = totalWeight(steps);
  let rolled: number;
  if (tw === 0) {
    rolled = steps.reduce((sum, s) => sum + toNum(s.percent_complete), 0) / steps.length;
  } else {
    rolled = steps.reduce((sum, s) => sum + toNum(s.weight) * toNum(s.percent_complete), 0) / tw;
  }
  const hasOpenMilestone = steps.some((s) => s.is_milestone && toNum(s.percent_complete) < 100);
  if (hasOpenMilestone && rolled > 99.999) rolled = 99.999;
  return Math.min(100, Math.max(0, rolled));
}

/** PV as a percent of BAC, or '-' when BAC is zero/unknown. */
export function pvPercentOfBac(pv: string | number | null | undefined, bac: string | number | null | undefined): string {
  const p = toNum(pv);
  const b = toNum(bac);
  if (!b) return '-';
  return `${((p / b) * 100).toFixed(1)}%`;
}

/** i18n default-value text for each deterministic EVM-distortion warning key. */
export const EVM_WARNING_DEFAULTS: Record<EvmWarningKey, string> = {
  units_type_without_budgeted_units:
    'Units type with no budgeted quantity - % cannot be derived from quantity.',
  duration_type_on_nonlinear_cost:
    'Duration type on front/back-loaded cost - earning by time will misstate EV.',
  physical_manual_pct_is_subjective:
    'Manual physical % with no steps - the percent is subjective and unverified.',
  all_steps_zero_weight: 'All steps have zero weight - the roll-up degrades to a plain average.',
};

/** The three percent-complete types in canonical (UI) order. */
export const PERCENT_TYPES: readonly PercentCompleteType[] = ['duration', 'units', 'physical'];
