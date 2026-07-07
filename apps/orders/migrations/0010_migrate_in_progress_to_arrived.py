from django.db import migrations


def forwards(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    # Old "in_progress" (usta ishlamoqda) maps to the new "arrived" (usta yetib
    # keldi, ish jarayonida). See OrderStatus in apps/orders/models.py.
    Order.objects.filter(status="in_progress").update(status="arrived")


def backwards(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(status="arrived").update(status="in_progress")


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0009_alter_order_status_ordermaster'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
