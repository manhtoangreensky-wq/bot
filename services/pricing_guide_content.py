"""Shared public pricing and guide copy for TOAN AAS.

This module is intentionally copy-only. It does not calculate charges, call
product engines, or change wallet/payment behavior.
"""

from __future__ import annotations

import html
import re
from typing import Iterable

from services.chat_pro_pricing import opus_price_per_thousand_labels
from services import video_ai_real_pricing


PRICING_DOWNLOAD_FILENAME = "bang-gia-toan-aas.md"
GUIDE_DOWNLOAD_FILENAME = "huong-dan-su-dung-toan-aas.md"

CONFIRM_GATE_COPY = (
    "TOAN AAS sẽ hiển thị hóa đơn trước khi xử lý. Hệ thống chỉ trừ Xu sau khi "
    "anh/chị xác nhận và tác vụ tạo ra kết quả hợp lệ."
)
MAINTENANCE_NOTICE = "Hệ thống đang bảo trì/nâng cấp. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."

TECHNICAL_WORDS = (
    "provider",
    "api",
    "asr",
    "tts",
    "mux",
    "ffmpeg",
    "adapter",
    "debug",
    "route",
    "payload",
    "traceback",
    "runtimeerror",
    "model id",
    "database",
    "worker",
)


PUBLIC_COPY_LOCALES = frozenset({
    "vi", "en", "zh", "es", "pt", "fr", "de", "ja", "ko", "hi", "ar",
    "ru", "tr", "th", "fil", "it", "id",
})


# Public documentation only. These labels do not control account market,
# payment eligibility, promotions, prices, or any product flow.
_PUBLIC_LOCALE_COPY = {
    "en": {
        "pricing": "TOAN AAS Pricing", "guide": "TOAN AAS Customer Guide", "home": "Home", "choose": "Choose a section:",
        "quote": "TOAN AAS shows the quote before processing and charges Xu only after confirmation and a valid result.",
        "images": "AI Images", "video": "Product Video", "music": "AI Music", "voice": "Voice",
        "subtitles": "Subtitles / Translation / Dubbing", "documents": "Documents / Files", "member": "Membership and Benefits", "free": "Free Items",
        "image_unit": "image", "video_unit": "scene", "input": "input", "output": "output",
    },
    "zh": {
        "pricing": "TOAN AAS 价格", "guide": "TOAN AAS 使用指南", "home": "首页", "choose": "请选择要查看的内容：",
        "quote": "系统会在处理前显示报价；只有在确认且获得有效结果后才会扣除 Xu。",
        "images": "AI 图片", "video": "Product Video", "music": "AI 音乐", "voice": "语音",
        "subtitles": "字幕 / 翻译 / 配音", "documents": "文档 / 文件", "member": "会员与优惠", "free": "免费项目",
        "image_unit": "张", "video_unit": "场", "input": "输入", "output": "输出",
    },
    "es": {
        "pricing": "Precios TOAN AAS", "guide": "Guía del usuario TOAN AAS", "home": "Inicio", "choose": "Elige una sección:",
        "quote": "El presupuesto se muestra antes de confirmar.", "images": "Imágenes con IA", "video": "Video de producto", "music": "Música con IA", "voice": "Voz",
        "subtitles": "Subtítulos / Traducción / Doblaje", "documents": "Documentos", "member": "Membresía", "free": "Elementos gratuitos",
        "image_unit": "imagen", "video_unit": "escena", "input": "entrada", "output": "salida",
    },
    "pt": {
        "pricing": "Preços TOAN AAS", "guide": "Guia do usuário TOAN AAS", "home": "Início", "choose": "Escolha uma seção:",
        "quote": "O orçamento é exibido antes da confirmação.", "images": "Imagens com IA", "video": "Vídeo do produto", "music": "Música com IA", "voice": "Voz",
        "subtitles": "Legendas / Tradução / Dublagem", "documents": "Documentos", "member": "Associação", "free": "Itens gratuitos",
        "image_unit": "imagem", "video_unit": "cena", "input": "entrada", "output": "saída",
    },
    "fr": {
        "pricing": "Tarifs TOAN AAS", "guide": "Guide d’utilisation TOAN AAS", "home": "Accueil", "choose": "Choisissez une section :",
        "quote": "Le devis s’affiche avant la confirmation.", "images": "Images IA", "video": "Vidéo produit", "music": "Musique IA", "voice": "Voix",
        "subtitles": "Sous-titres / Traduction / Doublage", "documents": "Documents", "member": "Adhésion", "free": "Éléments gratuits",
        "image_unit": "image", "video_unit": "scène", "input": "entrée", "output": "sortie",
    },
    "de": {
        "pricing": "TOAN AAS Preise", "guide": "TOAN AAS Benutzerhandbuch", "home": "Startseite", "choose": "Wähle einen Bereich:",
        "quote": "Das Angebot wird vor der Bestätigung angezeigt.", "images": "KI-Bilder", "video": "Produktvideo", "music": "KI-Musik", "voice": "Stimme",
        "subtitles": "Untertitel / Übersetzung / Synchronisation", "documents": "Dokumente", "member": "Mitgliedschaft", "free": "Kostenlose Elemente",
        "image_unit": "Bild", "video_unit": "Szene", "input": "Eingabe", "output": "Ausgabe",
    },
    "ja": {
        "pricing": "TOAN AAS 料金", "guide": "TOAN AAS ユーザーガイド", "home": "ホーム", "choose": "項目を選択:",
        "quote": "確認前に見積もりが表示されます。", "images": "AI画像", "video": "商品動画", "music": "AI音楽", "voice": "音声",
        "subtitles": "字幕 / 翻訳 / 吹き替え", "documents": "ドキュメント", "member": "メンバーシップ", "free": "無料項目",
        "image_unit": "枚", "video_unit": "シーン", "input": "入力", "output": "出力",
    },
    "ko": {
        "pricing": "TOAN AAS 요금", "guide": "TOAN AAS 사용자 가이드", "home": "홈", "choose": "섹션을 선택하세요:",
        "quote": "확인 전에 견적이 표시됩니다.", "images": "AI 이미지", "video": "제품 동영상", "music": "AI 음악", "voice": "음성",
        "subtitles": "자막 / 번역 / 더빙", "documents": "문서", "member": "멤버십", "free": "무료 항목",
        "image_unit": "장", "video_unit": "장면", "input": "입력", "output": "출력",
    },
    "hi": {
        "pricing": "TOAN AAS मूल्य", "guide": "TOAN AAS उपयोगकर्ता मार्गदर्शिका", "home": "होम", "choose": "एक अनुभाग चुनें:",
        "quote": "पुष्टि से पहले अनुमान दिखाया जाता है।", "images": "AI चित्र", "video": "उत्पाद वीडियो", "music": "AI संगीत", "voice": "आवाज़",
        "subtitles": "उपशीर्षक / अनुवाद / डबिंग", "documents": "दस्तावेज़", "member": "सदस्यता", "free": "मुफ़्त आइटम",
        "image_unit": "चित्र", "video_unit": "दृश्य", "input": "इनपुट", "output": "आउटपुट",
    },
    "ar": {
        "pricing": "أسعار TOAN AAS", "guide": "دليل المستخدم TOAN AAS", "home": "الرئيسية", "choose": "اختر قسمًا:",
        "quote": "يظهر عرض السعر قبل التأكيد.", "images": "صور بالذكاء الاصطناعي", "video": "فيديو المنتج", "music": "موسيقى بالذكاء الاصطناعي", "voice": "الصوت",
        "subtitles": "الترجمة النصية / الترجمة / الدبلجة", "documents": "المستندات", "member": "العضوية", "free": "العناصر المجانية",
        "image_unit": "صورة", "video_unit": "مشهد", "input": "إدخال", "output": "إخراج",
    },
    "ru": {
        "pricing": "Цены TOAN AAS", "guide": "Руководство пользователя TOAN AAS", "home": "Главная", "choose": "Выберите раздел:",
        "quote": "Расчёт отображается перед подтверждением.", "images": "Изображения с ИИ", "video": "Видео о продукте", "music": "Музыка с ИИ", "voice": "Голос",
        "subtitles": "Субтитры / Перевод / Озвучка", "documents": "Документы", "member": "Членство", "free": "Бесплатные элементы",
        "image_unit": "изображение", "video_unit": "сцена", "input": "ввод", "output": "вывод",
    },
    "tr": {
        "pricing": "TOAN AAS Fiyatları", "guide": "TOAN AAS Kullanım Kılavuzu", "home": "Ana sayfa", "choose": "Bir bölüm seçin:",
        "quote": "Fiyat teklifi onaydan önce gösterilir.", "images": "Yapay zekâ görselleri", "video": "Ürün videosu", "music": "Yapay zekâ müziği", "voice": "Ses",
        "subtitles": "Altyazılar / Çeviri / Dublaj", "documents": "Belgeler", "member": "Üyelik", "free": "Ücretsiz öğeler",
        "image_unit": "görsel", "video_unit": "sahne", "input": "girdi", "output": "çıktı",
    },
    "th": {
        "pricing": "ราคา TOAN AAS", "guide": "คู่มือผู้ใช้ TOAN AAS", "home": "หน้าหลัก", "choose": "เลือกหัวข้อ:",
        "quote": "ระบบจะแสดงใบเสนอราคาก่อนยืนยัน", "images": "ภาพ AI", "video": "วิดีโอสินค้า", "music": "เพลง AI", "voice": "เสียง",
        "subtitles": "คำบรรยาย / แปลภาษา / พากย์เสียง", "documents": "เอกสาร", "member": "สมาชิกภาพ", "free": "รายการฟรี",
        "image_unit": "ภาพ", "video_unit": "ฉาก", "input": "อินพุต", "output": "เอาต์พุต",
    },
    "fil": {
        "pricing": "Mga Presyo ng TOAN AAS", "guide": "Gabay para sa gumagamit ng TOAN AAS", "home": "Home", "choose": "Pumili ng seksyon:",
        "quote": "Ipinapakita ang pagtatantya bago kumpirmahin.", "images": "Mga larawang AI", "video": "Video ng produkto", "music": "Musikang AI", "voice": "Boses",
        "subtitles": "Mga subtitle / Pagsasalin / Pag-dub", "documents": "Mga dokumento", "member": "Pagiging miyembro", "free": "Mga libreng item",
        "image_unit": "larawan", "video_unit": "eksena", "input": "input", "output": "output",
    },
    "it": {
        "pricing": "Prezzi TOAN AAS", "guide": "Guida utente TOAN AAS", "home": "Home", "choose": "Scegli una sezione:",
        "quote": "Il preventivo viene mostrato prima della conferma.", "images": "Immagini AI", "video": "Video del prodotto", "music": "Musica AI", "voice": "Voce",
        "subtitles": "Sottotitoli / Traduzione / Doppiaggio", "documents": "Documenti", "member": "Iscrizione", "free": "Elementi gratuiti",
        "image_unit": "immagine", "video_unit": "scena", "input": "input", "output": "output",
    },
    "id": {
        "pricing": "Harga TOAN AAS", "guide": "Panduan Pengguna TOAN AAS", "home": "Beranda", "choose": "Pilih bagian:",
        "quote": "Penawaran harga ditampilkan sebelum konfirmasi.", "images": "Gambar AI", "video": "Video produk", "music": "Musik AI", "voice": "Suara",
        "subtitles": "Subtitle / Terjemahan / Dubbing", "documents": "Dokumen", "member": "Keanggotaan", "free": "Item gratis",
        "image_unit": "gambar", "video_unit": "adegan", "input": "masukan", "output": "keluaran",
    },
}


def public_copy_locale(lang: str | None = None) -> str:
    """Return the public-copy locale without changing user or market state."""

    value = str(lang or "").strip().lower().replace("_", "-")
    aliases = {
        "vi-vn": "vi", "zh-cn": "zh", "cn": "zh", "pt-br": "pt",
        "fil-ph": "fil", "id-id": "id",
    }
    value = aliases.get(value, value)
    return value if value in PUBLIC_COPY_LOCALES else "en"


def _public_locale_copy(lang: str | None = None) -> dict[str, str]:
    return dict(_PUBLIC_LOCALE_COPY.get(public_copy_locale(lang), _PUBLIC_LOCALE_COPY["en"]))


def _public_copy_labels(lang: str | None = None) -> dict[str, str]:
    locale = public_copy_locale(lang)
    if locale == "vi":
        return {"home": "← Trang chủ", "pricing": "Bảng giá TOAN AAS", "guide": "Hướng dẫn sử dụng TOAN AAS"}
    copy = _public_locale_copy(locale)
    return {"home": f"← {copy['home']}", "pricing": copy["pricing"], "guide": copy["guide"]}


def public_page_title(page: str, lang: str | None = None) -> str:
    """Return the existing public native label for a pricing or guide page."""

    labels = _public_copy_labels(lang)
    key = "pricing" if str(page or "").strip().lower() == "pricing" else "guide"
    return labels[key]


_IMAGE_LABELS = {
    "en": {
        "low": "Fast & clear",
        "standard": "Balanced",
        "standard_warranty": "Balanced + retry",
        "common": "Creative detail",
        "common_warranty": "Creative detail + retry",
        "high": "Premium control",
        "high_warranty": "Premium control + retry",
    },
    "zh": {
        "low": "快速清晰",
        "standard": "平衡",
        "standard_warranty": "平衡 + 重试保障",
        "common": "创意细节",
        "common_warranty": "创意细节 + 重试保障",
        "high": "高级控制",
        "high_warranty": "高级控制 + 重试保障",
    },
    "es": {
        "low": "Rápido y nítido",
        "standard": "Equilibrado",
        "standard_warranty": "Equilibrado + reintento",
        "common": "Detalle creativo",
        "common_warranty": "Detalle creativo + reintento",
        "high": "Control premium",
        "high_warranty": "Control premium + reintento",
    },
    "pt": {
        "low": "Rápido e nítido",
        "standard": "Equilibrado",
        "standard_warranty": "Equilibrado + nova tentativa",
        "common": "Detalhe criativo",
        "common_warranty": "Detalhe criativo + nova tentativa",
        "high": "Controle premium",
        "high_warranty": "Controle premium + nova tentativa",
    },
    "fr": {
        "low": "Rapide et net",
        "standard": "Équilibré",
        "standard_warranty": "Équilibré + nouvelle tentative",
        "common": "Détail créatif",
        "common_warranty": "Détail créatif + nouvelle tentative",
        "high": "Contrôle premium",
        "high_warranty": "Contrôle premium + nouvelle tentative",
    },
    "de": {
        "low": "Schnell und klar",
        "standard": "Ausgewogen",
        "standard_warranty": "Ausgewogen + erneuter Versuch",
        "common": "Kreatives Detail",
        "common_warranty": "Kreatives Detail + erneuter Versuch",
        "high": "Premium-Steuerung",
        "high_warranty": "Premium-Steuerung + erneuter Versuch",
    },
    "ja": {
        "low": "高速・高精細",
        "standard": "バランス",
        "standard_warranty": "バランス + 再試行保証",
        "common": "創造的な細部",
        "common_warranty": "創造的な細部 + 再試行保証",
        "high": "高度な制御",
        "high_warranty": "高度な制御 + 再試行保証",
    },
    "ko": {
        "low": "빠르고 선명함",
        "standard": "균형형",
        "standard_warranty": "균형형 + 재시도 보장",
        "common": "창의적 디테일",
        "common_warranty": "창의적 디테일 + 재시도 보장",
        "high": "고급 제어",
        "high_warranty": "고급 제어 + 재시도 보장",
    },
    "hi": {
        "low": "तेज़ और स्पष्ट",
        "standard": "संतुलित",
        "standard_warranty": "संतुलित + पुनः प्रयास",
        "common": "रचनात्मक विवरण",
        "common_warranty": "रचनात्मक विवरण + पुनः प्रयास",
        "high": "प्रीमियम नियंत्रण",
        "high_warranty": "प्रीमियम नियंत्रण + पुनः प्रयास",
    },
    "ar": {
        "low": "سريع وواضح",
        "standard": "متوازن",
        "standard_warranty": "متوازن + إعادة محاولة",
        "common": "تفاصيل إبداعية",
        "common_warranty": "تفاصيل إبداعية + إعادة محاولة",
        "high": "تحكم متقدم",
        "high_warranty": "تحكم متقدم + إعادة محاولة",
    },
    "ru": {
        "low": "Быстро и чётко",
        "standard": "Сбалансированный",
        "standard_warranty": "Сбалансированный + повторная попытка",
        "common": "Творческие детали",
        "common_warranty": "Творческие детали + повторная попытка",
        "high": "Премиум-контроль",
        "high_warranty": "Премиум-контроль + повторная попытка",
    },
    "tr": {
        "low": "Hızlı ve net",
        "standard": "Dengeli",
        "standard_warranty": "Dengeli + yeniden deneme",
        "common": "Yaratıcı ayrıntı",
        "common_warranty": "Yaratıcı ayrıntı + yeniden deneme",
        "high": "Üst düzey kontrol",
        "high_warranty": "Üst düzey kontrol + yeniden deneme",
    },
    "th": {
        "low": "รวดเร็วและคมชัด",
        "standard": "สมดุล",
        "standard_warranty": "สมดุล + ลองใหม่",
        "common": "รายละเอียดสร้างสรรค์",
        "common_warranty": "รายละเอียดสร้างสรรค์ + ลองใหม่",
        "high": "การควบคุมระดับพรีเมียม",
        "high_warranty": "การควบคุมระดับพรีเมียม + ลองใหม่",
    },
    "fil": {
        "low": "Mabilis at malinaw",
        "standard": "Balanse",
        "standard_warranty": "Balanse + muling subukan",
        "common": "Malikhaing detalye",
        "common_warranty": "Malikhaing detalye + muling subukan",
        "high": "Premium na kontrol",
        "high_warranty": "Premium na kontrol + muling subukan",
    },
    "it": {
        "low": "Rapido e nitido",
        "standard": "Bilanciato",
        "standard_warranty": "Bilanciato + nuovo tentativo",
        "common": "Dettaglio creativo",
        "common_warranty": "Dettaglio creativo + nuovo tentativo",
        "high": "Controllo premium",
        "high_warranty": "Controllo premium + nuovo tentativo",
    },
    "id": {
        "low": "Cepat dan jelas",
        "standard": "Seimbang",
        "standard_warranty": "Seimbang + coba lagi",
        "common": "Detail kreatif",
        "common_warranty": "Detail kreatif + coba lagi",
        "high": "Kontrol premium",
        "high_warranty": "Kontrol premium + coba lagi",
    },
}

_PRODUCT_VIDEO_LABELS = {
    "en": {
        200: "Fast & focused",
        300: "Standard with audio",
        400: "Balanced clarity",
        500: "Stable motion",
        600: "Motion with audio",
        700: "Long scene with audio",
        800: "Flexible premium",
        1000: "Natural performance",
        1200: "Multi-angle reference",
        1500: "Cinematic multi-shot",
    },
    "zh": {
        200: "快速聚焦",
        300: "标准含音频",
        400: "清晰均衡",
        500: "稳定运动",
        600: "运动含音频",
        700: "长场景含音频",
        800: "灵活高级",
        1000: "自然表演",
        1200: "多机位参考",
        1500: "电影多镜头",
    },
    "es": {
        200: "Rápido y enfocado",
        300: "Estándar con audio",
        400: "Claridad equilibrada",
        500: "Movimiento estable",
        600: "Movimiento con audio",
        700: "Escena larga con audio",
        800: "Premium flexible",
        1000: "Interpretación natural",
        1200: "Referencia multiángulo",
        1500: "Cinemático multitoma",
    },
    "pt": {
        200: "Rápido e focado",
        300: "Padrão com áudio",
        400: "Nitidez equilibrada",
        500: "Movimento estável",
        600: "Movimento com áudio",
        700: "Cena longa com áudio",
        800: "Premium flexível",
        1000: "Desempenho natural",
        1200: "Referência multiângulo",
        1500: "Cinematográfico com vários planos",
    },
    "fr": {
        200: "Rapide et ciblé",
        300: "Standard avec audio",
        400: "Clarté équilibrée",
        500: "Mouvement stable",
        600: "Mouvement avec audio",
        700: "Scène longue avec audio",
        800: "Premium flexible",
        1000: "Interprétation naturelle",
        1200: "Référence multi-angle",
        1500: "Cinématographique multi-plan",
    },
    "de": {
        200: "Schnell und fokussiert",
        300: "Standard mit Audio",
        400: "Ausgewogene Klarheit",
        500: "Stabile Bewegung",
        600: "Bewegung mit Audio",
        700: "Lange Szene mit Audio",
        800: "Flexibles Premium",
        1000: "Natürliches Spiel",
        1200: "Mehrwinkel-Referenz",
        1500: "Filmisch mit mehreren Einstellungen",
    },
    "ja": {
        200: "高速・焦点重視",
        300: "標準・音声付き",
        400: "バランスの取れた明瞭さ",
        500: "安定した動き",
        600: "音声付きの動き",
        700: "長尺シーン・音声付き",
        800: "柔軟なプレミアム",
        1000: "自然な演技",
        1200: "マルチアングル参照",
        1500: "映画的マルチショット",
    },
    "ko": {
        200: "빠르고 집중된",
        300: "오디오 포함 표준",
        400: "균형 잡힌 선명도",
        500: "안정적인 움직임",
        600: "오디오 포함 움직임",
        700: "오디오 포함 긴 장면",
        800: "유연한 프리미엄",
        1000: "자연스러운 연기",
        1200: "다중 앵글 참조",
        1500: "시네마틱 멀티샷",
    },
    "hi": {
        200: "तेज़ और केंद्रित",
        300: "ऑडियो सहित मानक",
        400: "संतुलित स्पष्टता",
        500: "स्थिर गति",
        600: "ऑडियो सहित गति",
        700: "ऑडियो सहित लंबा दृश्य",
        800: "लचीला प्रीमियम",
        1000: "स्वाभाविक अभिनय",
        1200: "बहु-कोण संदर्भ",
        1500: "सिनेमाई मल्टी-शॉट",
    },
    "ar": {
        200: "سريع ومركّز",
        300: "قياسي مع صوت",
        400: "وضوح متوازن",
        500: "حركة مستقرة",
        600: "حركة مع صوت",
        700: "مشهد طويل مع صوت",
        800: "متميز ومرن",
        1000: "أداء طبيعي",
        1200: "مرجع متعدد الزوايا",
        1500: "سينمائي متعدد اللقطات",
    },
    "ru": {
        200: "Быстрый и сфокусированный",
        300: "Стандарт со звуком",
        400: "Сбалансированная чёткость",
        500: "Стабильное движение",
        600: "Движение со звуком",
        700: "Длинная сцена со звуком",
        800: "Гибкий премиум",
        1000: "Естественная игра",
        1200: "Многоракурсный референс",
        1500: "Кинематографичный мультикадр",
    },
    "tr": {
        200: "Hızlı ve odaklı",
        300: "Sesli standart",
        400: "Dengeli netlik",
        500: "Kararlı hareket",
        600: "Sesli hareket",
        700: "Sesli uzun sahne",
        800: "Esnek premium",
        1000: "Doğal oyunculuk",
        1200: "Çok açılı referans",
        1500: "Sinematik çoklu çekim",
    },
    "th": {
        200: "รวดเร็วและเน้นจุดสำคัญ",
        300: "มาตรฐานพร้อมเสียง",
        400: "ความคมชัดสมดุล",
        500: "การเคลื่อนไหวเสถียร",
        600: "การเคลื่อนไหวพร้อมเสียง",
        700: "ฉากยาวพร้อมเสียง",
        800: "พรีเมียมแบบยืดหยุ่น",
        1000: "การแสดงเป็นธรรมชาติ",
        1200: "การอ้างอิงหลายมุม",
        1500: "ภาพยนตร์หลายช็อต",
    },
    "fil": {
        200: "Mabilis at nakatuon",
        300: "Pamantayan na may audio",
        400: "Balanseng linaw",
        500: "Matatag na galaw",
        600: "Galaw na may audio",
        700: "Mahabang eksena na may audio",
        800: "Flexible na premium",
        1000: "Likas na pagganap",
        1200: "Sangguniang maraming anggulo",
        1500: "Sinematikong maraming kuha",
    },
    "it": {
        200: "Rapido e mirato",
        300: "Standard con audio",
        400: "Nitidezza bilanciata",
        500: "Movimento stabile",
        600: "Movimento con audio",
        700: "Scena lunga con audio",
        800: "Premium flessibile",
        1000: "Interpretazione naturale",
        1200: "Riferimento multiangolo",
        1500: "Cinematografico multi-inquadratura",
    },
    "id": {
        200: "Cepat dan terfokus",
        300: "Standar dengan audio",
        400: "Kejelasan seimbang",
        500: "Gerakan stabil",
        600: "Gerakan dengan audio",
        700: "Adegan panjang dengan audio",
        800: "Premium fleksibel",
        1000: "Performa alami",
        1200: "Referensi multi-sudut",
        1500: "Sinematik multi-shot",
    },
}


_PRODUCT_VIDEO_DURATION_UNITS = {
    "en": "seconds",
    "zh": "秒",
    "es": "segundos",
    "pt": "segundos",
    "fr": "secondes",
    "de": "Sekunden",
    "ja": "秒",
    "ko": "초",
    "hi": "सेकंड",
    "ar": "ثوانٍ",
    "ru": "секунд",
    "tr": "saniye",
    "th": "วินาที",
    "fil": "segundo",
    "it": "secondi",
    "id": "detik",
}


# Public-copy snapshot authorized from the Video canonical checkpoint
# 3ba5986712d4dbab38c35b07be193edfa7289ca5.  This module is intentionally
# display-only: it must not control Product Video routing, invoice, wallet, or
# engine behavior while the separately-owned runtime change is integrated.
PUBLIC_PRODUCT_VIDEO_CATALOG_VERSION = "2026-08-11.video.5"
_PUBLIC_PRODUCT_VIDEO_CATALOG = (
    {"tier_id": 200, "name": "Nhanh gọn", "seconds": 5, "unit_xu": 200},
    {"tier_id": 300, "name": "Tiêu chuẩn có âm thanh", "seconds": 5, "unit_xu": 220},
    {"tier_id": 400, "name": "Cân bằng rõ nét", "seconds": 8, "unit_xu": 80},
    {"tier_id": 500, "name": "Chuyển động ổn định", "seconds": 5, "unit_xu": 110},
    {"tier_id": 600, "name": "Chuyển động có âm thanh", "seconds": 5, "unit_xu": 160},
    {"tier_id": 700, "name": "Cảnh dài có âm thanh", "seconds": 15, "unit_xu": 220},
    {"tier_id": 800, "name": "Cao cấp linh hoạt", "seconds": 10, "unit_xu": 370},
    {"tier_id": 1000, "name": "Diễn xuất chân thật", "seconds": 6, "unit_xu": 370},
    {"tier_id": 1200, "name": "Đa góc máy", "seconds": 8, "unit_xu": 1260},
    {"tier_id": 1500, "name": "Điện ảnh nhiều cảnh", "seconds": 10, "unit_xu": 2360},
)


_VIDEO_MULTISCENE_DISCOUNT_COPY = {
    "vi": "1 cảnh không giảm; 2–5 cảnh: giảm 10%; 6–10 cảnh: giảm 15%; 11–20 cảnh: giảm 20%.",
    "en": "1 scene: no discount; 2–5 scenes: 10% off; 6–10 scenes: 15% off; 11–20 scenes: 20% off.",
    "zh": "1 场不减价；2–5 场减 10%；6–10 场减 15%；11–20 场减 20%。",
    "es": "1 escena: sin descuento; 2–5 escenas: 10 % de descuento; 6–10 escenas: 15 %; 11–20 escenas: 20 %.",
    "pt": "1 cena: sem desconto; 2–5 cenas: 10% de desconto; 6–10 cenas: 15%; 11–20 cenas: 20%.",
    "fr": "1 scène : sans remise ; 2–5 scènes : -10 % ; 6–10 scènes : -15 % ; 11–20 scènes : -20 %.",
    "de": "1 Szene: kein Rabatt; 2–5 Szenen: 10 % Rabatt; 6–10 Szenen: 15 %; 11–20 Szenen: 20 %.",
    "ja": "1シーンは割引なし、2～5シーンは10%割引、6～10シーンは15%割引、11～20シーンは20%割引。",
    "ko": "1장면은 할인 없음, 2–5장면은 10% 할인, 6–10장면은 15% 할인, 11–20장면은 20% 할인.",
    "hi": "1 दृश्य: कोई छूट नहीं; 2–5 दृश्य: 10% छूट; 6–10 दृश्य: 15% छूट; 11–20 दृश्य: 20% छूट।",
    "ar": "مشهد واحد: بلا خصم؛ 2–5 مشاهد: خصم 10٪؛ 6–10 مشاهد: 15٪؛ 11–20 مشهدًا: 20٪.",
    "ru": "1 сцена: без скидки; 2–5 сцен: скидка 10%; 6–10 сцен: 15%; 11–20 сцен: 20%.",
    "tr": "1 sahne: indirim yok; 2–5 sahne: %10 indirim; 6–10 sahne: %15; 11–20 sahne: %20.",
    "th": "1 ฉาก: ไม่มีส่วนลด; 2–5 ฉาก: ลด 10%; 6–10 ฉาก: ลด 15%; 11–20 ฉาก: ลด 20%",
    "fil": "1 eksena: walang diskuwento; 2–5 eksena: 10% diskuwento; 6–10 eksena: 15%; 11–20 eksena: 20%.",
    "it": "1 scena: nessuno sconto; 2–5 scene: sconto del 10%; 6–10 scene: 15%; 11–20 scene: 20%.",
    "id": "1 adegan: tanpa diskon; 2–5 adegan: diskon 10%; 6–10 adegan: 15%; 11–20 adegan: 20%.",
}


def _format_public_xu(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _clean_lines(lines: Iterable[str]) -> list[str]:
    return [str(line) for line in lines]


def strip_html_tags(text: str) -> str:
    return re.sub(r"</?(?:b|code|i|u|strong|em)>", "", str(text or ""))


def technical_words_found(text: str) -> list[str]:
    lowered = strip_html_tags(text).lower()
    found = []
    for word in TECHNICAL_WORDS:
        if re.search(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])", lowered):
            found.append(word)
    return found


def html_lines_to_markdown(lines: Iterable[str]) -> str:
    converted = []
    for line in _clean_lines(lines):
        clean = strip_html_tags(line)
        clean = clean.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        converted.append(clean)
    return "\n".join(converted).strip() + "\n"


def lines_to_html_page(
    title: str,
    lines: Iterable[str],
    *,
    lang: str = "vi",
    home_href: str = "/",
) -> str:
    locale = public_copy_locale(lang)
    labels = _public_copy_labels(locale)
    body_lines = []
    for line in _clean_lines(lines):
        if not line:
            body_lines.append("")
        elif line.startswith(("• ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ")):
            body_lines.append(line)
        else:
            body_lines.append(line)
    body = "<br>\n".join(body_lines)
    return f"""<!doctype html>
<html lang="{html.escape(locale)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f7fbf9; color: #10241d; line-height: 1.6; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 32px 18px 48px; }}
    .card {{ background: #fff; border: 1px solid #d8ece4; border-radius: 14px; padding: 24px; box-shadow: 0 12px 32px rgba(20, 80, 60, .08); }}
    a {{ color: #087f5b; font-weight: 700; }}
  </style>
</head>
<body>
  <main>
    <p><a href="{html.escape(home_href, quote=True)}">{html.escape(labels['home'])}</a></p>
    <div class="card">{body}</div>
  </main>
</body>
</html>
"""


def pricing_menu_labels() -> list[tuple[str, str]]:
    return [
        ("pricing|total", "💰 Bảng giá tổng"),
        ("pricing|voice", "🎙 Bảng giá Giọng nói"),
        ("pricing|music", "🎵 Bảng giá Nhạc AI"),
        ("pricing|video", "🎬 Bảng giá Video"),
        ("pricing|subtitle", "🌐 Bảng giá Phụ đề / Lồng tiếng"),
        ("pricing|image", "🖼 Bảng giá Hình ảnh"),
        ("pricing|free", "🎁 Miễn phí / Không tính Xu"),
        ("pricing|member", "🎁 Khuyến mãi / Thành viên"),
        ("pricing|guide", "📘 Hướng dẫn sử dụng"),
        ("pricing|download_pricing", "📥 Tải bảng giá"),
        ("pricing|download_guide", "📘 Tải hướng dẫn sử dụng"),
    ]


def canonical_image_price_lines(lang: str = "vi") -> list[str]:
    locale = public_copy_locale(lang)
    if locale == "vi":
        return [
            f"• {entry['name']}: <b>{int(entry['unit_xu'])} Xu / ảnh</b>."
            for entry in video_ai_real_pricing.public_image_quality_catalog()
        ]
    copy = _public_locale_copy(locale)
    labels = _IMAGE_LABELS[locale]
    return [
        f"• {labels.get(str(entry['tier_key']), str(entry['tier_key']))}: "
        f"<b>{int(entry['unit_xu'])} Xu / {copy['image_unit']}</b>."
        for entry in video_ai_real_pricing.public_image_quality_catalog()
    ]


def public_product_video_catalog() -> list[dict[str, int | str]]:
    """Return the approved public Video catalog without touching Video runtime."""

    return [dict(entry) for entry in _PUBLIC_PRODUCT_VIDEO_CATALOG]


def public_video_price_lines() -> list[str]:
    """Return Vietnamese Markdown-ready public Video prices from the checkpoint."""

    return [
        (
            f"• {entry['name']} — {int(entry['seconds'])} giây/cảnh: "
            f"{int(entry['unit_xu']):,} Xu/cảnh."
        ).replace(",", ".")
        for entry in public_product_video_catalog()
    ]


def canonical_product_video_price_lines(lang: str = "vi") -> list[str]:
    locale = public_copy_locale(lang)
    if locale == "vi":
        return [
            f"• {entry['name']}: <b>{_format_public_xu(int(entry['unit_xu']))} Xu / cảnh</b> — {int(entry['seconds'])} giây."
            for entry in public_product_video_catalog()
        ]
    copy = _public_locale_copy(locale)
    labels = _PRODUCT_VIDEO_LABELS[locale]
    duration_unit = _PRODUCT_VIDEO_DURATION_UNITS[locale]
    return [
        f"• {labels.get(int(entry['tier_id']), str(entry['tier_id']))}: "
        f"<b>{_format_public_xu(int(entry['unit_xu']))} Xu / {copy['video_unit']}</b> — {int(entry['seconds'])} {duration_unit}."
        for entry in public_product_video_catalog()
    ]


def video_multiscene_discount_lines(lang: str = "vi") -> list[str]:
    """Return only the approved public Video scene-discount boundary."""

    locale = public_copy_locale(lang)
    if locale == "vi":
        return [
            "• 1 cảnh không giảm.",
            "• 2–5 cảnh: giảm 10%.",
            "• 6–10 cảnh: giảm 15%.",
            "• 11–20 cảnh: giảm 20%.",
        ]
    if locale == "zh":
        return [
            "• 1 场不减价。",
            "• 2–5 场减 10%。",
            "• 6–10 场减 15%。",
            "• 11–20 场减 20%。",
        ]
    return [f"• {_VIDEO_MULTISCENE_DISCOUNT_COPY[locale]}"]


def chat_pro_token_price_line(lang: str = "vi") -> str:
    labels = opus_price_per_thousand_labels()
    locale = public_copy_locale(lang)
    if locale == "zh":
        return f"• Chat Pro：输入 {labels['input']} Xu / 1K token；输出 {labels['output']} Xu / 1K token。"
    if locale == "en":
        return f"• Chat Pro: {labels['input']} Xu / 1K input tokens; {labels['output']} Xu / 1K output tokens."
    if locale != "vi":
        copy = _public_locale_copy(locale)
        return f"• Chat Pro: {copy['input']} {labels['input']} Xu / 1K token; {copy['output']} {labels['output']} Xu / 1K token."
    return f"• Chat Pro: {labels['input']} Xu / 1K token đầu vào; {labels['output']} Xu / 1K token đầu ra."


def canonical_music_background_prices() -> dict[str, int]:
    """Return standalone Music sale prices from the reviewed canonical catalog."""

    return video_ai_real_pricing.public_music_background_prices()


def default_context() -> dict:
    return {
        "image_price_lines": canonical_image_price_lines(),
        "video_price_lines": canonical_product_video_price_lines(),
        "document_price_lines": [
            "• Ảnh sang PDF: <b>0 Xu</b>.",
            "• PDF sang ảnh: <b>0 Xu</b>.",
            "• PDF sang Word text: <b>0 Xu</b> nếu công cụ đang mở.",
            "• Nén PDF: <b>0 Xu</b>.",
            "• Tách PDF: <b>0 Xu</b>.",
            "• Gộp PDF: <b>0 Xu</b>.",
            "• Các công cụ tài liệu đang thử nghiệm vẫn hiển thị rõ giá trước khi xử lý.",
        ],
        "member_discount_lines": ["• Chiết khấu thành viên: chưa kích hoạt."],
    }


def _context_value(context: dict | None, key: str) -> list[str]:
    data = dict(default_context())
    data.update(context or {})
    return list(data.get(key) or [])


def pricing_total_lines(context: dict | None = None) -> list[str]:
    voice_lines = _context_value(context, "voice_price_lines")
    subtitle_lines = _context_value(context, "subtitle_price_lines")
    video_addon_lines = _context_value(context, "video_addon_price_lines")
    image_lines = _context_value(context, "image_price_lines")
    music_prices = canonical_music_background_prices()
    return [
        "💰 <b>Bảng giá tổng TOAN AAS</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        *(voice_lines[:2] if voice_lines else ["• Giọng nói: từ 0.10 Xu / từ."]),
        chat_pro_token_price_line(),
        f"• Nhạc nền AI: {music_prices['basic']} / {music_prices['standard']} / {music_prices['premium']} Xu.",
        "• Bài hát có lời: 200 / 250 / 300 Xu.",
        "• Video AI: theo gói video đang chọn.",
        *(subtitle_lines if subtitle_lines else [
            "• Tạo phụ đề tự động: miễn phí.",
            "• Dịch phụ đề: 0.1 Xu / ký tự.",
            "• Lồng tiếng giọng mặc định: 0.10 Xu / ký tự.",
        ]),
        *image_lines,
        *(video_addon_lines if video_addon_lines else []),
        "• Tài nguyên tự có của anh/chị: miễn phí nếu hệ thống không cần tạo mới.",
        "",
        "<b>Nhóm giá chính</b>",
        "1. Giọng nói.",
        "2. Nhạc AI.",
        "3. Video.",
        "4. Phụ đề / Lồng tiếng.",
        "5. Hình ảnh.",
        "6. Tài liệu / file nếu công cụ đang mở.",
        "7. Miễn phí / không tính Xu.",
        "8. Chiết khấu / thành viên.",
        "",
        "TOAN AAS sẽ báo giá chi tiết trước khi xử lý.",
    ]


def pricing_voice_lines(context: dict | None = None) -> list[str]:
    voice_lines = _context_value(context, "voice_price_lines")
    return [
        "🎙 <b>Bảng giá Giọng nói</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        "<b>A. Tạo voice riêng</b>",
        *(voice_lines if voice_lines else [
            "• Voice riêng đầu tiên tạo thành công: miễn phí.",
            "• Từ voice riêng thứ 2 trở đi: 50 Xu / voice tạo thành công.",
            "• Tạo audio từ voice: 0.10 Xu / từ.",
        ]),
        "• Chỉ tính Xu khi tạo voice thành công.",
        "• Nếu mẫu lỗi, quá ngắn hoặc không tạo được voice hợp lệ: không trừ Xu.",
        "• Nếu tài khoản vận hành được miễn phí nội bộ, phần hiển thị cho khách vẫn giữ cùng cách báo giá.",
        "",
        "<b>B. Tạo audio từ voice</b>",
        "• Nội dung tối thiểu: 20 từ.",
        "• Tối thiểu thanh toán: 1 Xu.",
        "• Không giới hạn từ nếu hệ thống cho phép.",
        "• Có chỉnh tốc độ 0.1x-2.0x.",
        "• Có chỉnh âm lượng 0%-200%.",
        "• 100% là mức âm lượng đã chốt hiện tại.",
        "• 0% cần xác nhận riêng nếu tạo audio im lặng.",
        "",
        "<b>Ví dụ</b>",
        "• Anh/chị tạo audio 100 từ: 100 × 0.10 = 10 Xu, giảm số lượng 10%, tổng còn 9 Xu.",
        "• Anh/chị nhập 20 từ: 20 × 0.10 = 2 Xu.",
        "• Anh/chị tạo voice riêng lần đầu: 0 Xu.",
        "• Anh/chị tạo voice riêng lần thứ 2: 50 Xu nếu tạo thành công.",
    ]


def pricing_music_lines() -> list[str]:
    music_prices = canonical_music_background_prices()
    return [
        "🎵 <b>Bảng giá Nhạc AI</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        "<b>A. Nhạc nền / không lời</b>",
        f"• Cơ bản: {music_prices['basic']} Xu.",
        f"• Tiêu chuẩn: {music_prices['standard']} Xu.",
        f"• Cao cấp: {music_prices['premium']} Xu.",
        "",
        "<b>B. Bài hát có lời</b>",
        "• Cơ bản: 200 Xu.",
        "• Tiêu chuẩn: 250 Xu.",
        "• Cao cấp: 300 Xu.",
        "",
        "Nhạc nền dùng cho video quảng cáo, intro, nền TikTok/Facebook hoặc nội dung giới thiệu sản phẩm. Mặc định không có giọng hát.",
        "Bài hát có lời dùng để tạo bài hát có giọng hát, có thể chọn giọng nam, giọng nữ, song ca hoặc tự động. TOAN AAS sẽ tạo 3 gợi ý để anh/chị chọn trước khi tạo nhạc.",
        "• Mỗi yêu cầu tạo nhạc AI trả về 2 bản để anh/chị chọn.",
        "",
        "<b>Cách tính</b>",
        "• Tính theo mỗi lần tạo file nhạc thành công.",
        "• Không trừ Xu trước khi xác nhận.",
        "• Không trừ Xu nếu hệ thống không tạo được file nhạc hợp lệ.",
        "• Nếu tài khoản vận hành được miễn phí nội bộ, phần hiển thị cho khách vẫn giữ cùng cách báo giá.",
        "",
        "<b>Ví dụ</b>",
        "• Nhạc nền Tiêu chuẩn: tổng thanh toán 150 Xu.",
        "• Bài hát có lời Cao cấp, giọng nữ: tổng thanh toán 300 Xu.",
        "• Bấm Đổi gợi ý: không trừ Xu, chỉ tạo gợi ý mới.",
    ]


def pricing_video_lines(context: dict | None = None) -> list[str]:
    return [
        "🎬 <b>Bảng giá Video</b>",
        "",
        "Giá dưới đây tính cho từng cảnh theo đúng gói chất lượng đã chọn.",
        CONFIRM_GATE_COPY,
        "",
        *_context_value(context, "video_price_lines"),
        "",
        "<b>Khuyến mãi Video nhiều cảnh</b>",
        "Khuyến mãi chỉ áp dụng khi tạo từ 2 cảnh trong cùng một đơn Video nhiều cảnh.",
        *video_multiscene_discount_lines(),
        "• Phần giảm chỉ tính trên chi phí tạo video theo cảnh; add-on được cộng riêng theo lựa chọn.",
        "",
        "<b>Miễn phí trong video khi dùng tài nguyên có sẵn</b>",
        "• Watermark/logo chữ có sẵn nếu không tạo mới: miễn phí.",
        "• Dùng ảnh của khách: miễn phí phần tài nguyên ảnh.",
        "• Dùng nhạc của khách: miễn phí phần tài nguyên nhạc.",
        "• Dùng voice/audio có sẵn của khách: miễn phí phần tài nguyên có sẵn.",
        "• Tạo phụ đề gốc tự động từ voice/lời đọc có sẵn trong quy trình video: miễn phí nếu chỉ tạo phụ đề gốc.",
        "• Logo tự tạo bằng công cụ ảnh riêng: tính theo bảng giá Hình ảnh, không tính trong video nếu khách tự đưa tài nguyên.",
        "",
        "<b>Ví dụ</b>",
        "• Nhanh gọn 1 cảnh: 200 Xu; không áp dụng giảm giá nhiều cảnh.",
        "• Nhanh gọn 3 cảnh: 200 × 3 = 600 Xu; giảm 10% là 60 Xu; tiền video còn 540 Xu.",
        "• Nếu anh/chị chọn tạo ảnh/logo AI riêng bên ngoài, phần ảnh sẽ tính theo bảng giá Hình ảnh.",
    ]


def pricing_subtitle_lines(context: dict | None = None) -> list[str]:
    subtitle_lines = _context_value(context, "subtitle_price_lines")
    return [
        "🌐 <b>Bảng giá Phụ đề / Lồng tiếng</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        *(subtitle_lines if subtitle_lines else []),
        "" if subtitle_lines else "",
        "<b>A. Tạo phụ đề tự động</b>",
        "• Miễn phí nếu chỉ tạo phụ đề gốc trong luồng hiện tại." if subtitle_lines else "• Miễn phí.",
        "• Chỉ tạo phụ đề gốc từ video/audio/lời đọc.",
        "• Không dịch, không lồng tiếng nếu chưa chọn thêm tác vụ.",
        "",
        "<b>B. Dịch phụ đề</b>",
        "• Theo bảng giá trung tâm ở trên." if subtitle_lines else "• 0.1 Xu / ký tự.",
        "• Trên 1.000 ký tự: giảm 10%.",
        "• Trên 10.000 ký tự: giảm 20%.",
        "• Hệ thống hiển thị rõ số ký tự tính phí trước khi xử lý.",
        "",
        "<b>C. Lồng tiếng giọng mặc định</b>",
        "• Theo bảng giá trung tâm ở trên." if subtitle_lines else "• 0.10 Xu / ký tự.",
        "• Trên 1.000 ký tự: giảm 10%.",
        "• Trên 10.000 ký tự: giảm 20%.",
        "",
        "<b>D. Lồng tiếng voice riêng</b>",
        "• Theo bảng giá Giọng nói/Voice riêng ở bảng trung tâm.",
        "• Trên 1.000 ký tự: giảm 10%.",
        "• Trên 10.000 ký tự: giảm 20%.",
        "",
        "<b>E. Phụ đề + Lồng tiếng</b>",
        "Tổng = giá dịch phụ đề + giá lồng tiếng. Tạo phụ đề rồi lồng tiếng = giá phụ đề tự động + giá lồng tiếng.",
        "",
        "<b>Ví dụ</b>",
        "• Mỗi bước dịch/lồng tiếng hiển thị báo giá hiện hành trước khi xử lý.",
        "• Phụ đề + lồng tiếng: tổng luôn cộng từ hai dòng giá đang hiển thị ở bảng trung tâm.",
    ]


def pricing_image_lines(context: dict | None = None) -> list[str]:
    return [
        "🖼 <b>Bảng giá Hình ảnh</b>",
        "",
        CONFIRM_GATE_COPY,
        "",
        *_context_value(context, "image_price_lines"),
        "",
        "<b>Chọn chất lượng</b>",
        "• Bảng trên là các mức public hiện hành; mô tả từng mức xuất hiện ngay khi chọn.",
        "• Nếu hệ thống không tạo được ảnh hợp lệ: không trừ Xu.",
        "",
        "<b>Ví dụ</b>",
        "TOAN AAS hiển thị hóa đơn theo mức ảnh đã chọn trước khi xử lý. Nếu ảnh không tạo được hợp lệ, hệ thống không trừ Xu.",
    ]


def pricing_docs_lines(context: dict | None = None) -> list[str]:
    return [
        "📄 <b>Bảng giá Tài liệu / File</b>",
        "",
        *_context_value(context, "document_price_lines"),
        "",
        "TOAN AAS vẫn hiển thị rõ trước khi xử lý nếu một công cụ tài liệu có phí trong tương lai.",
    ]


def pricing_free_lines() -> list[str]:
    return [
        "🎁 <b>Những phần miễn phí</b>",
        "",
        "• Xem demo voice: miễn phí.",
        "• Đổi gợi ý nhạc: miễn phí.",
        "• Tạo gợi ý bài hát/nhạc: miễn phí.",
        "• Tạo phụ đề gốc tự động: miễn phí.",
        "• Dùng ảnh do anh/chị gửi lên: không tính phí tạo ảnh.",
        "• Dùng nhạc do anh/chị gửi lên: không tính phí tạo nhạc.",
        "• Dùng voice/audio có sẵn của anh/chị: không tính phí tạo voice mới.",
        "• Watermark/logo chữ có sẵn trong video: miễn phí nếu không tạo ảnh/logo mới.",
        "• Xem hóa đơn/tính thử giá: miễn phí.",
        "• Hủy trước xác nhận: không trừ Xu.",
        "",
        "Nếu anh/chị yêu cầu TOAN AAS tạo mới ảnh, voice, nhạc, phụ đề dịch, lồng tiếng hoặc video thì phần tạo mới sẽ tính theo bảng giá tương ứng.",
    ]


def pricing_member_lines(context: dict | None = None) -> list[str]:
    return [
        "🎁 <b>Khuyến mãi & Thành viên</b>",
        "",
        "<b>Chiết khấu thành viên hiện tại</b>",
        *_context_value(context, "member_discount_lines"),
        "",
        "<b>Cách cộng dồn</b>",
        "1. Tính giá gốc theo sản phẩm.",
        "2. Áp dụng chiết khấu theo số lượng/ký tự nếu có.",
        "3. Áp dụng chiết khấu thành viên trên số còn lại.",
        "4. Áp dụng voucher/khuyến mãi nếu hệ thống có, theo chính sách hiện có.",
        "5. Làm tròn theo đơn vị Xu hiện tại của ví.",
        "6. Hiển thị tổng cuối trước xác nhận.",
        "",
        "<b>Ví dụ có thành viên giảm 10%</b>",
        "Ví dụ hiển thị: tổng sau giảm theo số lượng và hạng thành viên luôn được báo rõ trước khi xác nhận.",
        "",
        "<b>Ví dụ không có thành viên</b>",
        "Tổng thanh toán sau giảm số lượng luôn hiển thị trước khi xác nhận.",
        "",
        "Khuyến mãi nạp tiền chỉ áp dụng cho PayOS hoặc chuyển khoản ngân hàng Việt Nam theo điều kiện từng chương trình.",
        "Khách quốc tế chỉ nhận Xu gốc đã xác minh; không áp dụng bonus, mã nạp, referral Xu hoặc Xu điều chỉnh vượt mức qua duyệt nạp.",
        "Chiết khấu dịch vụ theo hạng thành viên và quyền lợi không liên quan nạp tiền vẫn áp dụng khi đủ điều kiện.",
    ]


def _localized_international_pricing_lines(
    section: str,
    *,
    locale: str,
    image_lines: list[str],
    video_lines: list[str],
    music_prices: dict[str, int],
) -> list[str]:
    """Render compact native-language public copy for added international locales."""

    copy = _public_locale_copy(locale)
    common = copy["quote"]
    music_line = f"• {copy['music']}: {music_prices['basic']} / {music_prices['standard']} / {music_prices['premium']} Xu."
    song_line = "• 200 / 250 / 300 Xu."
    video_discounts = video_multiscene_discount_lines(locale)
    topup_policy = international_topup_policy_lines(locale)
    mapping = {
        "total": [
            f"💰 <b>{copy['pricing']}</b>", "", common, "", chat_pro_token_price_line(locale),
            f"<b>{copy['images']}</b>", *image_lines,
            "", f"<b>{copy['video']}</b>", *video_lines, *video_discounts,
            "", music_line, song_line,
            f"• {copy['voice']}: 0 Xu / 50 Xu.",
            f"• {copy['subtitles']}: {common}",
            f"• {copy['member']}: {common}",
            *topup_policy,
        ],
        "voice": [f"🎙 <b>{copy['voice']}</b>", "", common, "", "• 0 Xu / 50 Xu."],
        "music": [f"🎵 <b>{copy['music']}</b>", "", common, "", music_line, song_line],
        "video": [f"🎬 <b>{copy['video']}</b>", "", common, "", *video_lines, *video_discounts],
        "subtitle": [f"🌐 <b>{copy['subtitles']}</b>", "", common],
        "subtitle_dub": [f"🌐 <b>{copy['subtitles']}</b>", "", common],
        "image": [f"🖼 <b>{copy['images']}</b>", "", common, "", *image_lines],
        "docs": [f"📄 <b>{copy['documents']}</b>", "", common],
        "free": [f"🎁 <b>{copy['free']}</b>", "", common],
        "member": [f"👑 <b>{copy['member']}</b>", "", common, "", *topup_policy],
    }
    return mapping.get((section or "total").strip().lower(), mapping["total"])


def _international_pricing_lines(section: str, context: dict | None, lang: str) -> list[str]:
    """Render public non-Vietnamese copy without changing any pricing owner."""

    locale = public_copy_locale(lang)
    chinese = locale == "zh"
    image_lines = canonical_image_price_lines(locale)
    video_lines = canonical_product_video_price_lines(locale)
    video_discounts = video_multiscene_discount_lines(locale)
    music_prices = canonical_music_background_prices()
    chat_line = chat_pro_token_price_line(locale)
    topup_policy = international_topup_policy_lines(locale)
    if locale not in {"en", "zh"}:
        return _localized_international_pricing_lines(
            section,
            locale=locale,
            image_lines=image_lines,
            video_lines=video_lines,
            music_prices=music_prices,
        )
    if chinese:
        common = "系统会在处理前显示报价；只有在确认且获得有效结果后才会扣除 Xu。"
        mapping = {
            "total": [
                "💰 <b>TOAN AAS 价格</b>", "", common, "", chat_line,
                "<b>AI 图片</b>", *image_lines, "", "<b>Product Video</b>", *video_lines, *video_discounts,
                "", f"• AI 音乐：配乐基础 {music_prices['basic']} / 标准 {music_prices['standard']} / 高级 {music_prices['premium']} Xu；有歌词歌曲 200 / 250 / 300 Xu。",
                "• 语音、字幕和配音将按所选服务在确认前显示当前报价。",
                "• 符合资格的会员服务折扣仍然适用；国际账户按确认前显示的价格收费。",
                *topup_policy,
            ],
            "voice": [
                "🎙 <b>语音价格</b>", "", common, "",
                "• 首次成功创建专属语音：0 Xu。",
                "• 后续每个成功创建的专属语音：50 Xu。",
                "• 文字转语音：0.10 Xu / 词，最低 1 Xu。",
            ],
            "music": [
                "🎵 <b>AI 音乐</b>", "", common, "",
                f"• 配乐：基础 {music_prices['basic']} Xu；标准 {music_prices['standard']} Xu；高级 {music_prices['premium']} Xu。",
                "• 有歌词歌曲：基础 200 Xu；标准 250 Xu；高级 300 Xu。",
                "• 若无法生成有效音乐文件，不扣除 Xu。",
            ],
            "video": [
                "🎬 <b>Product Video 价格</b>", "", common, "", *video_lines, *video_discounts,
                "", "• 每个档位按已公布时长和场景数计算；确认页显示总 Xu。",
                "• 客户自带图片、音乐、语音或文字 logo 不收取创建资源费用。",
            ],
            "subtitle": [
                "🌐 <b>字幕 / 翻译 / 配音</b>", "", common, "",
                "• 原始字幕在当前支持的流程中免费。",
                "• 翻译和配音会在确认前显示当前报价。",
            ],
            "image": [
                "🖼 <b>AI 图片价格</b>", "", common, "", *image_lines,
                "", "• 若无法生成有效图片，不扣除 Xu。",
            ],
            "docs": [
                "📄 <b>文档 / 文件</b>", "",
                "• 当前可用的文件工具会在处理前显示价格；免费工具显示 0 Xu。",
            ],
            "free": [
                "🎁 <b>免费项目</b>", "",
                "• 查看价格、指南、演示和取消确认前的操作均免费。",
                "• 使用客户已有的图片、音乐或语音不收取创建该资源的费用。",
            ],
            "member": [
                "👑 <b>会员与优惠</b>", "",
                "• 会员权益和服务折扣按当前账户资格保留。",
                "• 月度套餐和组合包不会转换为自由 Xu，也不计入会员充值进度。",
                "• 国际账户按确认页显示的服务价格收费。",
                *topup_policy,
            ],
        }
    else:
        common = "TOAN AAS shows the quote before processing and only charges Xu after confirmation and a valid result."
        mapping = {
            "total": [
                "💰 <b>TOAN AAS Pricing</b>", "", common, "", chat_line,
                "<b>AI Images</b>", *image_lines, "", "<b>Product Video</b>", *video_lines, *video_discounts,
                "", f"• AI music: background {music_prices['basic']} / {music_prices['standard']} / {music_prices['premium']} Xu; songs with vocals 200 / 250 / 300 Xu.",
                "• Voice, subtitles and dubbing show their current quote for the selected service before confirmation.",
                "• Member service discounts remain available when eligible. International accounts are charged at the price shown before confirmation.",
                *topup_policy,
            ],
            "voice": [
                "🎙 <b>Voice Pricing</b>", "", common, "",
                "• First successful custom voice: 0 Xu.",
                "• Each later successful custom voice: 50 Xu.",
                "• Text-to-speech: 0.10 Xu / word, minimum 1 Xu.",
            ],
            "music": [
                "🎵 <b>AI Music</b>", "", common, "",
                f"• Background music: Basic {music_prices['basic']} Xu; Standard {music_prices['standard']} Xu; Premium {music_prices['premium']} Xu.",
                "• Songs with vocals: Basic 200 Xu; Standard 250 Xu; Premium 300 Xu.",
                "• If no valid music file can be generated, no Xu is charged.",
            ],
            "video": [
                "🎬 <b>Product Video Pricing</b>", "", common, "", *video_lines, *video_discounts,
                "", "• Each tier uses its published duration and scene count; the confirmation screen shows total Xu.",
                "• Customer-supplied images, music, voice, or text logo do not incur a resource-creation charge.",
            ],
            "subtitle": [
                "🌐 <b>Subtitles / Translation / Dubbing</b>", "", common, "",
                "• Original subtitles are free in supported current flows.",
                "• Translation and dubbing show their current quote before confirmation.",
            ],
            "image": [
                "🖼 <b>AI Image Pricing</b>", "", common, "", *image_lines,
                "", "• If no valid image can be generated, no Xu is charged.",
            ],
            "docs": [
                "📄 <b>Documents / Files</b>", "",
                "• Available document tools show their price before processing; free tools show 0 Xu.",
            ],
            "free": [
                "🎁 <b>Free Items</b>", "",
                "• Viewing pricing, guides, demos, and cancelling before confirmation are free.",
                "• Using customer-supplied images, music, or voice does not charge for creating that resource.",
            ],
            "member": [
                "👑 <b>Membership and Benefits</b>", "",
                "• Eligible membership benefits and service discounts remain available.",
                "• Monthly plans and combos are not convertible to flexible Xu and do not count toward member top-up progress.",
                "• International accounts use the service price shown on the confirmation screen.",
                *topup_policy,
            ],
        }
    return mapping.get((section or "total").strip().lower(), mapping["total"])


def pricing_lines(section: str = "total", context: dict | None = None, lang: str = "vi") -> list[str]:
    if public_copy_locale(lang) != "vi":
        return _international_pricing_lines(section, context, lang)
    key = (section or "total").strip().lower()
    mapping = {
        "catalog": pricing_total_lines,
        "main": pricing_total_lines,
        "total": pricing_total_lines,
        "voice": pricing_voice_lines,
        "music": lambda _context=None: pricing_music_lines(),
        "video": pricing_video_lines,
        "subtitle": pricing_subtitle_lines,
        "subtitle_dub": pricing_subtitle_lines,
        "image": pricing_image_lines,
        "docs": pricing_docs_lines,
        "free": lambda _context=None: pricing_free_lines(),
        "member": pricing_member_lines,
    }
    renderer = mapping.get(key, pricing_total_lines)
    return renderer(context)


def all_pricing_lines(context: dict | None = None, lang: str = "vi") -> list[str]:
    lines: list[str] = []
    for key in ("total", "voice", "music", "video", "subtitle", "image", "docs", "free", "member"):
        if lines:
            lines.extend(["", "-----", ""])
        lines.extend(pricing_lines(key, context, lang))
    return lines


def customer_guide_sections() -> list[tuple[str, str, str]]:
    music_prices = canonical_music_background_prices()
    return [
        (
            "quick_start",
            "Bắt đầu nhanh",
            "\n".join([
                "🚀 <b>BẮT ĐẦU NHANH</b>",
                "",
                "1. Chọn tính năng muốn dùng: Tạo ảnh, Tạo video, Studio âm thanh, Phụ đề / Dịch / Lồng tiếng hoặc Tài liệu.",
                "2. Gửi mô tả rõ mục tiêu, sản phẩm, phong cách, nền tảng đăng và yêu cầu riêng.",
                "3. Chọn gói phù hợp nếu tính năng có nhiều mức giá.",
                "4. Kiểm tra bản xem trước, bảng giá và thông tin xác nhận.",
                "5. Chỉ khi anh/chị xác nhận, hệ thống mới xử lý và mới trừ Xu nếu bước đó có phí.",
                "6. Nhận kết quả trong bot, tải về hoặc tiếp tục bước kế tiếp.",
                "",
                CONFIRM_GATE_COPY,
                "",
                "Ví dụ: muốn tạo video bán hàng, anh/chị có thể tạo ảnh sản phẩm trước, sau đó dùng ảnh đó để tạo video.",
            ]),
        ),
        (
            "voice_custom",
            "Tạo voice riêng",
            "\n".join([
                "🎙 <b>HƯỚNG DẪN TẠO VOICE RIÊNG</b>",
                "",
                "Dùng khi: anh/chị muốn có giọng riêng đã lưu để dùng cho nội dung sau này.",
                "",
                "Cách làm:",
                "1. Vào Studio âm thanh.",
                "2. Chọn tạo voice riêng.",
                "3. Gửi mẫu giọng rõ, đủ dài và ít tạp âm.",
                "4. Xem điều kiện và hóa đơn nếu đây không phải voice đầu tiên.",
                "5. Xác nhận tạo voice.",
                "",
                "Cách tính: voice riêng đầu tiên tạo thành công miễn phí; từ voice thứ 2 là 50 Xu / voice thành công.",
                "Ví dụ: tạo voice riêng lần đầu = 0 Xu; tạo voice riêng lần thứ 2 = 50 Xu nếu tạo thành công.",
            ]),
        ),
        (
            "voice_audio",
            "Tạo audio từ voice",
            "\n".join([
                "📘 <b>TẠO AUDIO TỪ VOICE</b>",
                "",
                "Dùng khi: anh/chị muốn biến văn bản thành file giọng đọc.",
                "",
                "Cách làm:",
                "1. Vào Studio âm thanh.",
                "2. Chọn Kho voice hoặc giọng mặc định.",
                "3. Bấm Tạo audio.",
                "4. Nhập nội dung từ 20 từ trở lên.",
                "5. Chỉnh tốc độ/âm lượng nếu cần.",
                "6. Xem hóa đơn.",
                "7. Xác nhận tạo audio.",
                "",
                "Cách tính: 0.10 Xu / từ, tối thiểu 1 Xu; từ 100 từ được giảm số lượng 10%.",
                "Ví dụ: 100 từ = 10 Xu, giảm 10%, tổng còn 9 Xu; 20 từ = 2 Xu.",
            ]),
        ),
        (
            "music_background",
            "Tạo nhạc nền AI",
            "\n".join([
                "🎵 <b>HƯỚNG DẪN TẠO NHẠC NỀN AI</b>",
                "",
                "Dùng khi: anh/chị cần nhạc không lời cho video, intro, quảng cáo hoặc nội dung sản phẩm.",
                "",
                "Cách làm:",
                "1. Vào Studio âm thanh.",
                "2. Chọn Nhạc nền AI.",
                "3. Mô tả phong cách, cảm xúc và mục đích sử dụng.",
                "4. Chọn Cơ bản, Tiêu chuẩn hoặc Cao cấp.",
                "5. Xem hóa đơn và xác nhận.",
                "",
                f"Cách tính: Cơ bản {music_prices['basic']} Xu, Tiêu chuẩn {music_prices['standard']} Xu, Cao cấp {music_prices['premium']} Xu.",
                f"Ví dụ: chọn Nhạc nền Tiêu chuẩn = {music_prices['standard']} Xu.",
            ]),
        ),
        (
            "music_song",
            "Tạo bài hát có lời",
            "\n".join([
                "🎤 <b>HƯỚNG DẪN TẠO BÀI HÁT CÓ LỜI</b>",
                "",
                "Dùng khi: anh/chị muốn bài hát ngắn cho thương hiệu, sản phẩm hoặc chiến dịch.",
                "",
                "Cách làm:",
                "1. Vào Studio âm thanh.",
                "2. Chọn Bài hát có lời.",
                "3. Nhập chủ đề, phong cách, cảm xúc và chọn giọng hát.",
                "4. Xem 3 gợi ý.",
                "5. Chọn gợi ý phù hợp, xem hóa đơn và xác nhận.",
                "",
                "Cách tính: Cơ bản 200 Xu, Tiêu chuẩn 250 Xu, Cao cấp 300 Xu.",
                "Ví dụ: bài hát có lời Cao cấp, giọng nữ = 300 Xu.",
                "Đổi gợi ý: không trừ Xu.",
            ]),
        ),
        (
            "audio",
            "Âm thanh",
            "\n".join([
                "🎧 <b>HƯỚNG DẪN ÂM THANH</b>",
                "",
                "Âm thanh giúp video dễ nghe, dễ bán hàng và chuyên nghiệp hơn.",
                "",
                "Bạn có thể dùng:",
                "• Tạo giọng đọc từ nội dung đã viết.",
                "• Tạo voice riêng.",
                "• Tạo nhạc nền theo phong cách mong muốn.",
                "• Tạo bài hát ngắn cho thương hiệu, sản phẩm hoặc chiến dịch.",
                "",
                "Giá cần nhớ:",
                "• Audio từ voice: 0.10 Xu / từ, tối thiểu 1 Xu.",
                "• Voice riêng đầu tiên: 0 Xu; từ voice thứ 2: 50 Xu nếu tạo thành công.",
                f"• Nhạc nền AI: {music_prices['basic']} / {music_prices['standard']} / {music_prices['premium']} Xu.",
                "• Bài hát có lời: 200 / 250 / 300 Xu.",
                "",
                "Ví dụ: audio 100 từ = 9 Xu sau giảm số lượng; nhạc nền Tiêu chuẩn = 150 Xu.",
                MAINTENANCE_NOTICE,
            ]),
        ),
        (
            "video_ai",
            "Tạo video",
            "\n".join([
                "🎬 <b>HƯỚNG DẪN TẠO VIDEO AI</b>",
                "",
                "Dùng khi: anh/chị muốn tạo video từ mô tả, ảnh có sẵn hoặc concept bán hàng.",
                "",
                "Quy trình tạo video:",
                "1. Mở mục <b>Tạo video</b>.",
                "2. Chọn chủ đề hoặc nguồn video và gửi ý tưởng chính.",
                "3. Chọn số cảnh trước để hệ thống phân bổ đúng số ý; hỗ trợ 1-20 cảnh.",
                "4. Chọn profile và ngữ cảnh phù hợp.",
                "5. Bổ sung yêu cầu chi tiết và các add-on ảnh hưởng nội dung, bố cục hoặc lời thoại.",
                "6. Kiểm tra kế hoạch và prompt riêng của từng cảnh.",
                "7. Chọn gói chất lượng video.",
                "8. Xem tổng chi phí, kiểm tra nội dung và xác nhận cuối.",
                "9. Hệ thống tạo, kiểm tra từng cảnh rồi ghép video.",
                "10. Add-on được thực hiện sau khi ghép; video hoàn chỉnh được kiểm tra và gửi về bot.",
                "",
                "Bảng giá video theo gói:",
                *canonical_product_video_price_lines(),
                "",
                "Khuyến mãi Video nhiều cảnh:",
                "Khuyến mãi chỉ áp dụng cho một đơn Video có từ 2 cảnh trở lên; 1 cảnh không giảm.",
                *video_multiscene_discount_lines(),
                "• Add-on được cộng riêng và không nằm trong phần giảm theo số cảnh.",
                "",
                "Ví dụ: Nhanh gọn 3 cảnh = 200 × 3 = 600 Xu; giảm 10% là 60 Xu; tiền video còn 540 Xu.",
            ]),
        ),
        (
            "auto_subtitle",
            "Tạo phụ đề tự động",
            "\n".join([
                "📝 <b>HƯỚNG DẪN TẠO PHỤ ĐỀ TỰ ĐỘNG</b>",
                "",
                "Dùng khi: anh/chị cần phụ đề gốc từ video/audio/lời đọc.",
                "Cách làm: mở Phụ đề / Dịch / Lồng tiếng, gửi video hoặc audio, chọn tạo phụ đề gốc, nhận kết quả để kiểm tra.",
                "Cách tính: miễn phí nếu chỉ tạo phụ đề gốc.",
                "Ví dụ: tạo phụ đề gốc cho video rõ tiếng = 0 Xu.",
            ]),
        ),
        (
            "translate_subtitle",
            "Dịch phụ đề",
            "\n".join([
                "🌐 <b>HƯỚNG DẪN DỊCH PHỤ ĐỀ</b>",
                "",
                "Dùng khi: anh/chị muốn chuyển phụ đề sang ngôn ngữ khác.",
                "Cách làm: gửi video/audio hoặc phụ đề, chọn ngôn ngữ đích, xem số ký tự tính phí, xem hóa đơn và xác nhận.",
                "Cách tính: báo giá được hiển thị theo dịch vụ, nội dung và điều kiện đang áp dụng trước khi xác nhận.",
                "Ví dụ: gửi phụ đề, xem báo giá hiện hành, rồi xác nhận nếu phù hợp.",
            ]),
        ),
        (
            "dub",
            "Lồng tiếng",
            "\n".join([
                "🎙 <b>HƯỚNG DẪN LỒNG TIẾNG</b>",
                "",
                "Dùng khi: anh/chị muốn tạo bản giọng đọc mới cho nội dung.",
                "Cách làm: gửi nội dung hoặc video, chọn giọng mặc định hoặc voice riêng, xem hóa đơn và xác nhận.",
                "Cách tính: báo giá được hiển thị theo lựa chọn giọng, nội dung và điều kiện đang áp dụng trước khi xác nhận.",
                "Ví dụ: chọn giọng, xem báo giá hiện hành, rồi xác nhận nếu phù hợp.",
            ]),
        ),
        (
            "subtitle_dub",
            "Phụ đề / Dịch / Lồng tiếng",
            "\n".join([
                "📝 <b>HƯỚNG DẪN PHỤ ĐỀ / DỊCH / LỒNG TIẾNG</b>",
                "",
                "Bạn có thể dùng:",
                "• Tạo phụ đề từ video hoặc audio.",
                "• Dịch nội dung sang ngôn ngữ khác.",
                "• Lồng tiếng lại video bằng giọng phù hợp.",
                "• Tạo phụ đề + lồng tiếng trong cùng quy trình.",
                "",
                "Giá cần nhớ:",
                "• Tạo phụ đề gốc tự động: miễn phí.",
                "• Dịch phụ đề: báo giá hiển thị trước khi xử lý.",
                "• Lồng tiếng giọng mặc định: báo giá hiển thị trước khi xử lý.",
                "• Lồng tiếng voice riêng: báo giá hiển thị trước khi xử lý.",
                "",
                "Ví dụ phụ đề + lồng tiếng: tổng là báo giá của các bước đã chọn và luôn hiển thị trước khi xác nhận.",
                MAINTENANCE_NOTICE,
            ]),
        ),
        (
            "image_ai",
            "Tạo/chỉnh ảnh",
            "\n".join([
                "🖼 <b>HƯỚNG DẪN TẠO/CHỈNH ẢNH</b>",
                "",
                "Dùng khi: anh/chị cần ảnh sản phẩm, ảnh quảng cáo, ảnh minh họa, ảnh dùng làm khung cho video.",
                "",
                "Cách làm:",
                "1. Mở mục Tạo ảnh.",
                "2. Gửi mô tả ảnh: sản phẩm, bối cảnh, ánh sáng, màu sắc, bố cục, tỉ lệ và phong cách.",
                "3. Chọn gói ảnh theo nhu cầu.",
                "4. Xem hóa đơn và xác nhận.",
                "5. Nhận ảnh trong bot, tải về hoặc dùng tiếp để tạo video.",
                "",
                "Bảng giá tạo ảnh:",
                *canonical_image_price_lines(),
                "",
                "Ví dụ: chọn mức ảnh hiện hành để tạo ảnh sản phẩm. Nếu ảnh không tạo được hợp lệ, hệ thống không trừ Xu.",
            ]),
        ),
        (
            "own_resources",
            "Dùng tài nguyên tự có",
            "\n".join([
                "🎁 <b>HƯỚNG DẪN DÙNG TÀI NGUYÊN TỰ CÓ</b>",
                "",
                "Dùng khi: anh/chị đã có ảnh, nhạc, voice/audio, logo hoặc nội dung riêng.",
                "",
                "Cách làm:",
                "1. Gửi tài nguyên vào đúng bước hệ thống yêu cầu.",
                "2. Chọn dùng tài nguyên đã gửi.",
                "3. Xem hóa đơn nếu có phần xử lý mới.",
                "4. Xác nhận trước khi xử lý.",
                "",
                "Cách tính: tài nguyên tự có không tính phí tạo mới. Nếu yêu cầu TOAN AAS tạo mới ảnh, nhạc, voice, phụ đề dịch, lồng tiếng hoặc video thì phần tạo mới tính theo bảng giá tương ứng.",
                "Ví dụ: dùng ảnh do anh/chị gửi lên trong video không tính phí tạo ảnh.",
            ]),
        ),
        (
            "credits",
            "Nạp Xu và xem hóa đơn",
            "\n".join([
                "💰 <b>HƯỚNG DẪN XU, HÓA ĐƠN VÀ BẢNG GIÁ</b>",
                "",
                "Quy đổi: 1 Xu = 100đ. Ví dụ 1.000 Xu tương đương 100.000đ giá trị sử dụng nội bộ trong TOAN AAS.",
                "",
                "Cách nạp Xu:",
                "1. Gõ /naptien.",
                "2. Chọn mệnh giá.",
                "3. Thanh toán theo hướng dẫn trong bot.",
                "4. Gõ /profile để kiểm tra số dư.",
                "",
                "Cách xem hóa đơn:",
                "1. Chọn công cụ cần dùng.",
                "2. Nhập nội dung hoặc chọn gói.",
                "3. Xem tổng Xu, chiết khấu nếu có và nút xác nhận.",
                "4. Chỉ xác nhận khi nội dung và giá đã đúng.",
                "",
                "Khuyến mãi nạp tiền chỉ áp dụng cho PayOS hoặc chuyển khoản ngân hàng Việt Nam nếu chương trình đang mở.",
                "Không áp dụng cho Zalo/MoMo hoặc kênh nạp quốc tế.",
                "Khách quốc tế chỉ nhận Xu gốc đã xác minh; không dùng duyệt nạp quốc tế để cộng bonus, mã nạp, referral Xu hoặc Xu điều chỉnh vượt mức.",
                "Chiết khấu dịch vụ theo hạng thành viên và quyền lợi không liên quan nạp tiền vẫn áp dụng khi đủ điều kiện.",
            ]),
        ),
        (
            "faq",
            "FAQ / Hoàn Xu",
            "\n".join([
                "❓ <b>FAQ / HOÀN XU</b>",
                "",
                "1. Mở menu có bị trừ Xu không? Không.",
                "2. Khi nào TOAN AAS trừ Xu? Sau khi anh/chị xem hóa đơn và xác nhận bước có phí.",
                "3. Khi nào được hoàn Xu? Nếu đã trừ Xu nhưng lỗi trước khi có kết quả hợp lệ theo chính sách.",
                "4. Thiếu Xu thì sao? Bot sẽ báo thiếu Xu và hướng dẫn nạp thêm.",
                "5. Có nên bấm tạo nhiều lần khi đang chờ không? Không nên; hãy chờ kết quả hoặc liên hệ hỗ trợ.",
                "6. Cần hỗ trợ thì gửi gì? Gửi ID Telegram, ảnh chụp màn hình, thời gian giao dịch hoặc nội dung yêu cầu gần nhất.",
            ]),
        ),
    ]


_INTERNATIONAL_TOPUP_GUIDE_COPY: dict[str, tuple[str, tuple[str, ...]]] = {
    "en": (
        "International Xu Top-up",
        (
            "International top-ups receive only verified base Xu.",
            "Vietnam domestic bonuses, extra Xu and top-up codes do not apply.",
            "USD top-up: USDT TRC20 only. Eligible membership service discounts remain.",
        ),
    ),
    "zh": (
        "国际 Xu 充值",
        (
            "国际充值只获得经核验的基础 Xu。",
            "不适用越南国内充值赠 Xu、加赠或充值码。",
            "CNY 充值可使用 ZaloPay/manual 或 Binance / USDT TRC20。符合条件的会员服务折扣仍然适用。",
        ),
    ),
    "es": (
        "Recarga internacional de Xu",
        (
            "Las recargas internacionales solo reciben Xu base verificados.",
            "No se aplican bonificaciones, Xu extra ni códigos de recarga nacionales de Vietnam.",
            "Los canales disponibles y los Xu base verificados se muestran antes de confirmar. Se mantienen los descuentos de servicio de membresía elegibles.",
        ),
    ),
    "pt": (
        "Recarga internacional de Xu",
        (
            "As recargas internacionais recebem apenas Xu base verificados.",
            "Bônus, Xu extra e códigos de recarga domésticos do Vietnã não se aplicam.",
            "Os canais disponíveis e os Xu base verificados são mostrados antes da confirmação. Os descontos elegíveis de serviço para membros permanecem.",
        ),
    ),
    "fr": (
        "Recharge Xu internationale",
        (
            "Les recharges internationales ne reçoivent que des Xu de base vérifiés.",
            "Les bonus, Xu supplémentaires et codes de recharge nationaux du Vietnam ne s'appliquent pas.",
            "Les canaux disponibles et les Xu de base vérifiés sont affichés avant confirmation. Les réductions de service membre éligibles restent disponibles.",
        ),
    ),
    "de": (
        "Internationale Xu-Aufladung",
        (
            "Internationale Aufladungen erhalten nur verifizierte Basis-Xu.",
            "Vietnamesische Inlandsboni, zusätzliche Xu und Aufladecodes gelten nicht.",
            "Verfügbare Kanäle und verifizierte Basis-Xu werden vor der Bestätigung angezeigt. Berechtigte Mitglieds-Service-Rabatte bleiben erhalten.",
        ),
    ),
    "ja": (
        "国際 Xu チャージ",
        (
            "国際チャージで受け取れるのは確認済みの基本 Xu のみです。",
            "ベトナム国内向けのボーナス、追加 Xu、チャージコードは適用されません。",
            "利用可能なチャネルと確認済み基本 Xu は確定前に表示されます。対象の会員サービス割引は引き続き利用できます。",
        ),
    ),
    "ko": (
        "국제 Xu 충전",
        (
            "국제 충전은 확인된 기본 Xu만 받습니다.",
            "베트남 국내 보너스, 추가 Xu 및 충전 코드는 적용되지 않습니다.",
            "사용 가능한 채널과 확인된 기본 Xu는 확정 전에 표시됩니다. 적용 대상 회원 서비스 할인은 유지됩니다.",
        ),
    ),
    "hi": (
        "अंतरराष्ट्रीय Xu टॉप-अप",
        (
            "अंतरराष्ट्रीय टॉप-अप पर केवल सत्यापित मूल Xu मिलते हैं।",
            "वियतनाम के घरेलू बोनस, अतिरिक्त Xu और टॉप-अप कोड लागू नहीं होते।",
            "उपलब्ध चैनल और सत्यापित मूल Xu पुष्टि से पहले दिखाए जाते हैं। पात्र सदस्य सेवा छूट बनी रहती है।",
        ),
    ),
    "ar": (
        "شحن Xu الدولي",
        (
            "الشحن الدولي يمنح فقط Xu الأساسي الذي تم التحقق منه.",
            "لا تنطبق مكافآت فيتنام المحلية أو Xu الإضافي أو رموز الشحن.",
            "تظهر القنوات المتاحة وXu الأساسي المتحقق منه قبل التأكيد. تبقى خصومات خدمة العضوية المؤهلة متاحة.",
        ),
    ),
    "ru": (
        "Международное пополнение Xu",
        (
            "Международное пополнение даёт только проверенные базовые Xu.",
            "Вьетнамские внутренние бонусы, дополнительные Xu и коды пополнения не применяются.",
            "Доступные каналы и проверенные базовые Xu показываются до подтверждения. Доступные скидки на услуги для участников сохраняются.",
        ),
    ),
    "tr": (
        "Uluslararası Xu yükleme",
        (
            "Uluslararası yüklemeler yalnızca doğrulanmış temel Xu alır.",
            "Vietnam içi bonuslar, ek Xu ve yükleme kodları uygulanmaz.",
            "Uygun kanallar ve doğrulanmış temel Xu onaydan önce gösterilir. Uygun üyelik hizmet indirimleri korunur.",
        ),
    ),
    "th": (
        "เติม Xu ระหว่างประเทศ",
        (
            "การเติมเงินระหว่างประเทศจะได้รับเฉพาะ Xu พื้นฐานที่ตรวจสอบแล้วเท่านั้น",
            "โบนัสภายในประเทศเวียดนาม Xu เพิ่มเติม และรหัสเติมเงินใช้ไม่ได้",
            "จะแสดงช่องทางที่ใช้ได้และ Xu พื้นฐานที่ตรวจสอบแล้วก่อนยืนยัน ส่วนลดบริการสมาชิกที่เข้าเกณฑ์ยังคงใช้ได้",
        ),
    ),
    "fil": (
        "Internasyonal na Xu top-up",
        (
            "Ang internasyonal na top-up ay tumatanggap lamang ng napatunayang base Xu.",
            "Hindi naaangkop ang mga domestic bonus ng Vietnam, dagdag na Xu, at top-up code.",
            "Ipinapakita ang mga available na channel at napatunayang base Xu bago kumpirmahin. Nanatili ang mga kwalipikadong diskuwento sa serbisyo ng miyembro.",
        ),
    ),
    "it": (
        "Ricarica Xu internazionale",
        (
            "Le ricariche internazionali ricevono solo Xu base verificati.",
            "Non si applicano bonus nazionali vietnamiti, Xu extra o codici di ricarica.",
            "I canali disponibili e gli Xu base verificati vengono mostrati prima della conferma. Restano disponibili gli sconti sui servizi per membri idonei.",
        ),
    ),
    "id": (
        "Isi ulang Xu internasional",
        (
            "Isi ulang internasional hanya menerima Xu dasar yang telah diverifikasi.",
            "Bonus domestik Vietnam, Xu tambahan, dan kode isi ulang tidak berlaku.",
            "Kanal yang tersedia dan Xu dasar terverifikasi ditampilkan sebelum konfirmasi. Diskon layanan anggota yang memenuhi syarat tetap tersedia.",
        ),
    ),
}


def _international_topup_guide_section(lang: str) -> tuple[str, str, str]:
    locale = public_copy_locale(lang)
    title, lines = _INTERNATIONAL_TOPUP_GUIDE_COPY[locale]
    return "credits", title, "\n".join([f"💳 <b>{title}</b>", "", *lines])


def international_topup_policy_lines(lang: str) -> list[str]:
    """Return public base-Xu-only policy copy for the selected international locale."""

    locale = public_copy_locale(lang)
    return list(_INTERNATIONAL_TOPUP_GUIDE_COPY[locale][1])


def _localized_international_guide_sections(lang: str) -> list[tuple[str, str, str]]:
    """Keep added locales on the same public price source without English fallback."""

    locale = public_copy_locale(lang)
    copy = _public_locale_copy(locale)
    image_lines = canonical_image_price_lines(locale)
    video_lines = canonical_product_video_price_lines(locale)
    video_discounts = video_multiscene_discount_lines(locale)
    music_prices = canonical_music_background_prices()
    music_line = f"{copy['music']}: {music_prices['basic']} / {music_prices['standard']} / {music_prices['premium']} Xu."
    return [
        ("quick_start", copy["guide"], "\n".join([f"📚 <b>{copy['guide']}</b>", "", copy["quote"]])),
        ("image_ai", copy["images"], "\n".join([f"🖼 <b>{copy['images']}</b>", "", copy["quote"], "", *image_lines])),
        ("video_ai", copy["video"], "\n".join([f"🎬 <b>{copy['video']}</b>", "", copy["quote"], "", *video_lines, *video_discounts])),
        ("audio", f"{copy['voice']} / {copy['music']}", "\n".join([f"🎧 <b>{copy['voice']} / {copy['music']}</b>", "", copy["quote"], "", music_line, "200 / 250 / 300 Xu."])),
        ("subtitle_dub", copy["subtitles"], "\n".join([f"🌐 <b>{copy['subtitles']}</b>", "", copy["quote"]])),
        _international_topup_guide_section(locale),
        ("packages", copy["member"], "\n".join([f"👑 <b>{copy['member']}</b>", "", copy["quote"]])),
        ("faq", copy["free"], "\n".join([f"❓ <b>{copy['free']}</b>", "", copy["quote"]])),
    ]


def _international_guide_sections(lang: str = "en") -> list[tuple[str, str, str]]:
    locale = public_copy_locale(lang)
    image_lines = canonical_image_price_lines(locale)
    video_lines = canonical_product_video_price_lines(locale)
    video_discounts = video_multiscene_discount_lines(locale)
    music_prices = canonical_music_background_prices()
    if locale not in {"en", "zh"}:
        return _localized_international_guide_sections(locale)
    if locale == "zh":
        return [
            (
                "quick_start",
                "快速开始",
                "\n".join([
                    "🚀 <b>TOAN AAS 快速开始</b>", "",
                    "1. 选择图片、Product Video、音频、字幕/翻译/配音或文档工具。",
                    "2. 清楚说明目标、素材、风格和用途。",
                    "3. 在任何付费处理前检查报价并确认。",
                    "4. 只有确认且获得有效结果后才会扣除 Xu。",
                ]),
            ),
            (
                "image_ai",
                "AI 图片",
                "\n".join([
                    "🖼 <b>AI 图片</b>", "",
                    "提交图片描述，选择质量档位，确认报价后再创建。", "",
                    "当前公开图片档位：", *image_lines,
                    "", "若无法生成有效图片，不扣除 Xu。",
                ]),
            ),
            (
                "video_ai",
                "Product Video",
                "\n".join([
                    "🎬 <b>Product Video</b>", "",
                    "先选择场景数量和质量档位，确认页会显示每场价格与总 Xu。", "",
                    "当前公开 Product Video 档位：", *video_lines,
                    *video_discounts,
                    "", "每个档位按公布时长和场景数计算。",
                ]),
            ),
            (
                "audio",
                "语音与音乐",
                "\n".join([
                    "🎧 <b>语音与音乐</b>", "",
                "首次成功创建专属语音为 0 Xu；后续每个成功创建为 50 Xu。",
                "文字转语音为 0.10 Xu / 词，最低 1 Xu。",
                f"配乐：基础 {music_prices['basic']} / 标准 {music_prices['standard']} / 高级 {music_prices['premium']} Xu。",
                "有歌词歌曲：基础 200 / 标准 250 / 高级 300 Xu。",
                ]),
            ),
            (
                "subtitle_dub",
                "字幕 / 翻译 / 配音",
                "\n".join([
                    "🌐 <b>字幕 / 翻译 / 配音</b>", "",
                    "发送视频、音频或文本，选择目标语言并在确认前查看当前报价。",
                    "仅在当前支持的流程中生成原始字幕时免费。",
                ]),
            ),
            _international_topup_guide_section(locale),
            (
                "packages",
                "套餐、组合与会员",
                "\n".join([
                    "🎁 <b>套餐、组合与会员</b>", "",
                    "套餐和组合按显示权益使用，不会转换为自由 Xu，也不计入会员充值进度。",
                    "符合资格的会员服务折扣会保留。",
                    "国际账户按确认页显示的服务价格收费。",
                ]),
            ),
            (
                "faq",
                "确认与支持",
                "\n".join([
                    "❓ <b>确认与支持</b>", "",
                    "请在确认前检查内容与报价。若付费步骤无法产生有效结果，不扣除 Xu 或按适用政策处理。",
                    "如需帮助，请发送 Telegram ID、截图和最近操作说明。",
                ]),
            ),
        ]
    return [
        (
            "quick_start",
            "Quick Start",
            "\n".join([
                "🚀 <b>TOAN AAS Quick Start</b>", "",
                "1. Choose Images, Product Video, Audio, Subtitles / Translation / Dubbing, or Documents.",
                "2. Describe the goal, source material, style, and intended use clearly.",
                "3. Review the quote before any paid processing.",
                "4. Xu is charged only after confirmation and a valid result.",
            ]),
        ),
        (
            "image_ai",
            "AI Images",
            "\n".join([
                "🖼 <b>AI Images</b>", "",
                "Send an image description, choose a quality tier, and confirm the quote before generation.", "",
                "Current public image tiers:", *image_lines,
                "", "If no valid image can be generated, no Xu is charged.",
            ]),
        ),
        (
            "video_ai",
            "Product Video",
            "\n".join([
                "🎬 <b>Product Video</b>", "",
                    "Choose the scene count and quality tier first. The confirmation screen shows per-scene pricing and total Xu.", "",
                    "Current public Product Video tiers:", *video_lines,
                    *video_discounts,
                    "", "Each tier uses its published duration and scene count.",
            ]),
        ),
        (
            "audio",
            "Voice and Music",
            "\n".join([
                "🎧 <b>Voice and Music</b>", "",
                "The first successful custom voice is 0 Xu; each later successful custom voice is 50 Xu.",
                "Text-to-speech is 0.10 Xu per word, minimum 1 Xu.",
                f"Background music: Basic {music_prices['basic']} / Standard {music_prices['standard']} / Premium {music_prices['premium']} Xu.",
                "Songs with vocals: Basic 200 / Standard 250 / Premium 300 Xu.",
            ]),
        ),
            (
                "subtitle_dub",
                "Subtitles / Translation / Dubbing",
            "\n".join([
                "🌐 <b>Subtitles / Translation / Dubbing</b>", "",
                "Send video, audio, or text, choose the target language, and review the current quote before confirmation.",
                    "Original subtitles are free only in supported current flows.",
                ]),
            ),
            _international_topup_guide_section(locale),
            (
                "packages",
            "Plans, Combos, and Membership",
            "\n".join([
                "🎁 <b>Plans, Combos, and Membership</b>", "",
                "Plans and combos are used according to their shown benefits; they are not convertible to flexible Xu and do not count toward member top-up progress.",
                "Eligible membership service discounts remain available.",
                "International accounts use the service price shown on the confirmation screen.",
            ]),
        ),
        (
            "faq",
            "Confirmation and Support",
            "\n".join([
                "❓ <b>Confirmation and Support</b>", "",
                "Review the request and quote before confirmation. If a paid step cannot produce a valid result, it is not charged or is handled under the applicable policy.",
                "For help, send your Telegram ID, a screenshot, and a description of the most recent action.",
            ]),
        ),
    ]


def guide_index_lines(lang: str = "vi") -> list[str]:
    locale = public_copy_locale(lang)
    sections = customer_guide_sections() if locale == "vi" else _international_guide_sections(locale)
    labels = _public_copy_labels(locale)
    copy = _public_locale_copy(locale)
    lines = [
        "📚 <b>HƯỚNG DẪN TOAN AAS</b>" if locale == "vi" else f"📚 <b>{labels['guide']}</b>",
        "",
        "Chọn mục bạn muốn xem:" if locale == "vi" else copy["choose"],
        "",
    ]
    for idx, (_key, title, _body) in enumerate(sections, start=1):
        lines.append(f"{idx}. {html.escape(title)} — /huongdan {idx}")
    lines.extend([
        "",
        "Người mới nên bắt đầu với /huongdan 1." if locale == "vi" else copy["quote"],
        CONFIRM_GATE_COPY if locale == "vi" else copy["quote"],
    ])
    return lines


def guide_lines(section: str = "", lang: str = "vi") -> list[str]:
    locale = public_copy_locale(lang)
    raw = (section or "").strip().lower()
    sections = customer_guide_sections() if locale == "vi" else _international_guide_sections(locale)
    aliases = {
        "guided_video": "video_ai",
        "trend": "video_ai",
        "music_add": "audio",
        "music": "audio",
        "voice": "audio",
        "amthanh": "audio",
        "phude": "subtitle_dub",
        "subtitle": "subtitle_dub",
        "translate": "subtitle_dub",
        "dub": "subtitle_dub",
        "dubbing": "subtitle_dub",
        "banggia": "credits",
        "pricing": "credits",
        "topup": "credits",
        "xu": "credits",
        "refund": "faq",
    }
    raw = aliases.get(raw, raw)
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(sections):
            key, title, body = sections[idx - 1]
            heading = "Hướng dẫn" if locale == "vi" else ("指南" if locale == "zh" else _public_locale_copy(locale)["guide"])
            index_label = "Mục lục" if locale == "vi" else ("目录" if locale == "zh" else _public_locale_copy(locale)["guide"])
            return [f"📘 <b>{heading} {idx}: {html.escape(title)}</b>", "", body, "", f"{index_label}: /huongdan"]
    for idx, (key, title, body) in enumerate(sections, start=1):
        if key == raw:
            heading = "Hướng dẫn" if locale == "vi" else ("指南" if locale == "zh" else _public_locale_copy(locale)["guide"])
            index_label = "Mục lục" if locale == "vi" else ("目录" if locale == "zh" else _public_locale_copy(locale)["guide"])
            return [f"📘 <b>{heading} {idx}: {html.escape(title)}</b>", "", body, "", f"{index_label}: /huongdan"]
    return guide_index_lines(locale)


def all_guide_lines(lang: str = "vi") -> list[str]:
    locale = public_copy_locale(lang)
    sections = customer_guide_sections() if locale == "vi" else _international_guide_sections(locale)
    lines = guide_index_lines(locale)
    for idx, (key, _title, _body) in enumerate(sections, start=1):
        lines.extend(["", "-----", ""])
        lines.extend(guide_lines(str(idx), locale))
    return lines


def pricing_markdown(context: dict | None = None, lang: str = "vi") -> str:
    return html_lines_to_markdown(all_pricing_lines(context, lang))


def guide_markdown(lang: str = "vi") -> str:
    return html_lines_to_markdown(all_guide_lines(lang))
