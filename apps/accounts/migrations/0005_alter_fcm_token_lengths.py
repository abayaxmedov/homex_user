from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_master_approval"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="fcm_token",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="master",
            name="fcm_token",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="fcmdevice",
            name="token",
            field=models.CharField(max_length=512, unique=True),
        ),
    ]
