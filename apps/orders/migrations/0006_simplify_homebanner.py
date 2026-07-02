from django.conf import settings
from django.db import migrations, models


def copy_banner_url(apps, schema_editor):
    HomeBanner = apps.get_model("orders", "HomeBanner")
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    for banner in HomeBanner.objects.all():
        banner_url = banner.external_banner_url or ""
        if not banner_url and banner.banner_image:
            banner_url = f"{media_url.rstrip('/')}/{banner.banner_image.name.lstrip('/')}"
        banner.banner_url = banner_url
        banner.save(update_fields=["banner_url"])


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_order_receipt_approval"),
    ]

    operations = [
        migrations.AddField(
            model_name="homebanner",
            name="banner_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.RunPython(copy_banner_url, migrations.RunPython.noop),
        migrations.RemoveField(model_name="homebanner", name="badge_text"),
        migrations.RemoveField(model_name="homebanner", name="banner_image"),
        migrations.RemoveField(model_name="homebanner", name="cta_action"),
        migrations.RemoveField(model_name="homebanner", name="cta_label"),
        migrations.RemoveField(model_name="homebanner", name="discount_percent"),
        migrations.RemoveField(model_name="homebanner", name="external_banner_url"),
        migrations.RemoveField(model_name="homebanner", name="key"),
        migrations.RemoveField(model_name="homebanner", name="sort_order"),
        migrations.RemoveField(model_name="homebanner", name="target_type"),
        migrations.RemoveField(model_name="homebanner", name="target_value"),
        migrations.RemoveField(model_name="homebanner", name="title"),
        migrations.RemoveField(model_name="homebanner", name="created_at"),
        migrations.RemoveField(model_name="homebanner", name="updated_at"),
        migrations.AlterModelOptions(name="homebanner", options={}),
    ]
