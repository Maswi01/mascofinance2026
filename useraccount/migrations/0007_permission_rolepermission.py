from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('useraccount', '0006_role_alter_customuser_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='role',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='Permission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codename', models.CharField(max_length=100, unique=True,
                    help_text='Unique slug, e.g. loans-create')),
                ('name', models.CharField(max_length=150,
                    help_text='Human-readable label, e.g. Create loans')),
                ('group', models.CharField(max_length=100,
                    help_text='Category shown in the UI, e.g. Loans')),
            ],
            options={
                'ordering': ['group', 'name'],
            },
        ),
        migrations.CreateModel(
            name='RolePermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='role_permissions', to='useraccount.role')),
                ('permission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='role_permissions', to='useraccount.permission')),
            ],
            options={
                'unique_together': {('role', 'permission')},
            },
        ),
    ]
