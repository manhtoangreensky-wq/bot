# P0 SubDub — checklist 2 giọng trước, nhiều giọng sau (2026-08-26)

Nguồn trạng thái bền vững chi tiết: `.agents/state/p0-subdub-multi-blackbox.yaml`.
Báo cáo này chỉ ghi số đã đo; `PASS` live chỉ được ghi khi Telegram đã giao
artifact thật.

## Thứ tự khóa

1. `Tự động 2 giọng` phải chạy trên cả `Phụ đề + Lồng tiếng` và
   `Lồng tiếng video`.
2. Mỗi speaker được phân loại độc lập. Hỗ trợ nam–nam, nam–nữ, nữ–nữ;
   bằng chứng mơ hồ phải chuyển manual, không ép một nam/một nữ.
3. Chỉ sau hai lane 2 giọng PASS mới chạy `Tự động nhiều giọng`.
4. Nếu live fail: `READ → RED → minimal fix → GREEN → review → ship → live lại`.

## Mốc rollback và correction đã xác minh

| Mốc | Bằng chứng đo được |
| --- | --- |
| PR #842 / `71c7e881` | Job `#7BC3037DF8` đã giao video message `26895`, receipt `26896`, charged `0 Xu` |
| PR #883 / `b9b0cc3` | Khôi phục đúng classifier/PCM của mốc trên; deploy run `32929180418` SUCCESS |
| PR #885 / `176f3c2` | Giữ exact component price qua prepare gate; invoice không còn lồng tiếng giả `0 Xu` |
| PR #887 / `371a422` | Auto combo giao thêm đúng một SRT sau MP4 |
| PR #889 / `f16fb75` | Bỏ forced-pair PR #886; phân loại từng speaker độc lập |

PR #853 không phải mốc rollback video đúng: filter/one-frame từ mốc này tạo
pitch drift và đã bị PR #883 loại bỏ. Không rollback toàn bộ `bot.py`; chỉ sửa
boundary có RED tái hiện được.

## Contract gender/cast đã khóa ở PR #889

- Chỉ nhận đúng `2` speaker labels.
- Mỗi label cần ít nhất `2` mẫu pitch đủ confidence.
- Weighted support cho register được chọn phải đạt `0.60`.
- Ba case nam–nam, nam–nữ, nữ–nữ đều có regression.
- Tie `2-vs-2`, thiếu bằng chứng, hoặc `3+` labels fail-closed về manual.
- RED: `4 failed, 1 passed in 112.58s`.
- GREEN: `5 passed in 7.59s`.
- Protected comparison: `NEW_FAILURES=0`.
- Runtime trước correction hiện tại: bot + owner worker cùng SHA
  `f16fb75fc3093683bfe707b17e6c8b2bf3bd67d7`; deploy run `32950303038`
  SUCCESS.

## Fixture live bắt buộc cho lane 2 giọng

- File: `C:\Users\toann\Downloads\test sub\2 giọng nam nữ.mp4`.
- Size: `4,284,017` byte.
- SHA-256: `85c8793d197cf2782bb554d46282e82a83bcb062a0483e412a0ca1da668f9f51`.
- Acceptance cast: đúng một speaker vào male pool và một speaker vào female
  pool từ evidence riêng của từng speaker.

`test 2 giọng.mp4` (`a89b16b…`) chỉ còn là fixture lịch sử. `Download.mp4` bị
cấm cho mọi live acceptance còn lại.

## Failure loop hiện tại — status panel trước ASR

Attempt đúng fixture trên runtime `f16fb75` dừng trước ASR/sidecar/classifier:

```text
_run_subdub_public_final_background
→ handle_video_dubbing_callback
→ safe_edit_or_send
→ query.edit_message_text
→ telegram.error.TimedOut
```

Root cause: status-panel `received_file` đầu tiên của background không có
best-effort boundary, nên Telegram WriteTimeout bị outer runner hiểu thành lỗi
pipeline và terminalize `failed_no_charge`.

Correction branch: `fix/p0-subdub-status-timeout`.

- RED: `1 failed, 1 warning in 711.25s`; pipeline call count `0`, exact stack
  dừng ở `bot.py:253596`.
- GREEN lần 1: `1 passed, 1 warning in 718.63s`; pipeline tiếp tục đúng một lần.
- Review RED: `2 failed, 1 warning in 12.97s`; chưa gửi replacement status và
  chưa persist replacement message id.
- Final GREEN: `2 passed, 1 warning in 10.24s`; replacement thành công được
  persist trước pipeline, replacement timeout vẫn tiếp tục pipeline đúng một lần.
- Protected batch cuối: `17 passed, 1 warning in 12.37s`.
- `py_compile bot.py`: exit `0`.
- `git diff --check`: exit `0` (chỉ cảnh báo CRLF).
- Provider call: `0`; wallet mutation: `0`; Telegram callback/upload: `0`.

Source correction đã vượt gate local và sẵn sàng ship. Chưa deploy và chưa
claim live PASS; live chỉ bắt đầu sau khi bot + owner worker cùng merge SHA.

## Giá và artifact acceptance

### Phụ đề + Lồng tiếng

- Telegram phải giao MP4 + SRT.
- Receipt phải có `Tự động 2 giọng`, giá phụ đề, giá lồng tiếng, tổng.
- Giá lồng tiếng tính từ `0.5 Xu / billable word`; không hiển thị `0 Xu` khi
  word count chưa biết.
- Admin vẫn hiển thị đầy đủ giá niêm yết nhưng `charged_xu=0`, không tạo wallet
  transaction.

### Lồng tiếng video

- Telegram phải giao MP4 + receipt.
- Receipt phải có `Tự động 2 giọng`, giá lồng tiếng và tổng.
- Cùng independent classifier/cast contract với combo.

## Fixture nhiều giọng — chỉ được chạy sau 2 giọng PASS

- File: `C:\Users\toann\Downloads\test sub\test nhiều giọng.mp4`.
- SHA-256: `83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e`.
- Size: `9,869,032` byte; duration `133.375420` giây.
- Video AV1 `854x480` `30 fps`; audio AAC stereo `44.1 kHz`.
- Audit local: `36` cue, `0` overlap, `57.91` giây thoại; refined labels `3`,
  phân bố cue `16 / 17 / 3`.

Fixture này đủ làm hard-regression under-cluster, nhưng chưa được phép live khi
hai lane 2 giọng chưa terminal PASS.

## Tài liệu cũ không còn là nguồn deploy truth

`docs/reports/SUBDUB_CANONICAL_CURRENT.md` còn ghi Railway và runtime ngày
2026-07-26. Production hiện là Ubuntu VPS `tg.toanaas.vn`; vì vậy file cũ chỉ
dùng tham khảo lịch sử. Nguồn truth của task này là checklist state, PR/merge
SHA, GitHub Actions deploy và kiểm chứng bot + owner worker trên VPS.

## Trạng thái cuối của checklist lúc viết báo cáo

- SPEC-01 rollback forensic: `completed`.
- SPEC-02 exact rollback: `completed`.
- SPEC-03 ship/deploy rollback: `completed`.
- SPEC-04 hai lane 2 giọng: `failure_loop`; chưa PASS.
- SPEC-05 nhiều giọng: `blocked_by_order`.
- SPEC-06 báo cáo cuối: `pending`.

Không tạo label/issue/Project mới trong correction P0 này. Repo đã có `2` issue
mở và `4` PR mở khi kiểm tra GitHub; external tester mutations không thuộc
minimal code footprint của lỗi status timeout.
