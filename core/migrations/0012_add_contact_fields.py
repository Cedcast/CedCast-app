from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_orgalertrecipient_last_retry_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='address',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='school',
            name='phone_primary',
            field=models.CharField(max_length=20, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='school',
            name='phone_secondary',
            field=models.CharField(max_length=20, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='organization',
            name='address',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='organization',
            name='phone_primary',
            field=models.CharField(max_length=20, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='organization',
            name='phone_secondary',
            field=models.CharField(max_length=20, blank=True, null=True),
        ),
    ]
