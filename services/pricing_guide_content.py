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


# Labels for the established Chinese guide-entry keyboard.  They remain in
# the public-copy owner so the legacy callback layout never falls back to
# English while its routes stay unchanged.
PUBLIC_GUIDE_NAVIGATION_I18N = {
    "zh": {
        "quick_start": "快速开始",
        "create_image": "创建图片",
        "create_video": "创建视频",
        "trend_video": "热门视频",
        "video_music": "视频音乐",
        "credits_topup": "Xu 充值",
        "faq_refunds": "常见问题与退款",
        "download_pricing": "下载价格表",
        "download_guide": "下载指南",
    },
}


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
        "images": "AI 图片", "video": "产品视频", "music": "AI 音乐", "voice": "语音",
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
        "pricing": "Mga Presyo ng TOAN AAS", "guide": "Gabay para sa gumagamit ng TOAN AAS", "home": "Pangunahing pahina", "choose": "Pumili ng seksyon:",
        "quote": "Ipinapakita ang pagtatantya bago kumpirmahin.", "images": "Mga larawang AI", "video": "Video ng produkto", "music": "Musikang AI", "voice": "Boses",
        "subtitles": "Mga subtitle / Pagsasalin / Pag-dub", "documents": "Mga dokumento", "member": "Pagiging miyembro", "free": "Mga libreng item",
        "image_unit": "larawan", "video_unit": "eksena", "input": "input", "output": "output",
    },
    "it": {
        "pricing": "Prezzi TOAN AAS", "guide": "Guida utente TOAN AAS", "home": "Pagina iniziale", "choose": "Scegli una sezione:",
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


# Customer-facing Telegram Hub copy.  This is intentionally kept with the
# public pricing/guide locale authority: it has no effect on routing, market
# eligibility, payment, or any provider/runtime behavior.
_PUBLIC_HUB_COPY = {
    "vi": {
        "hub_title": "TOAN AAS — Trợ lý AI của bạn",
        "hub_intro": "Chọn công cụ phù hợp để tạo nội dung, xử lý hình ảnh, video, âm thanh và tài liệu ngay trên Telegram.",
        "image_label": "Tạo ảnh AI", "image_description": "Tạo và chuẩn bị hình ảnh từ ý tưởng của bạn.",
        "video_label": "Tạo video AI", "video_description": "Lên ý tưởng và tạo video cho sản phẩm hoặc nội dung.",
        "music_label": "Nhạc & âm thanh", "music_description": "Chuẩn bị nhạc nền, hiệu ứng và nội dung âm thanh.",
        "voice_label": "Voice & lồng tiếng", "voice_description": "Xử lý giọng nói, phụ đề, dịch và lồng tiếng.",
        "chat_label": "Hỏi AI", "chat_description": "Trao đổi với AI để viết, lên ý tưởng và lập kế hoạch.",
        "guide_label": "Hướng dẫn", "guide_description": "Xem cách dùng, bảng giá và các bước tiếp theo.",
        "support": "Hỗ trợ", "center": "Trung tâm", "change_language": "Đổi ngôn ngữ", "main_menu": "Menu chính",
        "balance": "Số dư", "account_id": "ID", "tier": "Hạng", "language": "Ngôn ngữ",
    },
    "en": {
        "hub_title": "TOAN AAS — Your AI assistant",
        "hub_intro": "Choose a service to create content and work with images, video, audio, and documents directly in Telegram.",
        "image_label": "AI Images", "image_description": "Create and prepare visual assets from your ideas.",
        "video_label": "AI Video", "video_description": "Plan and create videos for products and content.",
        "music_label": "Music & Audio", "music_description": "Prepare background music, effects, and audio content.",
        "voice_label": "Voice & Dubbing", "voice_description": "Work with speech, subtitles, translation, and dubbing.",
        "chat_label": "Ask AI", "chat_description": "Talk with AI to write, develop ideas, and make plans.",
        "guide_label": "Guide", "guide_description": "View how-to information, pricing, and next steps.",
        "support": "Support", "center": "Center", "change_language": "Change language", "main_menu": "Main menu",
        "balance": "Balance", "account_id": "ID", "tier": "Tier", "language": "Language",
    },
    "zh": {
        "hub_title": "TOAN AAS — 您的 AI 助手",
        "hub_intro": "在 Telegram 中选择服务，完成内容创作、图片、视频、音频和文档工作。",
        "image_label": "AI 图片", "image_description": "根据您的想法创建并准备视觉素材。",
        "video_label": "AI 视频", "video_description": "为产品和内容策划并创建视频。",
        "music_label": "音乐与音频", "music_description": "准备背景音乐、音效和音频内容。",
        "voice_label": "语音与配音", "voice_description": "处理语音、字幕、翻译和配音。",
        "chat_label": "咨询 AI", "chat_description": "与 AI 交流，写作、构思并制定计划。",
        "guide_label": "使用指南", "guide_description": "查看使用方法、价格和下一步。",
        "support": "支持", "center": "中心", "change_language": "更改语言", "main_menu": "主菜单",
        "balance": "余额", "account_id": "ID", "tier": "等级", "language": "语言",
    },
    "es": {
        "hub_title": "TOAN AAS — Tu asistente de IA",
        "hub_intro": "Elige un servicio para crear contenido y trabajar con imágenes, vídeo, audio y documentos directamente en Telegram.",
        "image_label": "Imágenes con IA", "image_description": "Crea y prepara recursos visuales a partir de tus ideas.",
        "video_label": "Vídeo con IA", "video_description": "Planifica y crea vídeos para productos y contenido.",
        "music_label": "Música y audio", "music_description": "Prepara música de fondo, efectos y contenido de audio.",
        "voice_label": "Voz y doblaje", "voice_description": "Trabaja con voz, subtítulos, traducción y doblaje.",
        "chat_label": "Preguntar a la IA", "chat_description": "Habla con la IA para escribir, desarrollar ideas y hacer planes.",
        "guide_label": "Guía", "guide_description": "Consulta instrucciones, precios y los próximos pasos.",
        "support": "Ayuda", "center": "Centro", "change_language": "Cambiar idioma", "main_menu": "Menú principal",
        "balance": "Saldo", "account_id": "ID", "tier": "Nivel", "language": "Idioma",
    },
    "pt": {
        "hub_title": "TOAN AAS — Seu assistente de IA",
        "hub_intro": "Escolha um serviço para criar conteúdo e trabalhar com imagens, vídeo, áudio e documentos diretamente no Telegram.",
        "image_label": "Imagens com IA", "image_description": "Crie e prepare recursos visuais a partir das suas ideias.",
        "video_label": "Vídeo com IA", "video_description": "Planeje e crie vídeos para produtos e conteúdo.",
        "music_label": "Música e áudio", "music_description": "Prepare música de fundo, efeitos e conteúdo de áudio.",
        "voice_label": "Voz e dublagem", "voice_description": "Trabalhe com voz, legendas, tradução e dublagem.",
        "chat_label": "Perguntar à IA", "chat_description": "Converse com a IA para escrever, desenvolver ideias e planejar.",
        "guide_label": "Guia", "guide_description": "Veja instruções, preços e os próximos passos.",
        "support": "Suporte", "center": "Central", "change_language": "Mudar idioma", "main_menu": "Menu principal",
        "balance": "Saldo", "account_id": "ID", "tier": "Nível", "language": "Idioma",
    },
    "fr": {
        "hub_title": "TOAN AAS — Votre assistant IA",
        "hub_intro": "Choisissez un service pour créer du contenu et travailler avec des images, des vidéos, de l’audio et des documents dans Telegram.",
        "image_label": "Images IA", "image_description": "Créez et préparez des ressources visuelles à partir de vos idées.",
        "video_label": "Vidéo IA", "video_description": "Planifiez et créez des vidéos pour vos produits et contenus.",
        "music_label": "Musique et audio", "music_description": "Préparez musique de fond, effets et contenu audio.",
        "voice_label": "Voix et doublage", "voice_description": "Travaillez avec la voix, les sous-titres, la traduction et le doublage.",
        "chat_label": "Demander à l’IA", "chat_description": "Échangez avec l’IA pour écrire, développer des idées et planifier.",
        "guide_label": "Guide", "guide_description": "Consultez les instructions, les tarifs et les prochaines étapes.",
        "support": "Assistance", "center": "Centre", "change_language": "Changer de langue", "main_menu": "Menu principal",
        "balance": "Solde", "account_id": "ID", "tier": "Niveau", "language": "Langue",
    },
    "de": {
        "hub_title": "TOAN AAS — Ihr KI-Assistent",
        "hub_intro": "Wählen Sie einen Dienst, um Inhalte sowie Bilder, Videos, Audio und Dokumente direkt in Telegram zu bearbeiten.",
        "image_label": "KI-Bilder", "image_description": "Erstellen und bereiten Sie visuelle Inhalte aus Ihren Ideen vor.",
        "video_label": "KI-Video", "video_description": "Planen und erstellen Sie Videos für Produkte und Inhalte.",
        "music_label": "Musik und Audio", "music_description": "Bereiten Sie Hintergrundmusik, Effekte und Audioinhalte vor.",
        "voice_label": "Stimme und Synchronisation", "voice_description": "Arbeiten Sie mit Sprache, Untertiteln, Übersetzung und Synchronisation.",
        "chat_label": "KI fragen", "chat_description": "Sprechen Sie mit der KI zum Schreiben, Ideenentwickeln und Planen.",
        "guide_label": "Anleitung", "guide_description": "Sehen Sie Anleitungen, Preise und die nächsten Schritte an.",
        "support": "Support", "center": "Zentrum", "change_language": "Sprache ändern", "main_menu": "Hauptmenü",
        "balance": "Guthaben", "account_id": "ID", "tier": "Stufe", "language": "Sprache",
    },
    "ja": {
        "hub_title": "TOAN AAS — あなたの AI アシスタント",
        "hub_intro": "Telegram でサービスを選び、コンテンツ、画像、動画、音声、文書を作成・管理できます。",
        "image_label": "AI 画像", "image_description": "アイデアから視覚素材を作成し、準備します。",
        "video_label": "AI 動画", "video_description": "商品やコンテンツ向けの動画を企画・作成します。",
        "music_label": "音楽と音声", "music_description": "BGM、効果音、音声コンテンツを準備します。",
        "voice_label": "音声と吹き替え", "voice_description": "音声、字幕、翻訳、吹き替えを扱います。",
        "chat_label": "AI に相談", "chat_description": "AI と話して文章作成、発想、計画づくりを行います。",
        "guide_label": "ガイド", "guide_description": "使い方、料金、次の手順を確認できます。",
        "support": "サポート", "center": "センター", "change_language": "言語を変更", "main_menu": "メインメニュー",
        "balance": "残高", "account_id": "ID", "tier": "ランク", "language": "言語",
    },
    "ko": {
        "hub_title": "TOAN AAS — 나의 AI 도우미",
        "hub_intro": "Telegram에서 서비스를 선택해 콘텐츠, 이미지, 동영상, 오디오, 문서를 만들고 관리하세요.",
        "image_label": "AI 이미지", "image_description": "아이디어에서 시각 자료를 만들고 준비합니다.",
        "video_label": "AI 동영상", "video_description": "제품과 콘텐츠를 위한 동영상을 기획하고 만듭니다.",
        "music_label": "음악과 오디오", "music_description": "배경 음악, 효과음, 오디오 콘텐츠를 준비합니다.",
        "voice_label": "음성 및 더빙", "voice_description": "음성, 자막, 번역, 더빙 작업을 처리합니다.",
        "chat_label": "AI에게 물어보기", "chat_description": "AI와 대화하며 글쓰기, 아이디어 정리, 계획 수립을 합니다.",
        "guide_label": "가이드", "guide_description": "사용 방법, 요금, 다음 단계를 확인하세요.",
        "support": "지원", "center": "센터", "change_language": "언어 변경", "main_menu": "메인 메뉴",
        "balance": "잔액", "account_id": "ID", "tier": "등급", "language": "언어",
    },
    "hi": {
        "hub_title": "TOAN AAS — आपका AI सहायक",
        "hub_intro": "Telegram में सेवा चुनकर सामग्री, चित्र, वीडियो, ऑडियो और दस्तावेज़ पर काम करें।",
        "image_label": "AI चित्र", "image_description": "अपने विचारों से दृश्य सामग्री बनाएं और तैयार करें।",
        "video_label": "AI वीडियो", "video_description": "उत्पादों और सामग्री के लिए वीडियो की योजना बनाएं और तैयार करें।",
        "music_label": "संगीत और ऑडियो", "music_description": "पृष्ठभूमि संगीत, प्रभाव और ऑडियो सामग्री तैयार करें।",
        "voice_label": "आवाज़ और डबिंग", "voice_description": "आवाज़, उपशीर्षक, अनुवाद और डबिंग के साथ काम करें।",
        "chat_label": "AI से पूछें", "chat_description": "लिखने, विचार विकसित करने और योजना बनाने के लिए AI से बात करें।",
        "guide_label": "मार्गदर्शिका", "guide_description": "उपयोग विधि, कीमतें और अगले चरण देखें।",
        "support": "सहायता", "center": "केंद्र", "change_language": "भाषा बदलें", "main_menu": "मुख्य मेनू",
        "balance": "शेष राशि", "account_id": "ID", "tier": "स्तर", "language": "भाषा",
    },
    "ar": {
        "hub_title": "TOAN AAS — مساعدك بالذكاء الاصطناعي",
        "hub_intro": "اختر خدمة في Telegram لإنشاء المحتوى والعمل على الصور والفيديو والصوت والمستندات.",
        "image_label": "صور بالذكاء الاصطناعي", "image_description": "أنشئ وجهّز مواد مرئية من أفكارك.",
        "video_label": "فيديو بالذكاء الاصطناعي", "video_description": "خطط وأنشئ فيديوهات للمنتجات والمحتوى.",
        "music_label": "موسيقى وصوت", "music_description": "جهّز موسيقى الخلفية والمؤثرات والمحتوى الصوتي.",
        "voice_label": "صوت ودبلجة", "voice_description": "اعمل على الصوت والترجمة النصية والترجمة والدبلجة.",
        "chat_label": "اسأل الذكاء الاصطناعي", "chat_description": "تحدث مع الذكاء الاصطناعي للكتابة وتطوير الأفكار والتخطيط.",
        "guide_label": "الدليل", "guide_description": "اطلع على طريقة الاستخدام والأسعار والخطوات التالية.",
        "support": "الدعم", "center": "المركز", "change_language": "تغيير اللغة", "main_menu": "القائمة الرئيسية",
        "balance": "الرصيد", "account_id": "المعرّف", "tier": "المستوى", "language": "اللغة",
    },
    "ru": {
        "hub_title": "TOAN AAS — ваш помощник ИИ",
        "hub_intro": "Выберите сервис в Telegram для работы с контентом, изображениями, видео, аудио и документами.",
        "image_label": "Изображения ИИ", "image_description": "Создавайте и подготавливайте визуальные материалы по своим идеям.",
        "video_label": "Видео ИИ", "video_description": "Планируйте и создавайте видео для продуктов и контента.",
        "music_label": "Музыка и аудио", "music_description": "Подготавливайте фоновую музыку, эффекты и аудиоматериалы.",
        "voice_label": "Голос и дубляж", "voice_description": "Работайте с речью, субтитрами, переводом и дубляжом.",
        "chat_label": "Спросить ИИ", "chat_description": "Общайтесь с ИИ, чтобы писать, развивать идеи и планировать.",
        "guide_label": "Руководство", "guide_description": "Смотрите инструкции, цены и следующие шаги.",
        "support": "Поддержка", "center": "Центр", "change_language": "Сменить язык", "main_menu": "Главное меню",
        "balance": "Баланс", "account_id": "ID", "tier": "Уровень", "language": "Язык",
    },
    "tr": {
        "hub_title": "TOAN AAS — Yapay zekâ asistanınız",
        "hub_intro": "Telegram’da bir hizmet seçerek içerik, görsel, video, ses ve belgelerle çalışın.",
        "image_label": "Yapay zekâ görselleri", "image_description": "Fikirlerinizden görsel içerikler oluşturun ve hazırlayın.",
        "video_label": "Yapay zekâ videosu", "video_description": "Ürünler ve içerikler için videolar planlayın ve oluşturun.",
        "music_label": "Müzik ve ses", "music_description": "Arka plan müziği, efektler ve ses içeriği hazırlayın.",
        "voice_label": "Ses ve dublaj", "voice_description": "Ses, altyazı, çeviri ve dublaj ile çalışın.",
        "chat_label": "Yapay zekâya sor", "chat_description": "Yazmak, fikir geliştirmek ve plan yapmak için yapay zekâyla konuşun.",
        "guide_label": "Kılavuz", "guide_description": "Kullanım bilgilerini, fiyatları ve sonraki adımları görün.",
        "support": "Destek", "center": "Merkez", "change_language": "Dili değiştir", "main_menu": "Ana menü",
        "balance": "Bakiye", "account_id": "ID", "tier": "Seviye", "language": "Dil",
    },
    "th": {
        "hub_title": "TOAN AAS — ผู้ช่วย AI ของคุณ",
        "hub_intro": "เลือกบริการใน Telegram เพื่อสร้างเนื้อหาและทำงานกับภาพ วิดีโอ เสียง และเอกสาร",
        "image_label": "ภาพ AI", "image_description": "สร้างและเตรียมสื่อภาพจากไอเดียของคุณ",
        "video_label": "วิดีโอ AI", "video_description": "วางแผนและสร้างวิดีโอสำหรับสินค้าและเนื้อหา",
        "music_label": "เพลงและเสียง", "music_description": "เตรียมเพลงพื้นหลัง เอฟเฟกต์ และเนื้อหาเสียง",
        "voice_label": "เสียงและพากย์", "voice_description": "ทำงานกับเสียง คำบรรยาย การแปล และการพากย์",
        "chat_label": "ถาม AI", "chat_description": "สนทนากับ AI เพื่อเขียน พัฒนาไอเดีย และวางแผน",
        "guide_label": "คู่มือ", "guide_description": "ดูวิธีใช้ ราคา และขั้นตอนถัดไป",
        "support": "ช่วยเหลือ", "center": "ศูนย์กลาง", "change_language": "เปลี่ยนภาษา", "main_menu": "เมนูหลัก",
        "balance": "ยอดคงเหลือ", "account_id": "ID", "tier": "ระดับ", "language": "ภาษา",
    },
    "fil": {
        "hub_title": "TOAN AAS — Ang iyong katulong na AI",
        "hub_intro": "Pumili ng serbisyo sa Telegram para lumikha ng nilalaman at magtrabaho sa mga larawan, bidyo, tunog at dokumento.",
        "image_label": "Mga larawang AI", "image_description": "Gumawa at maghanda ng mga biswal na materyal mula sa iyong mga ideya.",
        "video_label": "Bidyong AI", "video_description": "Magplano at gumawa ng mga bidyo para sa produkto at nilalaman.",
        "music_label": "Musika at tunog", "music_description": "Maghanda ng musikang panglikuran, mga epekto at nilalamang tunog.",
        "voice_label": "Boses at dubbing", "voice_description": "Magtrabaho sa boses, subtitle, pagsasalin at dubbing.",
        "chat_label": "Magtanong sa AI", "chat_description": "Makipag-usap sa AI para magsulat, bumuo ng ideya at magplano.",
        "guide_label": "Gabay", "guide_description": "Tingnan ang paraan ng paggamit, presyo at susunod na hakbang.",
        "support": "Suporta", "center": "Sentro", "change_language": "Palitan ang wika", "main_menu": "Pangunahing menu",
        "balance": "Balanse", "account_id": "ID", "tier": "Antas", "language": "Wika",
    },
    "it": {
        "hub_title": "TOAN AAS — Il tuo assistente IA",
        "hub_intro": "Scegli un servizio in Telegram per creare contenuti e lavorare con immagini, video, audio e documenti.",
        "image_label": "Immagini IA", "image_description": "Crea e prepara risorse visive a partire dalle tue idee.",
        "video_label": "Video IA", "video_description": "Pianifica e crea video per prodotti e contenuti.",
        "music_label": "Musica e audio", "music_description": "Prepara musica di sottofondo, effetti e contenuti audio.",
        "voice_label": "Voce e doppiaggio", "voice_description": "Lavora con voce, sottotitoli, traduzione e doppiaggio.",
        "chat_label": "Chiedi all’IA", "chat_description": "Parla con l’IA per scrivere, sviluppare idee e pianificare.",
        "guide_label": "Guida", "guide_description": "Consulta istruzioni, prezzi e passaggi successivi.",
        "support": "Assistenza", "center": "Centro", "change_language": "Cambia lingua", "main_menu": "Menu principale",
        "balance": "Saldo", "account_id": "ID", "tier": "Livello", "language": "Lingua",
    },
    "id": {
        "hub_title": "TOAN AAS — Asisten AI Anda",
        "hub_intro": "Pilih layanan di Telegram untuk membuat konten dan bekerja dengan gambar, video, audio, serta dokumen.",
        "image_label": "Gambar AI", "image_description": "Buat dan siapkan materi visual dari ide Anda.",
        "video_label": "Video AI", "video_description": "Rencanakan dan buat video untuk produk serta konten.",
        "music_label": "Musik dan audio", "music_description": "Siapkan musik latar, efek, dan konten audio.",
        "voice_label": "Suara dan dubbing", "voice_description": "Bekerja dengan suara, subtitle, terjemahan, dan dubbing.",
        "chat_label": "Tanya AI", "chat_description": "Berbicara dengan AI untuk menulis, mengembangkan ide, dan merencanakan.",
        "guide_label": "Panduan", "guide_description": "Lihat cara penggunaan, harga, dan langkah berikutnya.",
        "support": "Dukungan", "center": "Pusat", "change_language": "Ganti bahasa", "main_menu": "Menu utama",
        "balance": "Saldo", "account_id": "ID", "tier": "Tingkat", "language": "Bahasa",
    },
}


# Small navigation-only additions for the same public copy authority above.
# They are deliberately copy-only and never determine payment, package, or
# account eligibility.
_PUBLIC_HUB_AUXILIARY_COPY = {
    "vi": {"back": "Quay lại", "manual_topup": "Nạp thủ công", "packages_label": "Gói & combo", "account_label": "Tài khoản", "topup_label": "Nạp Xu", "vietnamese_docx": "Hướng dẫn bằng tiếng Việt (DOCX)", "language_picker_title": "Chọn ngôn ngữ", "language_picker_intro": "Chọn ngôn ngữ bạn muốn dùng trong TOAN AAS."},
    "en": {"back": "Back", "manual_topup": "Manual top-up", "packages_label": "Plans & combos", "account_label": "Account", "topup_label": "Top up Xu", "vietnamese_docx": "Vietnamese guide (DOCX)", "language_picker_title": "Choose language", "language_picker_intro": "Choose the language you want to use in TOAN AAS."},
    "zh": {"back": "返回", "manual_topup": "手动充值", "packages_label": "套餐与组合", "account_label": "账户", "topup_label": "充值 Xu", "vietnamese_docx": "越南语指南（DOCX）", "language_picker_title": "选择语言", "language_picker_intro": "请选择您希望在 TOAN AAS 中使用的语言。"},
    "es": {"back": "Volver", "manual_topup": "Recarga manual", "packages_label": "Planes y combos", "account_label": "Cuenta", "topup_label": "Recargar Xu", "vietnamese_docx": "Guía en vietnamita (DOCX)", "language_picker_title": "Elige un idioma", "language_picker_intro": "Elige el idioma que quieres usar en TOAN AAS."},
    "pt": {"back": "Voltar", "manual_topup": "Recarga manual", "packages_label": "Planos e combos", "account_label": "Conta", "topup_label": "Recarregar Xu", "vietnamese_docx": "Guia em vietnamita (DOCX)", "language_picker_title": "Escolha um idioma", "language_picker_intro": "Escolha o idioma que deseja usar no TOAN AAS."},
    "fr": {"back": "Retour", "manual_topup": "Recharge manuelle", "packages_label": "Forfaits et combos", "account_label": "Compte", "topup_label": "Recharger Xu", "vietnamese_docx": "Guide en vietnamien (DOCX)", "language_picker_title": "Choisissez une langue", "language_picker_intro": "Choisissez la langue à utiliser dans TOAN AAS."},
    "de": {"back": "Zurück", "manual_topup": "Manuelle Aufladung", "packages_label": "Pakete und Kombis", "account_label": "Konto", "topup_label": "Xu aufladen", "vietnamese_docx": "Leitfaden auf Vietnamesisch (DOCX)", "language_picker_title": "Sprache wählen", "language_picker_intro": "Wähle die Sprache, die du in TOAN AAS verwenden möchtest."},
    "ja": {"back": "戻る", "manual_topup": "手動チャージ", "packages_label": "プランとコンボ", "account_label": "アカウント", "topup_label": "Xu をチャージ", "vietnamese_docx": "ベトナム語ガイド（DOCX）", "language_picker_title": "言語を選択", "language_picker_intro": "TOAN AAS で使用する言語を選択してください。"},
    "ko": {"back": "뒤로", "manual_topup": "수동 충전", "packages_label": "플랜 및 콤보", "account_label": "계정", "topup_label": "Xu 충전", "vietnamese_docx": "베트남어 가이드(DOCX)", "language_picker_title": "언어 선택", "language_picker_intro": "TOAN AAS에서 사용할 언어를 선택하세요."},
    "hi": {"back": "वापस", "manual_topup": "मैन्युअल टॉप-अप", "packages_label": "प्लान और कॉम्बो", "account_label": "खाता", "topup_label": "Xu टॉप-अप", "vietnamese_docx": "वियतनामी मार्गदर्शिका (DOCX)", "language_picker_title": "भाषा चुनें", "language_picker_intro": "TOAN AAS में उपयोग करने के लिए भाषा चुनें।"},
    "ar": {"back": "رجوع", "manual_topup": "شحن يدوي", "packages_label": "خطط وباقات", "account_label": "الحساب", "topup_label": "شحن Xu", "vietnamese_docx": "دليل باللغة الفيتنامية (DOCX)", "language_picker_title": "اختر اللغة", "language_picker_intro": "اختر اللغة التي تريد استخدامها في TOAN AAS."},
    "ru": {"back": "Назад", "manual_topup": "Ручное пополнение", "packages_label": "Планы и комплекты", "account_label": "Аккаунт", "topup_label": "Пополнить Xu", "vietnamese_docx": "Руководство на вьетнамском (DOCX)", "language_picker_title": "Выберите язык", "language_picker_intro": "Выберите язык для использования в TOAN AAS."},
    "tr": {"back": "Geri", "manual_topup": "Manuel yükleme", "packages_label": "Planlar ve paketler", "account_label": "Hesap", "topup_label": "Xu yükle", "vietnamese_docx": "Vietnamca kılavuz (DOCX)", "language_picker_title": "Dil seçin", "language_picker_intro": "TOAN AAS'ta kullanmak istediğiniz dili seçin."},
    "th": {"back": "ย้อนกลับ", "manual_topup": "เติมเงินด้วยตนเอง", "packages_label": "แพ็กเกจและคอมโบ", "account_label": "บัญชี", "topup_label": "เติม Xu", "vietnamese_docx": "คู่มือภาษาเวียดนาม (DOCX)", "language_picker_title": "เลือกภาษา", "language_picker_intro": "เลือกภาษาที่ต้องการใช้ใน TOAN AAS"},
    "fil": {"back": "Bumalik", "manual_topup": "Manwal na top-up", "packages_label": "Mga plano at combo", "account_label": "Account", "topup_label": "Mag-top-up ng Xu", "vietnamese_docx": "Gabay sa Vietnamese (DOCX)", "language_picker_title": "Pumili ng wika", "language_picker_intro": "Piliin ang wikang gusto mong gamitin sa TOAN AAS."},
    "it": {"back": "Indietro", "manual_topup": "Ricarica manuale", "packages_label": "Piani e combo", "account_label": "Account", "topup_label": "Ricarica Xu", "vietnamese_docx": "Guida in vietnamita (DOCX)", "language_picker_title": "Scegli una lingua", "language_picker_intro": "Scegli la lingua da usare in TOAN AAS."},
    "id": {"back": "Kembali", "manual_topup": "Isi ulang manual", "packages_label": "Paket dan kombo", "account_label": "Akun", "topup_label": "Isi ulang Xu", "vietnamese_docx": "Panduan berbahasa Vietnam (DOCX)", "language_picker_title": "Pilih bahasa", "language_picker_intro": "Pilih bahasa yang ingin digunakan di TOAN AAS."},
}


# Root-menu navigation is presentation-only.  These labels share the existing
# public-copy authority so every supported locale keeps the same callback map.
_PUBLIC_ROOT_NAVIGATION_COPY = {
    "vi": {"free_tools_label": "Công cụ miễn phí", "chat_pro_label": "Chat Pro", "audio_studio_label": "Studio âm thanh", "translation_label": "Dịch thuật", "notes_docs_label": "Ghi chú / Tài liệu", "topup_pricing_label": "Nạp Xu / Bảng giá", "feedback_label": "Góp ý / Báo lỗi", "admin_label": "Admin"},
    "en": {"free_tools_label": "Free tools", "chat_pro_label": "Chat Pro", "audio_studio_label": "Audio Studio", "translation_label": "Translation", "notes_docs_label": "Notes / Documents", "topup_pricing_label": "Top up Xu / Pricing", "feedback_label": "Feedback / Report a bug", "admin_label": "Admin"},
    "zh": {"free_tools_label": "免费工具", "chat_pro_label": "专业聊天", "audio_studio_label": "音频工作室", "translation_label": "翻译", "notes_docs_label": "笔记 / 文档", "topup_pricing_label": "充值 Xu / 价格", "feedback_label": "反馈 / 报错", "admin_label": "管理员"},
    "es": {"free_tools_label": "Herramientas gratuitas", "chat_pro_label": "Chat Pro", "audio_studio_label": "Estudio de audio", "translation_label": "Traducción", "notes_docs_label": "Notas / Documentos", "topup_pricing_label": "Recargar Xu / Precios", "feedback_label": "Opiniones / Informar de un error", "admin_label": "Administrador"},
    "pt": {"free_tools_label": "Ferramentas gratuitas", "chat_pro_label": "Chat Pro", "audio_studio_label": "Estúdio de áudio", "translation_label": "Tradução", "notes_docs_label": "Notas / Documentos", "topup_pricing_label": "Recarregar Xu / Preços", "feedback_label": "Comentários / Reportar erro", "admin_label": "Administrador"},
    "fr": {"free_tools_label": "Outils gratuits", "chat_pro_label": "Chat Pro", "audio_studio_label": "Studio audio", "translation_label": "Traduction", "notes_docs_label": "Notes / Documents", "topup_pricing_label": "Recharger Xu / Tarifs", "feedback_label": "Avis / Signaler un bug", "admin_label": "Administrateur"},
    "de": {"free_tools_label": "Kostenlose Tools", "chat_pro_label": "Chat Pro", "audio_studio_label": "Audiostudio", "translation_label": "Übersetzung", "notes_docs_label": "Notizen / Dokumente", "topup_pricing_label": "Xu aufladen / Preise", "feedback_label": "Feedback / Fehler melden", "admin_label": "Admin"},
    "ja": {"free_tools_label": "無料ツール", "chat_pro_label": "Chat Pro", "audio_studio_label": "オーディオスタジオ", "translation_label": "翻訳", "notes_docs_label": "メモ / ドキュメント", "topup_pricing_label": "Xu をチャージ / 料金", "feedback_label": "ご意見 / 不具合を報告", "admin_label": "管理者"},
    "ko": {"free_tools_label": "무료 도구", "chat_pro_label": "Chat Pro", "audio_studio_label": "오디오 스튜디오", "translation_label": "번역", "notes_docs_label": "메모 / 문서", "topup_pricing_label": "Xu 충전 / 요금", "feedback_label": "의견 / 오류 신고", "admin_label": "관리자"},
    "hi": {"free_tools_label": "निःशुल्क उपकरण", "chat_pro_label": "Chat Pro", "audio_studio_label": "ऑडियो स्टूडियो", "translation_label": "अनुवाद", "notes_docs_label": "नोट्स / दस्तावेज़", "topup_pricing_label": "Xu टॉप-अप / मूल्य", "feedback_label": "सुझाव / त्रुटि रिपोर्ट", "admin_label": "प्रशासक"},
    "ar": {"free_tools_label": "أدوات مجانية", "chat_pro_label": "Chat Pro", "audio_studio_label": "استوديو الصوت", "translation_label": "الترجمة", "notes_docs_label": "ملاحظات / مستندات", "topup_pricing_label": "شحن Xu / الأسعار", "feedback_label": "ملاحظات / بلاغ خطأ", "admin_label": "المشرف"},
    "ru": {"free_tools_label": "Бесплатные инструменты", "chat_pro_label": "Chat Pro", "audio_studio_label": "Аудиостудия", "translation_label": "Перевод", "notes_docs_label": "Заметки / Документы", "topup_pricing_label": "Пополнить Xu / Цены", "feedback_label": "Отзыв / Сообщить об ошибке", "admin_label": "Администратор"},
    "tr": {"free_tools_label": "Ücretsiz araçlar", "chat_pro_label": "Chat Pro", "audio_studio_label": "Ses stüdyosu", "translation_label": "Çeviri", "notes_docs_label": "Notlar / Belgeler", "topup_pricing_label": "Xu yükle / Fiyatlar", "feedback_label": "Geri bildirim / Hata bildir", "admin_label": "Yönetici"},
    "th": {"free_tools_label": "เครื่องมือฟรี", "chat_pro_label": "Chat Pro", "audio_studio_label": "สตูดิโอเสียง", "translation_label": "แปลภาษา", "notes_docs_label": "บันทึก / เอกสาร", "topup_pricing_label": "เติม Xu / ราคา", "feedback_label": "ข้อเสนอแนะ / แจ้งข้อผิดพลาด", "admin_label": "ผู้ดูแลระบบ"},
    "fil": {"free_tools_label": "Libreng mga tool", "chat_pro_label": "Chat Pro", "audio_studio_label": "Studio ng audio", "translation_label": "Pagsasalin", "notes_docs_label": "Mga tala / Dokumento", "topup_pricing_label": "Mag-top-up ng Xu / Mga presyo", "feedback_label": "Puna / Mag-ulat ng bug", "admin_label": "Administrador"},
    "it": {"free_tools_label": "Strumenti gratuiti", "chat_pro_label": "Chat Pro", "audio_studio_label": "Studio audio", "translation_label": "Traduzione", "notes_docs_label": "Note / Documenti", "topup_pricing_label": "Ricarica Xu / Prezzi", "feedback_label": "Feedback / Segnala un errore", "admin_label": "Amministratore"},
    "id": {"free_tools_label": "Alat gratis", "chat_pro_label": "Chat Pro", "audio_studio_label": "Studio audio", "translation_label": "Terjemahan", "notes_docs_label": "Catatan / Dokumen", "topup_pricing_label": "Isi ulang Xu / Harga", "feedback_label": "Masukan / Laporkan bug", "admin_label": "Admin"},
}


# Public Chat presentation copy.  These fields are intentionally display-only:
# they do not choose a provider, calculate a price, reserve/settle Xu, or
# change quota/memory state.  The English wording is the semantic baseline;
# every supported locale owns a direct customer-facing value below.
_PUBLIC_CHAT_ROOT_COPY = {
    "vi": {
        "chat_menu_title": "Chat TOAN AAS", "chat_mode_label": "Chế độ hiện tại", "chat_mode_free": "Chat miễn phí — Gemini", "chat_mode_pro": "Chat Pro — Opus 4.8", "chat_balance_label": "Số dư",
        "chat_free_summary": "Miễn phí: 20 câu trả lời thành công mỗi ngày Việt Nam; lỗi không trừ lượt.", "chat_pro_summary": "Pro: Opus 4.8, {rate} input/output; giá đã gồm ×3, tính theo usage thực tế, không giới hạn ngày khi đủ Xu.", "chat_memory_summary": "Bộ nhớ 48 giờ chỉ thuộc Chat công khai; phản hồi chỉ là văn bản.", "chat_owner_admin_summary": "Owner/Admin: miễn phí và không giới hạn.",
        "chat_pro_enable": "💎 Bật Chat Pro", "chat_pro_disable": "⏹ Tắt Chat Pro", "chat_free_label": "🆓 Chat miễn phí", "chat_account_label": "👤 Tài khoản",
        "chat_free_title": "Chat miễn phí", "chat_free_body": "Gemini 3.6 Flash; mỗi tài khoản có 20 câu trả lời thành công mỗi ngày Việt Nam. Lỗi không trừ lượt. Bộ nhớ tách riêng 48 giờ và chỉ trả văn bản.",
        "chat_error_quota": "⚠️ Bạn đã dùng hết 20 lượt Chat miễn phí hôm nay. Ngày Việt Nam mới sẽ tự mở lại.", "chat_error_insufficient_xu": "❌ Không đủ Xu cho Chat Pro. Bot chưa gọi Opus và chưa trừ thêm Xu.", "chat_error_unsupported": "⚠️ Nội dung này chưa thuộc năng lực của chế độ Chat đang chọn. Bot chưa gọi AI và chưa trừ Xu.", "chat_error_duplicate": "ℹ️ Tin nhắn trùng đã được xử lý; bot không gửi lặp câu trả lời.", "chat_error_provider": "⚠️ AI đang bận hoặc không trả lời hợp lệ. Bot chưa trừ Xu/lượt; bạn thử lại sau.",
        "chat_media_redirect_body": "Tác vụ tạo media dùng dịch vụ riêng có màn xác nhận. Chat chỉ trả văn bản; bot chưa gọi provider và chưa trừ Xu.", "chat_media_redirect_image": "🖼 Mở Tạo ảnh AI", "chat_media_redirect_video": "🎬 Mở Tạo video AI",
        "chat_footer_pro_admin": "💎 Chat Pro • Owner/Admin: miễn phí", "chat_footer_pro_usage": "💎 Chat Pro • -{charged} Xu • usage thực tế", "chat_footer_free_admin": "🆓 Chat miễn phí • Owner/Admin: miễn phí, không giới hạn", "chat_footer_free_remaining": "🆓 Chat miễn phí • còn {remaining} lượt hôm nay",
    },
    "en": {
        "chat_menu_title": "TOAN AAS Chat", "chat_mode_label": "Current mode", "chat_mode_free": "Free Chat — Gemini", "chat_mode_pro": "Chat Pro — Opus 4.8", "chat_balance_label": "Balance",
        "chat_free_summary": "Free: 20 successful replies per Vietnam day; failures do not consume quota.", "chat_pro_summary": "Pro: Opus 4.8, {rate} input/output; price includes ×3, billed by actual usage, with no daily cap while Xu is sufficient.", "chat_memory_summary": "Memory lasts 48 hours for public chat only; replies are text-only.", "chat_owner_admin_summary": "Owner/Admin: free and unlimited.",
        "chat_pro_enable": "💎 Enable Chat Pro", "chat_pro_disable": "⏹ Disable Chat Pro", "chat_free_label": "🆓 Free Chat", "chat_account_label": "👤 Account",
        "chat_free_title": "Free Chat", "chat_free_body": "Gemini 3.6 Flash; 20 successful replies per Vietnam day/account. Failed replies do not consume a turn. Memory is isolated to 48 hours and output is text-only.",
        "chat_error_quota": "⚠️ You have used all 20 Free Chat replies for today. The next Vietnam day will restore access.", "chat_error_insufficient_xu": "❌ There is not enough Xu for Chat Pro. The bot did not call Opus or charge additional Xu.", "chat_error_unsupported": "⚠️ This content is not supported by the selected Chat mode. The bot did not call AI or charge Xu.", "chat_error_duplicate": "ℹ️ This duplicate message was already processed; the bot will not send the reply twice.", "chat_error_provider": "⚠️ AI is busy or did not return a valid reply. No Xu or Free Chat turn was charged; please try again later.",
        "chat_media_redirect_body": "Media creation uses a separate service with its own confirmation screen. Chat returns text only; the bot did not call a provider or charge Xu.", "chat_media_redirect_image": "🖼 Open AI Images", "chat_media_redirect_video": "🎬 Open AI Video",
        "chat_footer_pro_admin": "💎 Chat Pro • Owner/Admin: free", "chat_footer_pro_usage": "💎 Chat Pro • -{charged} Xu • actual usage", "chat_footer_free_admin": "🆓 Free Chat • Owner/Admin: free and unlimited", "chat_footer_free_remaining": "🆓 Free Chat • {remaining} replies left today",
    },
    "zh": {
        "chat_menu_title": "TOAN AAS 聊天", "chat_mode_label": "当前模式", "chat_mode_free": "免费聊天 — Gemini", "chat_mode_pro": "专业聊天 — Opus 4.8", "chat_balance_label": "余额",
        "chat_free_summary": "免费：每个越南日最多 20 次成功回复；失败不扣次数。", "chat_pro_summary": "专业模式：Opus 4.8，{rate} 输入/输出；价格已含 ×3，按实际用量计费，Xu 充足时没有每日上限。", "chat_memory_summary": "记忆仅用于公开聊天，保留 48 小时；只返回文字。", "chat_owner_admin_summary": "Owner/Admin：免费且无限制。",
        "chat_pro_enable": "💎 开启专业聊天", "chat_pro_disable": "⏹ 关闭专业聊天", "chat_free_label": "🆓 免费聊天", "chat_account_label": "👤 我的账户",
        "chat_free_title": "免费聊天", "chat_free_body": "Gemini 3.6 Flash；每个账号每天（越南日期）最多 20 次成功回复，失败不扣次数。记忆仅保留 48 小时，回复只返回文字。",
        "chat_error_quota": "⚠️ 您今天已用完 20 次免费聊天回复。新的越南日期开始后会自动恢复。", "chat_error_insufficient_xu": "❌ Chat Pro 的 Xu 不足。机器人没有调用 Opus，也没有额外扣除 Xu。", "chat_error_unsupported": "⚠️ 所选聊天模式暂不支持此内容。机器人没有调用 AI，也没有扣除 Xu。", "chat_error_duplicate": "ℹ️ 重复消息已处理，机器人不会重复发送回复。", "chat_error_provider": "⚠️ AI 正忙或未返回有效回复。没有扣除 Xu 或免费次数，请稍后再试。",
        "chat_media_redirect_body": "媒体创建使用独立服务和确认页面。聊天只返回文字；机器人没有调用服务商或扣除 Xu。", "chat_media_redirect_image": "🖼 打开 AI 图片", "chat_media_redirect_video": "🎬 打开 AI 视频",
        "chat_footer_pro_admin": "💎 专业聊天 • Owner/Admin：免费", "chat_footer_pro_usage": "💎 专业聊天 • -{charged} Xu • 实际用量", "chat_footer_free_admin": "🆓 免费聊天 • Owner/Admin：免费且无限制", "chat_footer_free_remaining": "🆓 免费聊天 • 今日还剩 {remaining} 次",
    },
}


_PUBLIC_CHAT_ROOT_COPY.update({
    "es": {"chat_menu_title":"Chat de TOAN AAS","chat_mode_label":"Modo actual","chat_mode_free":"Chat gratuito — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Saldo","chat_free_summary":"Gratis: 20 respuestas correctas por día de Vietnam; los fallos no consumen cuota.","chat_pro_summary":"Pro: Opus 4.8, {rate} de entrada/salida; el precio incluye ×3, se cobra por uso real y no tiene límite diario si hay Xu suficientes.","chat_memory_summary":"La memoria dura 48 horas solo para el chat público; las respuestas son solo texto.","chat_owner_admin_summary":"Owner/Admin: gratis e ilimitado.","chat_pro_enable":"💎 Activar Chat Pro","chat_pro_disable":"⏹ Desactivar Chat Pro","chat_free_label":"🆓 Chat gratuito","chat_account_label":"👤 Cuenta","chat_free_title":"Chat gratuito","chat_free_body":"Gemini 3.6 Flash; 20 respuestas correctas por cuenta y día de Vietnam. Los fallos no consumen turno. La memoria se limita a 48 horas y la salida es solo texto.","chat_error_quota":"⚠️ Ya usaste las 20 respuestas de Chat gratuito de hoy. El próximo día de Vietnam restaurará el acceso.","chat_error_insufficient_xu":"❌ No hay Xu suficientes para Chat Pro. El bot no llamó a Opus ni cobró Xu adicionales.","chat_error_unsupported":"⚠️ Este contenido no es compatible con el modo de Chat elegido. El bot no llamó a la IA ni cobró Xu.","chat_error_duplicate":"ℹ️ Este mensaje duplicado ya fue procesado; el bot no enviará la respuesta dos veces.","chat_error_provider":"⚠️ La IA está ocupada o no devolvió una respuesta válida. No se cobró Xu ni un turno gratuito; inténtalo más tarde.","chat_media_redirect_body":"La creación de medios usa un servicio aparte con su propia pantalla de confirmación. El chat solo devuelve texto; el bot no llamó a un proveedor ni cobró Xu.","chat_media_redirect_image":"🖼 Abrir imágenes con IA","chat_media_redirect_video":"🎬 Abrir vídeo con IA","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: gratis","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • uso real","chat_footer_free_admin":"🆓 Chat gratuito • Owner/Admin: gratis e ilimitado","chat_footer_free_remaining":"🆓 Chat gratuito • quedan {remaining} respuestas hoy"},
    "pt": {"chat_menu_title":"Chat TOAN AAS","chat_mode_label":"Modo atual","chat_mode_free":"Chat gratuito — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Saldo","chat_free_summary":"Grátis: 20 respostas bem-sucedidas por dia do Vietnã; falhas não consomem a cota.","chat_pro_summary":"Pro: Opus 4.8, {rate} de entrada/saída; o preço inclui ×3, é cobrado pelo uso real e não há limite diário com Xu suficiente.","chat_memory_summary":"A memória dura 48 horas apenas para o chat público; as respostas são somente texto.","chat_owner_admin_summary":"Owner/Admin: grátis e ilimitado.","chat_pro_enable":"💎 Ativar Chat Pro","chat_pro_disable":"⏹ Desativar Chat Pro","chat_free_label":"🆓 Chat gratuito","chat_account_label":"👤 Conta","chat_free_title":"Chat gratuito","chat_free_body":"Gemini 3.6 Flash; 20 respostas bem-sucedidas por conta e dia do Vietnã. Falhas não consomem uma vez. A memória é isolada por 48 horas e a saída é apenas texto.","chat_error_quota":"⚠️ Você usou todas as 20 respostas gratuitas de hoje. O próximo dia do Vietnã restaurará o acesso.","chat_error_insufficient_xu":"❌ Não há Xu suficiente para o Chat Pro. O bot não chamou o Opus nem cobrou Xu adicional.","chat_error_unsupported":"⚠️ Este conteúdo não é compatível com o modo de Chat selecionado. O bot não chamou a IA nem cobrou Xu.","chat_error_duplicate":"ℹ️ Esta mensagem duplicada já foi processada; o bot não enviará a resposta duas vezes.","chat_error_provider":"⚠️ A IA está ocupada ou não retornou uma resposta válida. Nenhum Xu nem turno gratuito foi cobrado; tente mais tarde.","chat_media_redirect_body":"A criação de mídia usa um serviço separado com sua própria tela de confirmação. O chat responde apenas em texto; o bot não chamou um provedor nem cobrou Xu.","chat_media_redirect_image":"🖼 Abrir imagens com IA","chat_media_redirect_video":"🎬 Abrir vídeo com IA","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: grátis","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • uso real","chat_footer_free_admin":"🆓 Chat gratuito • Owner/Admin: grátis e ilimitado","chat_footer_free_remaining":"🆓 Chat gratuito • restam {remaining} respostas hoje"},
    "fr": {"chat_menu_title":"Chat TOAN AAS","chat_mode_label":"Mode actuel","chat_mode_free":"Chat gratuit — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Solde","chat_free_summary":"Gratuit : 20 réponses réussies par jour vietnamien ; les échecs ne consomment pas le quota.","chat_pro_summary":"Pro : Opus 4.8, {rate} en entrée/sortie ; le prix inclut ×3, facturé à l’usage réel, sans plafond quotidien si les Xu sont suffisants.","chat_memory_summary":"La mémoire dure 48 heures pour le chat public uniquement ; les réponses sont en texte uniquement.","chat_owner_admin_summary":"Owner/Admin : gratuit et illimité.","chat_pro_enable":"💎 Activer Chat Pro","chat_pro_disable":"⏹ Désactiver Chat Pro","chat_free_label":"🆓 Chat gratuit","chat_account_label":"👤 Compte","chat_free_title":"Chat gratuit","chat_free_body":"Gemini 3.6 Flash ; 20 réponses réussies par compte et jour vietnamien. Les échecs ne consomment pas de tour. La mémoire est isolée sur 48 heures et la sortie est uniquement textuelle.","chat_error_quota":"⚠️ Vous avez utilisé les 20 réponses gratuites d’aujourd’hui. Le prochain jour vietnamien rétablira l’accès.","chat_error_insufficient_xu":"❌ Xu insuffisants pour Chat Pro. Le bot n’a pas appelé Opus et n’a pas débité de Xu supplémentaire.","chat_error_unsupported":"⚠️ Ce contenu n’est pas pris en charge par le mode de chat sélectionné. Le bot n’a pas appelé l’IA ni débité de Xu.","chat_error_duplicate":"ℹ️ Ce message en double a déjà été traité ; le bot n’enverra pas la réponse deux fois.","chat_error_provider":"⚠️ L’IA est occupée ou n’a pas renvoyé de réponse valide. Aucun Xu ni tour gratuit n’a été débité ; réessayez plus tard.","chat_media_redirect_body":"La création de médias utilise un service distinct avec son propre écran de confirmation. Le chat ne renvoie que du texte ; le bot n’a appelé aucun fournisseur ni débité de Xu.","chat_media_redirect_image":"🖼 Ouvrir les images IA","chat_media_redirect_video":"🎬 Ouvrir la vidéo IA","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin : gratuit","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • usage réel","chat_footer_free_admin":"🆓 Chat gratuit • Owner/Admin : gratuit et illimité","chat_footer_free_remaining":"🆓 Chat gratuit • il reste {remaining} réponses aujourd’hui"},
    "de": {"chat_menu_title":"TOAN AAS Chat","chat_mode_label":"Aktueller Modus","chat_mode_free":"Kostenloser Chat — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Guthaben","chat_free_summary":"Kostenlos: 20 erfolgreiche Antworten pro vietnamesischem Tag; Fehler verbrauchen kein Kontingent.","chat_pro_summary":"Pro: Opus 4.8, {rate} Ein-/Ausgabe; Preis enthält ×3, Abrechnung nach tatsächlicher Nutzung, ohne Tageslimit bei ausreichend Xu.","chat_memory_summary":"Der Speicher gilt nur für den öffentlichen Chat und bleibt 48 Stunden erhalten; Antworten sind nur Text.","chat_owner_admin_summary":"Owner/Admin: kostenlos und unbegrenzt.","chat_pro_enable":"💎 Chat Pro aktivieren","chat_pro_disable":"⏹ Chat Pro deaktivieren","chat_free_label":"🆓 Kostenloser Chat","chat_account_label":"👤 Konto","chat_free_title":"Kostenloser Chat","chat_free_body":"Gemini 3.6 Flash; 20 erfolgreiche Antworten pro Konto und vietnamesischem Tag. Fehler verbrauchen keinen Zug. Der Speicher ist 48 Stunden getrennt und die Ausgabe ist nur Text.","chat_error_quota":"⚠️ Sie haben die 20 kostenlosen Antworten für heute aufgebraucht. Am nächsten vietnamesischen Tag wird der Zugriff wiederhergestellt.","chat_error_insufficient_xu":"❌ Nicht genügend Xu für Chat Pro. Der Bot hat Opus nicht aufgerufen und keine zusätzlichen Xu berechnet.","chat_error_unsupported":"⚠️ Dieser Inhalt wird vom gewählten Chat-Modus nicht unterstützt. Der Bot hat keine KI aufgerufen und keine Xu berechnet.","chat_error_duplicate":"ℹ️ Diese doppelte Nachricht wurde bereits verarbeitet; der Bot sendet die Antwort nicht zweimal.","chat_error_provider":"⚠️ Die KI ist beschäftigt oder hat keine gültige Antwort geliefert. Es wurden weder Xu noch ein kostenloser Zug berechnet; versuchen Sie es später erneut.","chat_media_redirect_body":"Medienerstellung nutzt einen separaten Dienst mit eigener Bestätigungsseite. Der Chat gibt nur Text zurück; der Bot hat keinen Anbieter aufgerufen und keine Xu berechnet.","chat_media_redirect_image":"🖼 KI-Bilder öffnen","chat_media_redirect_video":"🎬 KI-Video öffnen","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: kostenlos","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • tatsächliche Nutzung","chat_footer_free_admin":"🆓 Kostenloser Chat • Owner/Admin: kostenlos und unbegrenzt","chat_footer_free_remaining":"🆓 Kostenloser Chat • noch {remaining} Antworten heute"},
})


_PUBLIC_CHAT_ROOT_COPY.update({
    "fil": {"chat_menu_title":"TOAN AAS Chat","chat_mode_label":"Kasalukuyang mode","chat_mode_free":"Libreng chat — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Balanse","chat_free_summary":"Libre: 20 matagumpay na sagot bawat araw sa Vietnam; hindi nababawasan ang quota kapag nabigo.","chat_pro_summary":"Pro: Opus 4.8, input/output na {rate}; kasama ang ×3 sa presyo, batay sa aktuwal na paggamit, at walang arawang limit kapag sapat ang Xu.","chat_memory_summary":"Ang memorya ay 48 oras lamang para sa pampublikong chat; text lamang ang mga sagot.","chat_owner_admin_summary":"Owner/Admin: libre at walang limitasyon.","chat_pro_enable":"💎 I-on ang Chat Pro","chat_pro_disable":"⏹ I-off ang Chat Pro","chat_free_label":"🆓 Libreng chat","chat_account_label":"👤 Account","chat_free_title":"Libreng chat","chat_free_body":"Gemini 3.6 Flash; 20 matagumpay na sagot bawat account bawat araw sa Vietnam. Hindi nababawasan ang turn kapag nabigo, hiwalay ang memorya sa loob ng 48 oras, at text lamang ang output.","chat_error_quota":"⚠️ Nagamit mo na ang lahat ng 20 libreng sagot ngayong araw. Awtomatikong babalik ang access sa susunod na araw sa Vietnam.","chat_error_insufficient_xu":"❌ Kulang ang Xu para sa Chat Pro. Hindi tinawag ng bot ang Opus at walang dagdag na Xu na nabawas.","chat_error_unsupported":"⚠️ Hindi suportado ang nilalamang ito ng napiling Chat mode. Hindi tumawag ang bot sa AI at walang Xu na nabawas.","chat_error_duplicate":"ℹ️ Naproseso na ang dobleng mensaheng ito; hindi ipapadala ng bot ang sagot nang dalawang beses.","chat_error_provider":"⚠️ Abala ang AI o walang wastong sagot. Walang Xu o libreng turn na nabawas; subukan muli mamaya.","chat_media_redirect_body":"Gumagamit ang paglikha ng media ng hiwalay na serbisyo na may sariling screen ng kumpirmasyon. Text lamang ang sagot ng chat; walang provider na tinawag at walang Xu na nabawas.","chat_media_redirect_image":"🖼 Buksan ang AI images","chat_media_redirect_video":"🎬 Buksan ang AI video","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: libre","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • aktuwal na paggamit","chat_footer_free_admin":"🆓 Libreng chat • Owner/Admin: libre at walang limitasyon","chat_footer_free_remaining":"🆓 Libreng chat • {remaining} sagot ang natitira ngayon"},
    "it": {"chat_menu_title":"Chat TOAN AAS","chat_mode_label":"Modalità attuale","chat_mode_free":"Chat gratuito — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Saldo","chat_free_summary":"Gratuito: 20 risposte riuscite al giorno vietnamita; gli errori non consumano quota.","chat_pro_summary":"Pro: Opus 4.8, input/output {rate}; il prezzo include ×3, addebitato in base all'uso reale, senza limite giornaliero con Xu sufficienti.","chat_memory_summary":"La memoria dura 48 ore solo per la chat pubblica; le risposte sono solo testo.","chat_owner_admin_summary":"Owner/Admin: gratuito e illimitato.","chat_pro_enable":"💎 Attiva Chat Pro","chat_pro_disable":"⏹ Disattiva Chat Pro","chat_free_label":"🆓 Chat gratuita","chat_account_label":"👤 Account","chat_free_title":"Chat gratuita","chat_free_body":"Gemini 3.6 Flash; 20 risposte riuscite per account e giorno vietnamita. Gli errori non consumano un turno, la memoria è isolata per 48 ore e l'output è solo testo.","chat_error_quota":"⚠️ Hai usato tutte le 20 risposte gratuite di oggi. L'accesso tornerà automaticamente nel prossimo giorno vietnamita.","chat_error_insufficient_xu":"❌ Xu insufficienti per Chat Pro. Il bot non ha chiamato Opus e non ha addebitato Xu aggiuntivi.","chat_error_unsupported":"⚠️ Questo contenuto non è supportato dalla modalità Chat selezionata. Il bot non ha chiamato l'IA né addebitato Xu.","chat_error_duplicate":"ℹ️ Questo messaggio duplicato è già stato elaborato; il bot non invierà la risposta due volte.","chat_error_provider":"⚠️ L'IA è occupata o non ha restituito una risposta valida. Non sono stati addebitati Xu né un turno gratuito; riprova più tardi.","chat_media_redirect_body":"La creazione dei media usa un servizio separato con la propria schermata di conferma. La chat restituisce solo testo; il bot non ha chiamato un fornitore né addebitato Xu.","chat_media_redirect_image":"🖼 Apri immagini IA","chat_media_redirect_video":"🎬 Apri video IA","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: gratuito","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • uso reale","chat_footer_free_admin":"🆓 Chat gratuita • Owner/Admin: gratuito e illimitato","chat_footer_free_remaining":"🆓 Chat gratuita • restano {remaining} risposte oggi"},
    "id": {"chat_menu_title":"Chat TOAN AAS","chat_mode_label":"Mode saat ini","chat_mode_free":"Chat gratis — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Saldo","chat_free_summary":"Gratis: 20 balasan berhasil per hari Vietnam; kegagalan tidak menghabiskan kuota.","chat_pro_summary":"Pro: Opus 4.8, input/output {rate}; harga termasuk ×3, ditagih sesuai pemakaian nyata, tanpa batas harian jika Xu mencukupi.","chat_memory_summary":"Memori bertahan 48 jam hanya untuk chat publik; balasan hanya berupa teks.","chat_owner_admin_summary":"Owner/Admin: gratis dan tanpa batas.","chat_pro_enable":"💎 Aktifkan Chat Pro","chat_pro_disable":"⏹ Nonaktifkan Chat Pro","chat_free_label":"🆓 Chat gratis","chat_account_label":"👤 Akun","chat_free_title":"Chat gratis","chat_free_body":"Gemini 3.6 Flash; 20 balasan berhasil per akun per hari Vietnam. Kegagalan tidak menghabiskan giliran, memori terpisah selama 48 jam, dan keluaran hanya teks.","chat_error_quota":"⚠️ Anda telah memakai seluruh 20 balasan Chat gratis hari ini. Akses akan kembali otomatis pada hari Vietnam berikutnya.","chat_error_insufficient_xu":"❌ Xu tidak cukup untuk Chat Pro. Bot tidak memanggil Opus dan tidak memotong Xu tambahan.","chat_error_unsupported":"⚠️ Konten ini tidak didukung oleh mode Chat yang dipilih. Bot tidak memanggil AI dan tidak memotong Xu.","chat_error_duplicate":"ℹ️ Pesan duplikat ini sudah diproses; bot tidak akan mengirim balasan dua kali.","chat_error_provider":"⚠️ AI sedang sibuk atau tidak memberikan balasan yang valid. Tidak ada Xu atau giliran gratis yang dipotong; silakan coba lagi nanti.","chat_media_redirect_body":"Pembuatan media menggunakan layanan terpisah dengan layar konfirmasi sendiri. Chat hanya mengembalikan teks; bot tidak memanggil penyedia dan tidak memotong Xu.","chat_media_redirect_image":"🖼 Buka gambar AI","chat_media_redirect_video":"🎬 Buka video AI","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: gratis","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • pemakaian nyata","chat_footer_free_admin":"🆓 Chat gratis • Owner/Admin: gratis dan tanpa batas","chat_footer_free_remaining":"🆓 Chat gratis • tersisa {remaining} balasan hari ini"},
})


_PUBLIC_CHAT_ROOT_COPY.update({
    "ru": {"chat_menu_title":"Чат TOAN AAS","chat_mode_label":"Текущий режим","chat_mode_free":"Бесплатный чат — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Баланс","chat_free_summary":"Бесплатно: 20 успешных ответов за вьетнамский день; ошибки не расходуют лимит.","chat_pro_summary":"Pro: Opus 4.8, ввод/вывод {rate}; цена включает ×3, списание по фактическому использованию, без дневного лимита при достаточном Xu.","chat_memory_summary":"Память хранится 48 часов только для публичного чата; ответы только текстовые.","chat_owner_admin_summary":"Owner/Admin: бесплатно и без ограничений.","chat_pro_enable":"💎 Включить Chat Pro","chat_pro_disable":"⏹ Выключить Chat Pro","chat_free_label":"🆓 Бесплатный чат","chat_account_label":"👤 Аккаунт","chat_free_title":"Бесплатный чат","chat_free_body":"Gemini 3.6 Flash; 20 успешных ответов на аккаунт за вьетнамский день. Ошибки не расходуют попытку, память изолирована на 48 часов, ответы только текстовые.","chat_error_quota":"⚠️ Вы использовали все 20 бесплатных ответов сегодня. Доступ автоматически вернётся в следующий вьетнамский день.","chat_error_insufficient_xu":"❌ Недостаточно Xu для Chat Pro. Бот не вызывал Opus и не списывал дополнительные Xu.","chat_error_unsupported":"⚠️ Этот контент не поддерживается выбранным режимом чата. Бот не вызывал ИИ и не списывал Xu.","chat_error_duplicate":"ℹ️ Это повторное сообщение уже обработано; бот не отправит ответ дважды.","chat_error_provider":"⚠️ ИИ занят или не вернул корректный ответ. Xu или бесплатная попытка не списаны; попробуйте позже.","chat_media_redirect_body":"Создание медиа использует отдельный сервис с собственным экраном подтверждения. Чат возвращает только текст; бот не вызывал провайдера и не списывал Xu.","chat_media_redirect_image":"🖼 Открыть изображения ИИ","chat_media_redirect_video":"🎬 Открыть видео ИИ","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: бесплатно","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • фактическое использование","chat_footer_free_admin":"🆓 Бесплатный чат • Owner/Admin: бесплатно и без ограничений","chat_footer_free_remaining":"🆓 Бесплатный чат • осталось {remaining} ответов сегодня"},
    "tr": {"chat_menu_title":"TOAN AAS Sohbet","chat_mode_label":"Geçerli mod","chat_mode_free":"Ücretsiz sohbet — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"Bakiye","chat_free_summary":"Ücretsiz: Vietnam gününde 20 başarılı yanıt; başarısızlıklar kotayı tüketmez.","chat_pro_summary":"Pro: Opus 4.8, {rate} giriş/çıkış; fiyat ×3 içerir, gerçek kullanıma göre alınır ve yeterli Xu varsa günlük sınır yoktur.","chat_memory_summary":"Bellek yalnızca genel sohbet için 48 saat tutulur; yanıtlar yalnızca metindir.","chat_owner_admin_summary":"Owner/Admin: ücretsiz ve sınırsız.","chat_pro_enable":"💎 Chat Pro'yu aç","chat_pro_disable":"⏹ Chat Pro'yu kapat","chat_free_label":"🆓 Ücretsiz sohbet","chat_account_label":"👤 Hesap","chat_free_title":"Ücretsiz sohbet","chat_free_body":"Gemini 3.6 Flash; Vietnam gününde hesap başına 20 başarılı yanıt. Hatalar bir hakkı tüketmez, bellek 48 saat ayrıdır ve çıktı yalnızca metindir.","chat_error_quota":"⚠️ Bugünkü 20 ücretsiz sohbet yanıtının tamamını kullandınız. Sonraki Vietnam gününde erişim otomatik olarak açılır.","chat_error_insufficient_xu":"❌ Chat Pro için yeterli Xu yok. Bot Opus'u çağırmadı ve ek Xu kesmedi.","chat_error_unsupported":"⚠️ Bu içerik seçilen sohbet modunda desteklenmiyor. Bot AI'ı çağırmadı ve Xu kesmedi.","chat_error_duplicate":"ℹ️ Bu yinelenen mesaj zaten işlendi; bot yanıtı iki kez göndermeyecek.","chat_error_provider":"⚠️ AI meşgul veya geçerli bir yanıt döndürmedi. Xu ya da ücretsiz hak kesilmedi; daha sonra yeniden deneyin.","chat_media_redirect_body":"Medya oluşturma, kendi onay ekranı olan ayrı bir hizmet kullanır. Sohbet yalnızca metin döndürür; bot sağlayıcı çağırmadı ve Xu kesmedi.","chat_media_redirect_image":"🖼 AI görsellerini aç","chat_media_redirect_video":"🎬 AI videosunu aç","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: ücretsiz","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • gerçek kullanım","chat_footer_free_admin":"🆓 Ücretsiz sohbet • Owner/Admin: ücretsiz ve sınırsız","chat_footer_free_remaining":"🆓 Ücretsiz sohbet • bugün {remaining} yanıt kaldı"},
    "th": {"chat_menu_title":"แชต TOAN AAS","chat_mode_label":"โหมดปัจจุบัน","chat_mode_free":"แชตฟรี — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"ยอดคงเหลือ","chat_free_summary":"ฟรี: ตอบสำเร็จได้ 20 ครั้งต่อวันเวียดนาม ความล้มเหลวไม่ใช้โควตา","chat_pro_summary":"Pro: Opus 4.8, อินพุต/เอาต์พุต {rate}; ราคารวม ×3 คิดตามการใช้จริง และไม่จำกัดรายวันเมื่อมี Xu เพียงพอ","chat_memory_summary":"ความจำเก็บ 48 ชั่วโมงสำหรับแชตสาธารณะเท่านั้น และตอบเป็นข้อความเท่านั้น","chat_owner_admin_summary":"Owner/Admin: ฟรีและไม่จำกัด","chat_pro_enable":"💎 เปิด Chat Pro","chat_pro_disable":"⏹ ปิด Chat Pro","chat_free_label":"🆓 แชตฟรี","chat_account_label":"👤 บัญชี","chat_free_title":"แชตฟรี","chat_free_body":"Gemini 3.6 Flash; ตอบสำเร็จได้ 20 ครั้งต่อบัญชีต่อวันเวียดนาม ความล้มเหลวไม่ใช้ครั้ง ความจำแยกไว้ 48 ชั่วโมง และผลลัพธ์เป็นข้อความเท่านั้น","chat_error_quota":"⚠️ คุณใช้คำตอบแชตฟรีครบ 20 ครั้งของวันนี้แล้ว ระบบจะเปิดให้อัตโนมัติในวันเวียดนามถัดไป","chat_error_insufficient_xu":"❌ Xu ไม่พอสำหรับ Chat Pro บอตไม่ได้เรียก Opus และไม่ได้หัก Xu เพิ่มเติม","chat_error_unsupported":"⚠️ เนื้อหานี้ยังไม่รองรับในโหมดแชตที่เลือก บอตไม่ได้เรียก AI และไม่ได้หัก Xu","chat_error_duplicate":"ℹ️ ข้อความซ้ำนี้ได้รับการประมวลผลแล้ว บอตจะไม่ส่งคำตอบซ้ำ","chat_error_provider":"⚠️ AI กำลังไม่ว่างหรือไม่ส่งคำตอบที่ถูกต้อง ไม่มีการหัก Xu หรือสิทธิ์ฟรี โปรดลองใหม่ภายหลัง","chat_media_redirect_body":"การสร้างสื่อใช้บริการแยกพร้อมหน้าจอยืนยันของตนเอง แชตตอบเป็นข้อความเท่านั้น บอตไม่ได้เรียกผู้ให้บริการและไม่ได้หัก Xu","chat_media_redirect_image":"🖼 เปิดภาพ AI","chat_media_redirect_video":"🎬 เปิดวิดีโอ AI","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: ฟรี","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • การใช้จริง","chat_footer_free_admin":"🆓 แชตฟรี • Owner/Admin: ฟรีและไม่จำกัด","chat_footer_free_remaining":"🆓 แชตฟรี • เหลือ {remaining} คำตอบวันนี้"},
})


# Keep the remaining Chat root strings direct for every locale.  Values are
# presentation-only; provider and wallet terminology is intentionally absent.
_PUBLIC_CHAT_ROOT_COPY.update({
    "ja": {"chat_menu_title":"TOAN AAS チャット","chat_mode_label":"現在のモード","chat_mode_free":"無料チャット — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"残高","chat_free_summary":"無料：ベトナム日ごとに成功した返信は20回まで。失敗時は回数を消費しません。","chat_pro_summary":"Pro：Opus 4.8、入力/出力 {rate}。価格は×3込みで実利用に応じて請求され、Xuが十分なら日次上限はありません。","chat_memory_summary":"メモリは公開チャット専用で48時間保持され、返信はテキストのみです。","chat_owner_admin_summary":"Owner/Admin：無料・無制限です。","chat_pro_enable":"💎 Chat Proを有効化","chat_pro_disable":"⏹ Chat Proを無効化","chat_free_label":"🆓 無料チャット","chat_account_label":"👤 アカウント","chat_free_title":"無料チャット","chat_free_body":"Gemini 3.6 Flash。アカウントごとにベトナム日で成功した返信は20回までです。失敗時は回数を消費せず、メモリは48時間で、出力はテキストのみです。","chat_error_quota":"⚠️ 本日の無料チャット20回を使い切りました。次のベトナム日になると自動で利用できます。","chat_error_insufficient_xu":"❌ Chat Pro用のXuが不足しています。ボットはOpusを呼び出しておらず、追加のXuも引き落としていません。","chat_error_unsupported":"⚠️ 選択中のチャットモードではこの内容に対応していません。AIは呼び出されず、Xuも引き落とされません。","chat_error_duplicate":"ℹ️ 重複したメッセージはすでに処理済みです。返信は重複送信されません。","chat_error_provider":"⚠️ AIが混雑中か、有効な返信を返しませんでした。Xuまたは無料回数は消費されていません。後でもう一度お試しください。","chat_media_redirect_body":"メディア作成は確認画面を持つ別サービスで行います。チャットはテキストのみを返し、ボットはサービスを呼び出さずXuも引き落としません。","chat_media_redirect_image":"🖼 AI画像を開く","chat_media_redirect_video":"🎬 AI動画を開く","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin：無料","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • 実利用分","chat_footer_free_admin":"🆓 無料チャット • Owner/Admin：無料・無制限","chat_footer_free_remaining":"🆓 無料チャット • 本日の残り {remaining} 回"},
    "ko": {"chat_menu_title":"TOAN AAS 채팅","chat_mode_label":"현재 모드","chat_mode_free":"무료 채팅 — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"잔액","chat_free_summary":"무료: 베트남 날짜 기준 성공 답변은 하루 20회이며 실패는 할당량을 소진하지 않습니다.","chat_pro_summary":"Pro: Opus 4.8, 입력/출력 {rate}; 가격에는 ×3이 포함되며 실제 사용량으로 청구되고 Xu가 충분하면 일일 제한이 없습니다.","chat_memory_summary":"메모리는 공개 채팅에만 48시간 보관되며 답변은 텍스트만 제공합니다.","chat_owner_admin_summary":"Owner/Admin: 무료 및 무제한.","chat_pro_enable":"💎 Chat Pro 켜기","chat_pro_disable":"⏹ Chat Pro 끄기","chat_free_label":"🆓 무료 채팅","chat_account_label":"👤 계정","chat_free_title":"무료 채팅","chat_free_body":"Gemini 3.6 Flash; 계정당 베트남 날짜 기준 성공 답변은 하루 20회입니다. 실패는 횟수를 소진하지 않으며 메모리는 48시간으로 분리되고 출력은 텍스트만 제공합니다.","chat_error_quota":"⚠️ 오늘 무료 채팅 20회를 모두 사용했습니다. 다음 베트남 날짜에 자동으로 다시 열립니다.","chat_error_insufficient_xu":"❌ Chat Pro에 필요한 Xu가 부족합니다. 봇은 Opus를 호출하지 않았고 추가 Xu도 차감하지 않았습니다.","chat_error_unsupported":"⚠️ 선택한 채팅 모드에서 이 내용은 지원되지 않습니다. 봇은 AI를 호출하지 않았고 Xu도 차감하지 않았습니다.","chat_error_duplicate":"ℹ️ 중복 메시지는 이미 처리되었습니다. 봇은 답변을 두 번 보내지 않습니다.","chat_error_provider":"⚠️ AI가 바쁘거나 유효한 답변을 반환하지 않았습니다. Xu 또는 무료 횟수는 차감되지 않았습니다. 나중에 다시 시도하세요.","chat_media_redirect_body":"미디어 생성은 별도 확인 화면이 있는 서비스에서 처리됩니다. 채팅은 텍스트만 반환하며 봇은 제공업체를 호출하거나 Xu를 차감하지 않았습니다.","chat_media_redirect_image":"🖼 AI 이미지 열기","chat_media_redirect_video":"🎬 AI 동영상 열기","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: 무료","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • 실제 사용량","chat_footer_free_admin":"🆓 무료 채팅 • Owner/Admin: 무료 및 무제한","chat_footer_free_remaining":"🆓 무료 채팅 • 오늘 {remaining}회 남음"},
    "hi": {"chat_menu_title":"TOAN AAS चैट","chat_mode_label":"वर्तमान मोड","chat_mode_free":"मुफ़्त चैट — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"शेष राशि","chat_free_summary":"मुफ़्त: वियतनाम दिन में 20 सफल उत्तर; विफलता कोटा नहीं घटाती।","chat_pro_summary":"Pro: Opus 4.8, इनपुट/आउटपुट {rate}; मूल्य में ×3 शामिल है, वास्तविक उपयोग पर शुल्क है और पर्याप्त Xu होने पर दैनिक सीमा नहीं है।","chat_memory_summary":"स्मृति केवल सार्वजनिक चैट के लिए 48 घंटे रहती है; उत्तर केवल टेक्स्ट में हैं।","chat_owner_admin_summary":"Owner/Admin: मुफ़्त और असीमित।","chat_pro_enable":"💎 Chat Pro चालू करें","chat_pro_disable":"⏹ Chat Pro बंद करें","chat_free_label":"🆓 मुफ़्त चैट","chat_account_label":"👤 खाता","chat_free_title":"मुफ़्त चैट","chat_free_body":"Gemini 3.6 Flash; प्रत्येक खाते को वियतनाम दिन में 20 सफल उत्तर मिलते हैं। विफलता एक मौका नहीं घटाती, स्मृति 48 घंटे तक अलग रहती है और आउटपुट केवल टेक्स्ट है।","chat_error_quota":"⚠️ आपने आज के 20 मुफ़्त चैट उत्तर उपयोग कर लिए हैं। अगले वियतनाम दिन पर पहुंच अपने आप लौटेगी।","chat_error_insufficient_xu":"❌ Chat Pro के लिए पर्याप्त Xu नहीं है। बॉट ने Opus को कॉल नहीं किया और अतिरिक्त Xu नहीं काटे।","chat_error_unsupported":"⚠️ चुने हुए चैट मोड में यह सामग्री समर्थित नहीं है। बॉट ने AI को कॉल नहीं किया और Xu नहीं काटे।","chat_error_duplicate":"ℹ️ यह दोहराया गया संदेश पहले ही संसाधित हो चुका है; बॉट उत्तर दोबारा नहीं भेजेगा।","chat_error_provider":"⚠️ AI व्यस्त है या वैध उत्तर नहीं लौटा। कोई Xu या मुफ़्त मौका नहीं काटा गया; बाद में फिर प्रयास करें।","chat_media_redirect_body":"मीडिया निर्माण अलग पुष्टि स्क्रीन वाली सेवा से होता है। चैट केवल टेक्स्ट देता है; बॉट ने प्रदाता को कॉल नहीं किया और Xu नहीं काटे।","chat_media_redirect_image":"🖼 AI चित्र खोलें","chat_media_redirect_video":"🎬 AI वीडियो खोलें","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: मुफ़्त","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • वास्तविक उपयोग","chat_footer_free_admin":"🆓 मुफ़्त चैट • Owner/Admin: मुफ़्त और असीमित","chat_footer_free_remaining":"🆓 मुफ़्त चैट • आज {remaining} उत्तर शेष"},
    "ar": {"chat_menu_title":"دردشة TOAN AAS","chat_mode_label":"الوضع الحالي","chat_mode_free":"دردشة مجانية — Gemini","chat_mode_pro":"Chat Pro — Opus 4.8","chat_balance_label":"الرصيد","chat_free_summary":"مجاني: 20 رداً ناجحاً في اليوم الفيتنامي؛ الإخفاق لا يستهلك الحصة.","chat_pro_summary":"Pro: ‏Opus 4.8، إدخال/إخراج {rate}؛ السعر يتضمن ×3 ويُحاسب حسب الاستخدام الفعلي، ولا يوجد حد يومي عند توفر Xu.","chat_memory_summary":"تُحفظ الذاكرة لمدة 48 ساعة للدردشة العامة فقط؛ والردود نصية فقط.","chat_owner_admin_summary":"Owner/Admin: مجاني وغير محدود.","chat_pro_enable":"💎 تفعيل Chat Pro","chat_pro_disable":"⏹ إيقاف Chat Pro","chat_free_label":"🆓 دردشة مجانية","chat_account_label":"👤 الحساب","chat_free_title":"دردشة مجانية","chat_free_body":"Gemini 3.6 Flash؛ 20 رداً ناجحاً لكل حساب في اليوم الفيتنامي. الإخفاق لا يستهلك رداً، والذاكرة مستقلة لمدة 48 ساعة والمخرجات نصية فقط.","chat_error_quota":"⚠️ استخدمت كل الردود المجانية العشرين اليوم. ستعود الخدمة تلقائياً في اليوم الفيتنامي التالي.","chat_error_insufficient_xu":"❌ لا يوجد Xu كافٍ لـ Chat Pro. لم يستدعِ البوت Opus ولم يخصم Xu إضافياً.","chat_error_unsupported":"⚠️ هذا المحتوى غير مدعوم في وضع الدردشة المختار. لم يستدعِ البوت الذكاء الاصطناعي ولم يخصم Xu.","chat_error_duplicate":"ℹ️ تمت معالجة هذه الرسالة المكررة بالفعل؛ لن يرسل البوت الرد مرتين.","chat_error_provider":"⚠️ الذكاء الاصطناعي مشغول أو لم يُرجع رداً صالحاً. لم يُخصم Xu أو رد مجاني؛ حاول لاحقاً.","chat_media_redirect_body":"يستخدم إنشاء الوسائط خدمة منفصلة مع شاشة تأكيد خاصة بها. تعيد الدردشة نصاً فقط؛ لم يستدعِ البوت مزوداً ولم يخصم Xu.","chat_media_redirect_image":"🖼 فتح صور AI","chat_media_redirect_video":"🎬 فتح فيديو AI","chat_footer_pro_admin":"💎 Chat Pro • Owner/Admin: مجاني","chat_footer_pro_usage":"💎 Chat Pro • -{charged} Xu • الاستخدام الفعلي","chat_footer_free_admin":"🆓 دردشة مجانية • Owner/Admin: مجاني وغير محدود","chat_footer_free_remaining":"🆓 دردشة مجانية • متبقي {remaining} رد اليوم"},
})


# Attachment-facing Chat copy is kept separate from the root menu text.  The
# values are direct native customer text; they do not select a provider, route
# an attachment, calculate usage, or mutate quota/Xu state.
_PUBLIC_CHAT_ATTACHMENT_COPY = {
    "vi": {
        "chat_attachment_error_unsupported_type": "⚠️ Chat chưa hỗ trợ loại file này. Bot chưa tải file, chưa gọi AI và chưa trừ Xu.",
        "chat_attachment_error_unknown_size": "⚠️ Không xác minh được dung lượng file. Bot chưa tải file, chưa gọi AI và chưa trừ Xu.",
        "chat_attachment_error_size_limit": "⚠️ File vượt quá giới hạn dung lượng của Chat. Bot chưa tải file, chưa gọi AI và chưa trừ Xu.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro hiện nhận text, ảnh và PDF. Audio/video hãy dùng Chat miễn phí hoặc công cụ chuyên dụng; bot chưa trừ Xu.",
        "chat_attachment_error_invalid_file": "⚠️ Không đọc được file hợp lệ. Bot đã xóa file tạm, chưa gọi AI và chưa trừ Xu.",
        "chat_attachment_prompt_image": "Hãy phân tích ảnh này và trả lời bằng text.",
        "chat_attachment_prompt_audio": "Hãy nghe, tóm tắt audio này và trả lời bằng text.",
        "chat_attachment_prompt_video": "Hãy xem, tóm tắt video này và trả lời bằng text.",
        "chat_attachment_prompt_pdf": "Hãy đọc, tóm tắt tài liệu PDF này và trả lời bằng text.",
        "chat_attachment_prompt_text": "Hãy đọc nội dung file text này và trả lời bằng text.",
    },
    "en": {
        "chat_attachment_error_unsupported_type": "⚠️ Chat does not support this file type. The bot did not download the file, call AI, or charge Xu.",
        "chat_attachment_error_unknown_size": "⚠️ The file size could not be verified. The bot did not download the file, call AI, or charge Xu.",
        "chat_attachment_error_size_limit": "⚠️ The file exceeds the Chat size limit. The bot did not download the file, call AI, or charge Xu.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro currently accepts text, images, and PDF. For audio/video, use Free Chat or a specialized tool; no Xu was charged.",
        "chat_attachment_error_invalid_file": "⚠️ A valid file could not be read. The bot removed the temporary file, did not call AI, and did not charge Xu.",
        "chat_attachment_prompt_image": "Please analyze this image and answer in text.",
        "chat_attachment_prompt_audio": "Please listen to and summarize this audio, then answer in text.",
        "chat_attachment_prompt_video": "Please watch and summarize this video, then answer in text.",
        "chat_attachment_prompt_pdf": "Please read and summarize this PDF document, then answer in text.",
        "chat_attachment_prompt_text": "Please read the content of this text file and answer in text.",
    },
    "zh": {
        "chat_attachment_error_unsupported_type": "⚠️ 聊天暂不支持此文件类型。机器人未下载文件、未调用 AI，也未扣除 Xu。",
        "chat_attachment_error_unknown_size": "⚠️ 无法验证文件大小。机器人未下载文件、未调用 AI，也未扣除 Xu。",
        "chat_attachment_error_size_limit": "⚠️ 文件超过聊天的大小限制。机器人未下载文件、未调用 AI，也未扣除 Xu。",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro 目前支持文字、图片和 PDF。音频/视频请使用免费聊天或专业工具；未扣除 Xu。",
        "chat_attachment_error_invalid_file": "⚠️ 无法读取有效文件。机器人已删除临时文件，未调用 AI，也未扣除 Xu。",
        "chat_attachment_prompt_image": "请分析这张图片，并用文字回答。",
        "chat_attachment_prompt_audio": "请聆听并总结这段音频，然后用文字回答。",
        "chat_attachment_prompt_video": "请观看并总结这段视频，然后用文字回答。",
        "chat_attachment_prompt_pdf": "请阅读并总结这份 PDF 文档，然后用文字回答。",
        "chat_attachment_prompt_text": "请阅读此文本文件的内容，并用文字回答。",
    },
    "es": {
        "chat_attachment_error_unsupported_type": "⚠️ El chat no admite este tipo de archivo. El bot no descargó el archivo, no llamó a la IA ni cobró Xu.",
        "chat_attachment_error_unknown_size": "⚠️ No se pudo verificar el tamaño del archivo. El bot no descargó el archivo, no llamó a la IA ni cobró Xu.",
        "chat_attachment_error_size_limit": "⚠️ El archivo supera el límite de tamaño del chat. El bot no descargó el archivo, no llamó a la IA ni cobró Xu.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro acepta actualmente texto, imágenes y PDF. Para audio/vídeo, usa el Chat gratuito o una herramienta especializada; no se cobró Xu.",
        "chat_attachment_error_invalid_file": "⚠️ No se pudo leer un archivo válido. El bot eliminó el archivo temporal, no llamó a la IA ni cobró Xu.",
        "chat_attachment_prompt_image": "Analiza esta imagen y responde con texto.",
        "chat_attachment_prompt_audio": "Escucha y resume este audio, luego responde con texto.",
        "chat_attachment_prompt_video": "Mira y resume este vídeo, luego responde con texto.",
        "chat_attachment_prompt_pdf": "Lee y resume este documento PDF, luego responde con texto.",
        "chat_attachment_prompt_text": "Lee el contenido de este archivo de texto y responde con texto.",
    },
    "pt": {
        "chat_attachment_error_unsupported_type": "⚠️ O chat não oferece suporte a este tipo de arquivo. O bot não baixou o arquivo, não chamou a IA nem cobrou Xu.",
        "chat_attachment_error_unknown_size": "⚠️ Não foi possível verificar o tamanho do arquivo. O bot não baixou o arquivo, não chamou a IA nem cobrou Xu.",
        "chat_attachment_error_size_limit": "⚠️ O arquivo excede o limite de tamanho do chat. O bot não baixou o arquivo, não chamou a IA nem cobrou Xu.",
        "chat_attachment_error_pro_capability": "⚠️ O Chat Pro aceita atualmente texto, imagens e PDF. Para áudio/vídeo, use o Chat gratuito ou uma ferramenta especializada; nenhum Xu foi cobrado.",
        "chat_attachment_error_invalid_file": "⚠️ Não foi possível ler um arquivo válido. O bot removeu o arquivo temporário, não chamou a IA nem cobrou Xu.",
        "chat_attachment_prompt_image": "Analise esta imagem e responda em texto.",
        "chat_attachment_prompt_audio": "Ouça e resuma este áudio, depois responda em texto.",
        "chat_attachment_prompt_video": "Assista e resuma este vídeo, depois responda em texto.",
        "chat_attachment_prompt_pdf": "Leia e resuma este documento PDF, depois responda em texto.",
        "chat_attachment_prompt_text": "Leia o conteúdo deste arquivo de texto e responda em texto.",
    },
    "fr": {
        "chat_attachment_error_unsupported_type": "⚠️ Le chat ne prend pas en charge ce type de fichier. Le bot n’a pas téléchargé le fichier, appelé l’IA ni débité de Xu.",
        "chat_attachment_error_unknown_size": "⚠️ La taille du fichier n’a pas pu être vérifiée. Le bot n’a pas téléchargé le fichier, appelé l’IA ni débité de Xu.",
        "chat_attachment_error_size_limit": "⚠️ Le fichier dépasse la limite de taille du chat. Le bot n’a pas téléchargé le fichier, appelé l’IA ni débité de Xu.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro accepte actuellement le texte, les images et les PDF. Pour l’audio/la vidéo, utilisez le Chat gratuit ou un outil spécialisé ; aucun Xu n’a été débité.",
        "chat_attachment_error_invalid_file": "⚠️ Un fichier valide n’a pas pu être lu. Le bot a supprimé le fichier temporaire, n’a pas appelé l’IA et n’a pas débité de Xu.",
        "chat_attachment_prompt_image": "Analysez cette image et répondez par texte.",
        "chat_attachment_prompt_audio": "Écoutez et résumez cet audio, puis répondez par texte.",
        "chat_attachment_prompt_video": "Regardez et résumez cette vidéo, puis répondez par texte.",
        "chat_attachment_prompt_pdf": "Lisez et résumez ce document PDF, puis répondez par texte.",
        "chat_attachment_prompt_text": "Lisez le contenu de ce fichier texte et répondez par texte.",
    },
    "de": {
        "chat_attachment_error_unsupported_type": "⚠️ Der Chat unterstützt diesen Dateityp nicht. Der Bot hat die Datei nicht heruntergeladen, keine KI aufgerufen und keine Xu berechnet.",
        "chat_attachment_error_unknown_size": "⚠️ Die Dateigröße konnte nicht geprüft werden. Der Bot hat die Datei nicht heruntergeladen, keine KI aufgerufen und keine Xu berechnet.",
        "chat_attachment_error_size_limit": "⚠️ Die Datei überschreitet das Größenlimit des Chats. Der Bot hat die Datei nicht heruntergeladen, keine KI aufgerufen und keine Xu berechnet.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro akzeptiert derzeit Text, Bilder und PDF. Für Audio/Video nutze den kostenlosen Chat oder ein Spezialwerkzeug; es wurden keine Xu berechnet.",
        "chat_attachment_error_invalid_file": "⚠️ Eine gültige Datei konnte nicht gelesen werden. Der Bot hat die temporäre Datei entfernt, keine KI aufgerufen und keine Xu berechnet.",
        "chat_attachment_prompt_image": "Analysiere dieses Bild und antworte als Text.",
        "chat_attachment_prompt_audio": "Höre dir dieses Audio an, fasse es zusammen und antworte als Text.",
        "chat_attachment_prompt_video": "Sieh dir dieses Video an, fasse es zusammen und antworte als Text.",
        "chat_attachment_prompt_pdf": "Lies dieses PDF-Dokument, fasse es zusammen und antworte als Text.",
        "chat_attachment_prompt_text": "Lies den Inhalt dieser Textdatei und antworte als Text.",
    },
    "ja": {
        "chat_attachment_error_unsupported_type": "⚠️ このファイル形式はチャットでサポートされていません。ボットはファイルをダウンロードせず、AI を呼び出さず、Xu も引き落としていません。",
        "chat_attachment_error_unknown_size": "⚠️ ファイルサイズを確認できませんでした。ボットはファイルをダウンロードせず、AI を呼び出さず、Xu も引き落としていません。",
        "chat_attachment_error_size_limit": "⚠️ ファイルがチャットのサイズ上限を超えています。ボットはファイルをダウンロードせず、AI を呼び出さず、Xu も引き落としていません。",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro は現在、テキスト・画像・PDF に対応しています。音声/動画は無料チャットまたは専用ツールをご利用ください。Xu は引き落とされていません。",
        "chat_attachment_error_invalid_file": "⚠️ 有効なファイルを読み取れませんでした。ボットは一時ファイルを削除し、AI を呼び出さず、Xu も引き落としていません。",
        "chat_attachment_prompt_image": "この画像を分析し、テキストで回答してください。",
        "chat_attachment_prompt_audio": "この音声を聞いて要約し、テキストで回答してください。",
        "chat_attachment_prompt_video": "この動画を視聴して要約し、テキストで回答してください。",
        "chat_attachment_prompt_pdf": "この PDF 文書を読んで要約し、テキストで回答してください。",
        "chat_attachment_prompt_text": "このテキストファイルの内容を読み、テキストで回答してください。",
    },
    "ko": {
        "chat_attachment_error_unsupported_type": "⚠️ 채팅에서 이 파일 형식은 지원되지 않습니다. 봇은 파일을 다운로드하거나 AI를 호출하거나 Xu를 차감하지 않았습니다.",
        "chat_attachment_error_unknown_size": "⚠️ 파일 크기를 확인할 수 없습니다. 봇은 파일을 다운로드하거나 AI를 호출하거나 Xu를 차감하지 않았습니다.",
        "chat_attachment_error_size_limit": "⚠️ 파일이 채팅의 크기 제한을 초과했습니다. 봇은 파일을 다운로드하거나 AI를 호출하거나 Xu를 차감하지 않았습니다.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro는 현재 텍스트, 이미지, PDF를 지원합니다. 오디오/비디오는 무료 채팅 또는 전문 도구를 사용하세요. Xu는 차감되지 않았습니다.",
        "chat_attachment_error_invalid_file": "⚠️ 유효한 파일을 읽을 수 없습니다. 봇은 임시 파일을 삭제했으며 AI를 호출하거나 Xu를 차감하지 않았습니다.",
        "chat_attachment_prompt_image": "이 이미지를 분석하고 텍스트로 답변하세요.",
        "chat_attachment_prompt_audio": "이 오디오를 듣고 요약한 뒤 텍스트로 답변하세요.",
        "chat_attachment_prompt_video": "이 비디오를 보고 요약한 뒤 텍스트로 답변하세요.",
        "chat_attachment_prompt_pdf": "이 PDF 문서를 읽고 요약한 뒤 텍스트로 답변하세요.",
        "chat_attachment_prompt_text": "이 텍스트 파일의 내용을 읽고 텍스트로 답변하세요.",
    },
    "hi": {
        "chat_attachment_error_unsupported_type": "⚠️ चैट इस प्रकार की फ़ाइल का समर्थन नहीं करता। बॉट ने फ़ाइल डाउनलोड नहीं की, AI को कॉल नहीं किया और Xu नहीं काटे।",
        "chat_attachment_error_unknown_size": "⚠️ फ़ाइल का आकार सत्यापित नहीं किया जा सका। बॉट ने फ़ाइल डाउनलोड नहीं की, AI को कॉल नहीं किया और Xu नहीं काटे।",
        "chat_attachment_error_size_limit": "⚠️ फ़ाइल चैट की आकार सीमा से बड़ी है। बॉट ने फ़ाइल डाउनलोड नहीं की, AI को कॉल नहीं किया और Xu नहीं काटे।",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro अभी टेक्स्ट, चित्र और PDF स्वीकार करता है। ऑडियो/वीडियो के लिए मुफ़्त चैट या विशेष टूल का उपयोग करें; कोई Xu नहीं काटे गए।",
        "chat_attachment_error_invalid_file": "⚠️ मान्य फ़ाइल पढ़ी नहीं जा सकी। बॉट ने अस्थायी फ़ाइल हटा दी, AI को कॉल नहीं किया और Xu नहीं काटे।",
        "chat_attachment_prompt_image": "इस चित्र का विश्लेषण करें और टेक्स्ट में उत्तर दें।",
        "chat_attachment_prompt_audio": "इस ऑडियो को सुनें, उसका सार दें और टेक्स्ट में उत्तर दें।",
        "chat_attachment_prompt_video": "इस वीडियो को देखें, उसका सार दें और टेक्स्ट में उत्तर दें।",
        "chat_attachment_prompt_pdf": "इस PDF दस्तावेज़ को पढ़ें, उसका सार दें और टेक्स्ट में उत्तर दें।",
        "chat_attachment_prompt_text": "इस टेक्स्ट फ़ाइल की सामग्री पढ़ें और टेक्स्ट में उत्तर दें।",
    },
    "ar": {
        "chat_attachment_error_unsupported_type": "⚠️ الدردشة لا تدعم هذا النوع من الملفات. لم ينزّل البوت الملف ولم يستدعِ الذكاء الاصطناعي ولم يخصم Xu.",
        "chat_attachment_error_unknown_size": "⚠️ تعذّر التحقق من حجم الملف. لم ينزّل البوت الملف ولم يستدعِ الذكاء الاصطناعي ولم يخصم Xu.",
        "chat_attachment_error_size_limit": "⚠️ يتجاوز الملف حدّ الحجم في الدردشة. لم ينزّل البوت الملف ولم يستدعِ الذكاء الاصطناعي ولم يخصم Xu.",
        "chat_attachment_error_pro_capability": "⚠️ يقبل Chat Pro حالياً النصوص والصور وملفات PDF. للصوت/الفيديو استخدم الدردشة المجانية أو أداة متخصصة؛ لم يُخصم Xu.",
        "chat_attachment_error_invalid_file": "⚠️ تعذّرت قراءة ملف صالح. حذف البوت الملف المؤقت ولم يستدعِ الذكاء الاصطناعي ولم يخصم Xu.",
        "chat_attachment_prompt_image": "حلّل هذه الصورة وأجب بنص.",
        "chat_attachment_prompt_audio": "استمع إلى هذا الصوت ولخّصه ثم أجب بنص.",
        "chat_attachment_prompt_video": "شاهد هذا الفيديو ولخّصه ثم أجب بنص.",
        "chat_attachment_prompt_pdf": "اقرأ مستند PDF هذا ولخّصه ثم أجب بنص.",
        "chat_attachment_prompt_text": "اقرأ محتوى هذا الملف النصي وأجب بنص.",
    },
    "ru": {
        "chat_attachment_error_unsupported_type": "⚠️ Чат не поддерживает этот тип файла. Бот не скачивал файл, не вызывал ИИ и не списывал Xu.",
        "chat_attachment_error_unknown_size": "⚠️ Не удалось проверить размер файла. Бот не скачивал файл, не вызывал ИИ и не списывал Xu.",
        "chat_attachment_error_size_limit": "⚠️ Файл превышает лимит размера для чата. Бот не скачивал файл, не вызывал ИИ и не списывал Xu.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro сейчас принимает текст, изображения и PDF. Для аудио/видео используйте бесплатный чат или специальный инструмент; Xu не списаны.",
        "chat_attachment_error_invalid_file": "⚠️ Не удалось прочитать корректный файл. Бот удалил временный файл, не вызывал ИИ и не списывал Xu.",
        "chat_attachment_prompt_image": "Проанализируйте это изображение и ответьте текстом.",
        "chat_attachment_prompt_audio": "Прослушайте и кратко изложите это аудио, затем ответьте текстом.",
        "chat_attachment_prompt_video": "Просмотрите и кратко изложите это видео, затем ответьте текстом.",
        "chat_attachment_prompt_pdf": "Прочитайте и кратко изложите этот PDF-документ, затем ответьте текстом.",
        "chat_attachment_prompt_text": "Прочитайте содержимое этого текстового файла и ответьте текстом.",
    },
    "tr": {
        "chat_attachment_error_unsupported_type": "⚠️ Sohbet bu dosya türünü desteklemiyor. Bot dosyayı indirmedi, AI'ı çağırmadı ve Xu kesmedi.",
        "chat_attachment_error_unknown_size": "⚠️ Dosya boyutu doğrulanamadı. Bot dosyayı indirmedi, AI'ı çağırmadı ve Xu kesmedi.",
        "chat_attachment_error_size_limit": "⚠️ Dosya sohbet boyut sınırını aşıyor. Bot dosyayı indirmedi, AI'ı çağırmadı ve Xu kesmedi.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro şu anda metin, görsel ve PDF kabul ediyor. Ses/video için ücretsiz sohbeti veya özel bir aracı kullanın; Xu kesilmedi.",
        "chat_attachment_error_invalid_file": "⚠️ Geçerli bir dosya okunamadı. Bot geçici dosyayı sildi, AI'ı çağırmadı ve Xu kesmedi.",
        "chat_attachment_prompt_image": "Bu görseli analiz edin ve metin olarak yanıtlayın.",
        "chat_attachment_prompt_audio": "Bu sesi dinleyin, özetleyin ve metin olarak yanıtlayın.",
        "chat_attachment_prompt_video": "Bu videoyu izleyin, özetleyin ve metin olarak yanıtlayın.",
        "chat_attachment_prompt_pdf": "Bu PDF belgesini okuyun, özetleyin ve metin olarak yanıtlayın.",
        "chat_attachment_prompt_text": "Bu metin dosyasının içeriğini okuyun ve metin olarak yanıtlayın.",
    },
    "th": {
        "chat_attachment_error_unsupported_type": "⚠️ แชตไม่รองรับไฟล์ประเภทนี้ บอตยังไม่ได้ดาวน์โหลดไฟล์ เรียก AI หรือหัก Xu",
        "chat_attachment_error_unknown_size": "⚠️ ไม่สามารถตรวจสอบขนาดไฟล์ได้ บอตยังไม่ได้ดาวน์โหลดไฟล์ เรียก AI หรือหัก Xu",
        "chat_attachment_error_size_limit": "⚠️ ไฟล์เกินขีดจำกัดขนาดของแชต บอตยังไม่ได้ดาวน์โหลดไฟล์ เรียก AI หรือหัก Xu",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro รองรับข้อความ รูปภาพ และ PDF ในขณะนี้ สำหรับเสียง/วิดีโอให้ใช้แชตฟรีหรือเครื่องมือเฉพาะทาง โดยไม่มีการหัก Xu",
        "chat_attachment_error_invalid_file": "⚠️ ไม่สามารถอ่านไฟล์ที่ถูกต้องได้ บอตลบไฟล์ชั่วคราวแล้ว และยังไม่ได้เรียก AI หรือหัก Xu",
        "chat_attachment_prompt_image": "โปรดวิเคราะห์ภาพนี้และตอบเป็นข้อความ",
        "chat_attachment_prompt_audio": "โปรดฟังและสรุปเสียงนี้ แล้วตอบเป็นข้อความ",
        "chat_attachment_prompt_video": "โปรดดูและสรุปวิดีโอนี้ แล้วตอบเป็นข้อความ",
        "chat_attachment_prompt_pdf": "โปรดอ่านและสรุปเอกสาร PDF นี้ แล้วตอบเป็นข้อความ",
        "chat_attachment_prompt_text": "โปรดอ่านเนื้อหาในไฟล์ข้อความนี้และตอบเป็นข้อความ",
    },
    "fil": {
        "chat_attachment_error_unsupported_type": "⚠️ Hindi sinusuportahan ng chat ang uri ng file na ito. Hindi dinownload ng bot ang file, hindi tumawag sa AI, at walang Xu na nabawas.",
        "chat_attachment_error_unknown_size": "⚠️ Hindi ma-verify ang laki ng file. Hindi dinownload ng bot ang file, hindi tumawag sa AI, at walang Xu na nabawas.",
        "chat_attachment_error_size_limit": "⚠️ Lumampas ang file sa limitasyon ng laki ng chat. Hindi dinownload ng bot ang file, hindi tumawag sa AI, at walang Xu na nabawas.",
        "chat_attachment_error_pro_capability": "⚠️ Tumatanggap ang Chat Pro ng text, mga larawan, at PDF sa ngayon. Para sa audio/video, gamitin ang Libreng chat o espesyal na tool; walang Xu na nabawas.",
        "chat_attachment_error_invalid_file": "⚠️ Hindi mabasa ang isang wastong file. Inalis ng bot ang pansamantalang file, hindi tumawag sa AI, at walang Xu na nabawas.",
        "chat_attachment_prompt_image": "Suriin ang larawang ito at sumagot gamit ang text.",
        "chat_attachment_prompt_audio": "Pakinggan at ibuod ang audio na ito, pagkatapos ay sumagot gamit ang text.",
        "chat_attachment_prompt_video": "Panoorin at ibuod ang video na ito, pagkatapos ay sumagot gamit ang text.",
        "chat_attachment_prompt_pdf": "Basahin at ibuod ang dokumentong PDF na ito, pagkatapos ay sumagot gamit ang text.",
        "chat_attachment_prompt_text": "Basahin ang nilalaman ng text file na ito at sumagot gamit ang text.",
    },
    "it": {
        "chat_attachment_error_unsupported_type": "⚠️ La chat non supporta questo tipo di file. Il bot non ha scaricato il file, chiamato l’IA né addebitato Xu.",
        "chat_attachment_error_unknown_size": "⚠️ Non è stato possibile verificare la dimensione del file. Il bot non ha scaricato il file, chiamato l’IA né addebitato Xu.",
        "chat_attachment_error_size_limit": "⚠️ Il file supera il limite di dimensione della chat. Il bot non ha scaricato il file, chiamato l’IA né addebitato Xu.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro accetta attualmente testo, immagini e PDF. Per audio/video usa la chat gratuita o uno strumento specializzato; nessun Xu è stato addebitato.",
        "chat_attachment_error_invalid_file": "⚠️ Non è stato possibile leggere un file valido. Il bot ha rimosso il file temporaneo, non ha chiamato l’IA né addebitato Xu.",
        "chat_attachment_prompt_image": "Analizza questa immagine e rispondi in testo.",
        "chat_attachment_prompt_audio": "Ascolta e riassumi questo audio, poi rispondi in testo.",
        "chat_attachment_prompt_video": "Guarda e riassumi questo video, poi rispondi in testo.",
        "chat_attachment_prompt_pdf": "Leggi e riassumi questo documento PDF, poi rispondi in testo.",
        "chat_attachment_prompt_text": "Leggi il contenuto di questo file di testo e rispondi in testo.",
    },
    "id": {
        "chat_attachment_error_unsupported_type": "⚠️ Chat tidak mendukung jenis file ini. Bot tidak mengunduh file, memanggil AI, atau memotong Xu.",
        "chat_attachment_error_unknown_size": "⚠️ Ukuran file tidak dapat diverifikasi. Bot tidak mengunduh file, memanggil AI, atau memotong Xu.",
        "chat_attachment_error_size_limit": "⚠️ File melebihi batas ukuran Chat. Bot tidak mengunduh file, memanggil AI, atau memotong Xu.",
        "chat_attachment_error_pro_capability": "⚠️ Chat Pro saat ini menerima teks, gambar, dan PDF. Untuk audio/video, gunakan Chat gratis atau alat khusus; tidak ada Xu yang dipotong.",
        "chat_attachment_error_invalid_file": "⚠️ File yang valid tidak dapat dibaca. Bot menghapus file sementara, tidak memanggil AI, dan tidak memotong Xu.",
        "chat_attachment_prompt_image": "Analisis gambar ini dan jawab dalam teks.",
        "chat_attachment_prompt_audio": "Dengarkan dan rangkum audio ini, lalu jawab dalam teks.",
        "chat_attachment_prompt_video": "Tonton dan rangkum video ini, lalu jawab dalam teks.",
        "chat_attachment_prompt_pdf": "Baca dan rangkum dokumen PDF ini, lalu jawab dalam teks.",
        "chat_attachment_prompt_text": "Baca isi file teks ini dan jawab dalam teks.",
    },
}


# Root-screen copy follows the English semantic baseline but is stored as
# direct native customer copy. It never controls a route, provider, payment,
# price, account state, or feature availability.
_PUBLIC_ROOT_SCREEN_COPY = {
    "en": {
        "free_title": "TOAN AAS Free tools", "free_body": "Use zero-Xu helpers to prepare content, prompts, notes and drafts before paid tools. Real creation always shows a quote and asks for confirmation before Xu is charged.",
        "audio_title": "Audio Studio", "audio_body": "Choose the kind of audio you want to create. This studio creates a separate audio file and is not attached to the current video.",
        "audio_voice": "Voice", "audio_music": "Music", "back_main": "Back", "main_menu_label": "Main menu",
        "feedback_title": "Feedback / Report a bug", "feedback_body": "Choose the issue you want to report. Payment, media, document and refund issues create a ticket for admin review.",
        "support_title": "TOAN AAS Support", "support_body": "Contact the team, create a support ticket, review your tickets, or request advice. Do not send passwords, OTPs, private codes, or card information.",
        "support_admin": "Message admin", "support_ticket": "Create support ticket", "support_my_tickets": "My tickets", "support_auto": "Automated support",
    },
    "vi": {
        "free_title": "Công cụ miễn phí TOAN AAS", "free_body": "Dùng các công cụ 0 Xu để chuẩn bị nội dung, prompt, ghi chú và bản nháp trước khi dùng công cụ trả phí. Tác vụ tạo thật luôn báo giá và hỏi xác nhận trước khi trừ Xu.",
        "audio_title": "Studio âm thanh", "audio_body": "Chọn loại âm thanh bạn muốn tạo. Studio này tạo file âm thanh riêng và không gắn vào video hiện tại.",
        "audio_voice": "Giọng đọc", "audio_music": "Nhạc", "back_main": "Quay lại", "main_menu_label": "Menu chính",
        "feedback_title": "Góp ý / Báo lỗi", "feedback_body": "Chọn vấn đề bạn muốn báo. Vấn đề thanh toán, media, tài liệu hoặc hoàn Xu sẽ tạo ticket để admin kiểm tra.",
        "support_title": "Hỗ trợ TOAN AAS", "support_body": "Liên hệ đội ngũ, tạo ticket hỗ trợ, xem ticket của bạn hoặc yêu cầu tư vấn. Không gửi mật khẩu, OTP, mã riêng tư hay thông tin thẻ.",
        "support_admin": "Nhắn admin", "support_ticket": "Tạo ticket hỗ trợ", "support_my_tickets": "Ticket của tôi", "support_auto": "CSKH tự động",
    },
    "zh": {
        "free_title": "TOAN AAS 免费工具", "free_body": "先使用 0 Xu 工具准备内容、提示词、笔记和草稿，再使用付费工具。真实生成前会显示报价并要求确认后才扣除 Xu。",
        "audio_title": "音频工作室", "audio_body": "请选择要创建的音频类型。本工作室会创建独立音频文件，不会附加到当前视频。",
        "audio_voice": "语音", "audio_music": "音乐", "back_main": "返回", "main_menu_label": "主菜单",
        "feedback_title": "反馈 / 报错", "feedback_body": "请选择要报告的问题。付款、媒体、文档和退款问题会创建工单供管理员核查。",
        "support_title": "TOAN AAS 支持", "support_body": "联系团队、创建支持工单、查看您的工单或请求咨询。请勿发送密码、验证码、私密代码或银行卡信息。",
        "support_admin": "联系管理员", "support_ticket": "创建支持工单", "support_my_tickets": "我的工单", "support_auto": "自动客服",
    },
    "es": {"free_title": "Herramientas gratuitas de TOAN AAS", "free_body": "Usa herramientas de 0 Xu para preparar contenido, prompts, notas y borradores antes de las herramientas de pago. La creación real siempre muestra el precio y pide confirmación antes de cobrar Xu.", "audio_title": "Estudio de audio", "audio_body": "Elige el tipo de audio que deseas crear. Este estudio crea un archivo de audio independiente y no se adjunta al vídeo actual.", "audio_voice": "Voz", "audio_music": "Música", "back_main": "Volver", "main_menu_label": "Menú principal", "feedback_title": "Opiniones / Informar de un error", "feedback_body": "Elige el problema que quieres informar. Los problemas de pago, medios, documentos y reembolsos crean un ticket para la revisión del administrador."},
    "pt": {"free_title": "Ferramentas gratuitas do TOAN AAS", "free_body": "Use ferramentas de 0 Xu para preparar conteúdo, prompts, notas e rascunhos antes das ferramentas pagas. A criação real sempre mostra o preço e pede confirmação antes de cobrar Xu.", "audio_title": "Estúdio de áudio", "audio_body": "Escolha o tipo de áudio que deseja criar. Este estúdio cria um arquivo de áudio separado e não o anexa ao vídeo atual.", "audio_voice": "Voz", "audio_music": "Música", "back_main": "Voltar", "main_menu_label": "Menu principal", "feedback_title": "Comentários / Reportar erro", "feedback_body": "Escolha o problema que deseja informar. Problemas de pagamento, mídia, documentos e reembolso criam um ticket para análise do administrador."},
    "fr": {"free_title": "Outils gratuits TOAN AAS", "free_body": "Utilisez des outils à 0 Xu pour préparer du contenu, des prompts, des notes et des brouillons avant les outils payants. Toute création réelle affiche le tarif et demande confirmation avant de débiter des Xu.", "audio_title": "Studio audio", "audio_body": "Choisissez le type d’audio à créer. Ce studio crée un fichier audio indépendant, non joint à la vidéo en cours.", "audio_voice": "Voix", "audio_music": "Musique", "back_main": "Retour", "main_menu_label": "Menu principal", "feedback_title": "Avis / Signaler un bug", "feedback_body": "Choisissez le problème à signaler. Les problèmes de paiement, média, document ou remboursement créent un ticket pour examen par un administrateur."},
    "de": {"free_title": "Kostenlose TOAN-AAS-Tools", "free_body": "Nutze 0-Xu-Tools, um Inhalte, Prompts, Notizen und Entwürfe vor kostenpflichtigen Tools vorzubereiten. Echte Erstellung zeigt immer den Preis und fragt vor der Xu-Belastung nach einer Bestätigung.", "audio_title": "Audiostudio", "audio_body": "Wähle die Audioart aus, die du erstellen möchtest. Dieses Studio erstellt eine separate Audiodatei und hängt sie nicht an das aktuelle Video an.", "audio_voice": "Stimme", "audio_music": "Musik", "back_main": "Zurück", "main_menu_label": "Hauptmenü", "feedback_title": "Feedback / Fehler melden", "feedback_body": "Wähle das Problem aus, das du melden möchtest. Zahlungs-, Medien-, Dokument- und Erstattungsprobleme erstellen ein Ticket für die Admin-Prüfung."},
    "ja": {"free_title": "TOAN AAS 無料ツール", "free_body": "有料ツールの前に、0 Xu のツールでコンテンツ、プロンプト、メモ、下書きを準備できます。実際の作成では必ず料金が表示され、Xu を引き落とす前に確認を求めます。", "audio_title": "オーディオスタジオ", "audio_body": "作成する音声の種類を選択してください。このスタジオは独立した音声ファイルを作成し、現在の動画には添付しません。", "audio_voice": "音声", "audio_music": "音楽", "back_main": "戻る", "main_menu_label": "メインメニュー", "feedback_title": "ご意見 / 不具合を報告", "feedback_body": "報告する問題を選択してください。支払い、メディア、文書、返金に関する問題は管理者確認用のチケットを作成します。"},
    "ko": {"free_title": "TOAN AAS 무료 도구", "free_body": "유료 도구를 사용하기 전에 0 Xu 도구로 콘텐츠, 프롬프트, 메모와 초안을 준비하세요. 실제 생성은 항상 가격을 보여 주고 Xu를 차감하기 전에 확인을 요청합니다.", "audio_title": "오디오 스튜디오", "audio_body": "만들고 싶은 오디오 종류를 선택하세요. 이 스튜디오는 별도의 오디오 파일을 만들며 현재 동영상에 연결되지 않습니다.", "audio_voice": "음성", "audio_music": "음악", "back_main": "뒤로", "main_menu_label": "메인 메뉴", "feedback_title": "의견 / 오류 신고", "feedback_body": "신고할 문제를 선택하세요. 결제, 미디어, 문서, 환불 문제는 관리자가 검토할 수 있도록 티켓을 만듭니다."},
    "hi": {"free_title": "TOAN AAS के निःशुल्क उपकरण", "free_body": "सशुल्क उपकरणों से पहले सामग्री, प्रॉम्प्ट, नोट्स और ड्राफ़्ट तैयार करने के लिए 0 Xu उपकरणों का उपयोग करें। वास्तविक निर्माण से पहले मूल्य दिखाया जाता है और Xu काटने से पहले पुष्टि ली जाती है।", "audio_title": "ऑडियो स्टूडियो", "audio_body": "वह ऑडियो प्रकार चुनें जिसे आप बनाना चाहते हैं। यह स्टूडियो अलग ऑडियो फ़ाइल बनाता है और उसे वर्तमान वीडियो से नहीं जोड़ता।", "audio_voice": "आवाज़", "audio_music": "संगीत", "back_main": "वापस", "main_menu_label": "मुख्य मेनू", "feedback_title": "सुझाव / त्रुटि रिपोर्ट", "feedback_body": "जिस समस्या की रिपोर्ट करनी है उसे चुनें। भुगतान, मीडिया, दस्तावेज़ और रिफंड की समस्याओं के लिए एडमिन समीक्षा का टिकट बनाया जाता है।"},
    "ar": {"free_title": "أدوات TOAN AAS المجانية", "free_body": "استخدم أدوات 0 Xu لإعداد المحتوى والمطالبات والملاحظات والمسودات قبل الأدوات المدفوعة. تعرض عمليات الإنشاء الفعلية السعر دائمًا وتطلب التأكيد قبل خصم Xu.", "audio_title": "استوديو الصوت", "audio_body": "اختر نوع الصوت الذي تريد إنشاءه. ينشئ هذا الاستوديو ملفًا صوتيًا منفصلًا ولا يربطه بالفيديو الحالي.", "audio_voice": "الصوت", "audio_music": "الموسيقى", "back_main": "رجوع", "main_menu_label": "القائمة الرئيسية", "feedback_title": "ملاحظات / بلاغ خطأ", "feedback_body": "اختر المشكلة التي تريد الإبلاغ عنها. تنشئ مشكلات الدفع والوسائط والمستندات والاسترداد تذكرة لمراجعة المشرف."},
    "ru": {"free_title": "Бесплатные инструменты TOAN AAS", "free_body": "Используйте инструменты за 0 Xu, чтобы подготовить контент, промпты, заметки и черновики перед платными инструментами. Перед реальным созданием всегда показывается цена и запрашивается подтверждение списания Xu.", "audio_title": "Аудиостудия", "audio_body": "Выберите тип аудио, который хотите создать. Эта студия создаёт отдельный аудиофайл и не прикрепляет его к текущему видео.", "audio_voice": "Голос", "audio_music": "Музыка", "back_main": "Назад", "main_menu_label": "Главное меню", "feedback_title": "Отзыв / Сообщить об ошибке", "feedback_body": "Выберите проблему, о которой хотите сообщить. Проблемы с оплатой, медиа, документами и возвратом создают тикет для проверки администратором."},
    "tr": {"free_title": "Ücretsiz TOAN AAS araçları", "free_body": "Ücretli araçlardan önce içerik, istem, not ve taslak hazırlamak için 0 Xu araçlarını kullanın. Gerçek oluşturma her zaman fiyatı gösterir ve Xu kesilmeden önce onay ister.", "audio_title": "Ses stüdyosu", "audio_body": "Oluşturmak istediğiniz ses türünü seçin. Bu stüdyo ayrı bir ses dosyası oluşturur ve mevcut videoya eklemez.", "audio_voice": "Ses", "audio_music": "Müzik", "back_main": "Geri", "main_menu_label": "Ana menü", "feedback_title": "Geri bildirim / Hata bildir", "feedback_body": "Bildirmek istediğiniz sorunu seçin. Ödeme, medya, belge ve iade sorunları yönetici incelemesi için bir talep oluşturur."},
    "th": {"free_title": "เครื่องมือฟรี TOAN AAS", "free_body": "ใช้เครื่องมือ 0 Xu เพื่อเตรียมเนื้อหา พรอมต์ บันทึก และร่างงานก่อนใช้เครื่องมือแบบชำระเงิน การสร้างงานจริงจะแสดงราคาและขอการยืนยันก่อนหัก Xu เสมอ", "audio_title": "สตูดิโอเสียง", "audio_body": "เลือกประเภทเสียงที่ต้องการสร้าง สตูดิโอนี้สร้างไฟล์เสียงแยกต่างหากและไม่ผูกกับวิดีโอปัจจุบัน", "audio_voice": "เสียง", "audio_music": "เพลง", "back_main": "ย้อนกลับ", "main_menu_label": "เมนูหลัก", "feedback_title": "ข้อเสนอแนะ / แจ้งข้อผิดพลาด", "feedback_body": "เลือกปัญหาที่ต้องการแจ้ง ปัญหาการชำระเงิน สื่อ เอกสาร และการคืนเงินจะสร้างทิกเก็ตให้ผู้ดูแลตรวจสอบ"},
    "fil": {"free_title": "Libreng tool ng TOAN AAS", "free_body": "Gumamit ng mga tool na 0 Xu upang maghanda ng nilalaman, prompt, tala at draft bago ang mga bayad na tool. Laging ipinapakita ang presyo at hinihingi ang kumpirmasyon bago kaltasin ang Xu sa tunay na paggawa.", "audio_title": "Studio ng audio", "audio_body": "Piliin ang uri ng audio na gusto mong likhain. Gumagawa ang studio na ito ng hiwalay na audio file at hindi ito ikinakabit sa kasalukuyang video.", "audio_voice": "Boses", "audio_music": "Musika", "back_main": "Bumalik", "main_menu_label": "Pangunahing menu", "feedback_title": "Puna / Mag-ulat ng bug", "feedback_body": "Piliin ang problemang nais mong iulat. Ang mga isyu sa bayad, media, dokumento at refund ay gagawa ng ticket para sa pagsusuri ng admin."},
    "it": {"free_title": "Strumenti gratuiti TOAN AAS", "free_body": "Usa strumenti da 0 Xu per preparare contenuti, prompt, note e bozze prima degli strumenti a pagamento. La creazione reale mostra sempre il prezzo e chiede conferma prima di addebitare Xu.", "audio_title": "Studio audio", "audio_body": "Scegli il tipo di audio da creare. Questo studio crea un file audio separato e non lo collega al video corrente.", "audio_voice": "Voce", "audio_music": "Musica", "back_main": "Indietro", "main_menu_label": "Menu principale", "feedback_title": "Feedback / Segnala un errore", "feedback_body": "Scegli il problema da segnalare. I problemi di pagamento, media, documenti e rimborso creano un ticket per la revisione dell’amministratore."},
    "id": {"free_title": "Alat gratis TOAN AAS", "free_body": "Gunakan alat 0 Xu untuk menyiapkan konten, prompt, catatan, dan draf sebelum memakai alat berbayar. Pembuatan nyata selalu menampilkan harga dan meminta konfirmasi sebelum Xu dipotong.", "audio_title": "Studio audio", "audio_body": "Pilih jenis audio yang ingin dibuat. Studio ini membuat file audio terpisah dan tidak mengaitkannya dengan video saat ini.", "audio_voice": "Suara", "audio_music": "Musik", "back_main": "Kembali", "main_menu_label": "Menu utama", "feedback_title": "Masukan / Laporkan bug", "feedback_body": "Pilih masalah yang ingin dilaporkan. Masalah pembayaran, media, dokumen, dan pengembalian dana membuat tiket untuk ditinjau admin."},
}


# Free Tools root-menu labels are presentation-only.  The callbacks remain
# stable in bot.py; this table prevents every non-Vietnamese customer locale
# from silently falling back to the English menu.
_PUBLIC_FREE_HUB_ROOT_COPY = {
    "vi": {
        "freehub_enable_ai_chatbot": "Bật AI Chatbot", "freehub_meta": "Prompt Meta AI",
        "freehub_caption": "Caption / Hashtag", "freehub_ideas": "Ý tưởng nội dung",
        "freehub_prompts": "Prompt ảnh / video", "freehub_library": "Kho prompt mẫu",
        "freehub_publish_package": "Gói đăng bài", "freehub_notes_docs": "Ghi chú / Tài liệu",
        "freehub_save_temp_media": "Lưu media tạm", "freehub_voice_subdub_script": "Kịch bản voice / SubDub",
        "freehub_music_sfx_ideas": "Ý tưởng nhạc / SFX",
    },
    "en": {
        "freehub_enable_ai_chatbot": "Enable AI Chatbot", "freehub_meta": "Meta AI prompt",
        "freehub_caption": "Caption / hashtags", "freehub_ideas": "Content ideas",
        "freehub_prompts": "Image / video prompts", "freehub_library": "Prompt library",
        "freehub_publish_package": "Publish package", "freehub_notes_docs": "Notes / Documents",
        "freehub_save_temp_media": "Save temporary media", "freehub_voice_subdub_script": "Voice / SubDub script",
        "freehub_music_sfx_ideas": "Music / SFX ideas",
    },
    "zh": {
        "freehub_enable_ai_chatbot": "启用 AI 聊天机器人", "freehub_meta": "Meta AI 提示词",
        "freehub_caption": "文案 / 话题标签", "freehub_ideas": "内容创意",
        "freehub_prompts": "图片 / 视频提示词", "freehub_library": "提示词库",
        "freehub_publish_package": "发布内容包", "freehub_notes_docs": "笔记 / 文档",
        "freehub_save_temp_media": "保存临时媒体", "freehub_voice_subdub_script": "语音 / SubDub 脚本",
        "freehub_music_sfx_ideas": "音乐 / 音效创意",
    },
    "es": {
        "freehub_enable_ai_chatbot": "Activar chatbot de IA", "freehub_meta": "Prompt para Meta AI",
        "freehub_caption": "Texto / hashtags", "freehub_ideas": "Ideas de contenido",
        "freehub_prompts": "Prompts de imagen / vídeo", "freehub_library": "Biblioteca de prompts",
        "freehub_publish_package": "Paquete para publicar", "freehub_notes_docs": "Notas / Documentos",
        "freehub_save_temp_media": "Guardar medios temporales", "freehub_voice_subdub_script": "Guion de voz / SubDub",
        "freehub_music_sfx_ideas": "Ideas de música / efectos",
    },
    "pt": {
        "freehub_enable_ai_chatbot": "Ativar chatbot de IA", "freehub_meta": "Prompt para Meta AI",
        "freehub_caption": "Legenda / hashtags", "freehub_ideas": "Ideias de conteúdo",
        "freehub_prompts": "Prompts de imagem / vídeo", "freehub_library": "Biblioteca de prompts",
        "freehub_publish_package": "Pacote de publicação", "freehub_notes_docs": "Notas / Documentos",
        "freehub_save_temp_media": "Salvar mídia temporária", "freehub_voice_subdub_script": "Roteiro de voz / SubDub",
        "freehub_music_sfx_ideas": "Ideias de música / efeitos",
    },
    "fr": {
        "freehub_enable_ai_chatbot": "Activer le chatbot IA", "freehub_meta": "Prompt pour Meta AI",
        "freehub_caption": "Légende / hashtags", "freehub_ideas": "Idées de contenu",
        "freehub_prompts": "Prompts image / vidéo", "freehub_library": "Bibliothèque de prompts",
        "freehub_publish_package": "Pack de publication", "freehub_notes_docs": "Notes / Documents",
        "freehub_save_temp_media": "Enregistrer le média temporaire", "freehub_voice_subdub_script": "Script voix / SubDub",
        "freehub_music_sfx_ideas": "Idées musique / effets",
    },
    "de": {
        "freehub_enable_ai_chatbot": "KI-Chatbot aktivieren", "freehub_meta": "Meta-AI-Prompt",
        "freehub_caption": "Caption / Hashtags", "freehub_ideas": "Content-Ideen",
        "freehub_prompts": "Bild- / Video-Prompts", "freehub_library": "Prompt-Bibliothek",
        "freehub_publish_package": "Veröffentlichungspaket", "freehub_notes_docs": "Notizen / Dokumente",
        "freehub_save_temp_media": "Temporäre Medien speichern", "freehub_voice_subdub_script": "Voice- / SubDub-Skript",
        "freehub_music_sfx_ideas": "Musik- / SFX-Ideen",
    },
    "ja": {
        "freehub_enable_ai_chatbot": "AIチャットボットを有効にする", "freehub_meta": "Meta AI プロンプト",
        "freehub_caption": "キャプション / ハッシュタグ", "freehub_ideas": "コンテンツのアイデア",
        "freehub_prompts": "画像 / 動画プロンプト", "freehub_library": "プロンプトライブラリ",
        "freehub_publish_package": "投稿パッケージ", "freehub_notes_docs": "メモ / ドキュメント",
        "freehub_save_temp_media": "一時メディアを保存", "freehub_voice_subdub_script": "音声 / SubDub スクリプト",
        "freehub_music_sfx_ideas": "音楽 / 効果音のアイデア",
    },
    "ko": {
        "freehub_enable_ai_chatbot": "AI 챗봇 켜기", "freehub_meta": "Meta AI 프롬프트",
        "freehub_caption": "캡션 / 해시태그", "freehub_ideas": "콘텐츠 아이디어",
        "freehub_prompts": "이미지 / 동영상 프롬프트", "freehub_library": "프롬프트 라이브러리",
        "freehub_publish_package": "게시 패키지", "freehub_notes_docs": "메모 / 문서",
        "freehub_save_temp_media": "임시 미디어 저장", "freehub_voice_subdub_script": "음성 / SubDub 스크립트",
        "freehub_music_sfx_ideas": "음악 / 효과음 아이디어",
    },
    "hi": {
        "freehub_enable_ai_chatbot": "AI चैटबॉट चालू करें", "freehub_meta": "Meta AI प्रॉम्प्ट",
        "freehub_caption": "कैप्शन / हैशटैग", "freehub_ideas": "कॉन्टेंट आइडिया",
        "freehub_prompts": "छवि / वीडियो प्रॉम्प्ट", "freehub_library": "प्रॉम्प्ट लाइब्रेरी",
        "freehub_publish_package": "पोस्ट प्रकाशित पैकेज", "freehub_notes_docs": "नोट्स / दस्तावेज़",
        "freehub_save_temp_media": "अस्थायी मीडिया सहेजें", "freehub_voice_subdub_script": "वॉइस / SubDub स्क्रिप्ट",
        "freehub_music_sfx_ideas": "संगीत / SFX आइडिया",
    },
    "ar": {
        "freehub_enable_ai_chatbot": "تفعيل روبوت الدردشة بالذكاء الاصطناعي", "freehub_meta": "مطالبة Meta AI",
        "freehub_caption": "وصف / وسوم", "freehub_ideas": "أفكار للمحتوى",
        "freehub_prompts": "مطالبات صور / فيديو", "freehub_library": "مكتبة المطالبات",
        "freehub_publish_package": "حزمة نشر", "freehub_notes_docs": "ملاحظات / مستندات",
        "freehub_save_temp_media": "حفظ الوسائط المؤقتة", "freehub_voice_subdub_script": "نص صوت / SubDub",
        "freehub_music_sfx_ideas": "أفكار موسيقى / مؤثرات",
    },
    "ru": {
        "freehub_enable_ai_chatbot": "Включить ИИ-чатбот", "freehub_meta": "Промпт для Meta AI",
        "freehub_caption": "Подпись / хэштеги", "freehub_ideas": "Идеи для контента",
        "freehub_prompts": "Промпты для изображений / видео", "freehub_library": "Библиотека промптов",
        "freehub_publish_package": "Пакет для публикации", "freehub_notes_docs": "Заметки / Документы",
        "freehub_save_temp_media": "Сохранить временные медиа", "freehub_voice_subdub_script": "Сценарий голоса / SubDub",
        "freehub_music_sfx_ideas": "Идеи музыки / эффектов",
    },
    "tr": {
        "freehub_enable_ai_chatbot": "Yapay zekâ sohbet botunu aç", "freehub_meta": "Meta AI istemi",
        "freehub_caption": "Açıklama / etiketler", "freehub_ideas": "İçerik fikirleri",
        "freehub_prompts": "Görsel / video istemleri", "freehub_library": "İstem kitaplığı",
        "freehub_publish_package": "Yayın paketi", "freehub_notes_docs": "Notlar / Belgeler",
        "freehub_save_temp_media": "Geçici medyayı kaydet", "freehub_voice_subdub_script": "Ses / SubDub metni",
        "freehub_music_sfx_ideas": "Müzik / efekt fikirleri",
    },
    "th": {
        "freehub_enable_ai_chatbot": "เปิดใช้แชตบอต AI", "freehub_meta": "พรอมต์ Meta AI",
        "freehub_caption": "คำบรรยาย / แฮชแท็ก", "freehub_ideas": "ไอเดียคอนเทนต์",
        "freehub_prompts": "พรอมต์ภาพ / วิดีโอ", "freehub_library": "คลังพรอมต์",
        "freehub_publish_package": "แพ็กเกจสำหรับโพสต์", "freehub_notes_docs": "บันทึก / เอกสาร",
        "freehub_save_temp_media": "บันทึกสื่อชั่วคราว", "freehub_voice_subdub_script": "สคริปต์เสียง / SubDub",
        "freehub_music_sfx_ideas": "ไอเดียเพลง / เอฟเฟกต์",
    },
    "fil": {
        "freehub_enable_ai_chatbot": "I-on ang AI chatbot", "freehub_meta": "Prompt para sa Meta AI",
        "freehub_caption": "Caption / hashtag", "freehub_ideas": "Mga ideya sa content",
        "freehub_prompts": "Mga prompt para sa larawan / video", "freehub_library": "Aklatan ng prompt",
        "freehub_publish_package": "Package sa pag-post", "freehub_notes_docs": "Mga tala / Dokumento",
        "freehub_save_temp_media": "I-save ang pansamantalang media", "freehub_voice_subdub_script": "Script ng boses / SubDub",
        "freehub_music_sfx_ideas": "Mga ideya sa musika / SFX",
    },
    "it": {
        "freehub_enable_ai_chatbot": "Attiva il chatbot IA", "freehub_meta": "Prompt per Meta AI",
        "freehub_caption": "Didascalia / hashtag", "freehub_ideas": "Idee per i contenuti",
        "freehub_prompts": "Prompt per immagini / video", "freehub_library": "Libreria di prompt",
        "freehub_publish_package": "Pacchetto di pubblicazione", "freehub_notes_docs": "Note / Documenti",
        "freehub_save_temp_media": "Salva media temporanei", "freehub_voice_subdub_script": "Script voce / SubDub",
        "freehub_music_sfx_ideas": "Idee musica / effetti",
    },
    "id": {
        "freehub_enable_ai_chatbot": "Aktifkan chatbot AI", "freehub_meta": "Prompt Meta AI",
        "freehub_caption": "Caption / tagar", "freehub_ideas": "Ide konten",
        "freehub_prompts": "Prompt gambar / video", "freehub_library": "Pustaka prompt",
        "freehub_publish_package": "Paket publikasi", "freehub_notes_docs": "Catatan / Dokumen",
        "freehub_save_temp_media": "Simpan media sementara", "freehub_voice_subdub_script": "Skrip suara / SubDub",
        "freehub_music_sfx_ideas": "Ide musik / efek",
    },
}


# Image root text is a customer-facing introduction only.  Image creation,
# confirmation, jobs, providers and credit settlement keep their established
# owners in bot.py and are intentionally outside this copy table.
_PUBLIC_IMAGE_ROOT_COPY = {
    "vi": {
        "image_menu_title": "Hình ảnh TOAN AAS",
        "image_menu_body": "Chọn nhóm tác vụ:\n\n• Tạo ảnh nhanh: nhập prompt hoặc chọn gợi ý, rồi chọn tỷ lệ và gói.\n• Tạo prompt từ ảnh: gửi ảnh để bot viết prompt phù hợp.\n• Chỉnh sửa AI: sửa ảnh theo yêu cầu, có bước xác nhận trước khi xử lý.\n• Chỉnh sửa ảnh: crop/resize, chỉnh sáng, thêm chữ, logo/watermark, công thức màu và nâng chất lượng.\n\nMọi bước tạo hoặc chỉnh ảnh thật đều yêu cầu xác nhận trước khi trừ Xu.",
    },
    "en": {
        "image_menu_title": "TOAN AAS Image Tools",
        "image_menu_body": "Choose a task group:\n\n• Quick image: choose a suggestion or enter a prompt, then select the ratio and tier.\n• Prompt from image: send an image so the bot can write a matching prompt.\n• AI edit: edit an image as requested, with confirmation before processing.\n• Edit image: crop/resize, adjust brightness, add text, logo/watermark, colour presets and upscale.\n\nEvery real image create or edit step asks for confirmation before charging Xu.",
    },
    "zh": {
        "image_menu_title": "TOAN AAS 图片工具",
        "image_menu_body": "请选择任务类别：\n\n• 快速创建图片：选择建议或输入提示词，然后选择比例和档位。\n• 从图片生成提示词：发送图片，让机器人生成匹配的提示词。\n• AI 编辑：按您的要求编辑图片，处理前会要求确认。\n• 编辑图片：裁剪/调整尺寸、亮度、文字、Logo/水印、色彩预设和放大。\n\n所有实际图片创建或编辑步骤都会在扣除 Xu 前要求确认。",
    },
    "es": {
        "image_menu_title": "Herramientas de imagen TOAN AAS",
        "image_menu_body": "Elige una categoría de tarea:\n\n• Imagen rápida: elige una sugerencia o escribe un prompt y luego selecciona la proporción y el nivel.\n• Prompt desde imagen: envía una imagen para que el bot escriba un prompt adecuado.\n• Edición con IA: edita una imagen según tu pedido, con confirmación antes de procesar.\n• Editar imagen: recortar/cambiar tamaño, ajustar brillo, añadir texto, logo/marca de agua, preajustes de color y ampliar.\n\nToda creación o edición real de imagen solicita confirmación antes de cobrar Xu.",
    },
    "pt": {
        "image_menu_title": "Ferramentas de imagem TOAN AAS",
        "image_menu_body": "Escolha uma categoria de tarefa:\n\n• Imagem rápida: escolha uma sugestão ou escreva um prompt e depois selecione a proporção e o nível.\n• Prompt a partir da imagem: envie uma imagem para o bot escrever um prompt correspondente.\n• Edição com IA: edite uma imagem conforme o pedido, com confirmação antes do processamento.\n• Editar imagem: cortar/redimensionar, ajustar brilho, adicionar texto, logo/marca-d’água, predefinições de cor e ampliar.\n\nToda criação ou edição real de imagem pede confirmação antes de cobrar Xu.",
    },
    "fr": {
        "image_menu_title": "Outils d’image TOAN AAS",
        "image_menu_body": "Choisissez une catégorie de tâche :\n\n• Image rapide : choisissez une suggestion ou saisissez un prompt, puis le format et le niveau.\n• Prompt depuis une image : envoyez une image pour que le bot rédige un prompt adapté.\n• Modification par IA : modifiez une image selon votre demande, avec confirmation avant le traitement.\n• Modifier l’image : recadrer/redimensionner, ajuster la luminosité, ajouter du texte, un logo/filigrane, des préréglages couleur et agrandir.\n\nChaque création ou modification réelle d’image demande confirmation avant le débit de Xu.",
    },
    "de": {
        "image_menu_title": "TOAN AAS Bildwerkzeuge",
        "image_menu_body": "Wähle eine Aufgabengruppe:\n\n• Schnelles Bild: Wähle einen Vorschlag oder gib einen Prompt ein und wähle dann Format und Stufe.\n• Prompt aus Bild: Sende ein Bild, damit der Bot einen passenden Prompt schreibt.\n• KI-Bearbeitung: Bearbeite ein Bild nach Wunsch, mit Bestätigung vor der Verarbeitung.\n• Bild bearbeiten: Zuschneiden/Größe ändern, Helligkeit anpassen, Text, Logo/Wasserzeichen, Farbvorlagen und Hochskalierung.\n\nJede echte Bilderstellung oder -bearbeitung verlangt eine Bestätigung vor der Xu-Belastung.",
    },
    "ja": {
        "image_menu_title": "TOAN AAS 画像ツール",
        "image_menu_body": "タスクの種類を選択してください。\n\n• 画像をすばやく作成：候補を選ぶかプロンプトを入力し、比率とプランを選択します。\n• 画像からプロンプト：画像を送ると、ボットが適したプロンプトを作成します。\n• AIで編集：希望に沿って画像を編集し、処理前に確認します。\n• 画像を編集：トリミング/サイズ変更、明るさ調整、文字、ロゴ/透かし、カラープリセット、アップスケール。\n\n実際の画像作成・編集は、Xu を引き落とす前に必ず確認があります。",
    },
    "ko": {
        "image_menu_title": "TOAN AAS 이미지 도구",
        "image_menu_body": "작업 종류를 선택하세요.\n\n• 빠른 이미지 만들기: 추천을 선택하거나 프롬프트를 입력한 뒤 비율과 등급을 선택합니다.\n• 이미지에서 프롬프트: 이미지를 보내면 봇이 어울리는 프롬프트를 작성합니다.\n• AI로 편집: 요청에 맞게 이미지를 편집하며, 처리 전에 확인합니다.\n• 이미지 편집: 자르기/크기 변경, 밝기 조정, 텍스트, 로고/워터마크, 색상 프리셋 및 업스케일.\n\n실제 이미지 생성 또는 편집은 Xu 차감 전에 항상 확인을 요청합니다.",
    },
    "hi": {
        "image_menu_title": "TOAN AAS इमेज टूल",
        "image_menu_body": "कार्य समूह चुनें:\n\n• त्वरित छवि: सुझाव चुनें या प्रॉम्प्ट लिखें, फिर अनुपात और स्तर चुनें।\n• छवि से प्रॉम्प्ट: छवि भेजें ताकि बॉट मिलान वाला प्रॉम्प्ट लिख सके।\n• AI से संपादन: आपके अनुरोध के अनुसार छवि संपादित करें; प्रोसेस से पहले पुष्टि होगी।\n• छवि संपादित करें: क्रॉप/आकार बदलें, चमक समायोजित करें, टेक्स्ट, लोगो/वॉटरमार्क, रंग प्रीसेट और अपस्केल।\n\nहर वास्तविक छवि निर्माण या संपादन से पहले Xu काटने हेतु पुष्टि मांगी जाती है।",
    },
    "ar": {
        "image_menu_title": "أدوات الصور من TOAN AAS",
        "image_menu_body": "اختر فئة المهمة:\n\n• إنشاء صورة سريع: اختر اقتراحاً أو اكتب مطالبة ثم اختر النسبة والمستوى.\n• مطالبة من صورة: أرسل صورة ليكتب البوت مطالبة مناسبة.\n• تعديل بالذكاء الاصطناعي: عدّل الصورة حسب طلبك مع تأكيد قبل المعالجة.\n• تعديل الصورة: قص/تغيير الحجم، ضبط السطوع، إضافة نص، شعار/علامة مائية، إعدادات ألوان وتكبير.\n\nكل إنشاء أو تعديل فعلي للصور يتطلب تأكيداً قبل خصم Xu.",
    },
    "ru": {
        "image_menu_title": "Инструменты изображений TOAN AAS",
        "image_menu_body": "Выберите тип задачи:\n\n• Быстрое изображение: выберите подсказку или введите промпт, затем выберите формат и уровень.\n• Промпт из изображения: отправьте изображение, чтобы бот составил подходящий промпт.\n• Редактирование ИИ: измените изображение по запросу с подтверждением перед обработкой.\n• Редактировать изображение: обрезка/изменение размера, яркость, текст, логотип/водяной знак, цветовые пресеты и увеличение.\n\nЛюбое реальное создание или редактирование изображения требует подтверждения до списания Xu.",
    },
    "tr": {
        "image_menu_title": "TOAN AAS görsel araçları",
        "image_menu_body": "Bir görev grubu seçin:\n\n• Hızlı görsel: bir öneri seçin veya istem yazın, sonra oranı ve kademeyi seçin.\n• Görselden istem: botun uygun bir istem yazması için bir görsel gönderin.\n• Yapay zekâyla düzenle: görseli isteğinize göre düzenleyin; işlemden önce onay alınır.\n• Görseli düzenle: kırpma/boyutlandırma, parlaklık, metin, logo/filigran, renk ön ayarları ve büyütme.\n\nHer gerçek görsel oluşturma veya düzenleme, Xu kesilmeden önce onay ister.",
    },
    "th": {
        "image_menu_title": "เครื่องมือภาพ TOAN AAS",
        "image_menu_body": "เลือกกลุ่มงาน:\n\n• สร้างภาพด่วน: เลือกคำแนะนำหรือพิมพ์พรอมต์ แล้วเลือกสัดส่วนและระดับ\n• สร้างพรอมต์จากภาพ: ส่งภาพให้บอตเขียนพรอมต์ที่เหมาะสม\n• แก้ไขด้วย AI: แก้ไขภาพตามคำขอ พร้อมยืนยันก่อนประมวลผล\n• แก้ไขภาพ: ครอป/ปรับขนาด ปรับความสว่าง เพิ่มข้อความ โลโก้/ลายน้ำ พรีเซ็ตสี และอัปสเกล\n\nการสร้างหรือแก้ไขภาพจริงทุกครั้งต้องยืนยันก่อนหัก Xu.",
    },
    "fil": {
        "image_menu_title": "Mga tool sa larawan ng TOAN AAS",
        "image_menu_body": "Pumili ng uri ng gawain:\n\n• Mabilis na larawan: pumili ng mungkahi o maglagay ng prompt, saka piliin ang ratio at antas.\n• Prompt mula sa larawan: magpadala ng larawan upang makagawa ang bot ng angkop na prompt.\n• Pag-edit gamit ang AI: i-edit ang larawan ayon sa kahilingan, na may kumpirmasyon bago iproseso.\n• I-edit ang larawan: i-crop/baguhin ang laki, ayusin ang liwanag, magdagdag ng text, logo/watermark, color preset at upscale.\n\nAng bawat tunay na paggawa o pag-edit ng larawan ay nangangailangan ng kumpirmasyon bago mabawasan ang Xu.",
    },
    "it": {
        "image_menu_title": "Strumenti immagini TOAN AAS",
        "image_menu_body": "Scegli una categoria di attività:\n\n• Immagine rapida: scegli un suggerimento o inserisci un prompt, poi seleziona rapporto e livello.\n• Prompt da immagine: invia un’immagine affinché il bot scriva un prompt adatto.\n• Modifica con IA: modifica un’immagine secondo la richiesta, con conferma prima dell’elaborazione.\n• Modifica immagine: ritaglia/ridimensiona, regola la luminosità, aggiungi testo, logo/filigrana, preimpostazioni colore e aumenta la qualità.\n\nOgni creazione o modifica reale di immagini richiede conferma prima dell’addebito di Xu.",
    },
    "id": {
        "image_menu_title": "Alat gambar TOAN AAS",
        "image_menu_body": "Pilih kelompok tugas:\n\n• Gambar cepat: pilih saran atau masukkan prompt, lalu pilih rasio dan tingkat.\n• Prompt dari gambar: kirim gambar agar bot menulis prompt yang sesuai.\n• Edit dengan AI: edit gambar sesuai permintaan, dengan konfirmasi sebelum diproses.\n• Edit gambar: potong/ubah ukuran, atur kecerahan, tambahkan teks, logo/watermark, preset warna, dan tingkatkan kualitas.\n\nSetiap pembuatan atau pengeditan gambar nyata memerlukan konfirmasi sebelum Xu dipotong.",
    },
}


# Audio Studio entry and its Voice/Music hubs use copy only.  Their callbacks,
# state, engine readiness, creation jobs and Xu settlement remain unchanged.
_PUBLIC_AUDIO_ROOT_COPY = {
    "vi": {
        "audio_root_voice": "Giọng đọc", "audio_root_music": "Nhạc", "audio_root_back": "Quay lại",
        "voice_hub_title": "Giọng đọc", "voice_hub_body": "Tạo file giọng đọc riêng, bóc băng audio hoặc quản lý Kho voice đã lưu. Chọn giọng rồi gửi văn bản để TOAN AAS tạo file audio bằng giọng đó. Khu này không gắn vào đơn video hiện tại và chưa trừ Xu.",
        "voice_text_to_speech": "Văn bản thành giọng nói", "voice_speech_to_text": "Giọng nói thành văn bản", "voice_default_female": "Giọng nữ", "voice_default_male": "Giọng nam", "voice_default_neutral": "Giọng mặc định sẵn sàng", "voice_vault": "Kho voice", "voice_create_custom": "Tạo voice riêng",
        "music_hub_title": "Studio nhạc", "music_hub_body": "Bạn muốn làm gì?", "music_background": "Tạo nhạc nền", "music_song": "Bài hát có lời", "music_vault": "Kho nhạc", "music_edit": "Cắt / ghép nhạc",
    },
    "en": {
        "audio_root_voice": "Voice", "audio_root_music": "Music", "audio_root_back": "Back",
        "voice_hub_title": "Voice", "voice_hub_body": "Choose a default voice, a saved voice profile, or create a custom voice. This studio creates a separate audio file and is not attached to a video order.",
        "voice_text_to_speech": "Text to speech", "voice_speech_to_text": "Speech to text", "voice_default_female": "Female voice", "voice_default_male": "Male voice", "voice_default_neutral": "Ready default voice", "voice_vault": "Voice vault", "voice_create_custom": "Create custom voice",
        "music_hub_title": "Music Studio", "music_hub_body": "What would you like to do?", "music_background": "Create background music", "music_song": "Song with lyrics", "music_vault": "Music vault", "music_edit": "Cut / merge music",
    },
    "zh": {
        "audio_root_voice": "语音", "audio_root_music": "音乐", "audio_root_back": "返回",
        "voice_hub_title": "语音", "voice_hub_body": "选择默认声音、已保存的声音档案，或创建自定义声音。本工作室会创建独立音频文件，不会附加到视频订单。",
        "voice_text_to_speech": "文字转语音", "voice_speech_to_text": "语音转文字", "voice_default_female": "女声", "voice_default_male": "男声", "voice_default_neutral": "可用默认声音", "voice_vault": "声音库", "voice_create_custom": "创建自定义声音",
        "music_hub_title": "音乐工作室", "music_hub_body": "您想做什么？", "music_background": "创建背景音乐", "music_song": "带歌词的歌曲", "music_vault": "音乐库", "music_edit": "剪辑 / 合并音乐",
    },
    "es": {
        "audio_root_voice": "Voz", "audio_root_music": "Música", "audio_root_back": "Volver",
        "voice_hub_title": "Voz", "voice_hub_body": "Elige una voz predeterminada, un perfil de voz guardado o crea una voz personalizada. Este estudio crea un archivo de audio independiente y no se adjunta a un pedido de vídeo.",
        "voice_text_to_speech": "Texto a voz", "voice_speech_to_text": "Voz a texto", "voice_default_female": "Voz femenina", "voice_default_male": "Voz masculina", "voice_default_neutral": "Voz predeterminada disponible", "voice_vault": "Biblioteca de voces", "voice_create_custom": "Crear voz personalizada",
        "music_hub_title": "Estudio de música", "music_hub_body": "¿Qué te gustaría hacer?", "music_background": "Crear música de fondo", "music_song": "Canción con letra", "music_vault": "Biblioteca de música", "music_edit": "Cortar / unir música",
    },
    "pt": {
        "audio_root_voice": "Voz", "audio_root_music": "Música", "audio_root_back": "Voltar",
        "voice_hub_title": "Voz", "voice_hub_body": "Escolha uma voz padrão, um perfil de voz salvo ou crie uma voz personalizada. Este estúdio cria um arquivo de áudio separado e não o vincula a um pedido de vídeo.",
        "voice_text_to_speech": "Texto para voz", "voice_speech_to_text": "Voz para texto", "voice_default_female": "Voz feminina", "voice_default_male": "Voz masculina", "voice_default_neutral": "Voz padrão disponível", "voice_vault": "Biblioteca de vozes", "voice_create_custom": "Criar voz personalizada",
        "music_hub_title": "Estúdio de música", "music_hub_body": "O que você gostaria de fazer?", "music_background": "Criar música de fundo", "music_song": "Canção com letra", "music_vault": "Biblioteca de música", "music_edit": "Cortar / juntar música",
    },
    "fr": {
        "audio_root_voice": "Voix", "audio_root_music": "Musique", "audio_root_back": "Retour",
        "voice_hub_title": "Voix", "voice_hub_body": "Choisissez une voix par défaut, un profil vocal enregistré ou créez une voix personnalisée. Ce studio crée un fichier audio séparé qui n’est pas lié à une commande vidéo.",
        "voice_text_to_speech": "Texte vers voix", "voice_speech_to_text": "Voix vers texte", "voice_default_female": "Voix féminine", "voice_default_male": "Voix masculine", "voice_default_neutral": "Voix par défaut disponible", "voice_vault": "Bibliothèque de voix", "voice_create_custom": "Créer une voix personnalisée",
        "music_hub_title": "Studio de musique", "music_hub_body": "Que souhaitez-vous faire ?", "music_background": "Créer une musique de fond", "music_song": "Chanson avec paroles", "music_vault": "Bibliothèque musicale", "music_edit": "Couper / assembler la musique",
    },
    "de": {
        "audio_root_voice": "Stimme", "audio_root_music": "Musik", "audio_root_back": "Zurück",
        "voice_hub_title": "Stimme", "voice_hub_body": "Wähle eine Standardstimme, ein gespeichertes Stimmprofil oder erstelle eine eigene Stimme. Dieses Studio erstellt eine separate Audiodatei und ist nicht mit einem Videoauftrag verbunden.",
        "voice_text_to_speech": "Text zu Sprache", "voice_speech_to_text": "Sprache zu Text", "voice_default_female": "Weibliche Stimme", "voice_default_male": "Männliche Stimme", "voice_default_neutral": "Standardstimme verfügbar", "voice_vault": "Stimmarchiv", "voice_create_custom": "Eigene Stimme erstellen",
        "music_hub_title": "Musikstudio", "music_hub_body": "Was möchtest du tun?", "music_background": "Hintergrundmusik erstellen", "music_song": "Lied mit Text", "music_vault": "Musikarchiv", "music_edit": "Musik schneiden / zusammenfügen",
    },
    "ja": {
        "audio_root_voice": "音声", "audio_root_music": "音楽", "audio_root_back": "戻る",
        "voice_hub_title": "音声", "voice_hub_body": "標準の声、保存済みの音声プロフィールを選ぶか、カスタム音声を作成できます。このスタジオは独立した音声ファイルを作成し、動画の注文には紐づきません。",
        "voice_text_to_speech": "テキストを音声に", "voice_speech_to_text": "音声をテキストに", "voice_default_female": "女性の声", "voice_default_male": "男性の声", "voice_default_neutral": "利用可能な標準音声", "voice_vault": "音声ライブラリ", "voice_create_custom": "カスタム音声を作成",
        "music_hub_title": "音楽スタジオ", "music_hub_body": "何をしますか？", "music_background": "BGMを作成", "music_song": "歌詞付きの曲", "music_vault": "音楽ライブラリ", "music_edit": "音楽をカット / 結合",
    },
    "ko": {
        "audio_root_voice": "음성", "audio_root_music": "음악", "audio_root_back": "뒤로",
        "voice_hub_title": "음성", "voice_hub_body": "기본 음성이나 저장된 음성 프로필을 선택하거나 맞춤 음성을 만들 수 있습니다. 이 스튜디오는 별도 오디오 파일을 만들며 동영상 주문에는 연결되지 않습니다.",
        "voice_text_to_speech": "텍스트를 음성으로", "voice_speech_to_text": "음성을 텍스트로", "voice_default_female": "여성 음성", "voice_default_male": "남성 음성", "voice_default_neutral": "사용 가능한 기본 음성", "voice_vault": "음성 보관함", "voice_create_custom": "맞춤 음성 만들기",
        "music_hub_title": "음악 스튜디오", "music_hub_body": "무엇을 하시겠어요?", "music_background": "배경 음악 만들기", "music_song": "가사가 있는 노래", "music_vault": "음악 보관함", "music_edit": "음악 자르기 / 합치기",
    },
    "hi": {
        "audio_root_voice": "आवाज़", "audio_root_music": "संगीत", "audio_root_back": "वापस",
        "voice_hub_title": "आवाज़", "voice_hub_body": "डिफ़ॉल्ट आवाज़, सहेजे गए वॉइस प्रोफ़ाइल चुनें या अपनी आवाज़ बनाएं। यह स्टूडियो अलग ऑडियो फ़ाइल बनाता है और वीडियो ऑर्डर से जुड़ा नहीं होता।",
        "voice_text_to_speech": "टेक्स्ट से आवाज़", "voice_speech_to_text": "आवाज़ से टेक्स्ट", "voice_default_female": "महिला आवाज़", "voice_default_male": "पुरुष आवाज़", "voice_default_neutral": "डिफ़ॉल्ट आवाज़ उपलब्ध", "voice_vault": "वॉइस संग्रह", "voice_create_custom": "अपनी आवाज़ बनाएं",
        "music_hub_title": "संगीत स्टूडियो", "music_hub_body": "आप क्या करना चाहते हैं?", "music_background": "बैकग्राउंड संगीत बनाएं", "music_song": "बोल वाला गीत", "music_vault": "संगीत संग्रह", "music_edit": "संगीत काटें / जोड़ें",
    },
    "ar": {
        "audio_root_voice": "الصوت", "audio_root_music": "الموسيقى", "audio_root_back": "رجوع",
        "voice_hub_title": "الصوت", "voice_hub_body": "اختر صوتاً افتراضياً أو ملفاً صوتياً محفوظاً أو أنشئ صوتاً مخصصاً. ينشئ هذا الاستوديو ملفاً صوتياً منفصلاً ولا يرتبط بطلب فيديو.",
        "voice_text_to_speech": "النص إلى صوت", "voice_speech_to_text": "الصوت إلى نص", "voice_default_female": "صوت أنثوي", "voice_default_male": "صوت ذكوري", "voice_default_neutral": "الصوت الافتراضي متاح", "voice_vault": "مكتبة الأصوات", "voice_create_custom": "إنشاء صوت مخصص",
        "music_hub_title": "استوديو الموسيقى", "music_hub_body": "ماذا تريد أن تفعل؟", "music_background": "إنشاء موسيقى خلفية", "music_song": "أغنية بكلمات", "music_vault": "مكتبة الموسيقى", "music_edit": "قص / دمج الموسيقى",
    },
    "ru": {
        "audio_root_voice": "Голос", "audio_root_music": "Музыка", "audio_root_back": "Назад",
        "voice_hub_title": "Голос", "voice_hub_body": "Выберите голос по умолчанию, сохранённый голосовой профиль или создайте свой голос. Эта студия создаёт отдельный аудиофайл и не связана с заказом видео.",
        "voice_text_to_speech": "Текст в речь", "voice_speech_to_text": "Речь в текст", "voice_default_female": "Женский голос", "voice_default_male": "Мужской голос", "voice_default_neutral": "Стандартный голос доступен", "voice_vault": "Хранилище голосов", "voice_create_custom": "Создать свой голос",
        "music_hub_title": "Музыкальная студия", "music_hub_body": "Что вы хотите сделать?", "music_background": "Создать фоновую музыку", "music_song": "Песня с текстом", "music_vault": "Музыкальная библиотека", "music_edit": "Обрезать / объединить музыку",
    },
    "tr": {
        "audio_root_voice": "Ses", "audio_root_music": "Müzik", "audio_root_back": "Geri",
        "voice_hub_title": "Ses", "voice_hub_body": "Varsayılan bir ses, kaydedilmiş ses profili seçin veya özel ses oluşturun. Bu stüdyo ayrı bir ses dosyası üretir ve video siparişine bağlı değildir.",
        "voice_text_to_speech": "Metinden sese", "voice_speech_to_text": "Sesten metne", "voice_default_female": "Kadın sesi", "voice_default_male": "Erkek sesi", "voice_default_neutral": "Varsayılan ses hazır", "voice_vault": "Ses arşivi", "voice_create_custom": "Özel ses oluştur",
        "music_hub_title": "Müzik stüdyosu", "music_hub_body": "Ne yapmak istersiniz?", "music_background": "Arka plan müziği oluştur", "music_song": "Sözlü şarkı", "music_vault": "Müzik arşivi", "music_edit": "Müziği kes / birleştir",
    },
    "th": {
        "audio_root_voice": "เสียง", "audio_root_music": "เพลง", "audio_root_back": "ย้อนกลับ",
        "voice_hub_title": "เสียง", "voice_hub_body": "เลือกเสียงเริ่มต้น โปรไฟล์เสียงที่บันทึกไว้ หรือสร้างเสียงแบบกำหนดเอง สตูดิโอนี้สร้างไฟล์เสียงแยกต่างหากและไม่เชื่อมกับคำสั่งวิดีโอ",
        "voice_text_to_speech": "ข้อความเป็นเสียง", "voice_speech_to_text": "เสียงเป็นข้อความ", "voice_default_female": "เสียงผู้หญิง", "voice_default_male": "เสียงผู้ชาย", "voice_default_neutral": "เสียงเริ่มต้นพร้อมใช้", "voice_vault": "คลังเสียง", "voice_create_custom": "สร้างเสียงกำหนดเอง",
        "music_hub_title": "สตูดิโอเพลง", "music_hub_body": "คุณต้องการทำอะไร?", "music_background": "สร้างเพลงพื้นหลัง", "music_song": "เพลงพร้อมเนื้อร้อง", "music_vault": "คลังเพลง", "music_edit": "ตัด / รวมเพลง",
    },
    "fil": {
        "audio_root_voice": "Boses", "audio_root_music": "Musika", "audio_root_back": "Bumalik",
        "voice_hub_title": "Boses", "voice_hub_body": "Pumili ng default na boses, naka-save na profile ng boses, o gumawa ng sariling boses. Lumilikha ang studio na ito ng hiwalay na audio file at hindi ito konektado sa video order.",
        "voice_text_to_speech": "Text patungong boses", "voice_speech_to_text": "Boses patungong text", "voice_default_female": "Babaeng boses", "voice_default_male": "Lalaking boses", "voice_default_neutral": "Handa ang default na boses", "voice_vault": "Imbakan ng boses", "voice_create_custom": "Gumawa ng sariling boses",
        "music_hub_title": "Studio ng musika", "music_hub_body": "Ano ang gusto mong gawin?", "music_background": "Gumawa ng background music", "music_song": "Kantang may lyrics", "music_vault": "Imbakan ng musika", "music_edit": "Putulin / pagdugtungin ang musika",
    },
    "it": {
        "audio_root_voice": "Voce", "audio_root_music": "Musica", "audio_root_back": "Indietro",
        "voice_hub_title": "Voce", "voice_hub_body": "Scegli una voce predefinita, un profilo vocale salvato o crea una voce personalizzata. Questo studio crea un file audio separato e non è collegato a un ordine video.",
        "voice_text_to_speech": "Testo in voce", "voice_speech_to_text": "Voce in testo", "voice_default_female": "Voce femminile", "voice_default_male": "Voce maschile", "voice_default_neutral": "Voce predefinita disponibile", "voice_vault": "Archivio voci", "voice_create_custom": "Crea voce personalizzata",
        "music_hub_title": "Studio musicale", "music_hub_body": "Cosa desideri fare?", "music_background": "Crea musica di sottofondo", "music_song": "Brano con testo", "music_vault": "Archivio musicale", "music_edit": "Taglia / unisci musica",
    },
    "id": {
        "audio_root_voice": "Suara", "audio_root_music": "Musik", "audio_root_back": "Kembali",
        "voice_hub_title": "Suara", "voice_hub_body": "Pilih suara bawaan, profil suara tersimpan, atau buat suara khusus. Studio ini membuat file audio terpisah dan tidak terhubung ke pesanan video.",
        "voice_text_to_speech": "Teks ke suara", "voice_speech_to_text": "Suara ke teks", "voice_default_female": "Suara perempuan", "voice_default_male": "Suara laki-laki", "voice_default_neutral": "Suara bawaan siap", "voice_vault": "Penyimpanan suara", "voice_create_custom": "Buat suara khusus",
        "music_hub_title": "Studio musik", "music_hub_body": "Apa yang ingin Anda lakukan?", "music_background": "Buat musik latar", "music_song": "Lagu dengan lirik", "music_vault": "Perpustakaan musik", "music_edit": "Potong / gabungkan musik",
    },
}


_PUBLIC_ROOT_FLOW_COPY = {
    "en": {"memory_title": "Notes / Documents", "memory_body": "Save notes, reminders, checklists and personal documents here. Document tools guide upload, confirmation and processing; no technical command is required.", "docs_title": "PDF / Word tools", "docs_body": "Choose a tool, send the requested file or image, then confirm before processing. Sending files one by one is safer than albums.", "translation_title": "TOAN AAS Translation Center", "translation_body": "Choose the kind of content you want to translate.", "translation_language_title": "Language translation", "translation_language_body": "Choose a translation mode. Short text translation does not charge Xu; voice, audio, long documents and TTS are checked before processing.", "audio_media_title": "Voice / Media", "audio_media_body": "Transcribe audio or video, or create voice/TTS for content. Send voice, audio or video to transcribe when that tool is enabled.", "profile_title": "Account", "profile_body": "Use /profile to view your balance, tier and account information.", "video_menu_title": "TOAN AAS Video", "video_menu_body": "Choose the video tool you want to use."},
    "vi": {"memory_title": "Ghi chú / Tài liệu", "memory_body": "Lưu ghi chú, nhắc việc, checklist và tài liệu cá nhân tại đây. Công cụ tài liệu sẽ hướng dẫn gửi file, xác nhận và xử lý; không cần dùng lệnh kỹ thuật.", "docs_title": "Công cụ PDF / Word", "docs_body": "Chọn công cụ, gửi file hoặc ảnh được yêu cầu, rồi xác nhận trước khi xử lý. Gửi từng file một an toàn hơn album.", "translation_title": "Trung tâm dịch TOAN AAS", "translation_body": "Bạn muốn dịch loại nội dung nào?", "translation_language_title": "Dịch ngôn ngữ", "translation_language_body": "Chọn chế độ dịch. Dịch văn bản ngắn không trừ Xu; voice, audio, tài liệu dài và TTS sẽ được kiểm tra trước khi xử lý.", "audio_media_title": "Giọng đọc / Media", "audio_media_body": "Bóc băng audio hoặc video, hoặc tạo giọng đọc/TTS cho nội dung. Gửi voice, audio hoặc video để bóc băng khi công cụ đang bật.", "profile_title": "Tài khoản", "profile_body": "Dùng /profile để xem số dư, hạng và thông tin tài khoản.", "video_menu_title": "Video TOAN AAS", "video_menu_body": "Chọn công cụ video bạn muốn dùng."},
    "zh": {"memory_title": "笔记 / 文档", "memory_body": "在此保存笔记、提醒、清单和个人文档。文档工具会引导上传、确认和处理，无需技术命令。", "docs_title": "PDF / Word 工具", "docs_body": "选择工具，发送所需文件或图片，然后在处理前确认。逐个发送文件比相册更安全。", "translation_title": "TOAN AAS 翻译中心", "translation_body": "请选择要翻译的内容类型。", "translation_language_title": "语言翻译", "translation_language_body": "选择翻译模式。短文本翻译不扣 Xu；语音、音频、长文档和 TTS 会在处理前检查。", "audio_media_title": "语音 / 媒体", "audio_media_body": "转写音频或视频，或为内容创建语音/TTS。工具启用时可发送语音、音频或视频进行转写。", "profile_title": "账户", "profile_body": "使用 /profile 查看余额、等级和账户信息。", "video_menu_title": "TOAN AAS 视频", "video_menu_body": "请选择要使用的视频工具。"},
    "es": {"memory_title": "Notas / Documentos", "memory_body": "Guarda aquí notas, recordatorios, listas y documentos personales. Las herramientas de documentos guían la carga, confirmación y procesamiento; no necesitas comandos técnicos.", "docs_title": "Herramientas PDF / Word", "docs_body": "Elige una herramienta, envía el archivo o imagen solicitados y confirma antes de procesar. Enviar los archivos uno por uno es más seguro que usar álbumes.", "translation_title": "Centro de traducción TOAN AAS", "translation_body": "Elige el tipo de contenido que deseas traducir.", "translation_language_title": "Traducción de idiomas", "translation_language_body": "Elige un modo de traducción. La traducción de texto corto no cobra Xu; voz, audio, documentos largos y TTS se revisan antes de procesar.", "audio_media_title": "Voz / Medios", "audio_media_body": "Transcribe audio o vídeo, o crea voz/TTS para contenido. Envía voz, audio o vídeo para transcribir cuando la herramienta esté activa.", "profile_title": "Cuenta", "profile_body": "Usa /profile para ver tu saldo, nivel e información de cuenta.", "video_menu_title": "Vídeo TOAN AAS", "video_menu_body": "Elige la herramienta de vídeo que deseas usar."},
    "pt": {"memory_title": "Notas / Documentos", "memory_body": "Salve notas, lembretes, listas e documentos pessoais aqui. As ferramentas de documentos orientam o envio, a confirmação e o processamento; não é necessário comando técnico.", "docs_title": "Ferramentas PDF / Word", "docs_body": "Escolha uma ferramenta, envie o arquivo ou imagem solicitados e confirme antes de processar. Enviar arquivos um por um é mais seguro que usar álbuns.", "translation_title": "Centro de tradução TOAN AAS", "translation_body": "Escolha o tipo de conteúdo que deseja traduzir.", "translation_language_title": "Tradução de idiomas", "translation_language_body": "Escolha um modo de tradução. A tradução de texto curto não cobra Xu; voz, áudio, documentos longos e TTS são verificados antes do processamento.", "audio_media_title": "Voz / Mídia", "audio_media_body": "Transcreva áudio ou vídeo, ou crie voz/TTS para conteúdo. Envie voz, áudio ou vídeo para transcrever quando a ferramenta estiver ativa.", "profile_title": "Conta", "profile_body": "Use /profile para ver seu saldo, nível e informações da conta.", "video_menu_title": "Vídeo TOAN AAS", "video_menu_body": "Escolha a ferramenta de vídeo que deseja usar."},
    "fr": {"memory_title": "Notes / Documents", "memory_body": "Enregistrez ici vos notes, rappels, listes et documents personnels. Les outils documentaires guident l’envoi, la confirmation et le traitement ; aucune commande technique n’est nécessaire.", "docs_title": "Outils PDF / Word", "docs_body": "Choisissez un outil, envoyez le fichier ou l’image demandé, puis confirmez avant traitement. L’envoi des fichiers un par un est plus sûr que les albums.", "translation_title": "Centre de traduction TOAN AAS", "translation_body": "Choisissez le type de contenu à traduire.", "translation_language_title": "Traduction linguistique", "translation_language_body": "Choisissez un mode de traduction. La traduction de texte court ne débite pas de Xu ; voix, audio, longs documents et TTS sont vérifiés avant traitement.", "audio_media_title": "Voix / Média", "audio_media_body": "Transcrivez de l’audio ou de la vidéo, ou créez une voix/TTS pour votre contenu. Envoyez un vocal, audio ou vidéo pour transcription lorsque l’outil est actif.", "profile_title": "Compte", "profile_body": "Utilisez /profile pour voir votre solde, votre niveau et les informations du compte.", "video_menu_title": "Vidéo TOAN AAS", "video_menu_body": "Choisissez l’outil vidéo à utiliser."},
    "de": {"memory_title": "Notizen / Dokumente", "memory_body": "Speichere hier Notizen, Erinnerungen, Checklisten und persönliche Dokumente. Die Dokumentwerkzeuge führen durch Upload, Bestätigung und Verarbeitung; kein technischer Befehl ist nötig.", "docs_title": "PDF / Word-Werkzeuge", "docs_body": "Wähle ein Werkzeug, sende die angeforderte Datei oder das Bild und bestätige vor der Verarbeitung. Dateien einzeln zu senden ist sicherer als Alben.", "translation_title": "TOAN AAS Übersetzungszentrum", "translation_body": "Wähle die Art von Inhalt, die du übersetzen möchtest.", "translation_language_title": "Sprachübersetzung", "translation_language_body": "Wähle einen Übersetzungsmodus. Kurze Textübersetzung kostet keine Xu; Stimme, Audio, lange Dokumente und TTS werden vor der Verarbeitung geprüft.", "audio_media_title": "Stimme / Medien", "audio_media_body": "Transkribiere Audio oder Video oder erstelle Stimme/TTS für Inhalte. Sende Sprach-, Audio- oder Videodateien zur Transkription, wenn das Werkzeug aktiv ist.", "profile_title": "Konto", "profile_body": "Nutze /profile, um Guthaben, Stufe und Kontoinformationen zu sehen.", "video_menu_title": "TOAN AAS Video", "video_menu_body": "Wähle das Video-Werkzeug, das du verwenden möchtest."},
    "ja": {"memory_title": "メモ / ドキュメント", "memory_body": "メモ、リマインダー、チェックリスト、個人文書をここに保存できます。文書ツールがアップロード、確認、処理を案内するため、技術コマンドは不要です。", "docs_title": "PDF / Word ツール", "docs_body": "ツールを選び、必要なファイルまたは画像を送り、処理前に確認してください。アルバムより1件ずつ送る方が安全です。", "translation_title": "TOAN AAS 翻訳センター", "translation_body": "翻訳したいコンテンツの種類を選択してください。", "translation_language_title": "言語翻訳", "translation_language_body": "翻訳モードを選択してください。短いテキスト翻訳は Xu を消費しません。音声、長文書、TTS は処理前に確認されます。", "audio_media_title": "音声 / メディア", "audio_media_body": "音声や動画を文字起こししたり、コンテンツ用の音声/TTSを作成します。ツール有効時は音声、オーディオ、動画を送信できます。", "profile_title": "アカウント", "profile_body": "/profile で残高、ランク、アカウント情報を確認できます。", "video_menu_title": "TOAN AAS 動画", "video_menu_body": "使用する動画ツールを選択してください。"},
    "ko": {"memory_title": "메모 / 문서", "memory_body": "메모, 알림, 체크리스트 및 개인 문서를 여기에 저장하세요. 문서 도구가 업로드, 확인 및 처리를 안내하므로 기술 명령이 필요하지 않습니다.", "docs_title": "PDF / Word 도구", "docs_body": "도구를 선택하고 요청된 파일 또는 이미지를 보낸 뒤 처리 전에 확인하세요. 앨범보다 파일을 하나씩 보내는 것이 안전합니다.", "translation_title": "TOAN AAS 번역 센터", "translation_body": "번역할 콘텐츠 유형을 선택하세요.", "translation_language_title": "언어 번역", "translation_language_body": "번역 모드를 선택하세요. 짧은 텍스트 번역은 Xu가 차감되지 않으며 음성, 오디오, 긴 문서 및 TTS는 처리 전에 확인됩니다.", "audio_media_title": "음성 / 미디어", "audio_media_body": "오디오 또는 비디오를 받아쓰거나 콘텐츠용 음성/TTS를 만드세요. 도구가 활성화되면 음성, 오디오 또는 비디오를 보낼 수 있습니다.", "profile_title": "계정", "profile_body": "/profile에서 잔액, 등급 및 계정 정보를 확인하세요.", "video_menu_title": "TOAN AAS 동영상", "video_menu_body": "사용할 동영상 도구를 선택하세요."},
    "hi": {"memory_title": "नोट्स / दस्तावेज़", "memory_body": "नोट्स, रिमाइंडर, चेकलिस्ट और निजी दस्तावेज़ यहाँ सहेजें। दस्तावेज़ टूल अपलोड, पुष्टि और प्रोसेसिंग में मार्गदर्शन करते हैं; तकनीकी कमांड की आवश्यकता नहीं है।", "docs_title": "PDF / Word उपकरण", "docs_body": "एक टूल चुनें, आवश्यक फ़ाइल या चित्र भेजें, फिर प्रोसेस करने से पहले पुष्टि करें। फ़ाइलों को एक-एक करके भेजना एल्बम से अधिक सुरक्षित है।", "translation_title": "TOAN AAS अनुवाद केंद्र", "translation_body": "उस सामग्री का प्रकार चुनें जिसका अनुवाद करना है।", "translation_language_title": "भाषा अनुवाद", "translation_language_body": "अनुवाद मोड चुनें। छोटे पाठ का अनुवाद Xu नहीं काटता; आवाज़, ऑडियो, लंबे दस्तावेज़ और TTS की प्रोसेसिंग से पहले जाँच होती है।", "audio_media_title": "आवाज़ / मीडिया", "audio_media_body": "ऑडियो या वीडियो लिखित रूप में बदलें, या सामग्री के लिए आवाज़/TTS बनाएँ। टूल सक्षम होने पर आवाज़, ऑडियो या वीडियो भेजें।", "profile_title": "खाता", "profile_body": "अपना बैलेंस, स्तर और खाते की जानकारी देखने के लिए /profile का उपयोग करें।", "video_menu_title": "TOAN AAS वीडियो", "video_menu_body": "उपयोग करने के लिए वीडियो टूल चुनें।"},
    "ar": {"memory_title": "ملاحظات / مستندات", "memory_body": "احفظ الملاحظات والتذكيرات وقوائم التحقق والمستندات الشخصية هنا. ترشدك أدوات المستندات خلال الرفع والتأكيد والمعالجة؛ لا تحتاج إلى أمر تقني.", "docs_title": "أدوات PDF / Word", "docs_body": "اختر أداة وأرسل الملف أو الصورة المطلوبة ثم أكد قبل المعالجة. إرسال الملفات واحدًا تلو الآخر أكثر أمانًا من الألبومات.", "translation_title": "مركز ترجمة TOAN AAS", "translation_body": "اختر نوع المحتوى الذي تريد ترجمته.", "translation_language_title": "ترجمة اللغات", "translation_language_body": "اختر وضع الترجمة. ترجمة النص القصير لا تخصم Xu؛ ويتم التحقق من الصوت والملفات الطويلة وTTS قبل المعالجة.", "audio_media_title": "صوت / وسائط", "audio_media_body": "انسخ الصوت أو الفيديو إلى نص، أو أنشئ صوتًا/TTS للمحتوى. أرسل رسالة صوتية أو ملفًا صوتيًا أو فيديو عند تفعيل الأداة.", "profile_title": "الحساب", "profile_body": "استخدم /profile لعرض الرصيد والمستوى ومعلومات الحساب.", "video_menu_title": "فيديو TOAN AAS", "video_menu_body": "اختر أداة الفيديو التي تريد استخدامها."},
    "ru": {"memory_title": "Заметки / Документы", "memory_body": "Сохраняйте здесь заметки, напоминания, списки и личные документы. Инструменты документов проведут через загрузку, подтверждение и обработку; технические команды не нужны.", "docs_title": "Инструменты PDF / Word", "docs_body": "Выберите инструмент, отправьте нужный файл или изображение, затем подтвердите обработку. Отправлять файлы по одному безопаснее, чем альбомами.", "translation_title": "Центр перевода TOAN AAS", "translation_body": "Выберите тип контента для перевода.", "translation_language_title": "Перевод языков", "translation_language_body": "Выберите режим перевода. Короткий текст не списывает Xu; голос, аудио, длинные документы и TTS проверяются перед обработкой.", "audio_media_title": "Голос / Медиа", "audio_media_body": "Расшифруйте аудио или видео либо создайте голос/TTS для контента. При включённом инструменте отправьте голосовое, аудио или видео.", "profile_title": "Аккаунт", "profile_body": "Используйте /profile, чтобы увидеть баланс, уровень и данные аккаунта.", "video_menu_title": "Видео TOAN AAS", "video_menu_body": "Выберите инструмент видео, который хотите использовать."},
    "tr": {"memory_title": "Notlar / Belgeler", "memory_body": "Notları, hatırlatıcıları, kontrol listelerini ve kişisel belgeleri burada saklayın. Belge araçları yükleme, onay ve işlem adımlarını yönlendirir; teknik komut gerekmez.", "docs_title": "PDF / Word araçları", "docs_body": "Bir araç seçin, istenen dosya veya görseli gönderin, ardından işlemden önce onaylayın. Dosyaları tek tek göndermek albümlerden daha güvenlidir.", "translation_title": "TOAN AAS Çeviri Merkezi", "translation_body": "Çevirmek istediğiniz içerik türünü seçin.", "translation_language_title": "Dil çevirisi", "translation_language_body": "Bir çeviri modu seçin. Kısa metin çevirisi Xu kesmez; ses, ses dosyaları, uzun belgeler ve TTS işlemden önce kontrol edilir.", "audio_media_title": "Ses / Medya", "audio_media_body": "Ses veya videoyu yazıya dökün ya da içerik için ses/TTS oluşturun. Araç etkinse sesli mesaj, ses veya video gönderin.", "profile_title": "Hesap", "profile_body": "Bakiye, seviye ve hesap bilgilerini görmek için /profile kullanın.", "video_menu_title": "TOAN AAS Videosu", "video_menu_body": "Kullanmak istediğiniz video aracını seçin."},
    "th": {"memory_title": "บันทึก / เอกสาร", "memory_body": "บันทึกโน้ต การเตือนความจำ เช็กลิสต์ และเอกสารส่วนตัวไว้ที่นี่ เครื่องมือเอกสารจะแนะนำการอัปโหลด การยืนยัน และการประมวลผล โดยไม่ต้องใช้คำสั่งทางเทคนิค", "docs_title": "เครื่องมือ PDF / Word", "docs_body": "เลือกเครื่องมือ ส่งไฟล์หรือรูปภาพที่ระบบขอ แล้วกดยืนยันก่อนประมวลผล การส่งไฟล์ทีละไฟล์ปลอดภัยกว่าอัลบั้ม", "translation_title": "ศูนย์แปล TOAN AAS", "translation_body": "เลือกประเภทเนื้อหาที่ต้องการแปล", "translation_language_title": "แปลภาษา", "translation_language_body": "เลือกโหมดการแปล การแปลข้อความสั้นไม่หัก Xu; เสียง ไฟล์เสียง เอกสารยาว และ TTS จะถูกตรวจสอบก่อนประมวลผล", "audio_media_title": "เสียง / สื่อ", "audio_media_body": "ถอดเสียงจากไฟล์เสียงหรือวิดีโอ หรือสร้างเสียง/TTS สำหรับเนื้อหา ส่งข้อความเสียง ไฟล์เสียง หรือวิดีโอเมื่อเครื่องมือเปิดใช้งาน", "profile_title": "บัญชี", "profile_body": "ใช้ /profile เพื่อดูยอดคงเหลือ ระดับ และข้อมูลบัญชี", "video_menu_title": "วิดีโอ TOAN AAS", "video_menu_body": "เลือกเครื่องมือวิดีโอที่ต้องการใช้"},
    "fil": {"memory_title": "Mga tala / Dokumento", "memory_body": "I-save rito ang mga tala, paalala, checklist at personal na dokumento. Gagabayan ng mga tool sa dokumento ang pag-upload, kumpirmasyon at pagproseso; walang teknikal na command na kailangan.", "docs_title": "Mga tool sa PDF / Word", "docs_body": "Pumili ng tool, ipadala ang hinihinging file o larawan, pagkatapos ay kumpirmahin bago iproseso. Mas ligtas ang pagpapadala ng file nang paisa-isa kaysa album.", "translation_title": "Sentro ng pagsasalin ng TOAN AAS", "translation_body": "Piliin ang uri ng nilalamang nais isalin.", "translation_language_title": "Pagsasalin ng wika", "translation_language_body": "Pumili ng translation mode. Hindi nababawasan ang Xu sa maikling text; sinusuri ang boses, audio, mahabang dokumento at TTS bago iproseso.", "audio_media_title": "Boses / Media", "audio_media_body": "I-transcribe ang audio o video, o gumawa ng boses/TTS para sa nilalaman. Magpadala ng voice, audio o video kapag aktibo ang tool.", "profile_title": "Account", "profile_body": "Gamitin ang /profile upang makita ang balanse, antas at impormasyon ng account.", "video_menu_title": "Video ng TOAN AAS", "video_menu_body": "Piliin ang video tool na nais mong gamitin."},
    "it": {"memory_title": "Note / Documenti", "memory_body": "Salva qui note, promemoria, checklist e documenti personali. Gli strumenti per documenti guidano caricamento, conferma ed elaborazione; non serve alcun comando tecnico.", "docs_title": "Strumenti PDF / Word", "docs_body": "Scegli uno strumento, invia il file o l’immagine richiesta, poi conferma prima dell’elaborazione. Inviare i file uno alla volta è più sicuro degli album.", "translation_title": "Centro traduzioni TOAN AAS", "translation_body": "Scegli il tipo di contenuto da tradurre.", "translation_language_title": "Traduzione linguistica", "translation_language_body": "Scegli una modalità di traduzione. La traduzione di testo breve non addebita Xu; voce, audio, documenti lunghi e TTS vengono controllati prima dell’elaborazione.", "audio_media_title": "Voce / Media", "audio_media_body": "Trascrivi audio o video oppure crea voce/TTS per i contenuti. Quando lo strumento è attivo, invia un vocale, audio o video.", "profile_title": "Account", "profile_body": "Usa /profile per vedere saldo, livello e informazioni dell’account.", "video_menu_title": "Video TOAN AAS", "video_menu_body": "Scegli lo strumento video da usare."},
    "id": {"memory_title": "Catatan / Dokumen", "memory_body": "Simpan catatan, pengingat, daftar periksa, dan dokumen pribadi di sini. Alat dokumen memandu unggah, konfirmasi, dan pemrosesan; tidak memerlukan perintah teknis.", "docs_title": "Alat PDF / Word", "docs_body": "Pilih alat, kirim file atau gambar yang diminta, lalu konfirmasi sebelum diproses. Mengirim file satu per satu lebih aman daripada album.", "translation_title": "Pusat terjemahan TOAN AAS", "translation_body": "Pilih jenis konten yang ingin diterjemahkan.", "translation_language_title": "Terjemahan bahasa", "translation_language_body": "Pilih mode terjemahan. Terjemahan teks pendek tidak memotong Xu; suara, audio, dokumen panjang, dan TTS diperiksa sebelum pemrosesan.", "audio_media_title": "Suara / Media", "audio_media_body": "Transkripsikan audio atau video, atau buat suara/TTS untuk konten. Kirim pesan suara, audio, atau video saat alat aktif.", "profile_title": "Akun", "profile_body": "Gunakan /profile untuk melihat saldo, level, dan informasi akun.", "video_menu_title": "Video TOAN AAS", "video_menu_body": "Pilih alat video yang ingin digunakan."},
}


_PUBLIC_ROOT_ACTION_COPY = {
    "vi": {"image_quick": "Tạo ảnh nhanh", "image_prompt_from_image": "Tạo prompt từ ảnh", "image_ai_edit": "Chỉnh sửa AI", "image_edit": "Chỉnh sửa ảnh", "notes_create": "Tạo ghi chú", "notes_saved": "Ghi chú đã lưu", "notes_reminder": "Nhắc hẹn", "notes_save_document": "Lưu tài liệu", "notes_search": "Tìm ghi chú", "notes_delete": "Xóa ghi chú", "notes_storage": "Dung lượng của tôi", "notes_add_storage": "Mua thêm dung lượng", "notes_clean_files": "Dọn file cũ", "docs_tools": "Công cụ PDF / Word", "docs_pdf_to_word": "PDF sang Word", "docs_image_to_pdf": "Ảnh sang PDF", "docs_compress_pdf": "Nén PDF", "docs_split_pdf": "Tách PDF", "docs_merge_pdf": "Gộp PDF", "docs_all_tools": "Tất cả công cụ", "translation_language": "Dịch ngôn ngữ", "translation_subtitle_dubbing": "Phụ đề / Lồng tiếng", "translation_text": "Văn bản", "translation_file": "Dịch file", "translation_audio": "Dịch audio", "translation_conversation": "Hội thoại", "translation_two_way": "Dịch 2 chiều", "translation_auto": "Dịch tự động", "translation_languages": "Ngôn ngữ", "translation_stop": "Tắt dịch tự động", "feedback_payment_topup": "Nạp Xu / Thanh toán", "feedback_image_error": "Lỗi ảnh", "feedback_video_error": "Lỗi video", "feedback_document_pdf": "Tài liệu / PDF", "feedback_package_combo": "Gói / Combo", "feedback_refund": "Xu / Hoàn tiền", "feedback_feature_request": "Góp ý tính năng", "feedback_other": "Vấn đề khác"},
    "en": {"image_quick": "Quick image", "image_prompt_from_image": "Prompt from image", "image_ai_edit": "AI edit", "image_edit": "Edit image", "notes_create": "Create note", "notes_saved": "Saved notes", "notes_reminder": "Reminder", "notes_save_document": "Save document", "notes_search": "Search notes", "notes_delete": "Delete note", "notes_storage": "My storage", "notes_add_storage": "Add storage", "notes_clean_files": "Clean old files", "docs_tools": "PDF / Word tools", "docs_pdf_to_word": "PDF to Word", "docs_image_to_pdf": "Image to PDF", "docs_compress_pdf": "Compress PDF", "docs_split_pdf": "Split PDF", "docs_merge_pdf": "Merge PDF", "docs_all_tools": "All document tools", "translation_language": "Language translation", "translation_subtitle_dubbing": "Subtitles / dubbing", "translation_text": "Text", "translation_file": "Translate file", "translation_audio": "Translate audio", "translation_conversation": "Conversation", "translation_two_way": "Two-way", "translation_auto": "Auto translate", "translation_languages": "Languages", "translation_stop": "Stop auto translate", "feedback_payment_topup": "Top-up / payment", "feedback_image_error": "Image issue", "feedback_video_error": "Video issue", "feedback_document_pdf": "Document / PDF", "feedback_package_combo": "Package / combo", "feedback_refund": "Xu / refund", "feedback_feature_request": "Feature feedback", "feedback_other": "Other issue"},
    "zh": {"image_quick": "快速创建图片", "image_prompt_from_image": "从图片生成提示词", "image_ai_edit": "AI 编辑", "image_edit": "编辑图片", "notes_create": "创建笔记", "notes_saved": "已保存笔记", "notes_reminder": "提醒", "notes_save_document": "保存文档", "notes_search": "搜索笔记", "notes_delete": "删除笔记", "notes_storage": "我的存储", "notes_add_storage": "添加存储空间", "notes_clean_files": "清理旧文件", "docs_tools": "PDF / Word 工具", "docs_pdf_to_word": "PDF 转 Word", "docs_image_to_pdf": "图片转 PDF", "docs_compress_pdf": "压缩 PDF", "docs_split_pdf": "拆分 PDF", "docs_merge_pdf": "合并 PDF", "docs_all_tools": "所有文档工具", "translation_language": "语言翻译", "translation_subtitle_dubbing": "字幕 / 配音", "translation_text": "文本", "translation_file": "翻译文件", "translation_audio": "翻译音频", "translation_conversation": "对话", "translation_two_way": "双向翻译", "translation_auto": "自动翻译", "translation_languages": "语言", "translation_stop": "停止自动翻译", "feedback_payment_topup": "充值 / 付款", "feedback_image_error": "图片问题", "feedback_video_error": "视频问题", "feedback_document_pdf": "文档 / PDF", "feedback_package_combo": "套餐 / 组合", "feedback_refund": "Xu / 退款", "feedback_feature_request": "功能建议", "feedback_other": "其他问题"},
}


_PUBLIC_ROOT_ACTION_COPY.update({
    "es": {"image_quick": "Crear imagen rápida", "image_prompt_from_image": "Prompt desde imagen", "image_ai_edit": "Editar con IA", "image_edit": "Editar imagen", "notes_create": "Crear nota", "notes_saved": "Notas guardadas", "notes_reminder": "Recordatorio", "notes_save_document": "Guardar documento", "notes_search": "Buscar notas", "notes_delete": "Eliminar nota", "notes_storage": "Mi almacenamiento", "notes_add_storage": "Añadir almacenamiento", "notes_clean_files": "Limpiar archivos antiguos", "docs_tools": "Herramientas PDF / Word", "docs_pdf_to_word": "PDF a Word", "docs_image_to_pdf": "Imagen a PDF", "docs_compress_pdf": "Comprimir PDF", "docs_split_pdf": "Dividir PDF", "docs_merge_pdf": "Combinar PDF", "docs_all_tools": "Todas las herramientas", "translation_language": "Traducción de idiomas", "translation_subtitle_dubbing": "Subtítulos / doblaje", "translation_text": "Texto", "translation_file": "Traducir archivo", "translation_audio": "Traducir audio", "translation_conversation": "Conversación", "translation_two_way": "Dos direcciones", "translation_auto": "Traducción automática", "translation_languages": "Idiomas", "translation_stop": "Detener traducción automática", "feedback_payment_topup": "Recarga / pago", "feedback_image_error": "Problema de imagen", "feedback_video_error": "Problema de vídeo", "feedback_document_pdf": "Documento / PDF", "feedback_package_combo": "Paquete / combo", "feedback_refund": "Xu / reembolso", "feedback_feature_request": "Sugerencia de función", "feedback_other": "Otro problema"},
    "pt": {"image_quick": "Criar imagem rápida", "image_prompt_from_image": "Prompt a partir da imagem", "image_ai_edit": "Editar com IA", "image_edit": "Editar imagem", "notes_create": "Criar nota", "notes_saved": "Notas salvas", "notes_reminder": "Lembrete", "notes_save_document": "Salvar documento", "notes_search": "Pesquisar notas", "notes_delete": "Excluir nota", "notes_storage": "Meu armazenamento", "notes_add_storage": "Adicionar armazenamento", "notes_clean_files": "Limpar arquivos antigos", "docs_tools": "Ferramentas PDF / Word", "docs_pdf_to_word": "PDF para Word", "docs_image_to_pdf": "Imagem para PDF", "docs_compress_pdf": "Compactar PDF", "docs_split_pdf": "Dividir PDF", "docs_merge_pdf": "Mesclar PDF", "docs_all_tools": "Todas as ferramentas", "translation_language": "Tradução de idiomas", "translation_subtitle_dubbing": "Legendas / dublagem", "translation_text": "Texto", "translation_file": "Traduzir arquivo", "translation_audio": "Traduzir áudio", "translation_conversation": "Conversa", "translation_two_way": "Duas vias", "translation_auto": "Tradução automática", "translation_languages": "Idiomas", "translation_stop": "Parar tradução automática", "feedback_payment_topup": "Recarga / pagamento", "feedback_image_error": "Problema de imagem", "feedback_video_error": "Problema de vídeo", "feedback_document_pdf": "Documento / PDF", "feedback_package_combo": "Pacote / combo", "feedback_refund": "Xu / reembolso", "feedback_feature_request": "Sugestão de recurso", "feedback_other": "Outro problema"},
    "fr": {"image_quick": "Créer une image rapide", "image_prompt_from_image": "Prompt depuis une image", "image_ai_edit": "Modifier avec l’IA", "image_edit": "Modifier l’image", "notes_create": "Créer une note", "notes_saved": "Notes enregistrées", "notes_reminder": "Rappel", "notes_save_document": "Enregistrer le document", "notes_search": "Rechercher des notes", "notes_delete": "Supprimer la note", "notes_storage": "Mon stockage", "notes_add_storage": "Ajouter du stockage", "notes_clean_files": "Nettoyer les anciens fichiers", "docs_tools": "Outils PDF / Word", "docs_pdf_to_word": "PDF vers Word", "docs_image_to_pdf": "Image vers PDF", "docs_compress_pdf": "Compresser le PDF", "docs_split_pdf": "Scinder le PDF", "docs_merge_pdf": "Fusionner les PDF", "docs_all_tools": "Tous les outils", "translation_language": "Traduction linguistique", "translation_subtitle_dubbing": "Sous-titres / doublage", "translation_text": "Texte", "translation_file": "Traduire un fichier", "translation_audio": "Traduire l’audio", "translation_conversation": "Conversation", "translation_two_way": "Double sens", "translation_auto": "Traduction automatique", "translation_languages": "Langues", "translation_stop": "Arrêter la traduction automatique", "feedback_payment_topup": "Recharge / paiement", "feedback_image_error": "Problème d’image", "feedback_video_error": "Problème vidéo", "feedback_document_pdf": "Document / PDF", "feedback_package_combo": "Forfait / combo", "feedback_refund": "Xu / remboursement", "feedback_feature_request": "Suggestion de fonction", "feedback_other": "Autre problème"},
    "de": {"image_quick": "Schnelles Bild erstellen", "image_prompt_from_image": "Prompt aus Bild", "image_ai_edit": "Mit KI bearbeiten", "image_edit": "Bild bearbeiten", "notes_create": "Notiz erstellen", "notes_saved": "Gespeicherte Notizen", "notes_reminder": "Erinnerung", "notes_save_document": "Dokument speichern", "notes_search": "Notizen suchen", "notes_delete": "Notiz löschen", "notes_storage": "Mein Speicher", "notes_add_storage": "Speicher hinzufügen", "notes_clean_files": "Alte Dateien bereinigen", "docs_tools": "PDF / Word-Werkzeuge", "docs_pdf_to_word": "PDF zu Word", "docs_image_to_pdf": "Bild zu PDF", "docs_compress_pdf": "PDF komprimieren", "docs_split_pdf": "PDF teilen", "docs_merge_pdf": "PDF zusammenführen", "docs_all_tools": "Alle Werkzeuge", "translation_language": "Sprachübersetzung", "translation_subtitle_dubbing": "Untertitel / Synchronisation", "translation_text": "Text", "translation_file": "Datei übersetzen", "translation_audio": "Audio übersetzen", "translation_conversation": "Gespräch", "translation_two_way": "Zwei Wege", "translation_auto": "Automatisch übersetzen", "translation_languages": "Sprachen", "translation_stop": "Automatische Übersetzung stoppen", "feedback_payment_topup": "Aufladung / Zahlung", "feedback_image_error": "Bildproblem", "feedback_video_error": "Videoproblem", "feedback_document_pdf": "Dokument / PDF", "feedback_package_combo": "Paket / Kombi", "feedback_refund": "Xu / Erstattung", "feedback_feature_request": "Funktionsvorschlag", "feedback_other": "Anderes Problem"},
    "ja": {"image_quick": "画像をすばやく作成", "image_prompt_from_image": "画像からプロンプト", "image_ai_edit": "AIで編集", "image_edit": "画像を編集", "notes_create": "メモを作成", "notes_saved": "保存済みメモ", "notes_reminder": "リマインダー", "notes_save_document": "文書を保存", "notes_search": "メモを検索", "notes_delete": "メモを削除", "notes_storage": "自分のストレージ", "notes_add_storage": "ストレージを追加", "notes_clean_files": "古いファイルを整理", "docs_tools": "PDF / Word ツール", "docs_pdf_to_word": "PDFをWordへ", "docs_image_to_pdf": "画像をPDFへ", "docs_compress_pdf": "PDFを圧縮", "docs_split_pdf": "PDFを分割", "docs_merge_pdf": "PDFを結合", "docs_all_tools": "すべての文書ツール", "translation_language": "言語翻訳", "translation_subtitle_dubbing": "字幕 / 吹き替え", "translation_text": "テキスト", "translation_file": "ファイルを翻訳", "translation_audio": "音声を翻訳", "translation_conversation": "会話", "translation_two_way": "双方向", "translation_auto": "自動翻訳", "translation_languages": "言語", "translation_stop": "自動翻訳を停止", "feedback_payment_topup": "チャージ / 支払い", "feedback_image_error": "画像の問題", "feedback_video_error": "動画の問題", "feedback_document_pdf": "文書 / PDF", "feedback_package_combo": "パッケージ / コンボ", "feedback_refund": "Xu / 返金", "feedback_feature_request": "機能の提案", "feedback_other": "その他の問題"},
    "ko": {"image_quick": "빠른 이미지 만들기", "image_prompt_from_image": "이미지에서 프롬프트", "image_ai_edit": "AI로 편집", "image_edit": "이미지 편집", "notes_create": "메모 만들기", "notes_saved": "저장된 메모", "notes_reminder": "알림", "notes_save_document": "문서 저장", "notes_search": "메모 검색", "notes_delete": "메모 삭제", "notes_storage": "내 저장 공간", "notes_add_storage": "저장 공간 추가", "notes_clean_files": "오래된 파일 정리", "docs_tools": "PDF / Word 도구", "docs_pdf_to_word": "PDF를 Word로", "docs_image_to_pdf": "이미지를 PDF로", "docs_compress_pdf": "PDF 압축", "docs_split_pdf": "PDF 분할", "docs_merge_pdf": "PDF 합치기", "docs_all_tools": "모든 문서 도구", "translation_language": "언어 번역", "translation_subtitle_dubbing": "자막 / 더빙", "translation_text": "텍스트", "translation_file": "파일 번역", "translation_audio": "오디오 번역", "translation_conversation": "대화", "translation_two_way": "양방향", "translation_auto": "자동 번역", "translation_languages": "언어", "translation_stop": "자동 번역 중지", "feedback_payment_topup": "충전 / 결제", "feedback_image_error": "이미지 문제", "feedback_video_error": "동영상 문제", "feedback_document_pdf": "문서 / PDF", "feedback_package_combo": "패키지 / 콤보", "feedback_refund": "Xu / 환불", "feedback_feature_request": "기능 제안", "feedback_other": "기타 문제"},
})


_PUBLIC_INTERNATIONAL_SUPPORT_COPY = {
    "es": {"support_title": "Ayuda de TOAN AAS", "support_body": "Contacta con el equipo, crea un ticket de ayuda, revisa tus tickets o solicita asesoramiento. No envíes contraseñas, OTP, códigos privados ni datos de tarjeta."},
    "pt": {"support_title": "Suporte TOAN AAS", "support_body": "Entre em contato com a equipe, crie um ticket de suporte, veja seus tickets ou peça orientação. Não envie senhas, OTPs, códigos privados ou dados de cartão."},
    "fr": {"support_title": "Assistance TOAN AAS", "support_body": "Contactez l’équipe, créez un ticket, consultez vos tickets ou demandez conseil. N’envoyez jamais de mot de passe, OTP, code privé ou donnée bancaire."},
    "de": {"support_title": "TOAN AAS Support", "support_body": "Kontaktiere das Team, erstelle ein Support-Ticket, sieh deine Tickets an oder fordere Beratung an. Sende keine Passwörter, OTPs, privaten Codes oder Kartendaten."},
    "ja": {"support_title": "TOAN AAS サポート", "support_body": "チームへの連絡、サポートチケットの作成、チケット確認、相談依頼ができます。パスワード、OTP、秘密コード、カード情報は送信しないでください。"},
    "ko": {"support_title": "TOAN AAS 지원", "support_body": "팀에 문의하고, 지원 티켓을 만들거나, 내 티켓을 확인하고, 상담을 요청할 수 있습니다. 비밀번호, OTP, 개인 코드 또는 카드 정보를 보내지 마세요."},
    "hi": {"support_title": "TOAN AAS सहायता", "support_body": "टीम से संपर्क करें, सहायता टिकट बनाएं, अपने टिकट देखें या परामर्श मांगें। पासवर्ड, OTP, निजी कोड या कार्ड जानकारी न भेजें।"},
    "ar": {"support_title": "دعم TOAN AAS", "support_body": "تواصل مع الفريق أو أنشئ تذكرة دعم أو راجع تذاكرك أو اطلب استشارة. لا ترسل كلمات المرور أو رموز OTP أو الرموز الخاصة أو معلومات البطاقة."},
    "ru": {"support_title": "Поддержка TOAN AAS", "support_body": "Свяжитесь с командой, создайте обращение, просмотрите свои обращения или запросите консультацию. Не отправляйте пароли, OTP, приватные коды или данные карты."},
    "tr": {"support_title": "TOAN AAS Desteği", "support_body": "Ekiple iletişime geçin, destek talebi oluşturun, taleplerinizi inceleyin veya danışmanlık isteyin. Parola, OTP, özel kod veya kart bilgisi göndermeyin."},
    "th": {"support_title": "การช่วยเหลือ TOAN AAS", "support_body": "ติดต่อทีม สร้างทิกเก็ตช่วยเหลือ ดูทิกเก็ตของคุณ หรือขอคำปรึกษาได้ อย่าส่งรหัสผ่าน OTP รหัสส่วนตัว หรือข้อมูลบัตร"},
    "fil": {"support_title": "Suporta ng TOAN AAS", "support_body": "Makipag-ugnayan sa team, gumawa ng support ticket, tingnan ang iyong mga ticket, o humingi ng gabay. Huwag magpadala ng password, OTP, pribadong code o detalye ng card."},
    "it": {"support_title": "Assistenza TOAN AAS", "support_body": "Contatta il team, crea un ticket di assistenza, consulta i tuoi ticket o chiedi una consulenza. Non inviare password, OTP, codici privati o dati della carta."},
    "id": {"support_title": "Dukungan TOAN AAS", "support_body": "Hubungi tim, buat tiket dukungan, lihat tiket Anda, atau minta konsultasi. Jangan kirim kata sandi, OTP, kode pribadi, atau informasi kartu."},
}

# Root Support actions are merged into the already-native title/body records.
# The keys below are display-only; category IDs and callback data remain
# canonical so ticket routing and saved support data cannot change by locale.
for _locale, _support_actions in {
    "es": {"support_admin": "Escribir al administrador", "support_ticket": "Crear ticket de ayuda", "support_my_tickets": "Mis tickets", "support_auto": "Soporte automático"},
    "pt": {"support_admin": "Falar com o administrador", "support_ticket": "Criar ticket de suporte", "support_my_tickets": "Meus tickets", "support_auto": "Suporte automático"},
    "fr": {"support_admin": "Écrire à l’administrateur", "support_ticket": "Créer un ticket", "support_my_tickets": "Mes tickets", "support_auto": "Assistance automatique"},
    "de": {"support_admin": "Admin kontaktieren", "support_ticket": "Support-Ticket erstellen", "support_my_tickets": "Meine Tickets", "support_auto": "Automatischer Support"},
    "ja": {"support_admin": "管理者に連絡", "support_ticket": "サポートチケットを作成", "support_my_tickets": "マイチケット", "support_auto": "自動サポート"},
    "ko": {"support_admin": "관리자에게 문의", "support_ticket": "지원 티켓 만들기", "support_my_tickets": "내 티켓", "support_auto": "자동 지원"},
    "hi": {"support_admin": "एडमिन को संदेश भेजें", "support_ticket": "सहायता टिकट बनाएँ", "support_my_tickets": "मेरे टिकट", "support_auto": "स्वचालित सहायता"},
    "ar": {"support_admin": "مراسلة المشرف", "support_ticket": "إنشاء تذكرة دعم", "support_my_tickets": "تذاكري", "support_auto": "دعم تلقائي"},
    "ru": {"support_admin": "Написать администратору", "support_ticket": "Создать обращение", "support_my_tickets": "Мои обращения", "support_auto": "Автоподдержка"},
    "tr": {"support_admin": "Yöneticiye yaz", "support_ticket": "Destek talebi oluştur", "support_my_tickets": "Taleplerim", "support_auto": "Otomatik destek"},
    "th": {"support_admin": "ติดต่อผู้ดูแล", "support_ticket": "สร้างทิกเก็ตช่วยเหลือ", "support_my_tickets": "ทิกเก็ตของฉัน", "support_auto": "ช่วยเหลืออัตโนมัติ"},
    "fil": {"support_admin": "Mensahe sa admin", "support_ticket": "Gumawa ng support ticket", "support_my_tickets": "Mga ticket ko", "support_auto": "Awtomatikong suporta"},
    "it": {"support_admin": "Scrivi all’amministratore", "support_ticket": "Crea ticket di assistenza", "support_my_tickets": "I miei ticket", "support_auto": "Assistenza automatica"},
    "id": {"support_admin": "Hubungi admin", "support_ticket": "Buat tiket dukungan", "support_my_tickets": "Tiket saya", "support_auto": "Dukungan otomatis"},
}.items():
    _PUBLIC_INTERNATIONAL_SUPPORT_COPY[_locale].update(_support_actions)


_PUBLIC_ROOT_ACTION_COPY.update({
    "fil": {"image_quick": "Mabilis na gumawa ng larawan", "image_prompt_from_image": "Prompt mula sa larawan", "image_ai_edit": "Pag-edit gamit ang AI", "image_edit": "I-edit ang larawan", "notes_create": "Gumawa ng tala", "notes_saved": "Mga naka-save na tala", "notes_reminder": "Paalala", "notes_save_document": "I-save ang dokumento", "notes_search": "Maghanap ng mga tala", "notes_delete": "Tanggalin ang tala", "notes_storage": "Aking storage", "notes_add_storage": "Magdagdag ng storage", "notes_clean_files": "Linisin ang lumang file", "docs_tools": "Mga tool sa PDF / Word", "docs_pdf_to_word": "PDF patungong Word", "docs_image_to_pdf": "Larawan patungong PDF", "docs_compress_pdf": "I-compress ang PDF", "docs_split_pdf": "Hatiin ang PDF", "docs_merge_pdf": "Pagsamahin ang PDF", "docs_all_tools": "Lahat ng tool sa dokumento", "translation_language": "Pagsasalin ng wika", "translation_subtitle_dubbing": "Mga subtitle / dubbing", "translation_text": "Teksto", "translation_file": "Isalin ang file", "translation_audio": "Isalin ang audio", "translation_conversation": "Usapan", "translation_two_way": "Dalawang direksyon", "translation_auto": "Awtomatikong pagsasalin", "translation_languages": "Mga wika", "translation_stop": "Ihinto ang awtomatikong pagsasalin", "feedback_payment_topup": "Top-up / bayad", "feedback_image_error": "Problema sa larawan", "feedback_video_error": "Problema sa bidyo", "feedback_document_pdf": "Dokumento / PDF", "feedback_package_combo": "Package / combo", "feedback_refund": "Xu / refund", "feedback_feature_request": "Mungkahi sa feature", "feedback_other": "Ibang problema"},
    "it": {"image_quick": "Crea immagine rapida", "image_prompt_from_image": "Prompt da immagine", "image_ai_edit": "Modifica IA", "image_edit": "Modifica immagine", "notes_create": "Crea nota", "notes_saved": "Note salvate", "notes_reminder": "Promemoria", "notes_save_document": "Salva documento", "notes_search": "Cerca note", "notes_delete": "Elimina nota", "notes_storage": "Il mio spazio", "notes_add_storage": "Aggiungi spazio", "notes_clean_files": "Pulisci file vecchi", "docs_tools": "Strumenti PDF / Word", "docs_pdf_to_word": "PDF in Word", "docs_image_to_pdf": "Immagine in PDF", "docs_compress_pdf": "Comprimi PDF", "docs_split_pdf": "Dividi PDF", "docs_merge_pdf": "Unisci PDF", "docs_all_tools": "Tutti gli strumenti documento", "translation_language": "Traduzione linguistica", "translation_subtitle_dubbing": "Sottotitoli / doppiaggio", "translation_text": "Testo", "translation_file": "Traduci file", "translation_audio": "Traduci audio", "translation_conversation": "Conversazione", "translation_two_way": "Bidirezionale", "translation_auto": "Traduzione automatica", "translation_languages": "Lingue", "translation_stop": "Interrompi traduzione automatica", "feedback_payment_topup": "Ricarica / pagamento", "feedback_image_error": "Problema immagine", "feedback_video_error": "Problema video", "feedback_document_pdf": "Documento / PDF", "feedback_package_combo": "Pacchetto / combo", "feedback_refund": "Xu / rimborso", "feedback_feature_request": "Suggerimento funzione", "feedback_other": "Altro problema"},
    "id": {"image_quick": "Buat gambar cepat", "image_prompt_from_image": "Prompt dari gambar", "image_ai_edit": "Edit dengan AI", "image_edit": "Edit gambar", "notes_create": "Buat catatan", "notes_saved": "Catatan tersimpan", "notes_reminder": "Pengingat", "notes_save_document": "Simpan dokumen", "notes_search": "Cari catatan", "notes_delete": "Hapus catatan", "notes_storage": "Penyimpanan saya", "notes_add_storage": "Tambah penyimpanan", "notes_clean_files": "Bersihkan file lama", "docs_tools": "Alat PDF / Word", "docs_pdf_to_word": "PDF ke Word", "docs_image_to_pdf": "Gambar ke PDF", "docs_compress_pdf": "Kompres PDF", "docs_split_pdf": "Pisahkan PDF", "docs_merge_pdf": "Gabungkan PDF", "docs_all_tools": "Semua alat dokumen", "translation_language": "Terjemahan bahasa", "translation_subtitle_dubbing": "Subtitle / sulih suara", "translation_text": "Teks", "translation_file": "Terjemahkan file", "translation_audio": "Terjemahkan audio", "translation_conversation": "Percakapan", "translation_two_way": "Dua arah", "translation_auto": "Terjemahan otomatis", "translation_languages": "Bahasa", "translation_stop": "Hentikan terjemahan otomatis", "feedback_payment_topup": "Isi ulang / pembayaran", "feedback_image_error": "Masalah gambar", "feedback_video_error": "Masalah video", "feedback_document_pdf": "Dokumen / PDF", "feedback_package_combo": "Paket / kombo", "feedback_refund": "Xu / pengembalian dana", "feedback_feature_request": "Saran fitur", "feedback_other": "Masalah lain"},
})


_PUBLIC_ROOT_ACTION_COPY.update({
    "hi": {"image_quick": "त्वरित चित्र बनाएँ", "image_prompt_from_image": "चित्र से प्रॉम्प्ट", "image_ai_edit": "AI संपादन", "image_edit": "चित्र संपादित करें", "notes_create": "नोट बनाएँ", "notes_saved": "सहेजे गए नोट", "notes_reminder": "रिमाइंडर", "notes_save_document": "दस्तावेज़ सहेजें", "notes_search": "नोट खोजें", "notes_delete": "नोट हटाएँ", "notes_storage": "मेरा संग्रहण", "notes_add_storage": "संग्रहण जोड़ें", "notes_clean_files": "पुरानी फ़ाइलें साफ़ करें", "docs_tools": "PDF / Word उपकरण", "docs_pdf_to_word": "PDF से Word", "docs_image_to_pdf": "चित्र से PDF", "docs_compress_pdf": "PDF संपीड़ित करें", "docs_split_pdf": "PDF विभाजित करें", "docs_merge_pdf": "PDF मिलाएँ", "docs_all_tools": "सभी दस्तावेज़ उपकरण", "translation_language": "भाषा अनुवाद", "translation_subtitle_dubbing": "उपशीर्षक / डबिंग", "translation_text": "पाठ", "translation_file": "फ़ाइल अनुवाद", "translation_audio": "ऑडियो अनुवाद", "translation_conversation": "बातचीत", "translation_two_way": "दो-तरफ़ा", "translation_auto": "स्वतः अनुवाद", "translation_languages": "भाषाएँ", "translation_stop": "स्वतः अनुवाद रोकें", "feedback_payment_topup": "टॉप-अप / भुगतान", "feedback_image_error": "चित्र समस्या", "feedback_video_error": "वीडियो समस्या", "feedback_document_pdf": "दस्तावेज़ / PDF", "feedback_package_combo": "पैकेज / कॉम्बो", "feedback_refund": "Xu / धनवापसी", "feedback_feature_request": "सुविधा सुझाव", "feedback_other": "अन्य समस्या"},
    "ar": {"image_quick": "إنشاء صورة سريعة", "image_prompt_from_image": "إنشاء وصف من صورة", "image_ai_edit": "تحرير بالذكاء الاصطناعي", "image_edit": "تعديل الصورة", "notes_create": "إنشاء ملاحظة", "notes_saved": "الملاحظات المحفوظة", "notes_reminder": "تذكير", "notes_save_document": "حفظ مستند", "notes_search": "بحث في الملاحظات", "notes_delete": "حذف ملاحظة", "notes_storage": "مساحتي التخزينية", "notes_add_storage": "إضافة مساحة تخزين", "notes_clean_files": "تنظيف الملفات القديمة", "docs_tools": "أدوات PDF / Word", "docs_pdf_to_word": "تحويل PDF إلى Word", "docs_image_to_pdf": "تحويل صورة إلى PDF", "docs_compress_pdf": "ضغط PDF", "docs_split_pdf": "تقسيم PDF", "docs_merge_pdf": "دمج ملفات PDF", "docs_all_tools": "كل أدوات المستندات", "translation_language": "ترجمة اللغات", "translation_subtitle_dubbing": "ترجمة نصية / دبلجة", "translation_text": "نص", "translation_file": "ترجمة ملف", "translation_audio": "ترجمة الصوت", "translation_conversation": "محادثة", "translation_two_way": "ثنائي الاتجاه", "translation_auto": "ترجمة تلقائية", "translation_languages": "اللغات", "translation_stop": "إيقاف الترجمة التلقائية", "feedback_payment_topup": "شحن / دفع", "feedback_image_error": "مشكلة صورة", "feedback_video_error": "مشكلة فيديو", "feedback_document_pdf": "مستند / PDF", "feedback_package_combo": "باقة / مجموعة", "feedback_refund": "Xu / استرداد", "feedback_feature_request": "اقتراح ميزة", "feedback_other": "مشكلة أخرى"},
    "ru": {"image_quick": "Быстро создать изображение", "image_prompt_from_image": "Промпт по изображению", "image_ai_edit": "Редактирование ИИ", "image_edit": "Редактировать изображение", "notes_create": "Создать заметку", "notes_saved": "Сохранённые заметки", "notes_reminder": "Напоминание", "notes_save_document": "Сохранить документ", "notes_search": "Найти заметки", "notes_delete": "Удалить заметку", "notes_storage": "Моё хранилище", "notes_add_storage": "Добавить место", "notes_clean_files": "Очистить старые файлы", "docs_tools": "Инструменты PDF / Word", "docs_pdf_to_word": "PDF в Word", "docs_image_to_pdf": "Изображение в PDF", "docs_compress_pdf": "Сжать PDF", "docs_split_pdf": "Разделить PDF", "docs_merge_pdf": "Объединить PDF", "docs_all_tools": "Все инструменты документов", "translation_language": "Перевод языков", "translation_subtitle_dubbing": "Субтитры / дубляж", "translation_text": "Текст", "translation_file": "Перевести файл", "translation_audio": "Перевести аудио", "translation_conversation": "Разговор", "translation_two_way": "Двусторонний", "translation_auto": "Автоперевод", "translation_languages": "Языки", "translation_stop": "Остановить автоперевод", "feedback_payment_topup": "Пополнение / оплата", "feedback_image_error": "Проблема с изображением", "feedback_video_error": "Проблема с видео", "feedback_document_pdf": "Документ / PDF", "feedback_package_combo": "Пакет / комбо", "feedback_refund": "Xu / возврат", "feedback_feature_request": "Предложение функции", "feedback_other": "Другая проблема"},
    "tr": {"image_quick": "Hızlı görsel oluştur", "image_prompt_from_image": "Görselden prompt", "image_ai_edit": "Yapay zekâ ile düzenle", "image_edit": "Görseli düzenle", "notes_create": "Not oluştur", "notes_saved": "Kaydedilen notlar", "notes_reminder": "Hatırlatıcı", "notes_save_document": "Belge kaydet", "notes_search": "Notlarda ara", "notes_delete": "Notu sil", "notes_storage": "Depolama alanım", "notes_add_storage": "Depolama ekle", "notes_clean_files": "Eski dosyaları temizle", "docs_tools": "PDF / Word araçları", "docs_pdf_to_word": "PDF'den Word'e", "docs_image_to_pdf": "Görselden PDF'ye", "docs_compress_pdf": "PDF sıkıştır", "docs_split_pdf": "PDF böl", "docs_merge_pdf": "PDF'leri birleştir", "docs_all_tools": "Tüm belge araçları", "translation_language": "Dil çevirisi", "translation_subtitle_dubbing": "Altyazılar / dublaj", "translation_text": "Metin", "translation_file": "Dosya çevir", "translation_audio": "Ses çevir", "translation_conversation": "Konuşma", "translation_two_way": "Çift yönlü", "translation_auto": "Otomatik çeviri", "translation_languages": "Diller", "translation_stop": "Otomatik çeviriyi durdur", "feedback_payment_topup": "Yükleme / ödeme", "feedback_image_error": "Görsel sorunu", "feedback_video_error": "Video sorunu", "feedback_document_pdf": "Belge / PDF", "feedback_package_combo": "Paket / kombo", "feedback_refund": "Xu / iade", "feedback_feature_request": "Özellik önerisi", "feedback_other": "Diğer sorun"},
    "th": {"image_quick": "สร้างภาพด่วน", "image_prompt_from_image": "สร้างพรอมต์จากภาพ", "image_ai_edit": "แก้ไขด้วย AI", "image_edit": "แก้ไขภาพ", "notes_create": "สร้างบันทึก", "notes_saved": "บันทึกที่บันทึกไว้", "notes_reminder": "การแจ้งเตือน", "notes_save_document": "บันทึกเอกสาร", "notes_search": "ค้นหาบันทึก", "notes_delete": "ลบบันทึก", "notes_storage": "พื้นที่เก็บข้อมูลของฉัน", "notes_add_storage": "เพิ่มพื้นที่เก็บข้อมูล", "notes_clean_files": "ล้างไฟล์เก่า", "docs_tools": "เครื่องมือ PDF / Word", "docs_pdf_to_word": "แปลง PDF เป็น Word", "docs_image_to_pdf": "แปลงภาพเป็น PDF", "docs_compress_pdf": "บีบอัด PDF", "docs_split_pdf": "แยก PDF", "docs_merge_pdf": "รวม PDF", "docs_all_tools": "เครื่องมือเอกสารทั้งหมด", "translation_language": "แปลภาษา", "translation_subtitle_dubbing": "คำบรรยาย / พากย์", "translation_text": "ข้อความ", "translation_file": "แปลไฟล์", "translation_audio": "แปลเสียง", "translation_conversation": "การสนทนา", "translation_two_way": "สองทาง", "translation_auto": "แปลอัตโนมัติ", "translation_languages": "ภาษา", "translation_stop": "หยุดแปลอัตโนมัติ", "feedback_payment_topup": "เติมเงิน / ชำระเงิน", "feedback_image_error": "ปัญหาภาพ", "feedback_video_error": "ปัญหาวิดีโอ", "feedback_document_pdf": "เอกสาร / PDF", "feedback_package_combo": "แพ็กเกจ / คอมโบ", "feedback_refund": "Xu / คืนเงิน", "feedback_feature_request": "ข้อเสนอแนะฟีเจอร์", "feedback_other": "ปัญหาอื่น"},
})


# Feedback category selection is presentation-only.  The stable category codes
# remain owned by the ticket flow; this table only prevents a chosen customer
# locale from falling back to Vietnamese labels or an English prompt.
_PUBLIC_FEEDBACK_PROMPT_COPY = {
    "vi": {
        "feedback_prompt_title": "Nhóm góp ý",
        "feedback_prompt_body": "Bạn hãy gửi một tin nhắn mô tả lỗi/góp ý.\nNếu có, hãy kèm job ID, nút đã bấm hoặc màn hình đang dùng.\n\nTOAN AAS sẽ tạo ticket để admin kiểm tra. Bot chưa gọi AI/API và chưa trừ Xu.",
        "feedback_prompt_back": "Góp ý / Báo lỗi",
    },
    "en": {
        "feedback_prompt_title": "Feedback category",
        "feedback_prompt_body": "Please send one message describing the issue or suggestion.\nIf relevant, include the job ID, button name, or screen where it happened.\n\nTOAN AAS will create a ticket for admin review. The bot has not called AI/API and has not charged Xu.",
        "feedback_prompt_back": "Feedback / Report a bug",
    },
    "zh": {
        "feedback_prompt_title": "反馈类别",
        "feedback_prompt_body": "请发送一条消息说明问题或建议。\n如有，请附上任务 ID、所点击的按钮或出现问题的页面。\n\nTOAN AAS 会创建工单供管理员核查。机器人未调用 AI/API，也未扣除 Xu。",
        "feedback_prompt_back": "反馈 / 报错",
    },
    "es": {
        "feedback_prompt_title": "Categoría de comentarios",
        "feedback_prompt_body": "Envía un mensaje describiendo el problema o la sugerencia.\nSi corresponde, incluye el ID del trabajo, el botón pulsado o la pantalla donde ocurrió.\n\nTOAN AAS creará un ticket para que un administrador lo revise. El bot no ha llamado a IA/API ni cobrado Xu.",
        "feedback_prompt_back": "Opiniones / Informar de un error",
    },
    "pt": {
        "feedback_prompt_title": "Categoria de feedback",
        "feedback_prompt_body": "Envie uma mensagem descrevendo o problema ou a sugestão.\nSe for relevante, inclua o ID do trabalho, o botão pressionado ou a tela onde aconteceu.\n\nA TOAN AAS criará um ticket para análise do administrador. O bot não chamou IA/API nem cobrou Xu.",
        "feedback_prompt_back": "Comentários / Reportar erro",
    },
    "fr": {
        "feedback_prompt_title": "Catégorie de retour",
        "feedback_prompt_body": "Envoyez un message décrivant le problème ou la suggestion.\nSi utile, indiquez l’ID de tâche, le bouton utilisé ou l’écran concerné.\n\nTOAN AAS créera un ticket pour examen par un administrateur. Le bot n’a appelé ni IA/API ni débité de Xu.",
        "feedback_prompt_back": "Avis / Signaler un bug",
    },
    "de": {
        "feedback_prompt_title": "Feedback-Kategorie",
        "feedback_prompt_body": "Sende eine Nachricht mit einer Beschreibung des Problems oder Vorschlags.\nFalls vorhanden, nenne die Job-ID, den gedrückten Button oder den betroffenen Bildschirm.\n\nTOAN AAS erstellt ein Ticket zur Prüfung durch einen Admin. Der Bot hat keine KI/API aufgerufen und keine Xu belastet.",
        "feedback_prompt_back": "Feedback / Fehler melden",
    },
    "ja": {
        "feedback_prompt_title": "フィードバックの分類",
        "feedback_prompt_body": "問題またはご提案を説明するメッセージを1件送ってください。\n該当する場合は、ジョブ ID、押したボタン、または発生した画面を記載してください。\n\nTOAN AAS は管理者確認用のチケットを作成します。ボットは AI/API を呼び出しておらず、Xu も請求していません。",
        "feedback_prompt_back": "ご意見 / 不具合を報告",
    },
    "ko": {
        "feedback_prompt_title": "피드백 분류",
        "feedback_prompt_body": "문제 또는 제안을 설명하는 메시지 한 건을 보내 주세요.\n해당된다면 작업 ID, 누른 버튼 또는 문제가 발생한 화면을 함께 알려 주세요.\n\nTOAN AAS가 관리자의 검토를 위한 티켓을 만듭니다. 봇은 AI/API를 호출하지 않았고 Xu도 차감하지 않았습니다.",
        "feedback_prompt_back": "의견 / 오류 신고",
    },
    "hi": {
        "feedback_prompt_title": "प्रतिक्रिया श्रेणी",
        "feedback_prompt_body": "समस्या या सुझाव का वर्णन करने वाला एक संदेश भेजें।\nयदि लागू हो, तो जॉब ID, दबाया गया बटन या वह स्क्रीन शामिल करें जहाँ यह हुआ।\n\nTOAN AAS एडमिन की जाँच के लिए एक टिकट बनाएगा। बॉट ने AI/API को कॉल नहीं किया है और Xu नहीं काटे हैं।",
        "feedback_prompt_back": "सुझाव / त्रुटि रिपोर्ट",
    },
    "ar": {
        "feedback_prompt_title": "فئة الملاحظات",
        "feedback_prompt_body": "أرسل رسالة واحدة تشرح المشكلة أو الاقتراح.\nعند الإمكان، أرفق معرّف المهمة أو الزر الذي ضغطت عليه أو الشاشة التي ظهر فيها الأمر.\n\nسينشئ TOAN AAS تذكرة ليراجعها المشرف. لم يستدعِ البوت الذكاء الاصطناعي/API ولم يخصم Xu.",
        "feedback_prompt_back": "ملاحظات / بلاغ خطأ",
    },
    "ru": {
        "feedback_prompt_title": "Категория обратной связи",
        "feedback_prompt_body": "Отправьте одно сообщение с описанием проблемы или предложения.\nЕсли возможно, укажите ID задачи, нажатую кнопку или экран, где это произошло.\n\nTOAN AAS создаст тикет для проверки администратором. Бот не вызывал ИИ/API и не списывал Xu.",
        "feedback_prompt_back": "Отзыв / Сообщить об ошибке",
    },
    "tr": {
        "feedback_prompt_title": "Geri bildirim kategorisi",
        "feedback_prompt_body": "Sorunu veya öneriyi açıklayan tek bir mesaj gönderin.\nUygunsa iş kimliğini, bastığınız düğmeyi veya olayın yaşandığı ekranı ekleyin.\n\nTOAN AAS yönetici incelemesi için bir kayıt oluşturur. Bot AI/API çağırmadı ve Xu kesmedi.",
        "feedback_prompt_back": "Geri bildirim / Hata bildir",
    },
    "th": {
        "feedback_prompt_title": "หมวดหมู่ข้อเสนอแนะ",
        "feedback_prompt_body": "ส่งข้อความหนึ่งข้อความเพื่ออธิบายปัญหาหรือข้อเสนอแนะ\nหากมี โปรดระบุรหัสงาน ปุ่มที่กด หรือหน้าจอที่เกิดปัญหา\n\nTOAN AAS จะสร้างทิกเก็ตให้ผู้ดูแลตรวจสอบ บอตยังไม่ได้เรียก AI/API และไม่ได้หัก Xu",
        "feedback_prompt_back": "ข้อเสนอแนะ / แจ้งข้อผิดพลาด",
    },
    "fil": {
        "feedback_prompt_title": "Kategorya ng puna",
        "feedback_prompt_body": "Magpadala ng isang mensaheng naglalarawan sa problema o mungkahi.\nKung naaangkop, isama ang job ID, pindutang pinindot, o screen kung saan ito nangyari.\n\nGagawa ang TOAN AAS ng ticket para masuri ng admin. Hindi tumawag ang bot sa AI/API at walang Xu na nabawas.",
        "feedback_prompt_back": "Puna / Mag-ulat ng bug",
    },
    "it": {
        "feedback_prompt_title": "Categoria di feedback",
        "feedback_prompt_body": "Invia un messaggio che descriva il problema o il suggerimento.\nSe utile, includi l’ID del lavoro, il pulsante premuto o la schermata in cui è successo.\n\nTOAN AAS creerà un ticket per la verifica di un amministratore. Il bot non ha chiamato IA/API né addebitato Xu.",
        "feedback_prompt_back": "Feedback / Segnala un errore",
    },
    "id": {
        "feedback_prompt_title": "Kategori masukan",
        "feedback_prompt_body": "Kirim satu pesan yang menjelaskan masalah atau saran.\nJika relevan, sertakan ID pekerjaan, tombol yang ditekan, atau layar tempat masalah terjadi.\n\nTOAN AAS akan membuat tiket untuk ditinjau admin. Bot tidak memanggil AI/API dan tidak memotong Xu.",
        "feedback_prompt_back": "Masukan / Laporkan bug",
    },
}


# Notes/Documents storage display copy.  This table intentionally owns only
# status, cleanup and navigation language; it never chooses a storage tier,
# creates a payment order, or grants storage after payment.
_PUBLIC_MEMORY_STORAGE_COPY = {
    "vi": {
        "storage_status_title": "Dung lượng lưu trữ của bạn", "storage_status_current_plan": "Gói hiện tại", "storage_status_free_plan": "Miễn phí", "storage_status_free_plus": "Miễn phí + {addon_mb}MB mở rộng", "storage_status_notes": "Ghi chú", "storage_status_text_notes": "Text/ghi chú", "storage_status_files_media": "Tệp/ảnh/âm thanh", "storage_status_total_used": "Tổng đã dùng", "storage_status_ai_remaining": "AI classify còn lại", "storage_status_reminders_active": "Nhắc hẹn đang bật", "storage_status_expand": "Mở rộng dung lượng", "storage_status_near_quota": "Bạn sắp dùng hết dung lượng lưu trữ.", "storage_status_near_quota_body": "Bạn vẫn có thể dùng ghi chú text nhẹ. Nếu cần lưu thêm tệp/ảnh/âm thanh, hãy mua thêm dung lượng hoặc dọn file cũ.", "storage_addon_monthly_line": "• +{addon_mb}MB/tháng: {price}", "storage_addon_custom_hint": "• Cần số khác: nhập bội số 50MB hoặc số tiền tương ứng.", "storage_cleanup_title": "Dọn file cũ", "storage_cleanup_body": "Bạn có thể xem ghi chú bằng <code>/notes</code>, tìm lại bằng <code>/search_note</code> rồi xóa/lưu trữ ghi chú không còn cần dùng.\n\nFile tạm như PDF temp, preview output, cache tải về hoặc video/image temp sẽ không tính quota lâu dài nếu hệ thống tự xóa theo TTL.\nTOAN AAS chưa xóa dữ liệu của bạn từ màn này và chưa trừ Xu.",
    },
    "en": {
        "storage_status_title": "Your storage", "storage_status_current_plan": "Current plan", "storage_status_free_plan": "Free", "storage_status_free_plus": "Free + {addon_mb}MB extra", "storage_status_notes": "Notes", "storage_status_text_notes": "Text / notes", "storage_status_files_media": "Files / images / audio", "storage_status_total_used": "Total used", "storage_status_ai_remaining": "AI classification remaining", "storage_status_reminders_active": "Active reminders", "storage_status_expand": "Expand storage", "storage_status_near_quota": "Your storage is nearly full.", "storage_status_near_quota_body": "You can still use lightweight text notes. To save more files, images or audio, add storage or clean old files.", "storage_addon_monthly_line": "• +{addon_mb}MB/month: {price}", "storage_addon_custom_hint": "• Need another size? Enter a multiple of 50MB or the matching amount.", "storage_cleanup_title": "Clean old files", "storage_cleanup_body": "You can view notes with <code>/notes</code>, search them with <code>/search_note</code>, then delete or archive notes you no longer need.\n\nTemporary PDF files, previews, download caches, and temporary video/image files do not count toward long-term quota when the system removes them by TTL.\nTOAN AAS has not deleted your data from this screen and has not charged Xu.",
    },
    "zh": {
        "storage_status_title": "您的存储空间", "storage_status_current_plan": "当前套餐", "storage_status_free_plan": "免费", "storage_status_free_plus": "免费 + {addon_mb}MB 扩展", "storage_status_notes": "笔记", "storage_status_text_notes": "文本 / 笔记", "storage_status_files_media": "文件 / 图片 / 音频", "storage_status_total_used": "已用总量", "storage_status_ai_remaining": "剩余 AI 分类次数", "storage_status_reminders_active": "已启用提醒", "storage_status_expand": "扩展存储空间", "storage_status_near_quota": "您的存储空间即将用满。", "storage_status_near_quota_body": "您仍可使用轻量文字笔记。如需保存更多文件、图片或音频，请扩展存储空间或清理旧文件。", "storage_addon_monthly_line": "• +{addon_mb}MB/月：{price}", "storage_addon_custom_hint": "• 需要其他容量？请输入 50MB 的倍数或对应金额。", "storage_cleanup_title": "清理旧文件", "storage_cleanup_body": "您可以用 <code>/notes</code> 查看笔记，用 <code>/search_note</code> 查找，然后删除或归档不再需要的笔记。\n\n临时 PDF、预览输出、下载缓存和临时视频/图片文件在系统按 TTL 自动清理后不会计入长期配额。\nTOAN AAS 不会在此页面删除您的数据，也不会扣除 Xu。",
    },
    "es": {
        "storage_status_title": "Tu almacenamiento", "storage_status_current_plan": "Plan actual", "storage_status_free_plan": "Gratis", "storage_status_free_plus": "Gratis + {addon_mb}MB extra", "storage_status_notes": "Notas", "storage_status_text_notes": "Texto / notas", "storage_status_files_media": "Archivos / imágenes / audio", "storage_status_total_used": "Total usado", "storage_status_ai_remaining": "Clasificación con IA restante", "storage_status_reminders_active": "Recordatorios activos", "storage_status_expand": "Ampliar almacenamiento", "storage_status_near_quota": "Tu almacenamiento está casi lleno.", "storage_status_near_quota_body": "Aún puedes usar notas de texto ligeras. Para guardar más archivos, imágenes o audio, amplía el almacenamiento o limpia archivos antiguos.", "storage_addon_monthly_line": "• +{addon_mb}MB/mes: {price}", "storage_addon_custom_hint": "• ¿Necesitas otro tamaño? Introduce un múltiplo de 50MB o el importe correspondiente.", "storage_cleanup_title": "Limpiar archivos antiguos", "storage_cleanup_body": "Puedes ver notas con <code>/notes</code>, buscarlas con <code>/search_note</code> y después borrar o archivar las que ya no necesites.\n\nLos PDF temporales, vistas previas, cachés de descarga y archivos temporales de vídeo/imagen no cuentan para la cuota a largo plazo cuando el sistema los elimina por TTL.\nTOAN AAS no ha eliminado tus datos desde esta pantalla ni ha cobrado Xu.",
    },
    "pt": {
        "storage_status_title": "Seu armazenamento", "storage_status_current_plan": "Plano atual", "storage_status_free_plan": "Grátis", "storage_status_free_plus": "Grátis + {addon_mb}MB extra", "storage_status_notes": "Notas", "storage_status_text_notes": "Texto / notas", "storage_status_files_media": "Arquivos / imagens / áudio", "storage_status_total_used": "Total usado", "storage_status_ai_remaining": "Classificação por IA restante", "storage_status_reminders_active": "Lembretes ativos", "storage_status_expand": "Ampliar armazenamento", "storage_status_near_quota": "Seu armazenamento está quase cheio.", "storage_status_near_quota_body": "Você ainda pode usar notas de texto leves. Para salvar mais arquivos, imagens ou áudio, adicione armazenamento ou limpe arquivos antigos.", "storage_addon_monthly_line": "• +{addon_mb}MB/mês: {price}", "storage_addon_custom_hint": "• Precisa de outro tamanho? Informe um múltiplo de 50MB ou o valor correspondente.", "storage_cleanup_title": "Limpar arquivos antigos", "storage_cleanup_body": "Você pode ver notas com <code>/notes</code>, encontrá-las com <code>/search_note</code> e depois excluir ou arquivar as que não precisa mais.\n\nPDFs temporários, prévias, caches de download e arquivos temporários de vídeo/imagem não contam para a cota de longo prazo quando o sistema os remove por TTL.\nA TOAN AAS não excluiu seus dados nesta tela nem cobrou Xu.",
    },
    "fr": {
        "storage_status_title": "Votre stockage", "storage_status_current_plan": "Forfait actuel", "storage_status_free_plan": "Gratuit", "storage_status_free_plus": "Gratuit + {addon_mb}MB supplémentaires", "storage_status_notes": "Notes", "storage_status_text_notes": "Texte / notes", "storage_status_files_media": "Fichiers / images / audio", "storage_status_total_used": "Total utilisé", "storage_status_ai_remaining": "Classifications IA restantes", "storage_status_reminders_active": "Rappels actifs", "storage_status_expand": "Étendre le stockage", "storage_status_near_quota": "Votre stockage est presque plein.", "storage_status_near_quota_body": "Vous pouvez encore utiliser des notes texte légères. Pour enregistrer davantage de fichiers, images ou audio, ajoutez du stockage ou nettoyez les anciens fichiers.", "storage_addon_monthly_line": "• +{addon_mb}MB/mois : {price}", "storage_addon_custom_hint": "• Besoin d’une autre taille ? Saisissez un multiple de 50MB ou le montant correspondant.", "storage_cleanup_title": "Nettoyer les anciens fichiers", "storage_cleanup_body": "Vous pouvez consulter les notes avec <code>/notes</code>, les rechercher avec <code>/search_note</code>, puis supprimer ou archiver celles dont vous n’avez plus besoin.\n\nLes PDF temporaires, aperçus, caches de téléchargement et fichiers vidéo/image temporaires ne comptent pas dans le quota long terme lorsque le système les retire par TTL.\nTOAN AAS n’a supprimé aucune de vos données depuis cet écran et n’a pas débité de Xu.",
    },
    "de": {
        "storage_status_title": "Dein Speicher", "storage_status_current_plan": "Aktueller Tarif", "storage_status_free_plan": "Kostenlos", "storage_status_free_plus": "Kostenlos + {addon_mb}MB extra", "storage_status_notes": "Notizen", "storage_status_text_notes": "Text / Notizen", "storage_status_files_media": "Dateien / Bilder / Audio", "storage_status_total_used": "Insgesamt genutzt", "storage_status_ai_remaining": "Verbleibende KI-Klassifizierungen", "storage_status_reminders_active": "Aktive Erinnerungen", "storage_status_expand": "Speicher erweitern", "storage_status_near_quota": "Dein Speicher ist fast voll.", "storage_status_near_quota_body": "Du kannst weiterhin leichte Textnotizen verwenden. Um mehr Dateien, Bilder oder Audio zu speichern, erweitere den Speicher oder bereinige alte Dateien.", "storage_addon_monthly_line": "• +{addon_mb}MB/Monat: {price}", "storage_addon_custom_hint": "• Andere Größe benötigt? Gib ein Vielfaches von 50MB oder den passenden Betrag ein.", "storage_cleanup_title": "Alte Dateien bereinigen", "storage_cleanup_body": "Du kannst Notizen mit <code>/notes</code> ansehen, mit <code>/search_note</code> suchen und nicht mehr benötigte Notizen dann löschen oder archivieren.\n\nTemporäre PDFs, Vorschauen, Download-Caches und temporäre Video-/Bilddateien zählen nicht zur Langzeitquote, wenn das System sie per TTL entfernt.\nTOAN AAS hat auf diesem Bildschirm keine deiner Daten gelöscht und keine Xu belastet.",
    },
    "ja": {
        "storage_status_title": "ストレージ", "storage_status_current_plan": "現在のプラン", "storage_status_free_plan": "無料", "storage_status_free_plus": "無料 + {addon_mb}MB 拡張", "storage_status_notes": "メモ", "storage_status_text_notes": "テキスト / メモ", "storage_status_files_media": "ファイル / 画像 / 音声", "storage_status_total_used": "合計使用量", "storage_status_ai_remaining": "AI分類の残り", "storage_status_reminders_active": "有効なリマインダー", "storage_status_expand": "ストレージを拡張", "storage_status_near_quota": "ストレージがほぼいっぱいです。", "storage_status_near_quota_body": "軽量なテキストメモは引き続き使えます。さらにファイル、画像、音声を保存するには、ストレージを追加するか古いファイルを整理してください。", "storage_addon_monthly_line": "• +{addon_mb}MB/月：{price}", "storage_addon_custom_hint": "• 別の容量が必要ですか？50MB の倍数または対応する金額を入力してください。", "storage_cleanup_title": "古いファイルを整理", "storage_cleanup_body": "<code>/notes</code> でメモを表示し、<code>/search_note</code> で検索して、不要なメモを削除またはアーカイブできます。\n\n一時 PDF、プレビュー、ダウンロードキャッシュ、一時的な動画/画像ファイルは、システムが TTL で削除した場合は長期クォータに含まれません。\nこの画面から TOAN AAS があなたのデータを削除したり、Xu を請求したりすることはありません。",
    },
    "ko": {
        "storage_status_title": "내 저장 공간", "storage_status_current_plan": "현재 요금제", "storage_status_free_plan": "무료", "storage_status_free_plus": "무료 + {addon_mb}MB 추가", "storage_status_notes": "메모", "storage_status_text_notes": "텍스트 / 메모", "storage_status_files_media": "파일 / 이미지 / 오디오", "storage_status_total_used": "총 사용량", "storage_status_ai_remaining": "남은 AI 분류", "storage_status_reminders_active": "활성 알림", "storage_status_expand": "저장 공간 확장", "storage_status_near_quota": "저장 공간이 거의 찼습니다.", "storage_status_near_quota_body": "가벼운 텍스트 메모는 계속 사용할 수 있습니다. 더 많은 파일, 이미지 또는 오디오를 저장하려면 저장 공간을 추가하거나 오래된 파일을 정리하세요.", "storage_addon_monthly_line": "• +{addon_mb}MB/월: {price}", "storage_addon_custom_hint": "• 다른 용량이 필요하신가요? 50MB의 배수 또는 해당 금액을 입력하세요.", "storage_cleanup_title": "오래된 파일 정리", "storage_cleanup_body": "<code>/notes</code>에서 메모를 보고 <code>/search_note</code>로 찾은 뒤 더 이상 필요 없는 메모를 삭제하거나 보관할 수 있습니다.\n\n임시 PDF, 미리보기, 다운로드 캐시 및 임시 동영상/이미지 파일은 시스템이 TTL로 제거하면 장기 할당량에 포함되지 않습니다.\nTOAN AAS는 이 화면에서 데이터를 삭제하거나 Xu를 차감하지 않았습니다.",
    },
    "hi": {
        "storage_status_title": "आपका संग्रहण", "storage_status_current_plan": "वर्तमान योजना", "storage_status_free_plan": "निःशुल्क", "storage_status_free_plus": "निःशुल्क + {addon_mb}MB अतिरिक्त", "storage_status_notes": "नोट", "storage_status_text_notes": "टेक्स्ट / नोट", "storage_status_files_media": "फ़ाइलें / चित्र / ऑडियो", "storage_status_total_used": "कुल उपयोग", "storage_status_ai_remaining": "शेष AI वर्गीकरण", "storage_status_reminders_active": "सक्रिय रिमाइंडर", "storage_status_expand": "संग्रहण बढ़ाएँ", "storage_status_near_quota": "आपका संग्रहण लगभग भर गया है।", "storage_status_near_quota_body": "आप हल्के टेक्स्ट नोट इस्तेमाल कर सकते हैं। अधिक फ़ाइलें, चित्र या ऑडियो सहेजने के लिए संग्रहण जोड़ें या पुरानी फ़ाइलें साफ़ करें।", "storage_addon_monthly_line": "• +{addon_mb}MB/माह: {price}", "storage_addon_custom_hint": "• कोई अन्य आकार चाहिए? 50MB के गुणज या संबंधित राशि दर्ज करें।", "storage_cleanup_title": "पुरानी फ़ाइलें साफ़ करें", "storage_cleanup_body": "आप <code>/notes</code> से नोट देख सकते हैं, <code>/search_note</code> से खोज सकते हैं, फिर जिनकी आवश्यकता नहीं है उन्हें हटा या संग्रहित कर सकते हैं।\n\nअस्थायी PDF, प्रीव्यू, डाउनलोड कैश और अस्थायी वीडियो/चित्र फ़ाइलें सिस्टम द्वारा TTL से हटाए जाने पर दीर्घकालिक कोटा में नहीं गिनी जातीं।\nTOAN AAS ने इस स्क्रीन से आपका डेटा नहीं हटाया है और Xu नहीं काटे हैं।",
    },
    "ar": {
        "storage_status_title": "مساحة التخزين لديك", "storage_status_current_plan": "الخطة الحالية", "storage_status_free_plan": "مجاني", "storage_status_free_plus": "مجاني + {addon_mb}MB إضافية", "storage_status_notes": "ملاحظات", "storage_status_text_notes": "نص / ملاحظات", "storage_status_files_media": "ملفات / صور / صوت", "storage_status_total_used": "إجمالي المستخدم", "storage_status_ai_remaining": "تصنيفات الذكاء الاصطناعي المتبقية", "storage_status_reminders_active": "التذكيرات النشطة", "storage_status_expand": "توسيع التخزين", "storage_status_near_quota": "مساحة التخزين لديك قاربت على الامتلاء.", "storage_status_near_quota_body": "لا يزال بإمكانك استخدام الملاحظات النصية الخفيفة. لحفظ المزيد من الملفات أو الصور أو الصوت، أضف مساحة تخزين أو نظّف الملفات القديمة.", "storage_addon_monthly_line": "• +{addon_mb}MB/شهر: {price}", "storage_addon_custom_hint": "• هل تحتاج إلى حجم آخر؟ أدخل مضاعفًا لـ 50MB أو المبلغ المقابل.", "storage_cleanup_title": "تنظيف الملفات القديمة", "storage_cleanup_body": "يمكنك عرض الملاحظات عبر <code>/notes</code> والبحث عنها عبر <code>/search_note</code> ثم حذف أو أرشفة ما لم تعد تحتاجه.\n\nملفات PDF المؤقتة والمعاينات وذاكرة التنزيل المؤقتة وملفات الفيديو/الصور المؤقتة لا تُحسب ضمن الحصة طويلة الأجل عندما يزيلها النظام وفق TTL.\nلم يحذف TOAN AAS بياناتك من هذه الشاشة ولم يخصم Xu.",
    },
    "ru": {
        "storage_status_title": "Ваше хранилище", "storage_status_current_plan": "Текущий тариф", "storage_status_free_plan": "Бесплатный", "storage_status_free_plus": "Бесплатный + {addon_mb}MB дополнительно", "storage_status_notes": "Заметки", "storage_status_text_notes": "Текст / заметки", "storage_status_files_media": "Файлы / изображения / аудио", "storage_status_total_used": "Всего использовано", "storage_status_ai_remaining": "Осталось AI-классификаций", "storage_status_reminders_active": "Активные напоминания", "storage_status_expand": "Расширить хранилище", "storage_status_near_quota": "Ваше хранилище почти заполнено.", "storage_status_near_quota_body": "Вы по-прежнему можете использовать лёгкие текстовые заметки. Чтобы сохранить больше файлов, изображений или аудио, добавьте место или очистите старые файлы.", "storage_addon_monthly_line": "• +{addon_mb}MB/месяц: {price}", "storage_addon_custom_hint": "• Нужен другой объём? Введите число, кратное 50MB, или соответствующую сумму.", "storage_cleanup_title": "Очистить старые файлы", "storage_cleanup_body": "Вы можете просматривать заметки через <code>/notes</code>, искать их через <code>/search_note</code>, а затем удалить или архивировать ненужные.\n\nВременные PDF, предпросмотры, кэш загрузок и временные видео/изображения не учитываются в долгосрочной квоте, если система удаляет их по TTL.\nTOAN AAS не удалял ваши данные с этого экрана и не списывал Xu.",
    },
    "tr": {
        "storage_status_title": "Depolama alanınız", "storage_status_current_plan": "Geçerli plan", "storage_status_free_plan": "Ücretsiz", "storage_status_free_plus": "Ücretsiz + {addon_mb}MB ek", "storage_status_notes": "Notlar", "storage_status_text_notes": "Metin / notlar", "storage_status_files_media": "Dosyalar / görseller / ses", "storage_status_total_used": "Toplam kullanım", "storage_status_ai_remaining": "Kalan AI sınıflandırması", "storage_status_reminders_active": "Etkin hatırlatıcılar", "storage_status_expand": "Depolamayı genişlet", "storage_status_near_quota": "Depolama alanınız neredeyse dolu.", "storage_status_near_quota_body": "Hafif metin notlarını kullanmaya devam edebilirsiniz. Daha fazla dosya, görsel veya ses kaydetmek için depolama ekleyin ya da eski dosyaları temizleyin.", "storage_addon_monthly_line": "• +{addon_mb}MB/ay: {price}", "storage_addon_custom_hint": "• Başka bir boyut mu gerekiyor? 50MB'nin katını veya karşılık gelen tutarı girin.", "storage_cleanup_title": "Eski dosyaları temizle", "storage_cleanup_body": "Notları <code>/notes</code> ile görüntüleyebilir, <code>/search_note</code> ile arayabilir ve artık gerekmeyenleri silebilir veya arşivleyebilirsiniz.\n\nGeçici PDF'ler, önizlemeler, indirme önbellekleri ve geçici video/görsel dosyaları sistem TTL ile kaldırdığında uzun vadeli kotaya sayılmaz.\nTOAN AAS bu ekrandan verilerinizi silmedi ve Xu kesmedi.",
    },
    "th": {
        "storage_status_title": "พื้นที่เก็บข้อมูลของคุณ", "storage_status_current_plan": "แพ็กเกจปัจจุบัน", "storage_status_free_plan": "ฟรี", "storage_status_free_plus": "ฟรี + เพิ่ม {addon_mb}MB", "storage_status_notes": "บันทึก", "storage_status_text_notes": "ข้อความ / บันทึก", "storage_status_files_media": "ไฟล์ / ภาพ / เสียง", "storage_status_total_used": "ใช้ไปทั้งหมด", "storage_status_ai_remaining": "การจัดหมวดหมู่ AI ที่เหลือ", "storage_status_reminders_active": "การแจ้งเตือนที่เปิดอยู่", "storage_status_expand": "เพิ่มพื้นที่เก็บข้อมูล", "storage_status_near_quota": "พื้นที่เก็บข้อมูลของคุณใกล้เต็มแล้ว", "storage_status_near_quota_body": "คุณยังใช้บันทึกข้อความขนาดเล็กได้ หากต้องการเก็บไฟล์ ภาพ หรือเสียงเพิ่ม ให้เพิ่มพื้นที่เก็บข้อมูลหรือล้างไฟล์เก่า", "storage_addon_monthly_line": "• +{addon_mb}MB/เดือน: {price}", "storage_addon_custom_hint": "• ต้องการขนาดอื่นหรือไม่? ป้อนจำนวนที่เป็นพหุคูณของ 50MB หรือยอดเงินที่ตรงกัน", "storage_cleanup_title": "ล้างไฟล์เก่า", "storage_cleanup_body": "คุณดูบันทึกได้ด้วย <code>/notes</code> ค้นหาด้วย <code>/search_note</code> แล้วลบหรือเก็บถาวรบันทึกที่ไม่ต้องการได้\n\nPDF ชั่วคราว พรีวิว แคชดาวน์โหลด และไฟล์วิดีโอ/ภาพชั่วคราวจะไม่นับรวมโควต้าระยะยาวเมื่อระบบลบตาม TTL\nTOAN AAS ยังไม่ได้ลบข้อมูลของคุณจากหน้านี้และไม่ได้หัก Xu",
    },
    "fil": {
        "storage_status_title": "Iyong storage", "storage_status_current_plan": "Kasalukuyang plano", "storage_status_free_plan": "Libre", "storage_status_free_plus": "Libre + {addon_mb}MB dagdag", "storage_status_notes": "Mga tala", "storage_status_text_notes": "Text / mga tala", "storage_status_files_media": "Mga file / larawan / audio", "storage_status_total_used": "Kabuuang nagamit", "storage_status_ai_remaining": "Natitirang AI classification", "storage_status_reminders_active": "Aktibong paalala", "storage_status_expand": "Magdagdag ng storage", "storage_status_near_quota": "Halos puno na ang iyong storage.", "storage_status_near_quota_body": "Maaari ka pa ring gumamit ng magagaang text note. Para makapag-save ng mas maraming file, larawan o audio, magdagdag ng storage o linisin ang lumang file.", "storage_addon_monthly_line": "• +{addon_mb}MB/buwan: {price}", "storage_addon_custom_hint": "• Kailangan ng ibang laki? Maglagay ng multiple ng 50MB o katumbas na halaga.", "storage_cleanup_title": "Linisin ang lumang file", "storage_cleanup_body": "Maaari mong tingnan ang mga tala gamit ang <code>/notes</code>, hanapin gamit ang <code>/search_note</code>, at pagkatapos ay burahin o i-archive ang hindi na kailangan.\n\nAng pansamantalang PDF, preview, download cache, at pansamantalang video/larawan ay hindi kasama sa pangmatagalang quota kapag inalis ng system gamit ang TTL.\nHindi pa binura ng TOAN AAS ang iyong data mula sa screen na ito at walang Xu na nabawas.",
    },
    "it": {
        "storage_status_title": "Il tuo spazio", "storage_status_current_plan": "Piano attuale", "storage_status_free_plan": "Gratuito", "storage_status_free_plus": "Gratuito + {addon_mb}MB extra", "storage_status_notes": "Note", "storage_status_text_notes": "Testo / note", "storage_status_files_media": "File / immagini / audio", "storage_status_total_used": "Totale usato", "storage_status_ai_remaining": "Classificazioni IA rimanenti", "storage_status_reminders_active": "Promemoria attivi", "storage_status_expand": "Aggiungi spazio", "storage_status_near_quota": "Il tuo spazio è quasi pieno.", "storage_status_near_quota_body": "Puoi ancora usare note di testo leggere. Per salvare più file, immagini o audio, aggiungi spazio o pulisci i file vecchi.", "storage_addon_monthly_line": "• +{addon_mb}MB/mese: {price}", "storage_addon_custom_hint": "• Serve un'altra dimensione? Inserisci un multiplo di 50MB o l'importo corrispondente.", "storage_cleanup_title": "Pulisci file vecchi", "storage_cleanup_body": "Puoi visualizzare le note con <code>/notes</code>, cercarle con <code>/search_note</code> e poi eliminare o archiviare quelle che non ti servono più.\n\nPDF temporanei, anteprime, cache di download e file temporanei video/immagine non contano nella quota a lungo termine quando il sistema li rimuove con TTL.\nTOAN AAS non ha eliminato i tuoi dati da questa schermata né addebitato Xu.",
    },
    "id": {
        "storage_status_title": "Penyimpanan Anda", "storage_status_current_plan": "Paket saat ini", "storage_status_free_plan": "Gratis", "storage_status_free_plus": "Gratis + tambahan {addon_mb}MB", "storage_status_notes": "Catatan", "storage_status_text_notes": "Teks / catatan", "storage_status_files_media": "File / gambar / audio", "storage_status_total_used": "Total terpakai", "storage_status_ai_remaining": "Klasifikasi AI tersisa", "storage_status_reminders_active": "Pengingat aktif", "storage_status_expand": "Tambah penyimpanan", "storage_status_near_quota": "Penyimpanan Anda hampir penuh.", "storage_status_near_quota_body": "Anda masih dapat memakai catatan teks ringan. Untuk menyimpan lebih banyak file, gambar, atau audio, tambahkan penyimpanan atau bersihkan file lama.", "storage_addon_monthly_line": "• +{addon_mb}MB/bulan: {price}", "storage_addon_custom_hint": "• Perlu ukuran lain? Masukkan kelipatan 50MB atau jumlah yang sesuai.", "storage_cleanup_title": "Bersihkan file lama", "storage_cleanup_body": "Anda dapat melihat catatan dengan <code>/notes</code>, mencarinya dengan <code>/search_note</code>, lalu menghapus atau mengarsipkan yang tidak lagi diperlukan.\n\nPDF sementara, pratinjau, cache unduhan, dan file video/gambar sementara tidak dihitung dalam kuota jangka panjang saat sistem menghapusnya dengan TTL.\nTOAN AAS belum menghapus data Anda dari layar ini dan tidak memotong Xu.",
    },
}


# Translation is a public presentation flow.  These strings deliberately sit
# beside the established hub copy rather than in a global fallback helper: the
# callbacks, pending-session state and provider paths keep their existing
# owners, while each selected customer locale receives direct native text.
_PUBLIC_TRANSLATION_FLOW_COPY = {
    "vi": {
        "translation_session_two_way_title": "🔁 Đã bật dịch 2 chiều", "translation_session_live_title": "🗣 Đã bật chế độ phiên dịch", "translation_session_pair": "Cặp ngôn ngữ", "translation_session_input": "Đầu vào", "translation_session_output": "Đầu ra", "translation_session_send": "Gửi văn bản hoặc voice. TOAN AAS sẽ dịch sang {target}; bấm Đổi chiều để dịch ngược lại.", "translation_session_voice_fallback": "Nếu giọng đọc chưa sẵn sàng, bot vẫn trả bản dịch bằng văn bản. Bot chưa trừ Xu.", "translation_session_swap": "🔄 Đổi chiều", "translation_session_change_pair": "🌍 Đổi cặp ngôn ngữ", "translation_session_enable_voice": "🎙 Bật voice", "translation_session_stop": "⏹ Tắt chế độ dịch", "translation_pair_source": "🌐 Nguồn", "translation_pair_target": "➡️ Dịch sang", "translation_pair_start": "✅ Bắt đầu", "translation_picker_source": "ngôn ngữ cần dịch", "translation_picker_target": "ngôn ngữ dịch ra", "translation_picker_choose": "🌐 Chọn ngôn ngữ", "translation_picker_auto_detect": "🌍 Tự nhận diện", "translation_picker_more": "🌍 Ngôn ngữ khác", "translation_picker_back": "⬅️ Quay lại", "translation_picker_no_charge": "Bot chưa trừ Xu.", "translation_text_confirm_title": "🌐 Xác nhận dịch văn bản", "translation_text_confirm_target": "Ngôn ngữ đích", "translation_text_confirm_continue": "TOAN AAS chưa dịch nội dung và chưa trừ Xu. Bấm xác nhận để tiếp tục.", "translation_text_confirm_action": "✅ Xác nhận dịch", "translation_text_cancel": "❌ Hủy", "translation_result_more": "🔁 Dịch tiếp", "translation_result_change": "🌐 Đổi ngôn ngữ", "translation_result_direction": "Chiều dịch", "translation_result_original": "Nội dung gốc", "translation_result_translated": "Bản dịch", "translation_result_no_charge": "Bot chưa trừ Xu.", "translation_auto_target": "🌐 Ngôn ngữ đích tự động", "translation_interface_language": "🌍 Ngôn ngữ giao diện bot", "translation_input_too_long": "Nội dung quá dài. Vui lòng chia thành từng đoạn ngắn để dịch ổn định. Bot chưa trừ Xu.", "translation_service_unavailable": "Dịch vụ đang được kiểm tra tài nguyên xử lý. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau.",
    },
    "en": {
        "translation_session_two_way_title": "🔁 Two-way translation enabled", "translation_session_live_title": "🗣 Interpreter mode enabled", "translation_session_pair": "Language pair", "translation_session_input": "Input", "translation_session_output": "Output", "translation_session_send": "Send text or voice. TOAN AAS translates to {target}; tap Swap to translate in the other direction.", "translation_session_voice_fallback": "If voice output is unavailable, the translated text is still returned. No Xu charged.", "translation_session_swap": "🔄 Swap", "translation_session_change_pair": "🌍 Change languages", "translation_session_enable_voice": "🎙 Enable voice", "translation_session_stop": "⏹ Stop translation", "translation_pair_source": "🌐 From", "translation_pair_target": "➡️ To", "translation_pair_start": "✅ Start", "translation_picker_source": "source language", "translation_picker_target": "target language", "translation_picker_choose": "🌐 Choose language", "translation_picker_auto_detect": "🌍 Auto detect", "translation_picker_more": "🌍 More languages", "translation_picker_back": "⬅️ Back", "translation_picker_no_charge": "No Xu charged.", "translation_text_confirm_title": "🌐 Confirm text translation", "translation_text_confirm_target": "Target", "translation_text_confirm_continue": "TOAN AAS has not translated the text and has not charged Xu. Confirm to continue.", "translation_text_confirm_action": "✅ Confirm translation", "translation_text_cancel": "❌ Cancel", "translation_result_more": "🔁 Translate more", "translation_result_change": "🌐 Change language", "translation_result_direction": "Translation direction", "translation_result_original": "Original", "translation_result_translated": "Translation", "translation_result_no_charge": "No Xu charged.", "translation_auto_target": "🌐 Auto-translate target", "translation_interface_language": "🌍 Bot interface language", "translation_input_too_long": "The text is too long. Split it into shorter sections for reliable translation. No Xu charged.", "translation_service_unavailable": "The translation service is checking processing capacity. TOAN AAS has not processed or charged Xu. Please try again later.",
    },
    "zh": {
        "translation_session_two_way_title": "🔁 已启用双向翻译", "translation_session_live_title": "🗣 已启用口译模式", "translation_session_pair": "语言组合", "translation_session_input": "输入", "translation_session_output": "输出", "translation_session_send": "发送文字或语音。TOAN AAS 会翻译为{target}；点击切换方向可反向翻译。", "translation_session_voice_fallback": "若语音输出暂不可用，机器人仍会返回文字译文。不会扣除 Xu。", "translation_session_swap": "🔄 切换方向", "translation_session_change_pair": "🌍 更改语言组合", "translation_session_enable_voice": "🎙 启用语音", "translation_session_stop": "⏹ 停止翻译", "translation_pair_source": "🌐 源语言", "translation_pair_target": "➡️ 目标语言", "translation_pair_start": "✅ 开始", "translation_picker_source": "源语言", "translation_picker_target": "目标语言", "translation_picker_choose": "🌐 选择语言", "translation_picker_auto_detect": "🌍 自动识别", "translation_picker_more": "🌍 更多语言", "translation_picker_back": "⬅️ 返回", "translation_picker_no_charge": "不会扣除 Xu。", "translation_text_confirm_title": "🌐 确认文本翻译", "translation_text_confirm_target": "目标语言", "translation_text_confirm_continue": "TOAN AAS 尚未翻译内容，也未扣除 Xu。确认后继续。", "translation_text_confirm_action": "✅ 确认翻译", "translation_text_cancel": "❌ 取消", "translation_result_more": "🔁 继续翻译", "translation_result_change": "🌐 更改语言", "translation_result_direction": "翻译方向", "translation_result_original": "原文", "translation_result_translated": "译文", "translation_result_no_charge": "不会扣除 Xu。", "translation_auto_target": "🌐 自动翻译目标语言", "translation_interface_language": "🌍 机器人界面语言", "translation_input_too_long": "文本过长，请分成较短的段落以便稳定翻译。不会扣除 Xu。", "translation_service_unavailable": "翻译服务正在检查处理资源。TOAN AAS 尚未处理，也未扣除 Xu，请稍后再试。",
    },
    "es": {
        "translation_session_two_way_title": "🔁 Traducción bidireccional activada", "translation_session_live_title": "🗣 Modo intérprete activado", "translation_session_pair": "Par de idiomas", "translation_session_input": "Entrada", "translation_session_output": "Salida", "translation_session_send": "Envía texto o voz. TOAN AAS traducirá a {target}; toca Cambiar sentido para traducir al revés.", "translation_session_voice_fallback": "Si la voz no está disponible, recibirás igualmente la traducción en texto. No se cobra Xu.", "translation_session_swap": "🔄 Cambiar sentido", "translation_session_change_pair": "🌍 Cambiar idiomas", "translation_session_enable_voice": "🎙 Activar voz", "translation_session_stop": "⏹ Detener traducción", "translation_pair_source": "🌐 Desde", "translation_pair_target": "➡️ Hacia", "translation_pair_start": "✅ Iniciar", "translation_picker_source": "idioma de origen", "translation_picker_target": "idioma de destino", "translation_picker_choose": "🌐 Elegir idioma", "translation_picker_auto_detect": "🌍 Detectar automáticamente", "translation_picker_more": "🌍 Más idiomas", "translation_picker_back": "⬅️ Volver", "translation_picker_no_charge": "No se cobra Xu.", "translation_text_confirm_title": "🌐 Confirmar traducción de texto", "translation_text_confirm_target": "Destino", "translation_text_confirm_continue": "TOAN AAS aún no ha traducido el texto ni cobrado Xu. Confirma para continuar.", "translation_text_confirm_action": "✅ Confirmar traducción", "translation_text_cancel": "❌ Cancelar", "translation_result_more": "🔁 Traducir más", "translation_result_change": "🌐 Cambiar idioma", "translation_result_direction": "Dirección de traducción", "translation_result_original": "Original", "translation_result_translated": "Traducción", "translation_result_no_charge": "No se cobra Xu.", "translation_auto_target": "🌐 Destino de traducción automática", "translation_interface_language": "🌍 Idioma de la interfaz del bot", "translation_input_too_long": "El texto es demasiado largo. Divídelo en partes más cortas para una traducción estable. No se cobra Xu.", "translation_service_unavailable": "El servicio de traducción está comprobando la capacidad de procesamiento. TOAN AAS no ha procesado ni cobrado Xu. Inténtalo más tarde.",
    },
    "pt": {
        "translation_session_two_way_title": "🔁 Tradução bidirecional ativada", "translation_session_live_title": "🗣 Modo intérprete ativado", "translation_session_pair": "Par de idiomas", "translation_session_input": "Entrada", "translation_session_output": "Saída", "translation_session_send": "Envie texto ou voz. A TOAN AAS traduzirá para {target}; toque em Inverter para traduzir no sentido oposto.", "translation_session_voice_fallback": "Se a saída de voz não estiver disponível, o texto traduzido ainda será enviado. Nenhum Xu será cobrado.", "translation_session_swap": "🔄 Inverter", "translation_session_change_pair": "🌍 Alterar idiomas", "translation_session_enable_voice": "🎙 Ativar voz", "translation_session_stop": "⏹ Parar tradução", "translation_pair_source": "🌐 De", "translation_pair_target": "➡️ Para", "translation_pair_start": "✅ Iniciar", "translation_picker_source": "idioma de origem", "translation_picker_target": "idioma de destino", "translation_picker_choose": "🌐 Escolher idioma", "translation_picker_auto_detect": "🌍 Detectar automaticamente", "translation_picker_more": "🌍 Mais idiomas", "translation_picker_back": "⬅️ Voltar", "translation_picker_no_charge": "Nenhum Xu será cobrado.", "translation_text_confirm_title": "🌐 Confirmar tradução de texto", "translation_text_confirm_target": "Destino", "translation_text_confirm_continue": "A TOAN AAS ainda não traduziu o texto nem cobrou Xu. Confirme para continuar.", "translation_text_confirm_action": "✅ Confirmar tradução", "translation_text_cancel": "❌ Cancelar", "translation_result_more": "🔁 Traduzir mais", "translation_result_change": "🌐 Alterar idioma", "translation_result_direction": "Direção da tradução", "translation_result_original": "Original", "translation_result_translated": "Tradução", "translation_result_no_charge": "Nenhum Xu será cobrado.", "translation_auto_target": "🌐 Destino da tradução automática", "translation_interface_language": "🌍 Idioma da interface do bot", "translation_input_too_long": "O texto é longo demais. Divida-o em partes menores para uma tradução estável. Nenhum Xu será cobrado.", "translation_service_unavailable": "O serviço de tradução está verificando a capacidade de processamento. A TOAN AAS não processou nem cobrou Xu. Tente novamente mais tarde.",
    },
    "fr": {
        "translation_session_two_way_title": "🔁 Traduction bidirectionnelle activée", "translation_session_live_title": "🗣 Mode interprète activé", "translation_session_pair": "Paire de langues", "translation_session_input": "Entrée", "translation_session_output": "Sortie", "translation_session_send": "Envoyez du texte ou un message vocal. TOAN AAS traduira vers {target} ; utilisez Inverser pour traduire dans l’autre sens.", "translation_session_voice_fallback": "Si la sortie vocale n’est pas disponible, la traduction texte reste envoyée. Aucun Xu n’est débité.", "translation_session_swap": "🔄 Inverser", "translation_session_change_pair": "🌍 Changer de langues", "translation_session_enable_voice": "🎙 Activer la voix", "translation_session_stop": "⏹ Arrêter la traduction", "translation_pair_source": "🌐 De", "translation_pair_target": "➡️ Vers", "translation_pair_start": "✅ Démarrer", "translation_picker_source": "langue source", "translation_picker_target": "langue cible", "translation_picker_choose": "🌐 Choisir une langue", "translation_picker_auto_detect": "🌍 Détection automatique", "translation_picker_more": "🌍 Plus de langues", "translation_picker_back": "⬅️ Retour", "translation_picker_no_charge": "Aucun Xu n’est débité.", "translation_text_confirm_title": "🌐 Confirmer la traduction du texte", "translation_text_confirm_target": "Cible", "translation_text_confirm_continue": "TOAN AAS n’a pas encore traduit le texte ni débité de Xu. Confirmez pour continuer.", "translation_text_confirm_action": "✅ Confirmer la traduction", "translation_text_cancel": "❌ Annuler", "translation_result_more": "🔁 Traduire davantage", "translation_result_change": "🌐 Changer de langue", "translation_result_direction": "Sens de traduction", "translation_result_original": "Original", "translation_result_translated": "Traduction", "translation_result_no_charge": "Aucun Xu n’est débité.", "translation_auto_target": "🌐 Cible de traduction automatique", "translation_interface_language": "🌍 Langue de l’interface du bot", "translation_input_too_long": "Le texte est trop long. Découpez-le en passages plus courts pour une traduction fiable. Aucun Xu n’est débité.", "translation_service_unavailable": "Le service de traduction vérifie sa capacité de traitement. TOAN AAS n’a rien traité ni débité. Réessayez plus tard.",
    },
    "de": {
        "translation_session_two_way_title": "🔁 Zwei-Wege-Übersetzung aktiviert", "translation_session_live_title": "🗣 Dolmetschmodus aktiviert", "translation_session_pair": "Sprachpaar", "translation_session_input": "Eingabe", "translation_session_output": "Ausgabe", "translation_session_send": "Sende Text oder Sprache. TOAN AAS übersetzt nach {target}; mit Wechseln übersetzt du in die Gegenrichtung.", "translation_session_voice_fallback": "Falls Sprachausgabe nicht verfügbar ist, wird die Textübersetzung weiterhin gesendet. Es wird kein Xu berechnet.", "translation_session_swap": "🔄 Wechseln", "translation_session_change_pair": "🌍 Sprachen ändern", "translation_session_enable_voice": "🎙 Sprache aktivieren", "translation_session_stop": "⏹ Übersetzung beenden", "translation_pair_source": "🌐 Von", "translation_pair_target": "➡️ Nach", "translation_pair_start": "✅ Starten", "translation_picker_source": "Ausgangssprache", "translation_picker_target": "Zielsprache", "translation_picker_choose": "🌐 Sprache auswählen", "translation_picker_auto_detect": "🌍 Automatisch erkennen", "translation_picker_more": "🌍 Weitere Sprachen", "translation_picker_back": "⬅️ Zurück", "translation_picker_no_charge": "Es wird kein Xu berechnet.", "translation_text_confirm_title": "🌐 Textübersetzung bestätigen", "translation_text_confirm_target": "Ziel", "translation_text_confirm_continue": "TOAN AAS hat den Text noch nicht übersetzt und kein Xu berechnet. Zum Fortfahren bestätigen.", "translation_text_confirm_action": "✅ Übersetzung bestätigen", "translation_text_cancel": "❌ Abbrechen", "translation_result_more": "🔁 Weiter übersetzen", "translation_result_change": "🌐 Sprache ändern", "translation_result_direction": "Übersetzungsrichtung", "translation_result_original": "Original", "translation_result_translated": "Übersetzung", "translation_result_no_charge": "Es wird kein Xu berechnet.", "translation_auto_target": "🌐 Ziel der automatischen Übersetzung", "translation_interface_language": "🌍 Sprache der Bot-Oberfläche", "translation_input_too_long": "Der Text ist zu lang. Teile ihn für eine zuverlässige Übersetzung in kürzere Abschnitte. Es wird kein Xu berechnet.", "translation_service_unavailable": "Der Übersetzungsdienst prüft seine Verarbeitungskapazität. TOAN AAS hat nichts verarbeitet und kein Xu berechnet. Bitte später erneut versuchen.",
    },
    "ja": {
        "translation_session_two_way_title": "🔁 双方向翻訳を開始しました", "translation_session_live_title": "🗣 通訳モードを開始しました", "translation_session_pair": "言語ペア", "translation_session_input": "入力", "translation_session_output": "出力", "translation_session_send": "テキストまたは音声を送信してください。TOAN AAS が{target}へ翻訳します。方向を切り替えると逆方向に翻訳できます。", "translation_session_voice_fallback": "音声出力を利用できない場合でも、テキスト翻訳は返されます。Xu は消費されません。", "translation_session_swap": "🔄 方向を切り替え", "translation_session_change_pair": "🌍 言語ペアを変更", "translation_session_enable_voice": "🎙 音声を有効化", "translation_session_stop": "⏹ 翻訳を停止", "translation_pair_source": "🌐 翻訳元", "translation_pair_target": "➡️ 翻訳先", "translation_pair_start": "✅ 開始", "translation_picker_source": "翻訳元の言語", "translation_picker_target": "翻訳先の言語", "translation_picker_choose": "🌐 言語を選択", "translation_picker_auto_detect": "🌍 自動検出", "translation_picker_more": "🌍 その他の言語", "translation_picker_back": "⬅️ 戻る", "translation_picker_no_charge": "Xu は消費されません。", "translation_text_confirm_title": "🌐 テキスト翻訳を確認", "translation_text_confirm_target": "翻訳先", "translation_text_confirm_continue": "TOAN AAS はまだ翻訳も Xu の消費もしていません。確認して続行してください。", "translation_text_confirm_action": "✅ 翻訳を確認", "translation_text_cancel": "❌ キャンセル", "translation_result_more": "🔁 続けて翻訳", "translation_result_change": "🌐 言語を変更", "translation_result_direction": "翻訳方向", "translation_result_original": "原文", "translation_result_translated": "翻訳結果", "translation_result_no_charge": "Xu は消費されません。", "translation_auto_target": "🌐 自動翻訳の対象言語", "translation_interface_language": "🌍 ボットの表示言語", "translation_input_too_long": "テキストが長すぎます。安定して翻訳するため、短い段落に分けてください。Xu は消費されません。", "translation_service_unavailable": "翻訳サービスは処理リソースを確認中です。TOAN AAS は処理も Xu の消費もしていません。後でもう一度お試しください。",
    },
    "ko": {
        "translation_session_two_way_title": "🔁 양방향 번역을 켰습니다", "translation_session_live_title": "🗣 통역 모드를 켰습니다", "translation_session_pair": "언어 조합", "translation_session_input": "입력", "translation_session_output": "출력", "translation_session_send": "텍스트나 음성을 보내세요. TOAN AAS가 {target}(으)로 번역합니다. 방향 바꾸기를 누르면 반대 방향으로 번역합니다.", "translation_session_voice_fallback": "음성 출력을 사용할 수 없어도 번역 텍스트는 제공됩니다. Xu는 차감되지 않습니다.", "translation_session_swap": "🔄 방향 바꾸기", "translation_session_change_pair": "🌍 언어 조합 변경", "translation_session_enable_voice": "🎙 음성 켜기", "translation_session_stop": "⏹ 번역 중지", "translation_pair_source": "🌐 원문 언어", "translation_pair_target": "➡️ 번역 언어", "translation_pair_start": "✅ 시작", "translation_picker_source": "원문 언어", "translation_picker_target": "번역 언어", "translation_picker_choose": "🌐 언어 선택", "translation_picker_auto_detect": "🌍 자동 감지", "translation_picker_more": "🌍 더 많은 언어", "translation_picker_back": "⬅️ 뒤로", "translation_picker_no_charge": "Xu는 차감되지 않습니다.", "translation_text_confirm_title": "🌐 텍스트 번역 확인", "translation_text_confirm_target": "번역 언어", "translation_text_confirm_continue": "TOAN AAS는 아직 텍스트를 번역하거나 Xu를 차감하지 않았습니다. 계속하려면 확인하세요.", "translation_text_confirm_action": "✅ 번역 확인", "translation_text_cancel": "❌ 취소", "translation_result_more": "🔁 계속 번역", "translation_result_change": "🌐 언어 변경", "translation_result_direction": "번역 방향", "translation_result_original": "원문", "translation_result_translated": "번역문", "translation_result_no_charge": "Xu는 차감되지 않습니다.", "translation_auto_target": "🌐 자동 번역 대상 언어", "translation_interface_language": "🌍 봇 인터페이스 언어", "translation_input_too_long": "텍스트가 너무 깁니다. 안정적인 번역을 위해 짧은 부분으로 나누세요. Xu는 차감되지 않습니다.", "translation_service_unavailable": "번역 서비스가 처리 자원을 확인하고 있습니다. TOAN AAS는 처리하거나 Xu를 차감하지 않았습니다. 나중에 다시 시도하세요.",
    },
    "hi": {
        "translation_session_two_way_title": "🔁 दो-तरफ़ा अनुवाद चालू है", "translation_session_live_title": "🗣 दुभाषिया मोड चालू है", "translation_session_pair": "भाषा जोड़ी", "translation_session_input": "इनपुट", "translation_session_output": "आउटपुट", "translation_session_send": "पाठ या आवाज़ भेजें। TOAN AAS इसे {target} में अनुवाद करेगा; दिशा बदलने के लिए बदलें दबाएँ।", "translation_session_voice_fallback": "यदि आवाज़ आउटपुट उपलब्ध नहीं है, तो पाठ अनुवाद फिर भी भेजा जाएगा। Xu नहीं कटेगा।", "translation_session_swap": "🔄 दिशा बदलें", "translation_session_change_pair": "🌍 भाषाएँ बदलें", "translation_session_enable_voice": "🎙 आवाज़ चालू करें", "translation_session_stop": "⏹ अनुवाद रोकें", "translation_pair_source": "🌐 स्रोत", "translation_pair_target": "➡️ लक्ष्य", "translation_pair_start": "✅ शुरू करें", "translation_picker_source": "स्रोत भाषा", "translation_picker_target": "लक्ष्य भाषा", "translation_picker_choose": "🌐 भाषा चुनें", "translation_picker_auto_detect": "🌍 स्वतः पहचान", "translation_picker_more": "🌍 और भाषाएँ", "translation_picker_back": "⬅️ वापस", "translation_picker_no_charge": "Xu नहीं कटेगा।", "translation_text_confirm_title": "🌐 पाठ अनुवाद की पुष्टि करें", "translation_text_confirm_target": "लक्ष्य", "translation_text_confirm_continue": "TOAN AAS ने अभी पाठ का अनुवाद नहीं किया है और Xu नहीं काटा है। जारी रखने के लिए पुष्टि करें।", "translation_text_confirm_action": "✅ अनुवाद की पुष्टि करें", "translation_text_cancel": "❌ रद्द करें", "translation_result_more": "🔁 और अनुवाद करें", "translation_result_change": "🌐 भाषा बदलें", "translation_result_direction": "अनुवाद दिशा", "translation_result_original": "मूल", "translation_result_translated": "अनुवाद", "translation_result_no_charge": "Xu नहीं कटेगा।", "translation_auto_target": "🌐 स्वचालित अनुवाद लक्ष्य", "translation_interface_language": "🌍 बॉट इंटरफ़ेस भाषा", "translation_input_too_long": "पाठ बहुत लंबा है। विश्वसनीय अनुवाद के लिए इसे छोटे भागों में बाँटें। Xu नहीं कटेगा।", "translation_service_unavailable": "अनुवाद सेवा प्रसंस्करण क्षमता जाँच रही है। TOAN AAS ने कुछ संसाधित नहीं किया और Xu नहीं काटा। बाद में फिर प्रयास करें।",
    },
    "ar": {
        "translation_session_two_way_title": "🔁 تم تفعيل الترجمة ثنائية الاتجاه", "translation_session_live_title": "🗣 تم تفعيل وضع الترجمة الفورية", "translation_session_pair": "زوج اللغات", "translation_session_input": "الإدخال", "translation_session_output": "الإخراج", "translation_session_send": "أرسل نصاً أو رسالة صوتية. سيترجم TOAN AAS إلى {target}؛ اضغط تبديل للترجمة في الاتجاه الآخر.", "translation_session_voice_fallback": "إذا لم يتوفر إخراج صوتي فستتلقى الترجمة النصية. لا يتم خصم Xu.", "translation_session_swap": "🔄 تبديل الاتجاه", "translation_session_change_pair": "🌍 تغيير اللغات", "translation_session_enable_voice": "🎙 تفعيل الصوت", "translation_session_stop": "⏹ إيقاف الترجمة", "translation_pair_source": "🌐 من", "translation_pair_target": "➡️ إلى", "translation_pair_start": "✅ بدء", "translation_picker_source": "لغة المصدر", "translation_picker_target": "اللغة الهدف", "translation_picker_choose": "🌐 اختر اللغة", "translation_picker_auto_detect": "🌍 كشف تلقائي", "translation_picker_more": "🌍 المزيد من اللغات", "translation_picker_back": "⬅️ رجوع", "translation_picker_no_charge": "لا يتم خصم Xu.", "translation_text_confirm_title": "🌐 تأكيد ترجمة النص", "translation_text_confirm_target": "الهدف", "translation_text_confirm_continue": "لم يترجم TOAN AAS النص بعد ولم يخصم Xu. أكّد للمتابعة.", "translation_text_confirm_action": "✅ تأكيد الترجمة", "translation_text_cancel": "❌ إلغاء", "translation_result_more": "🔁 ترجمة المزيد", "translation_result_change": "🌐 تغيير اللغة", "translation_result_direction": "اتجاه الترجمة", "translation_result_original": "النص الأصلي", "translation_result_translated": "الترجمة", "translation_result_no_charge": "لا يتم خصم Xu.", "translation_auto_target": "🌐 هدف الترجمة التلقائية", "translation_interface_language": "🌍 لغة واجهة البوت", "translation_input_too_long": "النص طويل جداً. قسّمه إلى أجزاء أقصر لترجمة مستقرة. لا يتم خصم Xu.", "translation_service_unavailable": "تتحقق خدمة الترجمة من قدرة المعالجة. لم يعالج TOAN AAS شيئاً ولم يخصم Xu. حاول لاحقاً.",
    },
    "ru": {
        "translation_session_two_way_title": "🔁 Двусторонний перевод включён", "translation_session_live_title": "🗣 Режим переводчика включён", "translation_session_pair": "Языковая пара", "translation_session_input": "Ввод", "translation_session_output": "Вывод", "translation_session_send": "Отправьте текст или голосовое сообщение. TOAN AAS переведёт на {target}; нажмите «Сменить направление» для обратного перевода.", "translation_session_voice_fallback": "Если голосовой вывод недоступен, текстовый перевод всё равно будет отправлен. Xu не списываются.", "translation_session_swap": "🔄 Сменить направление", "translation_session_change_pair": "🌍 Изменить языки", "translation_session_enable_voice": "🎙 Включить голос", "translation_session_stop": "⏹ Остановить перевод", "translation_pair_source": "🌐 С", "translation_pair_target": "➡️ На", "translation_pair_start": "✅ Начать", "translation_picker_source": "исходный язык", "translation_picker_target": "целевой язык", "translation_picker_choose": "🌐 Выберите язык", "translation_picker_auto_detect": "🌍 Определить автоматически", "translation_picker_more": "🌍 Другие языки", "translation_picker_back": "⬅️ Назад", "translation_picker_no_charge": "Xu не списываются.", "translation_text_confirm_title": "🌐 Подтвердить перевод текста", "translation_text_confirm_target": "Целевой язык", "translation_text_confirm_continue": "TOAN AAS ещё не перевёл текст и не списал Xu. Подтвердите, чтобы продолжить.", "translation_text_confirm_action": "✅ Подтвердить перевод", "translation_text_cancel": "❌ Отмена", "translation_result_more": "🔁 Перевести ещё", "translation_result_change": "🌐 Изменить язык", "translation_result_direction": "Направление перевода", "translation_result_original": "Оригинал", "translation_result_translated": "Перевод", "translation_result_no_charge": "Xu не списываются.", "translation_auto_target": "🌐 Цель автоперевода", "translation_interface_language": "🌍 Язык интерфейса бота", "translation_input_too_long": "Текст слишком длинный. Разделите его на короткие части для стабильного перевода. Xu не списываются.", "translation_service_unavailable": "Сервис перевода проверяет ресурсы обработки. TOAN AAS ничего не обработал и не списал Xu. Попробуйте позже.",
    },
    "tr": {
        "translation_session_two_way_title": "🔁 Çift yönlü çeviri etkin", "translation_session_live_title": "🗣 Tercüman modu etkin", "translation_session_pair": "Dil çifti", "translation_session_input": "Girdi", "translation_session_output": "Çıktı", "translation_session_send": "Metin veya ses gönderin. TOAN AAS {target} diline çevirir; ters yönde çevirmek için Yön değiştir'e dokunun.", "translation_session_voice_fallback": "Sesli çıktı kullanılamazsa metin çevirisi yine gönderilir. Xu kesilmez.", "translation_session_swap": "🔄 Yön değiştir", "translation_session_change_pair": "🌍 Dilleri değiştir", "translation_session_enable_voice": "🎙 Sesi aç", "translation_session_stop": "⏹ Çeviriyi durdur", "translation_pair_source": "🌐 Kaynak", "translation_pair_target": "➡️ Hedef", "translation_pair_start": "✅ Başlat", "translation_picker_source": "kaynak dil", "translation_picker_target": "hedef dil", "translation_picker_choose": "🌐 Dil seçin", "translation_picker_auto_detect": "🌍 Otomatik algıla", "translation_picker_more": "🌍 Daha fazla dil", "translation_picker_back": "⬅️ Geri", "translation_picker_no_charge": "Xu kesilmez.", "translation_text_confirm_title": "🌐 Metin çevirisini onayla", "translation_text_confirm_target": "Hedef", "translation_text_confirm_continue": "TOAN AAS henüz metni çevirmedi ve Xu kesmedi. Devam etmek için onaylayın.", "translation_text_confirm_action": "✅ Çeviriyi onayla", "translation_text_cancel": "❌ İptal", "translation_result_more": "🔁 Daha fazla çevir", "translation_result_change": "🌐 Dili değiştir", "translation_result_direction": "Çeviri yönü", "translation_result_original": "Özgün metin", "translation_result_translated": "Çeviri", "translation_result_no_charge": "Xu kesilmez.", "translation_auto_target": "🌐 Otomatik çeviri hedefi", "translation_interface_language": "🌍 Bot arayüz dili", "translation_input_too_long": "Metin çok uzun. Kararlı çeviri için daha kısa bölümlere ayırın. Xu kesilmez.", "translation_service_unavailable": "Çeviri hizmeti işlem kapasitesini kontrol ediyor. TOAN AAS işlem yapmadı ve Xu kesmedi. Daha sonra tekrar deneyin.",
    },
    "th": {
        "translation_session_two_way_title": "🔁 เปิดการแปลสองทางแล้ว", "translation_session_live_title": "🗣 เปิดโหมดล่ามแล้ว", "translation_session_pair": "คู่ภาษา", "translation_session_input": "ข้อมูลเข้า", "translation_session_output": "ผลลัพธ์", "translation_session_send": "ส่งข้อความหรือเสียง TOAN AAS จะแปลเป็น {target}; แตะสลับทิศทางเพื่อแปลย้อนกลับ", "translation_session_voice_fallback": "หากยังใช้เสียงตอบกลับไม่ได้ ระบบจะส่งคำแปลเป็นข้อความให้ Xu จะไม่ถูกหัก", "translation_session_swap": "🔄 สลับทิศทาง", "translation_session_change_pair": "🌍 เปลี่ยนคู่ภาษา", "translation_session_enable_voice": "🎙 เปิดเสียง", "translation_session_stop": "⏹ หยุดการแปล", "translation_pair_source": "🌐 จาก", "translation_pair_target": "➡️ เป็น", "translation_pair_start": "✅ เริ่ม", "translation_picker_source": "ภาษาต้นทาง", "translation_picker_target": "ภาษาปลายทาง", "translation_picker_choose": "🌐 เลือกภาษา", "translation_picker_auto_detect": "🌍 ตรวจจับอัตโนมัติ", "translation_picker_more": "🌍 ภาษาเพิ่มเติม", "translation_picker_back": "⬅️ กลับ", "translation_picker_no_charge": "Xu จะไม่ถูกหัก", "translation_text_confirm_title": "🌐 ยืนยันการแปลข้อความ", "translation_text_confirm_target": "ภาษาเป้าหมาย", "translation_text_confirm_continue": "TOAN AAS ยังไม่ได้แปลข้อความและยังไม่หัก Xu กดยืนยันเพื่อดำเนินการต่อ", "translation_text_confirm_action": "✅ ยืนยันการแปล", "translation_text_cancel": "❌ ยกเลิก", "translation_result_more": "🔁 แปลต่อ", "translation_result_change": "🌐 เปลี่ยนภาษา", "translation_result_direction": "ทิศทางการแปล", "translation_result_original": "ต้นฉบับ", "translation_result_translated": "คำแปล", "translation_result_no_charge": "Xu จะไม่ถูกหัก", "translation_auto_target": "🌐 ภาษาเป้าหมายอัตโนมัติ", "translation_interface_language": "🌍 ภาษาหน้าจอบอต", "translation_input_too_long": "ข้อความยาวเกินไป โปรดแบ่งเป็นส่วนสั้น ๆ เพื่อการแปลที่เสถียร Xu จะไม่ถูกหัก", "translation_service_unavailable": "บริการแปลกำลังตรวจสอบทรัพยากรประมวลผล TOAN AAS ยังไม่ประมวลผลและยังไม่หัก Xu โปรดลองอีกครั้งภายหลัง",
    },
    "fil": {
        "translation_session_two_way_title": "🔁 Naka-on ang dalawang-daan na pagsasalin", "translation_session_live_title": "🗣 Naka-on ang interpreter mode", "translation_session_pair": "Pares ng wika", "translation_session_input": "Input", "translation_session_output": "Output", "translation_session_send": "Magpadala ng text o voice. Isasalin ng TOAN AAS sa {target}; pindutin ang Palitan ang direksyon para sa kabaligtaran.", "translation_session_voice_fallback": "Kung hindi handa ang voice output, ipapadala pa rin ang salin sa text. Walang mababawas na Xu.", "translation_session_swap": "🔄 Palitan ang direksyon", "translation_session_change_pair": "🌍 Palitan ang mga wika", "translation_session_enable_voice": "🎙 I-on ang boses", "translation_session_stop": "⏹ Ihinto ang pagsasalin", "translation_pair_source": "🌐 Mula sa", "translation_pair_target": "➡️ Patungo sa", "translation_pair_start": "✅ Simulan", "translation_picker_source": "pinagmulan na wika", "translation_picker_target": "target na wika", "translation_picker_choose": "🌐 Pumili ng wika", "translation_picker_auto_detect": "🌍 Awtomatikong tukuyin", "translation_picker_more": "🌍 Higit pang wika", "translation_picker_back": "⬅️ Bumalik", "translation_picker_no_charge": "Walang mababawas na Xu.", "translation_text_confirm_title": "🌐 Kumpirmahin ang pagsasalin ng text", "translation_text_confirm_target": "Target", "translation_text_confirm_continue": "Hindi pa naisalin ng TOAN AAS ang text at wala pang nababawas na Xu. Kumpirmahin upang magpatuloy.", "translation_text_confirm_action": "✅ Kumpirmahin ang pagsasalin", "translation_text_cancel": "❌ Kanselahin", "translation_result_more": "🔁 Magpatuloy sa pagsasalin", "translation_result_change": "🌐 Palitan ang wika", "translation_result_direction": "Direksyon ng pagsasalin", "translation_result_original": "Orihinal", "translation_result_translated": "Salin", "translation_result_no_charge": "Walang mababawas na Xu.", "translation_auto_target": "🌐 Target ng awtomatikong pagsasalin", "translation_interface_language": "🌍 Wika ng interface ng bot", "translation_input_too_long": "Masyadong mahaba ang text. Hatiin ito sa mas maiikling bahagi para sa maayos na pagsasalin. Walang mababawas na Xu.", "translation_service_unavailable": "Sinusuri ng serbisyo ng pagsasalin ang kakayahan sa pagproseso. Walang naproseso o nabawas na Xu ang TOAN AAS. Subukan muli mamaya.",
    },
    "it": {
        "translation_session_two_way_title": "🔁 Traduzione bidirezionale attivata", "translation_session_live_title": "🗣 Modalità interprete attivata", "translation_session_pair": "Coppia di lingue", "translation_session_input": "Input", "translation_session_output": "Output", "translation_session_send": "Invia testo o voce. TOAN AAS tradurrà in {target}; tocca Inverti per tradurre nell’altra direzione.", "translation_session_voice_fallback": "Se l’uscita vocale non è disponibile, verrà comunque inviato il testo tradotto. Nessun Xu viene addebitato.", "translation_session_swap": "🔄 Inverti", "translation_session_change_pair": "🌍 Cambia lingue", "translation_session_enable_voice": "🎙 Attiva voce", "translation_session_stop": "⏹ Interrompi traduzione", "translation_pair_source": "🌐 Da", "translation_pair_target": "➡️ A", "translation_pair_start": "✅ Avvia", "translation_picker_source": "lingua di origine", "translation_picker_target": "lingua di destinazione", "translation_picker_choose": "🌐 Scegli lingua", "translation_picker_auto_detect": "🌍 Rileva automaticamente", "translation_picker_more": "🌍 Altre lingue", "translation_picker_back": "⬅️ Indietro", "translation_picker_no_charge": "Nessun Xu viene addebitato.", "translation_text_confirm_title": "🌐 Conferma la traduzione del testo", "translation_text_confirm_target": "Destinazione", "translation_text_confirm_continue": "TOAN AAS non ha ancora tradotto il testo né addebitato Xu. Conferma per continuare.", "translation_text_confirm_action": "✅ Conferma traduzione", "translation_text_cancel": "❌ Annulla", "translation_result_more": "🔁 Traduci ancora", "translation_result_change": "🌐 Cambia lingua", "translation_result_direction": "Direzione della traduzione", "translation_result_original": "Originale", "translation_result_translated": "Traduzione", "translation_result_no_charge": "Nessun Xu viene addebitato.", "translation_auto_target": "🌐 Destinazione della traduzione automatica", "translation_interface_language": "🌍 Lingua dell’interfaccia del bot", "translation_input_too_long": "Il testo è troppo lungo. Suddividilo in parti più brevi per una traduzione affidabile. Nessun Xu viene addebitato.", "translation_service_unavailable": "Il servizio di traduzione sta verificando la capacità di elaborazione. TOAN AAS non ha elaborato né addebitato Xu. Riprova più tardi.",
    },
    "id": {
        "translation_session_two_way_title": "🔁 Terjemahan dua arah aktif", "translation_session_live_title": "🗣 Mode penerjemah aktif", "translation_session_pair": "Pasangan bahasa", "translation_session_input": "Masukan", "translation_session_output": "Keluaran", "translation_session_send": "Kirim teks atau suara. TOAN AAS akan menerjemahkan ke {target}; ketuk Tukar arah untuk menerjemahkan sebaliknya.", "translation_session_voice_fallback": "Jika keluaran suara belum tersedia, terjemahan teks tetap dikirim. Xu tidak dipotong.", "translation_session_swap": "🔄 Tukar arah", "translation_session_change_pair": "🌍 Ubah bahasa", "translation_session_enable_voice": "🎙 Aktifkan suara", "translation_session_stop": "⏹ Hentikan terjemahan", "translation_pair_source": "🌐 Dari", "translation_pair_target": "➡️ Ke", "translation_pair_start": "✅ Mulai", "translation_picker_source": "bahasa sumber", "translation_picker_target": "bahasa target", "translation_picker_choose": "🌐 Pilih bahasa", "translation_picker_auto_detect": "🌍 Deteksi otomatis", "translation_picker_more": "🌍 Bahasa lainnya", "translation_picker_back": "⬅️ Kembali", "translation_picker_no_charge": "Xu tidak dipotong.", "translation_text_confirm_title": "🌐 Konfirmasi terjemahan teks", "translation_text_confirm_target": "Target", "translation_text_confirm_continue": "TOAN AAS belum menerjemahkan teks atau memotong Xu. Konfirmasi untuk melanjutkan.", "translation_text_confirm_action": "✅ Konfirmasi terjemahan", "translation_text_cancel": "❌ Batal", "translation_result_more": "🔁 Terjemahkan lagi", "translation_result_change": "🌐 Ubah bahasa", "translation_result_direction": "Arah terjemahan", "translation_result_original": "Teks asli", "translation_result_translated": "Terjemahan", "translation_result_no_charge": "Xu tidak dipotong.", "translation_auto_target": "🌐 Target terjemahan otomatis", "translation_interface_language": "🌍 Bahasa antarmuka bot", "translation_input_too_long": "Teks terlalu panjang. Bagi menjadi bagian lebih pendek agar terjemahan stabil. Xu tidak dipotong.", "translation_service_unavailable": "Layanan terjemahan sedang memeriksa kapasitas pemrosesan. TOAN AAS belum memproses atau memotong Xu. Silakan coba lagi nanti.",
    },
}

# The following generic templates are assembled only by presentation renderers.
# They never decide a target language, mutate a session, or call a provider.
for _locale, _copy in _PUBLIC_TRANSLATION_FLOW_COPY.items():
    _copy.update({
        "translation_text_entry_title": _copy["translation_text_confirm_title"],
        "translation_text_entry_body": f"{_copy['translation_picker_target']}. {_copy['translation_picker_no_charge']}",
        "translation_text_custom_target": _copy["translation_picker_target"],
        "translation_two_way_entry": _copy["translation_session_two_way_title"],
        "translation_live_entry": _copy["translation_session_live_title"],
        "translation_pair_choose": f"{_copy['translation_picker_source']} / {_copy['translation_picker_target']}",
        "translation_pair_swapped": _copy["translation_session_swap"],
        "translation_no_active_session": _copy["translation_session_stop"],
        "translation_output_text_enabled": _copy["translation_result_translated"],
        "translation_output_voice_enabled": _copy["translation_session_enable_voice"],
        "translation_document_title": _copy["translation_text_confirm_title"],
        "translation_document_body": f"{_copy['translation_picker_target']}. {_copy['translation_picker_no_charge']}",
        "translation_language_options_body": f"{_copy['translation_auto_target']}. {_copy['translation_interface_language']}.",
        "translation_result_title": _copy["translation_result_translated"],
        "translation_cancelled": _copy["translation_text_cancel"],
        "translation_target_label_vi": "Tiếng Việt", "translation_target_label_en": "English", "translation_target_label_zh": "中文", "translation_target_label_ja": "日本語", "translation_target_label_ko": "한국어", "translation_target_label_th": "ไทย",
    })


# File and voice Translation remain presentation-only.  These are direct
# locale values for customer-facing validation, receipt and guard messages;
# they do not decide session state, routing, providers, or billing.
_PUBLIC_TRANSLATION_MEDIA_COPY = {
    "vi": {
        "translation_file_entry_body": "Gửi file cần dịch. Luồng này chỉ dùng cho file, không dùng cho video hoặc audio.",
        "translation_file_only": "Luồng này chỉ dùng để dịch file. Hãy chọn Dịch audio hoặc Phụ đề / Lồng tiếng nếu cần xử lý video hoặc audio.",
        "translation_audio_video_redirect": "Luồng này chỉ dùng để dịch audio. Nếu muốn xử lý video, hãy chọn các nút video trong Phụ đề / Lồng tiếng.",
        "translation_audio_need_file": "Hãy gửi voice hoặc file âm thanh cần dịch.",
        "translation_recent_media_missing": "Gửi hoặc reply voice, audio hoặc video ngắn trong vòng 2 phút rồi dùng /translate_voice.",
        "translation_recent_file_missing": "Gửi hoặc reply file txt/docx/pdf trong vòng 10 phút rồi dùng /translate_file.",
        "translation_invalid_selection": "Không nhận diện được lựa chọn dịch.",
        "translation_invalid_target": "Lựa chọn ngôn ngữ không hợp lệ.",
        "translation_unsupported_source": "Nguồn dịch chưa được hỗ trợ.",
        "translation_voice_guard": "Dịch voice đang chờ tài nguyên xử lý. TOAN AAS chưa xử lý và chưa trừ Xu.",
        "translation_audio_received_body": "Đã nhận audio/voice. Bạn có thể bóc băng, dịch sang ngôn ngữ khác hoặc dùng lệnh nhanh.",
        "translation_transcribe": "🎙 Bóc băng",
        "translation_pair_example_or": "hoặc",
    },
    "en": {
        "translation_file_entry_body": "Send the file to translate. This flow is for files only, not video or audio.",
        "translation_file_only": "This flow translates files only. Choose Audio translation or Subtitles / dubbing to process video or audio.",
        "translation_audio_video_redirect": "This flow translates audio only. To process a video, use a video option in Subtitles / dubbing.",
        "translation_audio_need_file": "Send the voice message or audio file to translate.",
        "translation_recent_media_missing": "Send or reply to a short voice, audio, or video within 2 minutes, then use /translate_voice.",
        "translation_recent_file_missing": "Send or reply to a txt/docx/pdf file within 10 minutes, then use /translate_file.",
        "translation_invalid_selection": "Translation selection was not recognized.",
        "translation_invalid_target": "The language selection is invalid.",
        "translation_unsupported_source": "This translation source is not supported.",
        "translation_voice_guard": "Voice translation is waiting for processing capacity. TOAN AAS has not processed or charged Xu.",
        "translation_audio_received_body": "Voice or audio received. You can transcribe it, translate it into another language, or use a quick command.",
        "translation_transcribe": "🎙 Transcribe",
        "translation_pair_example_or": "or",
    },
    "zh": {
        "translation_file_entry_body": "发送需要翻译的文件。此流程仅用于文件，不处理视频或音频。",
        "translation_file_only": "此流程仅用于翻译文件。如需处理视频或音频，请选择音频翻译或字幕 / 配音。",
        "translation_audio_video_redirect": "此流程仅用于翻译音频。如需处理视频，请在字幕 / 配音中选择视频功能。",
        "translation_audio_need_file": "请发送需要翻译的语音或音频文件。",
        "translation_recent_media_missing": "请在 2 分钟内发送或回复一段短语音、音频或视频，然后使用 /translate_voice。",
        "translation_recent_file_missing": "请在 10 分钟内发送或回复 txt/docx/pdf 文件，然后使用 /translate_file。",
        "translation_invalid_selection": "无法识别翻译选项。",
        "translation_invalid_target": "语言选项无效。",
        "translation_unsupported_source": "暂不支持此翻译来源。",
        "translation_voice_guard": "语音翻译正在等待处理资源。TOAN AAS 尚未处理，也未扣除 Xu。",
        "translation_audio_received_body": "已收到语音或音频。您可以转写为文字、翻译成其他语言，或使用快捷命令。",
        "translation_transcribe": "🎙 转写",
        "translation_pair_example_or": "或",
    },
    "es": {
        "translation_file_entry_body": "Envía el archivo que deseas traducir. Este flujo es solo para archivos, no para vídeo ni audio.",
        "translation_file_only": "Este flujo solo traduce archivos. Para procesar vídeo o audio, elige Traducción de audio o Subtítulos / doblaje.",
        "translation_audio_video_redirect": "Este flujo solo traduce audio. Para procesar vídeo, usa una opción de vídeo en Subtítulos / doblaje.",
        "translation_audio_need_file": "Envía el mensaje de voz o archivo de audio que deseas traducir.",
        "translation_recent_media_missing": "Envía o responde a una nota de voz, audio o vídeo corto en 2 minutos y usa /translate_voice.",
        "translation_recent_file_missing": "Envía o responde a un archivo txt/docx/pdf en 10 minutos y usa /translate_file.",
        "translation_invalid_selection": "No se reconoció la opción de traducción.",
        "translation_invalid_target": "La selección de idioma no es válida.",
        "translation_unsupported_source": "Esta fuente de traducción no es compatible.",
        "translation_voice_guard": "La traducción de voz está esperando capacidad de procesamiento. TOAN AAS no ha procesado ni cobrado Xu.",
        "translation_audio_received_body": "Se recibió voz o audio. Puedes transcribirlo, traducirlo a otro idioma o usar un comando rápido.",
        "translation_transcribe": "🎙 Transcribir",
        "translation_pair_example_or": "o",
    },
    "pt": {
        "translation_file_entry_body": "Envie o arquivo que deseja traduzir. Este fluxo é apenas para arquivos, não para vídeo ou áudio.",
        "translation_file_only": "Este fluxo traduz apenas arquivos. Para processar vídeo ou áudio, escolha Tradução de áudio ou Legendas / dublagem.",
        "translation_audio_video_redirect": "Este fluxo traduz apenas áudio. Para processar vídeo, use uma opção em Legendas / dublagem.",
        "translation_audio_need_file": "Envie a mensagem de voz ou arquivo de áudio que deseja traduzir.",
        "translation_recent_media_missing": "Envie ou responda a uma mensagem de voz, áudio ou vídeo curto em 2 minutos e use /translate_voice.",
        "translation_recent_file_missing": "Envie ou responda a um arquivo txt/docx/pdf em 10 minutos e use /translate_file.",
        "translation_invalid_selection": "A escolha de tradução não foi reconhecida.",
        "translation_invalid_target": "A escolha de idioma é inválida.",
        "translation_unsupported_source": "Esta origem de tradução não é compatível.",
        "translation_voice_guard": "A tradução de voz está aguardando capacidade de processamento. A TOAN AAS não processou nem cobrou Xu.",
        "translation_audio_received_body": "Voz ou áudio recebido. Você pode transcrever, traduzir para outro idioma ou usar um comando rápido.",
        "translation_transcribe": "🎙 Transcrever",
        "translation_pair_example_or": "ou",
    },
    "fr": {
        "translation_file_entry_body": "Envoyez le fichier à traduire. Ce flux concerne uniquement les fichiers, pas la vidéo ni l’audio.",
        "translation_file_only": "Ce flux traduit uniquement les fichiers. Pour traiter une vidéo ou un audio, choisissez Traduction audio ou Sous-titres / doublage.",
        "translation_audio_video_redirect": "Ce flux traduit uniquement l’audio. Pour traiter une vidéo, utilisez une option vidéo dans Sous-titres / doublage.",
        "translation_audio_need_file": "Envoyez le message vocal ou le fichier audio à traduire.",
        "translation_recent_media_missing": "Envoyez ou répondez à un court message vocal, audio ou vidéo dans les 2 minutes, puis utilisez /translate_voice.",
        "translation_recent_file_missing": "Envoyez ou répondez à un fichier txt/docx/pdf dans les 10 minutes, puis utilisez /translate_file.",
        "translation_invalid_selection": "Le choix de traduction n’a pas été reconnu.",
        "translation_invalid_target": "Le choix de langue est invalide.",
        "translation_unsupported_source": "Cette source de traduction n’est pas prise en charge.",
        "translation_voice_guard": "La traduction vocale attend de la capacité de traitement. TOAN AAS n’a rien traité ni débité de Xu.",
        "translation_audio_received_body": "Message vocal ou audio reçu. Vous pouvez le transcrire, le traduire dans une autre langue ou utiliser une commande rapide.",
        "translation_transcribe": "🎙 Transcrire",
        "translation_pair_example_or": "ou",
    },
    "de": {
        "translation_file_entry_body": "Sende die zu übersetzende Datei. Dieser Ablauf ist nur für Dateien, nicht für Video oder Audio.",
        "translation_file_only": "Dieser Ablauf übersetzt nur Dateien. Für Video oder Audio wähle Audioübersetzung oder Untertitel / Synchronisation.",
        "translation_audio_video_redirect": "Dieser Ablauf übersetzt nur Audio. Für Video verwende eine Videooption unter Untertitel / Synchronisation.",
        "translation_audio_need_file": "Sende die zu übersetzende Sprachnachricht oder Audiodatei.",
        "translation_recent_media_missing": "Sende oder beantworte innerhalb von 2 Minuten eine kurze Sprach-, Audio- oder Videodatei und nutze /translate_voice.",
        "translation_recent_file_missing": "Sende oder beantworte innerhalb von 10 Minuten eine txt/docx/pdf-Datei und nutze /translate_file.",
        "translation_invalid_selection": "Die Übersetzungsauswahl wurde nicht erkannt.",
        "translation_invalid_target": "Die Sprachauswahl ist ungültig.",
        "translation_unsupported_source": "Diese Übersetzungsquelle wird nicht unterstützt.",
        "translation_voice_guard": "Die Sprachübersetzung wartet auf Verarbeitungskapazität. TOAN AAS hat nichts verarbeitet und kein Xu berechnet.",
        "translation_audio_received_body": "Sprach- oder Audiodatei empfangen. Du kannst sie transkribieren, in eine andere Sprache übersetzen oder einen Schnellbefehl verwenden.",
        "translation_transcribe": "🎙 Transkribieren",
        "translation_pair_example_or": "oder",
    },
    "ja": {
        "translation_file_entry_body": "翻訳するファイルを送信してください。このフローはファイル専用で、動画や音声には使用できません。",
        "translation_file_only": "このフローはファイル翻訳専用です。動画や音声は「音声翻訳」または「字幕 / 吹き替え」を選択してください。",
        "translation_audio_video_redirect": "このフローは音声翻訳専用です。動画を処理する場合は「字幕 / 吹き替え」の動画機能を使用してください。",
        "translation_audio_need_file": "翻訳する音声メッセージまたは音声ファイルを送信してください。",
        "translation_recent_media_missing": "2分以内に短い音声、オーディオ、動画を送信または返信してから、/translate_voice を使用してください。",
        "translation_recent_file_missing": "10分以内に txt/docx/pdf ファイルを送信または返信してから、/translate_file を使用してください。",
        "translation_invalid_selection": "翻訳の選択を認識できませんでした。",
        "translation_invalid_target": "言語の選択が無効です。",
        "translation_unsupported_source": "この翻訳元はサポートされていません。",
        "translation_voice_guard": "音声翻訳は処理リソースを待機中です。TOAN AAS は処理も Xu の消費もしていません。",
        "translation_audio_received_body": "音声またはオーディオを受信しました。文字起こし、別の言語への翻訳、またはクイックコマンドを利用できます。",
        "translation_transcribe": "🎙 文字起こし",
        "translation_pair_example_or": "または",
    },
    "ko": {
        "translation_file_entry_body": "번역할 파일을 보내세요. 이 흐름은 파일 전용이며 동영상이나 오디오에는 사용할 수 없습니다.",
        "translation_file_only": "이 흐름은 파일만 번역합니다. 동영상이나 오디오는 오디오 번역 또는 자막 / 더빙을 선택하세요.",
        "translation_audio_video_redirect": "이 흐름은 오디오만 번역합니다. 동영상을 처리하려면 자막 / 더빙의 동영상 기능을 사용하세요.",
        "translation_audio_need_file": "번역할 음성 메시지 또는 오디오 파일을 보내세요.",
        "translation_recent_media_missing": "2분 안에 짧은 음성, 오디오 또는 동영상을 보내거나 답장한 후 /translate_voice를 사용하세요.",
        "translation_recent_file_missing": "10분 안에 txt/docx/pdf 파일을 보내거나 답장한 후 /translate_file을 사용하세요.",
        "translation_invalid_selection": "번역 선택을 인식하지 못했습니다.",
        "translation_invalid_target": "언어 선택이 올바르지 않습니다.",
        "translation_unsupported_source": "이 번역 원본은 지원되지 않습니다.",
        "translation_voice_guard": "음성 번역이 처리 용량을 기다리고 있습니다. TOAN AAS는 처리하거나 Xu를 차감하지 않았습니다.",
        "translation_audio_received_body": "음성 또는 오디오를 받았습니다. 받아쓰기를 하거나 다른 언어로 번역하거나 빠른 명령을 사용할 수 있습니다.",
        "translation_transcribe": "🎙 받아쓰기",
        "translation_pair_example_or": "또는",
    },
    "hi": {
        "translation_file_entry_body": "अनुवाद करने के लिए फ़ाइल भेजें। यह प्रवाह केवल फ़ाइलों के लिए है, वीडियो या ऑडियो के लिए नहीं।",
        "translation_file_only": "यह प्रवाह केवल फ़ाइलों का अनुवाद करता है। वीडियो या ऑडियो के लिए ऑडियो अनुवाद या उपशीर्षक / डबिंग चुनें।",
        "translation_audio_video_redirect": "यह प्रवाह केवल ऑडियो का अनुवाद करता है। वीडियो के लिए उपशीर्षक / डबिंग में वीडियो विकल्प उपयोग करें।",
        "translation_audio_need_file": "अनुवाद करने के लिए वॉइस संदेश या ऑडियो फ़ाइल भेजें।",
        "translation_recent_media_missing": "2 मिनट में छोटा वॉइस, ऑडियो या वीडियो भेजें या उत्तर दें, फिर /translate_voice उपयोग करें।",
        "translation_recent_file_missing": "10 मिनट में txt/docx/pdf फ़ाइल भेजें या उत्तर दें, फिर /translate_file उपयोग करें।",
        "translation_invalid_selection": "अनुवाद चयन पहचाना नहीं गया।",
        "translation_invalid_target": "भाषा चयन अमान्य है।",
        "translation_unsupported_source": "यह अनुवाद स्रोत समर्थित नहीं है।",
        "translation_voice_guard": "वॉइस अनुवाद प्रसंस्करण क्षमता की प्रतीक्षा कर रहा है। TOAN AAS ने संसाधित नहीं किया और Xu नहीं काटा।",
        "translation_audio_received_body": "वॉइस या ऑडियो प्राप्त हुआ। आप इसे लिखित रूप में बदल सकते हैं, दूसरी भाषा में अनुवाद कर सकते हैं या त्वरित कमांड का उपयोग कर सकते हैं।",
        "translation_transcribe": "🎙 लिप्यंतरण",
        "translation_pair_example_or": "या",
    },
    "ar": {
        "translation_file_entry_body": "أرسل الملف المراد ترجمته. هذا المسار للملفات فقط وليس للفيديو أو الصوت.",
        "translation_file_only": "هذا المسار يترجم الملفات فقط. لمعالجة الفيديو أو الصوت اختر ترجمة الصوت أو الترجمة النصية / الدبلجة.",
        "translation_audio_video_redirect": "هذا المسار يترجم الصوت فقط. لمعالجة فيديو استخدم خيار فيديو في الترجمة النصية / الدبلجة.",
        "translation_audio_need_file": "أرسل الرسالة الصوتية أو الملف الصوتي المراد ترجمته.",
        "translation_recent_media_missing": "أرسل أو رد على رسالة صوتية أو ملف صوتي أو فيديو قصير خلال دقيقتين ثم استخدم /translate_voice.",
        "translation_recent_file_missing": "أرسل أو رد على ملف txt/docx/pdf خلال 10 دقائق ثم استخدم /translate_file.",
        "translation_invalid_selection": "تعذر التعرف على اختيار الترجمة.",
        "translation_invalid_target": "اختيار اللغة غير صالح.",
        "translation_unsupported_source": "مصدر الترجمة هذا غير مدعوم.",
        "translation_voice_guard": "الترجمة الصوتية بانتظار سعة المعالجة. لم يعالج TOAN AAS شيئاً ولم يخصم Xu.",
        "translation_audio_received_body": "تم استلام رسالة صوتية أو ملف صوتي. يمكنك تفريغه أو ترجمته إلى لغة أخرى أو استخدام أمر سريع.",
        "translation_transcribe": "🎙 تفريغ صوتي",
        "translation_pair_example_or": "أو",
    },
    "ru": {
        "translation_file_entry_body": "Отправьте файл для перевода. Этот путь предназначен только для файлов, не для видео или аудио.",
        "translation_file_only": "Этот путь переводит только файлы. Для видео или аудио выберите перевод аудио или субтитры / дубляж.",
        "translation_audio_video_redirect": "Этот путь переводит только аудио. Для видео используйте опцию видео в разделе субтитров / дубляжа.",
        "translation_audio_need_file": "Отправьте голосовое сообщение или аудиофайл для перевода.",
        "translation_recent_media_missing": "В течение 2 минут отправьте или ответьте на короткое голосовое, аудио или видео, затем используйте /translate_voice.",
        "translation_recent_file_missing": "В течение 10 минут отправьте или ответьте на файл txt/docx/pdf, затем используйте /translate_file.",
        "translation_invalid_selection": "Выбор перевода не распознан.",
        "translation_invalid_target": "Выбор языка недействителен.",
        "translation_unsupported_source": "Этот источник перевода не поддерживается.",
        "translation_voice_guard": "Голосовой перевод ожидает ресурсы обработки. TOAN AAS ничего не обработал и не списал Xu.",
        "translation_audio_received_body": "Получено голосовое сообщение или аудио. Можно расшифровать его, перевести на другой язык или использовать быструю команду.",
        "translation_transcribe": "🎙 Расшифровать",
        "translation_pair_example_or": "или",
    },
    "tr": {
        "translation_file_entry_body": "Çevrilecek dosyayı gönderin. Bu akış yalnızca dosyalar içindir; video veya ses için değildir.",
        "translation_file_only": "Bu akış yalnızca dosyaları çevirir. Video veya ses için Ses çevirisi ya da Altyazılar / dublajı seçin.",
        "translation_audio_video_redirect": "Bu akış yalnızca sesi çevirir. Video için Altyazılar / dublaj içindeki video seçeneğini kullanın.",
        "translation_audio_need_file": "Çevrilecek sesli mesajı veya ses dosyasını gönderin.",
        "translation_recent_media_missing": "2 dakika içinde kısa bir sesli mesaj, ses veya video gönderin ya da yanıtlayın; ardından /translate_voice kullanın.",
        "translation_recent_file_missing": "10 dakika içinde bir txt/docx/pdf dosyası gönderin ya da yanıtlayın; ardından /translate_file kullanın.",
        "translation_invalid_selection": "Çeviri seçimi tanınmadı.",
        "translation_invalid_target": "Dil seçimi geçersiz.",
        "translation_unsupported_source": "Bu çeviri kaynağı desteklenmiyor.",
        "translation_voice_guard": "Sesli çeviri işlem kapasitesini bekliyor. TOAN AAS işlem yapmadı ve Xu kesmedi.",
        "translation_audio_received_body": "Sesli mesaj veya ses alındı. Yazıya dökebilir, başka bir dile çevirebilir veya hızlı komut kullanabilirsiniz.",
        "translation_transcribe": "🎙 Yazıya dök",
        "translation_pair_example_or": "veya",
    },
    "th": {
        "translation_file_entry_body": "ส่งไฟล์ที่ต้องการแปล ขั้นตอนนี้ใช้สำหรับไฟล์เท่านั้น ไม่ใช้กับวิดีโอหรือเสียง",
        "translation_file_only": "ขั้นตอนนี้แปลไฟล์เท่านั้น หากต้องการจัดการวิดีโอหรือเสียง ให้เลือกแปลเสียงหรือคำบรรยาย / พากย์",
        "translation_audio_video_redirect": "ขั้นตอนนี้แปลเสียงเท่านั้น หากต้องการจัดการวิดีโอ ให้ใช้ตัวเลือกวิดีโอในคำบรรยาย / พากย์",
        "translation_audio_need_file": "ส่งข้อความเสียงหรือไฟล์เสียงที่ต้องการแปล",
        "translation_recent_media_missing": "ส่งหรือตอบกลับเสียง ไฟล์เสียง หรือวิดีโอสั้นภายใน 2 นาที แล้วใช้ /translate_voice",
        "translation_recent_file_missing": "ส่งหรือตอบกลับไฟล์ txt/docx/pdf ภายใน 10 นาที แล้วใช้ /translate_file",
        "translation_invalid_selection": "ไม่พบตัวเลือกการแปล",
        "translation_invalid_target": "การเลือกภาษาไม่ถูกต้อง",
        "translation_unsupported_source": "ไม่รองรับแหล่งที่มาของการแปลนี้",
        "translation_voice_guard": "การแปลเสียงกำลังรอทรัพยากรประมวลผล TOAN AAS ยังไม่ประมวลผลและยังไม่หัก Xu",
        "translation_audio_received_body": "ได้รับเสียงหรือไฟล์เสียงแล้ว คุณสามารถถอดเสียง แปลเป็นภาษาอื่น หรือใช้คำสั่งด่วนได้",
        "translation_transcribe": "🎙 ถอดเสียง",
        "translation_pair_example_or": "หรือ",
    },
    "fil": {
        "translation_file_entry_body": "Ipadala ang file na isasalin. Para lamang ito sa mga file, hindi sa video o audio.",
        "translation_file_only": "Mga file lamang ang isinasalin ng daloy na ito. Para sa video o audio, piliin ang Pagsasalin ng audio o Mga subtitle / dubbing.",
        "translation_audio_video_redirect": "Audio lamang ang isinasalin ng daloy na ito. Para sa video, gumamit ng opsyon sa video sa Mga subtitle / dubbing.",
        "translation_audio_need_file": "Ipadala ang voice message o audio file na isasalin.",
        "translation_recent_media_missing": "Magpadala o tumugon sa maikling voice, audio o video sa loob ng 2 minuto, pagkatapos ay gamitin ang /translate_voice.",
        "translation_recent_file_missing": "Magpadala o tumugon sa txt/docx/pdf file sa loob ng 10 minuto, pagkatapos ay gamitin ang /translate_file.",
        "translation_invalid_selection": "Hindi nakilala ang pagpili sa pagsasalin.",
        "translation_invalid_target": "Hindi wasto ang pagpili ng wika.",
        "translation_unsupported_source": "Hindi suportado ang pinagmulan ng pagsasaling ito.",
        "translation_voice_guard": "Naghihintay ng kapasidad sa pagproseso ang pagsasalin ng voice. Walang naproseso o nabawas na Xu ang TOAN AAS.",
        "translation_audio_received_body": "Natanggap ang voice o audio. Maaari mo itong i-transcribe, isalin sa ibang wika o gumamit ng mabilis na command.",
        "translation_transcribe": "🎙 I-transcribe",
        "translation_pair_example_or": "o",
    },
    "it": {
        "translation_file_entry_body": "Invia il file da tradurre. Questo flusso è solo per file, non per video o audio.",
        "translation_file_only": "Questo flusso traduce solo file. Per video o audio scegli Traduzione audio o Sottotitoli / doppiaggio.",
        "translation_audio_video_redirect": "Questo flusso traduce solo audio. Per elaborare un video usa un’opzione video in Sottotitoli / doppiaggio.",
        "translation_audio_need_file": "Invia il messaggio vocale o il file audio da tradurre.",
        "translation_recent_media_missing": "Invia o rispondi a un breve messaggio vocale, audio o video entro 2 minuti, poi usa /translate_voice.",
        "translation_recent_file_missing": "Invia o rispondi a un file txt/docx/pdf entro 10 minuti, poi usa /translate_file.",
        "translation_invalid_selection": "La scelta della traduzione non è stata riconosciuta.",
        "translation_invalid_target": "La scelta della lingua non è valida.",
        "translation_unsupported_source": "Questa origine di traduzione non è supportata.",
        "translation_voice_guard": "La traduzione vocale attende capacità di elaborazione. TOAN AAS non ha elaborato né addebitato Xu.",
        "translation_audio_received_body": "Messaggio vocale o audio ricevuto. Puoi trascriverlo, tradurlo in un’altra lingua o usare un comando rapido.",
        "translation_transcribe": "🎙 Trascrivi",
        "translation_pair_example_or": "o",
    },
    "id": {
        "translation_file_entry_body": "Kirim file yang akan diterjemahkan. Alur ini hanya untuk file, bukan video atau audio.",
        "translation_file_only": "Alur ini hanya menerjemahkan file. Untuk video atau audio, pilih Terjemahan audio atau Subtitle / dubbing.",
        "translation_audio_video_redirect": "Alur ini hanya menerjemahkan audio. Untuk video, gunakan opsi video pada Subtitle / dubbing.",
        "translation_audio_need_file": "Kirim pesan suara atau file audio yang akan diterjemahkan.",
        "translation_recent_media_missing": "Kirim atau balas voice, audio, atau video pendek dalam 2 menit, lalu gunakan /translate_voice.",
        "translation_recent_file_missing": "Kirim atau balas file txt/docx/pdf dalam 10 menit, lalu gunakan /translate_file.",
        "translation_invalid_selection": "Pilihan terjemahan tidak dikenali.",
        "translation_invalid_target": "Pilihan bahasa tidak valid.",
        "translation_unsupported_source": "Sumber terjemahan ini tidak didukung.",
        "translation_voice_guard": "Terjemahan suara sedang menunggu kapasitas pemrosesan. TOAN AAS belum memproses atau memotong Xu.",
        "translation_audio_received_body": "Suara atau audio diterima. Anda dapat menyalinnya, menerjemahkannya ke bahasa lain, atau memakai perintah cepat.",
        "translation_transcribe": "🎙 Transkripsikan",
        "translation_pair_example_or": "atau",
    },
}

for _locale, _copy in _PUBLIC_TRANSLATION_MEDIA_COPY.items():
    _flow = _PUBLIC_TRANSLATION_FLOW_COPY[_locale]
    _actions = _PUBLIC_ROOT_ACTION_COPY[_locale]
    _copy.setdefault("translation_file_entry_title", f"📄 {_actions['translation_file']}")
    _copy.setdefault("translation_audio_only", _copy["translation_audio_video_redirect"])
    _copy.setdefault("translation_input_text_voice", f"{_actions['translation_text']} / {_actions['translation_audio']}")
    _copy.setdefault("translation_input_voice", _actions["translation_audio"])
    _copy.setdefault("translation_output_text", _actions["translation_text"])
    _copy.setdefault("translation_output_voice", _actions["translation_audio"])
    _copy.setdefault("translation_voice_result_title", f"🌐 {_actions['translation_audio']}")
    _copy.setdefault("translation_file_result_title", f"🌐 {_actions['translation_file']}")
    _copy.setdefault("translation_transcript_original", _flow["translation_result_original"])
    _copy.setdefault("translation_tts_caption", _flow["translation_session_enable_voice"])
    _copy.setdefault("translation_file_not_ready", _flow["translation_service_unavailable"])
    _copy.setdefault("translation_file_extract_error", _flow["translation_service_unavailable"])
    _copy.setdefault("translation_file_provider_error", _flow["translation_service_unavailable"])
    _copy.setdefault("translation_file_too_large", _flow["translation_input_too_long"])
    _copy.setdefault("translation_audio_missing_stt", _flow["translation_service_unavailable"])
    _copy.setdefault("translation_audio_error", _flow["translation_service_unavailable"])
    _copy.setdefault("translation_audio_translation_error", _flow["translation_service_unavailable"])
    _copy.setdefault("translation_audio_timeout", _flow["translation_service_unavailable"])


# Direct command and receipt wording for the public Translation flow.  These
# values intentionally do not describe routes, providers, state, credits, or
# execution; they only make the existing customer-facing shell follow the
# active locale instead of falling back to Vietnamese or English.
_PUBLIC_TRANSLATION_COMMAND_COPY = {
    "vi": {
        "translation_command_missing_text": "⚠️ Thiếu nội dung cần dịch. Ví dụ: <code>/translate en xin chào</code>",
        "translation_command_missing_target": "🌐 <b>Dịch voice/audio</b>\n\nChọn ngôn ngữ đích, ví dụ: <code>/translate_voice en</code> hoặc <code>/translate_voice vi</code>.\n\nDùng <code>/translate_tools</code> để xem các lệnh dịch.",
        "translation_tools_title": "🌐 CÔNG CỤ DỊCH TOAN AAS",
        "translation_tools_body": "Dùng <code>/translate en nội dung</code> để dịch văn bản, <code>/translate_file en</code> cho file và <code>/translate_voice en</code> cho voice/audio. Dùng <code>/translate_mode en</code> để bật dịch tự động, hoặc <code>/translate_mode_off</code> để tắt. Chỉ gửi nội dung bạn có quyền sử dụng.",
        "translation_auto_mode_enabled": "✅ Đã bật chế độ dịch tự động sang <b>{target}</b>. Tin nhắn văn bản thường sẽ được dịch thay vì vào AI chat. Tắt bằng <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ Đã tắt chế độ dịch tự động. Tin nhắn thường sẽ quay về AI chat.",
        "translation_auto_mode_already_disabled": "ℹ️ Chế độ dịch tự động đang tắt sẵn.",
        "translation_auto_mode_invalid_target": "⚠️ Ngôn ngữ chưa hỗ trợ. Dùng một mã trong: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 TRẠNG THÁI DỊCH TỰ ĐỘNG",
        "translation_auto_status_enabled": "bật",
        "translation_auto_status_disabled": "tắt",
        "translation_auto_status_target": "Ngôn ngữ đích",
        "translation_auto_status_enable_hint": "Bật: <code>/translate_mode</code> hoặc <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Tắt: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "đã sẵn sàng",
        "translation_transcribe_content": "Nội dung",
        "translation_transcribe_balance": "Còn lại",
        "translation_auto_result_title": "BẢN DỊCH TOAN AAS",
        "translation_auto_result_source": "Nguồn",
        "translation_auto_result_target": "Đích",
        "translation_auto_result_disable_hint": "Dùng <code>/translate_mode_off</code> để tắt.",
        "translation_auto_failed": "❌ Dịch tự động đang tạm lỗi hoặc quá tải. TOAN AAS chưa trừ Xu. Vui lòng thử lại sau.",
        "translation_auto_no_chat_fallback": "Không chuyển sang AI chat để tránh trả lời sai ngữ cảnh.",
        "translation_result_transcript_ready": "Đã bóc băng",
        "translation_result_translation_ready": "Đã dịch",
        "translation_result_already_target": "Nội dung đã ở ngôn ngữ đích",
    },
    "en": {
        "translation_command_missing_text": "⚠️ Translation text is missing. Example: <code>/translate en hello</code>",
        "translation_command_missing_target": "🌐 <b>Voice / audio translation</b>\n\nChoose a target language, for example <code>/translate_voice en</code> or <code>/translate_voice vi</code>.\n\nUse <code>/translate_tools</code> to view translation commands.",
        "translation_tools_title": "🌐 TOAN AAS TRANSLATION TOOLS",
        "translation_tools_body": "Use <code>/translate en text</code> for text, <code>/translate_file en</code> for a file, and <code>/translate_voice en</code> for voice or audio. Use <code>/translate_mode en</code> to enable automatic translation, or <code>/translate_mode_off</code> to turn it off. Send only content you are allowed to use.",
        "translation_auto_mode_enabled": "✅ Auto-translate is enabled to <b>{target}</b>. Normal text messages are translated instead of going to AI chat. Disable it with <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ Auto-translate is disabled. Normal text messages now go back to AI chat.",
        "translation_auto_mode_already_disabled": "ℹ️ Auto-translate is already disabled.",
        "translation_auto_mode_invalid_target": "⚠️ This language is not supported. Use one code from: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 AUTO-TRANSLATE STATUS",
        "translation_auto_status_enabled": "enabled",
        "translation_auto_status_disabled": "disabled",
        "translation_auto_status_target": "Target",
        "translation_auto_status_enable_hint": "Enable: <code>/translate_mode</code> or <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Disable: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "ready",
        "translation_transcribe_content": "Content",
        "translation_transcribe_balance": "Remaining",
        "translation_auto_result_title": "TOAN AAS TRANSLATION",
        "translation_auto_result_source": "Source",
        "translation_auto_result_target": "Target",
        "translation_auto_result_disable_hint": "Use <code>/translate_mode_off</code> to turn it off.",
        "translation_auto_failed": "❌ Automatic translation is temporarily unavailable or busy. TOAN AAS has not charged Xu. Please try again later.",
        "translation_auto_no_chat_fallback": "The message was not sent to AI chat to avoid an answer in the wrong context.",
        "translation_result_transcript_ready": "Transcription ready",
        "translation_result_translation_ready": "Translation ready",
        "translation_result_already_target": "The content is already in the target language",
    },
    "zh": {
        "translation_command_missing_text": "⚠️ 缺少要翻译的内容。示例：<code>/translate en 你好</code>",
        "translation_command_missing_target": "🌐 <b>语音 / 音频翻译</b>\n\n请选择目标语言，例如 <code>/translate_voice en</code> 或 <code>/translate_voice vi</code>。\n\n使用 <code>/translate_tools</code> 查看翻译命令。",
        "translation_tools_title": "🌐 TOAN AAS 翻译工具",
        "translation_tools_body": "文字请使用 <code>/translate en 内容</code>，文件请使用 <code>/translate_file en</code>，语音或音频请使用 <code>/translate_voice en</code>。使用 <code>/translate_mode en</code> 开启自动翻译，使用 <code>/translate_mode_off</code> 关闭。请只发送您有权使用的内容。",
        "translation_auto_mode_enabled": "✅ 已开启自动翻译到 <b>{target}</b>。普通文字消息会被翻译，而不会进入 AI 聊天。使用 <code>/translate_mode_off</code> 关闭。",
        "translation_auto_mode_disabled": "✅ 已关闭自动翻译。普通文字消息会回到 AI 聊天。",
        "translation_auto_mode_already_disabled": "ℹ️ 自动翻译本来就已关闭。",
        "translation_auto_mode_invalid_target": "⚠️ 不支持该语言。请使用以下代码之一：<code>{supported}</code>。",
        "translation_auto_status_title": "🌐 自动翻译状态",
        "translation_auto_status_enabled": "已开启",
        "translation_auto_status_disabled": "已关闭",
        "translation_auto_status_target": "目标语言",
        "translation_auto_status_enable_hint": "开启：<code>/translate_mode</code> 或 <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "关闭：<code>/translate_mode_off</code>",
        "translation_transcribe_ready": "已就绪",
        "translation_transcribe_content": "内容",
        "translation_transcribe_balance": "剩余",
        "translation_auto_result_title": "TOAN AAS 译文",
        "translation_auto_result_source": "来源",
        "translation_auto_result_target": "目标",
        "translation_auto_result_disable_hint": "使用 <code>/translate_mode_off</code> 关闭。",
        "translation_auto_failed": "❌ 自动翻译暂时不可用或繁忙。TOAN AAS 未扣除 Xu，请稍后再试。",
        "translation_auto_no_chat_fallback": "为避免在错误的上下文中回答，消息没有转入 AI 聊天。",
        "translation_result_transcript_ready": "已转写",
        "translation_result_translation_ready": "已翻译",
        "translation_result_already_target": "内容已是目标语言",
    },
    "es": {
        "translation_command_missing_text": "⚠️ Falta el texto que deseas traducir. Ejemplo: <code>/translate en hola</code>",
        "translation_command_missing_target": "🌐 <b>Traducción de voz / audio</b>\n\nElige un idioma de destino, por ejemplo <code>/translate_voice en</code> o <code>/translate_voice vi</code>.\n\nUsa <code>/translate_tools</code> para ver los comandos de traducción.",
        "translation_tools_title": "🌐 HERRAMIENTAS DE TRADUCCIÓN TOAN AAS",
        "translation_tools_body": "Usa <code>/translate en texto</code> para texto, <code>/translate_file en</code> para un archivo y <code>/translate_voice en</code> para voz o audio. Usa <code>/translate_mode en</code> para activar la traducción automática o <code>/translate_mode_off</code> para desactivarla. Envía solo contenido que tengas derecho a usar.",
        "translation_auto_mode_enabled": "✅ La traducción automática a <b>{target}</b> está activada. Los mensajes de texto normales se traducirán en vez de ir al chat con IA. Desactívala con <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ La traducción automática está desactivada. Los mensajes de texto normales vuelven al chat con IA.",
        "translation_auto_mode_already_disabled": "ℹ️ La traducción automática ya estaba desactivada.",
        "translation_auto_mode_invalid_target": "⚠️ Este idioma no es compatible. Usa uno de estos códigos: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 ESTADO DE TRADUCCIÓN AUTOMÁTICA",
        "translation_auto_status_enabled": "activada",
        "translation_auto_status_disabled": "desactivada",
        "translation_auto_status_target": "Destino",
        "translation_auto_status_enable_hint": "Activar: <code>/translate_mode</code> o <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Desactivar: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "listo",
        "translation_transcribe_content": "Contenido",
        "translation_transcribe_balance": "Restante",
        "translation_auto_result_title": "TRADUCCIÓN TOAN AAS",
        "translation_auto_result_source": "Origen",
        "translation_auto_result_target": "Destino",
        "translation_auto_result_disable_hint": "Usa <code>/translate_mode_off</code> para desactivarla.",
        "translation_auto_failed": "❌ La traducción automática no está disponible temporalmente o está ocupada. TOAN AAS no ha cobrado Xu. Inténtalo de nuevo más tarde.",
        "translation_auto_no_chat_fallback": "El mensaje no se envió al chat con IA para evitar una respuesta fuera de contexto.",
        "translation_result_transcript_ready": "Transcripción lista",
        "translation_result_translation_ready": "Traducción lista",
        "translation_result_already_target": "El contenido ya está en el idioma de destino",
    },
    "pt": {
        "translation_command_missing_text": "⚠️ Falta o texto a traduzir. Exemplo: <code>/translate en olá</code>",
        "translation_command_missing_target": "🌐 <b>Tradução de voz / áudio</b>\n\nEscolha um idioma de destino, por exemplo <code>/translate_voice en</code> ou <code>/translate_voice vi</code>.\n\nUse <code>/translate_tools</code> para ver os comandos de tradução.",
        "translation_tools_title": "🌐 FERRAMENTAS DE TRADUÇÃO TOAN AAS",
        "translation_tools_body": "Use <code>/translate en texto</code> para texto, <code>/translate_file en</code> para um arquivo e <code>/translate_voice en</code> para voz ou áudio. Use <code>/translate_mode en</code> para ativar a tradução automática ou <code>/translate_mode_off</code> para desligá-la. Envie apenas conteúdo que você tenha o direito de usar.",
        "translation_auto_mode_enabled": "✅ A tradução automática para <b>{target}</b> foi ativada. Mensagens de texto normais serão traduzidas em vez de ir ao chat de IA. Desative com <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ A tradução automática foi desativada. Mensagens de texto normais voltam ao chat de IA.",
        "translation_auto_mode_already_disabled": "ℹ️ A tradução automática já estava desativada.",
        "translation_auto_mode_invalid_target": "⚠️ Este idioma não é compatível. Use um destes códigos: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 STATUS DA TRADUÇÃO AUTOMÁTICA",
        "translation_auto_status_enabled": "ativada",
        "translation_auto_status_disabled": "desativada",
        "translation_auto_status_target": "Destino",
        "translation_auto_status_enable_hint": "Ativar: <code>/translate_mode</code> ou <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Desativar: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "pronto",
        "translation_transcribe_content": "Conteúdo",
        "translation_transcribe_balance": "Restante",
        "translation_auto_result_title": "TRADUÇÃO TOAN AAS",
        "translation_auto_result_source": "Origem",
        "translation_auto_result_target": "Destino",
        "translation_auto_result_disable_hint": "Use <code>/translate_mode_off</code> para desativar.",
        "translation_auto_failed": "❌ A tradução automática está indisponível ou ocupada no momento. TOAN AAS não cobrou Xu. Tente novamente mais tarde.",
        "translation_auto_no_chat_fallback": "A mensagem não foi enviada ao chat de IA para evitar uma resposta fora de contexto.",
        "translation_result_transcript_ready": "Transcrição pronta",
        "translation_result_translation_ready": "Tradução pronta",
        "translation_result_already_target": "O conteúdo já está no idioma de destino",
    },
    "fr": {
        "translation_command_missing_text": "⚠️ Le texte à traduire est manquant. Exemple : <code>/translate en bonjour</code>",
        "translation_command_missing_target": "🌐 <b>Traduction vocale / audio</b>\n\nChoisissez une langue cible, par exemple <code>/translate_voice en</code> ou <code>/translate_voice vi</code>.\n\nUtilisez <code>/translate_tools</code> pour voir les commandes de traduction.",
        "translation_tools_title": "🌐 OUTILS DE TRADUCTION TOAN AAS",
        "translation_tools_body": "Utilisez <code>/translate en texte</code> pour du texte, <code>/translate_file en</code> pour un fichier et <code>/translate_voice en</code> pour la voix ou l’audio. Utilisez <code>/translate_mode en</code> pour activer la traduction automatique ou <code>/translate_mode_off</code> pour l’arrêter. N’envoyez que du contenu que vous êtes autorisé à utiliser.",
        "translation_auto_mode_enabled": "✅ La traduction automatique vers <b>{target}</b> est activée. Les messages texte normaux seront traduits au lieu d’aller au chat IA. Désactivez-la avec <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ La traduction automatique est désactivée. Les messages texte normaux reviennent au chat IA.",
        "translation_auto_mode_already_disabled": "ℹ️ La traduction automatique était déjà désactivée.",
        "translation_auto_mode_invalid_target": "⚠️ Cette langue n’est pas prise en charge. Utilisez l’un de ces codes : <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 ÉTAT DE LA TRADUCTION AUTOMATIQUE",
        "translation_auto_status_enabled": "activée",
        "translation_auto_status_disabled": "désactivée",
        "translation_auto_status_target": "Cible",
        "translation_auto_status_enable_hint": "Activer : <code>/translate_mode</code> ou <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Désactiver : <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "prête",
        "translation_transcribe_content": "Contenu",
        "translation_transcribe_balance": "Restant",
        "translation_auto_result_title": "TRADUCTION TOAN AAS",
        "translation_auto_result_source": "Source",
        "translation_auto_result_target": "Cible",
        "translation_auto_result_disable_hint": "Utilisez <code>/translate_mode_off</code> pour désactiver.",
        "translation_auto_failed": "❌ La traduction automatique est temporairement indisponible ou occupée. TOAN AAS n’a pas débité de Xu. Réessayez plus tard.",
        "translation_auto_no_chat_fallback": "Le message n’a pas été envoyé au chat IA afin d’éviter une réponse hors contexte.",
        "translation_result_transcript_ready": "Transcription prête",
        "translation_result_translation_ready": "Traduction prête",
        "translation_result_already_target": "Le contenu est déjà dans la langue cible",
    },
    "de": {
        "translation_command_missing_text": "⚠️ Der zu übersetzende Text fehlt. Beispiel: <code>/translate en hallo</code>",
        "translation_command_missing_target": "🌐 <b>Sprach- / Audioübersetzung</b>\n\nWähle eine Zielsprache, zum Beispiel <code>/translate_voice en</code> oder <code>/translate_voice vi</code>.\n\nMit <code>/translate_tools</code> siehst du die Übersetzungsbefehle.",
        "translation_tools_title": "🌐 TOAN AAS ÜBERSETZUNGSWERKZEUGE",
        "translation_tools_body": "Nutze <code>/translate en Text</code> für Text, <code>/translate_file en</code> für eine Datei und <code>/translate_voice en</code> für Sprache oder Audio. Mit <code>/translate_mode en</code> aktivierst du die automatische Übersetzung, mit <code>/translate_mode_off</code> schaltest du sie aus. Sende nur Inhalte, die du verwenden darfst.",
        "translation_auto_mode_enabled": "✅ Die automatische Übersetzung nach <b>{target}</b> ist aktiviert. Normale Textnachrichten werden übersetzt statt an den KI-Chat zu gehen. Mit <code>/translate_mode_off</code> deaktivierst du sie.",
        "translation_auto_mode_disabled": "✅ Die automatische Übersetzung ist deaktiviert. Normale Textnachrichten gehen wieder an den KI-Chat.",
        "translation_auto_mode_already_disabled": "ℹ️ Die automatische Übersetzung war bereits deaktiviert.",
        "translation_auto_mode_invalid_target": "⚠️ Diese Sprache wird nicht unterstützt. Nutze einen dieser Codes: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 STATUS DER AUTOMATISCHEN ÜBERSETZUNG",
        "translation_auto_status_enabled": "aktiviert",
        "translation_auto_status_disabled": "deaktiviert",
        "translation_auto_status_target": "Ziel",
        "translation_auto_status_enable_hint": "Aktivieren: <code>/translate_mode</code> oder <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Deaktivieren: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "bereit",
        "translation_transcribe_content": "Inhalt",
        "translation_transcribe_balance": "Verbleibend",
        "translation_auto_result_title": "TOAN AAS ÜBERSETZUNG",
        "translation_auto_result_source": "Quelle",
        "translation_auto_result_target": "Ziel",
        "translation_auto_result_disable_hint": "Mit <code>/translate_mode_off</code> deaktivieren.",
        "translation_auto_failed": "❌ Die automatische Übersetzung ist vorübergehend nicht verfügbar oder ausgelastet. TOAN AAS hat keine Xu berechnet. Bitte versuche es später erneut.",
        "translation_auto_no_chat_fallback": "Die Nachricht wurde nicht an den KI-Chat gesendet, um eine Antwort im falschen Kontext zu vermeiden.",
        "translation_result_transcript_ready": "Transkription bereit",
        "translation_result_translation_ready": "Übersetzung bereit",
        "translation_result_already_target": "Der Inhalt ist bereits in der Zielsprache",
    },
    "ja": {
        "translation_command_missing_text": "⚠️ 翻訳する内容がありません。例：<code>/translate en こんにちは</code>",
        "translation_command_missing_target": "🌐 <b>音声 / オーディオ翻訳</b>\n\n対象言語を選択してください。例：<code>/translate_voice en</code> または <code>/translate_voice vi</code>。\n\n<code>/translate_tools</code> で翻訳コマンドを確認できます。",
        "translation_tools_title": "🌐 TOAN AAS 翻訳ツール",
        "translation_tools_body": "テキストは <code>/translate en 内容</code>、ファイルは <code>/translate_file en</code>、音声は <code>/translate_voice en</code> を使います。<code>/translate_mode en</code> で自動翻訳を有効にし、<code>/translate_mode_off</code> で無効にします。利用する権利のある内容のみ送信してください。",
        "translation_auto_mode_enabled": "✅ <b>{target}</b> への自動翻訳を有効にしました。通常のテキストメッセージは AI チャットではなく翻訳されます。<code>/translate_mode_off</code> で無効にできます。",
        "translation_auto_mode_disabled": "✅ 自動翻訳を無効にしました。通常のテキストメッセージは AI チャットに戻ります。",
        "translation_auto_mode_already_disabled": "ℹ️ 自動翻訳はすでに無効です。",
        "translation_auto_mode_invalid_target": "⚠️ この言語はサポートされていません。次のコードを使用してください：<code>{supported}</code>。",
        "translation_auto_status_title": "🌐 自動翻訳の状態",
        "translation_auto_status_enabled": "有効",
        "translation_auto_status_disabled": "無効",
        "translation_auto_status_target": "対象",
        "translation_auto_status_enable_hint": "有効化：<code>/translate_mode</code> または <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "無効化：<code>/translate_mode_off</code>",
        "translation_transcribe_ready": "準備完了",
        "translation_transcribe_content": "内容",
        "translation_transcribe_balance": "残高",
        "translation_auto_result_title": "TOAN AAS 翻訳",
        "translation_auto_result_source": "原文",
        "translation_auto_result_target": "翻訳先",
        "translation_auto_result_disable_hint": "<code>/translate_mode_off</code> で無効にできます。",
        "translation_auto_failed": "❌ 自動翻訳は一時的に利用できないか、混み合っています。TOAN AAS は Xu を引き落としていません。後でもう一度お試しください。",
        "translation_auto_no_chat_fallback": "誤った文脈で回答しないよう、メッセージは AI チャットへ送られませんでした。",
        "translation_result_transcript_ready": "文字起こし完了",
        "translation_result_translation_ready": "翻訳完了",
        "translation_result_already_target": "内容はすでに対象言語です",
    },
    "ko": {
        "translation_command_missing_text": "⚠️ 번역할 내용이 없습니다. 예: <code>/translate en 안녕하세요</code>",
        "translation_command_missing_target": "🌐 <b>음성 / 오디오 번역</b>\n\n대상 언어를 선택하세요. 예: <code>/translate_voice en</code> 또는 <code>/translate_voice vi</code>\n\n<code>/translate_tools</code>에서 번역 명령을 확인할 수 있습니다.",
        "translation_tools_title": "🌐 TOAN AAS 번역 도구",
        "translation_tools_body": "텍스트에는 <code>/translate en 내용</code>, 파일에는 <code>/translate_file en</code>, 음성이나 오디오에는 <code>/translate_voice en</code>을 사용하세요. <code>/translate_mode en</code>으로 자동 번역을 켜고 <code>/translate_mode_off</code>로 끌 수 있습니다. 사용할 권한이 있는 내용만 보내세요.",
        "translation_auto_mode_enabled": "✅ <b>{target}</b> 자동 번역을 켰습니다. 일반 텍스트 메시지는 AI 채팅 대신 번역됩니다. <code>/translate_mode_off</code>로 끌 수 있습니다.",
        "translation_auto_mode_disabled": "✅ 자동 번역을 껐습니다. 일반 텍스트 메시지는 AI 채팅으로 돌아갑니다.",
        "translation_auto_mode_already_disabled": "ℹ️ 자동 번역은 이미 꺼져 있습니다.",
        "translation_auto_mode_invalid_target": "⚠️ 지원하지 않는 언어입니다. 다음 코드 중 하나를 사용하세요: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 자동 번역 상태",
        "translation_auto_status_enabled": "켜짐",
        "translation_auto_status_disabled": "꺼짐",
        "translation_auto_status_target": "대상",
        "translation_auto_status_enable_hint": "켜기: <code>/translate_mode</code> 또는 <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "끄기: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "준비됨",
        "translation_transcribe_content": "내용",
        "translation_transcribe_balance": "남은 잔액",
        "translation_auto_result_title": "TOAN AAS 번역",
        "translation_auto_result_source": "원문",
        "translation_auto_result_target": "대상",
        "translation_auto_result_disable_hint": "<code>/translate_mode_off</code>로 끌 수 있습니다.",
        "translation_auto_failed": "❌ 자동 번역을 일시적으로 사용할 수 없거나 혼잡합니다. TOAN AAS는 Xu를 차감하지 않았습니다. 나중에 다시 시도하세요.",
        "translation_auto_no_chat_fallback": "잘못된 문맥의 답변을 막기 위해 메시지는 AI 채팅으로 보내지지 않았습니다.",
        "translation_result_transcript_ready": "받아쓰기 완료",
        "translation_result_translation_ready": "번역 완료",
        "translation_result_already_target": "내용이 이미 대상 언어입니다",
    },
    "hi": {
        "translation_command_missing_text": "⚠️ अनुवाद करने के लिए सामग्री नहीं है। उदाहरण: <code>/translate en नमस्ते</code>",
        "translation_command_missing_target": "🌐 <b>वॉइस / ऑडियो अनुवाद</b>\n\nलक्ष्य भाषा चुनें, जैसे <code>/translate_voice en</code> या <code>/translate_voice vi</code>।\n\nअनुवाद कमांड देखने के लिए <code>/translate_tools</code> उपयोग करें।",
        "translation_tools_title": "🌐 TOAN AAS अनुवाद उपकरण",
        "translation_tools_body": "टेक्स्ट के लिए <code>/translate en सामग्री</code>, फ़ाइल के लिए <code>/translate_file en</code> और वॉइस या ऑडियो के लिए <code>/translate_voice en</code> उपयोग करें। स्वचालित अनुवाद के लिए <code>/translate_mode en</code> और बंद करने के लिए <code>/translate_mode_off</code> उपयोग करें। केवल वही सामग्री भेजें जिसका उपयोग करने का अधिकार आपके पास है।",
        "translation_auto_mode_enabled": "✅ <b>{target}</b> के लिए स्वचालित अनुवाद चालू है। सामान्य टेक्स्ट संदेश AI चैट में जाने के बजाय अनुवादित होंगे। <code>/translate_mode_off</code> से बंद करें।",
        "translation_auto_mode_disabled": "✅ स्वचालित अनुवाद बंद है। सामान्य टेक्स्ट संदेश फिर AI चैट में जाएंगे।",
        "translation_auto_mode_already_disabled": "ℹ️ स्वचालित अनुवाद पहले से बंद है।",
        "translation_auto_mode_invalid_target": "⚠️ यह भाषा समर्थित नहीं है। इनमें से एक कोड उपयोग करें: <code>{supported}</code>।",
        "translation_auto_status_title": "🌐 स्वचालित अनुवाद स्थिति",
        "translation_auto_status_enabled": "चालू",
        "translation_auto_status_disabled": "बंद",
        "translation_auto_status_target": "लक्ष्य",
        "translation_auto_status_enable_hint": "चालू करें: <code>/translate_mode</code> या <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "बंद करें: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "तैयार",
        "translation_transcribe_content": "सामग्री",
        "translation_transcribe_balance": "शेष",
        "translation_auto_result_title": "TOAN AAS अनुवाद",
        "translation_auto_result_source": "स्रोत",
        "translation_auto_result_target": "लक्ष्य",
        "translation_auto_result_disable_hint": "बंद करने के लिए <code>/translate_mode_off</code> उपयोग करें।",
        "translation_auto_failed": "❌ स्वचालित अनुवाद अस्थायी रूप से उपलब्ध नहीं है या व्यस्त है। TOAN AAS ने Xu नहीं काटा। बाद में फिर प्रयास करें।",
        "translation_auto_no_chat_fallback": "गलत संदर्भ में उत्तर से बचने के लिए संदेश AI चैट को नहीं भेजा गया।",
        "translation_result_transcript_ready": "प्रतिलेखन तैयार",
        "translation_result_translation_ready": "अनुवाद तैयार",
        "translation_result_already_target": "सामग्री पहले से लक्ष्य भाषा में है",
    },
    "ar": {
        "translation_command_missing_text": "⚠️ لا يوجد محتوى للترجمة. مثال: <code>/translate en مرحباً</code>",
        "translation_command_missing_target": "🌐 <b>ترجمة الصوت / الملف الصوتي</b>\n\nاختر لغة الهدف، مثل <code>/translate_voice en</code> أو <code>/translate_voice vi</code>.\n\nاستخدم <code>/translate_tools</code> لعرض أوامر الترجمة.",
        "translation_tools_title": "🌐 أدوات الترجمة TOAN AAS",
        "translation_tools_body": "استخدم <code>/translate en المحتوى</code> للنص، و<code>/translate_file en</code> للملف، و<code>/translate_voice en</code> للصوت. استخدم <code>/translate_mode en</code> لتفعيل الترجمة التلقائية أو <code>/translate_mode_off</code> لإيقافها. أرسل فقط المحتوى الذي تملك حق استخدامه.",
        "translation_auto_mode_enabled": "✅ تم تفعيل الترجمة التلقائية إلى <b>{target}</b>. ستتم ترجمة الرسائل النصية العادية بدلاً من إرسالها إلى دردشة الذكاء الاصطناعي. أوقفها عبر <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ تم إيقاف الترجمة التلقائية. ستعود الرسائل النصية العادية إلى دردشة الذكاء الاصطناعي.",
        "translation_auto_mode_already_disabled": "ℹ️ الترجمة التلقائية متوقفة بالفعل.",
        "translation_auto_mode_invalid_target": "⚠️ هذه اللغة غير مدعومة. استخدم أحد الرموز التالية: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 حالة الترجمة التلقائية",
        "translation_auto_status_enabled": "مفعلة",
        "translation_auto_status_disabled": "متوقفة",
        "translation_auto_status_target": "الهدف",
        "translation_auto_status_enable_hint": "تفعيل: <code>/translate_mode</code> أو <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "إيقاف: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "جاهز",
        "translation_transcribe_content": "المحتوى",
        "translation_transcribe_balance": "المتبقي",
        "translation_auto_result_title": "ترجمة TOAN AAS",
        "translation_auto_result_source": "المصدر",
        "translation_auto_result_target": "الهدف",
        "translation_auto_result_disable_hint": "استخدم <code>/translate_mode_off</code> لإيقافها.",
        "translation_auto_failed": "❌ الترجمة التلقائية غير متاحة مؤقتاً أو مشغولة. لم يخصم TOAN AAS أي Xu. حاول لاحقاً.",
        "translation_auto_no_chat_fallback": "لم يتم إرسال الرسالة إلى دردشة الذكاء الاصطناعي لتجنب إجابة خارج السياق.",
        "translation_result_transcript_ready": "تم التفريغ",
        "translation_result_translation_ready": "تمت الترجمة",
        "translation_result_already_target": "المحتوى موجود بالفعل بلغة الهدف",
    },
    "ru": {
        "translation_command_missing_text": "⚠️ Нет текста для перевода. Пример: <code>/translate en привет</code>",
        "translation_command_missing_target": "🌐 <b>Перевод голоса / аудио</b>\n\nВыберите целевой язык, например <code>/translate_voice en</code> или <code>/translate_voice vi</code>.\n\nИспользуйте <code>/translate_tools</code>, чтобы увидеть команды перевода.",
        "translation_tools_title": "🌐 ИНСТРУМЕНТЫ ПЕРЕВОДА TOAN AAS",
        "translation_tools_body": "Для текста используйте <code>/translate en текст</code>, для файла — <code>/translate_file en</code>, для голоса или аудио — <code>/translate_voice en</code>. Включите автоперевод через <code>/translate_mode en</code> или выключите через <code>/translate_mode_off</code>. Отправляйте только контент, на использование которого у вас есть права.",
        "translation_auto_mode_enabled": "✅ Автоперевод на <b>{target}</b> включён. Обычные текстовые сообщения будут переводиться, а не отправляться в ИИ-чат. Выключите через <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ Автоперевод выключен. Обычные текстовые сообщения снова отправляются в ИИ-чат.",
        "translation_auto_mode_already_disabled": "ℹ️ Автоперевод уже выключен.",
        "translation_auto_mode_invalid_target": "⚠️ Этот язык не поддерживается. Используйте один из кодов: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 СОСТОЯНИЕ АВТОПЕРЕВОДА",
        "translation_auto_status_enabled": "включён",
        "translation_auto_status_disabled": "выключен",
        "translation_auto_status_target": "Цель",
        "translation_auto_status_enable_hint": "Включить: <code>/translate_mode</code> или <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Выключить: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "готово",
        "translation_transcribe_content": "Содержание",
        "translation_transcribe_balance": "Осталось",
        "translation_auto_result_title": "ПЕРЕВОД TOAN AAS",
        "translation_auto_result_source": "Источник",
        "translation_auto_result_target": "Цель",
        "translation_auto_result_disable_hint": "Выключить через <code>/translate_mode_off</code>.",
        "translation_auto_failed": "❌ Автоперевод временно недоступен или перегружен. TOAN AAS не списал Xu. Попробуйте позже.",
        "translation_auto_no_chat_fallback": "Сообщение не отправлено в ИИ-чат, чтобы избежать ответа вне контекста.",
        "translation_result_transcript_ready": "Расшифровка готова",
        "translation_result_translation_ready": "Перевод готов",
        "translation_result_already_target": "Содержимое уже на целевом языке",
    },
    "tr": {
        "translation_command_missing_text": "⚠️ Çevrilecek metin eksik. Örnek: <code>/translate en merhaba</code>",
        "translation_command_missing_target": "🌐 <b>Ses / ses dosyası çevirisi</b>\n\nHedef dili seçin; örneğin <code>/translate_voice en</code> veya <code>/translate_voice vi</code>.\n\nÇeviri komutlarını görmek için <code>/translate_tools</code> kullanın.",
        "translation_tools_title": "🌐 TOAN AAS ÇEVİRİ ARAÇLARI",
        "translation_tools_body": "Metin için <code>/translate en metin</code>, dosya için <code>/translate_file en</code>, ses için <code>/translate_voice en</code> kullanın. Otomatik çeviriyi <code>/translate_mode en</code> ile açın veya <code>/translate_mode_off</code> ile kapatın. Yalnızca kullanma hakkınız olan içeriği gönderin.",
        "translation_auto_mode_enabled": "✅ <b>{target}</b> için otomatik çeviri açıldı. Normal metin mesajları AI sohbetine gitmek yerine çevrilecek. <code>/translate_mode_off</code> ile kapatın.",
        "translation_auto_mode_disabled": "✅ Otomatik çeviri kapatıldı. Normal metin mesajları tekrar AI sohbetine gider.",
        "translation_auto_mode_already_disabled": "ℹ️ Otomatik çeviri zaten kapalı.",
        "translation_auto_mode_invalid_target": "⚠️ Bu dil desteklenmiyor. Şu kodlardan birini kullanın: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 OTOMATİK ÇEVİRİ DURUMU",
        "translation_auto_status_enabled": "açık",
        "translation_auto_status_disabled": "kapalı",
        "translation_auto_status_target": "Hedef",
        "translation_auto_status_enable_hint": "Aç: <code>/translate_mode</code> veya <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Kapat: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "hazır",
        "translation_transcribe_content": "İçerik",
        "translation_transcribe_balance": "Kalan",
        "translation_auto_result_title": "TOAN AAS ÇEVİRİSİ",
        "translation_auto_result_source": "Kaynak",
        "translation_auto_result_target": "Hedef",
        "translation_auto_result_disable_hint": "Kapatmak için <code>/translate_mode_off</code> kullanın.",
        "translation_auto_failed": "❌ Otomatik çeviri geçici olarak kullanılamıyor veya meşgul. TOAN AAS Xu kesmedi. Lütfen daha sonra tekrar deneyin.",
        "translation_auto_no_chat_fallback": "Yanlış bağlamda yanıtı önlemek için mesaj AI sohbetine gönderilmedi.",
        "translation_result_transcript_ready": "Döküm hazır",
        "translation_result_translation_ready": "Çeviri hazır",
        "translation_result_already_target": "İçerik zaten hedef dilde",
    },
    "th": {
        "translation_command_missing_text": "⚠️ ไม่มีข้อความสำหรับแปล ตัวอย่าง: <code>/translate en สวัสดี</code>",
        "translation_command_missing_target": "🌐 <b>แปลเสียง / ไฟล์เสียง</b>\n\nเลือกภาษาปลายทาง เช่น <code>/translate_voice en</code> หรือ <code>/translate_voice vi</code>\n\nใช้ <code>/translate_tools</code> เพื่อดูคำสั่งแปลภาษา",
        "translation_tools_title": "🌐 เครื่องมือแปลภาษา TOAN AAS",
        "translation_tools_body": "ใช้ <code>/translate en ข้อความ</code> สำหรับข้อความ, <code>/translate_file en</code> สำหรับไฟล์ และ <code>/translate_voice en</code> สำหรับเสียง ใช้ <code>/translate_mode en</code> เพื่อเปิดแปลอัตโนมัติ หรือ <code>/translate_mode_off</code> เพื่อปิด ส่งเฉพาะเนื้อหาที่คุณมีสิทธิ์ใช้เท่านั้น",
        "translation_auto_mode_enabled": "✅ เปิดแปลอัตโนมัติเป็น <b>{target}</b> แล้ว ข้อความปกติจะถูกแปลแทนที่จะส่งไปยังแชต AI ปิดได้ด้วย <code>/translate_mode_off</code>",
        "translation_auto_mode_disabled": "✅ ปิดแปลอัตโนมัติแล้ว ข้อความปกติจะกลับไปยังแชต AI",
        "translation_auto_mode_already_disabled": "ℹ️ แปลอัตโนมัติปิดอยู่แล้ว",
        "translation_auto_mode_invalid_target": "⚠️ ไม่รองรับภาษานี้ ใช้รหัสใดรหัสหนึ่ง: <code>{supported}</code>",
        "translation_auto_status_title": "🌐 สถานะการแปลอัตโนมัติ",
        "translation_auto_status_enabled": "เปิด",
        "translation_auto_status_disabled": "ปิด",
        "translation_auto_status_target": "เป้าหมาย",
        "translation_auto_status_enable_hint": "เปิด: <code>/translate_mode</code> หรือ <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "ปิด: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "พร้อม",
        "translation_transcribe_content": "เนื้อหา",
        "translation_transcribe_balance": "คงเหลือ",
        "translation_auto_result_title": "คำแปล TOAN AAS",
        "translation_auto_result_source": "ต้นทาง",
        "translation_auto_result_target": "ปลายทาง",
        "translation_auto_result_disable_hint": "ใช้ <code>/translate_mode_off</code> เพื่อปิด",
        "translation_auto_failed": "❌ ระบบแปลอัตโนมัติไม่พร้อมใช้งานชั่วคราวหรือกำลังใช้งานมาก TOAN AAS ยังไม่ได้หัก Xu โปรดลองใหม่ภายหลัง",
        "translation_auto_no_chat_fallback": "ข้อความไม่ได้ถูกส่งไปยังแชต AI เพื่อหลีกเลี่ยงคำตอบผิดบริบท",
        "translation_result_transcript_ready": "ถอดเสียงแล้ว",
        "translation_result_translation_ready": "แปลแล้ว",
        "translation_result_already_target": "เนื้อหาเป็นภาษาปลายทางอยู่แล้ว",
    },
    "fil": {
        "translation_command_missing_text": "⚠️ Walang tekstong isasalin. Halimbawa: <code>/translate en kumusta</code>",
        "translation_command_missing_target": "🌐 <b>Pagsasalin ng voice / audio</b>\n\nPumili ng target na wika, halimbawa <code>/translate_voice en</code> o <code>/translate_voice vi</code>.\n\nGamitin ang <code>/translate_tools</code> upang makita ang mga command sa pagsasalin.",
        "translation_tools_title": "🌐 MGA TOOL SA PAGSASALIN NG TOAN AAS",
        "translation_tools_body": "Gamitin ang <code>/translate en teksto</code> para sa text, <code>/translate_file en</code> para sa file at <code>/translate_voice en</code> para sa voice o audio. Gamitin ang <code>/translate_mode en</code> upang i-on ang awtomatikong pagsasalin, o <code>/translate_mode_off</code> upang i-off ito. Magpadala lamang ng content na may karapatan kang gamitin.",
        "translation_auto_mode_enabled": "✅ Naka-on ang awtomatikong pagsasalin sa <b>{target}</b>. Isasalin ang normal na text message sa halip na ipadala sa AI chat. I-off gamit ang <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ Naka-off ang awtomatikong pagsasalin. Babalik sa AI chat ang normal na text message.",
        "translation_auto_mode_already_disabled": "ℹ️ Naka-off na ang awtomatikong pagsasalin.",
        "translation_auto_mode_invalid_target": "⚠️ Hindi suportado ang wikang ito. Gumamit ng isa sa mga code: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 KATAYUAN NG AWTOMATIKONG PAGSASALIN",
        "translation_auto_status_enabled": "naka-on",
        "translation_auto_status_disabled": "naka-off",
        "translation_auto_status_target": "Target",
        "translation_auto_status_enable_hint": "I-on: <code>/translate_mode</code> o <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "I-off: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "handa",
        "translation_transcribe_content": "Nilalaman",
        "translation_transcribe_balance": "Natitira",
        "translation_auto_result_title": "PAGSASALIN NG TOAN AAS",
        "translation_auto_result_source": "Pinagmulan",
        "translation_auto_result_target": "Target",
        "translation_auto_result_disable_hint": "Gamitin ang <code>/translate_mode_off</code> upang i-off.",
        "translation_auto_failed": "❌ Pansamantalang hindi available o abala ang awtomatikong pagsasalin. Walang nabawas na Xu ang TOAN AAS. Subukan muli mamaya.",
        "translation_auto_no_chat_fallback": "Hindi ipinadala ang mensahe sa AI chat upang maiwasan ang sagot na wala sa tamang konteksto.",
        "translation_result_transcript_ready": "Handa ang transcript",
        "translation_result_translation_ready": "Handa ang salin",
        "translation_result_already_target": "Nasa target na wika na ang content",
    },
    "it": {
        "translation_command_missing_text": "⚠️ Manca il testo da tradurre. Esempio: <code>/translate en ciao</code>",
        "translation_command_missing_target": "🌐 <b>Traduzione voce / audio</b>\n\nScegli una lingua di destinazione, ad esempio <code>/translate_voice en</code> o <code>/translate_voice vi</code>.\n\nUsa <code>/translate_tools</code> per vedere i comandi di traduzione.",
        "translation_tools_title": "🌐 STRUMENTI DI TRADUZIONE TOAN AAS",
        "translation_tools_body": "Usa <code>/translate en testo</code> per il testo, <code>/translate_file en</code> per un file e <code>/translate_voice en</code> per voce o audio. Usa <code>/translate_mode en</code> per attivare la traduzione automatica o <code>/translate_mode_off</code> per disattivarla. Invia solo contenuti che hai il diritto di usare.",
        "translation_auto_mode_enabled": "✅ La traduzione automatica in <b>{target}</b> è attiva. I normali messaggi di testo verranno tradotti invece di andare alla chat AI. Disattivala con <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ La traduzione automatica è disattivata. I normali messaggi di testo tornano alla chat AI.",
        "translation_auto_mode_already_disabled": "ℹ️ La traduzione automatica era già disattivata.",
        "translation_auto_mode_invalid_target": "⚠️ Questa lingua non è supportata. Usa uno di questi codici: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 STATO DELLA TRADUZIONE AUTOMATICA",
        "translation_auto_status_enabled": "attiva",
        "translation_auto_status_disabled": "disattivata",
        "translation_auto_status_target": "Destinazione",
        "translation_auto_status_enable_hint": "Attiva: <code>/translate_mode</code> o <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Disattiva: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "pronta",
        "translation_transcribe_content": "Contenuto",
        "translation_transcribe_balance": "Rimanente",
        "translation_auto_result_title": "TRADUZIONE TOAN AAS",
        "translation_auto_result_source": "Origine",
        "translation_auto_result_target": "Destinazione",
        "translation_auto_result_disable_hint": "Usa <code>/translate_mode_off</code> per disattivarla.",
        "translation_auto_failed": "❌ La traduzione automatica non è temporaneamente disponibile o è occupata. TOAN AAS non ha addebitato Xu. Riprova più tardi.",
        "translation_auto_no_chat_fallback": "Il messaggio non è stato inviato alla chat AI per evitare una risposta fuori contesto.",
        "translation_result_transcript_ready": "Trascrizione pronta",
        "translation_result_translation_ready": "Traduzione pronta",
        "translation_result_already_target": "Il contenuto è già nella lingua di destinazione",
    },
    "id": {
        "translation_command_missing_text": "⚠️ Tidak ada teks untuk diterjemahkan. Contoh: <code>/translate en halo</code>",
        "translation_command_missing_target": "🌐 <b>Terjemahan suara / audio</b>\n\nPilih bahasa target, misalnya <code>/translate_voice en</code> atau <code>/translate_voice vi</code>.\n\nGunakan <code>/translate_tools</code> untuk melihat perintah terjemahan.",
        "translation_tools_title": "🌐 ALAT TERJEMAHAN TOAN AAS",
        "translation_tools_body": "Gunakan <code>/translate en teks</code> untuk teks, <code>/translate_file en</code> untuk file dan <code>/translate_voice en</code> untuk suara atau audio. Gunakan <code>/translate_mode en</code> untuk mengaktifkan terjemahan otomatis atau <code>/translate_mode_off</code> untuk mematikannya. Kirim hanya konten yang berhak Anda gunakan.",
        "translation_auto_mode_enabled": "✅ Terjemahan otomatis ke <b>{target}</b> aktif. Pesan teks biasa akan diterjemahkan, bukan dikirim ke chat AI. Matikan dengan <code>/translate_mode_off</code>.",
        "translation_auto_mode_disabled": "✅ Terjemahan otomatis dinonaktifkan. Pesan teks biasa kembali ke chat AI.",
        "translation_auto_mode_already_disabled": "ℹ️ Terjemahan otomatis sudah dinonaktifkan.",
        "translation_auto_mode_invalid_target": "⚠️ Bahasa ini tidak didukung. Gunakan salah satu kode: <code>{supported}</code>.",
        "translation_auto_status_title": "🌐 STATUS TERJEMAHAN OTOMATIS",
        "translation_auto_status_enabled": "aktif",
        "translation_auto_status_disabled": "nonaktif",
        "translation_auto_status_target": "Target",
        "translation_auto_status_enable_hint": "Aktifkan: <code>/translate_mode</code> atau <code>/translate_mode en</code>",
        "translation_auto_status_disable_hint": "Nonaktifkan: <code>/translate_mode_off</code>",
        "translation_transcribe_ready": "siap",
        "translation_transcribe_content": "Konten",
        "translation_transcribe_balance": "Sisa",
        "translation_auto_result_title": "TERJEMAHAN TOAN AAS",
        "translation_auto_result_source": "Sumber",
        "translation_auto_result_target": "Target",
        "translation_auto_result_disable_hint": "Gunakan <code>/translate_mode_off</code> untuk mematikannya.",
        "translation_auto_failed": "❌ Terjemahan otomatis sementara tidak tersedia atau sedang sibuk. TOAN AAS tidak memotong Xu. Silakan coba lagi nanti.",
        "translation_auto_no_chat_fallback": "Pesan tidak dikirim ke chat AI agar tidak mendapat jawaban di luar konteks.",
        "translation_result_transcript_ready": "Transkripsi siap",
        "translation_result_translation_ready": "Terjemahan siap",
        "translation_result_already_target": "Konten sudah dalam bahasa target",
    },
}

for _locale, _copy in _PUBLIC_TRANSLATION_COMMAND_COPY.items():
    _media = _PUBLIC_TRANSLATION_MEDIA_COPY[_locale]
    _copy.setdefault("translation_transcribe_title", f"🎙 {_media['translation_transcribe']}")


_PUBLIC_PACKAGE_NAVIGATION_COPY = {
    "es": {"monthly_plans": "Planes mensuales", "finished_combos": "Combos completos", "my_packages": "Mis paquetes", "large_order": "Pedido grande", "notes": "Notas", "refresh": "Actualizar", "confirm_purchase": "Confirmar compra"},
    "pt": {"monthly_plans": "Planos mensais", "finished_combos": "Combos completos", "my_packages": "Meus pacotes", "large_order": "Pedido maior", "notes": "Notas", "refresh": "Atualizar", "confirm_purchase": "Confirmar compra"},
    "fr": {"monthly_plans": "Forfaits mensuels", "finished_combos": "Combos complets", "my_packages": "Mes forfaits", "large_order": "Demande importante", "notes": "Notes", "refresh": "Actualiser", "confirm_purchase": "Confirmer l’achat"},
    "de": {"monthly_plans": "Monatspakete", "finished_combos": "Fertige Kombis", "my_packages": "Meine Pakete", "large_order": "Größere Anfrage", "notes": "Hinweise", "refresh": "Aktualisieren", "confirm_purchase": "Kauf bestätigen"},
    "ja": {"monthly_plans": "月額プラン", "finished_combos": "完成コンボ", "my_packages": "マイパッケージ", "large_order": "大口のご相談", "notes": "注意事項", "refresh": "更新", "confirm_purchase": "購入を確認"},
    "ko": {"monthly_plans": "월간 플랜", "finished_combos": "완성 콤보", "my_packages": "내 패키지", "large_order": "대량 문의", "notes": "안내", "refresh": "새로고침", "confirm_purchase": "구매 확인"},
    "hi": {"monthly_plans": "मासिक प्लान", "finished_combos": "पूर्ण कॉम्बो", "my_packages": "मेरे पैकेज", "large_order": "बड़ी मात्रा का अनुरोध", "notes": "नोट्स", "refresh": "रीफ़्रेश", "confirm_purchase": "खरीद की पुष्टि"},
    "ar": {"monthly_plans": "خطط شهرية", "finished_combos": "باقات مكتملة", "my_packages": "باقاتي", "large_order": "طلب كبير", "notes": "ملاحظات", "refresh": "تحديث", "confirm_purchase": "تأكيد الشراء"},
    "ru": {"monthly_plans": "Ежемесячные планы", "finished_combos": "Готовые комплекты", "my_packages": "Мои пакеты", "large_order": "Крупный заказ", "notes": "Примечания", "refresh": "Обновить", "confirm_purchase": "Подтвердить покупку"},
    "tr": {"monthly_plans": "Aylık planlar", "finished_combos": "Hazır paketler", "my_packages": "Paketlerim", "large_order": "Büyük sipariş", "notes": "Notlar", "refresh": "Yenile", "confirm_purchase": "Satın almayı onayla"},
    "th": {"monthly_plans": "แผนรายเดือน", "finished_combos": "คอมโบสำเร็จรูป", "my_packages": "แพ็กเกจของฉัน", "large_order": "คำขอจำนวนมาก", "notes": "หมายเหตุ", "refresh": "รีเฟรช", "confirm_purchase": "ยืนยันการซื้อ"},
    "fil": {"monthly_plans": "Mga buwanang plano", "finished_combos": "Mga kumpletong combo", "my_packages": "Mga package ko", "large_order": "Malaking order", "notes": "Mga tala", "refresh": "I-refresh", "confirm_purchase": "Kumpirmahin ang pagbili"},
    "it": {"monthly_plans": "Piani mensili", "finished_combos": "Combo completi", "my_packages": "I miei pacchetti", "large_order": "Ordine grande", "notes": "Note", "refresh": "Aggiorna", "confirm_purchase": "Conferma acquisto"},
    "id": {"monthly_plans": "Paket bulanan", "finished_combos": "Kombinasi lengkap", "my_packages": "Paket saya", "large_order": "Pesanan besar", "notes": "Catatan", "refresh": "Segarkan", "confirm_purchase": "Konfirmasi pembelian"},
}


_PUBLIC_PACKAGE_GUIDE_COPY = {
    "vi": "Gói tháng và combo dùng theo quyền lợi hiển thị; không quy đổi thành Xu linh hoạt và không kích hoạt khuyến mãi nạp tiền.",
    "en": "Plans and combos are used according to the benefits shown; they are not converted to flexible Xu and do not trigger top-up bonuses.",
    "zh": "月度套餐和组合按页面列明的权益使用；不能兑换为灵活 Xu，也不会触发充值赠送。",
    "es": "Los planes y combos se usan conforme a los beneficios mostrados; no se convierten en Xu flexible ni activan bonificaciones de recarga.",
    "pt": "Os planos e combos são usados conforme os benefícios exibidos; não se convertem em Xu flexível nem ativam bônus de recarga.",
    "fr": "Les forfaits et combos s'utilisent selon les avantages affichés ; ils ne sont pas convertibles en Xu flexible et ne déclenchent pas de bonus de recharge.",
    "de": "Pakete und Kombis werden gemäß den angezeigten Leistungen genutzt; sie werden nicht in flexibles Xu umgewandelt und lösen keine Aufladeboni aus.",
    "ja": "プランとコンボは表示された特典に従って利用します。柔軟に使える Xu への換算やチャージボーナスの対象にはなりません。",
    "ko": "플랜과 콤보는 표시된 혜택에 따라 사용됩니다. 유연하게 사용할 수 있는 Xu로 전환되지 않으며 충전 보너스도 발생하지 않습니다.",
    "hi": "प्लान और कॉम्बो दिखाए गए लाभों के अनुसार उपयोग होते हैं; इन्हें लचीले Xu में नहीं बदला जाता और ये टॉप-अप बोनस सक्रिय नहीं करते।",
    "ar": "تُستخدم الخطط والباقات وفق المزايا المعروضة؛ ولا تتحول إلى Xu مرن ولا تُفعّل مكافآت الشحن.",
    "ru": "Планы и комплекты используются согласно указанным преимуществам; они не преобразуются в гибкие Xu и не дают бонусов за пополнение.",
    "tr": "Planlar ve paketler gösterilen avantajlara göre kullanılır; esnek Xu'ya dönüştürülmez ve yükleme bonusu sağlamaz.",
    "th": "แพ็กเกจและคอมโบใช้ตามสิทธิประโยชน์ที่แสดงไว้ ไม่สามารถแปลงเป็น Xu แบบยืดหยุ่นและไม่ทำให้ได้รับโบนัสเติมเงิน",
    "fil": "Ginagamit ang mga plano at combo ayon sa ipinakitang benepisyo; hindi sila naisasalin sa flexible Xu at hindi nagpapagana ng bonus sa top-up.",
    "it": "I piani e i combo si usano secondo i vantaggi mostrati; non si convertono in Xu flessibili e non attivano bonus di ricarica.",
    "id": "Paket dan kombo digunakan sesuai manfaat yang ditampilkan; tidak dapat diubah menjadi Xu fleksibel dan tidak memicu bonus isi ulang.",
}


_PUBLIC_SUPPORT_PROFILE_COPY = {
    "vi": {
        "support_premium": "Đăng ký Premium", "support_custom_bot": "Kết nối bot riêng", "support_consult": "Tư vấn gói dịch vụ",
        "profile_topup": "Nạp Xu", "profile_pricing": "Bảng giá", "profile_packages": "Combo của tôi", "profile_membership": "Thành viên",
        "profile_xu_guide": "Hướng dẫn Xu", "profile_referral_link": "Link giới thiệu", "profile_referral_stats": "Người đã giới thiệu",
        "profile_referral_policy": "Cách nhận thưởng", "profile_change_language": "Đổi ngôn ngữ", "profile_back_account": "Quay lại Tài khoản",
        "profile_id": "ID", "profile_tier": "Hạng", "profile_balance": "Số dư", "profile_detail_hint": "Dùng /profile để xem giới thiệu, quà sinh nhật và chi tiết thành viên.",
        "profile_unlimited": "Không giới hạn", "profile_remaining_uses": "lượt dịch vụ còn lại",
    },
    "en": {
        "support_premium": "Premium sign-up", "support_custom_bot": "Connect a custom bot", "support_consult": "Service consultation",
        "profile_topup": "Top up Xu", "profile_pricing": "Pricing", "profile_packages": "My packages", "profile_membership": "Membership",
        "profile_xu_guide": "Xu guide", "profile_referral_link": "Referral link", "profile_referral_stats": "Referral activity",
        "profile_referral_policy": "Reward policy", "profile_change_language": "Change language", "profile_back_account": "Back to account",
        "profile_id": "ID", "profile_tier": "Tier", "profile_balance": "Balance", "profile_detail_hint": "Use /profile to view referrals, birthday gifts and membership details.",
        "profile_unlimited": "Unlimited", "profile_remaining_uses": "service uses remaining",
    },
    "zh": {
        "support_premium": "注册高级会员", "support_custom_bot": "连接专属机器人", "support_consult": "服务咨询",
        "profile_topup": "充值 Xu", "profile_pricing": "价格", "profile_packages": "我的套餐", "profile_membership": "会员等级",
        "profile_xu_guide": "Xu 指南", "profile_referral_link": "邀请链接", "profile_referral_stats": "邀请记录",
        "profile_referral_policy": "奖励规则", "profile_change_language": "更改语言", "profile_back_account": "返回账户",
        "profile_id": "ID", "profile_tier": "等级", "profile_balance": "余额", "profile_detail_hint": "使用 /profile 查看邀请、生日礼物和会员详情。",
        "profile_unlimited": "无限", "profile_remaining_uses": "次服务剩余",
    },
    "es": {
        "support_premium": "Suscribirse a Premium", "support_custom_bot": "Conectar un bot personalizado", "support_consult": "Asesoría de servicios",
        "profile_topup": "Recargar Xu", "profile_pricing": "Precios", "profile_packages": "Mis paquetes", "profile_membership": "Membresía",
        "profile_xu_guide": "Guía de Xu", "profile_referral_link": "Enlace de invitación", "profile_referral_stats": "Actividad de invitaciones",
        "profile_referral_policy": "Reglas de recompensa", "profile_change_language": "Cambiar idioma", "profile_back_account": "Volver a la cuenta",
        "profile_id": "ID", "profile_tier": "Nivel", "profile_balance": "Saldo", "profile_detail_hint": "Usa /profile para ver invitaciones, regalos de cumpleaños y detalles de membresía.",
        "profile_unlimited": "Ilimitado", "profile_remaining_uses": "usos de servicio restantes",
    },
    "pt": {
        "support_premium": "Assinar Premium", "support_custom_bot": "Conectar bot personalizado", "support_consult": "Consultoria de serviços",
        "profile_topup": "Recarregar Xu", "profile_pricing": "Preços", "profile_packages": "Meus pacotes", "profile_membership": "Assinatura",
        "profile_xu_guide": "Guia de Xu", "profile_referral_link": "Link de indicação", "profile_referral_stats": "Atividade de indicações",
        "profile_referral_policy": "Política de recompensa", "profile_change_language": "Mudar idioma", "profile_back_account": "Voltar à conta",
        "profile_id": "ID", "profile_tier": "Nível", "profile_balance": "Saldo", "profile_detail_hint": "Use /profile para ver indicações, presentes de aniversário e detalhes da assinatura.",
        "profile_unlimited": "Ilimitado", "profile_remaining_uses": "usos de serviço restantes",
    },
    "fr": {
        "support_premium": "S’inscrire à Premium", "support_custom_bot": "Connecter un bot personnalisé", "support_consult": "Conseil en services",
        "profile_topup": "Recharger des Xu", "profile_pricing": "Tarifs", "profile_packages": "Mes forfaits", "profile_membership": "Abonnement",
        "profile_xu_guide": "Guide Xu", "profile_referral_link": "Lien de parrainage", "profile_referral_stats": "Activité de parrainage",
        "profile_referral_policy": "Règles de récompense", "profile_change_language": "Changer de langue", "profile_back_account": "Retour au compte",
        "profile_id": "ID", "profile_tier": "Niveau", "profile_balance": "Solde", "profile_detail_hint": "Utilisez /profile pour voir les parrainages, cadeaux d’anniversaire et détails d’abonnement.",
        "profile_unlimited": "Illimité", "profile_remaining_uses": "utilisations de service restantes",
    },
    "de": {
        "support_premium": "Premium anmelden", "support_custom_bot": "Eigenen Bot verbinden", "support_consult": "Serviceberatung",
        "profile_topup": "Xu aufladen", "profile_pricing": "Preise", "profile_packages": "Meine Pakete", "profile_membership": "Mitgliedschaft",
        "profile_xu_guide": "Xu-Anleitung", "profile_referral_link": "Empfehlungslink", "profile_referral_stats": "Empfehlungsaktivität",
        "profile_referral_policy": "Belohnungsregeln", "profile_change_language": "Sprache ändern", "profile_back_account": "Zurück zum Konto",
        "profile_id": "ID", "profile_tier": "Stufe", "profile_balance": "Guthaben", "profile_detail_hint": "Nutze /profile für Empfehlungen, Geburtstagsgeschenke und Mitgliedschaftsdetails.",
        "profile_unlimited": "Unbegrenzt", "profile_remaining_uses": "verbleibende Servicenutzungen",
    },
    "ja": {
        "support_premium": "Premiumに登録", "support_custom_bot": "専用ボットを接続", "support_consult": "サービス相談",
        "profile_topup": "Xu をチャージ", "profile_pricing": "料金", "profile_packages": "マイパッケージ", "profile_membership": "メンバーシップ",
        "profile_xu_guide": "Xu ガイド", "profile_referral_link": "紹介リンク", "profile_referral_stats": "紹介履歴",
        "profile_referral_policy": "特典ルール", "profile_change_language": "言語を変更", "profile_back_account": "アカウントに戻る",
        "profile_id": "ID", "profile_tier": "ランク", "profile_balance": "残高", "profile_detail_hint": "/profile で紹介、誕生日特典、メンバーシップの詳細を確認できます。",
        "profile_unlimited": "無制限", "profile_remaining_uses": "回のサービス利用が残っています",
    },
    "ko": {
        "support_premium": "Premium 가입", "support_custom_bot": "맞춤 봇 연결", "support_consult": "서비스 상담",
        "profile_topup": "Xu 충전", "profile_pricing": "요금", "profile_packages": "내 패키지", "profile_membership": "멤버십",
        "profile_xu_guide": "Xu 안내", "profile_referral_link": "추천 링크", "profile_referral_stats": "추천 활동",
        "profile_referral_policy": "보상 규정", "profile_change_language": "언어 변경", "profile_back_account": "계정으로 돌아가기",
        "profile_id": "ID", "profile_tier": "등급", "profile_balance": "잔액", "profile_detail_hint": "/profile에서 추천, 생일 선물 및 멤버십 상세 정보를 확인하세요.",
        "profile_unlimited": "무제한", "profile_remaining_uses": "회 서비스 이용이 남았습니다",
    },
    "hi": {
        "support_premium": "Premium के लिए साइन अप करें", "support_custom_bot": "कस्टम बॉट कनेक्ट करें", "support_consult": "सेवा परामर्श",
        "profile_topup": "Xu टॉप-अप", "profile_pricing": "मूल्य", "profile_packages": "मेरे पैकेज", "profile_membership": "सदस्यता",
        "profile_xu_guide": "Xu गाइड", "profile_referral_link": "रेफरल लिंक", "profile_referral_stats": "रेफरल गतिविधि",
        "profile_referral_policy": "पुरस्कार नियम", "profile_change_language": "भाषा बदलें", "profile_back_account": "खाते पर वापस जाएँ",
        "profile_id": "ID", "profile_tier": "स्तर", "profile_balance": "शेष राशि", "profile_detail_hint": "रेफरल, जन्मदिन उपहार और सदस्यता विवरण देखने के लिए /profile का उपयोग करें।",
        "profile_unlimited": "असीमित", "profile_remaining_uses": "सेवा उपयोग शेष",
    },
    "ar": {
        "support_premium": "الاشتراك في Premium", "support_custom_bot": "ربط بوت مخصص", "support_consult": "استشارة الخدمات",
        "profile_topup": "شحن Xu", "profile_pricing": "الأسعار", "profile_packages": "باقاتي", "profile_membership": "العضوية",
        "profile_xu_guide": "دليل Xu", "profile_referral_link": "رابط الإحالة", "profile_referral_stats": "نشاط الإحالات",
        "profile_referral_policy": "قواعد المكافآت", "profile_change_language": "تغيير اللغة", "profile_back_account": "العودة إلى الحساب",
        "profile_id": "المعرف", "profile_tier": "المستوى", "profile_balance": "الرصيد", "profile_detail_hint": "استخدم /profile لعرض الإحالات وهدايا عيد الميلاد وتفاصيل العضوية.",
        "profile_unlimited": "غير محدود", "profile_remaining_uses": "استخدامات خدمة متبقية",
    },
    "ru": {
        "support_premium": "Подключить Premium", "support_custom_bot": "Подключить своего бота", "support_consult": "Консультация по услугам",
        "profile_topup": "Пополнить Xu", "profile_pricing": "Цены", "profile_packages": "Мои пакеты", "profile_membership": "Подписка",
        "profile_xu_guide": "Справка по Xu", "profile_referral_link": "Реферальная ссылка", "profile_referral_stats": "Активность приглашений",
        "profile_referral_policy": "Правила вознаграждений", "profile_change_language": "Сменить язык", "profile_back_account": "Вернуться к аккаунту",
        "profile_id": "ID", "profile_tier": "Уровень", "profile_balance": "Баланс", "profile_detail_hint": "Используйте /profile для просмотра приглашений, подарков ко дню рождения и сведений о подписке.",
        "profile_unlimited": "Без ограничений", "profile_remaining_uses": "использований сервиса осталось",
    },
    "tr": {
        "support_premium": "Premium'e katıl", "support_custom_bot": "Özel bot bağla", "support_consult": "Hizmet danışmanlığı",
        "profile_topup": "Xu yükle", "profile_pricing": "Fiyatlar", "profile_packages": "Paketlerim", "profile_membership": "Üyelik",
        "profile_xu_guide": "Xu rehberi", "profile_referral_link": "Davet bağlantısı", "profile_referral_stats": "Davet etkinliği",
        "profile_referral_policy": "Ödül kuralları", "profile_change_language": "Dili değiştir", "profile_back_account": "Hesaba dön",
        "profile_id": "ID", "profile_tier": "Seviye", "profile_balance": "Bakiye", "profile_detail_hint": "Davetleri, doğum günü hediyelerini ve üyelik ayrıntılarını görmek için /profile kullanın.",
        "profile_unlimited": "Sınırsız", "profile_remaining_uses": "hizmet kullanımı kaldı",
    },
    "th": {
        "support_premium": "สมัคร Premium", "support_custom_bot": "เชื่อมต่อบอตส่วนตัว", "support_consult": "ปรึกษาบริการ",
        "profile_topup": "เติม Xu", "profile_pricing": "ราคา", "profile_packages": "แพ็กเกจของฉัน", "profile_membership": "สมาชิก",
        "profile_xu_guide": "คู่มือ Xu", "profile_referral_link": "ลิงก์แนะนำ", "profile_referral_stats": "กิจกรรมการแนะนำ",
        "profile_referral_policy": "กติการางวัล", "profile_change_language": "เปลี่ยนภาษา", "profile_back_account": "กลับไปที่บัญชี",
        "profile_id": "ID", "profile_tier": "ระดับ", "profile_balance": "ยอดคงเหลือ", "profile_detail_hint": "ใช้ /profile เพื่อดูการแนะนำ ของขวัญวันเกิด และรายละเอียดสมาชิก",
        "profile_unlimited": "ไม่จำกัด", "profile_remaining_uses": "สิทธิ์ใช้บริการที่เหลือ",
    },
    "fil": {
        "support_premium": "Mag-sign up sa Premium", "support_custom_bot": "Ikonekta ang custom bot", "support_consult": "Konsultasyon sa serbisyo",
        "profile_topup": "Mag-top-up ng Xu", "profile_pricing": "Mga presyo", "profile_packages": "Mga package ko", "profile_membership": "Membership",
        "profile_xu_guide": "Gabay sa Xu", "profile_referral_link": "Link ng referral", "profile_referral_stats": "Aktibidad ng referral",
        "profile_referral_policy": "Mga patakaran sa gantimpala", "profile_change_language": "Palitan ang wika", "profile_back_account": "Bumalik sa account",
        "profile_id": "ID", "profile_tier": "Antas", "profile_balance": "Balanse", "profile_detail_hint": "Gamitin ang /profile upang makita ang referral, regalo sa kaarawan at detalye ng membership.",
        "profile_unlimited": "Walang limitasyon", "profile_remaining_uses": "natitirang paggamit ng serbisyo",
    },
    "it": {
        "support_premium": "Iscriviti a Premium", "support_custom_bot": "Collega un bot personalizzato", "support_consult": "Consulenza sui servizi",
        "profile_topup": "Ricarica Xu", "profile_pricing": "Prezzi", "profile_packages": "I miei pacchetti", "profile_membership": "Abbonamento",
        "profile_xu_guide": "Guida Xu", "profile_referral_link": "Link di invito", "profile_referral_stats": "Attività di invito",
        "profile_referral_policy": "Regole premio", "profile_change_language": "Cambia lingua", "profile_back_account": "Torna all’account",
        "profile_id": "ID", "profile_tier": "Livello", "profile_balance": "Saldo", "profile_detail_hint": "Usa /profile per vedere inviti, regali di compleanno e dettagli dell’abbonamento.",
        "profile_unlimited": "Illimitato", "profile_remaining_uses": "utilizzi del servizio rimanenti",
    },
    "id": {
        "support_premium": "Daftar Premium", "support_custom_bot": "Hubungkan bot khusus", "support_consult": "Konsultasi layanan",
        "profile_topup": "Isi ulang Xu", "profile_pricing": "Harga", "profile_packages": "Paket saya", "profile_membership": "Keanggotaan",
        "profile_xu_guide": "Panduan Xu", "profile_referral_link": "Tautan rujukan", "profile_referral_stats": "Aktivitas rujukan",
        "profile_referral_policy": "Aturan hadiah", "profile_change_language": "Ganti bahasa", "profile_back_account": "Kembali ke akun",
        "profile_id": "ID", "profile_tier": "Tingkat", "profile_balance": "Saldo", "profile_detail_hint": "Gunakan /profile untuk melihat rujukan, hadiah ulang tahun, dan detail keanggotaan.",
        "profile_unlimited": "Tanpa batas", "profile_remaining_uses": "penggunaan layanan tersisa",
    },
}


# Support child-flow labels are presentation-only.  They never select a ticket
# category, alter a callback, or change saved customer state.
_PUBLIC_SUPPORT_CHILD_LABELS = {
    "vi": {
        "support_contact_title": "Nhắn admin @toanaas", "support_auto_title": "CSKH tự động TOAN AAS",
        "support_open_telegram": "Mở Telegram @toanaas", "support_back": "Hỗ trợ",
        "support_ticket_prompt_title": "Tạo ticket hỗ trợ", "support_personal": "Cá nhân / Creator",
        "support_shop": "Shop / Affiliate", "support_business": "Doanh nghiệp", "support_private": "Tư vấn riêng",
        "support_bot_shop": "Bot bán hàng / shop online", "support_bot_content": "Bot nội dung / marketing",
        "support_bot_support": "Bot CSKH / ticket", "support_bot_internal": "Bot nội bộ doanh nghiệp",
        "support_bot_custom": "Nhập nhu cầu riêng", "support_consult_image": "Tạo ảnh",
        "support_consult_video": "Tạo video", "support_consult_frame_video": "Ghép ảnh thành video",
        "support_consult_document": "Tài liệu / PDF", "support_consult_voice": "Voice / TTS", "support_consult_package": "Gói / Combo",
    },
    "en": {
        "support_contact_title": "Message admin @toanaas", "support_auto_title": "TOAN AAS automated support",
        "support_open_telegram": "Open Telegram @toanaas", "support_back": "Support",
        "support_ticket_prompt_title": "Create a support ticket", "support_personal": "Personal / Creator",
        "support_shop": "Shop / Affiliate", "support_business": "Business", "support_private": "Private consultation",
        "support_bot_shop": "Sales / online-shop bot", "support_bot_content": "Content / marketing bot",
        "support_bot_support": "Customer-support / ticket bot", "support_bot_internal": "Internal business bot",
        "support_bot_custom": "Enter a custom need", "support_consult_image": "Image creation",
        "support_consult_video": "Video creation", "support_consult_frame_video": "Images to video",
        "support_consult_document": "Documents / PDF", "support_consult_voice": "Voice / TTS", "support_consult_package": "Plans / combos",
    },
    "zh": {
        "support_contact_title": "联系管理员 @toanaas", "support_auto_title": "TOAN AAS 自动客服",
        "support_open_telegram": "打开 Telegram @toanaas", "support_back": "支持",
        "support_ticket_prompt_title": "创建支持工单", "support_personal": "个人 / 创作者",
        "support_shop": "商店 / 联盟营销", "support_business": "企业", "support_private": "专属咨询",
        "support_bot_shop": "销售 / 网店机器人", "support_bot_content": "内容 / 营销机器人",
        "support_bot_support": "客服 / 工单机器人", "support_bot_internal": "企业内部机器人",
        "support_bot_custom": "填写自定义需求", "support_consult_image": "图片生成",
        "support_consult_video": "视频生成", "support_consult_frame_video": "图片转视频",
        "support_consult_document": "文档 / PDF", "support_consult_voice": "语音 / TTS", "support_consult_package": "套餐 / 组合",
    },
    "es": {
        "support_contact_title": "Escribir al administrador @toanaas", "support_auto_title": "Soporte automático de TOAN AAS",
        "support_open_telegram": "Abrir Telegram @toanaas", "support_back": "Soporte",
        "support_ticket_prompt_title": "Crear ticket de ayuda", "support_personal": "Personal / Creador",
        "support_shop": "Tienda / Afiliado", "support_business": "Empresa", "support_private": "Asesoría privada",
        "support_bot_shop": "Bot de ventas / tienda online", "support_bot_content": "Bot de contenido / marketing",
        "support_bot_support": "Bot de atención / tickets", "support_bot_internal": "Bot interno empresarial",
        "support_bot_custom": "Indicar necesidad personalizada", "support_consult_image": "Crear imágenes",
        "support_consult_video": "Crear vídeos", "support_consult_frame_video": "Imágenes a vídeo",
        "support_consult_document": "Documentos / PDF", "support_consult_voice": "Voz / TTS", "support_consult_package": "Planes / combos",
    },
    "pt": {
        "support_contact_title": "Falar com o administrador @toanaas", "support_auto_title": "Suporte automático TOAN AAS",
        "support_open_telegram": "Abrir Telegram @toanaas", "support_back": "Suporte",
        "support_ticket_prompt_title": "Criar ticket de suporte", "support_personal": "Pessoal / Criador",
        "support_shop": "Loja / Afiliado", "support_business": "Empresa", "support_private": "Consultoria privada",
        "support_bot_shop": "Bot de vendas / loja online", "support_bot_content": "Bot de conteúdo / marketing",
        "support_bot_support": "Bot de atendimento / tickets", "support_bot_internal": "Bot interno empresarial",
        "support_bot_custom": "Informar necessidade personalizada", "support_consult_image": "Criar imagens",
        "support_consult_video": "Criar vídeos", "support_consult_frame_video": "Imagens para vídeo",
        "support_consult_document": "Documentos / PDF", "support_consult_voice": "Voz / TTS", "support_consult_package": "Planos / combos",
    },
    "fr": {
        "support_contact_title": "Contacter l’administrateur @toanaas", "support_auto_title": "Assistance automatique TOAN AAS",
        "support_open_telegram": "Ouvrir Telegram @toanaas", "support_back": "Assistance",
        "support_ticket_prompt_title": "Créer un ticket d’assistance", "support_personal": "Personnel / Créateur",
        "support_shop": "Boutique / Affilié", "support_business": "Entreprise", "support_private": "Conseil privé",
        "support_bot_shop": "Bot de vente / boutique en ligne", "support_bot_content": "Bot de contenu / marketing",
        "support_bot_support": "Bot support / tickets", "support_bot_internal": "Bot interne d’entreprise",
        "support_bot_custom": "Saisir un besoin spécifique", "support_consult_image": "Création d’images",
        "support_consult_video": "Création de vidéos", "support_consult_frame_video": "Images vers vidéo",
        "support_consult_document": "Documents / PDF", "support_consult_voice": "Voix / TTS", "support_consult_package": "Forfaits / combos",
    },
    "de": {
        "support_contact_title": "Admin @toanaas kontaktieren", "support_auto_title": "Automatischer TOAN-AAS-Support",
        "support_open_telegram": "Telegram @toanaas öffnen", "support_back": "Support",
        "support_ticket_prompt_title": "Support-Ticket erstellen", "support_personal": "Privat / Creator",
        "support_shop": "Shop / Affiliate", "support_business": "Unternehmen", "support_private": "Private Beratung",
        "support_bot_shop": "Verkaufs- / Online-Shop-Bot", "support_bot_content": "Content- / Marketing-Bot",
        "support_bot_support": "Support- / Ticket-Bot", "support_bot_internal": "Interner Unternehmens-Bot",
        "support_bot_custom": "Eigenen Bedarf eingeben", "support_consult_image": "Bilder erstellen",
        "support_consult_video": "Videos erstellen", "support_consult_frame_video": "Bilder zu Video",
        "support_consult_document": "Dokumente / PDF", "support_consult_voice": "Stimme / TTS", "support_consult_package": "Pakete / Kombis",
    },
    "ja": {
        "support_contact_title": "管理者 @toanaas に連絡", "support_auto_title": "TOAN AAS 自動サポート",
        "support_open_telegram": "Telegram @toanaas を開く", "support_back": "サポート",
        "support_ticket_prompt_title": "サポートチケットを作成", "support_personal": "個人 / クリエイター",
        "support_shop": "ショップ / アフィリエイト", "support_business": "企業", "support_private": "個別相談",
        "support_bot_shop": "販売 / オンラインショップ用ボット", "support_bot_content": "コンテンツ / マーケティング用ボット",
        "support_bot_support": "CS サポート / チケット用ボット", "support_bot_internal": "社内業務用ボット",
        "support_bot_custom": "個別の要望を入力", "support_consult_image": "画像作成",
        "support_consult_video": "動画作成", "support_consult_frame_video": "画像から動画",
        "support_consult_document": "ドキュメント / PDF", "support_consult_voice": "音声 / TTS", "support_consult_package": "プラン / コンボ",
    },
    "ko": {
        "support_contact_title": "관리자 @toanaas에게 문의", "support_auto_title": "TOAN AAS 자동 지원",
        "support_open_telegram": "Telegram @toanaas 열기", "support_back": "지원",
        "support_ticket_prompt_title": "지원 티켓 만들기", "support_personal": "개인 / 크리에이터",
        "support_shop": "쇼핑몰 / 제휴", "support_business": "기업", "support_private": "개별 상담",
        "support_bot_shop": "판매 / 온라인 쇼핑몰 봇", "support_bot_content": "콘텐츠 / 마케팅 봇",
        "support_bot_support": "고객지원 / 티켓 봇", "support_bot_internal": "사내 업무 봇",
        "support_bot_custom": "맞춤 요구 입력", "support_consult_image": "이미지 만들기",
        "support_consult_video": "비디오 만들기", "support_consult_frame_video": "이미지를 비디오로",
        "support_consult_document": "문서 / PDF", "support_consult_voice": "음성 / TTS", "support_consult_package": "플랜 / 콤보",
    },
    "hi": {
        "support_contact_title": "एडमिन @toanaas को संदेश भेजें", "support_auto_title": "TOAN AAS स्वचालित सहायता",
        "support_open_telegram": "Telegram @toanaas खोलें", "support_back": "सहायता",
        "support_ticket_prompt_title": "सहायता टिकट बनाएं", "support_personal": "व्यक्तिगत / निर्माता",
        "support_shop": "दुकान / सहयोगी", "support_business": "व्यवसाय", "support_private": "निजी परामर्श",
        "support_bot_shop": "बिक्री / ऑनलाइन दुकान बॉट", "support_bot_content": "सामग्री / मार्केटिंग बॉट",
        "support_bot_support": "ग्राहक सहायता / टिकट बॉट", "support_bot_internal": "आंतरिक व्यवसाय बॉट",
        "support_bot_custom": "अपनी आवश्यकता लिखें", "support_consult_image": "छवि बनाना",
        "support_consult_video": "वीडियो बनाना", "support_consult_frame_video": "छवियों से वीडियो",
        "support_consult_document": "दस्तावेज़ / PDF", "support_consult_voice": "आवाज़ / TTS", "support_consult_package": "प्लान / कॉम्बो",
    },
    "ar": {
        "support_contact_title": "مراسلة المشرف @toanaas", "support_auto_title": "الدعم الآلي لـ TOAN AAS",
        "support_open_telegram": "فتح Telegram @toanaas", "support_back": "الدعم",
        "support_ticket_prompt_title": "إنشاء تذكرة دعم", "support_personal": "شخصي / منشئ",
        "support_shop": "متجر / شريك", "support_business": "شركة", "support_private": "استشارة خاصة",
        "support_bot_shop": "بوت مبيعات / متجر إلكتروني", "support_bot_content": "بوت محتوى / تسويق",
        "support_bot_support": "بوت دعم / تذاكر", "support_bot_internal": "بوت أعمال داخلي",
        "support_bot_custom": "أدخل احتياجاً مخصصاً", "support_consult_image": "إنشاء صور",
        "support_consult_video": "إنشاء فيديو", "support_consult_frame_video": "تحويل الصور إلى فيديو",
        "support_consult_document": "مستندات / PDF", "support_consult_voice": "صوت / TTS", "support_consult_package": "خطط / باقات",
    },
    "ru": {
        "support_contact_title": "Написать администратору @toanaas", "support_auto_title": "Автоподдержка TOAN AAS",
        "support_open_telegram": "Открыть Telegram @toanaas", "support_back": "Поддержка",
        "support_ticket_prompt_title": "Создать обращение", "support_personal": "Личный / Автор",
        "support_shop": "Магазин / Партнёр", "support_business": "Бизнес", "support_private": "Личная консультация",
        "support_bot_shop": "Бот продаж / интернет-магазина", "support_bot_content": "Бот контента / маркетинга",
        "support_bot_support": "Бот поддержки / обращений", "support_bot_internal": "Внутренний бизнес-бот",
        "support_bot_custom": "Указать свой запрос", "support_consult_image": "Создание изображений",
        "support_consult_video": "Создание видео", "support_consult_frame_video": "Изображения в видео",
        "support_consult_document": "Документы / PDF", "support_consult_voice": "Голос / TTS", "support_consult_package": "Пакеты / комбо",
    },
    "tr": {
        "support_contact_title": "Yönetici @toanaas'a yaz", "support_auto_title": "TOAN AAS otomatik destek",
        "support_open_telegram": "Telegram @toanaas'ı aç", "support_back": "Destek",
        "support_ticket_prompt_title": "Destek talebi oluştur", "support_personal": "Kişisel / İçerik üreticisi",
        "support_shop": "Mağaza / Ortak", "support_business": "İşletme", "support_private": "Özel danışmanlık",
        "support_bot_shop": "Satış / çevrimiçi mağaza botu", "support_bot_content": "İçerik / pazarlama botu",
        "support_bot_support": "Müşteri desteği / talep botu", "support_bot_internal": "Dahili işletme botu",
        "support_bot_custom": "Özel ihtiyacı girin", "support_consult_image": "Görsel oluşturma",
        "support_consult_video": "Video oluşturma", "support_consult_frame_video": "Görsellerden video",
        "support_consult_document": "Belgeler / PDF", "support_consult_voice": "Ses / TTS", "support_consult_package": "Planlar / paketler",
    },
    "th": {
        "support_contact_title": "ติดต่อผู้ดูแล @toanaas", "support_auto_title": "บริการช่วยเหลืออัตโนมัติ TOAN AAS",
        "support_open_telegram": "เปิด Telegram @toanaas", "support_back": "ช่วยเหลือ",
        "support_ticket_prompt_title": "สร้างทิกเก็ตช่วยเหลือ", "support_personal": "บุคคล / ครีเอเตอร์",
        "support_shop": "ร้านค้า / แอฟฟิลิเอต", "support_business": "ธุรกิจ", "support_private": "ปรึกษาส่วนตัว",
        "support_bot_shop": "บอตขาย / ร้านค้าออนไลน์", "support_bot_content": "บอตคอนเทนต์ / การตลาด",
        "support_bot_support": "บอตบริการลูกค้า / ทิกเก็ต", "support_bot_internal": "บอตงานภายในธุรกิจ",
        "support_bot_custom": "ระบุความต้องการเอง", "support_consult_image": "สร้างภาพ",
        "support_consult_video": "สร้างวิดีโอ", "support_consult_frame_video": "เปลี่ยนภาพเป็นวิดีโอ",
        "support_consult_document": "เอกสาร / PDF", "support_consult_voice": "เสียง / TTS", "support_consult_package": "แพ็กเกจ / คอมโบ",
    },
    "fil": {
        "support_contact_title": "Mensahe sa admin @toanaas", "support_auto_title": "Awtomatikong suporta ng TOAN AAS",
        "support_open_telegram": "Buksan ang Telegram @toanaas", "support_back": "Suporta",
        "support_ticket_prompt_title": "Gumawa ng support ticket", "support_personal": "Personal / Creator",
        "support_shop": "Shop / Affiliate", "support_business": "Negosyo", "support_private": "Pribadong konsultasyon",
        "support_bot_shop": "Sales / online-shop bot", "support_bot_content": "Content / marketing bot",
        "support_bot_support": "Customer support / ticket bot", "support_bot_internal": "Internal business bot",
        "support_bot_custom": "Ilagay ang sariling pangangailangan", "support_consult_image": "Paglikha ng larawan",
        "support_consult_video": "Paglikha ng video", "support_consult_frame_video": "Mga larawan papuntang video",
        "support_consult_document": "Mga dokumento / PDF", "support_consult_voice": "Boses / TTS", "support_consult_package": "Mga plano / combo",
    },
    "it": {
        "support_contact_title": "Scrivi all’amministratore @toanaas", "support_auto_title": "Assistenza automatica TOAN AAS",
        "support_open_telegram": "Apri Telegram @toanaas", "support_back": "Assistenza",
        "support_ticket_prompt_title": "Crea ticket di assistenza", "support_personal": "Personale / Creator",
        "support_shop": "Negozio / Affiliate", "support_business": "Azienda", "support_private": "Consulenza privata",
        "support_bot_shop": "Bot vendite / negozio online", "support_bot_content": "Bot contenuti / marketing",
        "support_bot_support": "Bot assistenza / ticket", "support_bot_internal": "Bot aziendale interno",
        "support_bot_custom": "Inserisci esigenza personalizzata", "support_consult_image": "Creazione immagini",
        "support_consult_video": "Creazione video", "support_consult_frame_video": "Immagini in video",
        "support_consult_document": "Documenti / PDF", "support_consult_voice": "Voce / TTS", "support_consult_package": "Piani / combo",
    },
    "id": {
        "support_contact_title": "Hubungi admin @toanaas", "support_auto_title": "Dukungan otomatis TOAN AAS",
        "support_open_telegram": "Buka Telegram @toanaas", "support_back": "Dukungan",
        "support_ticket_prompt_title": "Buat tiket dukungan", "support_personal": "Pribadi / Kreator",
        "support_shop": "Toko / Afiliasi", "support_business": "Bisnis", "support_private": "Konsultasi pribadi",
        "support_bot_shop": "Bot penjualan / toko online", "support_bot_content": "Bot konten / pemasaran",
        "support_bot_support": "Bot dukungan pelanggan / tiket", "support_bot_internal": "Bot bisnis internal",
        "support_bot_custom": "Masukkan kebutuhan khusus", "support_consult_image": "Pembuatan gambar",
        "support_consult_video": "Pembuatan video", "support_consult_frame_video": "Gambar menjadi video",
        "support_consult_document": "Dokumen / PDF", "support_consult_voice": "Suara / TTS", "support_consult_package": "Paket / kombo",
    },
}


_PUBLIC_SUPPORT_CHILD_TEXT = {
    "vi": {
        "support_contact_body": "Bạn có thể nhắn trực tiếp admin TOAN AAS tại @toanaas. Nếu cần kiểm tra giao dịch, hoàn Xu hoặc lỗi tác vụ, hãy tạo ticket trong bot để admin có đủ thông tin đối soát.",
        "support_auto_body": "Bạn có thể nhắn trực tiếp @toanaas. CSKH tự động hỗ trợ thông tin cơ bản về bảng giá, cách dùng và gói dịch vụ; các việc thanh toán, hoàn Xu hoặc lỗi cần kiểm tra sẽ được chuyển cho admin. Không gửi token, mật khẩu hoặc thông tin nhạy cảm.",
        "support_ticket_prompt_body": "Mô tả ngắn vấn đề bạn cần hỗ trợ. Ví dụ: cần tư vấn gói video, muốn làm bot riêng, cần hướng dẫn dùng công cụ hoặc muốn gặp admin. Nội dung về thanh toán, hoàn Xu hay lỗi kỹ thuật sẽ được tự phân loại.",
        "support_premium_body": "Premium phù hợp khi bạn dùng TOAN AAS thường xuyên, cần ưu tiên hỗ trợ, nhiều nội dung hơn hoặc quy trình riêng cho shop và doanh nghiệp. Bạn muốn đăng ký theo hướng nào?",
        "support_custom_body": "TOAN AAS có thể tư vấn bot riêng cho shop, đội nội dung, CSKH hoặc quy trình nội bộ. Bạn muốn làm loại bot nào?",
        "support_consult_body": "Bạn muốn tư vấn nhóm dịch vụ nào?",
    },
    "en": {
        "support_contact_body": "You can message the TOAN AAS admin directly at @toanaas. For a transaction check, Xu refund or task issue, create a ticket in the bot so the team has the details needed to review it.",
        "support_auto_body": "You can message @toanaas directly. Automated support helps with basic pricing, usage and plan information; payment, Xu refund or task issues are forwarded for review. Do not send tokens, passwords or sensitive information.",
        "support_ticket_prompt_body": "Briefly describe what you need help with. For example: advice on a video plan, a custom bot, using a tool, or contacting an admin. Payment, Xu refund and technical issues are categorized automatically.",
        "support_premium_body": "Premium suits regular TOAN AAS users who need priority support, more content capacity or a tailored workflow for a shop or business. Which route would you like to take?",
        "support_custom_body": "TOAN AAS can advise on a custom bot for a shop, content team, customer support or internal operations. What kind of bot do you need?",
        "support_consult_body": "Which service group would you like advice on?",
    },
    "zh": {
        "support_contact_body": "您可以直接向 @toanaas 联系 TOAN AAS 管理员。如需核查交易、Xu 退款或任务错误，请在机器人中创建工单，以便团队获得完整的核查信息。",
        "support_auto_body": "您可以直接向 @toanaas 发消息。自动客服可协助价格、使用方法和套餐等基本问题；付款、Xu 退款或任务错误会转交人工核查。请勿发送令牌、密码或敏感信息。",
        "support_ticket_prompt_body": "请简要说明您需要的帮助，例如咨询视频套餐、定制机器人、工具使用方法或联系管理员。付款、Xu 退款和技术问题会自动分类。",
        "support_premium_body": "Premium 适合经常使用 TOAN AAS、需要优先支持、更多内容额度或为商店和企业定制流程的用户。您想选择哪种方式？",
        "support_custom_body": "TOAN AAS 可为商店、内容团队、客服或内部流程提供定制机器人咨询。您需要哪类机器人？",
        "support_consult_body": "您希望咨询哪一类服务？",
    },
    "es": {
        "support_contact_body": "Puedes escribir directamente al administrador de TOAN AAS en @toanaas. Para revisar una transacción, reembolso de Xu o problema de tarea, crea un ticket en el bot para que el equipo tenga la información necesaria.",
        "support_auto_body": "Puedes escribir directamente a @toanaas. El soporte automático ayuda con precios, uso y planes; los asuntos de pago, reembolso de Xu o tareas se derivan para revisión. No envíes tokens, contraseñas ni información sensible.",
        "support_ticket_prompt_body": "Describe brevemente lo que necesitas. Por ejemplo: asesoría sobre un plan de vídeo, un bot personalizado, uso de una herramienta o contactar a un administrador. Los pagos, reembolsos de Xu y problemas técnicos se clasifican automáticamente.",
        "support_premium_body": "Premium es para quienes usan TOAN AAS con frecuencia y necesitan soporte prioritario, más capacidad o un flujo adaptado para una tienda o empresa. ¿Qué opción prefieres?",
        "support_custom_body": "TOAN AAS puede asesorarte sobre un bot personalizado para tienda, equipo de contenido, atención al cliente u operaciones internas. ¿Qué tipo de bot necesitas?",
        "support_consult_body": "¿Sobre qué grupo de servicios quieres asesoría?",
    },
    "pt": {
        "support_contact_body": "Você pode falar diretamente com o administrador da TOAN AAS em @toanaas. Para verificar uma transação, reembolso de Xu ou problema de tarefa, crie um ticket no bot para que a equipe tenha os dados necessários.",
        "support_auto_body": "Você pode enviar mensagem diretamente a @toanaas. O suporte automático ajuda com preços, uso e planos; questões de pagamento, reembolso de Xu ou tarefas são encaminhadas para análise. Não envie tokens, senhas ou dados sensíveis.",
        "support_ticket_prompt_body": "Descreva brevemente o que precisa. Por exemplo: orientação sobre um plano de vídeo, bot personalizado, uso de ferramenta ou falar com o administrador. Pagamentos, reembolsos de Xu e problemas técnicos são classificados automaticamente.",
        "support_premium_body": "Premium é indicado para quem usa TOAN AAS com frequência e precisa de suporte prioritário, mais capacidade ou um fluxo sob medida para loja ou empresa. Qual opção você prefere?",
        "support_custom_body": "TOAN AAS pode orientar sobre um bot personalizado para loja, equipe de conteúdo, atendimento ou operações internas. Que tipo de bot você precisa?",
        "support_consult_body": "Sobre qual grupo de serviços você quer orientação?",
    },
    "fr": {
        "support_contact_body": "Vous pouvez contacter directement l’administrateur de TOAN AAS via @toanaas. Pour vérifier une transaction, un remboursement de Xu ou un problème de tâche, créez un ticket dans le bot afin que l’équipe ait les éléments nécessaires.",
        "support_auto_body": "Vous pouvez écrire directement à @toanaas. L’assistance automatique aide pour les tarifs, l’utilisation et les forfaits ; les questions de paiement, remboursement de Xu ou tâche sont transmises pour vérification. N’envoyez ni jetons, ni mots de passe, ni données sensibles.",
        "support_ticket_prompt_body": "Décrivez brièvement votre besoin : conseil sur un forfait vidéo, bot personnalisé, utilisation d’un outil ou contact avec un administrateur. Les paiements, remboursements de Xu et problèmes techniques sont classés automatiquement.",
        "support_premium_body": "Premium convient aux utilisateurs réguliers de TOAN AAS qui souhaitent une assistance prioritaire, davantage de capacité ou un flux sur mesure pour une boutique ou une entreprise. Quelle option choisissez-vous ?",
        "support_custom_body": "TOAN AAS peut conseiller un bot personnalisé pour une boutique, une équipe de contenu, le support client ou des opérations internes. Quel bot vous faut-il ?",
        "support_consult_body": "Pour quel groupe de services souhaitez-vous un conseil ?",
    },
    "de": {
        "support_contact_body": "Du kannst den TOAN-AAS-Admin direkt über @toanaas kontaktieren. Für eine Transaktionsprüfung, Xu-Erstattung oder ein Aufgabenproblem erstelle bitte ein Ticket im Bot, damit das Team alle nötigen Angaben hat.",
        "support_auto_body": "Du kannst @toanaas direkt schreiben. Der automatische Support hilft bei Preisen, Nutzung und Paketen; Zahlungs-, Xu-Erstattungs- oder Aufgabenprobleme werden zur Prüfung weitergeleitet. Sende keine Tokens, Passwörter oder sensiblen Daten.",
        "support_ticket_prompt_body": "Beschreibe kurz, wobei du Hilfe brauchst: etwa zu einem Videopaket, einem eigenen Bot, der Nutzung eines Tools oder dem Kontakt zum Admin. Zahlungen, Xu-Erstattungen und technische Probleme werden automatisch eingeordnet.",
        "support_premium_body": "Premium eignet sich für regelmäßige TOAN-AAS-Nutzung mit priorisiertem Support, mehr Kapazität oder einem angepassten Ablauf für Shop oder Unternehmen. Welche Option möchtest du?",
        "support_custom_body": "TOAN AAS kann zu einem eigenen Bot für Shop, Content-Team, Kundensupport oder interne Abläufe beraten. Welchen Bot brauchst du?",
        "support_consult_body": "Zu welcher Servicegruppe möchtest du Beratung?",
    },
    "ja": {
        "support_contact_body": "TOAN AAS の管理者には @toanaas から直接連絡できます。取引確認、Xu の返金、タスクの問題については、確認に必要な情報を揃えるためボット内でチケットを作成してください。",
        "support_auto_body": "@toanaas に直接メッセージできます。自動サポートは料金、使い方、プランの基本案内を行い、支払い、Xu の返金、タスクの問題は確認のため担当者に引き継ぎます。トークン、パスワード、機密情報は送信しないでください。",
        "support_ticket_prompt_body": "必要なサポート内容を簡潔に説明してください。たとえば、動画プランの相談、専用ボット、ツールの使い方、管理者への連絡などです。支払い、Xu の返金、技術的な問題は自動分類されます。",
        "support_premium_body": "Premium は TOAN AAS を頻繁に利用し、優先サポート、より多い利用枠、またはショップ・企業向けの専用ワークフローが必要な方に適しています。どの方法で申し込みますか？",
        "support_custom_body": "TOAN AAS は、ショップ、コンテンツチーム、カスタマーサポート、社内業務向けの専用ボットを提案できます。どの種類のボットが必要ですか？",
        "support_consult_body": "どのサービスについて相談しますか？",
    },
    "ko": {
        "support_contact_body": "@toanaas에서 TOAN AAS 관리자에게 직접 문의할 수 있습니다. 거래 확인, Xu 환불 또는 작업 문제는 필요한 확인 정보를 갖출 수 있도록 봇에서 티켓을 만들어 주세요.",
        "support_auto_body": "@toanaas에 직접 메시지를 보낼 수 있습니다. 자동 지원은 요금, 사용 방법 및 플랜의 기본 정보를 안내하며 결제, Xu 환불 또는 작업 문제는 검토를 위해 전달합니다. 토큰, 비밀번호 또는 민감한 정보는 보내지 마세요.",
        "support_ticket_prompt_body": "필요한 도움을 간단히 설명해 주세요. 예: 비디오 플랜 상담, 맞춤 봇, 도구 사용법 또는 관리자 문의. 결제, Xu 환불 및 기술 문제는 자동으로 분류됩니다.",
        "support_premium_body": "Premium은 TOAN AAS를 자주 사용하며 우선 지원, 더 많은 이용량 또는 쇼핑몰·기업용 맞춤 워크플로가 필요한 사용자에게 적합합니다. 어떤 방식으로 신청하시겠어요?",
        "support_custom_body": "TOAN AAS는 쇼핑몰, 콘텐츠 팀, 고객 지원 또는 내부 업무를 위한 맞춤 봇을 상담해 드립니다. 어떤 유형의 봇이 필요하세요?",
        "support_consult_body": "어떤 서비스 그룹에 대해 상담을 원하시나요?",
    },
    "hi": {
        "support_contact_body": "आप @toanaas पर TOAN AAS एडमिन को सीधे संदेश भेज सकते हैं। लेन-देन जांच, Xu रिफंड या कार्य संबंधी समस्या के लिए बॉट में टिकट बनाएं ताकि टीम के पास समीक्षा के लिए आवश्यक जानकारी हो।",
        "support_auto_body": "आप @toanaas को सीधे संदेश भेज सकते हैं। स्वचालित सहायता कीमतों, उपयोग और प्लान की मूल जानकारी देती है; भुगतान, Xu रिफंड या कार्य समस्याएं समीक्षा के लिए भेजी जाती हैं। टोकन, पासवर्ड या संवेदनशील जानकारी न भेजें।",
        "support_ticket_prompt_body": "संक्षेप में बताएं कि आपको किस मदद की जरूरत है। उदाहरण: वीडियो प्लान पर सलाह, कस्टम बॉट, किसी टूल का उपयोग या एडमिन से संपर्क। भुगतान, Xu रिफंड और तकनीकी समस्याएं अपने आप वर्गीकृत होती हैं।",
        "support_premium_body": "Premium उन लोगों के लिए है जो TOAN AAS का नियमित उपयोग करते हैं और प्राथमिक सहायता, अधिक क्षमता या दुकान/व्यवसाय के लिए अनुकूलित कार्यप्रवाह चाहते हैं। आप कौन-सा विकल्प चुनना चाहते हैं?",
        "support_custom_body": "TOAN AAS दुकान, सामग्री टीम, ग्राहक सहायता या आंतरिक काम के लिए कस्टम बॉट पर सलाह दे सकता है। आपको किस प्रकार का बॉट चाहिए?",
        "support_consult_body": "आप किस सेवा समूह पर सलाह चाहते हैं?",
    },
    "ar": {
        "support_contact_body": "يمكنك مراسلة مشرف TOAN AAS مباشرة عبر @toanaas. للتحقق من معاملة أو استرداد Xu أو مشكلة مهمة، أنشئ تذكرة في البوت ليحصل الفريق على المعلومات اللازمة للمراجعة.",
        "support_auto_body": "يمكنك مراسلة @toanaas مباشرة. يساعد الدعم الآلي في الأسعار وطريقة الاستخدام والخطط؛ وتُحال مسائل الدفع أو استرداد Xu أو مشاكل المهام للمراجعة. لا ترسل رموزاً أو كلمات مرور أو معلومات حساسة.",
        "support_ticket_prompt_body": "اشرح باختصار المساعدة التي تحتاجها، مثل استشارة خطة فيديو أو بوت مخصص أو استخدام أداة أو التواصل مع المشرف. تُصنّف مسائل الدفع واسترداد Xu والمشكلات التقنية تلقائياً.",
        "support_premium_body": "Premium مناسب لمن يستخدم TOAN AAS بانتظام ويحتاج إلى دعم ذي أولوية أو سعة أكبر أو سير عمل مخصص لمتجر أو شركة. أي خيار تفضّل؟",
        "support_custom_body": "يمكن لـ TOAN AAS تقديم المشورة بشأن بوت مخصص لمتجر أو فريق محتوى أو دعم عملاء أو عمليات داخلية. ما نوع البوت الذي تحتاجه؟",
        "support_consult_body": "أي مجموعة خدمات تريد استشارة بشأنها؟",
    },
    "ru": {
        "support_contact_body": "Вы можете напрямую написать администратору TOAN AAS через @toanaas. Для проверки операции, возврата Xu или проблемы с задачей создайте обращение в боте, чтобы у команды были нужные данные.",
        "support_auto_body": "Вы можете написать @toanaas напрямую. Автоподдержка помогает с ценами, использованием и пакетами; вопросы оплаты, возврата Xu или задач передаются на проверку. Не отправляйте токены, пароли или конфиденциальные данные.",
        "support_ticket_prompt_body": "Кратко опишите, какая помощь нужна: консультация по видеопакету, свой бот, использование инструмента или связь с администратором. Оплата, возврат Xu и технические проблемы классифицируются автоматически.",
        "support_premium_body": "Premium подходит тем, кто регулярно использует TOAN AAS и хочет приоритетную поддержку, больше возможностей или индивидуальный процесс для магазина либо бизнеса. Какой вариант выбрать?",
        "support_custom_body": "TOAN AAS может проконсультировать по собственному боту для магазина, контент-команды, поддержки клиентов или внутренних процессов. Какой бот вам нужен?",
        "support_consult_body": "По какой группе услуг вам нужна консультация?",
    },
    "tr": {
        "support_contact_body": "TOAN AAS yöneticisine @toanaas üzerinden doğrudan yazabilirsiniz. İşlem kontrolü, Xu iadesi veya görev sorunu için ekibin inceleme yapabilmesi adına botta bir talep oluşturun.",
        "support_auto_body": "@toanaas'a doğrudan yazabilirsiniz. Otomatik destek fiyatlar, kullanım ve paketler hakkında temel bilgi verir; ödeme, Xu iadesi veya görev sorunları incelemeye iletilir. Token, parola veya hassas bilgi göndermeyin.",
        "support_ticket_prompt_body": "Neye yardım gerektiğini kısaca anlatın: video paketi danışmanlığı, özel bot, araç kullanımı veya yöneticiyle iletişim gibi. Ödeme, Xu iadesi ve teknik sorunlar otomatik sınıflandırılır.",
        "support_premium_body": "Premium, TOAN AAS'i düzenli kullanan ve öncelikli destek, daha fazla kapasite ya da mağaza/işletme için özel iş akışı isteyenler içindir. Hangi seçeneği tercih edersiniz?",
        "support_custom_body": "TOAN AAS; mağaza, içerik ekibi, müşteri desteği veya iç işlemler için özel bot konusunda danışmanlık verebilir. Hangi tür bota ihtiyacınız var?",
        "support_consult_body": "Hangi hizmet grubu için danışmanlık istiyorsunuz?",
    },
    "th": {
        "support_contact_body": "คุณสามารถติดต่อผู้ดูแล TOAN AAS โดยตรงที่ @toanaas หากต้องตรวจสอบธุรกรรม คืน Xu หรือมีปัญหางาน โปรดสร้างทิกเก็ตในบอตเพื่อให้ทีมมีข้อมูลสำหรับตรวจสอบ",
        "support_auto_body": "คุณสามารถส่งข้อความถึง @toanaas ได้โดยตรง ระบบช่วยเหลืออัตโนมัติให้ข้อมูลพื้นฐานเรื่องราคา การใช้งาน และแพ็กเกจ ส่วนการชำระเงิน คืน Xu หรือปัญหางานจะส่งให้ตรวจสอบ อย่าส่งโทเค็น รหัสผ่าน หรือข้อมูลสำคัญ",
        "support_ticket_prompt_body": "อธิบายสิ่งที่ต้องการความช่วยเหลือสั้น ๆ เช่น ปรึกษาแพ็กเกจวิดีโอ บอตแบบกำหนดเอง วิธีใช้เครื่องมือ หรือติดต่อผู้ดูแล เรื่องชำระเงิน คืน Xu และปัญหาทางเทคนิคจะถูกจัดหมวดหมู่อัตโนมัติ",
        "support_premium_body": "Premium เหมาะสำหรับผู้ใช้ TOAN AAS เป็นประจำที่ต้องการการช่วยเหลือก่อน ความจุมากขึ้น หรือเวิร์กโฟลว์เฉพาะสำหรับร้านค้าและธุรกิจ คุณต้องการเลือกแบบใด?",
        "support_custom_body": "TOAN AAS สามารถให้คำปรึกษาเรื่องบอตเฉพาะสำหรับร้านค้า ทีมคอนเทนต์ ฝ่ายบริการลูกค้า หรืองานภายใน ต้องการบอตประเภทใด?",
        "support_consult_body": "ต้องการปรึกษากลุ่มบริการใด?",
    },
    "fil": {
        "support_contact_body": "Maaari mong direktang kausapin ang TOAN AAS admin sa @toanaas. Para sa pagsusuri ng transaksyon, refund ng Xu o problema sa gawain, gumawa ng ticket sa bot upang kumpleto ang impormasyong susuriin ng team.",
        "support_auto_body": "Maaari kang direktang mag-message sa @toanaas. Tumutulong ang awtomatikong suporta sa presyo, paggamit at mga package; ipinapasa para suriin ang bayad, Xu refund o problema sa gawain. Huwag magpadala ng token, password o sensitibong impormasyon.",
        "support_ticket_prompt_body": "Ilarawan nang maikli ang kailangan mong tulong, tulad ng payo sa video package, custom bot, paggamit ng tool o pakikipag-ugnayan sa admin. Awtomatikong ikinokategorya ang bayad, Xu refund at teknikal na problema.",
        "support_premium_body": "Para ang Premium sa regular na gumagamit ng TOAN AAS na kailangan ng priority support, mas maraming kapasidad o inangkop na workflow para sa shop o negosyo. Aling opsyon ang gusto mo?",
        "support_custom_body": "Makakapagpayo ang TOAN AAS tungkol sa custom bot para sa shop, content team, customer support o internal operations. Anong uri ng bot ang kailangan mo?",
        "support_consult_body": "Anong grupo ng serbisyo ang gusto mong ikonsulta?",
    },
    "it": {
        "support_contact_body": "Puoi scrivere direttamente all’amministratore TOAN AAS su @toanaas. Per verificare una transazione, un rimborso Xu o un problema di attività, crea un ticket nel bot così il team avrà i dati necessari.",
        "support_auto_body": "Puoi scrivere direttamente a @toanaas. L’assistenza automatica aiuta con prezzi, uso e pacchetti; questioni di pagamento, rimborso Xu o attività vengono inoltrate per verifica. Non inviare token, password o dati sensibili.",
        "support_ticket_prompt_body": "Descrivi brevemente ciò di cui hai bisogno: consulenza su un pacchetto video, bot personalizzato, uso di uno strumento o contatto con l’amministratore. Pagamenti, rimborsi Xu e problemi tecnici vengono classificati automaticamente.",
        "support_premium_body": "Premium è pensato per chi usa TOAN AAS spesso e desidera assistenza prioritaria, più capacità o un flusso su misura per negozio o azienda. Quale opzione preferisci?",
        "support_custom_body": "TOAN AAS può consigliare un bot personalizzato per negozio, team contenuti, assistenza clienti o operazioni interne. Che tipo di bot ti serve?",
        "support_consult_body": "Per quale gruppo di servizi desideri una consulenza?",
    },
    "id": {
        "support_contact_body": "Anda dapat menghubungi admin TOAN AAS langsung di @toanaas. Untuk pemeriksaan transaksi, pengembalian Xu, atau masalah tugas, buat tiket di bot agar tim memiliki informasi yang diperlukan untuk meninjau.",
        "support_auto_body": "Anda dapat langsung mengirim pesan ke @toanaas. Dukungan otomatis membantu informasi dasar harga, penggunaan, dan paket; masalah pembayaran, pengembalian Xu, atau tugas diteruskan untuk ditinjau. Jangan kirim token, kata sandi, atau informasi sensitif.",
        "support_ticket_prompt_body": "Jelaskan secara singkat bantuan yang Anda perlukan, misalnya konsultasi paket video, bot khusus, penggunaan alat, atau menghubungi admin. Pembayaran, pengembalian Xu, dan masalah teknis dikategorikan otomatis.",
        "support_premium_body": "Premium cocok untuk pengguna TOAN AAS rutin yang memerlukan dukungan prioritas, kapasitas lebih banyak, atau alur kerja khusus untuk toko atau bisnis. Opsi mana yang Anda pilih?",
        "support_custom_body": "TOAN AAS dapat memberi konsultasi tentang bot khusus untuk toko, tim konten, dukungan pelanggan, atau operasi internal. Bot jenis apa yang Anda perlukan?",
        "support_consult_body": "Kelompok layanan mana yang ingin Anda konsultasikan?",
    },
}


# Deep Support copy is deliberately separate from ticket classifications and
# payload data.  The runtime uses the stable bot/service codes and inserts only
# the selected option into these presentation templates.
_PUBLIC_SUPPORT_DEEP_COPY = {
    "vi": {
        "support_detail_title": "Kết nối bot riêng", "support_detail_body": "TOAN AAS có thể tư vấn bot phù hợp với mục tiêu và quy trình của bạn.", "support_detail_questions": "Bạn mô tả giúp mình:",
        "support_detail_enter_need": "Nhập nhu cầu", "support_detail_create_lead": "Tạo lead tư vấn", "support_detail_back_bot": "Kết nối bot riêng",
        "support_consult_detail_title": "Tư vấn dịch vụ", "support_consult_detail_intro": "TOAN AAS có thể hỗ trợ:", "support_consult_detail_input": "Nhập nhu cầu riêng", "support_consult_detail_ticket": "Tạo ticket tư vấn", "support_consult_detail_premium": "Đăng ký Premium", "support_consult_detail_back": "Tư vấn gói dịch vụ",
        "support_lead_premium_title": "Đăng ký Premium", "support_lead_premium_body": "Bạn gửi mục đích sử dụng TOAN AAS, nhu cầu chính, tần suất dự kiến và cách liên hệ nếu muốn admin tư vấn.",
        "support_lead_custom_title": "Kết nối bot riêng", "support_lead_custom_body": "Bạn mô tả nhu cầu chính, quy mô sử dụng, quy trình muốn tự động hóa và cách liên hệ thuận tiện.",
        "support_input_one_message": "Bạn nhập câu trả lời trong một tin nhắn nhé.",
    },
    "en": {
        "support_detail_title": "Custom bot consultation", "support_detail_body": "TOAN AAS can advise on a bot that fits your goals and workflow.", "support_detail_questions": "Please describe:",
        "support_detail_enter_need": "Enter your needs", "support_detail_create_lead": "Create a consultation lead", "support_detail_back_bot": "Custom bot consultation",
        "support_consult_detail_title": "Service consultation", "support_consult_detail_intro": "TOAN AAS can help with:", "support_consult_detail_input": "Enter a custom need", "support_consult_detail_ticket": "Create a consultation ticket", "support_consult_detail_premium": "Join Premium", "support_consult_detail_back": "Service consultation",
        "support_lead_premium_title": "Join Premium", "support_lead_premium_body": "Send your TOAN AAS use case, main needs, expected frequency, and a contact method if you want an admin consultation.",
        "support_lead_custom_title": "Custom bot consultation", "support_lead_custom_body": "Describe your main need, usage scale, workflow to automate, and a convenient contact method.",
        "support_input_one_message": "Please send your answer in one message.",
    },
    "zh": {
        "support_detail_title": "定制机器人咨询", "support_detail_body": "TOAN AAS 可以为符合您目标和工作流程的机器人提供建议。", "support_detail_questions": "请说明：",
        "support_detail_enter_need": "填写需求", "support_detail_create_lead": "创建咨询线索", "support_detail_back_bot": "定制机器人咨询",
        "support_consult_detail_title": "服务咨询", "support_consult_detail_intro": "TOAN AAS 可提供以下帮助：", "support_consult_detail_input": "填写自定义需求", "support_consult_detail_ticket": "创建咨询工单", "support_consult_detail_premium": "加入 Premium", "support_consult_detail_back": "服务咨询",
        "support_lead_premium_title": "加入 Premium", "support_lead_premium_body": "请发送您使用 TOAN AAS 的目的、主要需求、预计频率，以及希望管理员咨询时的联系方式。",
        "support_lead_custom_title": "定制机器人咨询", "support_lead_custom_body": "请描述主要需求、使用规模、希望自动化的流程和方便的联系方式。",
        "support_input_one_message": "请在一条消息中发送您的回复。",
    },
    "es": {
        "support_detail_title": "Consulta sobre bot personalizado", "support_detail_body": "TOAN AAS puede aconsejarte sobre un bot que se ajuste a tus objetivos y flujo de trabajo.", "support_detail_questions": "Describe, por favor:",
        "support_detail_enter_need": "Indicar necesidades", "support_detail_create_lead": "Crear solicitud de consulta", "support_detail_back_bot": "Consulta sobre bot personalizado",
        "support_consult_detail_title": "Consulta de servicios", "support_consult_detail_intro": "TOAN AAS puede ayudarte con:", "support_consult_detail_input": "Indicar necesidad personalizada", "support_consult_detail_ticket": "Crear ticket de consulta", "support_consult_detail_premium": "Unirse a Premium", "support_consult_detail_back": "Consulta de servicios",
        "support_lead_premium_title": "Unirse a Premium", "support_lead_premium_body": "Envía el uso que darás a TOAN AAS, tus necesidades principales, la frecuencia prevista y un contacto si deseas asesoría del administrador.",
        "support_lead_custom_title": "Consulta sobre bot personalizado", "support_lead_custom_body": "Describe tu necesidad principal, escala de uso, flujo que quieres automatizar y un medio de contacto conveniente.",
        "support_input_one_message": "Envía tu respuesta en un solo mensaje.",
    },
    "pt": {
        "support_detail_title": "Consultoria de bot personalizado", "support_detail_body": "A TOAN AAS pode orientar sobre um bot adequado aos seus objetivos e fluxo de trabalho.", "support_detail_questions": "Descreva, por favor:",
        "support_detail_enter_need": "Informar necessidades", "support_detail_create_lead": "Criar solicitação de consulta", "support_detail_back_bot": "Consultoria de bot personalizado",
        "support_consult_detail_title": "Consultoria de serviços", "support_consult_detail_intro": "A TOAN AAS pode ajudar com:", "support_consult_detail_input": "Informar necessidade personalizada", "support_consult_detail_ticket": "Criar ticket de consulta", "support_consult_detail_premium": "Entrar no Premium", "support_consult_detail_back": "Consultoria de serviços",
        "support_lead_premium_title": "Entrar no Premium", "support_lead_premium_body": "Envie seu objetivo de uso da TOAN AAS, necessidades principais, frequência prevista e uma forma de contato se desejar orientação do administrador.",
        "support_lead_custom_title": "Consultoria de bot personalizado", "support_lead_custom_body": "Descreva sua necessidade principal, escala de uso, fluxo que deseja automatizar e uma forma conveniente de contato.",
        "support_input_one_message": "Envie sua resposta em uma única mensagem.",
    },
    "fr": {
        "support_detail_title": "Conseil pour bot personnalisé", "support_detail_body": "TOAN AAS peut vous conseiller un bot adapté à vos objectifs et à votre flux de travail.", "support_detail_questions": "Merci de décrire :",
        "support_detail_enter_need": "Saisir le besoin", "support_detail_create_lead": "Créer une demande de conseil", "support_detail_back_bot": "Conseil pour bot personnalisé",
        "support_consult_detail_title": "Conseil de service", "support_consult_detail_intro": "TOAN AAS peut vous aider pour :", "support_consult_detail_input": "Saisir un besoin spécifique", "support_consult_detail_ticket": "Créer un ticket de conseil", "support_consult_detail_premium": "Rejoindre Premium", "support_consult_detail_back": "Conseil de service",
        "support_lead_premium_title": "Rejoindre Premium", "support_lead_premium_body": "Envoyez votre usage de TOAN AAS, vos besoins principaux, la fréquence prévue et un moyen de contact si vous souhaitez un conseil de l’administrateur.",
        "support_lead_custom_title": "Conseil pour bot personnalisé", "support_lead_custom_body": "Décrivez votre besoin principal, l’ampleur d’utilisation, le flux à automatiser et un moyen de contact pratique.",
        "support_input_one_message": "Envoyez votre réponse dans un seul message.",
    },
    "de": {
        "support_detail_title": "Beratung für eigenen Bot", "support_detail_body": "TOAN AAS kann zu einem Bot beraten, der zu deinen Zielen und deinem Ablauf passt.", "support_detail_questions": "Bitte beschreibe:",
        "support_detail_enter_need": "Bedarf eingeben", "support_detail_create_lead": "Beratungsanfrage erstellen", "support_detail_back_bot": "Beratung für eigenen Bot",
        "support_consult_detail_title": "Serviceberatung", "support_consult_detail_intro": "TOAN AAS kann helfen bei:", "support_consult_detail_input": "Eigenen Bedarf eingeben", "support_consult_detail_ticket": "Beratungsticket erstellen", "support_consult_detail_premium": "Premium buchen", "support_consult_detail_back": "Serviceberatung",
        "support_lead_premium_title": "Premium buchen", "support_lead_premium_body": "Sende deinen TOAN-AAS-Einsatzzweck, die wichtigsten Anforderungen, die erwartete Häufigkeit und eine Kontaktmöglichkeit für eine Admin-Beratung.",
        "support_lead_custom_title": "Beratung für eigenen Bot", "support_lead_custom_body": "Beschreibe deinen Hauptbedarf, den Nutzungsumfang, den zu automatisierenden Ablauf und eine passende Kontaktmöglichkeit.",
        "support_input_one_message": "Bitte sende deine Antwort in einer Nachricht.",
    },
    "ja": {
        "support_detail_title": "カスタムボット相談", "support_detail_body": "TOAN AAS は、目標と業務フローに合うボットをご提案できます。", "support_detail_questions": "次の内容を教えてください：",
        "support_detail_enter_need": "要望を入力", "support_detail_create_lead": "相談リードを作成", "support_detail_back_bot": "カスタムボット相談",
        "support_consult_detail_title": "サービス相談", "support_consult_detail_intro": "TOAN AAS がお手伝いできる内容：", "support_consult_detail_input": "個別の要望を入力", "support_consult_detail_ticket": "相談チケットを作成", "support_consult_detail_premium": "Premium に申し込む", "support_consult_detail_back": "サービス相談",
        "support_lead_premium_title": "Premium に申し込む", "support_lead_premium_body": "TOAN AAS の利用目的、主な要望、予定利用頻度、管理者の相談を希望する場合の連絡先を送ってください。",
        "support_lead_custom_title": "カスタムボット相談", "support_lead_custom_body": "主な要望、利用規模、自動化したいフロー、連絡しやすい方法を説明してください。",
        "support_input_one_message": "回答は1通のメッセージで送信してください。",
    },
    "ko": {
        "support_detail_title": "맞춤 봇 상담", "support_detail_body": "TOAN AAS는 목표와 업무 흐름에 맞는 봇을 상담해 드릴 수 있습니다.", "support_detail_questions": "다음을 알려 주세요:",
        "support_detail_enter_need": "요구사항 입력", "support_detail_create_lead": "상담 요청 만들기", "support_detail_back_bot": "맞춤 봇 상담",
        "support_consult_detail_title": "서비스 상담", "support_consult_detail_intro": "TOAN AAS가 도와드릴 수 있는 내용:", "support_consult_detail_input": "맞춤 요구 입력", "support_consult_detail_ticket": "상담 티켓 만들기", "support_consult_detail_premium": "Premium 신청", "support_consult_detail_back": "서비스 상담",
        "support_lead_premium_title": "Premium 신청", "support_lead_premium_body": "TOAN AAS 사용 목적, 주요 요구, 예상 사용 빈도 및 관리자 상담을 원하는 경우 연락 방법을 보내 주세요.",
        "support_lead_custom_title": "맞춤 봇 상담", "support_lead_custom_body": "주요 요구, 사용 규모, 자동화할 업무 흐름 및 편리한 연락 방법을 설명해 주세요.",
        "support_input_one_message": "답변은 한 메시지로 보내 주세요.",
    },
    "hi": {
        "support_detail_title": "कस्टम बॉट परामर्श", "support_detail_body": "TOAN AAS आपके लक्ष्यों और कार्यप्रवाह के अनुरूप बॉट के बारे में सलाह दे सकता है।", "support_detail_questions": "कृपया बताएं:",
        "support_detail_enter_need": "आवश्यकता लिखें", "support_detail_create_lead": "परामर्श अनुरोध बनाएं", "support_detail_back_bot": "कस्टम बॉट परामर्श",
        "support_consult_detail_title": "सेवा परामर्श", "support_consult_detail_intro": "TOAN AAS इसमें सहायता कर सकता है:", "support_consult_detail_input": "अपनी आवश्यकता लिखें", "support_consult_detail_ticket": "परामर्श टिकट बनाएं", "support_consult_detail_premium": "Premium लें", "support_consult_detail_back": "सेवा परामर्श",
        "support_lead_premium_title": "Premium लें", "support_lead_premium_body": "TOAN AAS के उपयोग का उद्देश्य, मुख्य जरूरतें, अनुमानित उपयोग आवृत्ति और एडमिन सलाह चाहने पर संपर्क माध्यम भेजें।",
        "support_lead_custom_title": "कस्टम बॉट परामर्श", "support_lead_custom_body": "अपनी मुख्य जरूरत, उपयोग का स्तर, स्वचालित करने वाला कार्यप्रवाह और सुविधाजनक संपर्क माध्यम बताएं।",
        "support_input_one_message": "अपना उत्तर एक संदेश में भेजें।",
    },
    "ar": {
        "support_detail_title": "استشارة بوت مخصص", "support_detail_body": "يمكن لـ TOAN AAS تقديم المشورة حول بوت يناسب أهدافك وسير عملك.", "support_detail_questions": "يرجى توضيح:",
        "support_detail_enter_need": "أدخل الاحتياج", "support_detail_create_lead": "إنشاء طلب استشارة", "support_detail_back_bot": "استشارة بوت مخصص",
        "support_consult_detail_title": "استشارة خدمة", "support_consult_detail_intro": "يمكن لـ TOAN AAS المساعدة في:", "support_consult_detail_input": "أدخل احتياجاً مخصصاً", "support_consult_detail_ticket": "إنشاء تذكرة استشارة", "support_consult_detail_premium": "الاشتراك في Premium", "support_consult_detail_back": "استشارة خدمة",
        "support_lead_premium_title": "الاشتراك في Premium", "support_lead_premium_body": "أرسل هدفك من استخدام TOAN AAS واحتياجاتك الرئيسية وتكرار الاستخدام المتوقع وطريقة الاتصال إذا رغبت باستشارة من المشرف.",
        "support_lead_custom_title": "استشارة بوت مخصص", "support_lead_custom_body": "صف احتياجك الرئيسي وحجم الاستخدام وسير العمل الذي تريد أتمتته وطريقة اتصال مناسبة.",
        "support_input_one_message": "أرسل إجابتك في رسالة واحدة.",
    },
    "ru": {
        "support_detail_title": "Консультация по своему боту", "support_detail_body": "TOAN AAS может посоветовать бота под ваши цели и рабочий процесс.", "support_detail_questions": "Опишите, пожалуйста:",
        "support_detail_enter_need": "Указать потребность", "support_detail_create_lead": "Создать запрос на консультацию", "support_detail_back_bot": "Консультация по своему боту",
        "support_consult_detail_title": "Консультация по услуге", "support_consult_detail_intro": "TOAN AAS может помочь с:", "support_consult_detail_input": "Указать свой запрос", "support_consult_detail_ticket": "Создать консультационное обращение", "support_consult_detail_premium": "Оформить Premium", "support_consult_detail_back": "Консультация по услуге",
        "support_lead_premium_title": "Оформить Premium", "support_lead_premium_body": "Отправьте цель использования TOAN AAS, основные потребности, предполагаемую частоту и удобный способ связи, если хотите консультацию администратора.",
        "support_lead_custom_title": "Консультация по своему боту", "support_lead_custom_body": "Опишите основную потребность, масштаб использования, процесс для автоматизации и удобный способ связи.",
        "support_input_one_message": "Отправьте ответ одним сообщением.",
    },
    "tr": {
        "support_detail_title": "Özel bot danışmanlığı", "support_detail_body": "TOAN AAS, hedeflerinize ve iş akışınıza uygun bir bot için danışmanlık verebilir.", "support_detail_questions": "Lütfen şunları açıklayın:",
        "support_detail_enter_need": "İhtiyacı girin", "support_detail_create_lead": "Danışmanlık talebi oluştur", "support_detail_back_bot": "Özel bot danışmanlığı",
        "support_consult_detail_title": "Hizmet danışmanlığı", "support_consult_detail_intro": "TOAN AAS şu konularda yardımcı olabilir:", "support_consult_detail_input": "Özel ihtiyacı girin", "support_consult_detail_ticket": "Danışmanlık talebi oluştur", "support_consult_detail_premium": "Premium'a katıl", "support_consult_detail_back": "Hizmet danışmanlığı",
        "support_lead_premium_title": "Premium'a katıl", "support_lead_premium_body": "TOAN AAS kullanım amacınızı, ana ihtiyaçlarınızı, beklenen kullanım sıklığını ve yönetici danışmanlığı isterseniz iletişim yolunuzu gönderin.",
        "support_lead_custom_title": "Özel bot danışmanlığı", "support_lead_custom_body": "Ana ihtiyacınızı, kullanım ölçeğini, otomatikleştirmek istediğiniz iş akışını ve uygun iletişim yolunu açıklayın.",
        "support_input_one_message": "Yanıtınızı tek bir mesajda gönderin.",
    },
    "th": {
        "support_detail_title": "ปรึกษาบอตแบบกำหนดเอง", "support_detail_body": "TOAN AAS สามารถให้คำแนะนำเกี่ยวกับบอตที่เหมาะกับเป้าหมายและเวิร์กโฟลว์ของคุณ", "support_detail_questions": "โปรดอธิบาย:",
        "support_detail_enter_need": "ระบุความต้องการ", "support_detail_create_lead": "สร้างคำขอปรึกษา", "support_detail_back_bot": "ปรึกษาบอตแบบกำหนดเอง",
        "support_consult_detail_title": "ปรึกษาบริการ", "support_consult_detail_intro": "TOAN AAS สามารถช่วยเรื่อง:", "support_consult_detail_input": "ระบุความต้องการเอง", "support_consult_detail_ticket": "สร้างทิกเก็ตปรึกษา", "support_consult_detail_premium": "สมัคร Premium", "support_consult_detail_back": "ปรึกษาบริการ",
        "support_lead_premium_title": "สมัคร Premium", "support_lead_premium_body": "ส่งวัตถุประสงค์การใช้ TOAN AAS ความต้องการหลัก ความถี่ที่คาดไว้ และวิธีติดต่อหากต้องการคำปรึกษาจากผู้ดูแล",
        "support_lead_custom_title": "ปรึกษาบอตแบบกำหนดเอง", "support_lead_custom_body": "อธิบายความต้องการหลัก ขนาดการใช้งาน เวิร์กโฟลว์ที่ต้องการทำอัตโนมัติ และวิธีติดต่อที่สะดวก",
        "support_input_one_message": "ส่งคำตอบของคุณในข้อความเดียว",
    },
    "fil": {
        "support_detail_title": "Konsultasyon sa custom bot", "support_detail_body": "Makakapagpayo ang TOAN AAS tungkol sa bot na angkop sa iyong layunin at daloy ng trabaho.", "support_detail_questions": "Pakilarawan:",
        "support_detail_enter_need": "Ilagay ang pangangailangan", "support_detail_create_lead": "Gumawa ng kahilingan sa konsultasyon", "support_detail_back_bot": "Konsultasyon sa custom bot",
        "support_consult_detail_title": "Konsultasyon sa serbisyo", "support_consult_detail_intro": "Makakatulong ang TOAN AAS sa:", "support_consult_detail_input": "Ilagay ang sariling pangangailangan", "support_consult_detail_ticket": "Gumawa ng ticket sa konsultasyon", "support_consult_detail_premium": "Sumali sa Premium", "support_consult_detail_back": "Konsultasyon sa serbisyo",
        "support_lead_premium_title": "Sumali sa Premium", "support_lead_premium_body": "Ipadala ang layunin ng paggamit sa TOAN AAS, pangunahing pangangailangan, inaasahang dalas at paraan ng pakikipag-ugnayan kung gusto mo ng konsultasyon mula sa admin.",
        "support_lead_custom_title": "Konsultasyon sa custom bot", "support_lead_custom_body": "Ilarawan ang pangunahing pangangailangan, lawak ng paggamit, prosesong nais i-automate at maginhawang paraan ng pakikipag-ugnayan.",
        "support_input_one_message": "Ipadala ang sagot sa isang mensahe.",
    },
    "it": {
        "support_detail_title": "Consulenza per bot personalizzato", "support_detail_body": "TOAN AAS può consigliare un bot adatto ai tuoi obiettivi e al tuo flusso di lavoro.", "support_detail_questions": "Descrivi, per favore:",
        "support_detail_enter_need": "Inserisci esigenza", "support_detail_create_lead": "Crea richiesta di consulenza", "support_detail_back_bot": "Consulenza per bot personalizzato",
        "support_consult_detail_title": "Consulenza di servizio", "support_consult_detail_intro": "TOAN AAS può aiutarti con:", "support_consult_detail_input": "Inserisci esigenza personalizzata", "support_consult_detail_ticket": "Crea ticket di consulenza", "support_consult_detail_premium": "Iscriviti a Premium", "support_consult_detail_back": "Consulenza di servizio",
        "support_lead_premium_title": "Iscriviti a Premium", "support_lead_premium_body": "Invia lo scopo d’uso di TOAN AAS, le esigenze principali, la frequenza prevista e un contatto se desideri la consulenza dell’amministratore.",
        "support_lead_custom_title": "Consulenza per bot personalizzato", "support_lead_custom_body": "Descrivi l’esigenza principale, la scala d’uso, il flusso da automatizzare e un contatto comodo.",
        "support_input_one_message": "Invia la risposta in un solo messaggio.",
    },
    "id": {
        "support_detail_title": "Konsultasi bot khusus", "support_detail_body": "TOAN AAS dapat memberi saran tentang bot yang sesuai dengan tujuan dan alur kerja Anda.", "support_detail_questions": "Jelaskan, silakan:",
        "support_detail_enter_need": "Masukkan kebutuhan", "support_detail_create_lead": "Buat permintaan konsultasi", "support_detail_back_bot": "Konsultasi bot khusus",
        "support_consult_detail_title": "Konsultasi layanan", "support_consult_detail_intro": "TOAN AAS dapat membantu dengan:", "support_consult_detail_input": "Masukkan kebutuhan khusus", "support_consult_detail_ticket": "Buat tiket konsultasi", "support_consult_detail_premium": "Gabung Premium", "support_consult_detail_back": "Konsultasi layanan",
        "support_lead_premium_title": "Gabung Premium", "support_lead_premium_body": "Kirim tujuan penggunaan TOAN AAS, kebutuhan utama, frekuensi yang diharapkan, dan cara kontak jika Anda ingin konsultasi dengan admin.",
        "support_lead_custom_title": "Konsultasi bot khusus", "support_lead_custom_body": "Jelaskan kebutuhan utama, skala penggunaan, alur kerja yang ingin diotomatisasi, dan cara kontak yang nyaman.",
        "support_input_one_message": "Kirim jawaban Anda dalam satu pesan.",
    },
}


# Ticket presentation is intentionally kept separate from the ticket domain
# module.  The values below are customer-facing wording only: category/status
# codes, callbacks and stored ticket data stay canonical in the runtime.
_PUBLIC_SUPPORT_TICKET_COPY = {
    "vi": {
        "support_ticket_ack": "TOAN AAS đã nhận yêu cầu hỗ trợ của bạn.", "support_ticket_received_notice": "Admin sẽ kiểm tra và phản hồi sớm nhất có thể.",
        "support_ticket_label_code": "Mã ticket", "support_ticket_label_category": "Nhóm vấn đề", "support_ticket_label_status": "Trạng thái", "support_ticket_label_priority": "Ưu tiên", "support_ticket_label_time": "Thời gian", "support_ticket_label_latest_message": "Nội dung gần nhất", "support_ticket_label_latest_reply": "Phản hồi mới nhất",
        "support_ticket_list_empty": "Bạn chưa có ticket hỗ trợ nào. Bạn có thể tạo ticket mới nếu cần TOAN AAS hỗ trợ riêng.", "support_ticket_list_recent": "Các yêu cầu hỗ trợ gần đây:", "support_ticket_attachment_present": "Đã có file đính kèm.",
        "support_ticket_view_current": "Xem ticket này", "support_ticket_add_message": "Gửi thêm nội dung", "support_ticket_add_attachment": "Gửi thêm ảnh/file", "support_ticket_mark_done": "Đánh dấu đã xong", "support_ticket_back_to_ticket": "Ticket",
        "support_ticket_message_too_short": "Vui lòng mô tả rõ hơn để admin có đủ thông tin kiểm tra.", "support_ticket_reply_too_short": "Vui lòng nhập nội dung cần bổ sung.", "support_ticket_not_found": "Không tìm thấy ticket của bạn. Vui lòng mở lại mục Ticket của tôi.", "support_ticket_reply_prompt": "Nhập nội dung cần bổ sung. TOAN AAS sẽ lưu vào đúng ticket này.",
        "support_ticket_done_success": "đã được đánh dấu đã xong.", "support_ticket_attachment_prompt": "Gửi một ảnh chụp màn hình hoặc file cho ticket này. Nên gửi từng file một để tránh lỗi.", "support_ticket_attachment_success": "Đã lưu file vào ticket. Admin sẽ dùng file này để kiểm tra yêu cầu.", "support_ticket_attachment_need_media": "Vui lòng gửi một ảnh hoặc file tài liệu. Nếu không cần đính kèm, bạn có thể mở ticket khác hoặc về Menu chính.",
        "support_ticket_action_unsupported": "Thao tác ticket chưa được hỗ trợ.", "support_ticket_append_success": "Đã bổ sung thông tin vào ticket.", "support_ticket_append_notice": "TOAN AAS giữ cùng ticket để admin theo dõi liền mạch.", "support_ticket_feedback_notice": "Cảm ơn bạn. TOAN AAS đã tạo ticket góp ý/báo lỗi. Admin sẽ kiểm tra nội dung. Bot chưa gọi AI/API, chưa trừ và chưa tự hoàn Xu.", "support_ticket_lead_hint": "Ví dụ: tạo ảnh sản phẩm, video quảng cáo, content affiliate, bot tự động hóa hoặc gói doanh nghiệp.", "support_ticket_admin_only": "Khu vực này chỉ dành cho Admin.",
    },
    "en": {
        "support_ticket_ack": "TOAN AAS has received your support request.", "support_ticket_received_notice": "An admin will review it and reply as soon as possible.",
        "support_ticket_label_code": "Ticket", "support_ticket_label_category": "Category", "support_ticket_label_status": "Status", "support_ticket_label_priority": "Priority", "support_ticket_label_time": "Time", "support_ticket_label_latest_message": "Latest message", "support_ticket_label_latest_reply": "Latest reply",
        "support_ticket_list_empty": "You do not have any support tickets yet. Create a new ticket whenever you need individual help from TOAN AAS.", "support_ticket_list_recent": "Your recent support requests:", "support_ticket_attachment_present": "An attachment has been added.",
        "support_ticket_view_current": "View this ticket", "support_ticket_add_message": "Add a message", "support_ticket_add_attachment": "Add image/file", "support_ticket_mark_done": "Mark as done", "support_ticket_back_to_ticket": "Ticket",
        "support_ticket_message_too_short": "Please describe the issue in a little more detail so an admin can check it.", "support_ticket_reply_too_short": "Please enter the information you want to add.", "support_ticket_not_found": "Your ticket could not be found. Please open My tickets again.", "support_ticket_reply_prompt": "Enter the information you want to add. TOAN AAS will save it in this ticket.",
        "support_ticket_done_success": "has been marked as done.", "support_ticket_attachment_prompt": "Send a screenshot or file for this ticket. Sending one file at a time helps avoid errors.", "support_ticket_attachment_success": "The file was saved to the ticket. An admin will use it to review your request.", "support_ticket_attachment_need_media": "Please send an image or document file. If you do not need an attachment, you can open another ticket or return to the main menu.",
        "support_ticket_action_unsupported": "This ticket action is not supported.", "support_ticket_append_success": "Information has been added to the ticket.", "support_ticket_append_notice": "TOAN AAS will keep this in the same ticket so an admin can follow it continuously.", "support_ticket_feedback_notice": "Thank you. TOAN AAS has created a feedback or issue ticket. An admin will review it. The bot has not called AI/API, charged Xu, or issued an automatic Xu refund.", "support_ticket_lead_hint": "For example: product images, advertising video, affiliate content, workflow automation, or an enterprise package.", "support_ticket_admin_only": "This area is for admins only.",
    },
    "zh": {
        "support_ticket_ack": "TOAN AAS 已收到您的支持请求。", "support_ticket_received_notice": "管理员会尽快核查并回复。",
        "support_ticket_label_code": "工单编号", "support_ticket_label_category": "问题类别", "support_ticket_label_status": "状态", "support_ticket_label_priority": "优先级", "support_ticket_label_time": "时间", "support_ticket_label_latest_message": "最新内容", "support_ticket_label_latest_reply": "最新回复",
        "support_ticket_list_empty": "您还没有支持工单。如需 TOAN AAS 提供专属帮助，可以创建新工单。", "support_ticket_list_recent": "最近的支持请求：", "support_ticket_attachment_present": "已添加附件。",
        "support_ticket_view_current": "查看此工单", "support_ticket_add_message": "补充内容", "support_ticket_add_attachment": "添加图片/文件", "support_ticket_mark_done": "标记为完成", "support_ticket_back_to_ticket": "工单",
        "support_ticket_message_too_short": "请更详细地描述问题，以便管理员核查。", "support_ticket_reply_too_short": "请输入要补充的内容。", "support_ticket_not_found": "未找到您的工单。请重新打开“我的工单”。", "support_ticket_reply_prompt": "请输入要补充的内容。TOAN AAS 会保存到此工单中。",
        "support_ticket_done_success": "已标记为完成。", "support_ticket_attachment_prompt": "请为此工单发送截图或文件。一次发送一个文件可减少错误。", "support_ticket_attachment_success": "文件已保存到工单。管理员将用它核查您的请求。", "support_ticket_attachment_need_media": "请发送图片或文档文件。如无需附件，您可以创建其他工单或返回主菜单。",
        "support_ticket_action_unsupported": "不支持此工单操作。", "support_ticket_append_success": "信息已补充到工单。", "support_ticket_append_notice": "TOAN AAS 会保留在同一工单中，方便管理员连续跟进。", "support_ticket_feedback_notice": "谢谢。TOAN AAS 已创建反馈或问题工单。管理员会核查内容。机器人未调用 AI/API、未扣除 Xu，也不会自动退款 Xu。", "support_ticket_lead_hint": "例如：产品图片、广告视频、联盟内容、自动化流程或企业套餐。", "support_ticket_admin_only": "此区域仅限管理员使用。",
    },
    "es": {
        "support_ticket_ack": "TOAN AAS ha recibido tu solicitud de ayuda.", "support_ticket_received_notice": "Un administrador la revisará y responderá lo antes posible.",
        "support_ticket_label_code": "Ticket", "support_ticket_label_category": "Categoría", "support_ticket_label_status": "Estado", "support_ticket_label_priority": "Prioridad", "support_ticket_label_time": "Hora", "support_ticket_label_latest_message": "Mensaje más reciente", "support_ticket_label_latest_reply": "Respuesta más reciente",
        "support_ticket_list_empty": "Aún no tienes tickets de ayuda. Puedes crear uno nuevo cuando necesites ayuda personalizada de TOAN AAS.", "support_ticket_list_recent": "Tus solicitudes de ayuda recientes:", "support_ticket_attachment_present": "Se añadió un archivo adjunto.",
        "support_ticket_view_current": "Ver este ticket", "support_ticket_add_message": "Añadir mensaje", "support_ticket_add_attachment": "Añadir imagen/archivo", "support_ticket_mark_done": "Marcar como resuelto", "support_ticket_back_to_ticket": "Ticket",
        "support_ticket_message_too_short": "Describe el problema con un poco más de detalle para que el administrador pueda revisarlo.", "support_ticket_reply_too_short": "Escribe la información que deseas añadir.", "support_ticket_not_found": "No se encontró tu ticket. Abre de nuevo Mis tickets.", "support_ticket_reply_prompt": "Escribe la información que deseas añadir. TOAN AAS la guardará en este ticket.",
        "support_ticket_done_success": "se ha marcado como resuelto.", "support_ticket_attachment_prompt": "Envía una captura o un archivo para este ticket. Enviar un archivo cada vez ayuda a evitar errores.", "support_ticket_attachment_success": "El archivo se guardó en el ticket. Un administrador lo usará para revisar tu solicitud.", "support_ticket_attachment_need_media": "Envía una imagen o un documento. Si no necesitas adjuntar nada, puedes abrir otro ticket o volver al menú principal.",
        "support_ticket_action_unsupported": "Esta acción del ticket no es compatible.", "support_ticket_append_success": "La información se añadió al ticket.", "support_ticket_append_notice": "TOAN AAS mantendrá todo en el mismo ticket para que el administrador pueda seguirlo sin interrupciones.", "support_ticket_feedback_notice": "Gracias. TOAN AAS ha creado un ticket de comentarios o incidencia. Un administrador revisará el contenido. El bot no ha llamado a IA/API, no ha cobrado Xu ni ha emitido un reembolso automático de Xu.", "support_ticket_lead_hint": "Por ejemplo: imágenes de producto, vídeo publicitario, contenido de afiliados, automatización o un paquete empresarial.", "support_ticket_admin_only": "Esta sección es solo para administradores.",
    },
    "pt": {
        "support_ticket_ack": "TOAN AAS recebeu sua solicitação de suporte.", "support_ticket_received_notice": "Um administrador vai analisar e responder o mais breve possível.",
        "support_ticket_label_code": "Ticket", "support_ticket_label_category": "Categoria", "support_ticket_label_status": "Status", "support_ticket_label_priority": "Prioridade", "support_ticket_label_time": "Horário", "support_ticket_label_latest_message": "Mensagem mais recente", "support_ticket_label_latest_reply": "Resposta mais recente",
        "support_ticket_list_empty": "Você ainda não tem tickets de suporte. Crie um novo ticket quando precisar de ajuda personalizada da TOAN AAS.", "support_ticket_list_recent": "Suas solicitações de suporte recentes:", "support_ticket_attachment_present": "Um anexo foi adicionado.",
        "support_ticket_view_current": "Ver este ticket", "support_ticket_add_message": "Adicionar mensagem", "support_ticket_add_attachment": "Adicionar imagem/arquivo", "support_ticket_mark_done": "Marcar como concluído", "support_ticket_back_to_ticket": "Ticket",
        "support_ticket_message_too_short": "Descreva o problema com mais detalhes para que o administrador possa analisá-lo.", "support_ticket_reply_too_short": "Digite a informação que deseja adicionar.", "support_ticket_not_found": "Seu ticket não foi encontrado. Abra Meus tickets novamente.", "support_ticket_reply_prompt": "Digite a informação que deseja adicionar. A TOAN AAS a salvará neste ticket.",
        "support_ticket_done_success": "foi marcado como concluído.", "support_ticket_attachment_prompt": "Envie uma captura de tela ou arquivo para este ticket. Enviar um arquivo por vez ajuda a evitar erros.", "support_ticket_attachment_success": "O arquivo foi salvo no ticket. Um administrador o usará para analisar sua solicitação.", "support_ticket_attachment_need_media": "Envie uma imagem ou documento. Se não precisar anexar nada, você pode abrir outro ticket ou voltar ao menu principal.",
        "support_ticket_action_unsupported": "Esta ação de ticket não é compatível.", "support_ticket_append_success": "A informação foi adicionada ao ticket.", "support_ticket_append_notice": "A TOAN AAS manterá tudo no mesmo ticket para que o administrador possa acompanhar continuamente.", "support_ticket_feedback_notice": "Obrigado. A TOAN AAS criou um ticket de comentário ou problema. Um administrador analisará o conteúdo. O bot não chamou IA/API, não cobrou Xu e não emitiu reembolso automático de Xu.", "support_ticket_lead_hint": "Por exemplo: imagens de produto, vídeo publicitário, conteúdo de afiliado, automação ou pacote empresarial.", "support_ticket_admin_only": "Esta área é apenas para administradores.",
    },
    "fr": {
        "support_ticket_ack": "TOAN AAS a bien reçu votre demande d’assistance.", "support_ticket_received_notice": "Un administrateur la vérifiera et répondra dès que possible.",
        "support_ticket_label_code": "Ticket", "support_ticket_label_category": "Catégorie", "support_ticket_label_status": "Statut", "support_ticket_label_priority": "Priorité", "support_ticket_label_time": "Heure", "support_ticket_label_latest_message": "Dernier message", "support_ticket_label_latest_reply": "Dernière réponse",
        "support_ticket_list_empty": "Vous n’avez pas encore de ticket d’assistance. Créez-en un lorsque vous avez besoin d’une aide personnalisée de TOAN AAS.", "support_ticket_list_recent": "Vos demandes d’assistance récentes :", "support_ticket_attachment_present": "Une pièce jointe a été ajoutée.",
        "support_ticket_view_current": "Voir ce ticket", "support_ticket_add_message": "Ajouter un message", "support_ticket_add_attachment": "Ajouter image/fichier", "support_ticket_mark_done": "Marquer comme résolu", "support_ticket_back_to_ticket": "Ticket",
        "support_ticket_message_too_short": "Décrivez le problème plus en détail afin que l’administrateur puisse le vérifier.", "support_ticket_reply_too_short": "Saisissez les informations à ajouter.", "support_ticket_not_found": "Votre ticket est introuvable. Ouvrez de nouveau Mes tickets.", "support_ticket_reply_prompt": "Saisissez les informations à ajouter. TOAN AAS les enregistrera dans ce ticket.",
        "support_ticket_done_success": "a été marqué comme résolu.", "support_ticket_attachment_prompt": "Envoyez une capture d’écran ou un fichier pour ce ticket. Envoyer un fichier à la fois limite les erreurs.", "support_ticket_attachment_success": "Le fichier a été enregistré dans le ticket. Un administrateur l’utilisera pour vérifier votre demande.", "support_ticket_attachment_need_media": "Envoyez une image ou un document. Si vous n’avez pas de pièce jointe, vous pouvez créer un autre ticket ou revenir au menu principal.",
        "support_ticket_action_unsupported": "Cette action de ticket n’est pas prise en charge.", "support_ticket_append_success": "Les informations ont été ajoutées au ticket.", "support_ticket_append_notice": "TOAN AAS conservera tout dans le même ticket afin que l’administrateur puisse le suivre sans interruption.", "support_ticket_feedback_notice": "Merci. TOAN AAS a créé un ticket de commentaire ou de problème. Un administrateur examinera le contenu. Le bot n’a appelé ni IA/API, ni débité de Xu, ni accordé de remboursement Xu automatique.", "support_ticket_lead_hint": "Par exemple : images produit, vidéo publicitaire, contenu affilié, automatisation ou forfait entreprise.", "support_ticket_admin_only": "Cette zone est réservée aux administrateurs.",
    },
    "de": {
        "support_ticket_ack": "TOAN AAS hat deine Supportanfrage erhalten.", "support_ticket_received_notice": "Ein Admin wird sie prüfen und so bald wie möglich antworten.",
        "support_ticket_label_code": "Ticket", "support_ticket_label_category": "Kategorie", "support_ticket_label_status": "Status", "support_ticket_label_priority": "Priorität", "support_ticket_label_time": "Zeit", "support_ticket_label_latest_message": "Neueste Nachricht", "support_ticket_label_latest_reply": "Neueste Antwort",
        "support_ticket_list_empty": "Du hast noch keine Support-Tickets. Erstelle ein neues Ticket, wenn du individuelle Hilfe von TOAN AAS brauchst.", "support_ticket_list_recent": "Deine letzten Supportanfragen:", "support_ticket_attachment_present": "Ein Anhang wurde hinzugefügt.",
        "support_ticket_view_current": "Dieses Ticket ansehen", "support_ticket_add_message": "Nachricht hinzufügen", "support_ticket_add_attachment": "Bild/Datei hinzufügen", "support_ticket_mark_done": "Als erledigt markieren", "support_ticket_back_to_ticket": "Ticket",
        "support_ticket_message_too_short": "Bitte beschreibe das Problem genauer, damit ein Admin es prüfen kann.", "support_ticket_reply_too_short": "Bitte gib die Informationen ein, die du ergänzen möchtest.", "support_ticket_not_found": "Dein Ticket wurde nicht gefunden. Öffne Meine Tickets erneut.", "support_ticket_reply_prompt": "Gib die Informationen ein, die du ergänzen möchtest. TOAN AAS speichert sie in diesem Ticket.",
        "support_ticket_done_success": "wurde als erledigt markiert.", "support_ticket_attachment_prompt": "Sende einen Screenshot oder eine Datei für dieses Ticket. Eine Datei pro Nachricht hilft, Fehler zu vermeiden.", "support_ticket_attachment_success": "Die Datei wurde im Ticket gespeichert. Ein Admin verwendet sie zur Prüfung deiner Anfrage.", "support_ticket_attachment_need_media": "Bitte sende ein Bild oder ein Dokument. Wenn du keinen Anhang brauchst, kannst du ein anderes Ticket öffnen oder zum Hauptmenü zurückkehren.",
        "support_ticket_action_unsupported": "Diese Ticketaktion wird nicht unterstützt.", "support_ticket_append_success": "Die Informationen wurden zum Ticket hinzugefügt.", "support_ticket_append_notice": "TOAN AAS behält alles im selben Ticket, damit ein Admin es lückenlos verfolgen kann.", "support_ticket_feedback_notice": "Danke. TOAN AAS hat ein Feedback- oder Problem-Ticket erstellt. Ein Admin prüft den Inhalt. Der Bot hat keine KI/API aufgerufen, keine Xu belastet und keine automatische Xu-Erstattung ausgeführt.", "support_ticket_lead_hint": "Zum Beispiel: Produktbilder, Werbevideo, Affiliate-Inhalte, Automatisierung oder ein Unternehmenspaket.", "support_ticket_admin_only": "Dieser Bereich ist nur für Admins.",
    },
    "ja": {
        "support_ticket_ack": "TOAN AAS はサポートのご依頼を受け取りました。", "support_ticket_received_notice": "管理者が確認し、できるだけ早く返信します。",
        "support_ticket_label_code": "チケット番号", "support_ticket_label_category": "カテゴリ", "support_ticket_label_status": "状態", "support_ticket_label_priority": "優先度", "support_ticket_label_time": "日時", "support_ticket_label_latest_message": "最新メッセージ", "support_ticket_label_latest_reply": "最新の返信",
        "support_ticket_list_empty": "サポートチケットはまだありません。TOAN AAS の個別サポートが必要なときは新しいチケットを作成できます。", "support_ticket_list_recent": "最近のサポート依頼：", "support_ticket_attachment_present": "添付ファイルがあります。",
        "support_ticket_view_current": "このチケットを見る", "support_ticket_add_message": "内容を追加", "support_ticket_add_attachment": "画像/ファイルを追加", "support_ticket_mark_done": "完了にする", "support_ticket_back_to_ticket": "チケット",
        "support_ticket_message_too_short": "管理者が確認できるよう、問題をもう少し詳しく説明してください。", "support_ticket_reply_too_short": "追加したい内容を入力してください。", "support_ticket_not_found": "チケットが見つかりません。もう一度マイチケットを開いてください。", "support_ticket_reply_prompt": "追加したい内容を入力してください。TOAN AAS がこのチケットに保存します。",
        "support_ticket_done_success": "を完了としてマークしました。", "support_ticket_attachment_prompt": "このチケット用のスクリーンショットまたはファイルを送信してください。1回に1ファイルずつ送るとエラーを防げます。", "support_ticket_attachment_success": "ファイルをチケットに保存しました。管理者が依頼の確認に使用します。", "support_ticket_attachment_need_media": "画像または文書ファイルを送信してください。添付が不要な場合は、別のチケットを作成するかメインメニューに戻れます。",
        "support_ticket_action_unsupported": "このチケット操作には対応していません。", "support_ticket_append_success": "チケットに情報を追加しました。", "support_ticket_append_notice": "管理者が継続して確認できるよう、TOAN AAS は同じチケットにまとめます。", "support_ticket_feedback_notice": "ありがとうございます。TOAN AAS はフィードバックまたは問題のチケットを作成しました。管理者が内容を確認します。ボットは AI/API を呼び出しておらず、Xu の請求や自動返金も行っていません。", "support_ticket_lead_hint": "例：商品画像、広告動画、アフィリエイト用コンテンツ、自動化、企業向けパッケージ。", "support_ticket_admin_only": "この画面は管理者専用です。",
    },
    "ko": {
        "support_ticket_ack": "TOAN AAS가 지원 요청을 접수했습니다.", "support_ticket_received_notice": "관리자가 검토한 뒤 가능한 한 빨리 답변드립니다.",
        "support_ticket_label_code": "티켓 번호", "support_ticket_label_category": "분류", "support_ticket_label_status": "상태", "support_ticket_label_priority": "우선순위", "support_ticket_label_time": "시간", "support_ticket_label_latest_message": "최근 메시지", "support_ticket_label_latest_reply": "최근 답변",
        "support_ticket_list_empty": "아직 지원 티켓이 없습니다. TOAN AAS의 개별 도움이 필요하면 새 티켓을 만들 수 있습니다.", "support_ticket_list_recent": "최근 지원 요청:", "support_ticket_attachment_present": "첨부 파일이 추가되었습니다.",
        "support_ticket_view_current": "이 티켓 보기", "support_ticket_add_message": "내용 추가", "support_ticket_add_attachment": "이미지/파일 추가", "support_ticket_mark_done": "완료로 표시", "support_ticket_back_to_ticket": "티켓",
        "support_ticket_message_too_short": "관리자가 확인할 수 있도록 문제를 조금 더 자세히 설명해 주세요.", "support_ticket_reply_too_short": "추가할 내용을 입력해 주세요.", "support_ticket_not_found": "티켓을 찾을 수 없습니다. 내 티켓을 다시 열어 주세요.", "support_ticket_reply_prompt": "추가할 내용을 입력해 주세요. TOAN AAS가 이 티켓에 저장합니다.",
        "support_ticket_done_success": "이 완료로 표시되었습니다.", "support_ticket_attachment_prompt": "이 티켓에 대한 스크린샷 또는 파일을 보내 주세요. 한 번에 하나의 파일을 보내면 오류를 줄일 수 있습니다.", "support_ticket_attachment_success": "파일이 티켓에 저장되었습니다. 관리자가 요청을 검토하는 데 사용합니다.", "support_ticket_attachment_need_media": "이미지 또는 문서 파일을 보내 주세요. 첨부가 필요 없다면 다른 티켓을 만들거나 메인 메뉴로 돌아갈 수 있습니다.",
        "support_ticket_action_unsupported": "이 티켓 작업은 지원되지 않습니다.", "support_ticket_append_success": "정보가 티켓에 추가되었습니다.", "support_ticket_append_notice": "관리자가 끊김 없이 확인할 수 있도록 TOAN AAS는 같은 티켓에 보관합니다.", "support_ticket_feedback_notice": "감사합니다. TOAN AAS가 의견 또는 문제 티켓을 만들었습니다. 관리자가 내용을 검토합니다. 봇은 AI/API를 호출하지 않았고 Xu를 차감하거나 자동 환불하지 않았습니다.", "support_ticket_lead_hint": "예: 상품 이미지, 광고 동영상, 제휴 콘텐츠, 자동화 또는 기업 패키지.", "support_ticket_admin_only": "이 영역은 관리자 전용입니다.",
    },
    "hi": {
        "support_ticket_ack": "TOAN AAS ने आपका सहायता अनुरोध प्राप्त कर लिया है।", "support_ticket_received_notice": "एडमिन इसकी जाँच कर जल्द से जल्द उत्तर देंगे।",
        "support_ticket_label_code": "टिकट", "support_ticket_label_category": "श्रेणी", "support_ticket_label_status": "स्थिति", "support_ticket_label_priority": "प्राथमिकता", "support_ticket_label_time": "समय", "support_ticket_label_latest_message": "नवीनतम संदेश", "support_ticket_label_latest_reply": "नवीनतम उत्तर",
        "support_ticket_list_empty": "आपके पास अभी कोई सहायता टिकट नहीं है। TOAN AAS से व्यक्तिगत सहायता चाहिए तो नया टिकट बना सकते हैं।", "support_ticket_list_recent": "आपके हाल के सहायता अनुरोध:", "support_ticket_attachment_present": "एक संलग्नक जोड़ा गया है।",
        "support_ticket_view_current": "यह टिकट देखें", "support_ticket_add_message": "संदेश जोड़ें", "support_ticket_add_attachment": "चित्र/फ़ाइल जोड़ें", "support_ticket_mark_done": "पूर्ण चिह्नित करें", "support_ticket_back_to_ticket": "टिकट",
        "support_ticket_message_too_short": "एडमिन की जाँच के लिए कृपया समस्या को थोड़ा और विस्तार से लिखें।", "support_ticket_reply_too_short": "कृपया वह जानकारी लिखें जिसे आप जोड़ना चाहते हैं।", "support_ticket_not_found": "आपका टिकट नहीं मिला। कृपया मेरे टिकट फिर से खोलें।", "support_ticket_reply_prompt": "वह जानकारी लिखें जिसे आप जोड़ना चाहते हैं। TOAN AAS इसे इसी टिकट में सहेजेगा।",
        "support_ticket_done_success": "को पूर्ण के रूप में चिह्नित किया गया है।", "support_ticket_attachment_prompt": "इस टिकट के लिए स्क्रीनशॉट या फ़ाइल भेजें। एक बार में एक फ़ाइल भेजने से त्रुटियाँ कम होती हैं।", "support_ticket_attachment_success": "फ़ाइल टिकट में सहेज दी गई है। एडमिन इसका उपयोग आपके अनुरोध की जाँच के लिए करेंगे।", "support_ticket_attachment_need_media": "कृपया चित्र या दस्तावेज़ फ़ाइल भेजें। यदि संलग्नक नहीं चाहिए तो दूसरा टिकट खोलें या मुख्य मेनू पर लौटें।",
        "support_ticket_action_unsupported": "यह टिकट कार्रवाई समर्थित नहीं है।", "support_ticket_append_success": "जानकारी टिकट में जोड़ दी गई है।", "support_ticket_append_notice": "एडमिन लगातार देख सकें इसलिए TOAN AAS इसे उसी टिकट में रखेगा।", "support_ticket_feedback_notice": "धन्यवाद। TOAN AAS ने प्रतिक्रिया या समस्या टिकट बनाया है। एडमिन सामग्री की जाँच करेंगे। बॉट ने AI/API नहीं बुलाया, Xu नहीं काटा और Xu का स्वचालित रिफंड नहीं किया।", "support_ticket_lead_hint": "उदाहरण: उत्पाद चित्र, विज्ञापन वीडियो, संबद्ध सामग्री, स्वचालन या एंटरप्राइज़ पैकेज।", "support_ticket_admin_only": "यह क्षेत्र केवल एडमिन के लिए है।",
    },
    "ar": {
        "support_ticket_ack": "استلمت TOAN AAS طلب الدعم الخاص بك.", "support_ticket_received_notice": "سيراجعه المشرف ويرد في أقرب وقت ممكن.",
        "support_ticket_label_code": "التذكرة", "support_ticket_label_category": "الفئة", "support_ticket_label_status": "الحالة", "support_ticket_label_priority": "الأولوية", "support_ticket_label_time": "الوقت", "support_ticket_label_latest_message": "أحدث رسالة", "support_ticket_label_latest_reply": "أحدث رد",
        "support_ticket_list_empty": "ليس لديك تذاكر دعم بعد. يمكنك إنشاء تذكرة جديدة عندما تحتاج إلى مساعدة مخصصة من TOAN AAS.", "support_ticket_list_recent": "طلبات الدعم الأخيرة:", "support_ticket_attachment_present": "تمت إضافة مرفق.",
        "support_ticket_view_current": "عرض هذه التذكرة", "support_ticket_add_message": "إضافة رسالة", "support_ticket_add_attachment": "إضافة صورة/ملف", "support_ticket_mark_done": "وضع علامة مكتمل", "support_ticket_back_to_ticket": "التذكرة",
        "support_ticket_message_too_short": "يرجى وصف المشكلة بمزيد من التفاصيل حتى يتمكن المشرف من مراجعتها.", "support_ticket_reply_too_short": "يرجى إدخال المعلومات التي تريد إضافتها.", "support_ticket_not_found": "لم يتم العثور على تذكرتك. افتح تذاكري مرة أخرى.", "support_ticket_reply_prompt": "أدخل المعلومات التي تريد إضافتها. ستحفظها TOAN AAS في هذه التذكرة.",
        "support_ticket_done_success": "تم وضع علامة مكتمل عليها.", "support_ticket_attachment_prompt": "أرسل لقطة شاشة أو ملفًا لهذه التذكرة. يساعد إرسال ملف واحد في كل مرة على تجنب الأخطاء.", "support_ticket_attachment_success": "تم حفظ الملف في التذكرة. سيستخدمه المشرف لمراجعة طلبك.", "support_ticket_attachment_need_media": "يرجى إرسال صورة أو ملف مستند. إذا لم تحتج إلى مرفق، يمكنك فتح تذكرة أخرى أو العودة إلى القائمة الرئيسية.",
        "support_ticket_action_unsupported": "إجراء التذكرة هذا غير مدعوم.", "support_ticket_append_success": "تمت إضافة المعلومات إلى التذكرة.", "support_ticket_append_notice": "ستحتفظ TOAN AAS بكل شيء في التذكرة نفسها حتى يتمكن المشرف من المتابعة باستمرار.", "support_ticket_feedback_notice": "شكرًا لك. أنشأت TOAN AAS تذكرة ملاحظات أو مشكلة. سيراجع المشرف المحتوى. لم يستدعِ البوت AI/API، ولم يخصم Xu، ولم يصدر استرداد Xu تلقائيًا.", "support_ticket_lead_hint": "مثل: صور المنتجات أو فيديو إعلاني أو محتوى أفلييت أو أتمتة أو باقة للشركات.", "support_ticket_admin_only": "هذه المنطقة للمشرفين فقط.",
    },
    "ru": {
        "support_ticket_ack": "TOAN AAS получил ваш запрос в поддержку.", "support_ticket_received_notice": "Администратор проверит его и ответит как можно скорее.",
        "support_ticket_label_code": "Тикет", "support_ticket_label_category": "Категория", "support_ticket_label_status": "Статус", "support_ticket_label_priority": "Приоритет", "support_ticket_label_time": "Время", "support_ticket_label_latest_message": "Последнее сообщение", "support_ticket_label_latest_reply": "Последний ответ",
        "support_ticket_list_empty": "У вас пока нет обращений в поддержку. Создайте новое обращение, когда понадобится персональная помощь TOAN AAS.", "support_ticket_list_recent": "Ваши последние обращения:", "support_ticket_attachment_present": "Вложение добавлено.",
        "support_ticket_view_current": "Открыть тикет", "support_ticket_add_message": "Добавить сообщение", "support_ticket_add_attachment": "Добавить изображение/файл", "support_ticket_mark_done": "Отметить как решённое", "support_ticket_back_to_ticket": "Тикет",
        "support_ticket_message_too_short": "Опишите проблему подробнее, чтобы администратор мог её проверить.", "support_ticket_reply_too_short": "Введите информацию, которую хотите добавить.", "support_ticket_not_found": "Ваше обращение не найдено. Снова откройте Мои обращения.", "support_ticket_reply_prompt": "Введите информацию, которую хотите добавить. TOAN AAS сохранит её в этом обращении.",
        "support_ticket_done_success": "отмечено как решённое.", "support_ticket_attachment_prompt": "Отправьте скриншот или файл для этого обращения. Отправка одного файла за раз помогает избежать ошибок.", "support_ticket_attachment_success": "Файл сохранён в обращении. Администратор использует его для проверки запроса.", "support_ticket_attachment_need_media": "Отправьте изображение или документ. Если вложение не нужно, можно создать другое обращение или вернуться в главное меню.",
        "support_ticket_action_unsupported": "Это действие с обращением не поддерживается.", "support_ticket_append_success": "Информация добавлена к обращению.", "support_ticket_append_notice": "TOAN AAS сохранит всё в одном обращении, чтобы администратор мог непрерывно отслеживать его.", "support_ticket_feedback_notice": "Спасибо. TOAN AAS создал обращение по отзыву или проблеме. Администратор проверит содержание. Бот не вызывал ИИ/API, не списывал Xu и не делал автоматический возврат Xu.", "support_ticket_lead_hint": "Например: изображения товара, рекламное видео, партнёрский контент, автоматизация или корпоративный пакет.", "support_ticket_admin_only": "Этот раздел доступен только администраторам.",
    },
    "tr": {
        "support_ticket_ack": "TOAN AAS destek talebinizi aldı.", "support_ticket_received_notice": "Bir yönetici talebi inceleyip mümkün olan en kısa sürede yanıtlayacaktır.",
        "support_ticket_label_code": "Talep", "support_ticket_label_category": "Kategori", "support_ticket_label_status": "Durum", "support_ticket_label_priority": "Öncelik", "support_ticket_label_time": "Zaman", "support_ticket_label_latest_message": "Son mesaj", "support_ticket_label_latest_reply": "Son yanıt",
        "support_ticket_list_empty": "Henüz destek talebiniz yok. TOAN AAS'ten kişisel yardım gerektiğinde yeni bir talep oluşturabilirsiniz.", "support_ticket_list_recent": "Son destek talepleriniz:", "support_ticket_attachment_present": "Bir ek eklendi.",
        "support_ticket_view_current": "Bu talebi görüntüle", "support_ticket_add_message": "Mesaj ekle", "support_ticket_add_attachment": "Görsel/dosya ekle", "support_ticket_mark_done": "Tamamlandı olarak işaretle", "support_ticket_back_to_ticket": "Talep",
        "support_ticket_message_too_short": "Yöneticinin inceleyebilmesi için lütfen sorunu biraz daha ayrıntılı açıklayın.", "support_ticket_reply_too_short": "Lütfen eklemek istediğiniz bilgileri girin.", "support_ticket_not_found": "Talebiniz bulunamadı. Taleplerim bölümünü yeniden açın.", "support_ticket_reply_prompt": "Eklemek istediğiniz bilgileri girin. TOAN AAS bunları bu talepte saklar.",
        "support_ticket_done_success": "tamamlandı olarak işaretlendi.", "support_ticket_attachment_prompt": "Bu talep için ekran görüntüsü veya dosya gönderin. Her seferinde bir dosya göndermek hataları azaltır.", "support_ticket_attachment_success": "Dosya talebe kaydedildi. Bir yönetici isteğinizi incelemek için kullanacaktır.", "support_ticket_attachment_need_media": "Lütfen bir görsel veya belge dosyası gönderin. Ek gerekmiyorsa başka bir talep açabilir ya da ana menüye dönebilirsiniz.",
        "support_ticket_action_unsupported": "Bu talep işlemi desteklenmiyor.", "support_ticket_append_success": "Bilgi talebe eklendi.", "support_ticket_append_notice": "TOAN AAS, yöneticinin kesintisiz takip edebilmesi için her şeyi aynı talepte tutar.", "support_ticket_feedback_notice": "Teşekkür ederiz. TOAN AAS bir geri bildirim veya sorun talebi oluşturdu. Bir yönetici içeriği inceleyecektir. Bot AI/API çağırmadı, Xu kesmedi ve otomatik Xu iadesi yapmadı.", "support_ticket_lead_hint": "Örneğin: ürün görselleri, reklam videosu, ortaklık içeriği, otomasyon veya kurumsal paket.", "support_ticket_admin_only": "Bu alan yalnızca yöneticiler içindir.",
    },
    "th": {
        "support_ticket_ack": "TOAN AAS ได้รับคำขอความช่วยเหลือของคุณแล้ว", "support_ticket_received_notice": "ผู้ดูแลจะตรวจสอบและตอบกลับโดยเร็วที่สุด",
        "support_ticket_label_code": "ทิกเก็ต", "support_ticket_label_category": "หมวดหมู่", "support_ticket_label_status": "สถานะ", "support_ticket_label_priority": "ความสำคัญ", "support_ticket_label_time": "เวลา", "support_ticket_label_latest_message": "ข้อความล่าสุด", "support_ticket_label_latest_reply": "คำตอบล่าสุด",
        "support_ticket_list_empty": "คุณยังไม่มีทิกเก็ตช่วยเหลือ คุณสามารถสร้างทิกเก็ตใหม่เมื่อจำเป็นต้องได้รับความช่วยเหลือเฉพาะจาก TOAN AAS", "support_ticket_list_recent": "คำขอความช่วยเหลือล่าสุดของคุณ:", "support_ticket_attachment_present": "เพิ่มไฟล์แนบแล้ว",
        "support_ticket_view_current": "ดูทิกเก็ตนี้", "support_ticket_add_message": "เพิ่มข้อความ", "support_ticket_add_attachment": "เพิ่มภาพ/ไฟล์", "support_ticket_mark_done": "ทำเครื่องหมายว่าเสร็จแล้ว", "support_ticket_back_to_ticket": "ทิกเก็ต",
        "support_ticket_message_too_short": "โปรดอธิบายปัญหาให้ละเอียดขึ้นเพื่อให้ผู้ดูแลตรวจสอบได้", "support_ticket_reply_too_short": "โปรดกรอกข้อมูลที่ต้องการเพิ่ม", "support_ticket_not_found": "ไม่พบทิกเก็ตของคุณ โปรดเปิดทิกเก็ตของฉันอีกครั้ง", "support_ticket_reply_prompt": "กรอกข้อมูลที่ต้องการเพิ่ม แล้ว TOAN AAS จะบันทึกไว้ในทิกเก็ตนี้",
        "support_ticket_done_success": "ถูกทำเครื่องหมายว่าเสร็จแล้ว", "support_ticket_attachment_prompt": "ส่งภาพหน้าจอหรือไฟล์สำหรับทิกเก็ตนี้ การส่งครั้งละหนึ่งไฟล์ช่วยลดข้อผิดพลาด", "support_ticket_attachment_success": "บันทึกไฟล์ไว้ในทิกเก็ตแล้ว ผู้ดูแลจะใช้ตรวจสอบคำขอของคุณ", "support_ticket_attachment_need_media": "โปรดส่งภาพหรือไฟล์เอกสาร หากไม่ต้องแนบไฟล์ คุณสามารถเปิดทิกเก็ตอื่นหรือกลับสู่เมนูหลักได้",
        "support_ticket_action_unsupported": "ไม่รองรับการทำงานกับทิกเก็ตนี้", "support_ticket_append_success": "เพิ่มข้อมูลในทิกเก็ตแล้ว", "support_ticket_append_notice": "TOAN AAS จะเก็บไว้ในทิกเก็ตเดิมเพื่อให้ผู้ดูแลติดตามได้ต่อเนื่อง", "support_ticket_feedback_notice": "ขอบคุณ TOAN AAS ได้สร้างทิกเก็ตข้อเสนอแนะหรือปัญหาแล้ว ผู้ดูแลจะตรวจสอบเนื้อหา บอตไม่ได้เรียก AI/API ไม่ได้หัก Xu และไม่ได้คืน Xu อัตโนมัติ", "support_ticket_lead_hint": "ตัวอย่าง: ภาพสินค้า วิดีโอโฆษณา เนื้อหาแอฟฟิลิเอต ระบบอัตโนมัติ หรือแพ็กเกจธุรกิจ", "support_ticket_admin_only": "พื้นที่นี้สำหรับผู้ดูแลเท่านั้น",
    },
    "fil": {
        "support_ticket_ack": "Natanggap na ng TOAN AAS ang iyong kahilingan sa suporta.", "support_ticket_received_notice": "Susuriin ito ng admin at sasagot sa lalong madaling panahon.",
        "support_ticket_label_code": "Ticket", "support_ticket_label_category": "Kategorya", "support_ticket_label_status": "Katayuan", "support_ticket_label_priority": "Prayoridad", "support_ticket_label_time": "Oras", "support_ticket_label_latest_message": "Pinakabagong mensahe", "support_ticket_label_latest_reply": "Pinakabagong tugon",
        "support_ticket_list_empty": "Wala ka pang support ticket. Maaari kang gumawa ng bagong ticket kapag kailangan mo ng personal na tulong mula sa TOAN AAS.", "support_ticket_list_recent": "Mga huli mong kahilingan sa suporta:", "support_ticket_attachment_present": "May idinagdag na attachment.",
        "support_ticket_view_current": "Tingnan ang ticket na ito", "support_ticket_add_message": "Magdagdag ng mensahe", "support_ticket_add_attachment": "Magdagdag ng larawan/file", "support_ticket_mark_done": "Markahang tapos", "support_ticket_back_to_ticket": "Ticket",
        "support_ticket_message_too_short": "Ilarawan nang mas detalyado ang problema upang masuri ito ng admin.", "support_ticket_reply_too_short": "Ilagay ang impormasyong gusto mong idagdag.", "support_ticket_not_found": "Hindi makita ang iyong ticket. Buksan muli ang Mga ticket ko.", "support_ticket_reply_prompt": "Ilagay ang impormasyong gusto mong idagdag. Ise-save ito ng TOAN AAS sa ticket na ito.",
        "support_ticket_done_success": "ay minarkahang tapos.", "support_ticket_attachment_prompt": "Magpadala ng screenshot o file para sa ticket na ito. Ang pagpapadala ng isang file kada beses ay nakababawas ng error.", "support_ticket_attachment_success": "Nai-save ang file sa ticket. Gagamitin ito ng admin upang suriin ang iyong kahilingan.", "support_ticket_attachment_need_media": "Magpadala ng larawan o dokumento. Kung hindi kailangan ang attachment, maaari kang gumawa ng ibang ticket o bumalik sa pangunahing menu.",
        "support_ticket_action_unsupported": "Hindi suportado ang aksyong ito sa ticket.", "support_ticket_append_success": "Nadagdag ang impormasyon sa ticket.", "support_ticket_append_notice": "Mananatili ang lahat sa parehong ticket upang tuloy-tuloy itong masundan ng admin.", "support_ticket_feedback_notice": "Salamat. Gumawa ang TOAN AAS ng ticket para sa feedback o problema. Susuriin ng admin ang nilalaman. Hindi tumawag ang bot ng AI/API, hindi nagbawas ng Xu, at hindi nagbigay ng awtomatikong refund ng Xu.", "support_ticket_lead_hint": "Halimbawa: larawan ng produkto, video na pang-advertise, affiliate content, automation, o enterprise package.", "support_ticket_admin_only": "Para lamang ito sa mga admin.",
    },
    "it": {
        "support_ticket_ack": "TOAN AAS ha ricevuto la tua richiesta di assistenza.", "support_ticket_received_notice": "Un amministratore la controllerà e risponderà il prima possibile.",
        "support_ticket_label_code": "Ticket", "support_ticket_label_category": "Categoria", "support_ticket_label_status": "Stato", "support_ticket_label_priority": "Priorità", "support_ticket_label_time": "Ora", "support_ticket_label_latest_message": "Ultimo messaggio", "support_ticket_label_latest_reply": "Ultima risposta",
        "support_ticket_list_empty": "Non hai ancora ticket di assistenza. Puoi crearne uno quando ti serve un aiuto personalizzato da TOAN AAS.", "support_ticket_list_recent": "Le tue richieste di assistenza recenti:", "support_ticket_attachment_present": "È stato aggiunto un allegato.",
        "support_ticket_view_current": "Vedi questo ticket", "support_ticket_add_message": "Aggiungi messaggio", "support_ticket_add_attachment": "Aggiungi immagine/file", "support_ticket_mark_done": "Segna come risolto", "support_ticket_back_to_ticket": "Ticket",
        "support_ticket_message_too_short": "Descrivi il problema con maggiori dettagli affinché l’amministratore possa verificarlo.", "support_ticket_reply_too_short": "Inserisci le informazioni che vuoi aggiungere.", "support_ticket_not_found": "Il tuo ticket non è stato trovato. Apri di nuovo I miei ticket.", "support_ticket_reply_prompt": "Inserisci le informazioni che vuoi aggiungere. TOAN AAS le salverà in questo ticket.",
        "support_ticket_done_success": "è stato segnato come risolto.", "support_ticket_attachment_prompt": "Invia uno screenshot o un file per questo ticket. Inviare un file alla volta aiuta a evitare errori.", "support_ticket_attachment_success": "Il file è stato salvato nel ticket. Un amministratore lo userà per verificare la tua richiesta.", "support_ticket_attachment_need_media": "Invia un’immagine o un documento. Se non serve un allegato, puoi aprire un altro ticket o tornare al menu principale.",
        "support_ticket_action_unsupported": "Questa azione del ticket non è supportata.", "support_ticket_append_success": "Le informazioni sono state aggiunte al ticket.", "support_ticket_append_notice": "TOAN AAS manterrà tutto nello stesso ticket affinché l’amministratore possa seguirlo senza interruzioni.", "support_ticket_feedback_notice": "Grazie. TOAN AAS ha creato un ticket di feedback o problema. Un amministratore controllerà il contenuto. Il bot non ha chiamato AI/API, non ha addebitato Xu e non ha emesso un rimborso Xu automatico.", "support_ticket_lead_hint": "Ad esempio: immagini prodotto, video pubblicitario, contenuti affiliati, automazione o pacchetto aziendale.", "support_ticket_admin_only": "Quest’area è riservata agli amministratori.",
    },
    "id": {
        "support_ticket_ack": "TOAN AAS telah menerima permintaan dukungan Anda.", "support_ticket_received_notice": "Admin akan meninjaunya dan membalas sesegera mungkin.",
        "support_ticket_label_code": "Tiket", "support_ticket_label_category": "Kategori", "support_ticket_label_status": "Status", "support_ticket_label_priority": "Prioritas", "support_ticket_label_time": "Waktu", "support_ticket_label_latest_message": "Pesan terbaru", "support_ticket_label_latest_reply": "Balasan terbaru",
        "support_ticket_list_empty": "Anda belum memiliki tiket dukungan. Buat tiket baru saat memerlukan bantuan khusus dari TOAN AAS.", "support_ticket_list_recent": "Permintaan dukungan terbaru Anda:", "support_ticket_attachment_present": "Lampiran telah ditambahkan.",
        "support_ticket_view_current": "Lihat tiket ini", "support_ticket_add_message": "Tambah pesan", "support_ticket_add_attachment": "Tambah gambar/file", "support_ticket_mark_done": "Tandai selesai", "support_ticket_back_to_ticket": "Tiket",
        "support_ticket_message_too_short": "Jelaskan masalah dengan lebih rinci agar admin dapat meninjaunya.", "support_ticket_reply_too_short": "Masukkan informasi yang ingin Anda tambahkan.", "support_ticket_not_found": "Tiket Anda tidak ditemukan. Buka Tiket saya lagi.", "support_ticket_reply_prompt": "Masukkan informasi yang ingin Anda tambahkan. TOAN AAS akan menyimpannya di tiket ini.",
        "support_ticket_done_success": "telah ditandai selesai.", "support_ticket_attachment_prompt": "Kirim tangkapan layar atau file untuk tiket ini. Mengirim satu file setiap kali membantu mencegah kesalahan.", "support_ticket_attachment_success": "File telah disimpan pada tiket. Admin akan menggunakannya untuk meninjau permintaan Anda.", "support_ticket_attachment_need_media": "Kirim gambar atau dokumen. Jika tidak memerlukan lampiran, Anda dapat membuka tiket lain atau kembali ke menu utama.",
        "support_ticket_action_unsupported": "Tindakan tiket ini tidak didukung.", "support_ticket_append_success": "Informasi telah ditambahkan ke tiket.", "support_ticket_append_notice": "TOAN AAS akan menyimpan semuanya dalam tiket yang sama agar admin dapat menindaklanjuti secara berkelanjutan.", "support_ticket_feedback_notice": "Terima kasih. TOAN AAS telah membuat tiket masukan atau masalah. Admin akan meninjau isinya. Bot tidak memanggil AI/API, tidak memotong Xu, dan tidak melakukan pengembalian Xu otomatis.", "support_ticket_lead_hint": "Misalnya: gambar produk, video iklan, konten afiliasi, otomatisasi, atau paket perusahaan.", "support_ticket_admin_only": "Area ini hanya untuk admin.",
    },
}


_PUBLIC_SUPPORT_TICKET_STATUS_COPY = {
    "vi": ("Mới", "Đang kiểm tra", "Chờ khách bổ sung", "Chờ kiểm tra ngoài", "Chờ kiểm tra hoàn Xu", "Đã xử lý", "Đã đóng"),
    "en": ("New", "Under review", "Waiting for your details", "Waiting for external review", "Refund review pending", "Resolved", "Closed"),
    "zh": ("新建", "审核中", "等待您补充", "等待外部核查", "退款审核中", "已处理", "已关闭"),
    "es": ("Nuevo", "En revisión", "Esperando información suya", "Esperando revisión externa", "Revisión de reembolso pendiente", "Resuelto", "Cerrado"),
    "pt": ("Novo", "Em análise", "Aguardando suas informações", "Aguardando análise externa", "Análise de reembolso pendente", "Resolvido", "Fechado"),
    "fr": ("Nouveau", "En cours d’examen", "En attente de vos précisions", "En attente d’examen externe", "Remboursement en cours d’examen", "Résolu", "Fermé"),
    "de": ("Neu", "In Prüfung", "Warten auf Ihre Angaben", "Warten auf externe Prüfung", "Erstattungsprüfung ausstehend", "Gelöst", "Geschlossen"),
    "ja": ("新規", "確認中", "追加情報待ち", "外部確認待ち", "返金確認待ち", "解決済み", "クローズ"),
    "ko": ("신규", "검토 중", "추가 정보 대기", "외부 검토 대기", "환불 검토 대기", "처리 완료", "종료"),
    "hi": ("नया", "समीक्षा में", "आपकी जानकारी की प्रतीक्षा", "बाहरी समीक्षा की प्रतीक्षा", "रिफंड समीक्षा लंबित", "समाधान हुआ", "बंद"),
    "ar": ("جديد", "قيد المراجعة", "بانتظار معلوماتك", "بانتظار مراجعة خارجية", "مراجعة الاسترداد معلقة", "تم الحل", "مغلق"),
    "ru": ("Новое", "На проверке", "Ожидается ваша информация", "Ожидается внешняя проверка", "Проверка возврата ожидается", "Решено", "Закрыто"),
    "tr": ("Yeni", "İnceleniyor", "Bilgileriniz bekleniyor", "Harici inceleme bekleniyor", "İade incelemesi bekliyor", "Çözüldü", "Kapatıldı"),
    "th": ("ใหม่", "กำลังตรวจสอบ", "รอข้อมูลเพิ่มเติมจากคุณ", "รอการตรวจสอบภายนอก", "รอตรวจสอบการคืนเงิน", "แก้ไขแล้ว", "ปิดแล้ว"),
    "fil": ("Bago", "Sinusuri", "Hinihintay ang iyong dagdag na impormasyon", "Hinihintay ang panlabas na pagsusuri", "Naghihintay ng pagsusuri sa refund", "Nalutas", "Isinara"),
    "it": ("Nuovo", "In revisione", "In attesa delle tue informazioni", "In attesa di revisione esterna", "Revisione rimborso in attesa", "Risolto", "Chiuso"),
    "id": ("Baru", "Sedang ditinjau", "Menunggu informasi Anda", "Menunggu peninjauan eksternal", "Peninjauan pengembalian dana tertunda", "Selesai", "Ditutup"),
}


_PUBLIC_SUPPORT_TICKET_PRIORITY_COPY = {
    "vi": ("Thấp", "Bình thường", "Cao", "Khẩn cấp"), "en": ("Low", "Normal", "High", "Urgent"), "zh": ("低", "普通", "高", "紧急"), "es": ("Baja", "Normal", "Alta", "Urgente"), "pt": ("Baixa", "Normal", "Alta", "Urgente"), "fr": ("Basse", "Normale", "Haute", "Urgente"), "de": ("Niedrig", "Normal", "Hoch", "Dringend"), "ja": ("低", "通常", "高", "緊急"), "ko": ("낮음", "보통", "높음", "긴급"), "hi": ("कम", "सामान्य", "उच्च", "तत्काल"), "ar": ("منخفضة", "عادية", "عالية", "عاجلة"), "ru": ("Низкий", "Обычный", "Высокий", "Срочно"), "tr": ("Düşük", "Normal", "Yüksek", "Acil"), "th": ("ต่ำ", "ปกติ", "สูง", "เร่งด่วน"), "fil": ("Mababa", "Normal", "Mataas", "Agarang"), "it": ("Bassa", "Normale", "Alta", "Urgente"), "id": ("Rendah", "Normal", "Tinggi", "Mendesak"),
}


_PUBLIC_SUPPORT_TICKET_CATEGORY_SOURCE_KEYS = {
    "payment_topup": "feedback_payment_topup", "image_error": "feedback_image_error", "video_error": "feedback_video_error", "document_pdf": "feedback_document_pdf", "package_combo": "feedback_package_combo", "refund": "feedback_refund", "feature_request": "feedback_feature_request", "lead_consulting": "support_consult", "general_support": "support_ticket", "service_consulting": "support_consult", "premium_lead": "support_premium", "custom_bot_lead": "support_custom_bot", "other": "feedback_other",
}


_PUBLIC_SUPPORT_TICKET_STATUS_CODES = ("new", "reviewing", "waiting_user", "waiting_provider", "refund_pending", "resolved", "closed")
_PUBLIC_SUPPORT_TICKET_PRIORITY_CODES = ("low", "normal", "high", "urgent")


# The values are displayed only; ``support|consult_need|<type>|<index>`` keeps
# its existing stable service code and zero-based option index.
_PUBLIC_SUPPORT_CONSULT_CHOICES = {
    "vi": {
        "image": ("Ảnh sản phẩm", "Ảnh quảng cáo / social", "Ảnh thương hiệu"),
        "video": ("Video TikTok / affiliate", "Video quảng cáo sản phẩm", "Video doanh nghiệp"),
        "frame_video": ("Slideshow sản phẩm", "Reels / Shorts", "Video có nhạc hoặc giọng đọc"),
        "document": ("Chuyển đổi PDF", "OCR / tách nội dung", "Quy trình tài liệu"),
        "voice": ("Voice quảng cáo", "Thuyết minh video", "Giọng đọc nội dung"),
        "package": ("Gói cá nhân", "Gói shop / affiliate", "Gói doanh nghiệp"),
    },
    "en": {
        "image": ("Product images", "Advertising / social images", "Brand images"),
        "video": ("TikTok / affiliate video", "Product advertising video", "Business video"),
        "frame_video": ("Product slideshow", "Reels / Shorts", "Video with music or voice-over"),
        "document": ("PDF conversion", "OCR / content extraction", "Document workflow"),
        "voice": ("Advertising voice-over", "Video narration", "Content voice-over"),
        "package": ("Personal plan", "Shop / affiliate plan", "Business plan"),
    },
    "zh": {
        "image": ("产品图片", "广告 / 社交图片", "品牌图片"),
        "video": ("TikTok / 联盟营销视频", "产品广告视频", "企业视频"),
        "frame_video": ("产品幻灯片", "Reels / Shorts", "配乐或配音视频"),
        "document": ("PDF 转换", "OCR / 内容提取", "文档流程"),
        "voice": ("广告配音", "视频旁白", "内容朗读"),
        "package": ("个人套餐", "商店 / 联盟套餐", "企业套餐"),
    },
    "es": {
        "image": ("Imágenes de producto", "Imágenes publicitarias / sociales", "Imágenes de marca"),
        "video": ("Vídeo para TikTok / afiliados", "Vídeo publicitario de producto", "Vídeo empresarial"),
        "frame_video": ("Presentación de producto", "Reels / Shorts", "Vídeo con música o voz"),
        "document": ("Conversión de PDF", "OCR / extracción de contenido", "Flujo de documentos"),
        "voice": ("Voz publicitaria", "Narración de vídeo", "Voz para contenido"),
        "package": ("Plan personal", "Plan para tienda / afiliados", "Plan empresarial"),
    },
    "pt": {
        "image": ("Imagens de produto", "Imagens de publicidade / redes sociais", "Imagens de marca"),
        "video": ("Vídeo para TikTok / afiliados", "Vídeo publicitário de produto", "Vídeo empresarial"),
        "frame_video": ("Apresentação de produto", "Reels / Shorts", "Vídeo com música ou voz"),
        "document": ("Conversão de PDF", "OCR / extração de conteúdo", "Fluxo de documentos"),
        "voice": ("Voz publicitária", "Narração de vídeo", "Voz para conteúdo"),
        "package": ("Plano pessoal", "Plano para loja / afiliados", "Plano empresarial"),
    },
    "fr": {
        "image": ("Images produit", "Images publicitaires / sociales", "Images de marque"),
        "video": ("Vidéo TikTok / affilié", "Vidéo publicitaire produit", "Vidéo d’entreprise"),
        "frame_video": ("Diaporama produit", "Reels / Shorts", "Vidéo avec musique ou voix"),
        "document": ("Conversion PDF", "OCR / extraction de contenu", "Flux documentaire"),
        "voice": ("Voix publicitaire", "Narration vidéo", "Voix pour contenu"),
        "package": ("Forfait personnel", "Forfait boutique / affilié", "Forfait entreprise"),
    },
    "de": {
        "image": ("Produktbilder", "Werbe- / Social-Bilder", "Markenbilder"),
        "video": ("TikTok- / Affiliate-Video", "Produktwerbevideo", "Unternehmensvideo"),
        "frame_video": ("Produkt-Diashow", "Reels / Shorts", "Video mit Musik oder Sprecher"),
        "document": ("PDF-Umwandlung", "OCR / Inhaltsauszug", "Dokumentenablauf"),
        "voice": ("Werbesprecher", "Videokommentar", "Sprecher für Inhalte"),
        "package": ("Privatpaket", "Shop- / Affiliate-Paket", "Unternehmenspaket"),
    },
    "ja": {
        "image": ("商品画像", "広告 / SNS画像", "ブランド画像"),
        "video": ("TikTok / アフィリエイト動画", "商品広告動画", "企業動画"),
        "frame_video": ("商品スライドショー", "Reels / Shorts", "音楽またはナレーション付き動画"),
        "document": ("PDF変換", "OCR / 内容抽出", "文書ワークフロー"),
        "voice": ("広告ナレーション", "動画ナレーション", "コンテンツ読み上げ"),
        "package": ("個人プラン", "ショップ / アフィリエイトプラン", "法人プラン"),
    },
    "ko": {
        "image": ("상품 이미지", "광고 / 소셜 이미지", "브랜드 이미지"),
        "video": ("TikTok / 제휴 동영상", "상품 광고 동영상", "기업 동영상"),
        "frame_video": ("상품 슬라이드쇼", "Reels / Shorts", "음악 또는 내레이션 동영상"),
        "document": ("PDF 변환", "OCR / 내용 추출", "문서 워크플로"),
        "voice": ("광고 음성", "동영상 내레이션", "콘텐츠 음성"),
        "package": ("개인 플랜", "쇼핑몰 / 제휴 플랜", "기업 플랜"),
    },
    "hi": {
        "image": ("उत्पाद चित्र", "विज्ञापन / सोशल चित्र", "ब्रांड चित्र"),
        "video": ("TikTok / एफिलिएट वीडियो", "उत्पाद विज्ञापन वीडियो", "व्यावसायिक वीडियो"),
        "frame_video": ("उत्पाद स्लाइडशो", "Reels / Shorts", "संगीत या वॉइसओवर वाला वीडियो"),
        "document": ("PDF रूपांतरण", "OCR / सामग्री निष्कर्षण", "दस्तावेज़ कार्यप्रवाह"),
        "voice": ("विज्ञापन आवाज़", "वीडियो नैरेशन", "सामग्री वॉइसओवर"),
        "package": ("व्यक्तिगत प्लान", "दुकान / एफिलिएट प्लान", "व्यवसाय प्लान"),
    },
    "ar": {
        "image": ("صور المنتجات", "صور إعلانية / اجتماعية", "صور العلامة التجارية"),
        "video": ("فيديو TikTok / أفلييت", "فيديو إعلان المنتج", "فيديو أعمال"),
        "frame_video": ("عرض شرائح المنتج", "Reels / Shorts", "فيديو بموسيقى أو تعليق صوتي"),
        "document": ("تحويل PDF", "OCR / استخراج المحتوى", "سير عمل المستندات"),
        "voice": ("صوت إعلاني", "تعليق فيديو", "صوت للمحتوى"),
        "package": ("خطة شخصية", "خطة متجر / أفلييت", "خطة أعمال"),
    },
    "ru": {
        "image": ("Изображения товара", "Рекламные / социальные изображения", "Изображения бренда"),
        "video": ("Видео для TikTok / партнёров", "Рекламное видео товара", "Корпоративное видео"),
        "frame_video": ("Слайд-шоу товара", "Reels / Shorts", "Видео с музыкой или озвучкой"),
        "document": ("Конвертация PDF", "OCR / извлечение содержимого", "Документооборот"),
        "voice": ("Рекламная озвучка", "Видеонаррация", "Озвучка контента"),
        "package": ("Личный план", "План для магазина / партнёров", "Корпоративный план"),
    },
    "tr": {
        "image": ("Ürün görselleri", "Reklam / sosyal medya görselleri", "Marka görselleri"),
        "video": ("TikTok / ortaklık videosu", "Ürün reklam videosu", "Kurumsal video"),
        "frame_video": ("Ürün slayt gösterisi", "Reels / Shorts", "Müzik veya seslendirmeli video"),
        "document": ("PDF dönüştürme", "OCR / içerik çıkarma", "Belge iş akışı"),
        "voice": ("Reklam sesi", "Video anlatımı", "İçerik seslendirmesi"),
        "package": ("Kişisel plan", "Mağaza / ortaklık planı", "Kurumsal plan"),
    },
    "th": {
        "image": ("ภาพสินค้า", "ภาพโฆษณา / โซเชียล", "ภาพแบรนด์"),
        "video": ("วิดีโอ TikTok / แอฟฟิลิเอต", "วิดีโอโฆษณาสินค้า", "วิดีโอองค์กร"),
        "frame_video": ("สไลด์โชว์สินค้า", "Reels / Shorts", "วิดีโอพร้อมเพลงหรือเสียงพากย์"),
        "document": ("แปลง PDF", "OCR / ดึงเนื้อหา", "เวิร์กโฟลว์เอกสาร"),
        "voice": ("เสียงโฆษณา", "บรรยายวิดีโอ", "เสียงสำหรับเนื้อหา"),
        "package": ("แพ็กเกจบุคคล", "แพ็กเกจร้านค้า / แอฟฟิลิเอต", "แพ็กเกจธุรกิจ"),
    },
    "fil": {
        "image": ("Mga larawan ng produkto", "Larawang pang-advertise / social", "Larawan ng brand"),
        "video": ("TikTok / affiliate na video", "Video ng product advertising", "Video ng negosyo"),
        "frame_video": ("Product slideshow", "Reels / Shorts", "Video na may musika o boses"),
        "document": ("Pag-convert ng PDF", "OCR / pagkuha ng nilalaman", "Daloy ng dokumento"),
        "voice": ("Boses para sa ad", "Narration ng video", "Boses para sa content"),
        "package": ("Personal na plano", "Plano para sa shop / affiliate", "Plano para sa negosyo"),
    },
    "it": {
        "image": ("Immagini prodotto", "Immagini pubblicitarie / social", "Immagini del brand"),
        "video": ("Video TikTok / affiliati", "Video pubblicitario del prodotto", "Video aziendale"),
        "frame_video": ("Presentazione del prodotto", "Reels / Shorts", "Video con musica o voce"),
        "document": ("Conversione PDF", "OCR / estrazione contenuto", "Flusso documentale"),
        "voice": ("Voce pubblicitaria", "Narrazione video", "Voce per contenuti"),
        "package": ("Piano personale", "Piano negozio / affiliati", "Piano aziendale"),
    },
    "id": {
        "image": ("Gambar produk", "Gambar iklan / sosial", "Gambar merek"),
        "video": ("Video TikTok / afiliasi", "Video iklan produk", "Video bisnis"),
        "frame_video": ("Slideshow produk", "Reels / Shorts", "Video dengan musik atau suara"),
        "document": ("Konversi PDF", "OCR / ekstraksi konten", "Alur dokumen"),
        "voice": ("Suara iklan", "Narasi video", "Suara konten"),
        "package": ("Paket pribadi", "Paket toko / afiliasi", "Paket bisnis"),
    },
}


def public_support_consult_choices(service_type: str, lang: str | None = None) -> tuple[str, str, str]:
    """Return native display labels without touching support route identifiers."""

    locale = public_copy_locale(lang)
    value = _PUBLIC_SUPPORT_CONSULT_CHOICES[locale].get(str(service_type or ""))
    if value:
        return tuple(str(item) for item in value)
    return tuple(str(item) for item in _PUBLIC_SUPPORT_CONSULT_CHOICES[locale]["video"])


_PUBLIC_VIDEO_MENU_LABELS = {
    "vi": {
        "video_trend": "🔥 Video theo trend",
        "video_ai_real": "🎬 Video AI chân thật",
        "script_image_video": "🧩 Kịch bản → Video",
        "frame_video_local": "🎞 Ghép ảnh thành video",
        "self_shot_scene_change": "🎥 Video tự quay",
        "storyboard_prompt": "🎞 Storyboard",
        "multi_scene_film": "🎬 Video dài tập",
        "video_idea": "💡 Ý tưởng video",
        "video_local_edit": "🛠️ Chỉnh sửa / Nâng cấp video",
        "video_downloader": "📥 Tải video từ liên kết",
        "video_edit_planning": "🧭 Lên kế hoạch chỉnh sửa",
        "video_guide": "📖 Hướng dẫn video",
        "video_resume": "↩️ Tiếp tục kế hoạch video đang làm",
    },
    "en": {
        "video_trend": "🔥 Trend video",
        "video_ai_real": "🎬 Real AI video",
        "script_image_video": "🧩 Script → Video",
        "frame_video_local": "🎞 Image slideshow video",
        "self_shot_scene_change": "🎥 Self-shot video",
        "storyboard_prompt": "🎞 Storyboard",
        "multi_scene_film": "🎬 Long-form episodic video",
        "video_idea": "💡 Video ideas",
        "video_local_edit": "🛠️ Edit / enhance video",
        "video_downloader": "📥 Download video from link",
        "video_edit_planning": "🧭 Video editing planner",
        "video_guide": "📖 Video guide",
        "video_resume": "↩️ Resume current video plan",
    },
    "zh": {
        "video_trend": "🔥 趋势视频",
        "video_ai_real": "🎬 真实 AI 视频",
        "script_image_video": "🧩 脚本 → 视频",
        "frame_video_local": "🎞 图片幻灯片视频",
        "self_shot_scene_change": "🎥 自拍视频",
        "storyboard_prompt": "🎞 分镜脚本",
        "multi_scene_film": "🎬 长篇分集视频",
        "video_idea": "💡 视频创意",
        "video_local_edit": "🛠️ 编辑 / 增强视频",
        "video_downloader": "📥 从链接下载视频",
        "video_edit_planning": "🧭 视频剪辑规划",
        "video_guide": "📖 视频指南",
        "video_resume": "↩️ 继续当前视频计划",
    },
    "es": {
        "video_trend": "🔥 Vídeo de tendencias",
        "video_ai_real": "🎬 Vídeo IA realista",
        "script_image_video": "🧩 Guion → Vídeo",
        "frame_video_local": "🎞 Vídeo de presentación de imágenes",
        "self_shot_scene_change": "🎥 Vídeo grabado por ti",
        "storyboard_prompt": "🎞 Guion gráfico",
        "multi_scene_film": "🎬 Vídeo episódico de larga duración",
        "video_idea": "💡 Ideas para vídeo",
        "video_local_edit": "🛠️ Editar / mejorar vídeo",
        "video_downloader": "📥 Descargar vídeo desde enlace",
        "video_edit_planning": "🧭 Planificador de edición de vídeo",
        "video_guide": "📖 Guía de vídeo",
        "video_resume": "↩️ Continuar el plan de vídeo actual",
    },
    "pt": {
        "video_trend": "🔥 Vídeo em tendência",
        "video_ai_real": "🎬 Vídeo de IA realista",
        "script_image_video": "🧩 Roteiro → Vídeo",
        "frame_video_local": "🎞 Vídeo de apresentação de imagens",
        "self_shot_scene_change": "🎥 Vídeo gravado por você",
        "storyboard_prompt": "🎞 Storyboard",
        "multi_scene_film": "🎬 Vídeo episódico de longa duração",
        "video_idea": "💡 Ideias de vídeo",
        "video_local_edit": "🛠️ Editar / aprimorar vídeo",
        "video_downloader": "📥 Baixar vídeo por link",
        "video_edit_planning": "🧭 Planejador de edição de vídeo",
        "video_guide": "📖 Guia de vídeo",
        "video_resume": "↩️ Continuar o plano de vídeo atual",
    },
    "fr": {
        "video_trend": "🔥 Vidéo tendance",
        "video_ai_real": "🎬 Vidéo IA réaliste",
        "script_image_video": "🧩 Script → vidéo",
        "frame_video_local": "🎞 Diaporama vidéo d’images",
        "self_shot_scene_change": "🎥 Vidéo autoportrait",
        "storyboard_prompt": "🎞 Storyboard",
        "multi_scene_film": "🎬 Vidéo épisodique longue durée",
        "video_idea": "💡 Idées vidéo",
        "video_local_edit": "🛠️ Modifier / améliorer une vidéo",
        "video_downloader": "📥 Télécharger une vidéo depuis un lien",
        "video_edit_planning": "🧭 Planificateur de montage vidéo",
        "video_guide": "📖 Guide vidéo",
        "video_resume": "↩️ Reprendre le plan vidéo en cours",
    },
    "de": {
        "video_trend": "🔥 Trendvideo",
        "video_ai_real": "🎬 Realistisches KI-Video",
        "script_image_video": "🧩 Skript → Video",
        "frame_video_local": "🎞 Bilder-Diashow-Video",
        "self_shot_scene_change": "🎥 Selbstaufnahme-Video",
        "storyboard_prompt": "🎞 Storyboard",
        "multi_scene_film": "🎬 Langformat-Serienvideo",
        "video_idea": "💡 Videoideen",
        "video_local_edit": "🛠️ Video bearbeiten / verbessern",
        "video_downloader": "📥 Video über Link herunterladen",
        "video_edit_planning": "🧭 Video-Editing-Planer",
        "video_guide": "📖 Videoanleitung",
        "video_resume": "↩️ Aktuellen Videoplan fortsetzen",
    },
    "ja": {
        "video_trend": "🔥 トレンド動画",
        "video_ai_real": "🎬 リアルなAI動画",
        "script_image_video": "🧩 台本 → 動画",
        "frame_video_local": "🎞 画像スライドショー動画",
        "self_shot_scene_change": "🎥 自撮り動画",
        "storyboard_prompt": "🎞 絵コンテ",
        "multi_scene_film": "🎬 長編エピソード動画",
        "video_idea": "💡 動画アイデア",
        "video_local_edit": "🛠️ 動画を編集・高画質化",
        "video_downloader": "📥 リンクから動画をダウンロード",
        "video_edit_planning": "🧭 動画編集プランナー",
        "video_guide": "📖 動画ガイド",
        "video_resume": "↩️ 作成中の動画プランを続ける",
    },
    "ko": {
        "video_trend": "🔥 트렌드 동영상",
        "video_ai_real": "🎬 사실적인 AI 동영상",
        "script_image_video": "🧩 스크립트 → 동영상",
        "frame_video_local": "🎞 이미지 슬라이드쇼 동영상",
        "self_shot_scene_change": "🎥 셀프 촬영 동영상",
        "storyboard_prompt": "🎞 스토리보드",
        "multi_scene_film": "🎬 장편 에피소드 동영상",
        "video_idea": "💡 동영상 아이디어",
        "video_local_edit": "🛠️ 동영상 편집 / 향상",
        "video_downloader": "📥 링크에서 동영상 다운로드",
        "video_edit_planning": "🧭 동영상 편집 플래너",
        "video_guide": "📖 동영상 가이드",
        "video_resume": "↩️ 진행 중인 동영상 계획 계속하기",
    },
    "hi": {
        "video_trend": "🔥 ट्रेंडिंग वीडियो",
        "video_ai_real": "🎬 वास्तविक AI वीडियो",
        "script_image_video": "🧩 स्क्रिप्ट → वीडियो",
        "frame_video_local": "🎞 इमेज स्लाइडशो वीडियो",
        "self_shot_scene_change": "🎥 सेल्फ-शॉट वीडियो",
        "storyboard_prompt": "🎞 स्टोरीबोर्ड",
        "multi_scene_film": "🎬 लंबी एपिसोडिक वीडियो",
        "video_idea": "💡 वीडियो विचार",
        "video_local_edit": "🛠️ वीडियो संपादित / बेहतर करें",
        "video_downloader": "📥 लिंक से वीडियो डाउनलोड करें",
        "video_edit_planning": "🧭 वीडियो संपादन योजनाकार",
        "video_guide": "📖 वीडियो गाइड",
        "video_resume": "↩️ मौजूदा वीडियो योजना जारी रखें",
    },
    "ar": {
        "video_trend": "🔥 فيديو رائج",
        "video_ai_real": "🎬 فيديو ذكاء اصطناعي واقعي",
        "script_image_video": "🧩 نص → فيديو",
        "frame_video_local": "🎞 فيديو عرض شرائح الصور",
        "self_shot_scene_change": "🎥 فيديو تصوير ذاتي",
        "storyboard_prompt": "🎞 لوحة مشاهد",
        "multi_scene_film": "🎬 فيديو حلقات طويل",
        "video_idea": "💡 أفكار فيديو",
        "video_local_edit": "🛠️ تحرير / تحسين الفيديو",
        "video_downloader": "📥 تنزيل فيديو من رابط",
        "video_edit_planning": "🧭 مخطط تحرير الفيديو",
        "video_guide": "📖 دليل الفيديو",
        "video_resume": "↩️ متابعة خطة الفيديو الحالية",
    },
    "ru": {
        "video_trend": "🔥 Трендовое видео",
        "video_ai_real": "🎬 Реалистичное видео с ИИ",
        "script_image_video": "🧩 Сценарий → видео",
        "frame_video_local": "🎞 Видео-слайдшоу из изображений",
        "self_shot_scene_change": "🎥 Видео-селфи",
        "storyboard_prompt": "🎞 Раскадровка",
        "multi_scene_film": "🎬 Длинное эпизодическое видео",
        "video_idea": "💡 Идеи для видео",
        "video_local_edit": "🛠️ Редактировать / улучшить видео",
        "video_downloader": "📥 Скачать видео по ссылке",
        "video_edit_planning": "🧭 Планировщик видеомонтажа",
        "video_guide": "📖 Руководство по видео",
        "video_resume": "↩️ Продолжить текущий план видео",
    },
    "tr": {
        "video_trend": "🔥 Trend video",
        "video_ai_real": "🎬 Gerçekçi yapay zekâ videosu",
        "script_image_video": "🧩 Senaryo → Video",
        "frame_video_local": "🎞 Görsel slayt gösterisi videosu",
        "self_shot_scene_change": "🎥 Özçekim videosu",
        "storyboard_prompt": "🎞 Storyboard",
        "multi_scene_film": "🎬 Uzun bölümlü video",
        "video_idea": "💡 Video fikirleri",
        "video_local_edit": "🛠️ Videoyu düzenle / iyileştir",
        "video_downloader": "📥 Bağlantıdan video indir",
        "video_edit_planning": "🧭 Video düzenleme planlayıcısı",
        "video_guide": "📖 Video rehberi",
        "video_resume": "↩️ Mevcut video planına devam et",
    },
    "th": {
        "video_trend": "🔥 วิดีโอตามเทรนด์",
        "video_ai_real": "🎬 วิดีโอ AI สมจริง",
        "script_image_video": "🧩 สคริปต์ → วิดีโอ",
        "frame_video_local": "🎞 วิดีโอสไลด์โชว์ภาพ",
        "self_shot_scene_change": "🎥 วิดีโอถ่ายด้วยตนเอง",
        "storyboard_prompt": "🎞 สตอรี่บอร์ด",
        "multi_scene_film": "🎬 วิดีโอแบบตอนยาว",
        "video_idea": "💡 ไอเดียวิดีโอ",
        "video_local_edit": "🛠️ แก้ไข / ปรับปรุงวิดีโอ",
        "video_downloader": "📥 ดาวน์โหลดวิดีโอจากลิงก์",
        "video_edit_planning": "🧭 ตัววางแผนการตัดต่อวิดีโอ",
        "video_guide": "📖 คู่มือวิดีโอ",
        "video_resume": "↩️ ดำเนินแผนวิดีโอปัจจุบันต่อ",
    },
    "fil": {
        "video_trend": "🔥 Trending na bidyo",
        "video_ai_real": "🎬 Makatotohanang AI na bidyo",
        "script_image_video": "🧩 Script → Bidyo",
        "frame_video_local": "🎞 Bidyong slideshow ng larawan",
        "self_shot_scene_change": "🎥 Bidyong self-shot",
        "storyboard_prompt": "🎞 Storyboard",
        "multi_scene_film": "🎬 Mahabang episodikong bidyo",
        "video_idea": "💡 Mga ideya sa bidyo",
        "video_local_edit": "🛠️ I-edit / pagandahin ang bidyo",
        "video_downloader": "📥 Mag-download ng bidyo mula sa link",
        "video_edit_planning": "🧭 Tagaplano ng pag-edit ng bidyo",
        "video_guide": "📖 Gabay sa bidyo",
        "video_resume": "↩️ Ipagpatuloy ang kasalukuyang plano ng bidyo",
    },
    "it": {
        "video_trend": "🔥 Video di tendenza",
        "video_ai_real": "🎬 Video IA realistico",
        "script_image_video": "🧩 Sceneggiatura → Video",
        "frame_video_local": "🎞 Video slideshow di immagini",
        "self_shot_scene_change": "🎥 Video selfie",
        "storyboard_prompt": "🎞 Storyboard",
        "multi_scene_film": "🎬 Video episodico di lunga durata",
        "video_idea": "💡 Idee video",
        "video_local_edit": "🛠️ Modifica / migliora video",
        "video_downloader": "📥 Scarica video da link",
        "video_edit_planning": "🧭 Pianificatore di montaggio video",
        "video_guide": "📖 Guida video",
        "video_resume": "↩️ Riprendi il piano video attuale",
    },
    "id": {
        "video_trend": "🔥 Video tren",
        "video_ai_real": "🎬 Video AI realistis",
        "script_image_video": "🧩 Skrip → Video",
        "frame_video_local": "🎞 Video slideshow gambar",
        "self_shot_scene_change": "🎥 Video swafoto",
        "storyboard_prompt": "🎞 Papan cerita",
        "multi_scene_film": "🎬 Video episodik berdurasi panjang",
        "video_idea": "💡 Ide video",
        "video_local_edit": "🛠️ Edit / tingkatkan video",
        "video_downloader": "📥 Unduh video dari tautan",
        "video_edit_planning": "🧭 Perencana pengeditan video",
        "video_guide": "📖 Panduan video",
        "video_resume": "↩️ Lanjutkan rencana video saat ini",
    },
}


def public_video_menu_label(tool_id: str, lang: str | None = None) -> str:
    """Return display-only native copy for a known public Video root action.

    An empty result intentionally tells the caller to retain a legacy route's
    existing label.  This helper owns no route, callback, pricing or runtime
    decision.
    """

    return str(_PUBLIC_VIDEO_MENU_LABELS[public_copy_locale(lang)].get(str(tool_id or "")) or "")


def public_hub_copy(lang: str | None = None) -> dict[str, str]:
    """Return direct customer-facing Hub copy for a supported locale."""

    locale = public_copy_locale(lang)
    copy = dict(_PUBLIC_HUB_COPY[locale])
    copy.update(_PUBLIC_HUB_AUXILIARY_COPY[locale])
    copy.update(_PUBLIC_ROOT_NAVIGATION_COPY[locale])
    copy.update(_PUBLIC_CHAT_ROOT_COPY[locale])
    copy.update(_PUBLIC_CHAT_ATTACHMENT_COPY[locale])
    copy.update(_PUBLIC_ROOT_SCREEN_COPY[locale])
    copy.update(_PUBLIC_FREE_HUB_ROOT_COPY[locale])
    copy.update(_PUBLIC_IMAGE_ROOT_COPY[locale])
    copy.update(_PUBLIC_AUDIO_ROOT_COPY[locale])
    copy.update(_PUBLIC_ROOT_FLOW_COPY[locale])
    copy.update(_PUBLIC_ROOT_ACTION_COPY[locale])
    copy.update(_PUBLIC_FEEDBACK_PROMPT_COPY[locale])
    copy.update(_PUBLIC_MEMORY_STORAGE_COPY[locale])
    copy.update(_PUBLIC_TRANSLATION_FLOW_COPY[locale])
    copy.update(_PUBLIC_TRANSLATION_MEDIA_COPY[locale])
    copy.update(_PUBLIC_TRANSLATION_COMMAND_COPY[locale])
    copy.update(_PUBLIC_INTERNATIONAL_SUPPORT_COPY.get(locale, {}))
    copy.update(_PUBLIC_SUPPORT_PROFILE_COPY[locale])
    copy.update(_PUBLIC_SUPPORT_CHILD_LABELS[locale])
    copy.update(_PUBLIC_SUPPORT_CHILD_TEXT[locale])
    copy.update(_PUBLIC_SUPPORT_DEEP_COPY[locale])
    copy.update(_PUBLIC_SUPPORT_TICKET_COPY[locale])
    copy.update({
        f"support_ticket_status_{code}": _PUBLIC_SUPPORT_TICKET_STATUS_COPY[locale][index]
        for index, code in enumerate(_PUBLIC_SUPPORT_TICKET_STATUS_CODES)
    })
    copy.update({
        f"support_ticket_priority_{code}": _PUBLIC_SUPPORT_TICKET_PRIORITY_COPY[locale][index]
        for index, code in enumerate(_PUBLIC_SUPPORT_TICKET_PRIORITY_CODES)
    })
    copy.update(_PUBLIC_PACKAGE_NAVIGATION_COPY.get(locale, {}))
    return copy


def public_guide_navigation_copy(lang: str | None = None) -> dict[str, str]:
    """Return native labels for legacy guide-entry buttons when available."""

    return dict(PUBLIC_GUIDE_NAVIGATION_I18N.get(public_copy_locale(lang), {}))


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
    package_info = _PUBLIC_PACKAGE_GUIDE_COPY[locale]
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
        "member": [f"👑 <b>{copy['member']}</b>", "", common, "", package_info, *topup_policy],
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
                "<b>AI 图片</b>", *image_lines, "", "<b>产品视频</b>", *video_lines, *video_discounts,
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
                "🎬 <b>产品视频价格</b>", "", common, "", *video_lines, *video_discounts,
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
    package_info = _PUBLIC_PACKAGE_GUIDE_COPY[locale]
    return [
        ("quick_start", copy["guide"], "\n".join([f"📚 <b>{copy['guide']}</b>", "", copy["quote"]])),
        ("image_ai", copy["images"], "\n".join([f"🖼 <b>{copy['images']}</b>", "", copy["quote"], "", *image_lines])),
        ("video_ai", copy["video"], "\n".join([f"🎬 <b>{copy['video']}</b>", "", copy["quote"], "", *video_lines, *video_discounts])),
        ("audio", f"{copy['voice']} / {copy['music']}", "\n".join([f"🎧 <b>{copy['voice']} / {copy['music']}</b>", "", copy["quote"], "", music_line, "200 / 250 / 300 Xu."])),
        ("subtitle_dub", copy["subtitles"], "\n".join([f"🌐 <b>{copy['subtitles']}</b>", "", copy["quote"]])),
        _international_topup_guide_section(locale),
        ("packages", copy["member"], "\n".join([f"👑 <b>{copy['member']}</b>", "", copy["quote"], "", package_info])),
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
                    "1. 选择图片、产品视频、音频、字幕/翻译/配音或文档工具。",
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
                "产品视频",
                "\n".join([
                    "🎬 <b>产品视频</b>", "",
                    "先选择场景数量和质量档位，确认页会显示每场价格与总 Xu。", "",
                    "当前公开产品视频档位：", *video_lines,
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
