FRONTEND_GUIDE = """
HomeX API frontend va mobile integratsiya uchun tuzilgan. Barcha endpointlar `/api/v1/` prefix bilan ishlaydi.

## Tez boshlash

1. Client login: `POST /client/auth/send-otp/` -> `POST /client/auth/verify-otp/`.
2. Master login: `POST /master/auth/login/`.
3. Protected endpointlarda `Authorize` tugmasiga faqat access tokenni yozing. Swagger o'zi `Bearer` qo'shadi.
4. REST requestlarda header: `Authorization: Bearer <access_token>`.
5. Access token muddati: 3 kun. Refresh token muddati: 15 kun.
6. Refresh endpointlar yangi `access_token` va yangi `refresh_token` qaytaradi.
7. WebSocketlarda token URL query orqali yuborilmaydi. Faqat header: `Authorization: Bearer <access_token>`.

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
| Admin | Django staff/admin | `/warehouse/...`, `/masters/{id}/inventory/...` |

## Order statuslari

| Status | UI label | Ma'nosi |
|---|---|---|
| `new` | Usta qidirilmoqda | Client buyurtma yaratgan, tracking ochilgan, hali master birikmagan. |
| `accepted` | Usta yo'lda | Master buyurtmani oldi va location yuborishi mumkin. |
| `in_progress` | Usta ishlamoqda | Master `/master/orders/{id}/start/` orqali ishni boshlagan. |
| `completed` | Usta ishni tugatgan | Master yakunladi, client rating berishi mumkin. |
| `cancelled` | Bekor qilingan | Client bekor qilgan. |
| `rejected` | Rad etilgan | Master rad qilgan. |

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
    {"name": "Client Notifications", "description": "Notification list, read, read-all. Realtime uchun `/ws/client/notifications/`."},
    {"name": "Client Support", "description": "Client support chat REST list/create. Realtime uchun `/ws/client/support/`."},
    {"name": "Client Market", "description": "Market products, favorites, market orders, client listing create."},
    {"name": "Master Auth", "description": "Master phone/password login, refresh/logout/me/language/delete account."},
    {"name": "Master Home", "description": "Master dashboard stats, wallet summary, unread notifications, websocket hints."},
    {"name": "Master Orders", "description": "Master order list/detail, accept/reject/complete, tracking snapshot."},
    {"name": "Master Tracking", "description": "Master location REST fallback va WebSocket tracking ma'lumotlari."},
    {"name": "Master Wallet", "description": "Wallet balance, stats, transactions, withdraw request."},
    {"name": "Master Inventory", "description": "Master inventory list/detail/low-stock/use."},
    {"name": "Master Expenses", "description": "Master xarajatlari list/create/detail/delete."},
    {"name": "Master Reviews", "description": "Master review list va rating summary."},
    {"name": "Master Profile", "description": "Master profile, settings, certificates, documents."},
    {"name": "Master Push", "description": "Master FCM token register qilish."},
    {"name": "Master Notifications", "description": "Master notification list, read, read-all. Realtime uchun `/ws/master/notifications/`."},
    {"name": "Master Support", "description": "Master support chat REST list/create. Realtime uchun `/ws/master/support/`."},
    {"name": "Admin Master Inventory", "description": "Admin masterga warehouse product biriktirish, update, return/delete."},
    {"name": "Admin Warehouse Products", "description": "Admin warehouse products list. Masterga biriktirish uchun ishlatiladi."},
    {"name": "Privacy Policy", "description": "Public privacy policy content."},
    {"name": "Account", "description": "Umumiy account amallari."},
]
