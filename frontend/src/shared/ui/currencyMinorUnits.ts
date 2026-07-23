// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * ISO-4217 minor-unit lookup — Audit I1-I3.
 *
 * Browsers' built-in `Intl.NumberFormat` does the right thing for most
 * currencies, but real-world Node + older browsers ship with stale
 * currency tables. Hardcoding the deltas-from-default-of-2 means we
 * stop losing precision on KWD/BHD/OMR/TND (which need 3 decimals)
 * and stop padding fake decimals onto JPY/KRW/IDR/CLP/etc. (which
 * have 0 decimals).
 *
 * Sources:
 *  - ISO-4217 Maintenance Agency (https://www.six-group.com/dam/...
 *    list-one.xml) — official table.
 *  - SWIFT MT Standards Release Guide — confirms three-decimal
 *    currencies (Bahrain, Iraq, Jordan, Kuwait, Libya, Oman, Tunisia).
 *  - XAU/XAG/XBT/etc. are quoted in troy ounces / fractional crypto
 *    so we default them to 2 (they should always be passed with an
 *    explicit override at the call site for trading apps).
 *
 * The function is pure + synchronous (no I/O) so it's safe to call
 * from render code thousands of times per second.
 */

// Zero-decimal currencies (ISO-4217 minor unit = 0).
const ZERO_DECIMAL = new Set<string>([
  'BIF', // Burundian Franc
  'CLP', // Chilean Peso
  'DJF', // Djiboutian Franc
  'GNF', // Guinean Franc
  'ISK', // Icelandic Króna (officially 0 since 2007)
  'JPY', // Japanese Yen
  'KMF', // Comorian Franc
  'KRW', // South Korean Won
  'PYG', // Paraguayan Guaraní
  'RWF', // Rwandan Franc
  'UGX', // Ugandan Shilling
  'UYI', // Uruguay Peso en Unidades Indexadas (technical only)
  'VND', // Vietnamese Đồng
  'VUV', // Vanuatu Vatu
  'XAF', // Central African CFA Franc
  'XOF', // West African CFA Franc
  'XPF', // CFP Franc
]);

// Three-decimal currencies (mostly oil-trading and historic dinars).
const THREE_DECIMAL = new Set<string>([
  'BHD', // Bahraini Dinar
  'IQD', // Iraqi Dinar
  'JOD', // Jordanian Dinar
  'KWD', // Kuwaiti Dinar
  'LYD', // Libyan Dinar
  'OMR', // Omani Rial
  'TND', // Tunisian Dinar
]);

// Four-decimal currencies (the funds rather than the cash currency).
const FOUR_DECIMAL = new Set<string>([
  'CLF', // Unidad de Fomento (Chile)
  'UYW', // Uruguay Unidad Previsional
]);

/**
 * Returns the ISO-4217 minor-unit count for ``code``.
 *
 * Falls back to 2 for unknown currencies, matching the historic
 * default. The fallback is intentional so legacy data with codes
 * like ``""`` or ``"EUR"`` (which is genuinely 2) keeps working.
 */
export function currencyMinorUnits(code: string | null | undefined): number {
  if (!code) return 2;
  const c = code.toUpperCase();
  if (ZERO_DECIMAL.has(c)) return 0;
  if (THREE_DECIMAL.has(c)) return 3;
  if (FOUR_DECIMAL.has(c)) return 4;
  return 2;
}
