# Homex — Figma ↔ Backend API tizimli solishtiruv

Ikkala Figma **Chrome orqali ochib, ekranma-ekran ko'rib chiqildi** (2026-07-06 sessiyasi):
- **Dashboard** — `Homex-Dashboard` (Main page: 17 bo'lim)
- **App** — `Homex-App` (3 page: **Mijoz**, **Usta**, **Web App**)

> Verifikatsiya darajasi:
> - **Piksel-tekshirilgan** (bu sessiyada zoom bilan o'qildi): Dashboard → *Ombor*, *Buyurtmalar*, *Marketplace*; App → *Mijoz* va *Usta* ekran ro'yxati (frame nomlari).
> - **Inventar + endpoint darajasida**: qolgan bo'limlar frame nomlari + to'liq backend API xaritasi asosida.

Belgilar: ✅ bor va mos · 🟡 maydon darajasida tekshirish kerak · ❌ API yo'q (kamchilik) · 🆕 shu ish davomida qo'shildi

---

## 1. Dashboard (Homex-Dashboard Figma)

Figma bo'limlari (Layers): Dashboard · Buyurtma · Jonli Kuzatuvlar · Xaritalar · Ustalar · Mijozlar · Xodim · Xizmatlar va Narxlar · Marketplace · Tariflar · Moliya Hisobotlar · Xarajatlar · **Ombor** · Xabarlar · Sozlamalar · Login.

| Figma bo'limi | API | Holat |
|---|---|---|
| Login | `dashboard-auth-login/refresh/logout/me` | ✅ |
| Dashboard (statistika) | `dashboard-overview/stats/meta/orders-by-service/orders-weekly/income-dynamics/income-expense/today-orders` | ✅ |
| **Buyurtma** (tab: Barchasi/Yangi/Yo'lda/Bajarilmoqda/Yakunlangan/Bekor) | `dashboard-orders` (`?status`,`?category`🆕), `orders-board`, `order-detail/status/assign/tracking`, `order-assistants` | ✅ — piksel-tekshirilgan. Ustunlar: Sana·Mijoz·Xizmat·Usta·Shogird·Sum·Status. "Usta biriktirish" va "Shogird biriktirish" modallari bor |
| Jonli (Live) | `dashboard-live-streams/live-stream-detail/archived-videos` | 🟡 faqat dashboard tomonda (app-da yo'q — 4-bandga qarang) |
| Xarita (Map) | `dashboard-map-masters` | ✅ |
| Ustalar (ro'yxat/ariza/bloklangan/qo'shish/o'chirish) | `dashboard-masters`, `masters-available/applications/blocked`, `master-detail/location/status/orders/wallet/block`, `masters-specializations` | ✅ |
| Mijozlar | `dashboard-clients/client-detail/client-orders/client-stats` | ✅ |
| Xodim (Staff) | `dashboard-staff/staff-detail` | ✅ |
| Xizmatlar va Narxlar | `dashboard-service-categories`, `services` (`?category`), `service-prices` | ✅ |
| **Marketplace** (tab: Mahsulotlar/Buyurtmalar/Buyurtmalar tarixi) | `dashboard-market-categories`, `market-products` (`?category`), `market-product-images`, `market-orders` (`?category`🆕) | ✅ — piksel-tekshirilgan (mahsulot grid + kategoriya boshqaruvi) |
| Tariflar | `dashboard-tariffs/tariff-features` | ✅ |
| Moliya | `dashboard-wallet-transactions/withdraw-requests/finance-summary/finance-report`, `cash-handovers/accept/reject` | ✅ |
| Xarajatlar | `dashboard-expenses/company-expenses/warehouse-expenses` | ✅ |
| **Ombor** (Kategoriya filtri + Tannarx/Sotuv narxi ustunlari + "Ombor qiymati" kartasi) | `dashboard-warehouse-stats` (+`total_value`🆕), `warehouse-categories`🆕, `warehouse-products` (`?category`🆕), `stock-movements`, `master-inventory` | ✅ 🆕 — piksel-tekshirilgan (pastga qarang) |
| Xabarlar (Support) | `dashboard-support-threads/messages/message-read`, `notifications/unread-count/read-all` | ✅ |
| Sozlamalar | `dashboard-integration-settings` | ✅ |

**Ombor ekrani (piksel-tekshirilgan):** filtr qatori = `Qidiruv (Nomi bo'yicha)` + **`Kategoriya` (default "Barchasi")** + `Status` + `Tozalash`. Jadval ustunlari = **Mahsulot nomi · Kategoriya · Qoldiq · Tannarx · Sotuv narxi · Status · Amallar**. Kartalar: Jami mahsulotlar · Kirimlar · **Ombor qiymati**. → Backend shu sessiyada shu dizaynga moslab qurildi (kategoriya + narxlar + `total_value`).

---

## 2. Mijoz app (Homex-App → Mijoz page)

Ekranlar (Figma frame nomlari orqali tasdiqlangan): Auth · Home (+ Order Status) · Searching · Order/Create (ko'p bosqichli) · **Live View** · **SOS** · Notifications · Orders · My tools · Market/Sell/Search · Profile/Edit/Logout · Tariflar · Location/Add Location · Language · Support · Privacy/Delete.

| Figma ekrani | API | Holat |
|---|---|---|
| Auth / Create password / OTP | `client-send-otp/verify-otp/register/refresh/logout` | ✅ |
| Home (+ order status) | `client-home/map-config/recent-orders` | ✅ |
| Searching (usta qidirish) | `client-nearby-masters` (`?specialization`) | ✅ |
| Order / Create (bosqichlar) | `client-orders` (`?status`, `?category`🆕) | ✅ |
| Order tracking / detail / cancel / rate / pay | `client-order-track/detail/cancel/rate/pay` | ✅ |
| Receipt (chek) | `client-order-receipt-download` | ✅ |
| **SOS** | — | ❌ **API yo'q** (dizaynda bor) |
| **Live View** | — | ❌ **client API yo'q** (jonli faqat dashboardda) |
| Notifications | Admin (DB): `client-notifications/read/read-all` + unread count. Order status realtime: `/ws/client/notifications/` (WS) + FCM, DB'siz — alohida tizim. | ✅ |
| My tools (Uskunalar) | `client-devices/device-locations/device-order` | ✅ |
| Market / Sell / Search | `client-market-products/orders/favorites/listing-create/categories/search` (`?category`, orders+favorites `?category`🆕) | ✅ |
| Profile / Edit / Language | `client-profile` | ✅ |
| Tariflar | `client-tariffs/tariff-subscribe` | ✅ |
| Location / Add Location | `client-addresses/address-detail` | ✅ |
| Support | `client-support/support-chat/support-messages` | ✅ |
| Privacy / Delete account | `privacy-policy`, `client-delete` | ✅ |

---

## 3. Usta app (Homex-App → Usta page)

Ekranlar (frame + layer nomlari orqali): Auth/Create Password · Home · Order/Order info/Order Track/Complete · **Sklad** · **Wallet** · **Cash release** · **Review** · **Xarajatlar** · Add new tool · Profile/Edit/Language/Logout · Support · Privacy/Delete · Notification · Certificates.

| Figma ekrani | API | Holat |
|---|---|---|
| Auth / Create password | `master-register/login/refresh/logout` | ✅ |
| Home (statistika) | `master-home-stats/app-bootstrap` | ✅ |
| Buyurtmalarim / accept/start/reject/complete | `master-orders` (`?tab`,`?date`,`?category`🆕), `order-detail/accept/start/reject/complete/receipt-confirm` | ✅ |
| Order tracking (real-time) | `master-location-update` + WS `/ws/master/tracking/` | ✅ |
| Sklad / Add new tool | `master-inventory` (`?category`🆕), `low-stock/detail/use` | ✅ |
| Wallet | `master-wallet/transactions/stats` | ✅ |
| Cash release (Naqd topshirish) | `master-wallet-withdraw` → admin `cash-handover accept` | ✅ |
| Review | `master-reviews/reviews-summary` | ✅ |
| Xarajatlar | `master-expenses/expense-detail` | ✅ |
| Profile / Edit / Language / Logout | `master-profile/settings/language/me` | ✅ |
| Certificates / Documents | `master-certificates/documents` | ✅ |
| Support / Privacy / Delete | `master-support`, `master-delete` | ✅ |
| **Live stream (broadcast)** | — | ❌ **master API yo'q** (jonli faqat dashboardda ko'riladi) |

---

## 4. Haqiqiy kamchiliklar (Figma'da bor — API'da yo'q)

1. **Jonli translyatsiya (Live) — app tomoni yo'q.** ⏸ **MVP'da kerak emas deb qaror qilindi — hozircha e'tiborsiz qoldirildi.** (`DashboardLiveStream` modeli + dashboard `live-streams/archived-videos` bor; client "Live View" ko'rish va usta broadcast API'lari keyinroq.)
2. **SOS (client).** Mijoz app'ida **SOS** ekrani bor, lekin butun kodda `sos/emergency/panic` — model ham, endpoint ham yo'q.
3. **Usta market ruxsati.** Client market'da `orders/favorites/listings` — `IsClient` permission (usta token bilan ishlamaydi). Agar usta app'ida market kerak bo'lsa — endpoint/permission kerak. (Usta page'da alohida market ekrani tasdiqlanmadi; asosan Xarajatlar bor.)

## 4a. Shu sessiyada tuzatilgan kamchiliklar 🆕

- **Ombor kategoriyasi** — Figma'da bor edi, backendda yo'q edi. Endi: `WarehouseCategory` modeli + list API + `?category` filtri (dashboard/admin/master).
- **Ombor narxlari** — Figma'dagi *Tannarx/Sotuv narxi/Ombor qiymati* uchun `cost_price`, `sale_price`, `stock_value` + stats `total_value` qo'shildi.
- **Category filtri** — barcha category-bearing ro'yxatlarga `?category=<id|slug>` qo'shildi (Order, MarketOrder, Favorites, Warehouse) — client/master/dashboard/internal.

## 4b. 🟡 Maydon darajasida keyin tekshirish

- Order "Tasdiqlash" — bonus summa, to'lov turi, ustani baholash maydonlari (piksel).
- Wallet — "Bu hafta / Oyiga" trend statistikasi alohida qaytadimi.

---

## 5. Category list API + filter (bajarilgan ish)

Har bir "category qatnashgan" qism uchun **category-list API** (mavjud yoki yangi) + **`?category=<id|slug>` filtri** (`all`/`hammasi`/`barchasi` = filtrsiz). Umumiy yordamchi: `apps/common/filters.py → filter_by_category`.

| Domen | List API | Filter qo'shilgan ro'yxatlar |
|---|---|---|
| Xizmat (ServiceCategory) | client `services/`, dashboard `services/categories/`, internal `services/categories/` | client-orders, master-orders, dashboard-orders/board/client-orders/master-orders, internal order-collection/board/export/client-orders/master-orders/schedule |
| Market (MarketCategory) | client `market/categories/`, dashboard `market/categories/` | client market-orders + favorites, dashboard market-orders |
| Ombor (WarehouseCategory 🆕) | dashboard `warehouse/categories/`, admin `warehouse/categories/` | dashboard & admin warehouse-products, master inventory |

O'zgargan fayllar: `apps/common/filters.py` (yangi), `apps/orders/views.py`, `apps/market/views.py`, `apps/services/views.py`, `apps/dashboard/{views,serializers,urls}.py`, `apps/internal_api/views.py`, `apps/warehouse/{models,serializers,views,admin,admin_urls}.py` (+2 migration), `tests/test_category_filters.py` (yangi).
