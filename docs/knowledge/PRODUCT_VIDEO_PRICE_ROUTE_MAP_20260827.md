# Product Video Price + Provider Route Map

Nguon su that hien hanh: config/product_video_price_route_map_20260827.json.
Chot ngay 27/08/2026. Khong duoc sap xep provider bang tri nho.

## Luat

- Gia khach hang giu dung bang moi: thap nhat 80 Xu/canh, cao nhat 2.360 Xu/canh.
- So sanh provider chi khi cung thoi luong va du capability cua chat luong.
- Trong cac route du dieu kien, tong chi phi bao thu 2 canh thap hon dung truoc.
- Video live chi PASS khi MP4 co audio stream nghe duoc. Model video khong co audio phai qua add-on/final mux da duoc duyet.
- 2 canh duoc giam 10% phan gia Video.
- Ty gia snapshot: ShopAIKey 3.250 VND/USD; Key4U 3.000 VND/USD.

## Bang gia khach hang (sap tang dan)

| Tier | Chat luong | Giay/canh | Xu/canh | 2 canh truoc giam | Giam 10% | Khach tra |
|---:|---|---:|---:|---:|---:|---:|
| 400 | Nhanh gon | 8 | 80 | 160 | 16 | **144 Xu** |
| 500 | Chuyen dong on dinh | 5 | 110 | 220 | 22 | **198 Xu** |
| 600 | Chuyen dong co am thanh | 5 | 160 | 320 | 32 | **288 Xu** |
| 200 | Can bang ro net | 5 | 200 | 400 | 40 | **360 Xu** |
| 300 | Tieu chuan co am thanh | 5 | 220 | 440 | 44 | **396 Xu** |
| 700 | Canh dai co am thanh | 15 | 220 | 440 | 44 | **396 Xu** |
| 800 | Cao cap linh hoat | 10 | 370 | 740 | 74 | **666 Xu** |
| 1000 | Dien xuat chan that | 6 | 370 | 740 | 74 | **666 Xu** |
| 1200 | Da goc may | 8 | 1.260 | 2.520 | 252 | **2.268 Xu** |
| 1500 | Dien anh nhieu canh | 10 | 2.360 | 4.720 | 472 | **4.248 Xu** |

## Thu tu provider sau doi chieu gia live

| Tier | Primary | Chi phi 2 canh | Fallback du dieu kien | Chi phi 2 canh | Ghi chu |
|---:|---|---:|---|---:|---|
| 400 | ShopAIKey veo3.1-fast | 4.550 VND | Key4U veo_3_1-fast | 21.151 VND | Kling std + audio la 1,530 USD/giay = 73.441 VND/2 canh, dat hon VEO. |
| 500 | ShopAIKey veo3.1-fast | 4.550 VND | Key4U kling-video std + audio | 45.900 VND | Kling tinh theo giay: 1,530 USD/s x 5s/canh. |
| 600 | ShopAIKey veo3.1-fast | 4.550 VND | Key4U kling-video std + audio | 45.900 VND | Kling tinh theo giay: 1,530 USD/s x 5s/canh. |
| 200 | ShopAIKey grok-video-3 | 2.600 VND | Key4U pixverse-video V6 720p + audio | 14.771 VND | ShopAIKey primary phai qua live audio gate. |
| 300 | ShopAIKey grok-video-3 | 2.600 VND | Key4U grok-imagine-video 720p | 12.600 VND | ShopAIKey primary phai qua live audio gate. |
| 700 | Key4U kling-video pro + audio | 183.601 VND | Khong co | - | 2,040 USD/s x 15s/canh. Gia ban 2 canh 39.600 VND => lo 144.001 VND. |
| 800 | Key4U kling-video pro + audio | 122.401 VND | Khong co | - | 2,040 USD/s x 10s/canh. Gia ban 2 canh 66.600 VND => lo 55.801 VND. |
| 1000 | Key4U MiniMax-Hailuo-2.3 | 19.200 VND | Khong co | - | Video 6s; audio phai duoc add-on/mux va probe. |
| 1200 | ShopAIKey veo3.1-pro-components | 22.750 VND | Key4U viduq3-mix 1080p | 72.001 VND | Cung 8s reference/multi-angle. |
| 1500 | Key4U doubao-seedance-1-0-pro-250528 | 137.700 VND | Khong co | - | ShopAIKey Veo Pro re hon nhung khong dat exact 10s multi-shot. |

## Nguon do duoc

- ShopAIKey gia live: https://api.shopaikey.com/pricing.
- ShopAIKey hop dong Video: https://shopaikey.com/docs/veo-video.
- Key4U gia live: https://key4u.vn/api/pricing_v3.
- Key4U model live: https://api.key4u.vn/v1/models.
- Key4U VEO submit/poll: https://docs.key4u.vn/api-41690843 va https://docs.key4u.vn/api-41690898.
- Key4U Kling submit/poll: https://docs.key4u.vn/api-41690856 va https://docs.key4u.vn/api-41690863.
- Key4U Hailuo submit/poll: https://docs.key4u.vn/api-41690868 va https://docs.key4u.vn/api-41690869.
- Key4U pricing endpoint map: `gygkmi -> POST /v1/videos`; `m0kp1x -> POST /kling/v1/videos/text2video`; `1au654 -> POST /minimax/v1/video_generation`.
- Kling v3 wire `sound` dung enum `on`/`off`; bool chi duoc dung noi bo trong catalog.
- Kling 3.0 tinh phi theo giay; khong duoc doc cot gia Kling thanh gia/canh.

## Gate cap nhat

1. Cap nhat JSON nguon su that truoc.
2. Ghi timestamp va URL evidence.
3. Chay comparator gia/route.
4. Chi doi config/product_video_model_routing.json neu primary/fallback trong file nay doi.
5. Live test dung tier, 2 canh, audio, artifact, delivery va 0 Xu.
