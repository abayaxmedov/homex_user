"""Create a few unpaid orders for the Payme sandbox (test.paycom.uz).

Run on the SAME database the webhook reads (i.e. production), then send the
printed ``order_id`` + tiyin amounts to the Payme specialist. Each order's
``total_amount`` is what the webhook validates the Payme ``amount`` against.

    python manage.py create_payme_test_orders
    python manage.py create_payme_test_orders --amounts 1000 5000 25000
"""
from datetime import date, time
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.accounts.models import Client
from apps.orders.models import Order, OrderStatus, PaymentType
from apps.services.models import Service, ServiceCategory

DEFAULT_AMOUNTS_SOM = [1000, 5000, 25000]


class Command(BaseCommand):
    help = "Create test orders for the Payme sandbox and print order_id + amount (tiyin)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--amounts",
            nargs="*",
            type=int,
            default=DEFAULT_AMOUNTS_SOM,
            help="So'm amounts to create (default: 1000 5000 25000)",
        )

    def handle(self, *args, **options):
        amounts = options["amounts"] or DEFAULT_AMOUNTS_SOM

        client, _ = Client.objects.get_or_create(
            phone="+998900000001",
            defaults={"first_name": "Payme", "last_name": "Test"},
        )
        category, _ = ServiceCategory.objects.get_or_create(
            slug="payme-test", defaults={"name": "Payme test"}
        )
        service, _ = Service.objects.get_or_create(
            category=category, name="Payme test xizmat", defaults={"base_price": 0}
        )

        self.stdout.write(self.style.MIGRATE_HEADING("Payme sandbox test orders:"))
        self.stdout.write(f"{'order_id':<38}  {'som':>10}  {'tiyin (Payme amount)':>20}")
        for som in amounts:
            order = Order.objects.create(
                client=client,
                service=service,
                address_text="Payme test",
                lat=Decimal("41.30000000"),
                lng=Decimal("69.25000000"),
                scheduled_date=date.today(),
                scheduled_time=time(10, 0),
                status=OrderStatus.NEW,
                payment_type=PaymentType.ONLINE,
                service_fee=Decimal(som),
                total_amount=Decimal(som),
            )
            self.stdout.write(f"{str(order.id):<38}  {som:>10}  {som * 100:>20}")

        self.stdout.write(
            self.style.SUCCESS(
                "\nShohjahonga yuboring: har bir order_id + tiyin summasi. "
                "account field = order_id."
            )
        )
