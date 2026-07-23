"""‌⁠‍Update voices sidebar locale keys for the 7-card grouped catalog.

Adds: group_flagship, group_github, ref_cadbim_*, ref_agents_*, ref_excel_*,
ref_cad2data_*, ref_skills_*. Rewrites: aside_label, ref_book_*, ref_cwicr_*
to match the new card semantics (Guidebook + OpenConstructionEstimate).
The old ref_cad_* keys are dropped (no longer rendered).
"""
import json
from pathlib import Path

BASE = Path('C:/Users/Artem Boiko/Desktop/CodeProjects/ERP_26030500/website-marketing/pro/breeze/locales')

UPDATES = {
    'en': {
        'aside_label': 'DDC Ecosystem · projects mentioned above',
        'group_flagship': 'flagship products · datadrivenconstruction.io',
        'group_github': 'open-source on github · datadrivenconstruction',
        'ref_cadbim_name': 'CAD-BIM Converter',
        'ref_cadbim_meta': 'CAD/BIM Pipeline',
        'ref_agents_name': 'DDC AI Agents & Skills',
        'ref_agents_meta': 'Automation Toolbox',
        'ref_excel_name': 'DDC Excel Plugin',
        'ref_excel_meta': 'Spreadsheet Bridge',
        'ref_book_name': 'DDC Guidebook',
        'ref_book_meta': 'Reference Reading',
        'ref_cad2data_name': 'CAD2Data Pipeline',
        'ref_cad2data_meta': 'The Data Refinery',
        'ref_cwicr_name': 'OpenConstructionEstimate',
        'ref_cwicr_meta': 'The Financial Core',
        'ref_skills_name': 'DDC Skills for AI Agents',
        'ref_skills_meta': 'The Master Controller',
    },
    'de': {
        'aside_label': 'DDC-Ökosystem · oben erwähnte Projekte',
        'group_flagship': 'Flaggschiff-Produkte · datadrivenconstruction.io',
        'group_github': 'Open Source auf GitHub · datadrivenconstruction',
        'ref_cadbim_name': 'CAD-BIM Converter',
        'ref_cadbim_meta': 'CAD/BIM-Pipeline',
        'ref_agents_name': 'DDC KI-Agenten & Skills',
        'ref_agents_meta': 'Automatisierungs-Toolbox',
        'ref_excel_name': 'DDC Excel-Plugin',
        'ref_excel_meta': 'Tabellenbrücke',
        'ref_book_name': 'DDC Guidebook',
        'ref_book_meta': 'Nachschlagewerk',
        'ref_cad2data_name': 'CAD2Data Pipeline',
        'ref_cad2data_meta': 'Die Datenraffinerie',
        'ref_cwicr_name': 'OpenConstructionEstimate',
        'ref_cwicr_meta': 'Der finanzielle Kern',
        'ref_skills_name': 'DDC Skills für KI-Agenten',
        'ref_skills_meta': 'Die Meisterzentrale',
    },
    'ru': {
        'aside_label': 'Экосистема DDC · упомянутые в тексте проекты',
        'group_flagship': 'флагманские продукты · datadrivenconstruction.io',
        'group_github': 'открытый код на github · datadrivenconstruction',
        'ref_cadbim_name': 'CAD-BIM Converter',
        'ref_cadbim_meta': 'CAD/BIM-конвейер',
        'ref_agents_name': 'DDC AI-агенты и навыки',
        'ref_agents_meta': 'Набор автоматизации',
        'ref_excel_name': 'Плагин DDC для Excel',
        'ref_excel_meta': 'Мост к таблицам',
        'ref_book_name': 'DDC Guidebook',
        'ref_book_meta': 'Справочное чтение',
        'ref_cad2data_name': 'CAD2Data Pipeline',
        'ref_cad2data_meta': 'Очистка данных',
        'ref_cwicr_name': 'OpenConstructionEstimate',
        'ref_cwicr_meta': 'Финансовое ядро',
        'ref_skills_name': 'DDC-скиллы для AI-агентов',
        'ref_skills_meta': 'Главный контроллер',
    },
}

DROP_KEYS = ['ref_book_desc', 'ref_cad_name', 'ref_cad_meta', 'ref_cad_desc',
             'ref_cwicr_desc']

for lang, updates in UPDATES.items():
    p = BASE / f'{lang}.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    voices = data.get('voices', {})
    for k in DROP_KEYS:
        voices.pop(k, None)
    voices.update(updates)
    data['voices'] = voices
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'updated {p.name}: {len(updates)} keys set, {len(DROP_KEYS)} dropped')
