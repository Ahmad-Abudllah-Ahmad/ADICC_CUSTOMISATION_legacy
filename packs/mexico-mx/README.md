# Mexico Construction Pack

Pre-configures OpenConstructionERP for Mexican construction with the local
unit-price method, tax rules, electronic invoicing, social-housing context and
site-safety norms. Built so a real Mexican user can pilot on a social-housing
project and a private-residential project from day one.

## What this pack enables

- Currency MXN and IVA 16 percent, with the 8 percent border region (region
  fronteriza) and IVA/ISR retenciones on subcontractor payments
- Spanish locale (es) with a Mexican Spanish (es-MX) vocabulary overlay and
  Letter paper size
- APU estimating methodology (analisis de precios unitarios): costo directo
  (mano de obra, materiales, maquinaria) plus indirectos, financiamiento,
  utilidad and cargos adicionales, integrated per the LOPSRM reglamento
- CFDI 4.0 invoicing fields: RFC, regimen fiscal and uso CFDI
- Social-housing bodies for the vivienda pilot: INFONAVIT, FOVISSSTE, CONAVI
- IMSS social security and NOM-031-STPS construction site safety
- Mexican flag colours for co-branding
- 32 states available as cost regions, wired to the MX_MEXICO CWICR dataset

## Install

This pack ships inside OpenConstructionERP. Activate it from Modules then
Packs: click Rescan, find "Mexico Construction Pack", then Apply.

To run a workspace that boots straight into it:

```bash
OE_PACK=mexico-mx openconstructionerp serve
```

## Standards referenced

- Ley de Obras Publicas y Servicios Relacionados con las Mismas (LOPSRM) and
  its reglamento (integration of precios unitarios)
- Ley del Impuesto al Valor Agregado (SAT): IVA 16 percent, 8 percent in the
  border region, IVA/ISR retenciones
- CFDI 4.0 electronic invoicing (SAT): RFC, regimen fiscal, uso CFDI
- Instituto Mexicano del Seguro Social (IMSS) employer obligations
- NOM-031-STPS-2011 construction site safety (STPS)
- INFONAVIT, FOVISSSTE and CONAVI social-housing finance and policy

INFONAVIT, FOVISSSTE, CONAVI, IMSS, SAT, CFDI, LOPSRM and the NOM standards are
Mexican government bodies, laws and standards referenced for compliance.

## Estimating: APU

The pack activates the Mexican APU methodology. A unit price is integrated as
costo directo, then indirectos, financiamiento, utilidad and cargos adicionales
(the cinco al millar inspection fee is the usual content of cargos adicionales).
IVA is applied to the estimate total, not folded into the unit price. The
oe_mexico_pack module exposes endpoints that integrate a unit price, compute an
IVA breakdown, and compute IVA/ISR retenciones on a subcontract payment. Every
percentage is a clearly labelled, editable starting point, not a regulated
figure.

## Cost data

Rates are not bundled. The pack points at the MX_MEXICO CWICR region so real
Mexican cost data loads on demand once the snapshot is published. State location
factors are provided as indicative starting points and are fully editable; they
are not an official index.

## License

AGPL-3.0-or-later. OpenConstructionERP is authored and owned by
DataDrivenConstruction.
