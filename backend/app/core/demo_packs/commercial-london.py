# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
from __future__ import annotations

from app.core.demo_projects import DemoTemplate

# ---------------------------------------------------------------------------
# Flagship demo: Grade A commercial office building, City of London (UK)
# ---------------------------------------------------------------------------
# Elemental cost plan measured per RICS New Rules of Measurement (NRM 2,
# detailed measurement for building works) and structured to the NRM 1 element
# groups used by UK quantity surveyors for elemental cost planning. Pricing is
# at UK cost-index / London Q1 2026 levels in GBP, VAT exclusive. Building Regulations
# (Approved Documents A-S), the Building Safety Act 2022 (higher-risk building
# regime, golden thread, Gateways 1-3) and CDM 2015 govern the works.
# Structural design to the Eurocodes (BS EN 1990-1998) and BS 8500 concrete.
# Main contract JCT Design and Build 2024 with a two-stage tender. VAT (20%)
# is carried as a separate cumulative markup and never baked into unit rates.
#
# Program: circa 10,500 m2 GIA, NIA approx. 8,400 m2, a 10-storey Grade A
# speculative office over a single-level basement (plant, cycle store, end-of-
# trip facilities). In-situ reinforced-concrete flat-slab frame on a piled
# raft, unitised aluminium curtain walling, BREEAM Outstanding and NABERS UK
# 5-star targets, all-electric with air-source heat pumps and PV. Net Zero
# Carbon in operation aspiration. Headline construction cost circa GBP 42M
# (VAT exclusive).

TEMPLATE = DemoTemplate(
    demo_id="commercial-london",
    project_name="Aldgate Place Commercial Tower",
    project_description=(
        "New-build 10-storey Grade A speculative office over a single-level "
        "basement at Aldgate, City of London. GIA approx. 10,500 m2, NIA "
        "approx. 8,400 m2; typical floorplate circa 1,050 m2 with 2.85 m clear "
        "floor-to-ceiling. In-situ reinforced-concrete flat-slab frame on a "
        "piled raft (CFA / rotary bored piles), post-tensioned transfer at "
        "ground; unitised aluminium curtain walling with a double-skin "
        "ventilated facade to the south. All-electric servicing with air-source "
        "heat pumps, four-pipe fan coils and roof-mounted PV. Designed to the "
        "Eurocodes (BS EN 1990-1998) and the Building Regulations Approved "
        "Documents; delivered under the Building Safety Act 2022 higher-risk "
        "building regime (Gateways 1-3) and CDM 2015. BREEAM Outstanding and "
        "NABERS UK 5-star targets, Net Zero Carbon in operation aspiration. "
        "JCT Design and Build 2024 contract, two-stage tender. Estimated "
        "construction cost circa GBP 42M (VAT exclusive)."
    ),
    region="UK",
    classification_standard="nrm",
    currency="GBP",
    locale="en-GB",
    address={
        "street": "1 Aldgate High Street",
        "city": "London",
        "postcode": "EC3N 1AH",
        "country": "United Kingdom",
        "lat": 51.5138,
        "lng": -0.0759,
    },
    validation_rule_sets=["nrm", "boq_quality"],
    boq_name="Elemental Cost Plan - RICS NRM (Detailed)",
    boq_description=(
        "Detailed elemental cost plan measured to RICS NRM 2 and structured to "
        "the NRM 1 element groups; UK cost-index London Q1 2026 base, JCT D&B 2024"
    ),
    boq_metadata={
        "standard": "RICS NRM 2 (measurement) / NRM 1 (elemental groups)",
        "phase": "RIBA Stage 4 - Technical Design Cost Plan",
        "base_date": "2026-Q1",
        "price_level": "London 2026 (GBP, VAT excl.)",
        "tender_price_index": "UK tender price index 198 (London, 2026 Q1)",
    },
    sections=[
        # -- 0. Facilitating Works -------------------------------------------
        (
            "0",
            "0 - Facilitating Works",
            {"nrm": "0"},
            [
                ("0.1", "Site clearance and removal of redundant slabs (Site clearance)", "m2", 1450, 22.00, {"nrm": "0.1"}),
                ("0.2", "Demolition of existing 1960s office structure (Demolition)", "m3", 28000, 18.50, {"nrm": "0.2"}),
                ("0.3", "Asbestos survey and licensed removal (Asbestos removal)", "lsum", 1, 165000.00, {"nrm": "0.3"}),
                ("0.4", "Intrusive ground investigation and contamination survey (Ground investigation)", "lsum", 1, 92000.00, {"nrm": "0.4"}),
                ("0.5", "Remediation of contaminated made ground (Remediation)", "m3", 3200, 48.00, {"nrm": "0.5"}),
                ("0.6", "Temporary works - propping to retained party walls (Temporary works)", "lsum", 1, 285000.00, {"nrm": "0.6"}),
                ("0.7", "Archaeological watching brief, City of London (Archaeology)", "lsum", 1, 78000.00, {"nrm": "0.3"}),
                ("0.8", "Diversion of statutory utilities (Utility diversions)", "lsum", 1, 220000.00, {"nrm": "0.7"}),
            ],
        ),
        # -- 1. Substructure --------------------------------------------------
        (
            "1",
            "1 - Substructure",
            {"nrm": "1"},
            [
                ("1.1", "Secant piled retaining wall to basement perimeter (Secant wall)", "m2", 2650, 295.00, {"nrm": "1.1.1"}),
                ("1.2", "Rotary bored bearing piles 900mm dia (Bearing piles)", "m", 3800, 215.00, {"nrm": "1.1.1"}),
                ("1.3", "CFA piles 600mm dia to lift / core (CFA piles)", "m", 1100, 145.00, {"nrm": "1.1.1"}),
                ("1.4", "Pile caps and reinforced-concrete ground beams (Pile caps)", "m3", 980, 360.00, {"nrm": "1.1.1"}),
                ("1.5", "Basement excavation and muck-away off site (Basement dig)", "m3", 16500, 38.00, {"nrm": "1.1.2"}),
                ("1.6", "Reinforced-concrete raft slab 800mm thick (Raft slab)", "m3", 1150, 280.00, {"nrm": "1.1.1"}),
                ("1.7", "Reinforced-concrete basement retaining walls 350mm (Basement walls)", "m2", 2400, 205.00, {"nrm": "1.1.1"}),
                ("1.8", "Type A tanking / waterproofing to basement, BS 8102 (Tanking)", "m2", 5050, 88.00, {"nrm": "1.1.3"}),
                ("1.9", "Groundwater control and dewatering during works (Dewatering)", "lsum", 1, 175000.00, {"nrm": "1.1.2"}),
                ("1.10", "Lift pit and sump construction (Lift pits)", "pcs", 4, 18500.00, {"nrm": "1.1.1"}),
            ],
        ),
        # -- 2.1 Frame --------------------------------------------------------
        (
            "2.1",
            "2.1 - Superstructure: Frame",
            {"nrm": "2.1"},
            [
                ("2.1.1", "Reinforced-concrete columns C40/50 to BS 8500 (RC columns)", "m3", 1450, 425.00, {"nrm": "2.1"}),
                ("2.1.2", "Reinforced-concrete core / shear walls 400mm (RC cores)", "m3", 2200, 395.00, {"nrm": "2.1"}),
                ("2.1.3", "Post-tensioned transfer structure at ground (PT transfer)", "m3", 480, 720.00, {"nrm": "2.1"}),
                ("2.1.4", "Reinforcement to frame, high-yield B500B (Rebar)", "t", 1850, 1450.00, {"nrm": "2.1"}),
                ("2.1.5", "Structural steel to plant screen and canopy (Structural steel)", "t", 165, 3850.00, {"nrm": "2.1"}),
            ],
        ),
        # -- 2.2 Upper Floors -------------------------------------------------
        (
            "2.2",
            "2.2 - Superstructure: Upper Floors",
            {"nrm": "2.2"},
            [
                ("2.2.1", "Reinforced-concrete flat slab 300mm to office floors (RC flat slab)", "m2", 9450, 165.00, {"nrm": "2.2"}),
                ("2.2.2", "Edge upstands, downstands and slab penetrations (Slab edge works)", "m", 2400, 78.00, {"nrm": "2.2"}),
                ("2.2.3", "Permanent formwork and proprietary edge shutters (Formwork)", "m2", 9450, 42.00, {"nrm": "2.2"}),
                ("2.2.4", "Movement joints and bearings to slabs (Movement joints)", "m", 320, 165.00, {"nrm": "2.2"}),
            ],
        ),
        # -- 2.3 Roof ---------------------------------------------------------
        (
            "2.3",
            "2.3 - Superstructure: Roof",
            {"nrm": "2.3"},
            [
                ("2.3.1", "Warm-roof build-up, single-ply membrane, BS 6229 (Roof covering)", "m2", 1100, 145.00, {"nrm": "2.3"}),
                ("2.3.2", "Tapered PIR insulation 220mm to falls (Roof insulation)", "m2", 1100, 58.00, {"nrm": "2.3"}),
                ("2.3.3", "Structural plant deck and steelwork to roof (Plant deck)", "m2", 520, 195.00, {"nrm": "2.3"}),
                ("2.3.4", "Brown / biodiverse green roof to terraces (Green roof)", "m2", 420, 165.00, {"nrm": "2.3"}),
                ("2.3.5", "Roof drainage, outlets and overflow provision (Roof drainage)", "m", 280, 95.00, {"nrm": "2.3"}),
                ("2.3.6", "Mansafe horizontal-life-line edge protection (Edge protection)", "m", 360, 145.00, {"nrm": "2.3"}),
                ("2.3.7", "Photovoltaic array, roof-mounted, circa 90 kWp (PV array)", "m2", 480, 285.00, {"nrm": "2.3"}),
            ],
        ),
        # -- 2.4 Stairs and Ramps --------------------------------------------
        (
            "2.4",
            "2.4 - Superstructure: Stairs and Ramps",
            {"nrm": "2.4"},
            [
                ("2.4.1", "Reinforced-concrete escape stairs to cores (RC stairs)", "m", 220, 1250.00, {"nrm": "2.4"}),
                ("2.4.2", "Feature accommodation stair, steel and glass (Feature stair)", "pcs", 1, 285000.00, {"nrm": "2.4"}),
                ("2.4.3", "Metal stair balustrade and handrail, Part K (Balustrade)", "m", 480, 285.00, {"nrm": "2.4"}),
                ("2.4.4", "Basement vehicle ramp, reinforced concrete (Vehicle ramp)", "m2", 240, 215.00, {"nrm": "2.4"}),
            ],
        ),
        # -- 2.5 External Walls, Windows and Doors ---------------------------
        (
            "2.5",
            "2.5 - Superstructure: External Walls, Windows and Doors",
            {"nrm": "2.5"},
            [
                ("2.5.1", "Unitised aluminium curtain walling, Ucw 1.2 W/m2K (Unitised CWG)", "m2", 8200, 695.00, {"nrm": "2.5"}),
                ("2.5.2", "Double-skin ventilated facade to south elevation (Double-skin facade)", "m2", 1850, 1150.00, {"nrm": "2.5"}),
                ("2.5.3", "Feature entrance glazing, double-height (Entrance glazing)", "m2", 420, 1350.00, {"nrm": "2.5"}),
                ("2.5.4", "Solid spandrel and shadow-box panels (Spandrel panels)", "m2", 1600, 420.00, {"nrm": "2.5"}),
                ("2.5.5", "External brise-soleil and solar shading fins (Solar shading)", "m2", 960, 385.00, {"nrm": "2.5"}),
                ("2.5.6", "Reconstituted-stone rainscreen to base (Rainscreen cladding)", "m2", 740, 465.00, {"nrm": "2.6"}),
                ("2.5.7", "Aluminium louvres to plant and basement intake (Plant louvres)", "m2", 380, 345.00, {"nrm": "2.6"}),
                ("2.5.8", "Automatic revolving entrance doors (Revolving doors)", "pcs", 2, 42000.00, {"nrm": "2.7"}),
                ("2.5.9", "Powered loading-bay and basement roller shutters (Roller shutters)", "pcs", 5, 9800.00, {"nrm": "2.7"}),
                ("2.5.10", "Window-cleaning cradle and BMU track to roof (BMU / cradle)", "lsum", 1, 285000.00, {"nrm": "2.5"}),
            ],
        ),
        # -- 2.6 Internal Walls and Partitions -------------------------------
        (
            "2.6",
            "2.6 - Superstructure: Internal Walls and Partitions",
            {"nrm": "2.7"},
            [
                ("2.6.1", "Reinforced-concrete / blockwork core walls (Core walls)", "m2", 3400, 95.00, {"nrm": "2.7"}),
                ("2.6.2", "Metal-stud drylined partitions to cores, 2-hour FR (Drylining)", "m2", 5200, 72.00, {"nrm": "2.7"}),
                ("2.6.3", "Acoustic / fire-rated WC and shower partitions (WC partitions)", "m2", 1450, 165.00, {"nrm": "2.7"}),
                ("2.6.4", "Fire-rated riser and shaft enclosures, EI120 (Riser walls)", "m2", 1850, 125.00, {"nrm": "2.7"}),
                ("2.6.5", "Internal fire / smoke doorsets, Approved Document B (Internal doorsets)", "pcs", 220, 1450.00, {"nrm": "2.8"}),
                ("2.6.6", "Ironmongery and door hardware to internal doors (Ironmongery)", "pcs", 220, 320.00, {"nrm": "2.8"}),
            ],
        ),
        # -- 3. Internal Finishes --------------------------------------------
        (
            "3",
            "3 - Internal Finishes",
            {"nrm": "3"},
            [
                ("3.1", "Raised access floor 200mm, medium grade (Raised floor)", "m2", 8400, 78.00, {"nrm": "3.2"}),
                ("3.2", "Screeds and levelling to back-of-house slabs (Floor screeds)", "m2", 2200, 32.00, {"nrm": "3.2"}),
                ("3.3", "Natural-stone flooring to reception and lift lobbies (Stone flooring)", "m2", 850, 245.00, {"nrm": "3.2"}),
                ("3.4", "Porcelain tiling to WCs and shower rooms (Tiling)", "m2", 1650, 95.00, {"nrm": "3.1"}),
                ("3.5", "Plaster, skim and decoration to core walls (Wall finishes)", "m2", 6800, 38.00, {"nrm": "3.1"}),
                ("3.6", "Demountable suspended metal-tile ceilings (Suspended ceilings)", "m2", 7600, 62.00, {"nrm": "3.3"}),
                ("3.7", "Exposed soffit treatment to office floors (Exposed soffit)", "m2", 1800, 28.00, {"nrm": "3.3"}),
                ("3.8", "Acoustic feature ceiling rafts to reception (Acoustic rafts)", "m2", 420, 185.00, {"nrm": "3.3"}),
                ("3.9", "Skirtings, architraves and trims (Trims)", "m", 4200, 18.00, {"nrm": "3.1"}),
                ("3.10", "Entrance matting and barrier systems (Entrance matting)", "m2", 120, 220.00, {"nrm": "3.2"}),
            ],
        ),
        # -- 4. Fittings, Furnishings and Equipment --------------------------
        (
            "4",
            "4 - Fittings, Furnishings and Equipment",
            {"nrm": "4"},
            [
                ("4.1", "Reception desk and feature joinery (Reception joinery)", "lsum", 1, 165000.00, {"nrm": "4"}),
                ("4.2", "WC vanity units, IPS panels and cubicles (WC fit-out)", "pcs", 64, 2850.00, {"nrm": "4"}),
                ("4.3", "Tea-point and pantry joinery to each floor (Tea-points)", "pcs", 20, 9500.00, {"nrm": "4"}),
                ("4.4", "Signage, wayfinding and statutory notices (Signage)", "lsum", 1, 95000.00, {"nrm": "4"}),
                ("4.5", "End-of-trip lockers, drying and changing fit-out (End-of-trip)", "lsum", 1, 185000.00, {"nrm": "4"}),
                ("4.6", "Window blinds and solar-control internal screens (Blinds)", "m2", 8200, 42.00, {"nrm": "4"}),
                ("4.7", "Cycle racks and Sheffield stands to basement (Cycle store)", "pcs", 180, 320.00, {"nrm": "4"}),
            ],
        ),
        # -- 5.1 Mechanical Services -----------------------------------------
        (
            "5.1",
            "5.1 - Services: Mechanical, Heating, Cooling and Ventilation",
            {"nrm": "5"},
            [
                ("5.1.1", "Air-source heat pumps, roof plant, all-electric (ASHP plant)", "pcs", 6, 165000.00, {"nrm": "5.7"}),
                ("5.1.2", "Four-pipe fan-coil units to office floors (FCUs)", "pcs", 420, 1850.00, {"nrm": "5.6"}),
                ("5.1.3", "Air-handling units with heat recovery (AHUs)", "pcs", 8, 78000.00, {"nrm": "5.6"}),
                ("5.1.4", "Primary and secondary chilled / LTHW pipework (Pipework)", "m", 6800, 95.00, {"nrm": "5.5"}),
                ("5.1.5", "Galvanised supply and extract ductwork (Ductwork)", "m2", 18500, 78.00, {"nrm": "5.6"}),
                ("5.1.6", "Smoke-ventilation and stair-pressurisation system (Smoke vent)", "lsum", 1, 420000.00, {"nrm": "5.6"}),
                ("5.1.7", "Thermal insulation and acoustic lagging (Insulation / lagging)", "m", 6800, 28.00, {"nrm": "5.5"}),
                ("5.1.8", "Builders-work-in-connection, mechanical (Mech BWIC)", "lsum", 1, 185000.00, {"nrm": "5.6"}),
            ],
        ),
        # -- 5.2 Public Health and Fire Services -----------------------------
        (
            "5.2",
            "5.2 - Services: Public Health and Fire Protection",
            {"nrm": "5"},
            [
                ("5.2.1", "Hot and cold water services and risers (Water services)", "m", 4200, 65.00, {"nrm": "5.3"}),
                ("5.2.2", "Above-ground soil, waste and vent drainage (SWV drainage)", "m", 3600, 72.00, {"nrm": "5.2"}),
                ("5.2.3", "Sanitaryware, taps and WC fittings (Sanitaryware)", "pcs", 210, 950.00, {"nrm": "5.3"}),
                ("5.2.4", "Rainwater harvesting and grey-water plant (RWH plant)", "lsum", 1, 145000.00, {"nrm": "5.3"}),
                ("5.2.5", "Sprinkler installation throughout, BS EN 12845 (Sprinklers)", "m2", 10500, 38.00, {"nrm": "5.13"}),
                ("5.2.6", "Dry / wet fire-fighting risers and outlets (Fire mains)", "pcs", 12, 8500.00, {"nrm": "5.13"}),
                ("5.2.7", "Basement sump and foul-water pumping stations (PH pumps)", "pcs", 4, 18500.00, {"nrm": "5.2"}),
            ],
        ),
        # -- 5.3 Electrical and Lift Services --------------------------------
        (
            "5.3",
            "5.3 - Services: Electrical, Lifts and Communications",
            {"nrm": "5"},
            [
                ("5.3.1", "LV switchgear, main panels and sub-mains (LV distribution)", "lsum", 1, 685000.00, {"nrm": "5.8"}),
                ("5.3.2", "Standby generator and UPS to life-safety loads (Generator / UPS)", "pcs", 2, 165000.00, {"nrm": "5.8"}),
                ("5.3.3", "Small power, containment and floor boxes (Small power)", "m2", 8400, 48.00, {"nrm": "5.8"}),
                ("5.3.4", "LED lighting and DALI controls, BS EN 12464 (Lighting)", "m2", 10500, 72.00, {"nrm": "5.9"}),
                ("5.3.5", "Fire detection and alarm, BS 5839, L1 (Fire alarm)", "m2", 10500, 32.00, {"nrm": "5.12"}),
                ("5.3.6", "Passenger lifts 21-person, MRL, regen drive (Passenger lifts)", "pcs", 6, 195000.00, {"nrm": "5.11"}),
                ("5.3.7", "Goods / firefighting lift, EN 81-72 (Firefighting lift)", "pcs", 1, 245000.00, {"nrm": "5.11"}),
                ("5.3.8", "Structured cabling, IT and AV containment (ICT containment)", "m2", 8400, 28.00, {"nrm": "5.10"}),
                ("5.3.9", "Security, access control and CCTV (Security systems)", "lsum", 1, 285000.00, {"nrm": "5.10"}),
                ("5.3.10", "Building management system and metering, Part L (BMS)", "lsum", 1, 520000.00, {"nrm": "5.14"}),
                ("5.3.11", "EV-charging infrastructure to basement bays (EV charging)", "pcs", 24, 4800.00, {"nrm": "5.8"}),
                ("5.3.12", "Lightning protection and earthing, BS EN 62305 (LPS / earthing)", "lsum", 1, 95000.00, {"nrm": "5.8"}),
            ],
        ),
        # -- 6. External Works ------------------------------------------------
        (
            "6",
            "6 - External Works",
            {"nrm": "8"},
            [
                ("6.1", "Hard landscaping, York-stone paving to public realm (Hard landscaping)", "m2", 1850, 185.00, {"nrm": "8.2"}),
                ("6.2", "Soft landscaping, street trees and planting (Soft landscaping)", "m2", 620, 95.00, {"nrm": "8.3"}),
                ("6.3", "Below-ground foul and surface-water drainage (External drainage)", "m", 480, 165.00, {"nrm": "8.6"}),
                ("6.4", "Sustainable drainage attenuation tanks, SuDS (SuDS)", "m3", 220, 420.00, {"nrm": "8.6"}),
                ("6.5", "Incoming statutory mains connections (Utility connections)", "lsum", 1, 320000.00, {"nrm": "8.7"}),
                ("6.6", "External lighting and public-realm power (External lighting)", "pcs", 32, 2650.00, {"nrm": "8.5"}),
                ("6.7", "Boundary treatments, bollards and street furniture (Site furniture)", "lsum", 1, 145000.00, {"nrm": "8.4"}),
            ],
        ),
        # -- 8. Risk and Project / Design Team Fees --------------------------
        (
            "8",
            "8 - Risk Allowances and Project / Design Fees",
            {"nrm": "8"},
            [
                ("8.1", "Design-development risk allowance (Design risk)", "lsum", 1, 850000.00, {"nrm": "11.2"}),
                ("8.2", "Construction risk allowance (Construction risk)", "lsum", 1, 620000.00, {"nrm": "11.3"}),
                ("8.3", "Building Safety Act 2022 compliance and BSR Gateways (BSA compliance)", "lsum", 1, 285000.00, {"nrm": "11.2"}),
                ("8.4", "Professional and design-team fees (Design fees)", "lsum", 1, 2950000.00, {"nrm": "12"}),
                ("8.5", "CDM 2015 principal-designer duties (CDM duties)", "lsum", 1, 165000.00, {"nrm": "12"}),
                ("8.6", "Statutory and local-authority fees (Statutory fees)", "lsum", 1, 220000.00, {"nrm": "13"}),
            ],
        ),
    ],
    markups=[
        ("Main Contractor's Preliminaries", 13.0, "overhead", "direct_cost"),
        ("Main Contractor's Overheads & Profit (OH&P)", 6.0, "profit", "direct_cost"),
        ("Contingency / Risk Allowance", 4.0, "contingency", "cumulative"),
        ("VAT", 20.0, "tax", "cumulative"),
    ],
    total_months=30,
    tender_name="Main Contract - JCT Design and Build 2024 (Two-Stage)",
    tender_companies=[
        ("Mace Group", "tenders@macegroup.co.uk", 0.98),
        ("Multiplex Construction Europe", "bids@multiplex.co.uk", 1.06),
        ("Sir Robert McAlpine", "estimating@srm.co.uk", 1.02),
    ],
    project_metadata={
        "address": "1 Aldgate High Street, London EC3N 1AH",
        "client": "Aldgate Place Developments LLP",
        "developer": "City Quarter Estates Ltd",
        "architect": "PLP Architecture",
        "quantity_surveyor": "Gardiner & Theobald LLP",
        "structural_engineer": "AKT II",
        "mep_engineer": "Hoare Lea",
        "building_type": "Grade A commercial office (speculative)",
        "gia_m2": 10500,
        "nia_m2": 8400,
        "typical_floorplate_m2": 1050,
        "storeys": 10,
        "basement_levels": 1,
        "measurement_standard": "RICS NRM 2 (detailed) / NRM 1 (elemental groups) / NRM 3 (maintenance)",
        "cost_data": "UK construction cost index (London 2026)",
        "structural_standards": "Eurocodes BS EN 1990-1998, BS 8500 (concrete), BS 8102 (tanking)",
        "building_regulations": "Building Regulations Approved Documents A-S",
        "building_safety": "Building Safety Act 2022 - higher-risk building, BSR Gateways 1-3, golden thread",
        "health_and_safety": "CDM 2015 (Construction Design and Management Regulations)",
        "fire_strategy": "Approved Document B; BS 9999; sprinklers to BS EN 12845",
        "contract": "JCT Design and Build 2024 (two-stage)",
        "procurement": "Two-stage design and build, GMP at Stage 2",
        "sustainability_target": "BREEAM Outstanding; NABERS UK 5-star; Net Zero Carbon in operation aspiration",
        "epc_target": "EPC A (MEES compliant)",
        "tax_note": "All rates VAT exclusive; VAT 20% applied as a separate final markup",
    },
    tender_packages=[
        (
            "Main Contract - Design and Build (JCT 2024)",
            "Two-stage design-and-build delivery, GMP confirmed at Stage 2",
            "evaluating",
            [
                ("Mace Group", "tenders@macegroup.co.uk", 0.98),
                ("Multiplex Construction Europe", "bids@multiplex.co.uk", 1.06),
                ("Sir Robert McAlpine", "estimating@srm.co.uk", 1.02),
            ],
        ),
        (
            "Substructure & Concrete Frame",
            "Piling, basement, reinforced-concrete flat-slab frame and cores",
            "evaluating",
            [
                ("Byrne Bros (Formwork)", "tenders@byrnebrosformwork.co.uk", 0.97),
                ("Expanded Ltd (Laing O'Rourke)", "estimating@expanded.co.uk", 1.05),
                ("PC Harrington Contractors", "bids@pcharrington.co.uk", 1.01),
            ],
        ),
        (
            "Facade - Unitised Curtain Walling",
            "Unitised aluminium CWG, double-skin facade and entrance glazing",
            "evaluating",
            [
                ("Permasteelisa UK", "tenders@permasteelisa.co.uk", 0.99),
                ("Schmidlin (FaceUK)", "estimating@faceuk.co.uk", 1.04),
                ("Yuanda UK", "bids@yuanda.co.uk", 1.02),
            ],
        ),
        (
            "Mechanical, Electrical & Public Health (MEP)",
            "All-electric HVAC, electrical, public-health and BMS services",
            "evaluating",
            [
                ("NG Bailey", "tenders@ngbailey.co.uk", 0.98),
                ("SES Engineering Services", "estimating@ses-ltd.co.uk", 1.05),
                ("Imtech Engineering Services", "bids@imtech.co.uk", 1.03),
            ],
        ),
        (
            "Vertical Transportation (Lifts)",
            "Passenger, goods and firefighting lift installations",
            "evaluating",
            [
                ("KONE UK", "tenders@kone.co.uk", 0.99),
                ("Schindler UK", "estimating@schindler.co.uk", 1.04),
                ("Otis UK", "bids@otis.co.uk", 1.02),
            ],
        ),
    ],
)
