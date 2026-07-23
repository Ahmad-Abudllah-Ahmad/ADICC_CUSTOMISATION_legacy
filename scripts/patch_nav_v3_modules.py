"""‌⁠‍Backfill v3.0 18-Modules Wave nav.* keys across all 25 non-EN, non-MN locales.

These keys exist in en.ts as English; in every other locale (except mn) they
were copied through as English and never translated. The user explicitly flagged
this in v3.0.5 — fixing it before the release.

Glossary curated from established platform patterns + standard construction-domain
terminology in each language.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Translation matrix. Locale -> {key: translated_value}
# Locales: de, fr, es, it, pt, ru, zh, ja, ko, ar, hi, th, vi, id, tr,
#          nl, pl, cs, sv, no, da, fi, ro, bg, hr
# (mn already done in v3.0.5 Mongolian pass)

TRANSLATIONS = {
    "nav.daily_diary": {
        "de": "Bautagebuch", "fr": "Journal de chantier", "es": "Diario de obra",
        "it": "Giornale di cantiere", "pt": "Diário de obra", "ru": "Журнал стройплощадки",
        "zh": "施工日志", "ja": "工事日報", "ko": "현장 일지",
        "ar": "يوميات الموقع", "hi": "दैनिक डायरी", "th": "บันทึกประจำวัน",
        "vi": "Nhật ký công trường", "id": "Buku Harian Proyek", "tr": "Şantiye Günlüğü",
        "nl": "Bouwdagboek", "pl": "Dziennik budowy", "cs": "Stavební deník",
        "sv": "Byggdagbok", "no": "Byggdagbok", "da": "Byggedagbog",
        "fi": "Työmaapäiväkirja", "ro": "Jurnal de șantier", "bg": "Дневник на обекта",
        "hr": "Dnevnik gradilišta",
    },
    "nav.equipment": {
        "de": "Geräte & Fuhrpark", "fr": "Équipement & flotte", "es": "Equipos y flota",
        "it": "Attrezzature e flotta", "pt": "Equipamentos e frota", "ru": "Оборудование и автопарк",
        "zh": "设备与车队", "ja": "機材・車両", "ko": "장비 및 차량",
        "ar": "المعدات والأسطول", "hi": "उपकरण और बेड़ा", "th": "อุปกรณ์และยานพาหนะ",
        "vi": "Thiết bị & phương tiện", "id": "Peralatan & Armada", "tr": "Ekipman ve Filo",
        "nl": "Materieel & wagenpark", "pl": "Sprzęt i flota", "cs": "Vybavení a vozový park",
        "sv": "Utrustning & fordon", "no": "Utstyr og flåte", "da": "Udstyr og flåde",
        "fi": "Kalusto ja laitteet", "ro": "Echipamente și flotă", "bg": "Оборудване и автопарк",
        "hr": "Oprema i vozni park",
    },
    "nav.resources": {
        "de": "Ressourcen & Personal", "fr": "Ressources & équipes", "es": "Recursos y personal",
        "it": "Risorse e personale", "pt": "Recursos e equipas", "ru": "Ресурсы и бригады",
        "zh": "资源与人员", "ja": "リソース・人員", "ko": "리소스 및 인력",
        "ar": "الموارد والطاقم", "hi": "संसाधन और दल", "th": "ทรัพยากรและทีมงาน",
        "vi": "Tài nguyên & đội ngũ", "id": "Sumber Daya & Tim", "tr": "Kaynaklar ve Ekip",
        "nl": "Middelen & personeel", "pl": "Zasoby i załoga", "cs": "Zdroje a personál",
        "sv": "Resurser & personal", "no": "Ressurser og mannskap", "da": "Ressourcer og mandskab",
        "fi": "Resurssit ja henkilöstö", "ro": "Resurse și echipe", "bg": "Ресурси и екипи",
        "hr": "Resursi i osoblje",
    },
    "nav.service": {
        "de": "Service & Wartung", "fr": "Service & maintenance", "es": "Servicio y mantenimiento",
        "it": "Servizio e manutenzione", "pt": "Serviço e manutenção", "ru": "Сервис и обслуживание",
        "zh": "服务与维护", "ja": "サービス・保守", "ko": "서비스 및 유지보수",
        "ar": "الخدمة والصيانة", "hi": "सेवा और रखरखाव", "th": "บริการและบำรุงรักษา",
        "vi": "Dịch vụ & bảo trì", "id": "Layanan & Pemeliharaan", "tr": "Servis ve Bakım",
        "nl": "Service & onderhoud", "pl": "Serwis i konserwacja", "cs": "Servis a údržba",
        "sv": "Service & underhåll", "no": "Service og vedlikehold", "da": "Service og vedligehold",
        "fi": "Huolto ja kunnossapito", "ro": "Service și mentenanță", "bg": "Сервиз и поддръжка",
        "hr": "Servis i održavanje",
    },
    "nav.portal": {
        "de": "Nachunternehmer-Portal", "fr": "Portail sous-traitants", "es": "Portal de subcontratistas",
        "it": "Portale subappaltatori", "pt": "Portal de subempreiteiros", "ru": "Портал субподрядчиков",
        "zh": "分包商门户", "ja": "下請業者ポータル", "ko": "협력업체 포털",
        "ar": "بوابة المقاولين الفرعيين", "hi": "उपठेकेदार पोर्टल", "th": "พอร์ทัลผู้รับเหมาช่วง",
        "vi": "Cổng nhà thầu phụ", "id": "Portal Subkontraktor", "tr": "Alt Yüklenici Portalı",
        "nl": "Onderaannemersportaal", "pl": "Portal podwykonawców", "cs": "Portál subdodavatelů",
        "sv": "Underentreprenörsportal", "no": "Underentreprenørportal", "da": "Underentreprenørportal",
        "fi": "Aliurakoitsijaportaali", "ro": "Portal subantreprenori", "bg": "Портал за подизпълнители",
        "hr": "Portal podizvođača",
    },
    "nav.crm": {
        # CRM is universal acronym — keep but locales often use "ЦРМ" or full form
        "de": "CRM", "fr": "CRM", "es": "CRM", "it": "CRM", "pt": "CRM",
        "ru": "CRM", "zh": "客户关系管理 (CRM)", "ja": "CRM (顧客管理)", "ko": "CRM (고객 관리)",
        "ar": "إدارة العلاقات (CRM)", "hi": "CRM (ग्राहक प्रबंधन)", "th": "CRM (จัดการลูกค้า)",
        "vi": "CRM (Quản lý khách hàng)", "id": "CRM (Manajemen Pelanggan)", "tr": "CRM (Müşteri Yönetimi)",
        "nl": "CRM", "pl": "CRM", "cs": "CRM",
        "sv": "CRM", "no": "CRM", "da": "CRM",
        "fi": "CRM", "ro": "CRM", "bg": "CRM",
        "hr": "CRM",
    },
    "nav.contracts": {
        "de": "Verträge", "fr": "Contrats", "es": "Contratos",
        "it": "Contratti", "pt": "Contratos", "ru": "Контракты",
        "zh": "合同", "ja": "契約", "ko": "계약",
        "ar": "العقود", "hi": "अनुबंध", "th": "สัญญา",
        "vi": "Hợp đồng", "id": "Kontrak", "tr": "Sözleşmeler",
        "nl": "Contracten", "pl": "Kontrakty", "cs": "Smlouvy",
        "sv": "Kontrakt", "no": "Kontrakter", "da": "Kontrakter",
        "fi": "Sopimukset", "ro": "Contracte", "bg": "Договори",
        "hr": "Ugovori",
    },
    "nav.subcontractors": {
        "de": "Nachunternehmer", "fr": "Sous-traitants", "es": "Subcontratistas",
        "it": "Subappaltatori", "pt": "Subempreiteiros", "ru": "Субподрядчики",
        "zh": "分包商", "ja": "下請業者", "ko": "협력업체",
        "ar": "المقاولون الفرعيون", "hi": "उपठेकेदार", "th": "ผู้รับเหมาช่วง",
        "vi": "Nhà thầu phụ", "id": "Subkontraktor", "tr": "Alt Yükleniciler",
        "nl": "Onderaannemers", "pl": "Podwykonawcy", "cs": "Subdodavatelé",
        "sv": "Underentreprenörer", "no": "Underentreprenører", "da": "Underentreprenører",
        "fi": "Aliurakoitsijat", "ro": "Subantreprenori", "bg": "Подизпълнители",
        "hr": "Podizvođači",
    },
    "nav.bid_management": {
        "de": "Angebotsmanagement", "fr": "Gestion des offres", "es": "Gestión de ofertas",
        "it": "Gestione offerte", "pt": "Gestão de propostas", "ru": "Управление тендерами",
        "zh": "投标管理", "ja": "入札管理", "ko": "입찰 관리",
        "ar": "إدارة العطاءات", "hi": "बोली प्रबंधन", "th": "การจัดการประมูล",
        "vi": "Quản lý đấu thầu", "id": "Manajemen Penawaran", "tr": "Teklif Yönetimi",
        "nl": "Offertebeheer", "pl": "Zarządzanie ofertami", "cs": "Správa nabídek",
        "sv": "Anbudshantering", "no": "Anbudsstyring", "da": "Tilbudsstyring",
        "fi": "Tarjoushallinta", "ro": "Managementul ofertelor", "bg": "Управление на оферти",
        "hr": "Upravljanje ponudama",
    },
    "nav.variations": {
        "de": "Nachträge", "fr": "Avenants", "es": "Modificaciones",
        "it": "Varianti", "pt": "Aditivos", "ru": "Доп. соглашения",
        "zh": "变更单", "ja": "変更指示", "ko": "변경 지시",
        "ar": "أوامر التغيير", "hi": "परिवर्तन आदेश", "th": "ใบสั่งเปลี่ยนแปลง",
        "vi": "Lệnh thay đổi", "id": "Variasi", "tr": "Değişiklik Emirleri",
        "nl": "Meerwerken", "pl": "Zmiany umowy", "cs": "Změnové listy",
        "sv": "Ändringsorder", "no": "Endringsordrer", "da": "Ændringsordrer",
        "fi": "Muutostyöt", "ro": "Modificări contract", "bg": "Анекси",
        "hr": "Izmjene ugovora",
    },
    "nav.supplier_catalogs": {
        "de": "Lieferantenkataloge", "fr": "Catalogues fournisseurs", "es": "Catálogos de proveedores",
        "it": "Cataloghi fornitori", "pt": "Catálogos de fornecedores", "ru": "Каталоги поставщиков",
        "zh": "供应商目录", "ja": "サプライヤーカタログ", "ko": "공급업체 카탈로그",
        "ar": "كتالوجات الموردين", "hi": "आपूर्तिकर्ता कैटलॉग", "th": "แคตตาล็อกซัพพลายเออร์",
        "vi": "Danh mục nhà cung cấp", "id": "Katalog Pemasok", "tr": "Tedarikçi Katalogları",
        "nl": "Leverancierscatalogi", "pl": "Katalogi dostawców", "cs": "Katalogy dodavatelů",
        "sv": "Leverantörskataloger", "no": "Leverandørkataloger", "da": "Leverandørkataloger",
        "fi": "Toimittajaluettelot", "ro": "Cataloage furnizori", "bg": "Каталози на доставчици",
        "hr": "Katalozi dobavljača",
    },
    "nav.property_dev": {
        "de": "Projektentwicklung", "fr": "Promotion immobilière", "es": "Desarrollo inmobiliario",
        "it": "Sviluppo immobiliare", "pt": "Desenvolvimento imobiliário", "ru": "Девелопмент",
        "zh": "房地产开发", "ja": "不動産開発", "ko": "부동산 개발",
        "ar": "التطوير العقاري", "hi": "संपत्ति विकास", "th": "พัฒนาอสังหาริมทรัพย์",
        "vi": "Phát triển bất động sản", "id": "Pengembangan Properti", "tr": "Gayrimenkul Geliştirme",
        "nl": "Projectontwikkeling", "pl": "Deweloperka", "cs": "Developerství",
        "sv": "Fastighetsutveckling", "no": "Eiendomsutvikling", "da": "Ejendomsudvikling",
        "fi": "Kiinteistökehitys", "ro": "Dezvoltare imobiliară", "bg": "Девелопмънт",
        "hr": "Razvoj nekretnina",
    },
    "nav.schedule_advanced": {
        "de": "Erweiterter Terminplan", "fr": "Planning avancé", "es": "Cronograma avanzado",
        "it": "Pianificazione avanzata", "pt": "Cronograma avançado", "ru": "Расширенный график",
        "zh": "高级进度计划", "ja": "高度なスケジュール", "ko": "고급 일정",
        "ar": "جدول زمني متقدم", "hi": "उन्नत अनुसूची", "th": "ตารางเวลาขั้นสูง",
        "vi": "Lịch trình nâng cao", "id": "Jadwal Lanjutan", "tr": "Gelişmiş Zamanlama",
        "nl": "Geavanceerd schema", "pl": "Zaawansowany harmonogram", "cs": "Pokročilý harmonogram",
        "sv": "Avancerat schema", "no": "Avansert tidsplan", "da": "Avanceret tidsplan",
        "fi": "Edistynyt aikataulu", "ro": "Program avansat", "bg": "Разширен график",
        "hr": "Napredni raspored",
    },
    "nav.qms": {
        "de": "Qualitätsmanagement", "fr": "Gestion qualité", "es": "Gestión de calidad",
        "it": "Gestione qualità", "pt": "Gestão da qualidade", "ru": "Управление качеством",
        "zh": "质量管理", "ja": "品質管理", "ko": "품질 관리",
        "ar": "إدارة الجودة", "hi": "गुणवत्ता प्रबंधन", "th": "การจัดการคุณภาพ",
        "vi": "Quản lý chất lượng", "id": "Manajemen Kualitas", "tr": "Kalite Yönetimi",
        "nl": "Kwaliteitsbeheer", "pl": "Zarządzanie jakością", "cs": "Řízení kvality",
        "sv": "Kvalitetsstyrning", "no": "Kvalitetsstyring", "da": "Kvalitetsstyring",
        "fi": "Laadunhallinta", "ro": "Managementul calității", "bg": "Управление на качеството",
        "hr": "Upravljanje kvalitetom",
    },
    "nav.hse_advanced": {
        "de": "HSE-Management", "fr": "Gestion HSE", "es": "Gestión HSE",
        "it": "Gestione HSE", "pt": "Gestão HSE", "ru": "Управление HSE",
        "zh": "HSE 管理", "ja": "HSE 管理", "ko": "HSE 관리",
        "ar": "إدارة HSE", "hi": "HSE प्रबंधन", "th": "การจัดการ HSE",
        "vi": "Quản lý HSE", "id": "Manajemen HSE", "tr": "HSE Yönetimi",
        "nl": "HSE-management", "pl": "Zarządzanie HSE", "cs": "Řízení HSE",
        "sv": "HSE-hantering", "no": "HSE-styring", "da": "HSE-styring",
        "fi": "HSE-hallinta", "ro": "Management HSE", "bg": "HSE управление",
        "hr": "Upravljanje HSE",
    },
    "nav.carbon": {
        "de": "CO₂ & ESG", "fr": "Carbone & ESG", "es": "Carbono y ESG",
        "it": "Carbonio ed ESG", "pt": "Carbono e ESG", "ru": "Углерод и ESG",
        "zh": "碳与 ESG", "ja": "カーボン・ESG", "ko": "탄소 및 ESG",
        "ar": "الكربون و ESG", "hi": "कार्बन और ESG", "th": "คาร์บอนและ ESG",
        "vi": "Carbon & ESG", "id": "Karbon & ESG", "tr": "Karbon ve ESG",
        "nl": "Koolstof & ESG", "pl": "Węgiel i ESG", "cs": "Uhlík a ESG",
        "sv": "Koldioxid & ESG", "no": "Karbon og ESG", "da": "Kulstof og ESG",
        "fi": "Hiili ja ESG", "ro": "Carbon și ESG", "bg": "Въглерод и ESG",
        "hr": "Ugljik i ESG",
    },
    "nav.bi_dashboards": {
        "de": "BI-Dashboards", "fr": "Tableaux de bord BI", "es": "Paneles BI",
        "it": "Dashboard BI", "pt": "Painéis BI", "ru": "BI-дашборды",
        "zh": "BI 仪表板", "ja": "BI ダッシュボード", "ko": "BI 대시보드",
        "ar": "لوحات BI", "hi": "BI डैशबोर्ड", "th": "BI แดชบอร์ด",
        "vi": "Bảng điều khiển BI", "id": "Dasbor BI", "tr": "BI Panoları",
        "nl": "BI-dashboards", "pl": "Pulpity BI", "cs": "BI dashboardy",
        "sv": "BI-dashboards", "no": "BI-dashboards", "da": "BI-dashboards",
        "fi": "BI-koontinäytöt", "ro": "Panouri BI", "bg": "BI табла",
        "hr": "BI nadzorne ploče",
    },
    "nav.match_elements": {
        "de": "Element-Abgleich → Kosten", "fr": "Correspondance éléments → coûts",
        "es": "Coincidir elementos → Costos", "it": "Abbina elementi → Costi",
        "pt": "Comparar elementos → Custos", "ru": "Сопоставить элементы → Цены",
        "zh": "元素匹配 → 成本", "ja": "要素マッチ → コスト", "ko": "요소 매칭 → 비용",
        "ar": "مطابقة العناصر → التكاليف", "hi": "तत्व मिलान → लागत",
        "th": "จับคู่องค์ประกอบ → ต้นทุน", "vi": "Khớp phần tử → Chi phí",
        "id": "Cocokkan Elemen → Biaya", "tr": "Eleman Eşleştirme → Maliyet",
        "nl": "Elementen koppelen → Kosten", "pl": "Dopasuj elementy → Koszty",
        "cs": "Spárovat prvky → Náklady", "sv": "Matcha element → Kostnader",
        "no": "Match elementer → Kostnader", "da": "Match elementer → Omkostninger",
        "fi": "Yhdistä elementit → Kustannukset", "ro": "Potrivire elemente → Costuri",
        "bg": "Съпоставяне на елементи → Цени", "hr": "Spoji elemente → Troškovi",
    },
    "nav.group_quality": {
        "de": "Qualität & Sicherheit", "fr": "Qualité & sécurité", "es": "Calidad y seguridad",
        "it": "Qualità e sicurezza", "pt": "Qualidade e segurança", "ru": "Качество и безопасность",
        "zh": "质量与安全", "ja": "品質・安全", "ko": "품질 및 안전",
        "ar": "الجودة والسلامة", "hi": "गुणवत्ता और सुरक्षा", "th": "คุณภาพและความปลอดภัย",
        "vi": "Chất lượng & an toàn", "id": "Kualitas & Keselamatan", "tr": "Kalite ve Güvenlik",
        "nl": "Kwaliteit & veiligheid", "pl": "Jakość i bezpieczeństwo", "cs": "Kvalita a bezpečnost",
        "sv": "Kvalitet & säkerhet", "no": "Kvalitet og sikkerhet", "da": "Kvalitet og sikkerhed",
        "fi": "Laatu ja turvallisuus", "ro": "Calitate și siguranță", "bg": "Качество и безопасност",
        "hr": "Kvaliteta i sigurnost",
    },
    "nav.group_operations": {
        "de": "Baustellenbetrieb", "fr": "Opérations chantier", "es": "Operaciones en obra",
        "it": "Operazioni di cantiere", "pt": "Operações de obra", "ru": "Операции на объекте",
        "zh": "现场运营", "ja": "現場運用", "ko": "현장 운영",
        "ar": "عمليات الموقع", "hi": "क्षेत्र संचालन", "th": "การปฏิบัติงานภาคสนาม",
        "vi": "Vận hành công trường", "id": "Operasi Lapangan", "tr": "Saha Operasyonları",
        "nl": "Bouwplaatsoperaties", "pl": "Operacje budowy", "cs": "Provoz stavby",
        "sv": "Platsdrift", "no": "Driftsoperasjoner", "da": "Pladsoperationer",
        "fi": "Työmaatoiminta", "ro": "Operațiuni de șantier", "bg": "Полеви операции",
        "hr": "Operacije gradilišta",
    },
    "nav.group_operations_desc": {
        "de": "Tagesgeschäft der Baustelle — Servicetickets, Geräte, Bautagebuch, Nachunternehmerportal, Ressourcen",
        "fr": "Opérations quotidiennes du chantier — tickets, équipement, journal, portail sous-traitants, ressources",
        "es": "Operaciones diarias en obra: tickets, equipos, diario, portal de subcontratistas, recursos",
        "it": "Operazioni di cantiere quotidiane — ticket di servizio, attrezzature, giornale, portale subappaltatori, risorse",
        "pt": "Operações diárias na obra — chamados, equipamentos, diário, portal de subempreiteiros, recursos",
        "ru": "Ежедневная работа на стройплощадке — заявки, оборудование, журнал, портал субподрядчиков, ресурсы",
        "zh": "现场日常运营 — 服务工单、设备、日志、分包商门户、资源",
        "ja": "現場の日常運用 — サービス、機材、日報、下請ポータル、リソース",
        "ko": "현장 일일 운영 — 서비스, 장비, 일지, 협력업체 포털, 리소스",
        "ar": "العمليات اليومية في الموقع — تذاكر الخدمة، المعدات، اليوميات، بوابة المقاولين الفرعيين، الموارد",
        "hi": "दैनिक स्थल संचालन — सेवा टिकट, उपकरण, डायरी, उपठेकेदार पोर्टल, संसाधन",
        "th": "ปฏิบัติงานหน้างานประจำวัน — ทิคเก็ตบริการ อุปกรณ์ บันทึก พอร์ทัลผู้รับเหมาช่วง ทรัพยากร",
        "vi": "Vận hành công trường hàng ngày — phiếu dịch vụ, thiết bị, nhật ký, cổng nhà thầu phụ, tài nguyên",
        "id": "Operasi lapangan harian — tiket layanan, peralatan, buku harian, portal subkontraktor, sumber daya",
        "tr": "Günlük saha operasyonları — servis biletleri, ekipman, günlük, alt yüklenici portalı, kaynaklar",
        "nl": "Dagelijkse bouwplaatsoperaties — servicetickets, materieel, dagboek, onderaannemersportaal, middelen",
        "pl": "Codzienne operacje budowy — zgłoszenia serwisowe, sprzęt, dziennik, portal podwykonawców, zasoby",
        "cs": "Každodenní provoz stavby — servisní tikety, vybavení, deník, portál subdodavatelů, zdroje",
        "sv": "Daglig platsdrift — serviceärenden, utrustning, dagbok, underentreprenörsportal, resurser",
        "no": "Daglig driftsoperasjon — servicebilletter, utstyr, dagbok, underentreprenørportal, ressurser",
        "da": "Daglige pladsoperationer — servicetickets, udstyr, dagbog, underentreprenørportal, ressourcer",
        "fi": "Päivittäinen työmaatoiminta — palvelutiketit, kalusto, päiväkirja, aliurakoitsijaportaali, resurssit",
        "ro": "Operațiuni zilnice de șantier — tichete servicii, echipamente, jurnal, portal subantreprenori, resurse",
        "bg": "Ежедневни операции на обекта — заявки, оборудване, дневник, портал на подизпълнители, ресурси",
        "hr": "Svakodnevne operacije gradilišta — servisni tiketi, oprema, dnevnik, portal podizvođača, resursi",
    },
    "nav.group_commercial": {
        "de": "Kommerziell", "fr": "Commercial", "es": "Comercial",
        "it": "Commerciale", "pt": "Comercial", "ru": "Коммерческая часть",
        "zh": "商务", "ja": "商務", "ko": "상업",
        "ar": "تجاري", "hi": "वाणिज्यिक", "th": "เชิงพาณิชย์",
        "vi": "Thương mại", "id": "Komersial", "tr": "Ticari",
        "nl": "Commercieel", "pl": "Komercyjne", "cs": "Obchodní",
        "sv": "Kommersiellt", "no": "Kommersielt", "da": "Kommercielt",
        "fi": "Kaupallinen", "ro": "Comercial", "bg": "Търговско",
        "hr": "Komercijalno",
    },
    "nav.group_commercial_desc": {
        "de": "Kommerzielle Pipeline — CRM, Verträge, Angebote, Nachträge, Lieferanten, Projektentwicklung",
        "fr": "Pipeline commercial — CRM, contrats, offres, avenants, fournisseurs, promotion immobilière",
        "es": "Cadena comercial: CRM, contratos, ofertas, modificaciones, proveedores, desarrollo inmobiliario",
        "it": "Pipeline commerciale — CRM, contratti, offerte, varianti, fornitori, sviluppo immobiliare",
        "pt": "Pipeline comercial — CRM, contratos, propostas, aditivos, fornecedores, desenvolvimento imobiliário",
        "ru": "Коммерческий поток — CRM, контракты, тендеры, доп. соглашения, поставщики, девелопмент",
        "zh": "商务线 — 客户关系、合同、投标、变更、供应商、房地产开发",
        "ja": "商務パイプライン — CRM、契約、入札、変更、サプライヤー、不動産開発",
        "ko": "상업 파이프라인 — CRM, 계약, 입찰, 변경, 공급업체, 부동산 개발",
        "ar": "خط الأعمال التجاري — CRM، العقود، العطاءات، التغييرات، الموردون، التطوير العقاري",
        "hi": "वाणिज्यिक पाइपलाइन — CRM, अनुबंध, बोलियाँ, परिवर्तन, आपूर्तिकर्ता, संपत्ति विकास",
        "th": "ไปป์ไลน์เชิงพาณิชย์ — CRM สัญญา ประมูล เปลี่ยนแปลง ซัพพลายเออร์ พัฒนาอสังหา",
        "vi": "Pipeline thương mại — CRM, hợp đồng, đấu thầu, thay đổi, nhà cung cấp, phát triển bất động sản",
        "id": "Pipeline komersial — CRM, kontrak, penawaran, perubahan, pemasok, pengembangan properti",
        "tr": "Ticari pipeline — CRM, sözleşmeler, teklifler, değişiklikler, tedarikçiler, gayrimenkul",
        "nl": "Commerciële pipeline — CRM, contracten, offertes, meerwerken, leveranciers, projectontwikkeling",
        "pl": "Pipeline komercyjny — CRM, kontrakty, oferty, zmiany, dostawcy, deweloperka",
        "cs": "Obchodní pipeline — CRM, smlouvy, nabídky, změny, dodavatelé, developerství",
        "sv": "Kommersiell pipeline — CRM, kontrakt, anbud, ändringar, leverantörer, fastighetsutveckling",
        "no": "Kommersiell pipeline — CRM, kontrakter, anbud, endringer, leverandører, eiendomsutvikling",
        "da": "Kommerciel pipeline — CRM, kontrakter, tilbud, ændringer, leverandører, ejendomsudvikling",
        "fi": "Kaupallinen pipeline — CRM, sopimukset, tarjoukset, muutokset, toimittajat, kiinteistökehitys",
        "ro": "Pipeline comercial — CRM, contracte, oferte, modificări, furnizori, dezvoltare imobiliară",
        "bg": "Търговски поток — CRM, договори, оферти, анекси, доставчици, девелопмънт",
        "hr": "Komercijalni pipeline — CRM, ugovori, ponude, izmjene, dobavljači, razvoj nekretnina",
    },
    "nav.group_bi": {
        "de": "Analytik", "fr": "Analytique", "es": "Analítica",
        "it": "Analitica", "pt": "Analítica", "ru": "Аналитика",
        "zh": "分析", "ja": "分析", "ko": "분석",
        "ar": "تحليلات", "hi": "विश्लेषण", "th": "การวิเคราะห์",
        "vi": "Phân tích", "id": "Analitik", "tr": "Analitik",
        "nl": "Analytics", "pl": "Analityka", "cs": "Analytika",
        "sv": "Analys", "no": "Analyse", "da": "Analyse",
        "fi": "Analytiikka", "ro": "Analiză", "bg": "Анализ",
        "hr": "Analitika",
    },
    "nav.group_bi_desc": {
        "de": "BI-Dashboards auf Basis von Warehouse-Projektionen",
        "fr": "Tableaux de bord BI basés sur des projections d'entrepôt de données",
        "es": "Paneles BI sobre proyecciones del almacén de datos",
        "it": "Dashboard BI basate su proiezioni del data warehouse",
        "pt": "Painéis BI sobre projeções do data warehouse",
        "ru": "BI-дашборды поверх проекций хранилища данных",
        "zh": "基于数据仓库投影的 BI 仪表板",
        "ja": "データウェアハウス投影上の BI ダッシュボード",
        "ko": "데이터 웨어하우스 프로젝션 기반 BI 대시보드",
        "ar": "لوحات BI مبنية على إسقاطات مستودع البيانات",
        "hi": "वेयरहाउस प्रोजेक्शन पर निर्मित BI डैशबोर्ड",
        "th": "BI แดชบอร์ดสร้างจากการฉายข้อมูลคลัง",
        "vi": "Bảng điều khiển BI dựa trên hình chiếu kho dữ liệu",
        "id": "Dasbor BI di atas proyeksi gudang data",
        "tr": "Veri ambarı projeksiyonları üzerine kurulu BI panoları",
        "nl": "BI-dashboards op basis van datawarehouse-projecties",
        "pl": "Pulpity BI oparte na projekcjach hurtowni danych",
        "cs": "BI dashboardy postavené na projekcích datového skladu",
        "sv": "BI-dashboards byggda på datalagerprojektioner",
        "no": "BI-dashboards bygget på datavarehusprojekter",
        "da": "BI-dashboards bygget på datavarehusprojektioner",
        "fi": "BI-koontinäytöt tietovarastoprojektioiden päällä",
        "ro": "Panouri BI construite pe proiecții de depozit de date",
        "bg": "BI табла, изградени върху проекции на данни",
        "hr": "BI nadzorne ploče izgrađene na projekcijama skladišta podataka",
    },
}


def patch_locale(code: str) -> tuple[int, int]:
    """‌⁠‍Patch one locale file. Returns (replaced, skipped)."""
    path = ROOT / f'frontend/src/app/locales/{code}.ts'
    text = path.read_text(encoding='utf-8')
    original = text
    replaced = skipped = 0

    for key, by_locale in TRANSLATIONS.items():
        target = by_locale.get(code)
        if target is None:
            continue
        # Match "key": "..." (any value, may include escaped chars)
        pattern = (
            r'("' + re.escape(key) + r'"\s*:\s*")'
            r'((?:[^"\\]|\\.)*)'
            r'(")'
        )
        # Escape target for inside JSON-ish string literal
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
    print(f"Patching {len(TRANSLATIONS)} keys across {len(locales)} locales...")
    for code in locales:
        r, s = patch_locale(code)
        total_r += r
        total_s += s
        print(f"  {code:5s}: replaced={r:3d}  skipped={s:3d}")
    print(f"\nTOTAL: {total_r} replacements, {total_s} skipped (key missing in locale)")


if __name__ == '__main__':
    main()
