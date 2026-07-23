// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Pure helpers for tendering bid analysis — per-cell outlier flagging
 * and award recommendation classification. Dependency-free so they're
 * easy to unit-test and reuse across the comparison table, recommendation
 * banner, and any future tender export pipeline.
 */

export type CellOutlier = 'high' | 'low' | null;

/**
 * Classify one bid's unit_rate against the row median.
 *
 * Returns ``null`` when fewer than 2 priced bids are available or the
 * cell itself is zero (bid omitted that line). Returns ``'high'`` /
 * ``'low'`` when the rate falls outside ±threshold of the median. Median
 * (not mean) keeps a single extreme bid from skewing the comparison.
 */
export function classifyCell(
  rate: number,
  rowRates: number[],
  threshold = 0.15,
): CellOutlier {
  const priced = rowRates.filter((r) => r > 0);
  if (priced.length < 2 || rate <= 0) return null;
  const sorted = [...priced].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median =
    sorted.length % 2 === 0
      ? (sorted[mid - 1]! + sorted[mid]!) / 2
      : sorted[mid]!;
  if (median <= 0) return null;
  if (rate >= median * (1 + threshold)) return 'high';
  if (rate <= median * (1 - threshold)) return 'low';
  return null;
}

export interface BidTotalLike {
  bid_id: string;
  company_name: string;
  total: number;
  currency: string;
  deviation_pct: number;
  status: string;
}

export type RecommendationConfidence = 'high' | 'medium' | 'low';

export interface AwardRecommendation {
  winner: BidTotalLike;
  runnerUp: BidTotalLike | null;
  confidence: RecommendationConfidence;
  reasonKey:
    | 'single_bid'
    | 'clear_winner'
    | 'narrow_gap'
    | 'suspicious_low';
  gapAmount: number;
  belowMedianPct: number;
}

/**
 * Recommend a winner among submitted bid totals. ``rejected`` bids are
 * filtered so a previously-declined bidder is never recommended. Returns
 * ``null`` only when no eligible bid exists.
 */
export function recommend(
  totals: BidTotalLike[],
): AwardRecommendation | null {
  const eligible = totals.filter(
    (b) => b.status !== 'rejected' && b.total > 0,
  );
  if (eligible.length === 0) return null;
  const sorted = [...eligible].sort((a, b) => a.total - b.total);
  const winner = sorted[0]!;
  const runnerUp = sorted[1] ?? null;
  const gapAmount = runnerUp ? runnerUp.total - winner.total : 0;

  let belowMedianPct = 0;
  if (eligible.length >= 3) {
    const ms = eligible.map((b) => b.total).sort((a, b) => a - b);
    const mid = Math.floor(ms.length / 2);
    const median =
      ms.length % 2 === 0 ? (ms[mid - 1]! + ms[mid]!) / 2 : ms[mid]!;
    if (median > 0) {
      belowMedianPct = Math.max(0, ((median - winner.total) / median) * 100);
    }
  }

  if (eligible.length === 1) {
    return { winner, runnerUp: null, confidence: 'medium', reasonKey: 'single_bid', gapAmount: 0, belowMedianPct: 0 };
  }
  if (belowMedianPct > 20) {
    return { winner, runnerUp, confidence: 'low', reasonKey: 'suspicious_low', gapAmount, belowMedianPct: Math.round(belowMedianPct * 10) / 10 };
  }
  const gapRatio = runnerUp && winner.total > 0 ? gapAmount / winner.total : 0;
  if (gapRatio < 0.02) {
    return { winner, runnerUp, confidence: 'medium', reasonKey: 'narrow_gap', gapAmount, belowMedianPct: Math.round(belowMedianPct * 10) / 10 };
  }
  return { winner, runnerUp, confidence: 'high', reasonKey: 'clear_winner', gapAmount, belowMedianPct: Math.round(belowMedianPct * 10) / 10 };
}
