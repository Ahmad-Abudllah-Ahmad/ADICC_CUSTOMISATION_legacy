// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Per-country trade section / chapter / division tables.
 *
 * Each entry is a flat list of `{ code, label }` that the polymorphic
 * RegionalExchangePage renders as a "<standard> Chapters Reference"
 * card after a file is parsed. The label is intentionally bilingual
 * (native + English in parentheses) so a country specialist sees the
 * familiar code while a non-native reviewer still understands the
 * trade.
 *
 * These are the trade hierarchies of the standards themselves (DIN
 * 276 Kostengruppen, NRM elements, MasterFormat divisions, etc.) —
 * not implementation detail. Keeping them in a single data file
 * makes the 20 country modules truly data-driven.
 */

export interface TradeSection {
  code: string;
  label: string;
}

/** Australian ACMM / ANZSMM trade sections. */
export const AU_TRADE_SECTIONS: TradeSection[] = [
  { code: 'A', label: 'Preliminaries' },
  { code: 'B', label: 'Demolition & Site Preparation' },
  { code: 'C', label: 'Earthworks' },
  { code: 'D', label: 'Piling & Special Foundations' },
  { code: 'E', label: 'Concrete & Formwork' },
  { code: 'F', label: 'Structural Steel' },
  { code: 'G', label: 'Masonry' },
  { code: 'H', label: 'Waterproofing & Dampproofing' },
  { code: 'J', label: 'Roofing' },
  { code: 'K', label: 'Windows & External Doors' },
  { code: 'L', label: 'Internal Doors & Frames' },
  { code: 'M', label: 'Metalwork' },
  { code: 'N', label: 'Plastering & Rendering' },
  { code: 'P', label: 'Tiling' },
  { code: 'Q', label: 'Joinery & Cabinetwork' },
  { code: 'R', label: 'Painting & Decorating' },
  { code: 'S', label: 'Floor Coverings' },
  { code: 'T', label: 'Mechanical Services' },
  { code: 'U', label: 'Hydraulic Services' },
  { code: 'V', label: 'Fire Protection' },
  { code: 'W', label: 'Electrical Services' },
  { code: 'X', label: 'External Works & Landscaping' },
];

/** Brazilian SINAPI / TCPO trade sections. */
export const BR_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: 'Serviços Preliminares (Preliminaries)' },
  { code: '02', label: 'Movimento de Terra (Earthworks)' },
  { code: '03', label: 'Fundações (Foundations)' },
  { code: '04', label: 'Estrutura (Structure)' },
  { code: '05', label: 'Alvenaria (Masonry)' },
  { code: '06', label: 'Cobertura (Roofing)' },
  { code: '07', label: 'Impermeabilização (Waterproofing)' },
  { code: '08', label: 'Revestimento (Rendering & Finishes)' },
  { code: '09', label: 'Pavimentação (Flooring)' },
  { code: '10', label: 'Esquadrias (Doors & Windows)' },
  { code: '11', label: 'Pintura (Painting)' },
  { code: '12', label: 'Instalações Hidráulicas (Plumbing)' },
  { code: '13', label: 'Instalações Elétricas (Electrical)' },
  { code: '14', label: 'Instalações Especiais (Special Installations)' },
  { code: '15', label: 'Complementos (Complements)' },
];

/** Canadian MasterFormat / CIQS trade sections. */
export const CA_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: 'General Requirements' },
  { code: '02', label: 'Site Work & Demolition' },
  { code: '03', label: 'Concrete' },
  { code: '04', label: 'Masonry' },
  { code: '05', label: 'Metals' },
  { code: '06', label: 'Wood & Plastics' },
  { code: '07', label: 'Thermal & Moisture Protection' },
  { code: '08', label: 'Doors & Windows' },
  { code: '09', label: 'Finishes' },
  { code: '10', label: 'Specialties' },
  { code: '11', label: 'Equipment' },
  { code: '12', label: 'Furnishings' },
  { code: '13', label: 'Special Construction' },
  { code: '14', label: 'Conveying Systems' },
  { code: '22', label: 'Mechanical (Plumbing)' },
  { code: '23', label: 'Mechanical (HVAC)' },
  { code: '21', label: 'Fire Protection' },
  { code: '26', label: 'Electrical' },
  { code: '27', label: 'Communications' },
  { code: '32', label: 'Exterior Improvements' },
  { code: '33', label: 'Utilities' },
];

/** Chinese GB/T 50500 trade sections. */
export const CN_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: '土石方工程 (Earthworks)' },
  { code: '02', label: '桩基础工程 (Pile Foundations)' },
  { code: '03', label: '砸筑工程 (Masonry)' },
  { code: '04', label: '混凝土及钢筋混凝土工程 (Concrete & RC)' },
  { code: '05', label: '钢结构工程 (Steel Structures)' },
  { code: '06', label: '木结构工程 (Timber Structures)' },
  { code: '07', label: '屋面及防水工程 (Roofing & Waterproofing)' },
  { code: '08', label: '保温隔热防腐工程 (Insulation & Anti-corrosion)' },
  { code: '09', label: '楼地面装饰工程 (Floor Finishes)' },
  { code: '10', label: '墙柱面装饰工程 (Wall Finishes)' },
  { code: '11', label: '天棚工程 (Ceiling Works)' },
  { code: '12', label: '门窗工程 (Doors & Windows)' },
  { code: '13', label: '油漆涂料裱糊工程 (Painting & Wallcovering)' },
  { code: '14', label: '措施项目 (Provisional Items)' },
  { code: '15', label: '安装工程 (M&E Installation)' },
];

/** Czech URS / TSKP trade sections. */
export const CZ_TRADE_SECTIONS: TradeSection[] = [
  { code: '1', label: 'Zemni prace (Earthworks)' },
  { code: '2', label: 'Zakladani (Foundations)' },
  { code: '3', label: 'Svisle konstrukce (Vertical Structures)' },
  { code: '4', label: 'Vodorovne konstrukce (Horizontal Structures)' },
  { code: '5', label: 'Komunikace (Roads & Pavements)' },
  { code: '6', label: 'Upravy povrchu (Surface Finishes)' },
  { code: '61', label: 'Omitky (Plaster)' },
  { code: '62', label: 'Obklady (Cladding)' },
  { code: '63', label: 'Podlahy (Flooring)' },
  { code: '7', label: 'Izolace (Insulation)' },
  { code: '8', label: 'Potrubi (Piping)' },
  { code: '9', label: 'Ostatni konstrukce (Other Structures)' },
  { code: '91', label: 'Doplnky (Accessories)' },
  { code: '94', label: 'Leseni (Scaffolding)' },
  { code: '95', label: 'Dokoncovaci prace (Finishing)' },
  { code: '96', label: 'Bourani (Demolition)' },
  { code: '97', label: 'Prorazeni otvoru (Openings)' },
  { code: '99', label: 'Presun hmot (Material Transport)' },
];

/** DIN 276 Kostengruppen for DACH construction classification. */
export const DE_TRADE_SECTIONS: TradeSection[] = [
  { code: '100', label: 'Grundstück' },
  { code: '200', label: 'Vorbereitende Maßnahmen' },
  { code: '300', label: 'Bauwerk - Baukonstruktionen' },
  { code: '310', label: 'Baugrube/Erdbau' },
  { code: '320', label: 'Gründung' },
  { code: '330', label: 'Außenwände' },
  { code: '340', label: 'Innenwände' },
  { code: '350', label: 'Decken' },
  { code: '360', label: 'Dächer' },
  { code: '370', label: 'Baukonstruktive Einbauten' },
  { code: '390', label: 'Sonstige Baukonstruktionen' },
  { code: '400', label: 'Bauwerk - Technische Anlagen' },
  { code: '410', label: 'Abwasser-, Wasser-, Gasanlagen' },
  { code: '420', label: 'Wärmeversorgungsanlagen' },
  { code: '430', label: 'Lufttechnische Anlagen' },
  { code: '440', label: 'Starkstromanlagen' },
  { code: '450', label: 'Fernmelde- und IT-Anlagen' },
  { code: '460', label: 'Förderanlagen' },
  { code: '470', label: 'Nutzungsspezifische Anlagen' },
  { code: '480', label: 'Gebäudeautomation' },
  { code: '500', label: 'Außenanlagen und Freiflächen' },
  { code: '600', label: 'Ausstattung und Kunstwerke' },
  { code: '700', label: 'Baunebenkosten' },
];

/** Spanish PBC / Base de Precios chapters. */
export const ES_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: 'Actuaciones Previas (Preliminaries)' },
  { code: '02', label: 'Acondicionamiento del Terreno (Site Preparation)' },
  { code: '03', label: 'Cimentaciones (Foundations)' },
  { code: '04', label: 'Estructuras (Structures)' },
  { code: '05', label: 'Fachadas y Particiones (Facades & Partitions)' },
  { code: '06', label: 'Carpintería y Cerrajería (Joinery & Metalwork)' },
  { code: '07', label: 'Cubiertas (Roofing)' },
  { code: '08', label: 'Revestimientos y Acabados (Finishes)' },
  { code: '09', label: 'Instalaciones Eléctricas (Electrical)' },
  { code: '10', label: 'Fontanería (Plumbing)' },
  { code: '11', label: 'Climatización (HVAC)' },
  { code: '12', label: 'Protección contra Incendios (Fire Protection)' },
  { code: '13', label: 'Urbanización (External Works)' },
  { code: '14', label: 'Gestión de Residuos (Waste Management)' },
  { code: '15', label: 'Seguridad y Salud (Health & Safety)' },
];

/** French Lots techniques (DPGF/DQE work packages). */
export const FR_TRADE_SECTIONS: TradeSection[] = [
  { code: '1', label: 'Terrassement & Fondations (Earthworks & Foundations)' },
  { code: '2', label: 'Gros oeuvre (Structural Concrete)' },
  { code: '3', label: 'Charpente métallique (Structural Steel)' },
  { code: '4', label: 'Charpente bois / Menuiserie (Timber / Carpentry)' },
  { code: '5', label: 'Couverture & Étanchéité (Roofing & Waterproofing)' },
  { code: '6', label: 'Façades & Bardage (Facades & Cladding)' },
  { code: '7', label: 'Électricité (Electrical)' },
  { code: '8', label: 'Plomberie & Sanitaire (Plumbing & Sanitary)' },
  { code: '9', label: 'CVC (HVAC)' },
  { code: '10', label: 'Protection incendie (Fire Protection)' },
  { code: '11', label: 'Aménagements extérieurs (Landscaping)' },
  { code: '12', label: 'Peinture & Revêtements muraux (Painting & Wallcovering)' },
  { code: '13', label: 'Revêtements de sol (Floor Finishes)' },
  { code: '14', label: 'Menuiserie & Serrurerie (Joinery & Ironmongery)' },
  { code: '15', label: 'Ascenseurs (Lifts & Escalators)' },
];

/** Indian CPWD / IS 1200 trade sections. */
export const IN_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: 'Earthwork' },
  { code: '02', label: 'Concrete Work' },
  { code: '03', label: 'Brick Work & Plastering' },
  { code: '04', label: 'Stone Work' },
  { code: '05', label: 'Wood Work & Joinery' },
  { code: '06', label: 'Steel & Iron Work' },
  { code: '07', label: 'Roofing' },
  { code: '08', label: 'Flooring' },
  { code: '09', label: 'Finishing' },
  { code: '10', label: 'Painting' },
  { code: '11', label: 'Plumbing & Sanitary' },
  { code: '12', label: 'Water Supply' },
  { code: '13', label: 'Electrical Works' },
  { code: '14', label: 'HVAC' },
  { code: '15', label: 'Fire Protection' },
  { code: '16', label: 'External Development' },
  { code: '17', label: 'Demolition & Dismantling' },
];

/** Italian Computo Metrico capitoli. */
export const IT_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: 'Demolizioni e Scavi (Demolition & Excavation)' },
  { code: '02', label: 'Fondazioni (Foundations)' },
  { code: '03', label: 'Strutture in C.A. (RC Structures)' },
  { code: '04', label: 'Strutture in Acciaio (Steel Structures)' },
  { code: '05', label: 'Murature (Masonry)' },
  { code: '06', label: 'Solai e Coperture (Floors & Roofing)' },
  { code: '07', label: 'Impermeabilizzazioni (Waterproofing)' },
  { code: '08', label: 'Intonaci e Rivestimenti (Plaster & Cladding)' },
  { code: '09', label: 'Pavimentazioni (Flooring)' },
  { code: '10', label: 'Serramenti (Doors & Windows)' },
  { code: '11', label: 'Opere in Ferro (Metalwork)' },
  { code: '12', label: 'Tinteggiature (Painting)' },
  { code: '13', label: 'Impianto Idrico-Sanitario (Plumbing)' },
  { code: '14', label: 'Impianto Termico (Heating)' },
  { code: '15', label: 'Impianto Elettrico (Electrical)' },
  { code: '16', label: 'Opere Esterne (External Works)' },
  { code: '17', label: 'Sicurezza (Safety)' },
];

/** Japanese Sekisan Kijun trade sections. */
export const JP_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: '仮設工事 (Temporary Works)' },
  { code: '02', label: '土工事 (Earthworks)' },
  { code: '03', label: '地業工事 (Ground Improvement)' },
  { code: '04', label: '鉄筋工事 (Reinforcement)' },
  { code: '05', label: 'コンクリート工事 (Concrete)' },
  { code: '06', label: '鉄骨工事 (Steel Structure)' },
  { code: '07', label: '木工事 (Carpentry)' },
  { code: '08', label: '防水工事 (Waterproofing)' },
  { code: '09', label: '左官工事 (Plastering)' },
  { code: '10', label: 'タイル工事 (Tiling)' },
  { code: '11', label: '金属工事 (Metalwork)' },
  { code: '12', label: '建具工事 (Doors & Windows)' },
  { code: '13', label: '塗装工事 (Painting)' },
  { code: '14', label: '内装工事 (Interior Finishes)' },
  { code: '15', label: '機械設備工事 (Mechanical)' },
  { code: '16', label: '電気設備工事 (Electrical)' },
];

/** Korean Pyoojun Pumssem (Standard Estimating) trade sections. */
export const KR_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: '가설공사 (Temporary Works)' },
  { code: '02', label: '토공사 (Earthworks)' },
  { code: '03', label: '기초공사 (Foundation)' },
  { code: '04', label: '철근콘크리트공사 (RC Works)' },
  { code: '05', label: '철골공사 (Steel Structure)' },
  { code: '06', label: '조적공사 (Masonry)' },
  { code: '07', label: '방수공사 (Waterproofing)' },
  { code: '08', label: '미장공사 (Plastering)' },
  { code: '09', label: '타일공사 (Tiling)' },
  { code: '10', label: '목공사 (Carpentry)' },
  { code: '11', label: '창호공사 (Windows & Doors)' },
  { code: '12', label: '도장공사 (Painting)' },
  { code: '13', label: '금속공사 (Metalwork)' },
  { code: '14', label: '기계설비공사 (Mechanical)' },
  { code: '15', label: '전기설비공사 (Electrical)' },
  { code: '16', label: '조경공사 (Landscaping)' },
];

/** Dutch STABU / RAW trade sections. */
export const NL_TRADE_SECTIONS: TradeSection[] = [
  { code: '00', label: 'Algemeen (General)' },
  { code: '01', label: 'Grondwerk (Earthworks)' },
  { code: '03', label: 'Beton- en Metselwerk (Concrete & Masonry)' },
  { code: '04', label: 'Staalconstructies (Steel Structures)' },
  { code: '05', label: 'Houtconstructies (Timber Structures)' },
  { code: '06', label: 'Metaalwerken (Metalwork)' },
  { code: '20', label: 'Daken (Roofing)' },
  { code: '21', label: 'Beglazing (Glazing)' },
  { code: '22', label: 'Kozijnen en Deuren (Frames & Doors)' },
  { code: '30', label: 'Stukadoorwerk (Plastering)' },
  { code: '31', label: 'Tegelwerk (Tiling)' },
  { code: '33', label: 'Plafonds (Ceilings)' },
  { code: '34', label: 'Schilderwerk (Painting)' },
  { code: '40', label: 'Sanitair (Sanitary)' },
  { code: '41', label: 'Verwarming (Heating)' },
  { code: '42', label: 'Ventilatie (Ventilation)' },
  { code: '43', label: 'Elektra (Electrical)' },
  { code: '50', label: 'Terreinwerk (External Works)' },
];

/** Nordic NS 3420 / AMA / V&S trade sections. */
export const NORDIC_TRADE_SECTIONS: TradeSection[] = [
  { code: 'A', label: 'Rigging og drift (Site Setup & Operation)' },
  { code: 'B', label: 'Grunnarbeid (Ground Works)' },
  { code: 'C', label: 'Betongarbeid (Concrete)' },
  { code: 'D', label: 'Stålkonstruksjoner (Steel Structures)' },
  { code: 'E', label: 'Trekonstruksjoner (Timber Structures)' },
  { code: 'F', label: 'Muring (Masonry)' },
  { code: 'G', label: 'Taktekking (Roofing)' },
  { code: 'H', label: 'Blikkenslager (Sheet Metal)' },
  { code: 'J', label: 'Tømrer (Carpentry)' },
  { code: 'K', label: 'Malerarbeid (Painting)' },
  { code: 'L', label: 'Gulvlegging (Flooring)' },
  { code: 'M', label: 'VVS-installasjoner (HVAC & Plumbing)' },
  { code: 'N', label: 'Elektroinstallasjoner (Electrical)' },
  { code: 'P', label: 'Heis (Elevators)' },
  { code: 'Q', label: 'Utomhus (External Works)' },
  { code: 'R', label: 'Riving (Demolition)' },
];

/** Polish KNR / KNNR trade sections. */
export const PL_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: 'Roboty ziemne (Earthworks)' },
  { code: '02', label: 'Fundamenty (Foundations)' },
  { code: '03', label: 'Konstrukcje żelbetowe (RC Structures)' },
  { code: '04', label: 'Konstrukcje stalowe (Steel Structures)' },
  { code: '05', label: 'Roboty murowe (Masonry)' },
  { code: '06', label: 'Konstrukcje drewniane (Timber)' },
  { code: '07', label: 'Pokrycia dachowe (Roofing)' },
  { code: '08', label: 'Izolacje (Insulation)' },
  { code: '09', label: 'Tynki i okładziny (Plaster & Cladding)' },
  { code: '10', label: 'Posadzki (Flooring)' },
  { code: '11', label: 'Stolarka (Joinery)' },
  { code: '12', label: 'Ślusarka (Metalwork)' },
  { code: '13', label: 'Malowanie (Painting)' },
  { code: '14', label: 'Instalacje sanitarne (Sanitary)' },
  { code: '15', label: 'Instalacje elektryczne (Electrical)' },
  { code: '16', label: 'Instalacje grzewcze (Heating)' },
  { code: '17', label: 'Wentylacja (Ventilation)' },
  { code: '18', label: 'Roboty zewnętrzne (External Works)' },
];

/** Russian GESN collection codes. */
export const RU_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: 'Земляные работы (Earthworks)' },
  { code: '06', label: 'Бетонные и железобетонные конструкции (Concrete & RC)' },
  { code: '07', label: 'Сборные железобетонные конструкции (Precast Concrete)' },
  { code: '08', label: 'Конструкции из кирпича (Masonry)' },
  { code: '09', label: 'Металлические конструкции (Steel Structures)' },
  { code: '10', label: 'Деревянные конструкции (Timber Structures)' },
  { code: '11', label: 'Полы (Flooring)' },
  { code: '12', label: 'Кровли (Roofing)' },
  { code: '13', label: 'Защитные покрытия (Protective Coatings)' },
  { code: '15', label: 'Отделочные работы (Finishing)' },
  { code: '16', label: 'Сантехнические работы (Plumbing)' },
  { code: '17', label: 'Электромонтаж (Electrical)' },
  { code: '18', label: 'Отопление (Heating)' },
  { code: '19', label: 'Вентиляция и кондиционирование (HVAC)' },
  { code: '20', label: 'Временные здания (Temporary Works)' },
  { code: '46', label: 'Реконструкция (Reconstruction)' },
];

/** Turkish Bayindirlik Birim Fiyat trade sections. */
export const TR_TRADE_SECTIONS: TradeSection[] = [
  { code: '01', label: 'Hafriyat Isleri (Excavation)' },
  { code: '04', label: 'Beton ve Betonarme Isleri (Concrete & RC)' },
  { code: '07', label: 'Ahsap Isleri (Timber Works)' },
  { code: '10', label: 'Demir Isleri (Ironwork)' },
  { code: '13', label: 'Cati Isleri (Roofing)' },
  { code: '15', label: 'Sihhi Tesisat (Plumbing)' },
  { code: '16', label: 'Kalorifer Tesisati (Heating)' },
  { code: '17', label: 'Havalandirma Tesisati (Ventilation)' },
  { code: '18', label: 'Elektrik Tesisati (Electrical)' },
  { code: '21', label: 'Boya Isleri (Painting)' },
  { code: '23', label: 'Kaplama Isleri (Cladding & Finishes)' },
  { code: '25', label: 'Insaat Demiri Isleri (Rebar)' },
  { code: '27', label: 'Yalitim Isleri (Insulation)' },
  { code: '30', label: 'Asansor (Elevators)' },
];

/** UAE FIDIC / NRM-POMI trade sections (high-rise / infrastructure / hospitality). */
export const UAE_TRADE_SECTIONS: TradeSection[] = [
  { code: 'A', label: 'Preliminaries' },
  { code: 'B', label: 'Substructure' },
  { code: 'C', label: 'Concrete Works' },
  { code: 'D', label: 'Masonry' },
  { code: 'E', label: 'Structural Steelwork' },
  { code: 'F', label: 'Waterproofing' },
  { code: 'G', label: 'Roofing' },
  { code: 'H', label: 'Windows & Doors' },
  { code: 'I', label: 'Internal Finishes' },
  { code: 'J', label: 'External Finishes' },
  { code: 'K', label: 'MEP - Mechanical' },
  { code: 'L', label: 'MEP - Electrical' },
  { code: 'M', label: 'MEP - Plumbing' },
  { code: 'N', label: 'Fire Protection' },
  { code: 'O', label: 'Landscaping & External Works' },
  { code: 'P', label: 'Swimming Pools & Water Features' },
  { code: 'Q', label: 'Specialist Works' },
];

/** UK NRM 1 element hierarchy (Level 1 groups). */
export const NRM_ELEMENTS: TradeSection[] = [
  { code: '0', label: 'Facilitating works' },
  { code: '1', label: 'Substructure' },
  { code: '2', label: 'Superstructure' },
  { code: '3', label: 'Internal finishes' },
  { code: '4', label: 'Fittings, furnishings and equipment' },
  { code: '5', label: 'Services' },
  { code: '6', label: 'Prefabricated buildings and building units' },
  { code: '7', label: 'Work to existing buildings' },
  { code: '8', label: 'External works' },
  { code: '9', label: "Main contractor's preliminaries" },
  { code: '10', label: "Main contractor's overheads and profit" },
  { code: '11', label: 'Project/design team fees' },
  { code: '12', label: 'Other development/project costs' },
  { code: '13', label: 'Risks' },
  { code: '14', label: 'Inflation' },
];

/** CSI MasterFormat divisions. */
export const MF_DIVISIONS: TradeSection[] = [
  { code: '00', label: 'Procurement and Contracting Requirements' },
  { code: '01', label: 'General Requirements' },
  { code: '02', label: 'Existing Conditions' },
  { code: '03', label: 'Concrete' },
  { code: '04', label: 'Masonry' },
  { code: '05', label: 'Metals' },
  { code: '06', label: 'Wood, Plastics, and Composites' },
  { code: '07', label: 'Thermal and Moisture Protection' },
  { code: '08', label: 'Openings' },
  { code: '09', label: 'Finishes' },
  { code: '10', label: 'Specialties' },
  { code: '11', label: 'Equipment' },
  { code: '12', label: 'Furnishings' },
  { code: '13', label: 'Special Construction' },
  { code: '14', label: 'Conveying Equipment' },
  { code: '21', label: 'Fire Suppression' },
  { code: '22', label: 'Plumbing' },
  { code: '23', label: 'Heating, Ventilating, and Air Conditioning (HVAC)' },
  { code: '25', label: 'Integrated Automation' },
  { code: '26', label: 'Electrical' },
  { code: '27', label: 'Communications' },
  { code: '28', label: 'Electronic Safety and Security' },
  { code: '31', label: 'Earthwork' },
  { code: '32', label: 'Exterior Improvements' },
  { code: '33', label: 'Utilities' },
  { code: '34', label: 'Transportation' },
  { code: '35', label: 'Waterway and Marine Construction' },
  { code: '40', label: 'Process Integration' },
  { code: '41', label: 'Material Processing and Handling Equipment' },
  { code: '42', label: 'Process Heating, Cooling, and Drying Equipment' },
  { code: '43', label: 'Process Gas and Liquid Handling' },
  { code: '44', label: 'Pollution and Waste Control Equipment' },
  { code: '45', label: 'Industry-Specific Manufacturing Equipment' },
  { code: '46', label: 'Water and Wastewater Equipment' },
  { code: '48', label: 'Electrical Power Generation' },
];
