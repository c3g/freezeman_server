# Generated by Django 3.1 on 2021-01-27 21:58

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('fms_core', '0012_v3_0_1'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='sample',
            name='reception_date',
        ),
    ]