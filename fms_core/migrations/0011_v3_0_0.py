# Generated by Django 3.1 on 2021-01-04 16:19

from django.db import migrations, models
from reversion.models import Version
import json


def change_individual_label_field_in_versions(apps, schema_editor):
    for version in Version.objects.filter(content_type__model='individual'):
        data = json.loads(version.serialized_data)
        data[0]["fields"]["name"] = data[0]["fields"]["label"]
        del data[0]["fields"]["label"]
        version.serialized_data = json.dumps(data)
        version.save()


class Migration(migrations.Migration):
    dependencies = [
        ('fms_core', '0010_v2_6_1'),
    ]

    operations = [
        migrations.RenameField(
            model_name='individual',
            old_name='label',
            new_name='name',
        ),
        migrations.AlterField(
            model_name='individual',
            name='cohort',
            field=models.CharField(blank=True, help_text='Name to group some individuals in a specific study.',
                                   max_length=200),
        ),
        migrations.RunPython(
            change_individual_label_field_in_versions,
            migrations.RunPython.noop
        ),
    ]
