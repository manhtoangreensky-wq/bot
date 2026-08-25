# P0 SubDub Auto 2 giọng / nhiều giọng — source gate 2026-08-26

## Trạng thái đo được trước push

- Base hậu-rebase đã kiểm: `d43343a0157ba6e6916e92b97ee2dccb1ddfb168`.
- Candidate được giữ trong một local rollback commit; PR head sẽ được ghi sau
  khi rebase lên `origin/main` mới nhất.
- Candidate chưa push, chưa merge, chưa deploy và chưa được công nhận LIVE.
- Pytest tập trung: `29 passed, 1 warning in 924.54s`; warning duy nhất là
  `google.genai` deprecation.
- `py_compile` thành công cho đúng 3 runtime file: `bot.py`,
  `auto_speaker.py`, `auto_multi_speaker.py`.
- `git diff --check`: exit `0`.
- Gate hậu-rebase trên VPS production venv: `29 passed in 89.73s`, compile
  exit `0`, diff-check exit `0`.
- Provider call: `0`; wallet mutation: `0`; Telegram callback/upload: `0`.

## Contract hiện tại

Hai lựa chọn công khai là hai lane riêng nhưng dùng chung pricing, settlement,
TTS, mux và delivery đã được bảo vệ:

| Nút | Marker | Blackbox |
| --- | --- | --- |
| `👥 Tự động 2 giọng` | không có `auto_speaker_lane` | `auto_speaker` |
| `👥 Tự động nhiều giọng` | `auto_speaker_lane="multi"` | `auto_multi_speaker` |

Hai nút nằm cùng một hàng. Confirmation phải ghi đúng lane đã chọn.

Lane 2 giọng phục hồi đúng hai điều kiện của checkpoint từng chạy thật tại PR
`#853`, SHA `7b4053a`:

1. PCM filter `highpass=70,lowpass=320,afftdn=nr=6:nf=-50`.
2. Chấp nhận một pitch frame mạnh cho đoạn thoại ngắn.

Lane nhiều giọng giữ blackbox riêng. Khi diarization trả thiếu đúng 2 nhãn cho
fixture nhiều người nói, lane này chỉ tách thêm nhãn khi cùng một nhãn có ít
nhất 2 cue low + 2 cue high và median pitch cách nhau ít nhất `30 Hz`. Mọi bằng
chứng mơ hồ vẫn fail-closed trước TTS/charge.

## Đối chiếu tài liệu thiết kế ngày 2026-08-24

Ba giả định trong spec/plan gốc không còn đúng và không được dùng để rollback:

1. “Lane 2 giọng giữ cấu hình pre-PR #853” trái với job thật từng PASS nhờ
   filter + one-frame tại PR #853; PR #860 đã làm hồi quy hai điều kiện này.
2. “Lane multi không invent khi provider trả 2 nhãn” không đáp ứng fixture
   Owner đã chọn; contract mới chỉ refine từ 2 thành 3+ khi có acoustic proof
   chặt như mô tả trên.
3. `Download.mp4` không phải fixture live được phép. Fixture duy nhất là
   `C:\Users\toann\Downloads\test sub\test nhiều giọng.mp4`.

## Fixture nhiều giọng đã đánh giá cục bộ

- SHA-256: `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`.
- Dung lượng: `9,869,032` byte; thời lượng: `133.375420` giây.
- Video: AV1 `854x480`, `30 fps`; audio: AAC stereo `44.1 kHz`.
- Sidecar: `36` cue, `0` overlap, tổng `57.91` giây thoại.
- Refined labels: `3`; phân bố cue `16 / 17 / 3`; label ít nhất có `9.71`
  giây thoại.

Kết luận: fixture đủ chuẩn làm hard-regression và live test nhiều giọng vì nó
bắt được lỗi under-cluster thật. Nó không phải benchmark duy nhất cho độ chính
xác diarization vì confidence ở một số cue ngắn thấp.

## Case tester và thứ tự live bắt buộc

1. Deploy đúng merge SHA, bot + worker cùng SHA và generation accepted.
2. Live `Tự động 2 giọng` trước; chỉ PASS khi có MP4 thật được Telegram giao,
   audio hợp lệ, receipt xanh và `charged_xu=0`. Lưu PR/SHA/job/artifact làm mốc
   rollback.
3. Chỉ sau case 2 delivered mới upload đúng fixture hash ở trên vào
   `Tự động nhiều giọng`.
4. Multi chỉ PASS khi có MP4 + SRT thật, 3+ speaker labels, số voice distinct
   bằng số speaker, receipt hiện loại lane + giá phụ đề + giá lồng tiếng, một
   job/outbox và `charged_xu=0`.

Không tạo nhãn, issue hoặc GitHub Project trong đợt này: đó là external mutation
ngoài phạm vi sửa P0 và cần Owner duyệt riêng trước khi tạo thật.
