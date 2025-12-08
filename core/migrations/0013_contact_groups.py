from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_add_contact_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContactGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='groups', to='core.organization')),
                ('contacts', models.ManyToManyField(blank=True, related_name='groups', to='core.contact')),
            ],
        ),
    ]
