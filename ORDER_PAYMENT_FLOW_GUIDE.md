# HomeX — Order to'lov oqimi (Frontend + Flutter qo'llanma)

Bu hujjat **yangi order to'lov oqimini** frontend (React dashboard) va Flutter (client/usta app)
dasturchilari uchun misollar bilan tushuntiradi.

## Nima o'zgardi (qisqacha)

- Order **yaratishda to'lov turi tanlanmaydi** va **oldindan to'lov yo'q**.
- **Xizmat narxi (`service_fee`) katalogdan olinmaydi** — ustaning o'zi ishni tugatganda kiritadi.
- Usta narx + ishlatilgan uskunalarni kiritib **chekni yuboradi** → order `completed` emas, **`awaiting_payment`** bo'ladi.
- Mijoz chekni ko'rib **to'laydi (naqd yoki online)**. **To'lovdan keyingina** order `completed` bo'ladi va usta hamyoni kreditlanadi.

## Status oqimi

```
new → accepted → on_way → arrived → awaiting_payment → completed
                                          │
                                    (chek yuborildi)
                                          │
                        ┌─────────────────┴─────────────────┐
                     ONLINE                               NAQD
              (Payme/Click to'lov)          (mijoz "naqd" tanlaydi → darrov)
                        └─────────────────┬─────────────────┘
                                    → completed
```
Bekor holatlar: `cancelled`, `rejected`.

> **Tracking:** `awaiting_payment` holatida `tracking_status = "master_finished"` (Usta ishni tugatgan),
> `completed` da `tracking_status = "completed"`.

## Umumiy qoidalar

- **Base URL:** `/api/v1/`
- **Auth (REST):** `Authorization: Bearer <access_token>`
- **Auth (WebSocket):** brauzer header yubora olmaydi → `?token=<access_token>` query bilan ulaning
  (masalan `wss://host/ws/client/track/<order_id>/?token=...`). Header ham ishlaydi.
- **Javob konverti:** hamma REST javoblar `{ "success": true, "message": "OK", "data": { ... } }` shaklида.

---

## 1-qadam — Mijoz order yaratadi (to'lov turi/narx YO'Q)

`POST /api/v1/client/orders/`

`payment_type` va `service_fee` **yuborilmaydi** (yuborilsa ham e'tiborga olinmaydi/keyin o'rnatiladi).

```bash
curl -X POST https://api.homex.uz/api/v1/client/orders/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "service": "b2c3...uuid",
    "device": "d1e2...uuid",            // ixtiyoriy (My tools qurilmasidan)
    "address_text": "Chilonzor, 12-mavze, 45-uy",
    "lat": "41.31000000",
    "lng": "69.24000000",
    "scheduled_date": "2026-07-25",
    "scheduled_time": "10:00:00",
    "note": "Konditsioner ishlamayapti"
  }'
```

**Javob (201):**
```json
{ "success": true, "message": "OK", "data": {
  "id": "a1b2...uuid",
  "status": "new",
  "payment_type": null,          // hali tanlanmagan
  "service_fee": "0.00",         // usta keyin kiritadi
  "inventory_total": "0.00",
  "total_amount": "0.00",
  "receipt_status": "not_ready",
  "can_download_receipt": false
} }
```

**Flutter (Dart):**
```dart
final res = await dio.post('/api/v1/client/orders/', data: {
  'service': serviceId,
  'address_text': 'Chilonzor, 12-mavze, 45-uy',
  'lat': '41.31000000', 'lng': '69.24000000',
  'scheduled_date': '2026-07-25', 'scheduled_time': '10:00:00',
});
final orderId = res.data['data']['id'];
```

---

## 2-qadam — Usta ishni oladi (o'zgarmagan)

Admin ustani biriktiradi, keyin usta:
- `POST /api/v1/master/orders/<id>/accept/` → `accepted`
- `POST /api/v1/master/orders/<id>/on-way/` → `on_way`
- `POST /api/v1/master/orders/<id>/arrived/` → `arrived` (multipart, `before_photo` ixtiyoriy)

---

## 3-qadam — Usta CHEKNI yuboradi (narx + uskunalar) ⭐

`POST /api/v1/master/orders/<id>/complete/` — **multipart/form-data**

> ⚠️ Bu tugma endi order'ni **yakunlamaydi** — chekni yuboradi. Order `awaiting_payment` bo'ladi.

| Maydon | Majburiy | Izoh |
|---|---|---|
| `service_fee` | ✅ | Xizmat narxi (usta qo'lda kiritadi), so'mda |
| `comment` | — (Figmada `*`) | "Xizmat haqida izoh" |
| `completion_photo` | — (Figmada `*`) | Ishdan keyingi rasm |
| `used_items` | — | Ishlatilgan uskunalar (JSON massiv) |

`used_items` formati: `[{"inventory_id": "<usta_inventar_id>", "quantity": 2}]`
(narx `unit_price` — ustaning ombordagi mahsulotining `sale_price`idan avtomatik olinadi.)

```bash
curl -X POST https://api.homex.uz/api/v1/master/orders/$ID/complete/ \
  -H "Authorization: Bearer $MASTER_TOKEN" \
  -F "service_fee=280000" \
  -F "comment=Kompressor tozalandi, freon to'ldirildi" \
  -F "completion_photo=@after.jpg" \
  -F 'used_items=[{"inventory_id":"f1a2...uuid","quantity":2}]'
```

**Javob (200):**
```json
{ "success": true, "message": "OK", "data": {
  "order": {
    "id": "a1b2...uuid",
    "status": "awaiting_payment",
    "service_fee": "280000.00",
    "inventory_total": "34000.00",
    "total_amount": "314000.00",
    "receipt_status": "approved",
    "can_download_receipt": true,
    "receipt_download_url": "https://api.homex.uz/api/v1/client/orders/a1b2.../receipt/download/"
  },
  "service_fee": "280000.00",
  "inventory_total": "34000.00",
  "total_amount": "314000.00"
} }
```

**Flutter (usta app — FormData):**
```dart
final form = FormData.fromMap({
  'service_fee': '280000',
  'comment': 'Kompressor tozalandi',
  'completion_photo': await MultipartFile.fromFile(photoPath),
  'used_items': jsonEncode([{'inventory_id': invId, 'quantity': 2}]),
});
await dio.post('/api/v1/master/orders/$orderId/complete/', data: form);
```

> Chek yuborilganda mijozga avtomatik **"Chek tayyor"** notification ketadi (notification socket + FCM).

---

## 4-qadam — Mijoz chekni ko'radi

Order `awaiting_payment` bo'lgach mijoz chekni **to'lovdan oldin** ko'ra oladi:

- Order tafsiloti: `GET /api/v1/client/orders/<id>/` → `total_amount`, `service_fee`, `inventory_total`, `can_download_receipt: true`.
- Chek PDF: `GET /api/v1/client/orders/<id>/receipt/download/` → `application/pdf` fayl.

```bash
curl -L -H "Authorization: Bearer $TOKEN" \
  https://api.homex.uz/api/v1/client/orders/$ID/receipt/download/ -o check.pdf
```

---

## 5-qadam — Mijoz TO'LAYDI

Mijoz check ekranida **naqd** yoki **online** tanlaydi.

### 5A. ONLINE (Click / Payme)

`POST /api/v1/client/orders/<id>/pay/`  (faqat `awaiting_payment` holatida)

```bash
curl -X POST https://api.homex.uz/api/v1/client/orders/$ID/pay/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "payment_method": "online" }'
```
`payment_method`: `online` | `card` | `plastic`.

**Javob (200):**
```json
{ "success": true, "message": "OK", "data": { "payment_url": "https://checkout.paycom.uz/..." } }
```

Frontend `payment_url` ni ochadi (WebView/browser). Mijoz to'lagach **Payme webhook** order'ni
avtomatik `completed` qiladi va usta hamyonini (online balans) kreditlaydi — **frontend hech narsa
chaqirmaydi**. Yakunlanishni ikki yo'l bilan biladi:
- **Notification socket:** `order.status` event, `data.status = "completed"` (tavsiya), yoki
- **Polling:** `GET /api/v1/client/orders/<id>/` → `status == "completed"`.

> Payme checkout havolasini alohida olish uchun: `GET /api/v1/payme/checkout-url/<order_id>/`
> (`checkout_url` qaytaradi). To'lov holatini poll qilish: `GET /api/v1/payme/order-status/<order_id>/`
> (`is_paid` qaytaradi).

### 5B. NAQD

Mijoz check ekranida **naqd**ni tanlaydi → order **darrov yakunlanadi** (usta tasdig'i **kerak emas**).
Xuddi shu `pay` endpoint, `payment_method: "cash"`:

`POST /api/v1/client/orders/<id>/pay/`  (faqat `awaiting_payment`)

```bash
curl -X POST https://api.homex.uz/api/v1/client/orders/$ID/pay/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "payment_method": "cash" }'
```

**Javob (200):** yakunlangan **order obyekti** (`status: "completed"`, `is_paid: true`) — `payment_url` YO'Q.
Usta naqd balansi kreditlanadi; mijozga "Buyurtma yakunlandi" notification ketadi. Jismoniy naqdni
usta oladi (keyin mavjud cash-handover orqali adminga topshiradi).

**Flutter (client app):**
```dart
final res = await dio.post('/api/v1/client/orders/$orderId/pay/',
    data: {'payment_method': 'cash'});
// res.data['data']['status'] == 'completed'
```

---

## 6-qadam — Yakunlangandan keyin

- Order `completed`, `is_paid: true`, `paid_at` to'ldirilgan.
- Mijoz baho beradi: `POST /api/v1/client/orders/<id>/rate/` `{ "rating": 5, "comment": "Zo'r" }`.

---

## WebSocket (realtime)

| Socket | URL |
|---|---|
| Mijoz — order tracking | `ws/client/track/<order_id>/?token=<access>` |
| Mijoz — notifications | `ws/client/notifications/?token=<access>` |
| Usta — notifications | `ws/master/notifications/?token=<access>` |

`order.status` event `payload.data.status` da yangi statusni beradi (`awaiting_payment`, `completed`, ...).

```js
const proto = location.protocol === "https:" ? "wss" : "ws";
const ws = new WebSocket(`${proto}://${host}/ws/client/notifications/?token=${accessToken}`);
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.event === "order.status" && msg.data.status === "awaiting_payment") showCheck(msg.data.order_id);
};
```

---

## Dashboard — "Usta tahrirlash" (yangi maydonlar)

`PATCH /api/v1/dashboard/masters/<id>/` — endi `daraja` va `address` bor:

```json
{
  "first_name": "Jaloliddin",
  "last_name": "Ahmadaliyev",
  "daraja": "katta_usta",         // "usta" | "katta_usta"  (Figmadagi "Daraja")
  "specialization": "Konditsioner ustasi",   // "Roli"
  "phone": "+998989984468",
  "address": "Yunusobod 12-uy",   // "Manzil"
  "password": "yangi-parol"       // ixtiyoriy, faqat yozish uchun
}
```

---

## Client "My tools" (uskunalar) — delete

Mijoz o'z qurilmasini o'chiradi:

`DELETE /api/v1/client/devices/<device_id>/` → `204` (faqat o'z qurilmasi).

```dart
await dio.delete('/api/v1/client/devices/$deviceId/');
```

---

## ⚠️ Kontrakt o'zgarishlari (e'tibor bering)

1. **Yangi status `awaiting_payment`** — barcha order enumlariga qo'shing.
2. Order yaratishda **`payment_type` yubormang** (majburiy emas; null qaytadi).
3. Usta **"complete"** endi chek yuboradi (order yakunlanmaydi). Yakunlash to'lovdan keyin.
4. **To'lov bitta endpoint:** `POST /client/orders/<id>/pay/` `{payment_method}`. `cash` → order darrov yakunlanadi (order obyekti qaytadi); `online`/`card`/`plastic` → `payment_url` qaytadi. (Usta naqd tasdiqlash endpointi **yo'q**.)
5. Chek `awaiting_payment` da (to'lovdan **oldin**) yuklab olinadi.
6. `service_fee` katalogdan emas — usta kiritadi.
7. Master modelida `daraja` + `address` yangi maydonlar.
8. Eski `POST /master/orders/<id>/receipt/confirm/` endi **ortiqcha** — chaqirmang (chek submit'da avto-ochiladi).
```
