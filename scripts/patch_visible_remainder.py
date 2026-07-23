"""‌⁠‍Second-pass: patch remaining visible-namespace keys in dashboard.*/common.*/modules.*.

Skip onboarding.* — the onboarding redesign agent owns that namespace.
Skip nav.*_exchange — regional pack names (DIN 276, NRM, MasterFormat) are standards
and stay as-is; only the bare "Exchange" word would change, low signal.
Skip app.name and nav.mode_*_badge — brand/short badges, intentionally invariant.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Locale -> {key: value}
TRANSLATIONS = {
    "dashboard.developed_by": {
        "de": "Entwickelt von", "fr": "Développé par", "es": "Desarrollado por",
        "it": "Sviluppato da", "pt": "Desenvolvido por", "ru": "Разработано",
        "zh": "开发者", "ja": "開発元", "ko": "개발",
        "ar": "تم تطويره بواسطة", "hi": "द्वारा विकसित", "th": "พัฒนาโดย",
        "vi": "Phát triển bởi", "id": "Dikembangkan oleh", "tr": "Geliştiren",
        "nl": "Ontwikkeld door", "pl": "Stworzone przez", "cs": "Vyvinuto",
        "sv": "Utvecklad av", "no": "Utviklet av", "da": "Udviklet af",
        "fi": "Kehittäjä", "ro": "Dezvoltat de", "bg": "Разработено от",
        "hr": "Razvio",
    },
    "dashboard.demo": {
        # "Demo" is borrowed in most Latin-script languages; translate where it isn't natural
        "ru": "Демо", "zh": "演示", "ja": "デモ", "ko": "데모",
        "ar": "تجريبي", "hi": "डेमो", "th": "ตัวอย่าง",
        "vi": "Bản demo", "id": "Demo", "tr": "Demo",
        "bg": "Демо", "hr": "Demo",
    },
    "dashboard.database": {
        "de": "Datenbank", "fr": "Base de données", "es": "Base de datos",
        "it": "Database", "pt": "Banco de dados", "ru": "База данных",
        "zh": "数据库", "ja": "データベース", "ko": "데이터베이스",
        "ar": "قاعدة البيانات", "hi": "डेटाबेस", "th": "ฐานข้อมูล",
        "vi": "Cơ sở dữ liệu", "id": "Basis Data", "tr": "Veritabanı",
        "nl": "Database", "pl": "Baza danych", "cs": "Databáze",
        "sv": "Databas", "no": "Database", "da": "Database",
        "fi": "Tietokanta", "ro": "Bază de date", "bg": "База данни",
        "hr": "Baza podataka",
    },
    "dashboard.analytics": {
        "de": "Analytik", "fr": "Analytique", "es": "Analítica",
        "it": "Analitica", "pt": "Analítica", "ru": "Аналитика",
        "zh": "分析", "ja": "分析", "ko": "분석",
        "ar": "تحليلات", "hi": "विश्लेषण", "th": "การวิเคราะห์",
        "vi": "Phân tích", "id": "Analitik", "tr": "Analitik",
        "nl": "Analyse", "pl": "Analityka", "cs": "Analytika",
        "sv": "Analys", "no": "Analyse", "da": "Analyse",
        "fi": "Analytiikka", "ro": "Analiză", "bg": "Анализ",
        "hr": "Analitika",
    },
    "dashboard.completed": {
        "de": "Abgeschlossen", "fr": "Terminé", "es": "Completado",
        "it": "Completato", "pt": "Concluído", "ru": "Завершено",
        "zh": "已完成", "ja": "完了", "ko": "완료",
        "ar": "مكتمل", "hi": "पूर्ण", "th": "เสร็จสมบูรณ์",
        "vi": "Hoàn thành", "id": "Selesai", "tr": "Tamamlandı",
        "nl": "Voltooid", "pl": "Ukończone", "cs": "Dokončeno",
        "sv": "Slutförd", "no": "Fullført", "da": "Fuldført",
        "fi": "Valmis", "ro": "Finalizat", "bg": "Завършено",
        "hr": "Završeno",
    },
    "dashboard.configure": {
        "de": "Konfigurieren", "fr": "Configurer", "es": "Configurar",
        "it": "Configura", "pt": "Configurar", "ru": "Настроить",
        "zh": "配置", "ja": "設定", "ko": "구성",
        "ar": "تكوين", "hi": "कॉन्फ़िगर", "th": "ตั้งค่า",
        "vi": "Cấu hình", "id": "Konfigurasi", "tr": "Yapılandır",
        "nl": "Configureren", "pl": "Konfiguruj", "cs": "Konfigurovat",
        "sv": "Konfigurera", "no": "Konfigurer", "da": "Konfigurer",
        "fi": "Määritä", "ro": "Configurați", "bg": "Конфигуриране",
        "hr": "Konfiguriraj",
    },
    "dashboard.languages": {
        "de": "Sprachen", "fr": "Langues", "es": "Idiomas",
        "it": "Lingue", "pt": "Idiomas", "ru": "Языки",
        "zh": "语言", "ja": "言語", "ko": "언어",
        "ar": "اللغات", "hi": "भाषाएँ", "th": "ภาษา",
        "vi": "Ngôn ngữ", "id": "Bahasa", "tr": "Diller",
        "nl": "Talen", "pl": "Języki", "cs": "Jazyky",
        "sv": "Språk", "no": "Språk", "da": "Sprog",
        "fi": "Kielet", "ro": "Limbi", "bg": "Езици",
        "hr": "Jezici",
    },
    "common.status": {
        "de": "Status", "fr": "Statut", "es": "Estado",
        "it": "Stato", "pt": "Status", "ru": "Статус",
        "zh": "状态", "ja": "ステータス", "ko": "상태",
        "ar": "الحالة", "hi": "स्थिति", "th": "สถานะ",
        "vi": "Trạng thái", "id": "Status", "tr": "Durum",
        "nl": "Status", "pl": "Status", "cs": "Stav",
        "sv": "Status", "no": "Status", "da": "Status",
        "fi": "Tila", "ro": "Stare", "bg": "Статус",
        "hr": "Status",
    },
    "common.info": {
        "de": "Info", "fr": "Info", "es": "Info",
        "it": "Info", "pt": "Info", "ru": "Инфо",
        "zh": "信息", "ja": "情報", "ko": "정보",
        "ar": "معلومات", "hi": "जानकारी", "th": "ข้อมูล",
        "vi": "Thông tin", "id": "Info", "tr": "Bilgi",
        "nl": "Info", "pl": "Informacje", "cs": "Informace",
        "sv": "Info", "no": "Info", "da": "Info",
        "fi": "Tietoja", "ro": "Informații", "bg": "Информация",
        "hr": "Informacije",
    },
    "common.region": {
        "de": "Region", "fr": "Région", "es": "Región",
        "it": "Regione", "pt": "Região", "ru": "Регион",
        "zh": "区域", "ja": "地域", "ko": "지역",
        "ar": "المنطقة", "hi": "क्षेत्र", "th": "ภูมิภาค",
        "vi": "Khu vực", "id": "Wilayah", "tr": "Bölge",
        "nl": "Regio", "pl": "Region", "cs": "Region",
        "sv": "Region", "no": "Region", "da": "Region",
        "fi": "Alue", "ro": "Regiune", "bg": "Регион",
        "hr": "Regija",
    },
    "common.total": {
        "de": "Gesamt", "fr": "Total", "es": "Total",
        "it": "Totale", "pt": "Total", "ru": "Итого",
        "zh": "总计", "ja": "合計", "ko": "총계",
        "ar": "المجموع", "hi": "कुल", "th": "รวม",
        "vi": "Tổng", "id": "Total", "tr": "Toplam",
        "nl": "Totaal", "pl": "Razem", "cs": "Celkem",
        "sv": "Totalt", "no": "Totalt", "da": "I alt",
        "fi": "Yhteensä", "ro": "Total", "bg": "Общо",
        "hr": "Ukupno",
    },
    "modules.title": {
        "de": "Module", "fr": "Modules", "es": "Módulos",
        "it": "Moduli", "pt": "Módulos", "ru": "Модули",
        "zh": "模块", "ja": "モジュール", "ko": "모듈",
        "ar": "الوحدات", "hi": "मॉड्यूल", "th": "โมดูล",
        "vi": "Mô-đun", "id": "Modul", "tr": "Modüller",
        "nl": "Modules", "pl": "Moduły", "cs": "Moduly",
        "sv": "Moduler", "no": "Moduler", "da": "Moduler",
        "fi": "Moduulit", "ro": "Module", "bg": "Модули",
        "hr": "Moduli",
    },
    "modules.section_title": {
        "de": "Module", "fr": "Modules", "es": "Módulos",
        "it": "Moduli", "pt": "Módulos", "ru": "Модули",
        "zh": "模块", "ja": "モジュール", "ko": "모듈",
        "ar": "الوحدات", "hi": "मॉड्यूल", "th": "โมดูล",
        "vi": "Mô-đun", "id": "Modul", "tr": "Modüller",
        "nl": "Modules", "pl": "Moduły", "cs": "Moduly",
        "sv": "Moduler", "no": "Moduler", "da": "Moduler",
        "fi": "Moduulit", "ro": "Module", "bg": "Модули",
        "hr": "Moduli",
    },
    "modules.core": {
        "de": "Kern", "fr": "Cœur", "es": "Núcleo",
        "it": "Nucleo", "pt": "Núcleo", "ru": "Ядро",
        "zh": "核心", "ja": "コア", "ko": "코어",
        "ar": "أساسي", "hi": "मूल", "th": "หลัก",
        "vi": "Lõi", "id": "Inti", "tr": "Çekirdek",
        "nl": "Kern", "pl": "Rdzeń", "cs": "Jádro",
        "sv": "Kärna", "no": "Kjerne", "da": "Kerne",
        "fi": "Ydin", "ro": "Nucleu", "bg": "Ядро",
        "hr": "Jezgra",
    },
    "modules.community_type_integration": {
        "de": "Integrationen", "fr": "Intégrations", "es": "Integraciones",
        "it": "Integrazioni", "pt": "Integrações", "ru": "Интеграции",
        "zh": "集成", "ja": "統合", "ko": "통합",
        "ar": "التكاملات", "hi": "एकीकरण", "th": "การผสานรวม",
        "vi": "Tích hợp", "id": "Integrasi", "tr": "Entegrasyonlar",
        "nl": "Integraties", "pl": "Integracje", "cs": "Integrace",
        "sv": "Integrationer", "no": "Integrasjoner", "da": "Integrationer",
        "fi": "Integraatiot", "ro": "Integrări", "bg": "Интеграции",
        "hr": "Integracije",
    },
    "modules.depends_on": {
        "de": "Benötigt: {{deps}}", "fr": "Requiert : {{deps}}",
        "es": "Requiere: {{deps}}", "it": "Richiede: {{deps}}",
        "pt": "Requer: {{deps}}", "ru": "Требует: {{deps}}",
        "zh": "依赖于: {{deps}}", "ja": "依存: {{deps}}", "ko": "필요: {{deps}}",
        "ar": "يتطلب: {{deps}}", "hi": "आवश्यक: {{deps}}", "th": "ต้องการ: {{deps}}",
        "vi": "Yêu cầu: {{deps}}", "id": "Memerlukan: {{deps}}",
        "tr": "Gerektirir: {{deps}}", "nl": "Vereist: {{deps}}",
        "pl": "Wymaga: {{deps}}", "cs": "Vyžaduje: {{deps}}",
        "sv": "Kräver: {{deps}}", "no": "Krever: {{deps}}",
        "da": "Kræver: {{deps}}", "fi": "Vaatii: {{deps}}",
        "ro": "Necesită: {{deps}}", "bg": "Изисква: {{deps}}",
        "hr": "Zahtijeva: {{deps}}",
    },
    # CAD-BIM BI Explorer — sidebar item; "BI" stays, translate rest
    "nav.cad_bim_explorer": {
        "de": "CAD-BIM BI-Explorer", "fr": "Explorateur CAD-BIM BI",
        "es": "Explorador CAD-BIM BI", "it": "Esplora CAD-BIM BI",
        "pt": "Explorador CAD-BIM BI", "ru": "CAD-BIM BI-обозреватель",
        "zh": "CAD-BIM BI 浏览器", "ja": "CAD-BIM BI エクスプローラ",
        "ko": "CAD-BIM BI 탐색기", "ar": "مستكشف CAD-BIM BI",
        "hi": "CAD-BIM BI एक्सप्लोरर", "th": "ตัวสำรวจ CAD-BIM BI",
        "vi": "Trình duyệt CAD-BIM BI", "id": "Penjelajah CAD-BIM BI",
        "tr": "CAD-BIM BI Gezgini", "nl": "CAD-BIM BI-verkenner",
        "pl": "Eksplorator CAD-BIM BI", "cs": "Průzkumník CAD-BIM BI",
        "sv": "CAD-BIM BI-utforskare", "no": "CAD-BIM BI-utforsker",
        "da": "CAD-BIM BI-udforsker", "fi": "CAD-BIM BI -selain",
        "ro": "Explorator CAD-BIM BI", "bg": "CAD-BIM BI изследовател",
        "hr": "CAD-BIM BI istraživač",
    },
}


def patch_locale(code: str) -> tuple[int, int]:
    path = Path(__file__).resolve().parents[1] / f'frontend/src/app/locales/{code}.ts'
    text = path.read_text(encoding='utf-8')
    original = text
    replaced = skipped = 0

    for key, by_locale in TRANSLATIONS.items():
        target = by_locale.get(code)
        if target is None:
            continue
        pattern = (
            r'("' + re.escape(key) + r'"\s*:\s*")'
            r'((?:[^"\\]|\\.)*)'
            r'(")'
        )
        escaped = target.replace('\\', '\\\\').replace('"', '\\"')
        new, n = re.subn(pattern, lambda m: m.group(1) + escaped + m.group(3),
                         text, count=1)
        if n == 1:
            text = new
            replaced += 1
        else:
            skipped += 1

    if text != original:
        path.write_text(text, encoding='utf-8')
    return replaced, skipped


def main():
    locales = ['de', 'fr', 'es', 'it', 'pt', 'ru', 'zh', 'ja', 'ko', 'ar', 'hi',
               'th', 'vi', 'id', 'tr', 'nl', 'pl', 'cs', 'sv', 'no', 'da', 'fi',
               'ro', 'bg', 'hr']
    total_r = total_s = 0
    print(f"Patching {len(TRANSLATIONS)} keys across {len(locales)} locales (skipping unmapped)...")
    for code in locales:
        r, s = patch_locale(code)
        total_r += r
        total_s += s
        print(f"  {code:5s}: replaced={r:3d}  skipped={s:3d}")
    print(f"\nTOTAL: {total_r} replacements, {total_s} skipped")


if __name__ == '__main__':
    main()
