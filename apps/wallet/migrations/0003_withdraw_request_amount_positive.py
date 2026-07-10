from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0002_cashhandover"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="withdrawrequest",
            constraint=models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="withdraw_request_amount_positive",
            ),
        ),
    ]
