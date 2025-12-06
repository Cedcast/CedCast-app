from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_org_and_contact'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrgMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('scheduled_time', models.DateTimeField()),
                ('sent', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
            ],
        ),
        migrations.CreateModel(
            name='OrgAlertRecipient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('contact', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.contact')),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recipients_status', to='core.orgmessage')),
            ],
        ),
    ]