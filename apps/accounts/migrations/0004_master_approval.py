from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_master_location"),
    ]

    operations = [
        migrations.AlterField(
            model_name="master",
            name="password",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="master",
            name="approval_status",
            field=models.CharField(
                choices=[
                    ("pending", "Tasdiq kutilmoqda"),
                    ("approved", "Tasdiqlangan"),
                    ("rejected", "Rad etilgan"),
                ],
                default="approved",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="master",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="master",
            name="rejected_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
