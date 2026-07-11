"""Tracking WebSocket'ni Swagger/Postman orqali qo'lda sinash uchun demo data.

Har ishga tushirishda: demo master (approved, parolli) va demo client
yaratadi/yangilaydi, YANGI (status=new, ustasiz) order ochadi va socket
testi uchun kerak bo'lgan hamma narsani (tokenlar, URLlar, payloadlar)
chiqarib beradi.

    python manage.py seed_tracking_demo
    # docker local stackda:
    docker compose -f docker-compose.local.yml exec web python manage.py seed_tracking_demo
"""
from datetime import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Client, Master, MasterApprovalStatus
from apps.accounts.tokens import issue_role_tokens
from apps.orders.models import Order, OrderMaster, OrderStatus
from apps.services.models import Service, ServiceCategory

MASTER_PHONE = "+998900011223"
MASTER_PASSWORD = "demo1234"
CLIENT_PHONE = "+998900099887"


class Command(BaseCommand):
    help = "Tracking WS demo: approved master + client + yangi NEW order + tokenlar"

    def handle(self, *args, **options):
        category, _ = ServiceCategory.objects.get_or_create(
            slug="konditsioner", defaults={"name": "Konditsioner", "is_active": True}
        )
        service, _ = Service.objects.get_or_create(
            category=category, name="Konditsioner tozalash", defaults={"base_price": 150000, "is_active": True}
        )

        master, _ = Master.objects.get_or_create(
            phone=MASTER_PHONE, defaults={"first_name": "Demo", "last_name": "Usta"}
        )
        master.set_password(MASTER_PASSWORD)
        master.approval_status = MasterApprovalStatus.APPROVED
        master.is_active = True
        master.is_online = True
        master.is_available = True
        master.save()

        client, _ = Client.objects.get_or_create(
            phone=CLIENT_PHONE, defaults={"first_name": "Demo", "last_name": "Mijoz"}
        )
        client.is_active = True
        client.save(update_fields=["is_active", "updated_at"])

        order = Order.objects.create(
            client=client,
            service=service,
            address_text="Chilonzor 9-kvartal, Tashkent",
            lat="41.28500000",
            lng="69.20390000",
            scheduled_date=timezone.localdate(),
            scheduled_time=time(10, 0),
            status=OrderStatus.NEW,
        )
        # Admin biriktiradi: master faqat o'ziga biriktirilgan orderni ko'radi/qabul qiladi.
        OrderMaster.objects.get_or_create(order=order, master=master)

        master_token = issue_role_tokens(master, "master")["access_token"]
        client_token = issue_role_tokens(client, "client")["access_token"]

        w = self.stdout.write
        w(self.style.SUCCESS("=== TRACKING WS DEMO DATA TAYYOR ==="))
        w("")
        w(self.style.MIGRATE_HEADING("MASTER (login/parol Swagger uchun):"))
        w(f"  phone:    {MASTER_PHONE}")
        w(f"  password: {MASTER_PASSWORD}")
        w(f"  login:    POST /api/v1/master/auth/login/  body: {{\"phone\": \"{MASTER_PHONE}\", \"password\": \"{MASTER_PASSWORD}\"}}")
        w(f"  tayyor access_token (3 kun amal qiladi):\n  {master_token}")
        w("")
        w(self.style.MIGRATE_HEADING("CLIENT:"))
        w(f"  phone: {CLIENT_PHONE}  (OTP flow: send-otp -> verify-otp; yoki tayyor token pastda)")
        w(f"  tayyor access_token (3 kun amal qiladi):\n  {client_token}")
        w("")
        w(self.style.MIGRATE_HEADING("ORDER (yangi, MASTER'ga biriktirilgan):"))
        w(f"  order_id: {order.id}")
        w(f"  status:   {order.status}  (master biriktirilgan, hali qabul qilmagan)")
        w("")
        w(self.style.MIGRATE_HEADING("TEST QADAMLARI (yangi oqim: accept -> yo'lda -> yetib keldi -> yakunlandi):"))
        w("  Order bo'lganda client 2 ta socketga ulanadi:")
        w("    - NOTIFICATION (doim ochiq): ws://localhost:8000/ws/client/notifications/  -> har status o'zgarishi 'order.status'")
        w(f"    - TRACKING (faqat usta yo'lda): ws://localhost:8000/ws/client/track/{order.id}/  -> 'tracking.snapshot' + 'master.location'")
        w("    Header (ikkalasida): Authorization: Bearer <CLIENT access_token>")
        w(f"  2) Accept (MASTER token):   POST /api/v1/master/orders/{order.id}/accept/   body: {{}}")
        w("     -> status=accepted; notification socketga 'order.status' (accepted) + FCM push.")
        w(f"  3) Yo'lda (MASTER token):   POST /api/v1/master/orders/{order.id}/on-way/   body: {{}}")
        w("     -> status=on_way; notification socketga 'order.status' (on_way). Endi tracking socket lokatsiya oladi.")
        w(f"  4) Yetib keldi (MASTER):    POST /api/v1/master/orders/{order.id}/arrived/  body: {{}}")
        w("     -> status=arrived; notification socketga 'order.status' (arrived).")
        w(f"  5) Yakunlash (MASTER):      POST /api/v1/master/orders/{order.id}/complete/ body: {{\"service_fee\":\"150000\"}}")
        w("     -> status=completed; notification socketga 'order.status' (completed), to'lov/check bosqichiga o'tiladi.")
        w("  --- Usta yo'lda vaqti lokatsiya (WS): ws://localhost:8000/ws/master/tracking/ + MASTER token")
        w('      Yuboring: {"lat": "41.311081", "lng": "69.240562"}  (order_id shart emas) -> client tracking socketda master.location oladi.')
        w("")
        w("Dashboard tekshiruv: GET /api/v1/dashboard/orders/?tab=yangi|yo'lda|bajarilmoqda|yakunlangan|bekor")
        w("Ko'p usta biriktirish: PATCH /api/v1/dashboard/orders/<id>/assign/  body: {\"masters\":[\"id1\",\"id2\"], \"assistants\":[\"id3\"]}")
        w("")
        w("Eslatma: WS faqat ASGI serverda ishlaydi (uvicorn/docker local stack), 'runserver' emas.")
