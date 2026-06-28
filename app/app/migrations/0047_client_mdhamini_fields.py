from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0046_bankcashtransaction_created_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='mdhamini_jina_kamili',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_checkno',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_kitambulisho_kazi',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_kazi',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_kituo_kazi',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_kata',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_tarafa',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_wilaya',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_mkoa',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='mdhamini_simu',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
