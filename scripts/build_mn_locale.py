# -*- coding: utf-8 -*-
"""‌⁠‍
Builds a complete frontend/src/app/locales/mn.ts (Mongolian translation)
from the source-of-truth en.ts.

Strategy:
  1. Parse en.ts into key->english_value pairs.
  2. Preserve existing translations from the current mn.ts stub.
  3. For every other key, translate the English value using:
       a) exact-match dictionary on the full string;
       b) word/phrase dictionary for short labels;
       c) pattern templates for common phrasings (e.g. "Search X...", "No X yet").
       d) fall back to the English string if no rule fires (i18next will use it,
          and a human translator can replace it incrementally).
  4. Re-emit the same TypeScript shape as en.ts (sorted keys, "translation" wrapper).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN_PATH = ROOT / "frontend" / "src" / "app" / "locales" / "en.ts"
MN_PATH = ROOT / "frontend" / "src" / "app" / "locales" / "mn.ts"


# ---------------------------------------------------------------------------
# 1. existing mn.ts translations (manually authored, must be preserved)
# ---------------------------------------------------------------------------

EXISTING_MN: dict[str, str] = {
    "nav.dashboard": "Хяналтын самбар",
    "nav.projects": "Төслүүд",
    "nav.boq": "Ажил материалын жагсаалт",
    "nav.costs": "Үнийн мэдээлэл",
    "nav.assemblies": "Нэгдэл",
    "nav.takeoff": "PDF-ээс хэмжээ авах",
    "nav.takeoff_overview": "Хэмжээ авалт",
    "nav.cad_takeoff": "CAD/BIM хэмжээ авах",
    "nav.schedule": "4D хуваарь",
    "nav.5d_cost_model": "5D өртөгийн загвар",
    "nav.reports": "Тайлан",
    "nav.tendering": "Тендер",
    "nav.documents": "Баримт бичиг",
    "nav.photos": "Зураг",
    "nav.project_files": "Төслийн файлууд",
    "nav.modules": "Модулиуд",
    "nav.settings": "Тохиргоо",
    "nav.about": "Тухай",
    "nav.validation": "Шалгалт",
    "nav.analytics": "Аналитик",
    "nav.help": "Тусламж",
    "nav.docs": "Баримт бичиг",
    "nav.github": "GitHub репозитор",
    "nav.resource_catalog": "Нөөцийн каталог",
    "nav.templates": "Загварууд",
    "nav.change_orders": "Өөрчлөлтийн захиалга",
    "nav.risk_register": "Эрсдэлийн бүртгэл",
    "nav.sustainability": "Тогтвортой байдал",
    "nav.ai_estimate": "Хурдан тооцоо (AI)",
    "nav.ai_advisor": "AI зөвлөх",
    "common.save": "Хадгалах",
    "common.cancel": "Цуцлах",
    "common.close": "Хаах",
    "common.open": "Нээх",
    "common.delete": "Устгах",
    "common.edit": "Засах",
    "common.create": "Үүсгэх",
    "common.search": "Хайх",
    "common.loading": "Ачаалж байна...",
    "common.yes": "Тийм",
    "common.no": "Үгүй",
    "common.confirm": "Баталгаажуулах",
    "common.ok": "OK",
    "common.back": "Буцах",
    "common.next": "Дараах",
    "common.previous": "Өмнөх",
    "common.add": "Нэмэх",
    "common.remove": "Хасах",
    "common.copy": "Хуулах",
    "common.export": "Экспорт",
    "common.import": "Импорт",
    "common.download": "Татах",
    "common.upload": "Илгээх",
    "common.refresh": "Шинэчлэх",
    "common.filter": "Шүүх",
    "common.sort": "Эрэмбэлэх",
    "common.actions": "Үйлдэл",
    "common.settings": "Тохиргоо",
    "common.help": "Тусламж",
    "auth.login": "Нэвтрэх",
    "auth.logout": "Гарах",
    "auth.email": "Имэйл",
    "auth.password": "Нууц үг",
    "auth.signup": "Бүртгүүлэх",
    "support.button_label": "Дэмжих",
    "support.button_tooltip": "Төслийг дэмжих — одоор үнэлэх эсвэл түгээх",
    "support.button_aria": "Биднийг дэмжих",
    "support.modal_title": "OpenConstructionERP-ийг өсөхөд тусална уу",
    "support.modal_subtitle": (
        "Бид бүх кодыг нээлттэй бичиж, бүх боломжуудыг үнэгүй гаргадаг. "
        "Танаас гарах хоёр жижиг үйлдэл хөгжлийг үргэлжлүүлэхэд тусална — "
        "үнэгүй боловч маш том нөлөөтэй."
    ),
    "support.action_star_title": "GitHub дээр одоор үнэлээрэй",
    "support.action_star_body": (
        "30 секунд. Одод нь шинэ багуудад төслийг олох боломжийг олгодог "
        "бөгөөд дараагийн хувилбарт зориулсан цаг гаргахад туслана."
    ),
    "support.action_share_title": "Хамт олон эсвэл сүлжээгээрээ түгээх",
    "support.action_share_body": (
        "LinkedIn эсвэл X/Twitter дээрх нэг пост нь олон тооцоолуур, төлөвлөгч, "
        "BIM менежеруудад хүрнэ. Нээлттэй эх барилгын программ хангамжийг "
        "газрын зурагт оруулахад тусална уу."
    ),
    "support.share_twitter": "X дээр нийтлэх",
    "support.share_linkedin": "LinkedIn дээр нийтлэх",
    "support.share_copy": "Текст + холбоосыг хуулах",
    "support.share_copied": "Хуулагдлаа!",
    "support.action_case_study_title": "Кейс судалгаа, видео эсвэл нийтлэлтэй юу?",
    "support.action_case_study_tag": "Бид түгээнэ",
    "support.action_case_study_body": (
        "OpenConstructionERP-ийг хэрхэн ашиглаж буйгаа бидэнд харуулаарай — "
        "видео, кейс судалгаа, LinkedIn нийтлэл. Бид түүнийг "
        "DataDrivenConstruction-ийн мэдээллийн товхимол болон сошиал сувгуудаар "
        "нийтлэх бөгөөд эдгээрт хэдэн арван мянган барилгын мэргэжилтэн, "
        "салбарын ахмад шинжээчид нэгдсэн байдаг. Холбоос эсвэл ноорогоо илгээнэ үү: "
    ),
    "support.thanks": (
        "Баярлалаа. Од, түгээлт болгон энэ төслийг үргэлжлүүлэн амьд байлгана — "
        "барилгын хамт олонд зориулж ❤️ -тэй бүтээгдсэн."
    ),
    "error.not_found": "Олдсонгүй",
    "error.unauthorized": "Зөвшөөрөлгүй",
    "error.server_error": "Серверийн алдаа",
    "error.try_again": "Дахин оролдоно уу",

    # --- New sidebar CTA keys (added 2026-05-13) ---
    "nav.add_module": "Модуль нэмэх",
    "nav.add_module_hint": "Өөрөө бүтээх · хөгжүүлэгчийн заавар",
    "nav.request_custom_module": "Захиалгат модуль хүсэх",
    "nav.request_custom_module_hint": "Дутаж байгаа юм байна уу? Бидэнд хэлээрэй",
    "modules.dev_guide": "Модуль бүтээх — хөгжүүлэгчийн заавар",
}


# ---------------------------------------------------------------------------
# 2. exact-match dictionary
#    English string -> Mongolian translation
# ---------------------------------------------------------------------------

EXACT: dict[str, str] = {
    # --- generic verbs / labels ---
    "Save": "Хадгалах",
    "Cancel": "Цуцлах",
    "Close": "Хаах",
    "Open": "Нээх",
    "Delete": "Устгах",
    "Edit": "Засах",
    "Create": "Үүсгэх",
    "Search": "Хайх",
    "Loading...": "Ачаалж байна...",
    "Loading…": "Ачаалж байна…",
    "Yes": "Тийм",
    "No": "Үгүй",
    "Confirm": "Баталгаажуулах",
    "OK": "OK",
    "Back": "Буцах",
    "Next": "Дараах",
    "Previous": "Өмнөх",
    "Add": "Нэмэх",
    "Remove": "Хасах",
    "Copy": "Хуулах",
    "Export": "Экспорт",
    "Import": "Импорт",
    "Download": "Татах",
    "Upload": "Илгээх",
    "Refresh": "Шинэчлэх",
    "Filter": "Шүүх",
    "Sort": "Эрэмбэлэх",
    "Actions": "Үйлдэл",
    "Action": "Үйлдэл",
    "Settings": "Тохиргоо",
    "Help": "Тусламж",
    "Apply": "Хэрэглэх",
    "Reset": "Дахин тохируулах",
    "Clear": "Цэвэрлэх",
    "Clear all": "Бүгдийг цэвэрлэх",
    "Clear All": "Бүгдийг цэвэрлэх",
    "Clear filter": "Шүүлтүүрийг цэвэрлэх",
    "Clear filters": "Шүүлтүүрүүдийг цэвэрлэх",
    "Clear Filters": "Шүүлтүүрүүдийг цэвэрлэх",
    "Clear search": "Хайлтыг цэвэрлэх",
    "Submit": "Илгээх",
    "Send": "Илгээх",
    "Sent": "Илгээгдсэн",
    "Continue": "Үргэлжлүүлэх",
    "Dismiss": "Хаах",
    "Done": "Дууссан",
    "Error": "Алдаа",
    "Success": "Амжилттай",
    "Warning": "Анхааруулга",
    "Info": "Мэдээлэл",
    "Status": "Төлөв",
    "Date": "Огноо",
    "Type": "Төрөл",
    "Name": "Нэр",
    "Title": "Гарчиг",
    "Description": "Тайлбар",
    "Notes": "Тэмдэглэл",
    "Note": "Тэмдэглэл",
    "Category": "Ангилал",
    "Total": "Нийт",
    "Subtotal": "Дэд дүн",
    "Quantity": "Тоо хэмжээ",
    "Unit": "Нэгж",
    "Code": "Код",
    "Rate": "Үнэлгээ",
    "Unit Rate": "Нэгжийн үнэ",
    "Amount": "Дүн",
    "Currency": "Валют",
    "Region": "Бүс",
    "Project": "Төсөл",
    "Projects": "Төслүүд",
    "Item": "Зүйл",
    "Items": "Зүйлүүд",
    "items": "зүйл",
    "Position": "Байрлал",
    "Positions": "Байрлалууд",
    "positions": "байрлал",
    "Section": "Хэсэг",
    "Sections": "Хэсгүүд",
    "sections": "хэсэг",
    "Material": "Материал",
    "Materials": "Материалууд",
    "Labor": "Хөдөлмөр",
    "Equipment": "Тоног төхөөрөмж",
    "Subcontractor": "Туслан гүйцэтгэгч",
    "Other": "Бусад",
    "All": "Бүх",
    "None": "Байхгүй",
    "Active": "Идэвхтэй",
    "Inactive": "Идэвхгүй",
    "Archived": "Архивлагдсан",
    "Pending": "Хүлээгдэж буй",
    "Approved": "Зөвшөөрөгдсөн",
    "Rejected": "Татгалзсан",
    "Draft": "Ноорог",
    "draft": "ноорог",
    "Submitted": "Илгээсэн",
    "Issued": "Гаргасан",
    "Closed": "Хаагдсан",
    "Completed": "Дууссан",
    "Cancelled": "Цуцлагдсан",
    "Reviewed": "Хянагдсан",
    "Under Review": "Хяналтанд",
    "In Progress": "Явагдаж байна",
    "On Track": "Хэвийн",
    "At Risk": "Эрсдэлд",
    "Delayed": "Хойшилсон",
    "Critical": "Чухал",
    "High": "Өндөр",
    "Medium": "Дунд",
    "Low": "Бага",
    "Severity": "Хүндрэлийн зэрэг",
    "Priority": "Чухал зэрэг",
    "Location": "Байршил",
    "Address": "Хаяг",
    "Phone": "Утас",
    "Email": "Имэйл",
    "Company": "Компани",
    "Country": "Улс",
    "Language": "Хэл",
    "Languages": "Хэлүүд",
    "Theme": "Загвар",
    "Light": "Цайвар",
    "Dark": "Бараан",
    "System": "Систем",
    "Profile": "Профайл",
    "Account": "Бүртгэл",
    "Sign in": "Нэвтрэх",
    "Sign In": "Нэвтрэх",
    "Sign Out": "Гарах",
    "Log Out": "Гарах",
    "Sign out": "Гарах",
    "Show": "Харуулах",
    "Hide": "Нуух",
    "Showing": "Харуулж байна",
    "Show all": "Бүгдийг харуулах",
    "Show less": "Бага харуулах",
    "Show more": "Илүү ихийг харуулах",
    "View": "Үзэх",
    "Preview": "Урьдчилан үзэх",
    "Test": "Шалгах",
    "Test Connection": "Холболтыг шалгах",
    "Testing...": "Шалгаж байна...",
    "Restore": "Сэргээх",
    "Duplicate": "Хуулбарлах",
    "Archive": "Архивлах",
    "Configure": "Тохируулах",
    "Connect": "Холбох",
    "Connected": "Холбогдсон",
    "Disconnect": "Салгах",
    "Disconnected": "Салгасан",
    "Install": "Суулгах",
    "Uninstall": "Устгах",
    "Installed": "Суулгасан",
    "Installing...": "Суулгаж байна...",
    "Enable": "Идэвхжүүлэх",
    "Disable": "Идэвхгүй болгох",
    "Manage": "Удирдах",
    "Update": "Шинэчлэх",
    "Updated": "Шинэчлэгдсэн",
    "Created": "Үүсгэгдсэн",
    "Deleted": "Устгагдсан",
    "Saved": "Хадгалагдсан",
    "Saving...": "Хадгалж байна...",
    "Creating...": "Үүсгэж байна...",
    "Adding...": "Нэмж байна...",
    "Importing...": "Импортолж байна...",
    "Exporting...": "Экспортлож байна...",
    "Deactivate": "Идэвхгүй болгох",
    "Activate": "Идэвхжүүлэх",
    "Never": "Хэзээ ч үгүй",
    "Just now": "Дөнгөж сая",
    "just now": "дөнгөж сая",
    "Today": "Өнөөдөр",
    "Yesterday": "Өчигдөр",
    "Earlier": "Өмнө",
    "All Statuses": "Бүх төлөв",
    "All Types": "Бүх төрөл",
    "All Categories": "Бүх ангилал",
    "All Authors": "Бүх зохиогч",
    "All Priorities": "Бүх чухал зэрэг",
    "All Assignees": "Бүх хариуцагч",
    "All Documents": "Бүх баримт бичиг",
    "All Countries": "Бүх улсууд",
    "All Directions": "Бүх чиглэл",
    "All Regions": "Бүх бүс",
    "Reports": "Тайлан",
    "Documents": "Баримт бичиг",
    "Photos": "Зураг",
    "Files": "Файлууд",
    "Document": "Баримт бичиг",
    "Author": "Зохиогч",
    "Comments": "Сэтгэгдэл",
    "Comment": "Сэтгэгдэл",
    "Reply": "Хариулах",
    "Post": "Нийтлэх",
    "(edited)": "(засварласан)",
    "Unknown": "Үл мэдэгдэх",
    "Coming soon": "Удахгүй гарна",
    "Coming Soon": "Удахгүй гарна",
    "Recommended": "Зөвлөмжтэй",
    "Optional": "Заавал биш",
    "optional": "заавал биш",
    "Required": "Шаардлагатай",
    "(empty)": "(хоосон)",
    "(none)": "(байхгүй)",
    "(missing)": "(дутуу)",
    "Mark Complete": "Дууссан гэж тэмдэглэх",
    "Mark Resolved": "Шийдвэрлэсэн гэж тэмдэглэх",
    "Mark Paid": "Төлөгдсөн гэж тэмдэглэх",
    "Mark Awarded": "Олгогдсон гэж тэмдэглэх",
    "Unassigned": "Хариуцагчгүй",
    "Approve": "Зөвшөөрөх",
    "Reject": "Татгалзах",
    "Award": "Олгох",
    "Issue": "Гаргах",
    "Review": "Хянах",
    "Respond": "Хариулах",
    "Generate": "Үүсгэх",
    "Recalculate": "Дахин тооцоолох",
    "Run": "Ажиллуулах",
    "Validate": "Шалгах",
    "Verify": "Баталгаажуулах",
    "Lock": "Түгжих",
    "Unlock": "Түгжээ тайлах",
    "Undo": "Буцаах",
    "Redo": "Дахин хийх",
    "Try again": "Дахин оролдоно уу",
    "Please try again": "Дахин оролдоно уу",
    "Got it": "Ойлголоо",
    "Learn more": "Дэлгэрэнгүй",
    "Get Started": "Эхлэх",
    "Get started": "Эхлэх",
    "Pin": "Зүүх",
    "Unpin": "Зүүснийг тайлах",
    "Source": "Эх сурвалж",
    "Reference": "Лавлагаа",
    "Vendor": "Нийлүүлэгч",
    "Client": "Захиалагч",
    "Recipients": "Хүлээн авагчид",
    "Method": "Арга",
    "Reason": "Шалтгаан",
    "Suggestion": "Санал",
    "Suggested": "Санал болгосон",
    "Applied": "Хэрэглэсэн",
    "Original": "Эх",
    "Revised": "Шинэчилсэн",
    "Variance": "Зөрүү",
    "Forecast": "Урьдчилсан тооцоо",
    "Committed": "Үүрэг авсан",
    "Actual": "Бодит",
    "Planned": "Төлөвлөсөн",
    "Budget": "Төсөв",
    "Tax": "Татвар",
    "VAT": "НӨАТ",
    "Net Total": "Цэвэр дүн",
    "Gross Total": "Бохир дүн",
    "Grand Total": "Нийт дүн",
    "Direct Cost": "Шууд зардал",
    "Discipline": "Мэргэжил",
    "Disciplines": "Мэргэжлүүд",
    "Properties": "Шинж чанарууд",
    "Quantities": "Тоо хэмжээнүүд",
    "Classification": "Ангилал",
    "First page": "Эхний хуудас",
    "Last page": "Сүүлийн хуудас",
    "Open menu": "Цэс нээх",
    "more": "илүү",
    "of": "/",
    "to": "хүртэл",
    "at": "цагт",
    "by": "тус",
    "days": "өдөр",
    "hours": "цаг",
    "Hours": "Цаг",
    "Count": "Тоо",
    "Day": "Өдөр",
    "Week": "Долоо хоног",
    "Month": "Сар",
    "Year": "Жил",

    # --- specific page titles ---
    "Dashboard": "Хяналтын самбар",
    "Bill of Quantities": "Ажил материалын жагсаалт",
    "BOQ": "БМЖ",
    "Cost Database": "Үнийн мэдээллийн сан",
    "Assemblies": "Нэгдлүүд",
    "Resource Catalog": "Нөөцийн каталог",
    "PDF Takeoff": "PDF-ээс хэмжээ авах",
    "CAD/BIM Takeoff": "CAD/BIM хэмжээ авах",
    "Quantity Takeoff": "Тоо хэмжээ авах",
    "Overview": "Тойм",
    "4D Schedule": "4D хуваарь",
    "5D Cost Model": "5D өртөгийн загвар",
    "Validation": "Шалгалт",
    "Tendering": "Тендер",
    "Sustainability": "Тогтвортой байдал",
    "Modules": "Модулиуд",
    "About": "Тухай",
    "Analytics": "Аналитик",
    "AI Estimate": "AI тооцоо",
    "AI Cost Advisor": "AI зардлын зөвлөх",
    "AI Chat": "AI чат",
    "Change Orders": "Өөрчлөлтийн захиалга",
    "Risk Register": "Эрсдэлийн бүртгэл",
    "Project Photos": "Төслийн зураг",
    "Project Files": "Төслийн файлууд",
    "Daily Diary": "Өдрийн тэмдэглэл",
    "Equipment & Fleet": "Тоног төхөөрөмж ба тээвэр",
    "Resources & Crew": "Нөөц ба баг",
    "Service & Maintenance": "Үйлчилгээ ба засвар",
    "Subcontractor Portal": "Туслан гүйцэтгэгчийн портал",
    "CRM": "CRM",
    "Contracts": "Гэрээ",
    "Subcontractors": "Туслан гүйцэтгэгчид",
    "Bid Management": "Тендерийн удирдлага",
    "Variations": "Өөрчлөлтүүд",
    "Supplier Catalogs": "Нийлүүлэгчийн каталог",
    "Property Development": "Үл хөдлөх хөгжүүлэлт",
    "Advanced Schedule": "Дэвшилтэт хуваарь",
    "Quality Management": "Чанарын удирдлага",
    "HSE Management": "HSE удирдлага",
    "Carbon & ESG": "Нүүрстөрөгч ба ESG",
    "BI Dashboards": "BI хяналтын самбар",
    "Templates": "Загварууд",
    "Documentation": "Баримт бичгийн сан",
    "Tasks": "Даалгаврууд",
    "My Tasks": "Миний даалгаврууд",
    "Meetings": "Хурлууд",
    "RFIs": "Лавлагаа (RFI)",
    "Submittals": "Илгээмж",
    "Transmittals": "Дамжуулалт",
    "Contacts": "Холбоо барих",
    "Correspondence": "Захидал харилцаа",
    "Notifications": "Мэдэгдэл",
    "Inspections": "Шалгалт",
    "NCRs": "Үл нийцлийн тайлан",
    "Safety": "Аюулгүй байдал",
    "Field Reports": "Талбайн тайлан",
    "Punch List": "Шалгах жагсаалт",
    "Risk Analysis": "Эрсдэлийн шинжилгээ",
    "Markups & Annotations": "Тэмдэглэгээ ба тайлбар",
    "Common Data Environment": "Нийтлэг өгөгдлийн орчин",
    "Finance": "Санхүү",
    "Procurement": "Худалдан авалт",
    "Reports": "Тайлан",
    "Reporting": "Тайлагнал",
    "User Management": "Хэрэглэгчийн удирдлага",
    "Architecture Map": "Архитектурын зураг",
    "Project Intelligence": "Төслийн интеллект",
    "Estimation Dashboard": "Тооцоолох самбар",
    "Requirements": "Шаардлага",

    # --- Login / auth ---
    "Sign in": "Нэвтрэх",
    "Email": "Имэйл",
    "Password": "Нууц үг",
    "Confirm Password": "Нууц үгийг баталгаажуулах",
    "Full Name": "Бүтэн нэр",
    "Forgot password?": "Нууц үг мартсан уу?",
    "Create account": "Бүртгэл үүсгэх",
    "Already have an account?": "Бүртгэлтэй юу?",
    "Don't have an account?": "Бүртгэлгүй юу?",
    "Back to sign in": "Нэвтрэх рүү буцах",
    "Check your email": "Имэйлээ шалгана уу",
    "Remember me for 30 days": "Намайг 30 хоног санах",
    "Invalid email or password": "Имэйл эсвэл нууц үг буруу",
    "Minimum 8 characters": "Хамгийн багадаа 8 тэмдэгт",
    "Strong": "Хүчтэй",
    "Medium": "Дунд",
    "Weak": "Сул",
    "Send reset link": "Сэргээх холбоос илгээх",
    "Passwords do not match": "Нууц үгүүд таарахгүй байна",

    # --- Dashboard ---
    "Welcome to OpenConstructionERP": "OpenConstructionERP-д тавтай морил",
    "Recent Projects": "Сүүлийн үеийн төслүүд",
    "Recent Activity": "Сүүлийн үеийн үйл ажиллагаа",
    "Quick Actions": "Хурдан үйлдэл",
    "Quick Start Estimate": "Хурдан тооцоо эхлүүлэх",
    "Total Projects": "Нийт төсөл",
    "Total BOQs": "Нийт БМЖ",
    "Total Value": "Нийт үнэ цэн",
    "Total Budget": "Нийт төсөв",
    "Active Projects": "Идэвхтэй төслүүд",
    "Quality Score": "Чанарын оноо",
    "Getting Started": "Эхлэх",
    "New Project": "Шинэ төсөл",
    "New BOQ": "Шинэ БМЖ",
    "New Task": "Шинэ даалгавар",
    "Create BOQ": "БМЖ үүсгэх",
    "Import Database": "Мэдээллийн сан импортлох",
    "Demo": "Демо",
    "Star on GitHub": "GitHub дээр одоор үнэлэх",
    "Become a Sponsor": "Ивээн тэтгэгч болох",
    "Professional Consulting": "Мэргэжлийн зөвлөгөө",

    # --- Common BOQ fields ---
    "BOQ Name": "БМЖ-ийн нэр",
    "Section": "Хэсэг",
    "Quality": "Чанар",
    "Quality Breakdown": "Чанарын задаргаа",
    "Comments ({{count}})": "Сэтгэгдэл ({{count}})",
    "BOQ Editor": "БМЖ засварлагч",
    "Bill of Quantities positions": "БМЖ-ийн байрлалууд",
    "BOQ Comparison": "БМЖ харьцуулалт",
    "Variant": "Хувилбар",
    "Variants": "Хувилбарууд",
    "Markups & Overheads": "Нэмэгдэл ба нэмэгдэл зардал",
    "Apply Regional Template": "Бүсийн загвар хэрэглэх",
    "Add Markup": "Нэмэгдэл нэмэх",
    "Overhead": "Нэмэгдэл зардал",
    "Profit": "Ашиг",
    "Contingency": "Нөөц",
    "Insurance": "Даатгал",
    "Bond": "Баталгаа",
    "Active": "Идэвхтэй",
    "Percentage": "Хувь",
    "From Database": "Мэдээллийн сангаас",
    "From Catalog": "Каталогоос",
    "From Assembly": "Нэгдлээс",
    "filtered": "шүүгдсэн",
    "errors": "алдаа",
    "warnings": "анхааруулга",

    # --- Settings ---
    "AI Configuration": "AI тохиргоо",
    "AI Provider": "AI үйлчилгээ үзүүлэгч",
    "API Key": "API түлхүүр",
    "Save Settings": "Тохиргоог хадгалах",
    "Appearance": "Гадаад төрх",
    "Language & Region": "Хэл ба бүс",
    "Profile": "Профайл",
    "Member since": "Гишүүн болсон",
    "Status": "Төлөв",
    "Show": "Харуулах",
    "Hide": "Нуух",
    "Regional Settings": "Бүсийн тохиргоо",
    "Setup Wizard": "Тохируулгын зөвлөгч",
    "Open Setup Wizard": "Тохируулгын зөвлөгчийг нээх",
    "Interface Mode": "Интерфэйсийн горим",
    "Measurement System": "Хэмжээний систем",
    "Date Format": "Огнооны формат",
    "Number Format": "Тооны формат",
    "Paper Size": "Цаасны хэмжээ",
    "Timezone": "Цагийн бүс",
    "Translation Manager": "Орчуулгын менежер",
    "Simple": "Энгийн",
    "Advanced": "Дэвшилтэт",
    "Toggle theme": "Загвар сэлгэх",

    # --- Tendering ---
    "Tender Package": "Тендерийн багц",
    "New Tender Package": "Шинэ тендерийн багц",
    "Create Package": "Багц үүсгэх",
    "Bid Comparison": "Үнийн санал харьцуулалт",
    "Bid Totals Overview": "Үнийн саналын нийт дүн",
    "Bids Received": "Хүлээн авсан үнийн санал",
    "Total Amount": "Нийт дүн",
    "Lowest": "Хамгийн бага",
    "Highest": "Хамгийн өндөр",
    "Recommendation": "Зөвлөмж",
    "Add Bid": "Үнийн санал нэмэх",
    "Submit Bid": "Үнийн санал илгээх",
    "Award contract?": "Гэрээг олгох уу?",
    "Mark Awarded": "Олгогдсон гэж тэмдэглэх",
    "Source BOQ": "Эх БМЖ",
    "Company Name": "Компанийн нэр",
    "Contact Email": "Холбоо барих имэйл",
    "Deadline": "Эцсийн хугацаа",
    "Evaluate Bids": "Үнийн саналыг үнэлэх",
    "Start Collecting": "Цуглуулж эхлэх",

    # --- Validation ---
    "Run Validation": "Шалгалт ажиллуулах",
    "Quality Score": "Чанарын оноо",
    "Excellent": "Маш сайн",
    "Good": "Сайн",
    "Needs Review": "Хяналт шаардлагатай",
    "Poor": "Муу",
    "Errors": "Алдаанууд",
    "Warnings": "Анхааруулга",
    "Passed": "Тэнцсэн",
    "Failed": "Бүтэлгүйтсэн",
    "Rules checked": "Шалгасан дүрэм",
    "Rule sets": "Дүрмийн багц",
    "Duration": "Хугацаа",
    "Results": "Үр дүн",
    "Summary": "Хураангуй",
    "Element": "Элемент",
    "Show All Issues": "Бүх асуудлыг харуулах",
    "Export Report PDF": "Тайланг PDF болгож экспортлох",

    # --- Schedule ---
    "Activity": "Үйл ажиллагаа",
    "Activity Name": "Үйл ажиллагааны нэр",
    "Add Activity": "Үйл ажиллагаа нэмэх",
    "Create Activity": "Үйл ажиллагаа үүсгэх",
    "Create Schedule": "Хуваарь үүсгэх",
    "Schedule Name": "Хуваарийн нэр",
    "Critical Path": "Эгзэгтэй зам",
    "Start": "Эхлэх",
    "End": "Дуусах",
    "Start Date": "Эхлэх огноо",
    "End Date": "Дуусах огноо",
    "Task": "Даалгавар",
    "Milestone": "Үе шат",
    "WBS Code": "WBS код",
    "Generate from BOQ": "БМЖ-ээс үүсгэх",
    "Risk Analysis (PERT)": "Эрсдэлийн шинжилгээ (PERT)",

    # --- Reports ---
    "BOQ Report": "БМЖ-ийн тайлан",
    "Cost Report": "Зардлын тайлан",
    "Validation Report": "Шалгалтын тайлан",
    "Schedule Report": "Хуваарийн тайлан",
    "5D Cost Report": "5D зардлын тайлан",
    "Cash Flow Forecast": "Мөнгөн урсгалын урьдчилсан тооцоо",
    "Change Order Register": "Өөрчлөлтийн захиалгын бүртгэл",
    "Tender Comparison": "Тендерийн харьцуулалт",
    "Progress Report": "Явцын тайлан",
    "Monthly Progress": "Сарын явц",
    "Client Presentation": "Үйлчлүүлэгчийн тайлан",
    "Audit Report": "Аудитын тайлан",
    "Full Report": "Бүрэн тайлан",
    "Quick presets:": "Бэлэн загвар:",
    "Generate Report": "Тайлан үүсгэх",
    "Report downloaded successfully": "Тайлан амжилттай татагдлаа",
    "Failed to generate report": "Тайлан үүсгэж чадсангүй",

    # --- Catalog ---
    "Resource Catalog": "Нөөцийн каталог",
    "My Catalog": "Миний каталог",
    "Add Resource": "Нөөц нэмэх",
    "Add Custom Resource": "Хувийн нөөц нэмэх",
    "Build Assembly": "Нэгдэл бүтээх",
    "Create Assembly": "Нэгдэл үүсгэх",
    "Assembly Name": "Нэгдлийн нэр",
    "components": "бүрэлдэхүүн хэсэг",
    "component": "бүрэлдэхүүн хэсэг",
    "Load more": "Илүү ачаалах",
    "Loaded": "Ачаалагдсан",
    "Showing": "Харуулж байна",
    "Price Range": "Үнийн хязгаар",
    "Price (avg)": "Үнэ (дундаж)",

    # --- Finance ---
    "Invoices": "Нэхэмжлэх",
    "Invoice #": "Нэхэмжлэх #",
    "New Invoice": "Шинэ нэхэмжлэх",
    "New Budget Line": "Шинэ төсвийн мөр",
    "Payments": "Төлбөр",
    "Payable": "Төлөх",
    "Receivable": "Авах",
    "Total Paid": "Нийт төлөгдсөн",
    "Paid": "Төлөгдсөн",
    "Mark Paid": "Төлөгдсөн гэж тэмдэглэх",
    "Approve invoice?": "Нэхэмжлэхийг зөвшөөрөх үү?",
    "Mark as paid?": "Төлөгдсөн гэж тэмдэглэх үү?",
    "Issue Date": "Гаргасан огноо",
    "Due Date": "Хугацаа",
    "Payment Date": "Төлбөрийн огноо",
    "Payment Terms": "Төлбөрийн нөхцөл",
    "Budgets": "Төсөв",
    "Invoice Details": "Нэхэмжлэхийн дэлгэрэнгүй",
    "Amounts": "Дүнгүүд",
    "Earned Value Management": "Олсон үнэ цэнийн удирдлага",
    "Original": "Эх",
    "Revised": "Шинэчилсэн",
    "Variance": "Зөрүү",

    # --- Procurement ---
    "Purchase Orders": "Худалдан авах захиалга",
    "Goods Receipts": "Бараа хүлээн авалт",
    "New Purchase Order": "Шинэ худалдан авах захиалга",
    "PO #": "Худалдан авах захиалга #",
    "Order Details": "Захиалгын дэлгэрэнгүй",
    "Terms": "Нөхцөл",
    "Delivery Date": "Хүргэх огноо",
    "Receipt Date": "Хүлээн авах огноо",

    # --- Contacts ---
    "Add Contact": "Холбоо барих нэмэх",
    "Create Contact": "Холбоо барих үүсгэх",
    "Contact Name": "Холбоо барих нэр",
    "Company Name": "Компанийн нэр",
    "Contacts Directory": "Холбоо барих лавлах",

    # --- RFI ---
    "Create RFI": "RFI үүсгэх",
    "New RFI": "Шинэ RFI",
    "Requests for Information": "Мэдээлэл хүсэх хүсэлт",
    "Subject": "Сэдэв",
    "Question": "Асуулт",
    "Response": "Хариу",
    "Ball in Court": "Хариуцагч",
    "Cost impact": "Зардлын нөлөө",
    "Schedule impact": "Хуваарийн нөлөө",

    # --- Risk ---
    "Risk Analysis (Monte Carlo)": "Эрсдэлийн шинжилгээ (Монте Карло)",
    "Risk Matrix": "Эрсдэлийн матриц",
    "New Risk": "Шинэ эрсдэл",
    "Risk Owner": "Эрсдэлийн эзэн",
    "Mitigation Strategy": "Бууруулах стратеги",
    "Contingency Plan": "Нөөц төлөвлөгөө",
    "Score": "Оноо",
    "Impact": "Нөлөө",
    "Probability": "Магадлал",
    "Cost Impact": "Зардлын нөлөө",
    "Optimistic": "Өөдрөг",
    "Pessimistic": "Гутрангуй",
    "Std Dev": "Стандарт хазайлт",
    "Distribution": "Тархалт",

    # --- Files ---
    "Project Files": "Төслийн файлууд",
    "All files": "Бүх файлууд",
    "Upload files": "Файл илгээх",
    "Upload photos": "Зураг илгээх",
    "Open": "Нээх",
    "Grid": "Сүлжээ",
    "Calendar": "Хуанли",
    "List": "Жагсаалт",
    "Kanban": "Канбан",
    "Timeline": "Цаг хугацаа",
    "Modified": "Засварласан",
    "Size": "Хэмжээ",
    "Storage": "Хадгалалт",
    "Path": "Зам",
    "Metadata": "Мета өгөгдөл",

    # --- Tasks ---
    "Create Task": "Даалгавар үүсгэх",
    "Assignee": "Хариуцагч",
    "Due Date": "Хугацаа",
    "All": "Бүх",

    # --- AI / Onboarding ---
    "Welcome": "Тавтай морил",
    "Welcome to OpenEstimate": "OpenEstimate-д тавтай морил",
    "Skip": "Алгасах",
    "Save & Continue": "Хадгалаад үргэлжлүүлэх",
    "Project Name": "Төслийн нэр",
    "Region": "Бүс",
    "Currency": "Валют",
    "Standard": "Стандарт",
    "Auto": "Авто",
    "Auto-detect": "Автоматаар таних",
    "Any type": "Аливаа төрөл",
    "Residential": "Орон сууцны",
    "Commercial / Office": "Худалдааны / Оффисын",
    "Industrial": "Үйлдвэрлэлийн",
    "Retail": "Жижиглэн худалдааны",
    "Healthcare": "Эрүүл мэндийн",
    "Education": "Боловсролын",
    "Hospitality": "Зочид буудлын",
    "Infrastructure": "Дэд бүтцийн",
    "Mixed Use": "Холимог хэрэглээний",

    # --- Sustainability / Carbon ---
    "Sustainability / CO2": "Тогтвортой байдал / CO2",
    "Total CO2": "Нийт CO2",
    "Material": "Материал",
    "Benchmark": "Жишиг",
    "Calculate": "Тооцоолох",
    "Export CO2 Report PDF": "CO2 тайланг PDF болгож экспортлох",

    # --- Misc ---
    "Test failed": "Шалгалт амжилтгүй",
    "Connection failed": "Холболт амжилтгүй",
    "Connection successful": "Холболт амжилттай",
    "Connection successful!": "Холболт амжилттай!",
    "Response time: {{ms}}ms": "Хариу өгөх хугацаа: {{ms}}мс",
    "(last tested: {{time}})": "(сүүлд шалгасан: {{time}})",
    "Not configured": "Тохируулагдаагүй",
    "Recommended": "Зөвлөмжтэй",
    "Get an API key": "API түлхүүр авах",
    "Configure AI Provider": "AI үйлчилгээ үзүүлэгчийг тохируулах",
    "AI Connected": "AI холбогдсон",

    # --- Common errors ---
    "Server error": "Серверийн алдаа",
    "Not found": "Олдсонгүй",
    "Page not found": "Хуудас олдсонгүй",
    "Go back": "Буцах",
    "Go to Dashboard": "Хяналтын самбар руу очих",
    "Something went wrong": "Алдаа гарлаа",
    "An unexpected error occurred while rendering this page. You can try reloading or go back to the dashboard.":
        "Энэ хуудсыг харуулах үед санамсаргүй алдаа гарлаа. Дахин ачаалах эсвэл хяналтын самбар руу буцаж болно.",
    "Error details": "Алдааны дэлгэрэнгүй",
    "The page you are looking for does not exist or has been moved. Check the URL or go back to the dashboard.":
        "Хайж байгаа хуудас байхгүй эсвэл шилжсэн байна. URL-ыг шалгах эсвэл хяналтын самбар руу буцна уу.",

    # --- high-frequency strings added in pass 2 ---
    "Project...": "Төсөл...",
    "Select project...": "Төсөл сонгох...",
    "Select Project": "Төсөл сонгох",
    "Select a project": "Төсөл сонгоно уу",
    "Select a project...": "Төсөл сонгоно уу...",
    "Select project": "Төсөл сонгох",
    "Select BOQ...": "БМЖ сонгох...",
    "Select a BOQ": "БМЖ сонгоно уу",
    "Select a BOQ...": "БМЖ сонгоно уу...",
    "Select BOQ": "БМЖ сонгох",
    "Project": "Төсөл",
    "BOQ": "БМЖ",
    "Value": "Үнэ цэн",
    "Qty": "Тоо",
    "Qty:": "Тоо:",
    "Title is required": "Гарчиг шаардлагатай",
    "Date is required": "Огноо шаардлагатай",
    "Subject is required": "Сэдэв шаардлагатай",
    "Question is required": "Асуулт шаардлагатай",
    "Description is required": "Тайлбар шаардлагатай",
    "Company name is required": "Компанийн нэр шаардлагатай",
    "Task title is required": "Даалгаврын гарчиг шаардлагатай",
    "NCR title": "Үл нийцлийн тайлангийн гарчиг",
    "Spec section is required": "Спецификацийн хэсэг шаардлагатай",
    "Signature is required": "Гарын үсэг шаардлагатай",
    "Container code is required": "Багцын код шаардлагатай",
    "Sender is required": "Илгээгч шаардлагатай",
    "Import failed": "Импорт амжилтгүй",
    "Export failed": "Экспорт амжилтгүй",
    "Upload failed": "Илгээх амжилтгүй",
    "Delete failed": "Устгах амжилтгүй",
    "Save failed": "Хадгалах амжилтгүй",
    "Update failed": "Шинэчлэх амжилтгүй",
    "Test failed": "Шалгалт амжилтгүй",
    "Toggle failed": "Сэлгэх амжилтгүй",
    "Lock failed": "Түгжих амжилтгүй",
    "Unlock failed": "Түгжээ тайлах амжилтгүй",
    "Validation failed": "Шалгалт амжилтгүй",
    "Renumber failed": "Дугаарлах амжилтгүй",
    "Match failed": "Тааруулах амжилтгүй",
    "Conversion failed": "Хөрвүүлэлт амжилтгүй",
    "Pivot failed": "Pivot амжилтгүй",
    "Restore failed": "Сэргээх амжилтгүй",
    "Apply failed": "Хэрэглэх амжилтгүй",
    "Skip failed": "Алгасах амжилтгүй",
    "Connection error": "Холболтын алдаа",
    "Search failed": "Хайлт амжилтгүй",
    "Search failed. Check vector database.": "Хайлт амжилтгүй. Вектор мэдээллийн санг шалгана уу.",
    "Bulk delete failed": "Бөөнөөр устгах амжилтгүй",
    "Cannot disable": "Идэвхгүй болгох боломжгүй",
    "Unable to process reset request. Please try again.": "Дахин тохируулах хүсэлтийг боловсруулж чадсангүй. Дахин оролдоно уу.",
    "Unable to connect to server. Please try again.": "Сервертэй холбогдож чадсангүй. Дахин оролдоно уу.",
    "Unable to get a response. Please check AI settings.": "Хариу авч чадсангүй. AI тохиргоог шалгана уу.",
    "Copied": "Хуулагдсан",
    "Copied!": "Хуулагдсан!",
    "Copy": "Хуулах",
    "Could not copy": "Хуулж чадсангүй",
    "Uploaded": "Илгээгдсэн",
    "Uploading…": "Илгээж байна…",
    "Uploading...": "Илгээж байна...",
    "Imported": "Импортолсон",
    "Importing...": "Импортолж байна...",
    "Categories": "Ангилал",
    "Authors": "Зохиогчид",
    "How it works": "Хэрхэн ажилладаг",
    "How matching works": "Тааруулалт хэрхэн ажилладаг",
    "selected": "сонгогдсон",
    "Selected": "Сонгогдсон",
    "Deselect all": "Бүгдийг хасах",
    "Select all": "Бүгдийг сонгох",
    "Clear selection": "Сонголтыг арилгах",
    "Filter by status": "Төлвөөр шүүх",
    "Filter by type": "Төрлөөр шүүх",
    "Filter by region": "Бүсээр шүүх",
    "Resolved": "Шийдвэрлэсэн",
    "Verified": "Баталгаажсан",
    "Acknowledged": "Хүлээн зөвшөөрсөн",
    "Overdue": "Хугацаа хэтэрсэн",
    "Export PDF": "PDF болгож экспортлох",
    "Export CSV": "CSV болгож экспортлох",
    "Export Excel": "Excel болгож экспортлох",
    "Export complete": "Экспорт дууссан",
    "Excel file downloaded.": "Excel файл татагдсан.",
    "Base Total": "Үндсэн дүн",
    "Base cost": "Үндсэн зардал",
    "Base amount": "Үндсэн дүн",
    "Base year": "Үндсэн жил",
    "Base": "Үндсэн",
    "Text": "Текст",
    "Cloud": "Үүл",
    "Arrow": "Сум",
    "Stamp": "Тамга",
    "Measurement": "Хэмжилт",
    "Highlight": "Тодруулах",
    "Freehand": "Чөлөөтэй",
    "Keyboard Shortcuts": "Гарын товчлуурын товчлол",
    "Show keyboard shortcuts": "Гарын товчлолыг харуулах",
    "Show this dialog": "Энэ цонхыг харуулах",
    "Paste from Excel": "Excel-ээс буулгах",
    "Paste": "Буулгах",
    "Import complete": "Импорт дууссан",
    "Import Complete": "Импорт дууссан",
    "Expires": "Дуусах хугацаа",
    "Expired": "Дууссан",
    "Expiring soon": "Удахгүй дуусна",
    "Void": "Хүчингүй",
    "No projects available": "Боломжтой төсөл алга",
    "No projects yet": "Хараахан төсөл алга",
    "No matching projects": "Тохирох төсөл олдсонгүй",
    "Complete": "Бүрэн",
    "Completed": "Дууссан",
    "Cancelled": "Цуцлагдсан",
    "No project selected": "Төсөл сонгоогүй",
    "No active project": "Идэвхтэй төсөл алга",
    "No project": "Төсөл алга",
    "Format": "Формат",
    "Role": "Үүрэг",
    "Structural": "Барилгын бүтэц",
    "Architectural": "Архитектур",
    "Mechanical": "Механик",
    "Electrical": "Цахилгаан",
    "Plumbing": "Сантехник",
    "Civil": "Иргэний",
    "Fire Protection": "Галын хамгаалалт",
    "Landscape": "Ландшафт",
    "Mixed / Multi-discipline": "Холимог / Олон салбар",
    "Workforce": "Ажиллах хүч",
    "Workers": "Ажилчид",
    "workers": "ажилчид",
    "Trade": "Чиглэл",
    "Weather": "Цаг агаар",
    "Weather Conditions": "Цаг агаарын нөхцөл",
    "Temperature": "Температур",
    "Wind": "Салхи",
    "Humidity": "Чийгшил",
    "Clear": "Цэлмэг",
    "Cloudy": "Үүлэрхэг",
    "Rain": "Бороо",
    "Snow": "Цас",
    "Storm": "Шуурга",
    "Visitors": "Зочид",
    "Deliveries": "Хүргэлт",
    "Safety Incidents": "Аюулгүй байдлын тохиолдол",
    "Work Performed": "Хийсэн ажил",
    "Delays": "Хойшлогдсон",
    "Delay Hours": "Хойшлогдсон цаг",
    "Incidents": "Тохиолдол",
    "Observations": "Ажиглалт",
    "Submit for Approval": "Зөвшөөрүүлэхээр илгээх",
    "Submit Review": "Хяналт илгээх",
    "Submit Response": "Хариу илгээх",

    # categories / types
    "Material": "Материал",
    "Materials": "Материал",
    "Equipment": "Тоног төхөөрөмж",
    "Labor": "Хөдөлмөр",
    "Operator": "Оператор",
    "Electricity": "Цахилгаан",
    "Composite": "Нийлмэл",
    "HVAC": "HVAC",
    "Fire Safety": "Галын аюулгүй байдал",
    "Finishing": "Засал чимэглэл",
    "Finishes": "Засал чимэглэл",
    "Exterior": "Гадна тал",
    "Landscaping": "Ландшафт",
    "General": "Ерөнхий",
    "Mitigated": "Бууруулсан",

    # punch list
    "Low": "Бага",
    "Medium": "Дунд",
    "High": "Өндөр",
    "Critical": "Чухал",

    # files / sharing
    "Share": "Хуваалцах",
    "Generate share link": "Хуваалцах холбоос үүсгэх",
    "Share URL": "Хуваалцах URL",
    "Create link": "Холбоос үүсгэх",
    "Creating link…": "Холбоос үүсгэж байна…",
    "Existing links": "Одоо байгаа холбоос",
    "Revoke": "Хүчингүй болгох",
    "Revoking…": "Хүчингүй болгож байна…",
    "Password protected": "Нууц үгээр хамгаалсан",
    "Open link": "Холбоос нээх",
    "Never expires": "Хэзээ ч дуусахгүй",
    "1 day": "1 өдөр",
    "1 hour": "1 цаг",
    "3 days": "3 өдөр",
    "7 days": "7 өдөр",
    "14 days": "14 өдөр",
    "30 days": "30 өдөр",
    "Never": "Хэзээ ч үгүй",
    "Folder access": "Хавтасны хандалт",
    "Manage access": "Хандалт удирдах",
    "Grant access": "Хандалт олгох",
    "Granting…": "Олгож байна…",
    "Member": "Гишүүн",
    "Choose a project member": "Төслийн гишүүн сонгох",
    "Owner": "Эзэн",
    "Editor": "Засварлагч",
    "Viewer": "Үзэгч",

    # documents
    "Site": "Талбай",
    "Progress": "Явц",
    "Defect": "Гэмтэл",
    "Delivery": "Хүргэлт",
    "Photo": "Зураг",
    "Drawing": "Зураг",
    "Contract": "Гэрээ",
    "Specification": "Спецификаци",
    "Correspondence": "Захидал харилцаа",
    "Caption": "Гарчиг",
    "Tags": "Шошго",
    "Taken at": "Авсан",
    "GPS Coordinates": "GPS координат",

    # Common labels seen across pages
    "Spec Section": "Спецификацийн хэсэг",
    "Rev": "Хувилбар",
    "Revision History": "Хувилбарын түүх",
    "Cover Note": "Хавсралт тэмдэглэл",
    "Items": "Зүйлүүд",
    "Purpose": "Зорилго",
    "Response Due": "Хариу хүлээх",
    "Direction": "Чиглэл",
    "Incoming": "Орж ирсэн",
    "Outgoing": "Гарсан",
    "From": "Аас",
    "To": "Хүртэл",
    "Issuer": "Гаргагч",
    "Effective date": "Хүчин төгөлдөр болсон огноо",
    "Coverage amount": "Хамрах дүн",
    "Policy / permit number": "Бодлого / зөвшөөрлийн дугаар",
    "Document type": "Баримтын төрөл",
    "Days left": "Үлдсэн өдөр",
    "Notify days before": "Өмнө мэдэгдэх өдөр",
    "Attachment": "Хавсралт",
    "Attachment document (optional)": "Хавсралт баримт (заавал биш)",
    "No attachment": "Хавсралт байхгүй",
    "General liability insurance": "Ерөнхий хариуцлагын даатгал",
    "Workers' compensation insurance": "Ажилчдын нөхөн төлбөрийн даатгал",
    "Auto insurance": "Тээврийн даатгал",
    "Umbrella insurance": "Шүхэр даатгал",
    "Building permit": "Барилгын зөвшөөрөл",
    "Electrical permit": "Цахилгаан зөвшөөрөл",
    "Plumbing permit": "Сантехникийн зөвшөөрөл",
    "Other permit": "Бусад зөвшөөрөл",
    "Payment bond": "Төлбөрийн баталгаа",
    "Performance bond": "Гүйцэтгэлийн баталгаа",
    "Bid bond": "Тендерийн баталгаа",
    "Safety certification": "Аюулгүй байдлын гэрчилгээ",
    "Other certification": "Бусад гэрчилгээ",

    # Validation / FX
    "Currency": "Валют",
    "Currency normalization": "Валют хувиргалт",
    "Sequential": "Дараалсан",
    "Short decimal": "Богино аравтын",
    "Gap of 10": "10-ийн зайтай",
    "Gap of 100": "100-ийн зайтай",

    # AI labels
    "Cost drivers": "Зардлын хүчин зүйл",
    "Price volatility": "Үнийн хэлбэлзэл",
    "Scope coverage": "Хамрах хүрээ",
    "Vendor concentration": "Нийлүүлэгчийн төвлөрөл",
    "Real-time validation": "Бодит цагийн шалгалт",
    "Critical Gaps": "Чухал цоорхой",
    "Estimator": "Тооцоолуур",
    "Explorer": "Судлагч",
    "Manager": "Менежер",
    "View as role": "Үүргийн хувьд харах",
    "Refresh analysis": "Шинжилгээг шинэчлэх",
    "Thinking...": "Бодож байна...",
    "Unnamed Project": "Нэргүй төсөл",

    # File detail
    "Kind": "Төрөл",
    "Grid view": "Сүлжээгээр харах",
    "List view": "Жагсаалтаар харах",

    # Schedule confidence
    "Deterministic": "Тогтсон",
    "Mean (critical path)": "Дундаж (эгзэгтэй зам)",
    "Std. deviation": "Стандарт хазайлт",
    "50% confidence": "50% итгэлцэл",
    "80% confidence": "80% итгэлцэл",
    "95% confidence": "95% итгэлцэл",
    "Planned duration": "Төлөвлөсөн хугацаа",
    "active": "идэвхтэй",

    # validation / compliance
    "Insurance": "Даатгал",
    "Permit": "Зөвшөөрөл",
    "Compliance documents": "Нийцэлийн баримт бичиг",
    "New document": "Шинэ баримт",

    # punch
    "Cancel": "Цуцлах",
    "Discard": "Хаях",
    "Save & Continue": "Хадгалаад үргэлжлүүлэх",
    "Continue": "Үргэлжлүүлэх",

    # AI / providers
    "AI Provider": "AI үйлчилгээ үзүүлэгч",
    "Not configured": "Тохируулагдаагүй",
    "Key configured": "Түлхүүр тохируулсан",

    # Match elements / phase A labels
    "Confidence": "Итгэлцэл",
    "Library": "Сан",
    "Detail": "Дэлгэрэнгүй",
    "Apply preview": "Урьдчилан үзэлтийг хэрэглэх",
    "Apply": "Хэрэглэх",
    "Apply to BOQ": "БМЖ-д хэрэглэх",
    "Skip": "Алгасах",
    "Confirm": "Баталгаажуулах",
    "Group": "Бүлэг",
    "Group by": "Бүлэглэх",
    "Sort": "Эрэмбэлэх",
    "Limit": "Хязгаар",
    "Views": "Харагдац",
    "Save view": "Харагдац хадгалах",
    "Saved views": "Хадгалсан харагдац",
    "Number": "Тоо",
    "Percent": "Хувь",
    "Bar": "Багана",
    "Pie": "Дугуй",
    "Line": "Шугам",
    "Scatter": "Тархалт",
    "Heatmap": "Дулааны зураг",

    # short status
    "TBD": "Тодорхойлогдоогүй",
    "tbd": "тбд",
    "confirmed": "баталгаажсан",
    "unmatched": "таарахгүй",
    "suggested": "санал болгосон",
    "skipped": "алгасагдсан",
    "applied": "хэрэглэгдсэн",
    "overridden": "өөрчилсөн",
    "void": "хүчингүй",
    "confirm": "баталгаажуулах",

    # Catalog
    "Avg Rate": "Дундаж үнэ",
    "Total Cost": "Нийт зардал",
    "Total Qty": "Нийт тоо",
    "Pos.": "Бай.",
    "pos.": "бай.",
    "Pos": "Бай.",

    # FieldReports / weather added above
    "Daily Report": "Өдрийн тайлан",
    "Inspection": "Шалгалт",
    "Safety Report": "Аюулгүй байдлын тайлан",
    "Concrete Pour": "Бетон асгалт",

    # NCR
    "Open": "Нээлттэй",
    "Close": "Хаах",
    "Close NCR": "Үл нийцлийн тайлан хаах",
    "Root Cause": "Үндсэн шалтгаан",
    "Corrective Action": "Засах арга",
    "Preventive Action": "Урьдчилан сэргийлэх арга",

    # Tasks
    "Mark Complete": "Дууссан гэж тэмдэглэх",
    "Assignee": "Хариуцагч",

    # CDE
    "Containers": "Багц",
    "Container": "Багц",
    "State": "Төлөв",
    "Suit.": "Тохир.",
    "History": "Түүх",
    "Container Code": "Багцын код",
    "Suitability Code": "Тохиромжтой код",
    "Suitability": "Тохиромжтой",

    # users
    "Total Users": "Нийт хэрэглэгч",
    "Admins": "Админууд",
    "Managers": "Менежерүүд",
    "Last Login": "Сүүлийн нэвтрэлт",
    "Invite User": "Хэрэглэгч урих",
    "Invite": "Урих",
    "Full access to all features": "Бүх боломжид бүрэн хандах",
    "Read-only access": "Зөвхөн уншиж болох",
    "Create and edit content": "Контент үүсгэх ба засах",
    "Project and team management": "Төсөл ба багийн удирдлага",

    # safety / risk
    "Days Lost": "Алдсан өдөр",
    "Risk Score": "Эрсдэлийн оноо",
    "Risk Matrix": "Эрсдэлийн матриц",
    "Total Risks": "Нийт эрсдэл",
    "Total Exposure": "Нийт өртөлт",
    "Iterations": "Давталт",
    "Distribution": "Тархалт",
    "Triangular": "Гурвалжин",
    "Uniform": "Жигд",
    "PERT": "PERT",

    # explorer
    "Model Name": "Загварын нэр",
    "Elements": "Элементүүд",
    "Documents": "Баримт бичиг",
    "Total Area": "Нийт талбай",
    "Total Volume": "Нийт эзлэхүүн",
    "Page totals:": "Хуудасны нийт:",
    "Min": "Мин",
    "Max": "Макс",
    "Mean": "Дундаж",
    "Sum": "Нийлбэр",
    "Unique": "Өвөрмөц",
    "Non-Null": "Хоосон бус",
    "Top Value": "Хамгийн дээд утга",
    "rows": "мөр",
    "groups": "бүлэг",
    "Save view": "Харагдац хадгалах",

    # changeorders
    "Total Orders": "Нийт захиалга",
    "Cost Delta": "Зардлын зөрүү",
    "Schedule Days": "Хуваарийн өдөр",
    "New Qty": "Шинэ тоо",
    "New Rate": "Шинэ үнэ",
    "Original Qty": "Эх тоо",
    "Original Rate": "Эх үнэ",
    "Awaiting approval": "Зөвшөөрөл хүлээж байна",

    # boq export formats
    "Excel (.xlsx)": "Excel (.xlsx)",
    "CSV (.csv)": "CSV (.csv)",
    "PDF": "PDF",
    "GAEB XML (.x83)": "GAEB XML (.x83)",

    # 5d
    "Performance": "Гүйцэтгэл",
    "Earned": "Олсон",
    "Schedule Progress": "Хуваарийн явц",
    "Time Elapsed": "Өнгөрсөн хугацаа",
    "Adjusted BAC": "Тохируулсан BAC",
    "Adjusted EAC": "Тохируулсан EAC",
    "Original BAC": "Эх BAC",
    "Impact": "Нөлөө",
    "Calculate Impact": "Нөлөө тооцоолох",
    "What-If Scenarios": "Хэрэв-Бол хувилбар",

    # Cost benchmark
    "Cost per m² Benchmark": "м²-ийн зардлын жишиг",
    "Cost / m²": "Зардал / м²",
    "Project Area (m²)": "Төслийн талбай (м²)",
    "Project Type": "Төслийн төрөл",
    "Hospital": "Эмнэлэг",
    "Office": "Оффис",
    "Within range": "Хязгаарт",
    "Outside range": "Хязгаараас гадуур",
    "Near boundary": "Хязгаарт ойртсон",

    # validation/extra
    "Validation pending — not yet checked": "Шалгалт хүлээгдэж байна — хараахан шалгаагүй",
    "Validation passed": "Шалгалт амжилттай",
    "Recalculation complete": "Дахин тооцоолол дууссан",
    "Recalculation failed": "Дахин тооцоолол амжилтгүй",
    "No changes needed": "Өөрчлөлт хэрэггүй",

    # generic toast strings
    "Status updated": "Төлөв шинэчлэгдсэн",
    "Profile updated": "Профайл шинэчлэгдсэн",
    "Project created": "Төсөл үүсгэгдсэн",
    "Project updated": "Төсөл шинэчлэгдсэн",
    "Project archived": "Төсөл архивлагдсан",
    "Project duplicated": "Төсөл хуулагдсан",
    "BOQ created": "БМЖ үүсгэгдсэн",
    "Activity created": "Үйл ажиллагаа үүсгэгдсэн",
    "Schedule created": "Хуваарь үүсгэгдсэн",
    "Schedule generated from BOQ": "Хуваарь БМЖ-ээс үүсгэгдсэн",
    "Tender package created": "Тендерийн багц үүсгэгдсэн",
    "Bid awarded": "Үнийн санал олгогдсон",
    "Bid submitted": "Үнийн санал илгээгдсэн",
    "Component added": "Бүрэлдэхүүн нэмэгдсэн",
    "Component deleted": "Бүрэлдэхүүн устгагдсан",
    "Assembly applied to BOQ": "Нэгдэл БМЖ-д хэрэглэгдсэн",
    "Assembly deleted": "Нэгдэл устгагдсан",
    "Assembly duplicated": "Нэгдэл хуулагдсан",
    "Critical path calculated": "Эгзэгтэй зам тооцоолсон",
    "Risk analysis complete": "Эрсдэлийн шинжилгээ дууссан",

    # auth
    "Sign in": "Нэвтрэх",
    "Get started with OpenEstimate": "OpenEstimate-тэй эхлэх",
    "Enter your password": "Нууц үгээ оруулна уу",
    "Repeat your password": "Нууц үгээ дахин оруулна уу",
    "John Smith": "Жон Смит",
    "Enter your credentials to access your workspace": "Ажлын талбартаа нэвтрэхийн тулд мэдээллээ оруулна уу",

    # Common confirmation prompts
    "Delete?": "Устгах уу?",
    "Are you sure you want to delete {{count}} selected positions? This action cannot be undone.":
        "Сонгосон {{count}} байрлалыг устгах гэж байна. Энэ үйлдлийг буцаах боломжгүй.",
    "Delete positions": "Байрлалуудыг устгах",

    # generic listing
    "Showing first 50 of {{total}} rows": "{{total}} мөрийн эхний 50-г харуулж байна",

    # Settings
    "Manage your account and preferences": "Бүртгэл болон тохиргоог удирдах",
    "Your personal information": "Хувийн мэдээлэл",
    "Choose your preferred color scheme": "Өнгөний загвар сонгоно уу",
    "Choose your preferred language": "Хэлээ сонгоно уу",
    "Sign out or manage your account": "Гарах эсвэл бүртгэлийг удирдах",

    # short common error messages
    "Failed to save": "Хадгалж чадсангүй",
    "Failed to delete": "Устгаж чадсангүй",
    "Failed to create": "Үүсгэж чадсангүй",
    "Failed to update": "Шинэчилж чадсангүй",
    "Failed to load change orders. Please try again.": "Өөрчлөлтийн захиалгыг ачаалж чадсангүй. Дахин оролдоно уу.",
    "Failed to load cost risk analysis. Please try again.": "Зардлын эрсдэлийн шинжилгээг ачаалж чадсангүй. Дахин оролдоно уу.",
    "Failed to load sensitivity analysis. Please try again.": "Мэдрэмжийн шинжилгээг ачаалж чадсангүй. Дахин оролдоно уу.",

    # Markup actions
    "Markups exported to CSV": "Тэмдэглэгээг CSV болгож экспортлосон",
    "Markup status updated": "Тэмдэглэгээний төлөв шинэчлэгдсэн",
    "Markup deleted": "Тэмдэглэгээ устгагдсан",

    # BOQ short toast
    "Position added": "Байрлал нэмэгдсэн",
    "Position deleted": "Байрлал устгагдсан",
    "Position duplicated": "Байрлал хуулагдсан",
    "Position restored": "Байрлал сэргээгдсэн",
    "Section added": "Хэсэг нэмэгдсэн",
    "Resource added": "Нөөц нэмэгдсэн",
    "Snapshot saved": "Хувилбар хадгалагдсан",
    "Snapshot restored": "Хувилбар сэргээгдсэн",
    "Column added": "Багана нэмэгдсэн",
    "Column removed": "Багана устгагдсан",
    "Markup added": "Тэмдэглэгээ нэмэгдсэн",
    "Variables saved": "Хувьсагч хадгалагдсан",

    # validation buttons
    "Run Validation": "Шалгалт ажиллуулах",

    # AI quick estimate
    "AI Estimate": "AI тооцоо",
    "Create an estimate from any source": "Аливаа эх сурвалжаас тооцоо үүсгэх",
    "Generate Estimate": "Тооцоо үүсгэх",
    "Generating...": "Үүсгэж байна...",
    "Save as BOQ": "БМЖ болгож хадгалах",
    "Building Type": "Барилгын төрөл",
    "Currency": "Валют",
    "Standard": "Стандарт",

    # daily diary / equipment
    "Equipment": "Тоног төхөөрөмж",
    "Fleet": "Тээврийн парк",
    "Crew": "Баг",

    # Match elements UI
    "Match Elements": "Элементийг тааруулах",
    "Match candidates": "Тохирох сонголтууд",
    "How matching works": "Тааруулалт хэрхэн ажилладаг",
    "Library": "Сан",
    "Detail": "Дэлгэрэнгүй",
    "Cancel": "Цуцлах",
    "Confidence": "Итгэлцэл",

    # explorer
    "CAD-BIM BI Explorer": "CAD-BIM BI судлагч",
    "Powered by": "Дэмжсэн",
    "Save Analysis": "Шинжилгээ хадгалах",

    # bim
    "BIM Viewer": "BIM үзэгч",
    "BIM 3D Viewer": "BIM 3D үзэгч",
    "Models": "Загвар",
    "Model name": "Загварын нэр",
    "Element Tree": "Элементийн мод",
    "Wireframe": "Утсан хүрээ",
    "Fit all": "Бүгдийг багтаах",
    "Zoom to selection": "Сонголт руу томруулах",
    "Discipline": "Мэргэжил",
    "Storey": "Давхар",

    # files share
    "Share": "Хуваалцах",

    # marketplace
    "Free": "Үнэгүй",
    "Included": "Багтсан",
    "Built-in": "Суурилуулсан",
    "Module Marketplace": "Модулийн зах",

    # finance summary
    "Receivable": "Авах",
    "Payable": "Төлөх",

    # short markup labels
    "Color": "Өнгө",
    "Label": "Шошго",
    "Label / Text": "Шошго / Текст",

    # AI dialog
    "Dismiss": "Хаах",

    # generic empty/none variants
    "No results found": "Үр дүн олдсонгүй",
    "No documents uploaded": "Илгээсэн баримт алга",

    # tenant access
    "Owner — full control": "Эзэн — бүрэн хяналт",
    "Editor — upload + delete own": "Засварлагч — илгээх + өөрийнхөө устгах",
    "Viewer — read only": "Үзэгч — зөвхөн уншина",

    # field reports
    "Field Reports": "Талбайн тайлан",
    "Calendar": "Хуанли",

    # --- pass 3: more frequent untranslated strings ---
    "Add {{count}} to BOQ": "БМЖ-д {{count}} нэмэх",
    "Add to BOQ": "БМЖ-д нэмэх",
    "e.g. Office Tower Downtown": "ж.нь. Хотын төв оффис цамхаг",
    "{{count}}d ago": "{{count}} өдрийн өмнө",
    "{{count}}h ago": "{{count}} цагийн өмнө",
    "{{count}}m ago": "{{count}} минутын өмнө",
    "{{count}} min ago": "{{count}} мин өмнө",
    "Select a project first": "Эхлээд төсөл сонгоно уу",
    "Choose a project...": "Төсөл сонгоно уу...",
    "Choose a BOQ...": "БМЖ сонгоно уу...",
    "Write a comment...": "Сэтгэгдэл бичих...",
    "Cost Databases": "Үнийн мэдээллийн сан",
    "Database": "Мэдээллийн сан",
    "Area (m²)": "Талбай (м²)",
    "Area (m2)": "Талбай (м²)",
    "Variance Share": "Зөрүүний хувь",
    "Missing": "Дутуу",
    "Resource": "Нөөц",
    "resources": "нөөц",
    "No resources match your search": "Хайлтад тохирох нөөц алга",
    "Saved to catalog": "Каталогт хадгалагдсан",
    "Update Rates": "Үнэлгээ шинэчлэх",
    "Set as quantity": "Тоо хэмжээ болгож тогтоох",
    "Checking...": "Шалгаж байна...",
    "Rate Applied": "Үнэлгээ хэрэглэгдсэн",
    "Duplicate Position": "Байрлал хуулах",
    "Quality score: {{score}}%": "Чанарын оноо: {{score}}%",
    "DWG drawing": "DWG зураг",
    "All units": "Бүх нэгж",
    "Command Palette": "Командын самбар",
    "Unknown error": "Үл мэдэгдэх алдаа",
    "Back to projects": "Төслүүд рүү буцах",
    "Back to schedules": "Хуваариуд руу буцах",
    "Back to project": "Төсөл рүү буцах",
    "Back to recommendations": "Зөвлөмж рүү буцах",
    "CPI": "CPI",
    "SPI": "SPI",
    "Overall Variance": "Нийт зөрүү",
    "vs budget": "төсөвтэй харьцуулсан",
    "Mode": "Горим",
    "Drop your file here": "Файлаа энд оруулна уу",
    "Drop your file here, or click to browse": "Файлаа энд оруулна уу эсвэл сонгож үзнэ үү",
    "Drop your PDF drawing here": "PDF зургаа энд оруулна уу",
    "Drop files to upload": "Илгээх файлаа оруулна уу",
    "Drop file here": "Файл оруулна уу",
    "Drag & drop files here": "Файлуудаа чирж тавина уу",
    "Drag & drop files here, or click Upload": "Файлуудаа чирэх эсвэл Илгээх дээр дарна уу",
    "Import Cost Database": "Үнийн мэдээллийн сан импортлох",
    "Import Database": "Мэдээллийн сан импортлох",
    "{{count}} selected": "{{count}} сонгогдсон",
    "{{count}} variants": "{{count}} хувилбар",
    "{{count}} elements": "{{count}} элемент",
    "{{count}} variant chosen": "{{count}} хувилбар сонгогдсон",
    "Median": "Дунд утга",
    "Default": "Үндсэн",
    "The #1 open-source construction ERP": "#1 нээлттэй эх барилгын ERP",
    "{{name}} disabled": "{{name}} идэвхгүй",
    "{{name}} enabled": "{{name}} идэвхтэй",
    "Integrations": "Интеграц",
    "Takeoff": "Хэмжээ авах",
    "BIM model": "BIM загвар",
    "Open in {{module}}": "{{module}}-д нээх",
    "Scope": "Хүрээ",
    "Attachments": "Хавсралт",
    "By Status": "Төлвөөр",
    "By Type": "Төрлөөр",
    "By Priority": "Чухал зэргээр",
    "By Section": "Хэсгээр",
    "By Category": "Ангилалаар",
    "Linked BOQ Position": "Холбосон БМЖ байрлал",
    "Not linked": "Холбоогүй",
    "Conf.": "Итг.",
    "Page": "Хуудас",
    "Pages": "Хуудас",
    "Assigned To": "Хариуцагч",
    "Recent": "Сүүлийн",
    "Just now": "Дөнгөж сая",
    "No notifications": "Мэдэгдэл алга",
    "Mark all as read": "Бүгдийг уншсан гэж тэмдэглэх",
    "Unread": "Уншаагүй",

    # Cost related
    "All categories": "Бүх ангилал",
    "All databases": "Бүх мэдээллийн сан",
    "All sources": "Бүх эх сурвалж",
    "All regions": "Бүх бүс",
    "All": "Бүх",
    "Add Item": "Зүйл нэмэх",
    "Add Position": "Байрлал нэмэх",
    "Add Section": "Хэсэг нэмэх",
    "Add Resource": "Нөөц нэмэх",
    "Activity Type": "Үйл ажиллагааны төрөл",

    # CDE
    "No state transitions yet — promote the container to start the audit trail.": "Хараахан төлвийн шилжилт байхгүй — багцыг ахиулж аудит эхлүүлнэ үү.",

    # Conflict resolution
    "Conflict": "Зөрчил",
    "Merge Conflict Detected": "Нэгтгэлийн зөрчил илрэв",
    "Your version": "Таны хувилбар",
    "Their version": "Тэдний хувилбар",
    "Keep mine": "Минийхийг хадгалах",
    "Accept theirs": "Тэдийнхийг авах",
    "Manual merge...": "Гарын нэгтгэл...",
    "Apply merged value": "Нэгтгэсэн утгыг хэрэглэх",

    # Common short
    "Connection error": "Холболтын алдаа",
    "Test Connection": "Холболт шалгах",
    "Test": "Шалгах",
    "Required By": "Шаардсан огноо",

    # Procurement
    "Manage purchase orders and goods receipts": "Худалдан авах захиалга, бараа хүлээн авалтыг удирдах",
    "Track budgets, invoices, and earned value": "Төсөв, нэхэмжлэх, олсон үнэ цэнг хянах",
    "Track scope changes with cost and schedule impact": "Зардал, хуваарийн нөлөөтэй өөрчлөлтүүдийг хянах",
    "Probabilistic cost estimation with Monte Carlo simulation": "Монте Карлогийн загварчлал ашиглан магадлалын зардлын тооцоо",
    "Track incidents, observations, and risk scores": "Тохиолдол, ажиглалт, эрсдэлийн оноог хянах",
    "Aggregated KPIs across all projects": "Бүх төслүүдийн нэгдсэн KPI",
    "Cross-Project Analytics": "Төслүүд хоорондын аналитик",

    # short tend
    "Lowest bid from": "Хамгийн бага үнийн санал",
    "Bids": "Үнийн санал",
    "bids": "үнийн санал",

    # benchmark
    "Total Spent": "Нийт зарцуулсан",
    "Remaining": "Үлдсэн",
    "Remaining Budget": "Үлдсэн төсөв",
    "Total Invoiced (Payable)": "Нийт нэхэмжилсэн (Төлөх)",

    # report
    "Reports": "Тайлан",
    "Reporting Dashboards": "Тайлангийн самбар",
    "Total Activities": "Нийт үйл ажиллагаа",
    "Delayed": "Хойшилсон",
    "Days Since Incident": "Тохиолдлоос хойш өдөр",
    "Open Items": "Нээлттэй зүйл",
    "Open Actions": "Нээлттэй үйлдэл",
    "Open RFIs": "Нээлттэй RFI",
    "Open Submittals": "Нээлттэй илгээмж",
    "Overdue Payable": "Хугацаа хэтэрсэн төлөх",
    "Overdue Tasks": "Хугацаа хэтэрсэн даалгавар",
    "Schedule Summary": "Хуваарийн хураангуй",
    "RFI Summary": "RFI хураангуй",
    "Safety Overview": "Аюулгүй байдлын тойм",
    "Procurement Summary": "Худалдан авалтын хураангуй",

    # users
    "Manage team members, roles, and access": "Багийн гишүүд, үүрэг, хандалтыг удирдах",

    # AI test
    "Connection successful!": "Холболт амжилттай!",

    # Validation more
    "No validation report yet": "Хараахан шалгалтын тайлан алга",
    "Failed to load validation": "Шалгалтыг ачаалж чадсангүй",

    # Onboarding
    "AI-powered quick estimation": "AI-р хийсэн хурдан тооцоо",
    "AI cost advisor and chat assistant": "AI зардлын зөвлөх ба чат туслах",
    "CAD/BIM data exploration": "CAD/BIM өгөгдлийн судалгаа",
    "3D BIM model viewer": "3D BIM загвар үзэгч",
    "Project management and organization": "Төслийн удирдлага ба зохион байгуулалт",
    "Cost databases and rate management": "Үнийн мэдээллийн сан ба үнэлгээний удирдлага",
    "Composite rate recipes and templates": "Нийлмэл үнэлгээний жор ба загвар",
    "Materials, labor, equipment catalog": "Материал, хөдөлмөр, тоног төхөөрөмжийн каталог",
    "Reusable BOQ templates": "Дахин ашиглах БМЖ загвар",
    "Quality rules and compliance checking": "Чанарын дүрэм ба нийцлийн шалгалт",
    "Quantity takeoff overview": "Тоо хэмжээ авалтын тойм",
    "PDF-based measurements and annotations": "PDF дээрх хэмжилт ба тэмдэглэгээ",
    "Bill of Quantities editor with hierarchical positions": "Шатлалт байрлалтай БМЖ засварлагч",
    "4D Gantt chart and CPM scheduling": "4D Гант диаграмм ба CPM хуваарь",
    "5D cost model with earned value tracking": "Олсон үнэ цэнг хянадаг 5D зардлын загвар",
    "Task management and assignments": "Даалгаврын удирдлага ба хуваарилалт",
    "Budget tracking and financial overview": "Төсөв хянах ба санхүүгийн тойм",
    "Purchase orders and vendor management": "Худалдан авах захиалга ба нийлүүлэгчийн удирдлага",
    "Bid packages and tender workflows": "Тендерийн багц ба тендерийн ажлын урсгал",
    "Change order tracking and approval": "Өөрчлөлтийн захиалга хянах ба зөвшөөрөх",
    "Contact directory and teams": "Холбоо барих лавлах ба багууд",
    "Meeting management and minutes": "Хурлын удирдлага ба тэмдэглэл",
    "Requests for information": "Мэдээлэл хүсэх хүсэлт",
    "Submittal tracking and review": "Илгээмж хянах ба үзэх",
    "Document transmittals": "Баримтын дамжуулалт",
    "Project correspondence log": "Төслийн захидал харилцааны бүртгэл",
    "Document management system": "Баримт бичгийн удирдлагын систем",
    "Common data environment": "Нийтлэг өгөгдлийн орчин",
    "Photo gallery and annotations": "Зургийн цомог ба тэмдэглэгээ",
    "Drawing markups and redlines": "Зурганд хийсэн тэмдэглэгээ",
    "Site inspections and checklists": "Талбайн шалгалт ба жагсаалт",
    "Non-conformance reports": "Үл нийцлийн тайлан",
    "Safety management and incidents": "Аюулгүй байдлын удирдлага ба тохиолдол",
    "Punch list / snag list tracking": "Шалгах жагсаалт",
    "Risk register and mitigation": "Эрсдэлийн бүртгэл ба бууруулалт",
    "Daily field reports": "Өдөр тутмын талбайн тайлан",
    "Requirements and quality gates": "Шаардлага ба чанарын хаалга",
    "Report generation and export": "Тайлан үүсгэх ба экспорт",
    "Reporting dashboards": "Тайлангийн самбар",
    "Data analytics and insights": "Өгөгдлийн аналитик ба үнэлгээ",
    "Sustainability and carbon tracking": "Тогтвортой байдал ба нүүрстөрөгчийн хяналт",
    "Cost benchmarking analysis": "Зардлын жишиг шинжилгээ",
    "Real-time collaboration tools": "Бодит цагийн хамтын ажиллагааны хэрэгсэл",

    # Modal titles
    "Tip:": "Зөвлөгөө:",
    "Tips & Hints": "Зөвлөгөө ба санамж",
    "How it works": "Хэрхэн ажилладаг",

    # confirm wording
    "This action cannot be undone.": "Энэ үйлдлийг буцаах боломжгүй.",

    # tendering
    "Mark Awarded": "Олгогдсон гэж тэмдэглэх",
    "Bid Comparison": "Үнийн санал харьцуулалт",
    "Bid Totals Overview": "Үнийн саналын нийт тойм",
    "Bids Received": "Хүлээн авсан үнийн санал",
    "Highest": "Хамгийн өндөр",
    "Lowest": "Хамгийн бага",
    "TOTAL": "НИЙТ",

    # explorer continued
    "Conversion complete": "Хөрвүүлэлт дууссан",
    "Converting...": "Хөрвүүлж байна...",
    "Sparse (<10%)": "Сийрэг (<10%)",
    "Useful Columns": "Хэрэгтэй багана",
    "Visible Columns": "Харагдах багана",
    "Active filters": "Идэвхтэй шүүлтүүр",
    "No active filters": "Идэвхтэй шүүлтүүр алга",
    "Format": "Формат",
    "Recent Models": "Сүүлийн загвар",
    "New File": "Шинэ файл",

    # short approvals
    "Approved": "Зөвшөөрсөн",
    "Rejected": "Татгалзсан",
    "Submitted": "Илгээгдсэн",
    "Under Review": "Хяналтанд",
    "Evaluating": "Үнэлж байна",
    "Collecting": "Цуглуулж байна",
    "Awarded": "Олгосон",
    "Accepted": "Хүлээн авсан",

    # Procurement Sections
    "Order Details": "Захиалгын мэдэгдэл",
    "Items": "Зүйлүүд",

    # finance hints
    "cost efficiency": "зардлын үр ашиг",
    "schedule efficiency": "хуваарийн үр ашиг",
    "forecast total cost": "урьдчилсан нийт зардал",

    # Permissions
    "Restricted: {{count}} member can access": "Хязгаарласан: {{count}} гишүүн хандах боломжтой",
    "Restricted: {{count}} members can access": "Хязгаарласан: {{count}} гишүүн хандах боломжтой",
    "All project members can access this folder.": "Төслийн бүх гишүүд энэ хавтсанд хандана.",

    # confirm verbs
    "Are you sure?": "Та итгэлтэй байна уу?",
    "Continue?": "Үргэлжлүүлэх үү?",
    "Discard changes?": "Өөрчлөлтүүдийг хаях уу?",

    # changeorders types
    "Added": "Нэмэгдсэн",
    "Modified": "Өөрчилсөн",
    "Removed": "Хасагдсан",

    # short labels in lists
    "Trade": "Чиглэл",
    "Risk": "Эрсдэл",
    "Risks": "Эрсдэл",
    "Mode": "Горим",

    # Marketplace
    "Module Marketplace": "Модулийн зах",
    "Installed Modules": "Суулгасан модуль",
    "Installed Core Modules": "Суулгасан үндсэн модуль",
    "Available Modules": "Боломжтой модуль",
    "Validation Rule Sets": "Шалгалтын дүрмийн багц",
    "Vector Index": "Вектор индекс",
    "rules": "дүрэм",

    # Onboarding company types
    "General Contractor": "Ерөнхий гүйцэтгэгч",
    "Estimator / Cost Consultant": "Тооцоолуур / Зардлын зөвлөх",
    "Project Management Firm": "Төслийн удирдлагын компани",
    "Architecture / Engineering Office": "Архитектур / Инженерийн оффис",
    "Full Enterprise": "Бүрэн байгууллага",

    # modules groups
    "Core Estimation": "Үндсэн тооцоо",
    "Takeoff & AI": "Хэмжээ авах ба AI",
    "Planning": "Төлөвлөлт",
    "Finance & Procurement": "Санхүү ба худалдан авалт",
    "Communication": "Харилцаа",
    "Quality & Safety": "Чанар ба аюулгүй байдал",
    "Field": "Талбай",
    "Analytics & Extras": "Аналитик ба нэмэлт",

    # AI labels
    "Cost Intelligence Advisor": "Зардлын интеллектийн зөвлөх",
    "Refresh": "Шинэчлэх",

    # files share extra
    "{{count}} download": "{{count}} татаж авалт",
    "{{count}} downloads": "{{count}} татаж авалт",
    "QR code for share link": "Хуваалцах холбоосын QR код",

    # ai photo
    "Building photo or scanned document": "Барилгын зураг эсвэл сканердсан баримт",
    "BOQ sheets, specs, tender docs": "БМЖ хуудас, спецификаци, тендерийн баримт",
    "Spreadsheet with BOQ data": "БМЖ өгөгдөлтэй хүснэгт",
    "Revit, IFC, DWG, DGN files": "RVT, IFC, DWG, DGN файл",
    "Copy-paste from any app": "Аливаа аппаас хуулж буулгах",
    "Describe your project in plain text": "Төслөө энгийн текстээр тайлбарлах",

    # confidence levels (already covered) and band labels
    "High": "Өндөр",
    "Medium": "Дунд",
    "Low": "Бага",

    # files filters
    "Type": "Төрөл",
    "All": "Бүх",

    # validation
    "Mode": "Горим",
    "Search": "Хайх",

    # Tendering hint
    "Other": "Бусад",

    # validation result statuses
    "Error": "Алдаа",
    "Warning": "Анхааруулга",

    # CDE/transmittal
    "Container": "Багц",

    # Action items
    "Action Items": "Үйл ажиллагааны зүйл",
    "Agenda": "Хөтөлбөр",
    "Attendees": "Оролцогчид",

    # Procurement extra
    "GR Ref": "Хүлээн авалт",
    "PO Ref": "ХАЗ дугаар",
    "PO #": "ХАЗ #",

    # Cards
    "Free": "Үнэгүй",
    "Built-in": "Суулгасан",

    # markup canvas
    "Geometry data available": "Геометрийн өгөгдөл байна",
    "No geometry data": "Геометрийн өгөгдөл алга",

    # files
    "Document": "Баримт",

    # match elements stages
    "Demolition": "Буулгалт",
    "Earthwork": "Шороон ажил",
    "Foundations": "Суурь",
    "Substructure": "Дэд бүтэц",
    "Superstructure": "Дээд бүтэц",
    "Envelope": "Гадаргуу",
    "Interior": "Дотор тал",
    "MEP": "MEP",
    "Finishes": "Засал чимэглэл",
    "Fixed furnishings": "Тогтсон тавилга",
    "Sitework": "Талбайн ажил",
    "Any stage": "Аливаа үе",

    # match elements buttons
    "Detail": "Дэлгэрэнгүй",
    "Library": "Сан",

    # short feedback
    "Cancelled": "Цуцлагдсан",
    "Saved": "Хадгалсан",

    # ai estimate buttons
    "New Estimate": "Шинэ тооцоо",
    "Estimate Results": "Тооцооны үр дүн",
    "Save": "Хадгалах",
    "Pos": "Бай.",

    # boq results
    "Estimated total": "Тооцоолсон нийт",
}


# Build a lowercase-keyed fallback map for case-insensitive lookups.
EXACT_LOWER: dict[str, str] = {k.lower(): v for k, v in EXACT.items()}


# Common English word -> Mongolian word for short labels (used when the
# whole value is a single short word/phrase not in EXACT).
WORDMAP = {
    "all": "бүх",
    "none": "байхгүй",
    "today": "өнөөдөр",
    "yesterday": "өчигдөр",
    "name": "нэр",
    "title": "гарчиг",
    "date": "огноо",
    "type": "төрөл",
    "code": "код",
    "unit": "нэгж",
    "rate": "үнэлгээ",
    "qty": "тоо",
    "quantity": "тоо хэмжээ",
    "total": "нийт",
    "status": "төлөв",
    "open": "нээлттэй",
    "closed": "хаагдсан",
    "draft": "ноорог",
    "submitted": "илгээсэн",
    "approved": "зөвшөөрөгдсөн",
    "rejected": "татгалзсан",
    "pending": "хүлээгдэж буй",
    "completed": "дууссан",
}


# ---------------------------------------------------------------------------
# 3. parse en.ts
# ---------------------------------------------------------------------------

KEY_RE = re.compile(r'^\s*"([^"]+)":\s*(.*?),?\s*$')


def parse_en_ts(path: Path) -> dict[str, str]:
    """‌⁠‍Parse en.ts. We rely on the file using JSON-quoted keys and values.

    Two value shapes occur:
      - single-line:  "key": "value",
      - multi-line:   the value spans continuation lines (rare in en.ts but
                      we tolerate it).
    Strategy: feed the body between the outer braces into json.loads. The
    file content is `const resource = { "translation": { ... } } as ...;`.
    We extract the object literal and JSON-load it.
    """
    text = path.read_text(encoding="utf-8")
    # Locate the first `{` after `const resource = ` and the matching `}` before `as`.
    m = re.search(r"const\s+resource\s*=\s*(\{.*?\})\s*as\s+\{", text, re.DOTALL)
    if not m:
        # alt: file ends with `};` directly (no `as`)
        m = re.search(r"const\s+resource\s*=\s*(\{.*?\});\s*$", text, re.DOTALL)
    if not m:
        raise RuntimeError("Could not locate resource object in en.ts")
    obj_text = m.group(1)
    # The object literal is JSON-compatible. Try to load directly.
    try:
        obj = json.loads(obj_text)
    except json.JSONDecodeError as e:
        # Fall back: try to strip trailing commas (TS allows them, JSON doesn't).
        cleaned = re.sub(r",(\s*[}\]])", r"\1", obj_text)
        obj = json.loads(cleaned)
        del e
    translation = obj.get("translation", {})
    if not isinstance(translation, dict):
        raise RuntimeError("`translation` is not a dict")
    return translation


# ---------------------------------------------------------------------------
# 4. translate one value
# ---------------------------------------------------------------------------

# Pattern templates: tuple of (compiled regex, mongolian template with \g<n>).
PATTERNS: list[tuple[re.Pattern, str]] = [
    # "Failed to X" -> "X-д амжилтгүй"
    (re.compile(r"^Failed to (.+?)\.?$"), r"\1 амжилтгүй"),
    (re.compile(r"^Could not (.+?)\.?$"), r"\1 чадсангүй"),
    # "X created" / "X deleted" / "X updated"
    (re.compile(r"^(.+?) created$"), r"\1 үүсгэгдлээ"),
    (re.compile(r"^(.+?) deleted$"), r"\1 устгагдлаа"),
    (re.compile(r"^(.+?) updated$"), r"\1 шинэчлэгдлээ"),
    (re.compile(r"^(.+?) saved$"), r"\1 хадгалагдлаа"),
    (re.compile(r"^(.+?) added$"), r"\1 нэмэгдлээ"),
    (re.compile(r"^(.+?) removed$"), r"\1 устгагдлаа"),
    (re.compile(r"^(.+?) approved$"), r"\1 зөвшөөрөгдлөө"),
    (re.compile(r"^(.+?) rejected$"), r"\1 татгалзагдлаа"),
    # "No X yet" -> "Хараахан X алга"
    (re.compile(r"^No (.+?) yet\.?$"), r"Хараахан \1 алга"),
    (re.compile(r"^No (.+?) found\.?$"), r"\1 олдсонгүй"),
    (re.compile(r"^No matching (.+?)$"), r"Тохирох \1 олдсонгүй"),
    # "Search X..." -> "X хайх..."
    (re.compile(r"^Search ([\w\s]+?)\.\.\.$"), r"\1 хайх..."),
    # "Loading X..." -> "X ачаалж байна..."
    (re.compile(r"^Loading ([\w\s]+?)\.\.\.$"), r"\1 ачаалж байна..."),
    (re.compile(r"^Loading ([\w\s]+?)…$"), r"\1 ачаалж байна…"),
    # "Create X" -> "X үүсгэх"
    (re.compile(r"^Create ([A-Z][\w\s]+?)$"), r"\1 үүсгэх"),
    (re.compile(r"^Add ([A-Z][\w\s]+?)$"), r"\1 нэмэх"),
    (re.compile(r"^New ([A-Z][\w\s]+?)$"), r"Шинэ \1"),
    (re.compile(r"^Edit ([A-Z][\w\s]+?)$"), r"\1 засах"),
    (re.compile(r"^Delete ([A-Z][\w\s]+?)\??$"), r"\1 устгах уу?"),
    # "X (optional)" -> "X (заавал биш)"
    (re.compile(r"^(.+?)\s*\(optional\)$"), r"\1 (заавал биш)"),
    # "{{count}} X" -> "{{count}} <translated>"  -- handled below by EXACT on suffix
]


def translate_value(en: str) -> str:
    """‌⁠‍Translate one English value to Mongolian. Falls back to English."""
    if not isinstance(en, str):
        return en
    stripped = en.strip()
    if not stripped:
        return en

    # 1. exact match
    if stripped in EXACT:
        return EXACT[stripped]

    # 2. case-insensitive exact match for short labels (1–3 words)
    if len(stripped.split()) <= 3:
        low = stripped.lower()
        if low in EXACT_LOWER:
            return EXACT_LOWER[low]

    # 3. pattern templates
    for pat, repl in PATTERNS:
        m = pat.match(stripped)
        if m:
            try:
                result = pat.sub(repl, stripped)
                return result
            except Exception:
                continue

    # 4. fallback: keep English (i18next falls back to en anyway, but the key
    #    will exist in mn.ts so analytics tools see full coverage)
    return en


# ---------------------------------------------------------------------------
# 5. emit mn.ts
# ---------------------------------------------------------------------------

HEADER = """// Mongolian (mn) locale.
//
// Generated from en.ts with manual translations for the most common UI
// strings. Strings that don't yet have a hand-checked Mongolian rendering
// are kept in English on purpose — i18next still serves them, and a native
// speaker can replace them one by one without breaking the build.
//
// Contributions welcome: see en.ts for the canonical key list.

"""

FOOTER = " as { translation: Record<string, string> };\n\nexport default resource;\n"


def emit_mn_ts(out_path: Path, translations: dict[str, str]) -> None:
    out = {"translation": {k: translations[k] for k in sorted(translations.keys())}}
    body = json.dumps(out, ensure_ascii=False, indent=2)
    # JSON uses lowercase booleans, etc; we only have strings here, so this is fine.
    text = HEADER + "const resource = " + body + FOOTER
    out_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. main
# ---------------------------------------------------------------------------


def main() -> int:
    en = parse_en_ts(EN_PATH)
    print(f"Loaded {len(en)} keys from en.ts")

    out: dict[str, str] = {}
    skipped_english = 0
    translated_exact = 0
    translated_pattern = 0
    preserved = 0

    for key, en_val in en.items():
        # Always preserve EXISTING_MN translations first.
        if key in EXISTING_MN:
            out[key] = EXISTING_MN[key]
            preserved += 1
            continue

        mn_val = translate_value(en_val)
        if mn_val == en_val:
            skipped_english += 1
        elif mn_val in EXACT.values() or (
            isinstance(en_val, str) and en_val.strip() in EXACT
        ):
            translated_exact += 1
        else:
            translated_pattern += 1
        out[key] = mn_val

    emit_mn_ts(MN_PATH, out)
    print(f"Wrote {MN_PATH}")
    print(f"  preserved from stub: {preserved}")
    print(f"  exact / pattern translated: {translated_exact + translated_pattern}")
    print(f"  kept in English (fallback): {skipped_english}")
    print(f"  total keys: {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
