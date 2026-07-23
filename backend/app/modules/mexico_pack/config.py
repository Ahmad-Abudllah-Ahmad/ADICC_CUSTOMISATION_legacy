# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Regional configuration for Mexico.

All figures are drawn from public Mexican standards, laws and tax rules.
Money is represented as Decimal-as-string, in line with the platform money
convention. State location factors are indicative starting points, not an
official index, and are meant to be edited per organisation.

VAT (IVA) ownership note: the canonical Mexican IVA rates live in
``app.core.tax`` (MX standard 16 percent, border region 8 percent captured as
the ``reduced`` kind, zero 0 percent) and the LATAM regional pack already
declares them for the cross-pack completeness check. This pack therefore does
NOT re-declare a ``vat_rates`` aggregation key; it adds Mexican construction
depth (APU integration, retenciones, CFDI, social housing, site safety) on top
of that shared rate source. The ``tax`` block below is reference data served by
the router, not a competing rate registry.
"""

from typing import Any

# IVA rates as percentage strings, mirrored from app.core.tax for the router
# and the APU integration default. 16 percent is the standard rate; 8 percent
# applies in the northern and southern border regions (region fronteriza).
IVA_STANDARD_PCT = "16"
IVA_BORDER_PCT = "8"

# Cinco al millar (5 per 1000 = 0.5 percent): the federal inspection and
# oversight fee withheld on public works, the usual content of "cargos
# adicionales" in an APU under the LOPSRM reglamento.
CINCO_AL_MILLAR_PCT = "0.5"

# Reference IVA retention rate for labor-provision subcontracts (Art. 1-A,
# fraction IV of the Ley del IVA, effective 2020-01-01: a 6 percent IVA
# retention when personnel are placed at the contratante's disposal). It is a
# configurable starting point, not an automatic charge; retention applicability
# depends on the supplier's regime and the contract.
DEFAULT_RETENCION_IVA_PCT = "6"

PACK_CONFIG: dict[str, Any] = {
    # ── Identity ─────────────────────────────────────────────────────────────
    "region_code": "MX",
    "countries": ["MX"],
    "default_currency": "MXN",
    "default_locale": "es-MX",
    "measurement_system": "metric",
    # Mexico uses US Letter, not ISO A4, for printed tender and estimate output.
    "paper_size": "Letter",
    "date_format": "DD/MM/YYYY",
    # es-MX groups thousands with a comma and uses a dot decimal separator
    # (1,234.56), unlike Spain's 1.234,56. This is a deliberate Mexican setting.
    "number_format": "1,234.56",
    # ── Public-works regulatory context ──────────────────────────────────────
    "regulatory_framework": {
        "public_works_law": {
            "code": "LOPSRM",
            "name": "Ley de Obras Publicas y Servicios Relacionados con las Mismas",
            "scope": "Federal public works and related services",
            "regulator": "Secretaria de la Funcion Publica (SFP)",
        },
        "regulation": {
            "code": "RLOPSRM",
            "name": "Reglamento de la Ley de Obras Publicas y Servicios Relacionados con las Mismas",
            "scope": "Integration of unit prices (precios unitarios) and contract administration",
        },
        "note": (
            "Federal public works follow the LOPSRM and its reglamento; many "
            "states mirror the structure in their own obra publica statutes. "
            "Unit prices are integrated per the reglamento as costo directo, "
            "indirectos, financiamiento, utilidad and cargos adicionales."
        ),
    },
    # ── Estimating methodology: APU (analisis de precios unitarios) ──────────
    "apu": {
        "name": "Analisis de precios unitarios (APU)",
        "methodology_slug": "mexico",
        "integration_order": [
            "costo_directo",
            "costo_indirecto",
            "costo_por_financiamiento",
            "cargo_por_utilidad",
            "cargos_adicionales",
        ],
        "components": [
            {
                "key": "materiales",
                "label": "Materiales",
                "part_of": "costo_directo",
                "description": "Cost of materials placed at the work site.",
            },
            {
                "key": "mano_de_obra",
                "label": "Mano de obra",
                "part_of": "costo_directo",
                "description": "Labor cost, including the salario real factor and statutory charges.",
            },
            {
                "key": "maquinaria_herramienta",
                "label": "Maquinaria, equipo y herramienta",
                "part_of": "costo_directo",
                "description": "Construction machinery, equipment and minor tools (herramienta menor).",
            },
            {
                "key": "indirectos",
                "label": "Costo indirecto",
                "applies_to": "costo_directo",
                "description": "Office (oficinas centrales) and field (oficinas de campo) overhead, as a percentage.",
            },
            {
                "key": "financiamiento",
                "label": "Costo por financiamiento",
                "applies_to": "costo_directo + indirectos",
                "description": "Cost of money to fund the work between expenditure and payment, as a percentage.",
            },
            {
                "key": "utilidad",
                "label": "Cargo por utilidad",
                "applies_to": "costo_directo + indirectos + financiamiento",
                "description": "Contractor profit, as a percentage of the accumulated cost.",
            },
            {
                "key": "cargos_adicionales",
                "label": "Cargos adicionales",
                "applies_to": "costo_directo + indirectos + financiamiento + utilidad",
                "description": (
                    "Additional charges set by law, typically the cinco al millar inspection fee "
                    "and other mandated contributions. Not the IVA, which is added to the total."
                ),
            },
        ],
        "note": (
            "The precio unitario is the sum of costo directo, indirectos, "
            "financiamiento, utilidad and cargos adicionales. IVA is applied to "
            "the estimate total, not folded into the unit price."
        ),
    },
    # ── Tax: IVA and retenciones (reference data, served by the router) ──────
    "tax": {
        "iva": {
            "code": "MX_IVA",
            "name": "IVA - Impuesto al Valor Agregado",
            "regulator": "Servicio de Administracion Tributaria (SAT)",
            "legislation": "Ley del Impuesto al Valor Agregado",
            "standard_rate_pct": IVA_STANDARD_PCT,
            "border_region_rate_pct": IVA_BORDER_PCT,
            "zero_rate_pct": "0",
            "border_region_note": (
                "An 8 percent rate applies in the northern and southern border "
                "regions (region fronteriza) under the SAT stimulus decrees, "
                "subject to registration and compliance conditions."
            ),
        },
        "retenciones": [
            {
                "code": "RET_IVA",
                "name": "Retencion de IVA",
                "reference_rate_pct": DEFAULT_RETENCION_IVA_PCT,
                "basis": (
                    "IVA withheld on certain subcontracted services (e.g. the 6 percent "
                    "retention on labor-provision services under Art. 1-A fraction IV of the "
                    "Ley del IVA). Applicability depends on the service and the supplier's regime."
                ),
            },
            {
                "code": "RET_ISR",
                "name": "Retencion de ISR",
                "reference_rate_pct": "0",
                "basis": (
                    "ISR withheld on subcontractor payments in the cases the Ley del ISR "
                    "establishes. The rate depends on the payment type and regime, so it is "
                    "left for the user to set per contract."
                ),
            },
        ],
        "note": (
            "Retenciones are withheld from the subcontractor payment and paid to "
            "the SAT by the contratante. Rates here are configurable references, "
            "applied only after human confirmation, never automatically."
        ),
    },
    # ── Electronic invoicing: CFDI 4.0 ───────────────────────────────────────
    "cfdi": {
        "version": "4.0",
        "name": "Comprobante Fiscal Digital por Internet (CFDI)",
        "regulator": "Servicio de Administracion Tributaria (SAT)",
        "required_issuer_fields": ["rfc", "nombre_razon_social", "regimen_fiscal", "codigo_postal"],
        "required_receiver_fields": [
            "rfc",
            "nombre_razon_social",
            "domicilio_fiscal_receptor",
            "regimen_fiscal",
            "uso_cfdi",
        ],
        "rfc_note": (
            "RFC has 12 characters for a persona moral (company) and 13 for a "
            "persona fisica (individual): a 3 or 4 letter prefix, a 6 digit date "
            "(YYMMDD) and a 3 character homoclave."
        ),
        "regimen_fiscal_examples": [
            {"code": "601", "label": "General de Ley Personas Morales"},
            {"code": "603", "label": "Personas Morales con Fines no Lucrativos"},
            {"code": "612", "label": "Personas Fisicas con Actividades Empresariales y Profesionales"},
            {"code": "626", "label": "Regimen Simplificado de Confianza (RESICO)"},
        ],
        "uso_cfdi_examples": [
            {"code": "G01", "label": "Adquisicion de mercancias"},
            {"code": "G03", "label": "Gastos en general"},
            {"code": "I01", "label": "Construcciones"},
            {"code": "CP01", "label": "Pagos"},
        ],
        "metodo_pago": [
            {"code": "PUE", "label": "Pago en una sola exhibicion"},
            {"code": "PPD", "label": "Pago en parcialidades o diferido"},
        ],
    },
    # ── Social housing programs and bodies ───────────────────────────────────
    "social_housing": {
        "note": (
            "Social-housing projects in Mexico are financed and regulated mainly "
            "through INFONAVIT, FOVISSSTE and the CONAVI policy framework."
        ),
        "bodies": [
            {
                "code": "INFONAVIT",
                "name": "Instituto del Fondo Nacional de la Vivienda para los Trabajadores",
                "role": "Mortgage financing and housing fund for private-sector workers.",
            },
            {
                "code": "FOVISSSTE",
                "name": "Fondo de la Vivienda del ISSSTE",
                "role": "Housing fund and mortgage financing for public-sector workers.",
            },
            {
                "code": "CONAVI",
                "name": "Comision Nacional de Vivienda",
                "role": "National housing policy, subsidies and technical guidelines.",
            },
        ],
    },
    # ── Labor and site safety (IMSS + NOM) ───────────────────────────────────
    "labor_safety": {
        "social_security": {
            "code": "IMSS",
            "name": "Instituto Mexicano del Seguro Social",
            "role": (
                "Social security registration of construction workers and "
                "employer contributions, including the construction-industry "
                "obligations (obra) under the IMSS regulations."
            ),
        },
        "nom_standards": [
            {
                "code": "NOM-031-STPS-2011",
                "name": "Construccion - condiciones de seguridad y salud en el trabajo",
                "regulator": "Secretaria del Trabajo y Prevision Social (STPS)",
                "scope": "Primary construction site safety and health standard.",
            },
            {
                "code": "NOM-009-STPS-2011",
                "name": "Condiciones de seguridad para trabajos en altura",
                "regulator": "Secretaria del Trabajo y Prevision Social (STPS)",
                "scope": "Work at height.",
            },
            {
                "code": "NOM-001-STPS-2008",
                "name": "Edificios, locales, instalaciones y areas - condiciones de seguridad",
                "regulator": "Secretaria del Trabajo y Prevision Social (STPS)",
                "scope": "Buildings, premises and areas safety conditions.",
            },
        ],
    },
    # ── Contract types (LOPSRM) ──────────────────────────────────────────────
    "contract_types": [
        {"code": "MX_PRECIO_UNITARIO", "name": "Contrato a precios unitarios", "publisher": "LOPSRM"},
        {"code": "MX_PRECIO_ALZADO", "name": "Contrato a precio alzado", "publisher": "LOPSRM"},
        {"code": "MX_MIXTO", "name": "Contrato mixto", "publisher": "LOPSRM"},
    ],
    # ── States (32 federal entities, indicative location factors) ────────────
    # Base Ciudad de Mexico = 1.00. ``border_region`` flags entities where the
    # 8 percent IVA border-region rate can apply (subject to SAT conditions).
    "states": [
        {"name": "Aguascalientes", "location_factor_indicative": "0.95", "border_region": False},
        {"name": "Baja California", "location_factor_indicative": "1.05", "border_region": True},
        {"name": "Baja California Sur", "location_factor_indicative": "1.06", "border_region": True},
        {"name": "Campeche", "location_factor_indicative": "0.98", "border_region": True},
        {"name": "Chiapas", "location_factor_indicative": "0.94", "border_region": True},
        {"name": "Chihuahua", "location_factor_indicative": "1.00", "border_region": True},
        {"name": "Ciudad de Mexico", "location_factor_indicative": "1.00", "border_region": False},
        {"name": "Coahuila", "location_factor_indicative": "0.99", "border_region": True},
        {"name": "Colima", "location_factor_indicative": "0.97", "border_region": False},
        {"name": "Durango", "location_factor_indicative": "0.95", "border_region": False},
        {"name": "Guanajuato", "location_factor_indicative": "0.96", "border_region": False},
        {"name": "Guerrero", "location_factor_indicative": "0.97", "border_region": False},
        {"name": "Hidalgo", "location_factor_indicative": "0.95", "border_region": False},
        {"name": "Jalisco", "location_factor_indicative": "1.01", "border_region": False},
        {"name": "Mexico", "location_factor_indicative": "1.00", "border_region": False},
        {"name": "Michoacan", "location_factor_indicative": "0.96", "border_region": False},
        {"name": "Morelos", "location_factor_indicative": "0.98", "border_region": False},
        {"name": "Nayarit", "location_factor_indicative": "0.96", "border_region": False},
        {"name": "Nuevo Leon", "location_factor_indicative": "1.04", "border_region": True},
        {"name": "Oaxaca", "location_factor_indicative": "0.95", "border_region": False},
        {"name": "Puebla", "location_factor_indicative": "0.97", "border_region": False},
        {"name": "Queretaro", "location_factor_indicative": "0.99", "border_region": False},
        {"name": "Quintana Roo", "location_factor_indicative": "1.03", "border_region": True},
        {"name": "San Luis Potosi", "location_factor_indicative": "0.97", "border_region": False},
        {"name": "Sinaloa", "location_factor_indicative": "0.98", "border_region": False},
        {"name": "Sonora", "location_factor_indicative": "1.02", "border_region": True},
        {"name": "Tabasco", "location_factor_indicative": "1.00", "border_region": True},
        {"name": "Tamaulipas", "location_factor_indicative": "1.01", "border_region": True},
        {"name": "Tlaxcala", "location_factor_indicative": "0.95", "border_region": False},
        {"name": "Veracruz", "location_factor_indicative": "0.98", "border_region": False},
        {"name": "Yucatan", "location_factor_indicative": "0.98", "border_region": False},
        {"name": "Zacatecas", "location_factor_indicative": "0.95", "border_region": False},
    ],
    "states_note": (
        "Location factors are indicative starting points relative to Ciudad de "
        "Mexico, not an official index. Edit them to match your own cost data. "
        "The border_region flag marks entities where the 8 percent IVA border "
        "rate can apply, subject to SAT registration and compliance conditions."
    ),
    # ── Units (metric defaults) ──────────────────────────────────────────────
    "default_units": {
        "length": "m",
        "area": "m2",
        "volume": "m3",
        "weight": "kg",
        "temperature": "°C",
    },
    # ── Cost database integration ────────────────────────────────────────────
    # MX_MEXICO is the canonical CWICR region for Mexico (currency MXN). The
    # HuggingFace snapshot for it is published under the legacy stem
    # MX_MEXICOCITY; that translation is handled inside the cost layer, so the
    # region id used everywhere in the app is MX_MEXICO.
    "cost_database_integrations": [
        {
            "code": "CWICR_MX_MEXICO",
            "name": "CWICR Mexico (Mexico City)",
            "region_code": "MX_MEXICO",
            "currency": "MXN",
            "language": "es",
            "enabled": True,
            "note": (
                "Cost rows download on demand from the CWICR data repo; the "
                "BGE-M3 vector snapshot loads via "
                "'python -m scripts.seed_cwicr_v3 --regions MX_MEXICO'. The "
                "snapshot file is published under the legacy stem MX_MEXICOCITY "
                "and resolved automatically."
            ),
        },
    ],
}
