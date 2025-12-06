# Generated migration for adding ClickSend fields to School model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_school_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='clicksend_username',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='school',
            name='clicksend_api_key',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]