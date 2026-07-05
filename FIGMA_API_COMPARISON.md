# Homex — Figma ↔ API tizimli solishtiruv

Ikkala Figma (App: Mijoz + Usta sahifalari, Dashboard) Chrome orqali ochib ko'rildi va barcha bo'limlar backend API'lar bilan solishtirildi.

> Eslatma: Figma dizayn — WebGL canvas. Skrinshot olish mumkin, lekin matn/qatlamlarni "data" sifatida o'qib bo'lmaydi. Shuning uchun solishtiruv **endpoint darajasida** (aniq) + ekran nomlari + siz bergan batafsil skrinshotlar asosida. Piksel darajasidagi maydon farqlari uchun "tekshirish kerak" deb belgilandi.

Belgilar: ✅ bor va mos · 🟡 bor, lekin maydon/xatti-harakatni tekshirish kerak · ❌ API yo'q (kamchilik) · 🆕 shu sessiyada qo'shildi

---

## 1. Dashboard (Homex-Dashboard Figma)

| Figma bo'limi | API | Holat |
|---|---|---|
| Login | `dashboard-auth-login/refresh/logout/me` | ✅ |
| Dashboard (statistika) | `dashboard-overview/stats/meta/orders-by-service/orders-weekly/income-dynamics/income-expense/today-orders` | ✅ |
| Buyurtma (Orders) | `dashboard-orders/orders-board/order-detail/order-status/order-assign/order-tracking` | ✅ |
| Jonli (Live) | `dashboard-live-streams/live-stream-detail/archived-videos` | 🟡 faqat dashboard tomonda (app-da yo'q — pastga qarang) |
| Xarita (Map) | `dashboard-map-masters` | ✅ |
| Ustalar → ro'yxat / boshqarish | `dashboard-masters`, `masters-available`, `master-detail/location/status/orders/wallet`, `masters-specializations` | ✅ |
| Ustalar → **So'rov qoldirganlar** | `dashboard-masters-applications` | ✅ 🆕 |
| Ustalar → **Bloklanganlar** | `dashboard-masters-blocked` | ✅ 🆕 |
| Ustalar → **Bloklash / O'chirish / Qo'shish** | `dashboard-master-block`, `master-detail (DELETE)`, `masters (POST)` | ✅ (block 🆕) |
| Mijozlar (Clients) | `dashboard-clients/client-detail/client-orders/client-stats` | ✅ |
| Xodim (Staff) | `dashboard-staff/staff-detail` | ✅ |
| Xizmat (Services) | `dashboard-service-categories/services/service-prices` | ✅ |
| Market | `dashboard-market-categories/products/product-images/orders` | ✅ |
| Tariflar | `dashboard-tariffs/tariff-features` | ✅ |
| Moliya → wallet / withdraw / hisobot | `dashboard-wallet-transactions/withdraw-requests/finance-summary/finance-report` | ✅ |
| Moliya → **Masterdan naqd pul qabul qilish** | `dashboard-cash-handovers/accept/reject` | ✅ 🆕 |
| Xarajat (Expenses) | `dashboard-expenses/company-expenses/warehouse-expenses` | ✅ |
| Ombor (Warehouse) | `dashboard-warehouse-stats/products/stock-movements/master-inventory` | ✅ |
| Xabar (Notifications) | `dashboard-notifications/unread-count/read-all` | ✅ |
| Sozlamalar (Settings) | `dashboard-integration-settings` | ✅ |

**Dashboard xulosa:** endpoint darajasida to'liq qamrab olingan. Ustalar (applications/blocked/block) va Moliya (cash handover) bo'limlari — Figmadagi "So'rov qoldirganlar / Bloklanganlar / Bloklash / Masterdan naqd pul" ekranlariga **aynan mos** (shu sessiyada qurildi).

---

## 2. Client app (Mijoz sahifasi)

| Figma ekrani | API | Holat |
|---|---|---|
| Auth / Create password / OTP | `client-send-otp/verify-otp/register/refresh/logout` | ✅ |
| Home (+ order status) | `client-home/map-config/recent-orders` | ✅ |
| Search (usta qidirish) | `client-nearby-masters` (+ `?specialization=`) | ✅ |
| Order yaratish / Tasdiqlash | `client-orders` (device inline/`device_id` bilan) | ✅ 🆕(device) |
| Order tracking / detail / cancel / rate / pay | `client-order-track/detail/cancel/rate/pay` | ✅ |
| Receipt (chek) | `client-order-receipt-download` | ✅ |
| **SOS** | — | ❌ **API yo'q** |
| **Live View (jonli)** | — | ❌ **client API yo'q** (live faqat dashboardda) |
| Notifications | `client-notifications/read/read-all` | ✅ |
| My tools (Uskunalar) | `client-devices/device-locations/device-order` | ✅ 🆕 |
| Market / Sell / Search | `client-market-products/orders/favorites/listing-create/categories/search` | ✅ |
| Profile / Edit profile | `client-profile` (language shu yerda) | ✅ |
| Tariffs | `client-tariffs/tariff-subscribe` | ✅ |
| Location / Add location | `client-addresses/address-detail` | ✅ |
| Language | `client-profile` (PATCH language) | ✅ |
| Support | `client-support/support-chat/support-messages` | ✅ |
| Privacy / Delete account | `privacy-policy`, `client-delete` | ✅ |

**Client kamchiliklari:** **SOS** ekrani (favqulodda tugma) va **Live View** (jonli video ko'rish) uchun API yo'q.

---

## 3. Master app (Usta sahifasi)

| Figma ekrani | API | Holat |
|---|---|---|
| Auth / Create password | `master-register/login/refresh/logout` | ✅ |
| Home (statistika) | `master-home-stats/app-bootstrap` | ✅ |
| Buyurtmalarim / Order / Complete / Tasdiqlash | `master-orders/order-detail/accept/start/reject/complete/receipt-confirm` | ✅ |
| Order tracking (real-time) | `master-location-update` + WS `/ws/master/tracking/` | ✅ 🆕(status broadcast) |
| Sklad / Add new tool (ombor) | `master-inventory/low-stock/detail/use` | ✅ |
| Wallet | `master-wallet/transactions/stats` | 🟡 haftalik/oylik trend? (pastga) |
| **Cash release (Naqd topshirish)** | `master-wallet-withdraw` (create) → admin `cash-handover accept` | ✅ 🆕 |
| Review | `master-reviews/reviews-summary` | ✅ |
| Xarajat (Expenses) | `master-expenses/expense-detail` | ✅ |
| Haraj (Market) | `client-market-*` (umumiy market) | 🟡 tekshirish |
| Profile / Edit / Language / Logout | `master-profile/settings/language/me` | ✅ |
| Certificates / Documents | `master-certificates/documents` | ✅ |
| Support / Privacy / Delete | `master-support`, `master-delete` | ✅ |
| **Live stream (broadcast)** | — | ❌ **master API yo'q** (live faqat dashboardda ko'riladi) |

**Master kamchiliklari:** jonli translyatsiyani **boshlash** uchun master API yo'q (dashboard faqat ko'radi/arxivlaydi).

---

## 4. Asosiy kamchiliklar (tuzatish uchun — tasdiqingizni kutaman)

1. **Live streaming — app tomoni yo'q.** `DashboardLiveStream` modeli bor, dashboard ko'radi/arxivlaydi, lekin:
   - Master uchun stream **boshlash/tugatish** API yo'q.
   - Client uchun stream **ko'rish** API yo'q.
   - Figmada: client "Live View" + dashboard "Jonli" bor → to'liq oqim uchun master+client endpointlari kerak.

2. **SOS (client).** Favqulodda/SOS ekrani bor, lekin API yo'q. Model + endpoint (masalan: SOS yuborish → adminga notification/dashboard bo'limi) kerak.

3. **🟡 Tekshirish kerak (maydon darajasi, aniq skrinshot bilan):**
   - Wallet: "Bu hafta / Oyiga" trend (+15% / −2%) statistikasi `master-wallet/stats` da alohida qaytadimi.
   - Market (Usta "Haraj") — usta market ekranlari client market API bilan to'liq mosligini.
   - Order "Tasdiqlash" — bonus summa, to'lov turi, ustani baholash maydonlari.

**Endpoint darajasida qolgan hamma narsa qamrab olingan.** Yuqoridagi 1–2 haqiqiy kamchilik, 3 esa maydon-darajali tekshirish.

Qaysi birini(larini) tuzatay? Har biri uchun aniq Figma ekranini (skrinshot) bersangiz, aniq moslashtiram.
