FRONTEND_GUIDE = """
HomeX API frontend va mobile integratsiya uchun tuzilgan. Barcha endpointlar `/api/v1/` prefix bilan ishlaydi.

## Tez boshlash

1. Client login: `POST /client/auth/send-otp/` -> `POST /client/auth/verify-otp/`.
2. Master login: `POST /master/auth/login/`.
3. Dashboard admin login: `POST /dashboard/auth/login/`.
4. Protected endpointlarda `Authorize` tugmasiga faqat access tokenni yozing. Swagger o'zi `Bearer` qo'shadi.
5. REST requestlarda header: `Authorization: Bearer <access_token>`.
6. Access token muddati: 3 kun. Refresh token muddati: 15 kun.
7. Refresh endpointlar yangi `access_token` va yangi `refresh_token` qaytaradi.
8. WebSocketlarda token URL query orqali yuborilmaydi. Faqat header: `Authorization: Bearer <access_token>`.

## Standart response formatlari

Success response:

```json
{
  "success": true,
  "message": "OK",
  "data": {}
}
```

Paginated list:

```json
{
  "success": true,
  "count": 10,
  "next": null,
  "previous": null,
  "results": []
}
```

Error response:

```json
{
  "success": false,
  "error": "VALIDATIONERROR",
  "message": "Validation failed",
  "details": {}
}
```

## HTTP status kodlar

| Status | Ma'nosi | Frontend nima qiladi |
|---|---|---|
| 200 | OK | Response `data` yoki `results` ni ekranga chiqaradi. |
| 201 | Created | Yangi obyekt yaratildi. ID ni saqlab, list/detailni yangilang. |
| 204 | No content | Amal bajarildi, body bo'lmasligi mumkin. |
| 400 | Bad request | Field validation xatolarini form yonida ko'rsating. |
| 401 | Unauthorized | Access token yo'q yoki muddati tugagan. Refresh qiling yoki login sahifaga qaytaring. |
| 403 | Forbidden | Token bor, lekin role noto'g'ri: client master APIga kira olmaydi yoki aksincha. |
| 404 | Not found | ID noto'g'ri yoki obyekt shu userga tegishli emas. |
| 429 | Too many requests | OTP rate limit yoki throttling. Userga kutish kerakligini ko'rsating. |
| 500 | Server error | Frontend retry/log ko'rsin, backend log tekshiriladi. |

## Role qoidalari

| Role | Token claim | Ishlatadigan prefix |
|---|---|---|
| Client | `role=client` | `/client/...` |
| Master | `role=master` | `/master/...` |
| Dashboard/Admin | `role=admin` yoki Django staff/admin session | `/dashboard/...`, `/warehouse/...`, `/masters/{id}/inventory/...` |

## Order statuslari

| Status | UI label | Ma'nosi |
|---|---|---|
| `new` | Yangi | Client buyurtma yaratgan; admin ustaga biriktiradi (`/dashboard/orders/{id}/assign/`). Hali usta qabul qilmagan. |
| `accepted` | Qabul qilindi | Admin biriktirgan usta qabul qildi; birinchi qabul qilgan usta lead bo'ladi. |
| `on_way` | Yo'lda | Usta `/master/orders/{id}/on-way/` orqali yo'lga chiqdi; location yuboradi. |
| `arrived` | Yetib keldi | Usta `/master/orders/{id}/arrived/` (yoki `start/`) orqali manzilga yetib keldi; `before_photo` **majburiy**. |
| `completed` | Yakunlandi | Usta yakunladi; `completion_photo` optional, socket yopiladi va to'lov/check bosqichiga o'tadi. |
| `cancelled` | Bekor qilingan | Client bekor qilgan. |
| `rejected` | Rad etilgan | Master rad qilgan. |

## Order check flow

- Master `POST /api/v1/master/orders/{id}/complete/` orqali orderni yakunlaydi va checkni tasdiqlaydi.
- Agar order allaqachon `completed` bo'lsa, master `POST /api/v1/master/orders/{id}/receipt/confirm/` orqali checkni alohida tasdiqlashi mumkin.
- Client faqat `receipt_status=approved` bo'lganda `GET /api/v1/client/orders/{id}/receipt/download/` orqali `.pdf` checkni yuklab oladi.

## Payment type qiymatlari

| Value | UI label |
|---|---|
| `cash` | Naqd |
| `online` | Online |
| `card` | Karta |
| `plastic` | Plastik |

## Market status va qiymatlari

| Field | Value | Ma'nosi |
|---|---|---|
| `condition` | `new` | Yangi mahsulot |
| `condition` | `used` | Ishlatilgan mahsulot |
| `market_order.status` | `pending` | Yangi market order |
| `market_order.status` | `confirmed` | Tasdiqlangan |
| `market_order.status` | `delivered` | Yetkazilgan |
| `market_order.status` | `cancelled` | Bekor qilingan |

## Master auth onboarding

| Endpoint | Bo'lim | Ma'nosi |
|---|---|---|
| `POST /master/auth/register/` | Master Auth | Usta ism, familiya, telefon va ixtisoslik bilan ariza qoldiradi. Response `approval_status=pending`. |
| `POST /master/auth/login/` | Master Auth | Faqat admin tasdiqlagan va password berilgan master login qiladi. |
| `POST /master/auth/refresh/` | Master Auth | Approved/active master tokenlarini yangilaydi. |

`approval_status` qiymatlari: `pending`, `approved`, `rejected`.

## Profile page uchun muhim fieldlar

`GET /client/profile/` response’da `current_tariff` tarif nomi sifatida qaytadi, ID emas. `addresses_count` esa Profile sahifadagi "Manzillar 3" kabi count uchun ishlatiladi.

## Realtime WebSocket endpointlar

| Kanal | URL | Role |
|---|---|---|
| Client notifications | `/ws/client/notifications/` | client |
| Master notifications | `/ws/master/notifications/` | master |
| Client support chat | `/ws/client/support/` | client |
| Master support chat | `/ws/master/support/` | master |
| Master tracking send | `/ws/master/tracking/` | master |
| Client order tracking | `/ws/client/track/{order_id}/` | client |

Tracking snapshot va socket payloadlarida `tracking_status`, `tracking_status_label`, `tracking_step`, `tracking_total_steps`, `tracking_steps`, `master_contact.phone_number`, `master_location`, `distance_km`, `eta_minutes` keladi. Client bilan master orasida chat yo'q; client faqat master telefon raqamini oladi.

Browser `new WebSocket()` custom `Authorization` header yubora olmaydi. Web frontend uchun gateway/proxy yoki header yubora oladigan WebSocket client strategiyasi kerak.
"""


OPENAPI_TAGS = [
    {"name": "Dashboard - Auth", "description": "Dashboard admin/staff login, token refresh, logout va hozirgi admin profilini olish."},
    {"name": "Dashboard - Dashboard", "description": "Dashboard bosh sahifa: stats cardlar, chartlar, bugungi orderlar, meta va global search."},
    {"name": "Dashboard - Mijozlar", "description": "Mijozlar sahifasi: client ro'yxati, detail, order tarixi va client statistikasi."},
    {"name": "Dashboard - Xodim", "description": "Xodimlar sahifasi: dashboard staff/admin userlarni yaratish, ko'rish, tahrirlash va o'chirish."},
    {"name": "Dashboard - Xaritalar", "description": "Xaritalar sahifasi: lokatsiyasi bor ustalarni marker ko'rinishida chiqarish."},
    {"name": "Dashboard - Ustalar", "description": "Ustalar sahifasi: master ro'yxati, profil, status, lokatsiya, available masterlar va order tarixi."},
    {"name": "Dashboard - Buyurtmalar", "description": "Buyurtmalar sahifasi: order list/detail, board, status update, master assign, tracking va assistantlar."},
    {"name": "Dashboard - Xizmatlar va Narxlar", "description": "Xizmatlar va narxlar sahifasi: category, service va service price CRUD endpointlari."},
    {"name": "Dashboard - Tariflar", "description": "Tariflar sahifasi: tariflar va tarif featurelarini boshqarish."},
    {"name": "Dashboard - Bildirishnomalar", "description": "Bildirishnomalar sahifasi: notification list/create, detail, unread count, read va read-all."},
    {"name": "Dashboard - Xarajatlar", "description": "Xarajatlar sahifasi: usta, kompaniya va ombor xarajatlarini boshqarish."},
    {"name": "Dashboard - Marketplace", "description": "Marketplace sahifasi: kategoriyalar, mahsulotlar, mahsulot rasmlari va market orderlar."},
    {"name": "Dashboard - Ombor", "description": "Ombor sahifasi: warehouse stats, mahsulotlar, stock movementlar va usta inventari."},
    {"name": "Dashboard - Jonli Kuzatuv", "description": "Jonli kuzatuv sahifasi: live streamlar va arxiv videolar."},
    {"name": "Dashboard - Xabarlar", "description": "Xabarlar sahifasi: support threadlar, xabarlar va o'qilgan holatga o'tkazish."},
    {"name": "Dashboard - Moliya Hisobotlar", "description": "Moliya hisobotlari sahifasi: wallet transactionlar, withdraw requestlar, summary va report chartlar."},
    {"name": "Dashboard - Sozlamalar", "description": "Sozlamalar sahifasi: integratsiya sozlamalarini boshqarish."},
    {"name": "Client Auth", "description": "Client OTP login, profile completion, refresh/logout/delete account."},
    {"name": "Client Home", "description": "Client asosiy sahifa: service categories, active orders, map config, quick actions."},
    {"name": "Client Services", "description": "Service category va category bo'yicha price list."},
    {"name": "Client Masters", "description": "Map uchun yaqin online/available masterlar. `lat`, `lng`, `radius_km` query ishlatiladi."},
    {"name": "Client Orders", "description": "Client order lifecycle: create, detail, cancel, track, rate, pay."},
    {"name": "Client Devices", "description": "Profile/My tools screen: client uskunalari va uskuna asosida order flow."},
    {"name": "Client Addresses", "description": "Client manzillari. Profile page count uchun `/client/profile/` ichida `addresses_count` ham bor."},
    {"name": "Client Tariffs", "description": "Tariflar list va tarifga ulanish. Profile response `current_tariff` nom qaytaradi."},
    {"name": "Client Profile", "description": "Client profile card: avatar, phone, name, language, notification settings, tariff name, address count."},
    {"name": "Client Push", "description": "Client FCM token register qilish."},
    {"name": "Client Notifications", "description": "Admindan yuborilgan (DB'da saqlanadigan) notificationlar: list, read, read-all + unread count. Order status realtime eventlari alohida: DB'siz, faqat `/ws/client/notifications/` + FCM orqali keladi (bu ro'yxatga tushmaydi)."},
    {"name": "Client Support", "description": "Client support chat REST list/create. Realtime uchun `/ws/client/support/`."},
    {"name": "Client Market", "description": "Market products, categories, favorites, market orders, client listing create."},
    {"name": "Master Auth", "description": "Master ariza qoldirish, admin tasdiqlagandan keyin phone/password login, refresh/logout/me/language/delete account."},
    {"name": "Master Home", "description": "Master dashboard stats, wallet summary, unread notifications, websocket hints."},
    {"name": "Master Orders", "description": "Master order list/detail, accept/reject/complete, tracking snapshot."},
    {"name": "Master Tracking", "description": "Master location REST fallback va WebSocket tracking ma'lumotlari."},
    {"name": "Master Wallet", "description": "Wallet balance, stats, transactions, withdraw request."},
    {"name": "Master Inventory", "description": "Master inventory list/detail/low-stock/use."},
    {"name": "Master Expenses", "description": "Master xarajatlari list/create/detail/delete."},
    {"name": "Master Reviews", "description": "Master review list va rating summary."},
    {"name": "Master Profile", "description": "Master profile, settings, certificates, documents."},
    {"name": "Master Push", "description": "Master FCM token register qilish."},
    {"name": "Master Notifications", "description": "Admindan yuborilgan (DB'da saqlanadigan) notificationlar: list, read, read-all + unread count. Order status realtime eventlari alohida: DB'siz, faqat `/ws/master/notifications/` + FCM orqali keladi (bu ro'yxatga tushmaydi)."},
    {"name": "Master Support", "description": "Master support chat REST list/create. Realtime uchun `/ws/master/support/`."},
    {"name": "Admin Master Inventory", "description": "Admin masterga warehouse product biriktirish, update, return/delete."},
    {"name": "Admin Warehouse Products", "description": "Admin warehouse products list. Masterga biriktirish uchun ishlatiladi."},
    {"name": "Privacy Policy", "description": "Public privacy policy content."},
    {"name": "Account", "description": "Umumiy account amallari."},
]
