from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0006_simplify_homebanner"),
    ]

    operations = [
        migrations.AddField(
            model_name="homebanner",
            name="banner_image",
            field=models.ImageField(blank=True, null=True, upload_to="home/banners/"),
        ),
    ]
