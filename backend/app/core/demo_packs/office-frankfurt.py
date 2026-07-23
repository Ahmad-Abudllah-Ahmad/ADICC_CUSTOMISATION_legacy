# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
from __future__ import annotations

from app.core.demo_projects import DemoTemplate

# ---------------------------------------------------------------------------
# Partner-pack demo: BIM-coordinated office building Frankfurt am Main (Hessen)
# Pack: bimhessen-de  ·  DIN 276:2018-12 cost calculation (HOAI LP3)
# ---------------------------------------------------------------------------

TEMPLATE = DemoTemplate(
    demo_id="office-frankfurt",
    project_name="Buerogebaeude Frankfurt Europaviertel",
    project_description=(
        "Neubau eines BIM-koordinierten Buero- und Geschaeftshauses im "
        "Europaviertel Frankfurt am Main. 8 Obergeschosse + Staffelgeschoss, "
        "2 Untergeschosse Tiefgarage mit 140 Stellplaetzen. "
        "BGF ca. 14.000 m2, BRI ca. 56.000 m3, ca. 9.800 m2 Mietflaeche (MF/G). "
        "Tragwerk: Stahlbeton-Skelettbau (RC frame) mit Flachdecken auf Stuetzenraster "
        "8,10 x 8,10 m, Aussteifung ueber Treppen-/Aufzugskerne. "
        "Gebaeudehuelle: Elementfassade / Pfosten-Riegel-Vorhangfassade (curtain wall) "
        "mit Dreifach-Isolierverglasung und aussenliegendem Sonnenschutz. "
        "Energiestandard GEG / KfW Effizienzgebaeude 40 (NWG), DGNB Gold angestrebt. "
        "Planung und Ausfuehrung als BIM-Projekt nach ISO 19650 (BAP/AIA). "
        "Baukosten KG 300+400 ca. 44 Mio EUR (Kostenberechnung HOAI LP3)."
    ),
    region="DACH",
    classification_standard="din276",
    currency="EUR",
    locale="de",
    address={
        "street": "Europa-Allee 90",
        "city": "Frankfurt am Main",
        "postcode": "60486",
        "country": "Germany",
        "lat": 50.1075,
        "lng": 8.6385,
    },
    validation_rule_sets=["din276", "gaeb", "boq_quality"],
    boq_name="Kostenberechnung nach DIN 276 (HOAI LP3)",
    boq_description=(
        "Detaillierte Kostenberechnung gem. DIN 276:2018-12, "
        "Schwerpunkt KG 300 Bauwerk-Baukonstruktionen und KG 400 "
        "Bauwerk-Technische Anlagen, zzgl. KG 500 Aussenanlagen. "
        "Mengenermittlung modellbasiert aus BIM-Koordinationsmodell (ISO 19650)."
    ),
    boq_metadata={
        "standard": "DIN 276:2018-12",
        "phase": "Kostenberechnung (HOAI LP3)",
        "base_date": "2026-Q1",
        "price_level": "Frankfurt/Hessen 2026",
    },
    sections=[
        # ── KG 310 Baugrube / Erdbau ─────────────────────────────────
        (
            "310",
            "KG 310 - Baugrube / Erdbau",
            {"din276": "310"},
            [
                ("310.1", "Baugrundgutachten + Baugrunderkundung (Geotechnical survey)", "lsum", 1, 42000.00, {"din276": "311"}),
                ("310.2", "Kampfmittelsondierung Grundstueck (UXO survey)", "m2", 4200, 4.20, {"din276": "311"}),
                ("310.3", "Bohrpfahlwand verankert d=900mm (Secant pile wall)", "m2", 4800, 215.00, {"din276": "312"}),
                ("310.4", "Verpressanker temporaer (Temporary ground anchors)", "pcs", 220, 1450.00, {"din276": "312"}),
                ("310.5", "Aushub Baugrube Klasse 3-5 (Pit excavation)", "m3", 78000, 16.50, {"din276": "313"}),
                ("310.6", "Bodenabtransport + Deponie Z1.1/Z2 (Soil disposal)", "m3", 72000, 28.00, {"din276": "313"}),
                ("310.7", "Grundwasserhaltung offene Wasserhaltung (Dewatering)", "month", 14, 18500.00, {"din276": "314"}),
                ("310.8", "Sohlabdichtung Unterwasserbeton (Underwater concrete plug)", "m3", 1200, 165.00, {"din276": "314"}),
                ("310.9", "Verdichtung + Planum Baugrubensohle (Compaction/formation)", "m2", 3600, 5.80, {"din276": "313"}),
                ("310.10", "Baustrasse + Andienung Schottertragschicht (Haul road)", "m2", 1400, 32.00, {"din276": "319"}),
            ],
        ),
        # ── KG 320 Gruendung, Unterbau ───────────────────────────────
        (
            "320",
            "KG 320 - Gruendung, Unterbau",
            {"din276": "320"},
            [
                ("320.1", "Sauberkeitsschicht C12/15 (Blinding concrete)", "m2", 3600, 13.50, {"din276": "322"}),
                ("320.2", "Bodenplatte WU-Beton C30/37 XC4, d=80cm (WU foundation raft)", "m3", 2880, 215.00, {"din276": "324"}),
                ("320.3", "Bewehrung Bodenplatte BSt 500 (Raft reinforcement)", "t", 360, 1620.00, {"din276": "324"}),
                ("320.4", "Pfahlgruendung Bohrpfaehle d=900mm, L=18m (Bored piles)", "m", 3240, 185.00, {"din276": "322"}),
                ("320.5", "Fugenbleche + Quellband WU-Konzept (Waterstops/joint sheets)", "m", 1800, 38.00, {"din276": "324"}),
                ("320.6", "Aufzugsunterfahrt / Pumpensumpf (Lift pit / sump)", "pcs", 4, 8500.00, {"din276": "324"}),
                ("320.7", "Drainage + Ringdrainage DN200 (Perimeter drainage)", "m", 360, 72.00, {"din276": "326"}),
                ("320.8", "Bodenplatten-Beschichtung Tiefgarage OS8 (TG floor coating)", "m2", 6400, 28.00, {"din276": "325"}),
            ],
        ),
        # ── KG 330 Aussenwaende / Vertikale Baukonstruktionen ────────
        (
            "330",
            "KG 330 - Aussenwaende / vertikale Baukonstruktionen, aussen",
            {"din276": "330"},
            [
                ("330.1", "Kelleraussenwand WU-Beton C30/37, d=40cm (Basement RC wall)", "m3", 1180, 245.00, {"din276": "331"}),
                ("330.2", "Schalung Aussenwaende Rahmenschalung (Wall formwork)", "m2", 8400, 38.00, {"din276": "331"}),
                ("330.3", "Bewehrung Aussenwaende BSt 500 (Wall reinforcement)", "t", 142, 1680.00, {"din276": "331"}),
                ("330.4", "Stahlbetonstuetzen C45/55, Rundstuetzen (RC columns)", "m3", 460, 420.00, {"din276": "331"}),
                ("330.5", "Perimeterdaemmung XPS 160mm erdberuehrt (Perimeter insulation)", "m2", 3800, 52.00, {"din276": "335"}),
                ("330.6", "Bauwerksabdichtung KMB erdberuehrt (Below-grade waterproofing)", "m2", 3800, 46.00, {"din276": "335"}),
                ("330.7", "Elementfassade Aluminium 3-fach-Verglasung Uw 0,9 (Unitised curtain wall)", "m2", 7200, 720.00, {"din276": "337"}),
                ("330.8", "Pfosten-Riegel-Fassade Eingangshalle (Stick curtain wall lobby)", "m2", 640, 580.00, {"din276": "337"}),
                ("330.9", "Aussenliegender Sonnenschutz Raffstore motorisiert (External venetian blinds)", "m2", 6800, 165.00, {"din276": "338"}),
                ("330.10", "Oeffnungsfluegel / Parallelausstellfenster (Opening vents/PAF)", "pcs", 280, 1450.00, {"din276": "337"}),
                ("330.11", "Festverglasung Brandschutz F30 Atrium (Fire-rated glazing)", "m2", 320, 480.00, {"din276": "337"}),
                ("330.12", "Aussentueren Aluminium Eingang (Aluminium entrance doors)", "pcs", 6, 6800.00, {"din276": "334"}),
                ("330.13", "Fassadenbefahranlage Anschlagpunkte (Facade access anchors)", "lsum", 1, 38000.00, {"din276": "338"}),
            ],
        ),
        # ── KG 340 Innenwaende / Vertikale Baukonstruktionen, innen ──
        (
            "340",
            "KG 340 - Innenwaende / vertikale Baukonstruktionen, innen",
            {"din276": "340"},
            [
                ("340.1", "Stahlbetonkerne C35/45 Treppen/Aufzug (RC cores)", "m3", 1240, 395.00, {"din276": "341"}),
                ("340.2", "Schalung Kerne Kletterschalung (Core climbing formwork)", "m2", 7200, 44.00, {"din276": "341"}),
                ("340.3", "Bewehrung Kerne BSt 500 (Core reinforcement)", "t", 168, 1680.00, {"din276": "341"}),
                ("340.4", "Trennwand Trockenbau doppelt beplankt CW100 (Drywall partition)", "m2", 9600, 58.00, {"din276": "342"}),
                ("340.5", "Brandwand F90 Trockenbau (Fire wall F90)", "m2", 2400, 135.00, {"din276": "342"}),
                ("340.6", "Systemtrennwand verglast Buero (Glazed office partition)", "m2", 3200, 285.00, {"din276": "342"}),
                ("340.7", "Schachtwaende Installationsschaechte F90 (Shaft walls F90)", "m2", 1800, 92.00, {"din276": "342"}),
                ("340.8", "Innentueren Holz / Stahlzargen (Internal doors/frames)", "pcs", 420, 720.00, {"din276": "344"}),
                ("340.9", "Brandschutztueren T30/T90 (Fire doors T30/T90)", "pcs", 96, 1450.00, {"din276": "344"}),
                ("340.10", "WC-Trennwandsysteme HPL (Sanitary cubicles)", "pcs", 64, 980.00, {"din276": "346"}),
                ("340.11", "Wandbeschichtung / Dispersion innen (Internal wall coating)", "m2", 22000, 9.50, {"din276": "345"}),
                ("340.12", "Wandfliesen Sanitaerbereiche (Wall tiling wet areas)", "m2", 2200, 62.00, {"din276": "345"}),
            ],
        ),
        # ── KG 350 Decken / Horizontale Baukonstruktionen ────────────
        (
            "350",
            "KG 350 - Decken / horizontale Baukonstruktionen",
            {"din276": "350"},
            [
                ("350.1", "Stahlbeton-Flachdecke C30/37, d=32cm (RC flat slab)", "m3", 4480, 335.00, {"din276": "351"}),
                ("350.2", "Schalung Decken Deckentische (Slab formwork)", "m2", 14000, 32.00, {"din276": "351"}),
                ("350.3", "Bewehrung Decken BSt 500 (Slab reinforcement)", "t", 520, 1680.00, {"din276": "351"}),
                ("350.4", "Durchstanzbewehrung Stuetzenkopf (Punching shear reinforcement)", "pcs", 280, 320.00, {"din276": "351"}),
                ("350.5", "Hohlraumboden / Doppelboden Bueroflaechen (Raised access floor)", "m2", 8800, 78.00, {"din276": "352"}),
                ("350.6", "Zementestrich CT-C25-F4 Nebenflaechen (Cement screed)", "m2", 3200, 28.00, {"din276": "352"}),
                ("350.7", "Trittschalldaemmung MW-T 30mm (Impact sound insulation)", "m2", 11000, 14.50, {"din276": "352"}),
                ("350.8", "Bodenbelag Teppichfliese Buero (Carpet tile flooring)", "m2", 7600, 42.00, {"din276": "352"}),
                ("350.9", "Bodenbelag Naturwerkstein Eingangshalle (Stone flooring lobby)", "m2", 680, 185.00, {"din276": "352"}),
                ("350.10", "Bodenbelag Feinsteinzeug Nebenflaechen (Porcelain tiling)", "m2", 2400, 68.00, {"din276": "352"}),
                ("350.11", "Akustik-Metalldecke Kassetten abgehaengt (Acoustic metal ceiling)", "m2", 9200, 88.00, {"din276": "353"}),
                ("350.12", "Gipskarton-Unterdecke F30/F90 (Plasterboard ceiling)", "m2", 3600, 52.00, {"din276": "353"}),
                ("350.13", "Sockelleisten Aluminium (Aluminium skirting)", "m", 6400, 11.50, {"din276": "352"}),
            ],
        ),
        # ── KG 360 Daecher ───────────────────────────────────────────
        (
            "360",
            "KG 360 - Daecher",
            {"din276": "360"},
            [
                ("360.1", "Stahlbeton-Dachdecke C30/37, d=30cm (RC roof slab)", "m3", 540, 345.00, {"din276": "361"}),
                ("360.2", "Gefaelledaemmung PIR 220-300mm (Tapered roof insulation)", "m2", 1900, 78.00, {"din276": "363"}),
                ("360.3", "Dachabdichtung FPO/TPO 2-lagig (TPO roof membrane)", "m2", 1900, 56.00, {"din276": "363"}),
                ("360.4", "Extensivbegruenung Substrat + Vegetation (Extensive green roof)", "m2", 1100, 62.00, {"din276": "363"}),
                ("360.5", "Dachrandabschluss / Attikaabdeckung Alu (Parapet capping)", "m", 420, 68.00, {"din276": "362"}),
                ("360.6", "Absturzsicherung Sekuranten + Gelaender (Fall protection)", "m", 420, 145.00, {"din276": "362"}),
                ("360.7", "Lichtkuppeln / RWA Treppenhaeuser (Rooflights / smoke vents)", "pcs", 6, 4800.00, {"din276": "362"}),
                ("360.8", "Dachdurchfuehrungen + Entlueftung (Roof penetrations)", "pcs", 48, 320.00, {"din276": "362"}),
                ("360.9", "PV-Anlage Aufdach 180 kWp (Rooftop PV system)", "lsum", 1, 245000.00, {"din276": "362"}),
            ],
        ),
        # ── KG 370 Infrastrukturanlagen / sonst. Baukonstruktionen ───
        (
            "370",
            "KG 370 - Baukonstruktive Einbauten",
            {"din276": "370"},
            [
                ("370.1", "Stahlbeton-Fertigteiltreppen (RC precast stairs)", "pcs", 36, 5200.00, {"din276": "379"}),
                ("370.2", "Treppengelaender Edelstahl + Glas (Stainless/glass balustrade)", "m", 540, 295.00, {"din276": "379"}),
                ("370.3", "Empfangstresen / Lobby-Einbau (Reception desk fit-out)", "lsum", 1, 68000.00, {"din276": "371"}),
                ("370.4", "Teekuechen / Pantry-Module je Geschoss (Tea kitchen modules)", "pcs", 18, 8500.00, {"din276": "371"}),
                ("370.5", "Sanitaer-Trennwandanlagen + Spiegel (Sanitary fit-out)", "lsum", 1, 42000.00, {"din276": "371"}),
                ("370.6", "Beschilderung / Leitsystem (Signage / wayfinding)", "lsum", 1, 38000.00, {"din276": "374"}),
            ],
        ),
        # ── KG 390 Sonstige Massnahmen Baukonstruktionen ─────────────
        (
            "390",
            "KG 390 - Sonstige Massnahmen fuer Baukonstruktionen",
            {"din276": "390"},
            [
                ("390.1", "Baustelleneinrichtung Grossbaustelle (Site setup/establishment)", "lsum", 1, 420000.00, {"din276": "391"}),
                ("390.2", "Turmdrehkran inkl. Vorhaltung (Tower crane provision)", "month", 16, 16500.00, {"din276": "392"}),
                ("390.3", "Geruest Fassade Standgeruest (Facade scaffolding)", "m2", 9800, 18.50, {"din276": "392"}),
                ("390.4", "Baureinigung + Schlussreinigung (Builders clean)", "m2", 14000, 6.50, {"din276": "395"}),
                ("390.5", "Winterbaumassnahmen (Winter construction measures)", "lsum", 1, 65000.00, {"din276": "394"}),
            ],
        ),
        # ── KG 410 Abwasser, Wasser, Gas ─────────────────────────────
        (
            "410",
            "KG 410 - Abwasser-, Wasser-, Gasanlagen",
            {"din276": "410"},
            [
                ("410.1", "Grundleitungen SML/PE DN100-DN200 (Below-ground drainage)", "m", 1600, 58.00, {"din276": "411"}),
                ("410.2", "Schmutz-/Regenwasserleitung Steigstraenge (Soil/rainwater stacks)", "m", 2400, 46.00, {"din276": "411"}),
                ("410.3", "Hebeanlage Tiefgarage (Sewage pump station)", "pcs", 4, 8800.00, {"din276": "411"}),
                ("410.4", "Trinkwasserinstallation PE-Xc/Edelstahl (Domestic water installation)", "m", 4800, 42.00, {"din276": "412"}),
                ("410.5", "Trinkwassererwaermung Frischwasserstation (DHW station)", "pcs", 9, 6800.00, {"din276": "412"}),
                ("410.6", "Sanitaerobjekte WC/Waschtisch komplett (Sanitary fixtures)", "pcs", 220, 1250.00, {"din276": "412"}),
                ("410.7", "Regenwassernutzung Zisterne + Pumpe (Rainwater harvesting)", "lsum", 1, 38000.00, {"din276": "419"}),
                ("410.8", "Daemmung Rohrleitungen EnEV/GEG (Pipe insulation)", "m", 4800, 14.50, {"din276": "419"}),
            ],
        ),
        # ── KG 420 Waermeversorgungsanlagen ──────────────────────────
        (
            "420",
            "KG 420 - Waermeversorgungsanlagen",
            {"din276": "420"},
            [
                ("420.1", "Fernwaerme-Uebergabestation 900 kW (District heating substation)", "pcs", 1, 92000.00, {"din276": "421"}),
                ("420.2", "Luft-Wasser-Waermepumpe Kaskade 240 kW (ASHP cascade)", "lsum", 1, 185000.00, {"din276": "421"}),
                ("420.3", "Pufferspeicher 2000 L (Buffer storage tanks)", "pcs", 3, 6800.00, {"din276": "421"}),
                ("420.4", "Heizungsverteiler + Pumpengruppen (Manifolds/pump sets)", "lsum", 1, 78000.00, {"din276": "422"}),
                ("420.5", "Heizungssteigleitungen Stahl gedaemmt (Insulated heating risers)", "m", 3200, 38.00, {"din276": "422"}),
                ("420.6", "Statische Heizflaechen / Konvektoren (Radiators/convectors)", "pcs", 180, 420.00, {"din276": "423"}),
                ("420.7", "Betonkernaktivierung BKT Rohrregister (Concrete core activation)", "m2", 8800, 38.00, {"din276": "423"}),
            ],
        ),
        # ── KG 430 Raumlufttechnische Anlagen ────────────────────────
        (
            "430",
            "KG 430 - Raumlufttechnische Anlagen",
            {"din276": "430"},
            [
                ("430.1", "RLT-Zentralgeraet mit WRG 60.000 m3/h (AHU with heat recovery)", "pcs", 4, 92000.00, {"din276": "431"}),
                ("430.2", "Luftkanaele verzinkt Hauptverteilung (Galvanised ductwork)", "m2", 9200, 78.00, {"din276": "431"}),
                ("430.3", "Volumenstromregler VVS (VAV terminal units)", "pcs", 420, 480.00, {"din276": "431"}),
                ("430.4", "Brandschutzklappen EI90 (Fire dampers)", "pcs", 320, 285.00, {"din276": "431"}),
                ("430.5", "Luftauslaesse Drall-/Schlitzauslaesse (Air diffusers/grilles)", "pcs", 1600, 95.00, {"din276": "431"}),
                ("430.6", "Schalldaempfer Kulissenschalldaempfer (Duct silencers)", "pcs", 160, 320.00, {"din276": "431"}),
                ("430.7", "Tiefgaragenentlueftung CO-gesteuert (Garage ventilation)", "lsum", 1, 95000.00, {"din276": "434"}),
                ("430.8", "Kueche-/Sonderabluft Edelstahl (Kitchen/special extract)", "lsum", 1, 42000.00, {"din276": "434"}),
            ],
        ),
        # ── KG 440 Elektrische Anlagen ───────────────────────────────
        (
            "440",
            "KG 440 - Elektrische Anlagen, Starkstrom",
            {"din276": "440"},
            [
                ("440.1", "Mittelspannungsuebergabe + Trafostation 2x1000 kVA (MV/transformer station)", "lsum", 1, 285000.00, {"din276": "441"}),
                ("440.2", "Niederspannungshauptverteilung NSHV (Main LV switchboard)", "pcs", 2, 48000.00, {"din276": "443"}),
                ("440.3", "Unterverteilungen je Geschoss (Sub-distribution boards)", "pcs", 22, 5800.00, {"din276": "443"}),
                ("440.4", "Netzersatzanlage Diesel-NEA 400 kVA (Standby generator)", "pcs", 1, 145000.00, {"din276": "442"}),
                ("440.5", "USV-Anlage Sicherheitsverbraucher (UPS for safety loads)", "pcs", 2, 38000.00, {"din276": "442"}),
                ("440.6", "Kabeltrassen + Bus-Schienen Verteilung (Cable trays / busbars)", "m", 6800, 38.00, {"din276": "444"}),
                ("440.7", "Installationsleitungen NYM/Funktionserhalt (Wiring / fire-rated cable)", "m", 96000, 4.20, {"din276": "444"}),
                ("440.8", "Allgemeinbeleuchtung LED DALI (LED lighting, DALI)", "m2", 11000, 58.00, {"din276": "445"}),
                ("440.9", "Sicherheitsbeleuchtung Zentralbatterie (Emergency lighting CBS)", "lsum", 1, 88000.00, {"din276": "445"}),
                ("440.10", "Blitzschutz + Erdung aeusserer/innerer (Lightning protection/earthing)", "lsum", 1, 92000.00, {"din276": "446"}),
                ("440.11", "E-Ladeinfrastruktur Tiefgarage 11/22 kW (EV charging infrastructure)", "pcs", 70, 2400.00, {"din276": "442"}),
            ],
        ),
        # ── KG 450 Kommunikations-/sicherheitstechnische Anlagen ─────
        (
            "450",
            "KG 450 - Kommunikations-, sicherheits- u. informationstechn. Anlagen",
            {"din276": "450"},
            [
                ("450.1", "Strukturierte Verkabelung Cat.7 / LWL (Structured cabling)", "m2", 11000, 32.00, {"din276": "456"}),
                ("450.2", "Brandmeldeanlage BMA VdS Kat. 1 (Fire alarm system)", "m2", 14000, 14.50, {"din276": "454"}),
                ("450.3", "Sprachalarmierung SAA / ELA (Voice alarm / PA)", "lsum", 1, 78000.00, {"din276": "454"}),
                ("450.4", "Zutrittskontrolle + Schliessanlage (Access control system)", "pcs", 180, 680.00, {"din276": "453"}),
                ("450.5", "Videoueberwachung VSS / CCTV (Video surveillance)", "pcs", 96, 980.00, {"din276": "452"}),
                ("450.6", "Einbruchmeldeanlage EMA (Intruder alarm)", "lsum", 1, 42000.00, {"din276": "452"}),
            ],
        ),
        # ── KG 460 Foerderanlagen ────────────────────────────────────
        (
            "460",
            "KG 460 - Foerderanlagen",
            {"din276": "460"},
            [
                ("460.1", "Personenaufzug 1600 kg / 21 Pers., 11 Haltestellen (Passenger lift)", "pcs", 4, 165000.00, {"din276": "461"}),
                ("460.2", "Lasten-/Feuerwehraufzug 2000 kg (Goods/firefighter lift)", "pcs", 2, 215000.00, {"din276": "461"}),
                ("460.3", "Fassadenbefahranlage Dach-BMU (Building maintenance unit)", "pcs", 1, 185000.00, {"din276": "462"}),
            ],
        ),
        # ── KG 480 Gebaeude- und Anlagenautomation ───────────────────
        (
            "480",
            "KG 480 - Gebaeudeautomation (GA/MSR)",
            {"din276": "480"},
            [
                ("480.1", "GLT Managementebene + Server (BMS management/server)", "lsum", 1, 165000.00, {"din276": "481"}),
                ("480.2", "DDC-Automationsstationen (DDC controllers)", "pcs", 48, 4200.00, {"din276": "482"}),
                ("480.3", "Feldgeraete / Sensorik / Aktorik (Field devices/sensors)", "lsum", 1, 285000.00, {"din276": "483"}),
                ("480.4", "Raumautomation Buero KNX (Room automation, KNX)", "m2", 9800, 22.00, {"din276": "484"}),
                ("480.5", "Inbetriebnahme + GA-Funktionspruefung (Commissioning)", "lsum", 1, 88000.00, {"din276": "485"}),
            ],
        ),
        # ── KG 500 Aussenanlagen und Freiflaechen ────────────────────
        (
            "500",
            "KG 500 - Aussenanlagen und Freiflaechen",
            {"din276": "500"},
            [
                ("500.1", "Erdarbeiten Aussenanlagen / Oberboden (Earthworks external)", "m3", 2200, 22.00, {"din276": "510"}),
                ("500.2", "Tiefgaragenrampe Beton + Heizung (Garage ramp, heated)", "m2", 220, 245.00, {"din276": "520"}),
                ("500.3", "Verkehrsflaechen Asphalt + Pflaster (Paving asphalt/blocks)", "m2", 2400, 78.00, {"din276": "520"}),
                ("500.4", "Plattenbelag Naturstein Vorplatz (Stone paving forecourt)", "m2", 1200, 165.00, {"din276": "520"}),
                ("500.5", "Baumpflanzung + Pflanzbeete (Trees/planting beds)", "pcs", 42, 1850.00, {"din276": "530"}),
                ("500.6", "Rasen-/Staudenflaechen (Lawn/perennial planting)", "m2", 1800, 32.00, {"din276": "530"}),
                ("500.7", "Aussenkanalisation + Anschluss (External drainage/connections)", "m", 320, 145.00, {"din276": "541"}),
                ("500.8", "Versorgungsanschluesse MS/Wasser/FW (Utility connections)", "lsum", 1, 165000.00, {"din276": "540"}),
                ("500.9", "Aussenbeleuchtung Mastleuchten + Poller (External lighting)", "pcs", 38, 1450.00, {"din276": "550"}),
                ("500.10", "Fahrradstellplaetze ueberdacht (Covered bicycle parking)", "pcs", 120, 320.00, {"din276": "560"}),
                ("500.11", "Einfriedung + Tore (Boundary fencing/gates)", "m", 240, 145.00, {"din276": "560"}),
                ("500.12", "Regenrueckhaltung / Versickerung (Stormwater attenuation)", "lsum", 1, 78000.00, {"din276": "541"}),
            ],
        ),
    ],
    markups=[
        ("Baustellengemeinkosten (BGK / site overhead)", 9.0, "overhead", "direct_cost"),
        ("Allgemeine Geschaeftskosten (AGK / general overhead)", 7.0, "overhead", "direct_cost"),
        ("Wagnis (W / risk)", 2.0, "contingency", "direct_cost"),
        ("Gewinn (G / profit)", 4.0, "profit", "direct_cost"),
        ("Mehrwertsteuer (MwSt. / VAT)", 19.0, "tax", "cumulative"),
    ],
    total_months=30,
    tender_name="Rohbau (Structural works)",
    tender_companies=[
        ("Bickhardt Bau Hessen GmbH", "vergabe@bickhardt-bau.de", 0.98),
        ("Wolff & Mueller GmbH & Co. KG", "ausschreibung@wolff-mueller.de", 1.03),
        ("Adolf Lupp GmbH + Co KG", "angebote@lupp.de", 1.01),
    ],
    project_metadata={
        "address": "Europa-Allee 90, 60486 Frankfurt am Main",
        "client": "Europaviertel Projekt GmbH & Co. KG",
        "architect": "schneider+schumacher Architekten, Frankfurt",
        "structural_engineer": "Bollinger+Grohmann Ingenieure",
        "mep_engineer": "ZWP Ingenieur-AG",
        "gfa_m2": 14000,
        "rentable_area_m2": 9800,
        "bri_m3": 56000,
        "storeys_above": 9,
        "storeys_below": 2,
        "parking_spaces": 140,
        "structure_system": "Stahlbeton-Skelettbau / RC frame, flat slabs, core-braced",
        "facade_system": "Elementfassade / unitised curtain wall, triple glazing Uw 0,9",
        "grid_m": "8.10 x 8.10",
        "energy_standard": "GEG / KfW Effizienzgebaeude 40 (NWG)",
        "sustainability_target": "DGNB Gold",
        "bim_standard": "ISO 19650 (BAP/AIA), IFC4 coordination model",
        "design_phase": "HOAI LP3 Entwurfsplanung / Kostenberechnung",
        "applicable_standards": [
            "DIN 276:2018-12",
            "VOB/C (DIN 18299 ff.)",
            "GAEB DA XML 3.3 (X83)",
            "HOAI 2021",
            "ISO 19650-1/-2",
            "GEG 2024",
            "Baukosten-Benchmarks 2025 (Neubau Bueroge.)",
        ],
        "permit_authority": "Bauaufsicht Stadt Frankfurt am Main (HBO 2018)",
        "fire_concept": "Brandschutzkonzept gem. HBO / MIndBauRL, Sonderbau",
        "cost_basis": "Baukosten-Benchmarks Gebaeude Neubau 2025, Regionalfaktor Frankfurt/M.",
    },
    tender_packages=[
        (
            "Rohbau (Structural works)",
            "Baugrube, Verbau, Gruendung, Stahlbeton-Skelettbau, Kerne, Decken",
            "evaluating",
            [
                ("Bickhardt Bau Hessen GmbH", "vergabe@bickhardt-bau.de", 0.98),
                ("Wolff & Mueller GmbH & Co. KG", "ausschreibung@wolff-mueller.de", 1.03),
                ("Adolf Lupp GmbH + Co KG", "angebote@lupp.de", 1.01),
            ],
        ),
        (
            "Fassade (Building envelope)",
            "Elementfassade, Pfosten-Riegel, Sonnenschutz, Dachabdichtung",
            "evaluating",
            [
                ("Lindner Fassaden GmbH", "vergabe@lindner-group.com", 0.97),
                ("Gartner / Permasteelisa Group", "tender@josef-gartner.de", 1.05),
                ("Metallbau Schmees GmbH", "angebote@schmees-metallbau.de", 1.02),
            ],
        ),
        (
            "TGA Heizung/Lueftung/Sanitaer (MEP mechanical)",
            "Fernwaerme, Waermepumpen, BKT, RLT-Anlagen, Sanitaer",
            "evaluating",
            [
                ("Imtech Deutschland GmbH", "vergabe@imtech.de", 0.99),
                ("Caverion Deutschland GmbH", "angebote@caverion.de", 1.06),
                ("Rud. Otto Meyer Technik (ROM)", "tga@rom-technik.de", 1.02),
            ],
        ),
        (
            "Elektro / GA (MEP electrical & BMS)",
            "MS/NS-Verteilung, NEA/USV, Beleuchtung, Sicherheitstechnik, GLT",
            "evaluating",
            [
                ("SPIE Deutschland & Zentraleuropa", "tender@spie.de", 0.98),
                ("Cegelec / VINCI Energies", "angebote@cegelec.de", 1.04),
                ("Bauer Elektroanlagen Hessen", "vergabe@bauer-elektro.de", 1.01),
            ],
        ),
        (
            "Innenausbau (Interior fit-out)",
            "Trockenbau, Doppelboden, Akustikdecken, Bodenbelaege, Tueren",
            "draft",
            [
                ("Lindner Group", "ausbau@lindner-group.com", 0.96),
                ("Brochier Gebaeudetechnik", "angebote@brochier.de", 1.03),
                ("Pohl Bauunternehmen Hessen", "vergabe@pohl-bau.de", 1.02),
            ],
        ),
        (
            "Aussenanlagen (External works)",
            "Erdbau, Verkehrsflaechen, Begruenung, Aussenleuchten, Anschluesse",
            "draft",
            [
                ("Sonntag Baugesellschaft Hessen", "angebote@sonntag-bau.de", 0.99),
                ("GaLaBau Hessen Rhein-Main GmbH", "vergabe@galabau-rheinmain.de", 1.05),
            ],
        ),
    ],
)
