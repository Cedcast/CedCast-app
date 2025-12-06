from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_school_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='sender_id',
            field=models.CharField(blank=True, help_text='Optional alphanumeric sender ID (requires approval)', max_length=20, null=True),
        ),
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('org_type', models.CharField(choices=[('pharmacy', 'Pharmacy'), ('company', 'Company'), ('ngo', 'NGO'), ('other', 'Other')], default='company', max_length=20)),
                ('slug', models.SlugField(max_length=100, unique=True)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='org_logos/')),
                ('primary_color', models.CharField(default='#0d6efd', max_length=7)),
                ('secondary_color', models.CharField(default='#6c757d', max_length=7)),
                ('clicksend_username', models.CharField(blank=True, max_length=100, null=True)),
                ('clicksend_api_key', models.CharField(blank=True, max_length=100, null=True)),
                ('sender_id', models.CharField(blank=True, max_length=20, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Contact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('phone_number', models.CharField(max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='core.organization')),
            ],
        ),
    ]