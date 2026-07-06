# Dashboard support — realtime WebSocket (yo'riqnoma)

Endi dashboard (brauzer) support chatlarni **realtime** oladi. Buning uchun:
- WS autentifikatsiya `role="admin"` (dashboard) tokenini taniydigan qildik.
- Brauzer WebSocket'da header qo'yib bo'lmagani uchun token `?token=` query orqali ham qabul qilinadi.
- Dashboard uchun ikkita WS endpoint qo'shildi (mavjud, staff-gated consumerlarni ishlatadi).

---

## 1. Autentifikatsiya

Token = dashboard **access_token** (`POST /api/v1/dashboard/auth/login/` dan olinadi).

- **Brauzer (dashboard SPA):** `?token=<access_token>` query orqali.
- **Native app:** `Authorization: Bearer <access_token>` header orqali.

> Ishlab chiqarishda albatta **`wss://`** (TLS) ishlating — token query'da bo'lgani uchun shifrlangan kanal shart. Server access-log'lari query stringni yozmasligiga ishonch hosil qiling.

---

## 2. Endpointlar

### a) Inbox (threadlar ro'yxati) — realtime yangilanish
```
wss://<host>/ws/dashboard/support/?token=<access_token>
```
Yangi xabar kelganda yoki o'qilganda quyidagi event keladi (inbox badge/tartibini yangilash uchun):
```json
{
  "type": "chat.update",
  "chat_id": "…",
  "participant_role": "client",      // yoki "master"
  "unread_by_admin": 3,
  "updated_at": "2026-07-06T09:12:00Z"
}
```
Bu yerda **xabar matni yo'q** — faqat qaysi chatda o'zgarish borligi. Ro'yxatni yangilash uchun REST `GET /dashboard/support/threads/` bilan birga ishlating.

### b) Bitta chat — xabarlar realtime
```
wss://<host>/ws/dashboard/support/<chat_id>/?token=<access_token>
```
- Ulanganda darrov **tarix** keladi (va chat "o'qilgan" deb belgilanadi):
  ```json
  { "type": "history", "chat_id": "…", "messages": [ { …message… }, … ] }
  ```
- Client/master (yoki boshqa admin) yozganda **jonli** keladi:
  ```json
  { "type": "message", "message": { …message… }, "data": { …message… } }
  ```
- **Admin javob yuborish** (shu socket orqali):
  ```json
  { "content": "Assalomu alaykum, yordam beramiz" }
  ```
  (`content`, `message` yoki `text` kaliti qabul qilinadi. Bo'sh bo'lsa `{"type":"error"}` qaytadi.)

`message` obyekti `SupportMessageSerializer` formatida: `id, chat, sender_role, sender, message, content, attachment, is_read, from_user, created_at, …`.

---

## 3. JS misol

```js
const token = localStorage.getItem("dashboard_access_token");
const base = "wss://api.homex.uz";

// Inbox — badge/tartibni yangilash
const lobby = new WebSocket(`${base}/ws/dashboard/support/?token=${token}`);
lobby.onmessage = (e) => {
  const ev = JSON.parse(e.data);
  if (ev.type === "chat.update") updateInbox(ev.chat_id, ev.unread_by_admin);
};

// Ochilgan chat — xabarlar realtime
const chat = new WebSocket(`${base}/ws/dashboard/support/${chatId}/?token=${token}`);
chat.onmessage = (e) => {
  const ev = JSON.parse(e.data);
  if (ev.type === "history") renderMessages(ev.messages);
  if (ev.type === "message") appendMessage(ev.message);
};
// Javob yuborish
function reply(text) { chat.send(JSON.stringify({ content: text })); }
```

**Reconnect:** `onclose` da qayta ulaning (masalan 1–3s backoff). Token muddati tugasa `dashboard/auth/refresh/` bilan yangilab, qayta ulaning.

---

## 4. Nima o'zgardi (backend)

- `apps/accounts/ws_auth.py` — `role="admin"` (staff user) taniladi; token header **yoki** `?token=` query'dan olinadi.
- `config/routing.py` — `ws/dashboard/support/` va `ws/dashboard/support/<chat_id>/` qo'shildi (mavjud `AdminSupportLobbyConsumer` / `AdminSupportChatConsumer` ishlatiladi, ikkalasi ham `is_staff` tekshiradi).
- Broadcast allaqachon `support_admin` guruhiga borardi — shuning uchun qo'shimcha broadcast kerak emas, faqat auth + routing yetishmayotgan edi.

Testlar: WS auth admin tokenni (header + query) tanishi qo'shildi. `pytest` — 55 passed.

---

# Figma ↔ Backend (Dashboard) — farqlar va reja

> Diqqat: ish papkasi oxirgi turlarda **reset** bo'lgan — avval qurgan quyidagi bo'limlar hozir backendda **yo'q** (qayta qo'shish kerak). Bu Figmada bor, backendda yo'q asosiy farqlar:

| # | Figma bo'limi | Hozirgi backend | Task |
|---|---|---|---|
| 1 | Ustalar → **So'rov qoldirganlar** (applications) | ❌ yo'q | `dashboard/masters/applications/` endpoint + serializer + (Unfold proxy) |
| 2 | Ustalar → **Bloklanganlar** + **Bloklash** | ❌ yo'q | `is_blocked` field + `masters/blocked/` + `masters/<id>/block/` + Unfold |
| 3 | Moliya → **Masterdan naqd pul qabul qilish** | ❌ yo'q | Cash handover accept/reject + `dashboard/cash-handovers/` + Unfold |
| 4 | Jonli (Live) | dashboard ✅, app-side ❌ | Master start / client watch uchun API (app tomoni) |
| 5 | Qolgan bo'limlar (Login, Dashboard, Buyurtma, Xarita, Mijozlar, Xodim, Xizmat, Market, Tariflar, Xarajat, Ombor, Xabar, Sozlamalar) | ✅ endpoint darajasida bor | Maydon darajasida Figma bilan tekshirish |

**Reja (prioritet):** 1→2→3 (Figmada aniq ko'rsatilgan, avval qurilgan) → 4 (kattaroq, alohida) → 5 (maydon-darajali tekshirish, aniq skrinshot bilan).

Tasdiqlang — qaysi tartibda tuzatay? (1–3 ni men avval qilganman, tez qayta qo'shaman.)
