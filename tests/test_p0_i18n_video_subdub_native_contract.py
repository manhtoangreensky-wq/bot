"""Source-only contract for native Video and SubDub customer presentation.

The test never imports ``bot``.  It inspects only public copy and renderer
source so no provider, worker, wallet, payment, database, or Telegram action
can run.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
COPY_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")
LOCALES = (
    "vi", "en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de",
    "hi", "ru", "tr", "fil", "it", "id",
)


def _literal(name: str):
    match = re.search(
        rf"^{re.escape(name)}\s*=\s*(.+?)(?=^[A-Z_][A-Z0-9_]*(?::[^=]+)?\s*=|^def\s+|\Z)",
        COPY_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"missing literal assignment: {name}"
    return ast.literal_eval(match.group(1).strip())


def _function_source(name: str) -> str:
    match = re.search(
        rf"^(?:async\s+)?def\s+{re.escape(name)}\b.*?(?=^(?:async\s+)?def\s+|^class\s+|^@|\Z)",
        BOT_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, name
    return match.group(0)


def _aligned_copy(keys_name: str, values_name: str) -> dict[str, dict[str, str]]:
    keys = _literal(keys_name)
    values = _literal(values_name)
    assert set(values) == set(LOCALES)
    return {
        locale: dict(zip(keys, values[locale], strict=True))
        for locale in LOCALES
    }


def _assert_native_table(table: dict[str, dict[str, str]]) -> None:
    english = table["en"]
    vietnamese = table["vi"]
    for locale, row in table.items():
        assert row
        assert all(str(value).strip() for value in row.values()), locale
        assert all("\ufffd" not in str(value) and "???" not in str(value) for value in row.values()), locale
        if locale in {"vi", "en"}:
            continue
        assert not [key for key, value in row.items() if value == english[key]], (locale, "English fallback")
        assert not [key for key, value in row.items() if value == vietnamese[key]], (locale, "Vietnamese fallback")


VIDEO_CORE_RENDERERS = (
    "video_profile_studio_menu_text",
    "video_profile_studio_menu_keyboard",
    "video_profile_studio_question_text",
    "video_profile_studio_preview_text",
    "video_profile_scene1_subject_text",
    "architecture_profile_menu_text",
    "video_edit_hub_text",
    "video_edit_hub_keyboard",
    "video_edit_info_text",
    "video_edit_guide_text",
    "video_ai_edit_intro_text",
    "video_editor_menu_text",
    "video_editor_upload_required_text",
    "video_editor_public_guard_text",
    "video_editor_menu_keyboard",
    "video_editor_job_status_text",
    "video_script_hub_text",
    "video_script_hub_keyboard",
    "video_script_nav_keyboard",
)

VIDEO_TAIL_RENDERERS = (
    "video_finalization_menu_text",
    "video_finalization_menu_keyboard",
    "video_finalization_aspect_text",
    "video_finalization_tier_text",
    "video_finalization_scene_count_text",
    "video_finalization_music_text",
    "video_finalization_addon_text",
    "video_finalization_voice_text",
    "video_finalization_summary_text",
    "video_addon_menu_text",
    "video_addon_menu_keyboard",
    "video_quote_invoice_text",
    "public_video_confirm_text",
    "trend_workflow_content_confirm_text",
    "trend_video_pending_prompt_text",
)

SUBDUB_RENDERERS = (
    "video_dubbing_menu_text",
    "video_dubbing_menu_keyboard",
    "video_dubbing_source_text",
    "video_dubbing_source_keyboard",
    "video_dubbing_output_text",
    "video_dubbing_output_keyboard",
    "video_dubbing_language_text",
    "video_dubbing_language_keyboard",
    "video_dubbing_voice_text",
    "video_dubbing_voice_keyboard",
    "video_dubbing_confirm_text",
    "video_dubbing_confirm_keyboard",
    "subdub_progress_text",
    "subdub_progress_keyboard",
    "subdub_clean_failure_text",
    "subdub_mode_success_text",
    "subdub_mode_fail_text",
    "video_dubbing_job_status_text",
    "subtitle_editor_text",
    "subtitle_editor_keyboard",
)


def test_video_and_subdub_copy_tables_are_direct_native_for_all_17_locales():
    _assert_native_table(_aligned_copy("_PUBLIC_VIDEO_DEEP_KEYS", "_PUBLIC_VIDEO_DEEP_VALUES"))
    _assert_native_table(_aligned_copy("_PUBLIC_SUBDUB_DEEP_KEYS", "_PUBLIC_SUBDUB_DEEP_VALUES"))


def test_video_customer_renderers_use_native_copy_without_binary_locale_branch():
    stale_patterns = (
        r"normalize_user_language\([^)]*\)\s*[!=]=\s*['\"]vi['\"]",
        r"\b(?:is_vi|labels_vi|labels_en)\b",
        r"\bif\s+lang\s*==\s*['\"](?:vi|en|zh)['\"]",
    )
    for name in VIDEO_CORE_RENDERERS + VIDEO_TAIL_RENDERERS:
        source = _function_source(name)
        assert "public_video_deep_copy" in source, name
        assert not [pattern for pattern in stale_patterns if re.search(pattern, source)], name


def test_subdub_customer_renderers_use_native_copy_without_binary_locale_branch():
    stale_patterns = (
        r"normalize_user_language\([^)]*\)\s*[!=]=\s*['\"]vi['\"]",
        r"\b(?:is_vi|labels_vi|labels_en)\b",
        r"\bif\s+lang\s*==\s*['\"](?:vi|en|zh)['\"]",
    )
    for name in SUBDUB_RENDERERS:
        source = _function_source(name)
        assert "public_subdub_deep_copy" in source, name
        assert not [pattern for pattern in stale_patterns if re.search(pattern, source)], name


def test_copy_only_change_keeps_video_and_subdub_route_callbacks_present():
    for callback in (
        "vprofile|start", "videoedit|ai", "videoedit|manual", "vproduct|script_ai",
        "vproduct|script_manual", "vproduct|script_upload", "vfinal|voice",
        "vfinal|music", "vfinal|addon", "videoaddon|invoice", "trendg|start",
        "videodub|source_upload", "videodub|confirm", "menu|main_video", "menu|main",
    ):
        assert callback in BOT_SOURCE


AUTO_SPEAKER_COPY = {
    "vi": ("👥 Tự nhận giọng (tối đa 16)", "Ghép giọng theo đặc điểm âm thanh cho tối đa 16 nhãn người nói; không xác định danh tính hay giới tính cá nhân.", "Không thể ghép giọng tự động một cách an toàn. Vui lòng chọn giọng thủ công."),
    "en": ("👥 Auto voice matching (up to 16)", "Matches voices from acoustic traits for up to 16 speaker labels; it does not identify people or personal gender.", "Auto could not match voices safely. Please choose a voice manually."),
    "zh": ("👥 自动匹配声音（最多 16 个）", "根据声学特征为最多 16 个说话人标签匹配声音；不识别身份或个人性别。", "无法安全地自动匹配声音。请选择手动声音。"),
    "es": ("👥 Asignación automática de voces (máx. 16)", "Asigna voces por rasgos acústicos a un máximo de 16 etiquetas de hablante; no identifica personas ni su género personal.", "No se pudieron asignar las voces automáticamente de forma segura. Elige una voz manualmente."),
    "pt": ("👥 Atribuição automática de vozes (máx. 16)", "Associa vozes por características acústicas a até 16 rótulos de falante; não identifica pessoas nem gênero pessoal.", "Não foi possível associar as vozes automaticamente com segurança. Escolha uma voz manualmente."),
    "fr": ("👥 Attribution automatique des voix (16 max.)", "Associe des voix selon des caractéristiques acoustiques pour 16 étiquettes de locuteur au maximum, sans identifier une personne ni son genre.", "L’attribution automatique n’a pas pu être faite de façon sûre. Choisissez une voix manuellement."),
    "de": ("👥 Automatische Stimmenzuordnung (max. 16)", "Ordnet bis zu 16 Sprecherlabels anhand akustischer Merkmale Stimmen zu; Personen oder persönliches Geschlecht werden nicht erkannt.", "Die Stimmen konnten nicht sicher automatisch zugeordnet werden. Bitte wählen Sie eine Stimme manuell."),
    "ja": ("👥 音声を自動割り当て（最大 16）", "音響的な特徴から最大 16 個の話者ラベルに音声を割り当てます。人物の特定や個人の性別判定は行いません。", "安全に自動割り当てできませんでした。音声を手動で選択してください。"),
    "ko": ("👥 음성 자동 배정(최대 16)", "음향 특성으로 최대 16개 화자 라벨에 음성을 배정하며, 사람의 신원이나 개인 성별을 식별하지 않습니다.", "음성을 안전하게 자동 배정하지 못했습니다. 음성을 직접 선택해 주세요."),
    "hi": ("👥 आवाज़ों का अपने-आप मिलान (अधिकतम 16)", "ध्वनिक गुणों से अधिकतम 16 वक्ता लेबलों के लिए आवाज़ मिलाता है; यह व्यक्ति की पहचान या निजी लिंग निर्धारित नहीं करता।", "आवाज़ों का सुरक्षित स्वचालित मिलान नहीं हो सका। कृपया आवाज़ मैन्युअल रूप से चुनें।"),
    "ar": ("👥 تعيين تلقائي للأصوات (حتى 16)", "يطابق الأصوات حسب الخصائص الصوتية لما يصل إلى 16 تسمية متحدث، ولا يحدد هوية الأشخاص أو جنسهم الشخصي.", "تعذر تعيين الأصوات تلقائياً بأمان. يرجى اختيار صوت يدوياً."),
    "ru": ("👥 Автоподбор голосов (до 16)", "Подбирает голоса по акустическим признакам максимум для 16 меток говорящих; не определяет личность или личный гендер.", "Безопасно подобрать голоса автоматически не удалось. Выберите голос вручную."),
    "tr": ("👥 Otomatik ses eşleme (en fazla 16)", "Akustik özelliklere göre en fazla 16 konuşmacı etiketine ses eşler; kişi kimliği veya kişisel cinsiyet belirlemez.", "Sesler güvenli biçimde otomatik eşlenemedi. Lütfen sesi elle seçin."),
    "th": ("👥 จับคู่เสียงอัตโนมัติ (สูงสุด 16)", "จับคู่เสียงจากลักษณะทางเสียงให้ป้ายผู้พูดได้สูงสุด 16 ป้าย โดยไม่ระบุตัวบุคคลหรือเพศส่วนบุคคล", "ไม่สามารถจับคู่เสียงอัตโนมัติได้อย่างปลอดภัย โปรดเลือกเสียงด้วยตนเอง"),
    "fil": ("👥 Awtomatikong pagtutugma ng boses (hanggang 16)", "Itinutugma ang boses ayon sa katangiang akustiko para sa hanggang 16 label ng tagapagsalita; hindi nito kinikilala ang tao o personal na kasarian.", "Hindi ligtas na naitugma nang awtomatiko ang mga boses. Pumili ng boses nang manu-mano."),
    "it": ("👥 Assegnazione automatica delle voci (max 16)", "Abbina le voci in base a caratteristiche acustiche per un massimo di 16 etichette di parlante; non identifica persone né il genere personale.", "Non è stato possibile abbinare automaticamente le voci in modo sicuro. Scegli una voce manualmente."),
    "id": ("👥 Pencocokan suara otomatis (maks. 16)", "Mencocokkan suara dari ciri akustik untuk maksimal 16 label pembicara; tidak mengidentifikasi orang atau gender pribadi.", "Suara tidak dapat dicocokkan secara otomatis dengan aman. Silakan pilih suara secara manual."),
}


def test_auto_speaker_copy_is_exact_and_native_for_all_17_locales():
    table = _aligned_copy("_PUBLIC_SUBDUB_DEEP_KEYS", "_PUBLIC_SUBDUB_DEEP_VALUES")
    assert set(AUTO_SPEAKER_COPY) == set(LOCALES)
    for locale, expected in AUTO_SPEAKER_COPY.items():
        assert (
            table[locale]["voice_auto_speaker"],
            table[locale]["voice_auto_explanation"],
            table[locale]["voice_auto_manual_required"],
        ) == expected


AUTO_EXACT_KEYS = (
    "voice_auto_billable_words",
    "voice_auto_price_rule",
    "voice_auto_exact_required",
    "voice_auto_exact_confirm",
    "voice_auto_exact_cancel",
    "voice_auto_exact_expired",
)

AUTO_EXACT_COPY = {
    "vi": (
        "🧮 Số từ tính phí",
        "0.5 Xu mỗi từ tính phí; giảm 10% từ 1,000 từ, giảm 20% từ 10,000 từ; phần Tự nhận giọng được làm tròn lên riêng.",
        "⚠️ Giá chính xác đã sẵn sàng. Vui lòng xác nhận lại trước khi tiếp tục.",
        "✅ Xác nhận giá chính xác", "❌ Hủy tác vụ",
        "⌛ Xác nhận giá chính xác đã hết hạn. Vui lòng bắt đầu lại.",
    ),
    "en": (
        "🧮 Billable words",
        "0.5 Xu per billable word; 10% off from 1,000 words, 20% off from 10,000 words; the Auto voice component is rounded up separately.",
        "⚠️ The exact price is ready. Confirm it again before continuing.",
        "✅ Confirm exact price", "❌ Cancel job",
        "⌛ The exact-price confirmation expired. Please start again.",
    ),
    "zh": (
        "🧮 计费字数",
        "每个计费字 0.5 Xu；达到 1,000 字优惠 10%，达到 10,000 字优惠 20%；自动配音部分单独向上取整。",
        "⚠️ 精确价格已生成。继续前请再次确认。", "✅ 确认精确价格", "❌ 取消任务",
        "⌛ 精确价格确认已过期。请重新开始。",
    ),
    "ja": (
        "🧮 課金対象語数",
        "課金対象1語あたり 0.5 Xu。1,000語以上で10%割引、10,000語以上で20%割引。自動音声分は個別に切り上げます。",
        "⚠️ 正確な料金が確定しました。続行前にもう一度確認してください。", "✅ 正確な料金を確認", "❌ 処理をキャンセル",
        "⌛ 正確な料金の確認期限が切れました。最初からやり直してください。",
    ),
    "ko": (
        "🧮 과금 단어 수",
        "과금 단어당 0.5 Xu; 1,000단어부터 10% 할인, 10,000단어부터 20% 할인; 자동 음성 금액은 별도로 올림 처리합니다.",
        "⚠️ 정확한 금액이 준비되었습니다. 계속하기 전에 다시 확인해 주세요.", "✅ 정확한 금액 확인", "❌ 작업 취소",
        "⌛ 정확한 금액 확인 시간이 만료되었습니다. 다시 시작해 주세요.",
    ),
    "th": (
        "🧮 จำนวนคำที่คิดค่าบริการ",
        "0.5 Xu ต่อคำที่คิดค่าบริการ; ลด 10% ตั้งแต่ 1,000 คำ และลด 20% ตั้งแต่ 10,000 คำ; ส่วนค่าเสียงอัตโนมัติปัดขึ้นแยกต่างหาก",
        "⚠️ ราคาที่แน่นอนพร้อมแล้ว โปรดยืนยันอีกครั้งก่อนดำเนินการต่อ", "✅ ยืนยันราคาที่แน่นอน", "❌ ยกเลิกงาน",
        "⌛ การยืนยันราคาที่แน่นอนหมดอายุแล้ว โปรดเริ่มใหม่",
    ),
    "ar": (
        "🧮 عدد الكلمات المحتسبة",
        "0.5 Xu لكل كلمة محتسبة؛ خصم 10% ابتداءً من 1,000 كلمة و20% ابتداءً من 10,000 كلمة؛ يُقرَّب مكوّن الصوت التلقائي إلى الأعلى بصورة منفصلة.",
        "⚠️ أصبح السعر الدقيق جاهزاً. يرجى تأكيده مرة أخرى قبل المتابعة.", "✅ تأكيد السعر الدقيق", "❌ إلغاء المهمة",
        "⌛ انتهت صلاحية تأكيد السعر الدقيق. يرجى البدء من جديد.",
    ),
    "es": (
        "🧮 Palabras facturables",
        "0.5 Xu por palabra facturable; 10% de descuento desde 1,000 palabras y 20% desde 10,000; el componente de voz automática se redondea por separado hacia arriba.",
        "⚠️ El precio exacto está listo. Confírmalo de nuevo antes de continuar.", "✅ Confirmar precio exacto", "❌ Cancelar tarea",
        "⌛ La confirmación del precio exacto caducó. Empieza de nuevo.",
    ),
    "pt": (
        "🧮 Palavras faturáveis",
        "0.5 Xu por palavra faturável; 10% de desconto a partir de 1,000 palavras e 20% a partir de 10,000; o componente de voz automática é arredondado para cima separadamente.",
        "⚠️ O preço exato está pronto. Confirme-o novamente antes de continuar.", "✅ Confirmar preço exato", "❌ Cancelar tarefa",
        "⌛ A confirmação do preço exato expirou. Comece novamente.",
    ),
    "fr": (
        "🧮 Mots facturables",
        "0.5 Xu par mot facturable ; remise de 10% dès 1,000 mots et de 20% dès 10,000 mots ; la composante de voix automatique est arrondie séparément à l’entier supérieur.",
        "⚠️ Le prix exact est prêt. Confirmez-le de nouveau avant de continuer.", "✅ Confirmer le prix exact", "❌ Annuler la tâche",
        "⌛ La confirmation du prix exact a expiré. Veuillez recommencer.",
    ),
    "de": (
        "🧮 Abrechenbare Wörter",
        "0.5 Xu pro abrechenbarem Wort; 10% Rabatt ab 1,000 Wörtern und 20% ab 10,000 Wörtern; die Komponente für automatische Stimmen wird separat aufgerundet.",
        "⚠️ Der genaue Preis steht fest. Bestätigen Sie ihn erneut, bevor Sie fortfahren.", "✅ Genauen Preis bestätigen", "❌ Auftrag abbrechen",
        "⌛ Die Bestätigung des genauen Preises ist abgelaufen. Bitte beginnen Sie erneut.",
    ),
    "hi": (
        "🧮 बिल योग्य शब्द",
        "प्रति बिल योग्य शब्द 0.5 Xu; 1,000 शब्द से 10% और 10,000 शब्द से 20% छूट; स्वतः आवाज़ घटक को अलग से ऊपर की ओर पूर्णांकित किया जाता है।",
        "⚠️ सटीक मूल्य तैयार है। आगे बढ़ने से पहले इसकी फिर से पुष्टि करें।", "✅ सटीक मूल्य की पुष्टि करें", "❌ कार्य रद्द करें",
        "⌛ सटीक मूल्य की पुष्टि की समय-सीमा समाप्त हो गई। कृपया फिर से शुरू करें।",
    ),
    "ru": (
        "🧮 Оплачиваемые слова",
        "0.5 Xu за оплачиваемое слово; скидка 10% от 1,000 слов и 20% от 10,000 слов; компонент автоозвучки отдельно округляется вверх.",
        "⚠️ Точная цена рассчитана. Подтвердите её ещё раз перед продолжением.", "✅ Подтвердить точную цену", "❌ Отменить задачу",
        "⌛ Срок подтверждения точной цены истёк. Начните заново.",
    ),
    "tr": (
        "🧮 Ücretlendirilen kelimeler",
        "Ücretlendirilen kelime başına 0.5 Xu; 1,000 kelimeden itibaren 10% indirim, 10,000 kelimeden itibaren 20% indirim; otomatik ses bileşeni ayrı olarak yukarı yuvarlanır.",
        "⚠️ Kesin fiyat hazır. Devam etmeden önce yeniden onaylayın.", "✅ Kesin fiyatı onayla", "❌ Görevi iptal et",
        "⌛ Kesin fiyat onayının süresi doldu. Lütfen yeniden başlayın.",
    ),
    "fil": (
        "🧮 Mga salitang sinisingil",
        "0.5 Xu sa bawat salitang sinisingil; 10% bawas mula 1,000 salita at 20% mula 10,000 salita; hiwalay na itinataas sa susunod na buong Xu ang bahagi ng awtomatikong boses.",
        "⚠️ Handa na ang eksaktong presyo. Kumpirmahin itong muli bago magpatuloy.", "✅ Kumpirmahin ang eksaktong presyo", "❌ Kanselahin ang gawain",
        "⌛ Lumagpas na sa oras ang pagkumpirma ng eksaktong presyo. Magsimulang muli.",
    ),
    "it": (
        "🧮 Parole fatturabili",
        "0.5 Xu per parola fatturabile; sconto del 10% da 1,000 parole e del 20% da 10,000 parole; il componente voce automatica viene arrotondato separatamente per eccesso.",
        "⚠️ Il prezzo esatto è pronto. Confermalo di nuovo prima di continuare.", "✅ Conferma il prezzo esatto", "❌ Annulla attività",
        "⌛ La conferma del prezzo esatto è scaduta. Ricomincia.",
    ),
    "id": (
        "🧮 Kata yang ditagihkan",
        "0.5 Xu per kata yang ditagihkan; diskon 10% mulai 1,000 kata dan 20% mulai 10,000 kata; komponen suara otomatis dibulatkan ke atas secara terpisah.",
        "⚠️ Harga pasti sudah tersedia. Konfirmasikan lagi sebelum melanjutkan.", "✅ Konfirmasi harga pasti", "❌ Batalkan tugas",
        "⌛ Konfirmasi harga pasti telah kedaluwarsa. Silakan mulai lagi.",
    ),
}


def test_auto_exact_pricing_and_receipt_copy_is_exact_native_for_all_17_locales():
    table = _aligned_copy("_PUBLIC_SUBDUB_DEEP_KEYS", "_PUBLIC_SUBDUB_DEEP_VALUES")
    assert set(AUTO_EXACT_COPY) == set(LOCALES)
    assert set(AUTO_EXACT_KEYS) <= set(table["en"])
    for locale, expected in AUTO_EXACT_COPY.items():
        actual = tuple(table[locale][key] for key in AUTO_EXACT_KEYS)
        assert actual == expected
        assert all(marker in actual[1] for marker in ("0.5", "1,000", "10%", "10,000", "20%"))
        if locale not in {"vi", "en"}:
            assert actual != tuple(table["en"][key] for key in AUTO_EXACT_KEYS)
            assert actual != tuple(table["vi"][key] for key in AUTO_EXACT_KEYS)


def _auto_pricing_receipt_branches() -> tuple[str, list[tuple[str, str]]]:
    source = _function_source("video_dubbing_confirm_text")
    tree = ast.parse(source)
    nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "auto_pricing"
    ]
    assert len(nodes) == 2

    def statements_source(statements: list[ast.stmt]) -> str:
        return "\n".join(ast.get_source_segment(source, node) or "" for node in statements)

    return source, [
        (statements_source(node.body), statements_source(node.orelse))
        for node in nodes
    ]


def test_auto_receipt_uses_native_word_and_total_labels_without_legacy_labels():
    _, branches = _auto_pricing_receipt_branches()
    native_keys = set(_literal("_PUBLIC_SUBDUB_DEEP_KEYS"))
    for auto_source, _ in branches:
        copy_keys = set(re.findall(r"copy\[['\"]([^'\"]+)['\"]\]", auto_source))
        assert "characters:" not in auto_source and "total:" not in auto_source
        assert {"voice_auto_billable_words", "voice_auto_price_rule"} <= copy_keys <= native_keys
        assert any("total" in key for key in copy_keys)


def test_manual_receipt_keeps_legacy_character_pricing_behind_manual_guard():
    source, branches = _auto_pricing_receipt_branches()
    tree = ast.parse(source)
    guards = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == "auto_pricing"
    ]
    manual_sources = [manual_source for _, manual_source in branches]
    guarded_source = "\n".join(
        ast.get_source_segment(source, statement) or ""
        for guard in guards for statement in guard.body
    )
    assert len(guards) == 1 and "characters:" in guarded_source
    assert source.count("characters:") == guarded_source.count("characters:")
    assert all(all(label in manual for label in ("discount:", "total:")) for manual in manual_sources)


def test_public_pricing_uses_native_auto_word_tiers_for_all_17_locales():
    source = _function_source("video_dubbing_pricing_text")
    copy_keys = set(re.findall(r"copy\[['\"]([^'\"]+)['\"]\]", source))
    table = _aligned_copy("_PUBLIC_SUBDUB_DEEP_KEYS", "_PUBLIC_SUBDUB_DEEP_VALUES")
    rules = {locale: table[locale]["voice_auto_price_rule"] for locale in LOCALES}

    assert "public_subdub_deep_copy" in source
    assert {"voice_auto_speaker", "voice_auto_price_rule"} <= copy_keys
    assert not re.search(r"normalize_user_language\([^)]*\)\s*[!=]=\s*['\"]vi['\"]", source)
    assert all(all(marker in rule for marker in ("0.5", "1,000", "10%", "10,000", "20%")) for rule in rules.values())
    assert all(rules[locale] not in {rules["en"], rules["vi"]} for locale in LOCALES if locale not in {"en", "vi"})


def test_public_pricing_preserves_native_manual_voice_labels_and_discount_rule():
    source = _function_source("video_dubbing_pricing_text")
    copy_keys = set(re.findall(r"copy\[['\"]([^'\"]+)['\"]", source))
    table = _aligned_copy("_PUBLIC_SUBDUB_DEEP_KEYS", "_PUBLIC_SUBDUB_DEEP_VALUES")
    required = {
        "pricing_dub_default",
        "pricing_dub_saved",
        "pricing_manual_discount",
    }

    assert required <= copy_keys
    for locale in LOCALES:
        row = table[locale]
        assert all(str(row[key]).strip() for key in required)
        assert all(
            marker in row["pricing_manual_discount"]
            for marker in ("10", "1", "20")
        )
