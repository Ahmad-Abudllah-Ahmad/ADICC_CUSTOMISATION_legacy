# `openconstructionerp-aus-nzs` — DEPRECATED

This combined Australia + New Zealand partner pack has been **split** into
two single-jurisdiction packs because AU and NZ use different defaults
that cannot live in one `PartnerPackManifest`:

|                | Australia (`aus`)            | New Zealand (`nzs`)              |
| -------------- | ---------------------------- | -------------------------------- |
| Currency       | AUD                          | NZD                              |
| GST rate       | 10 %                         | 15 %                             |
| Locale         | en-AU                        | en-NZ                            |
| Building code  | NCC 2022                     | NZBC + MBIE Acceptable Solutions |
| Timber framing | AS 1684 Parts 1-4            | NZS 3604:2011                    |
| Conditions     | AS 4000-1997 / AS 4902-2000  | NZS 3910:2023                    |
| Licence regime | State-specific (VBA, QBCC, NSW Fair Trading, …) | National LBP (MBIE)              |

Install the appropriate per-country pack instead:

```bash
pip install openconstructionerp-aus   # Australia
pip install openconstructionerp-nzs   # New Zealand
```

The legacy `openconstructionerp-aus-nzs` is preserved as a backward-
compatibility shim that depends on `openconstructionerp-aus` and re-
exports its manifest unchanged. Importing it emits a
`DeprecationWarning`. It will be removed in a future major release.
