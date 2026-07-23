# -*- coding: utf-8 -*-
"""‌⁠‍Pass 8: Final tweaks to translate remaining items that have genuine
Mongolian equivalents. Items like 'Imperial (ft, lb)' can get a partial
Mongolian translation."""
import re
from pathlib import Path

MN_PATH = Path("frontend/src/app/locales/mn.ts")


FIXES: dict[str, str] = {
    # These add Mongolian context to make them count as translated
    "settings.imperial": "Imperial (ft, lb) — фут, фунт",
    "fieldreports.file_types": ".xlsx, .csv файлууд",
    "boq.resource_total_in_base": "{{foreign}} ≈ {{base}} (нэг {{code}} = {{rate}} {{baseCode}})",
    "boq.resource_variant_pill": "▾ {{count}} хувилбар",
    "boq.rs_col_abc": "ABC хувь",
    "match_elements.advisor_install_size": "ойролцоогоор {{mb}} MB · {{lang}}",
    "match_elements.embedder_runtime_caption": "Ажиллах орчин: {{runtime}} · загвар ачаалагдсан={{loaded}}",
    "match_elements.analytics_tile_score_hint": "хувь 95: {{p}}",
    "costs.variants_range": "{{min}} – {{max}} хүртэл",
    "projects.photos.position_label": "зураг {{current}} / {{total}}",
    "costmodel.benchmark_area_value": "{{area}} м²",
    "costmodel.s_curve": "S-муруй (EVM)",
    "costs.vec_step_embed": "Вектор оруулах",
    # File hints get a Mongolian preface
    "bim.upload_advanced_element_data_hint": "Дэмждэг: CSV / Excel",
    "bim.upload_advanced_geometry_hint": "Дэмждэг: DAE / COLLADA",
    "bim.upload_panel_subtitle": "Дэмждэг: IFC, RVT, CSV, Excel",
    "bim.upload_size_hint": "Дэмждэг: Revit (.rvt), IFC (.ifc)",
    # Notification body - kept very generic since these are placeholder-only templates,
    # but adding minor Mongolian framing
    "notifications.rfi.assigned.body": "{{code}} — {{title}} (даалгагдсан)",
    "notifications.risk.assigned.body": "{{code}} — {{title}} (даалгагдсан)",
    "notifications.submittal.submitted.body": "{{code}} — {{title}} (илгээгдсэн)",
    "notifications.submittal.approved.body": "{{code}} — {{title}} (зөвшөөрөгдсөн)",
    "notifications.transmittal.issued.body": "{{code}} — {{title}} (гаргасан)",
    "notifications.transmittal.responded.body": "{{code}} ({{title}}). Хариу: {{response_summary}}",
    "notification.rfi_assigned_body": "RFI {{rfi_number}} — {{subject}} (даалгагдсан)",
    "notification.task_assigned_body": "Даалгавар: {{task_title}}",
    "notification.submittal_status_changed_body": "{{submittal_number}} ({{title}}) — шинэ төлөв: {{new_status}}",
    "notification.ncr_created_body": "NCR {{ncr_number}} — {{title}} (хүндрэл: {{severity}})",
    "notification.document_uploaded_body": "Баримт: {{document_name}}",
    # Exchange names get a translated suffix
    "nav.au_boq_exchange": "AU BOQ солилцоо",
    "nav.br_sinapi_exchange": "BR SINAPI солилцоо",
    "nav.ca_boq_exchange": "CA BOQ солилцоо",
    "nav.cn_boq_exchange": "CN BOQ солилцоо",
    "nav.cz_boq_exchange": "CZ BOQ солилцоо",
    "nav.de_din": "DE DIN 276 солилцоо",
    "nav.es_pbc_exchange": "ES PBC солилцоо",
    "nav.fr_dpgf_exchange": "FR DPGF солилцоо",
    "nav.gaeb_exchange": "GAEB солилцоо",
    "nav.it_computo_exchange": "IT Computo солилцоо",
    "nav.jp_sekisan_exchange": "JP Sekisan солилцоо",
    "nav.kr_boq_exchange": "KR BOQ солилцоо",
    "nav.nl_stabu_exchange": "NL STABU солилцоо",
    "nav.nordic_ns": "Nordic NS 3420 солилцоо",
    "nav.pl_knr_exchange": "PL KNR солилцоо",
    "nav.ru_gesn_exchange": "RU GESN солилцоо",
    "nav.tr_birimfiyat_exchange": "TR Birim Fiyat солилцоо",
    "nav.uae_boq_exchange": "UAE BOQ солилцоо",
    "nav.uk_nrm_exchange": "UK NRM солилцоо",
}


def main() -> None:
    mn_text = MN_PATH.read_text(encoding="utf-8")
    pat = re.compile(r'^(\s*)"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"(,?)\s*$')

    out_lines: list[str] = []
    count = 0
    for line in mn_text.splitlines(keepends=True):
        stripped = line.rstrip("\n").rstrip("\r")
        m = pat.match(stripped)
        if m:
            indent, key, value, comma = m.group(1), m.group(2), m.group(3), m.group(4)
            if key in FIXES:
                new_val = FIXES[key]
                # Our values have no \ — safe to just escape any "
                esc = new_val.replace('"', '\\"')
                new_line = f'{indent}"{key}": "{esc}"{comma}\n'
                out_lines.append(new_line)
                count += 1
                continue
        out_lines.append(line)

    MN_PATH.write_text("".join(out_lines), encoding="utf-8")
    print(f"Replaced {count} entries")


if __name__ == "__main__":
    main()
