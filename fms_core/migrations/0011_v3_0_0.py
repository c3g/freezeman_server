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
        migrations.AlterField(
            model_name='sample',
            name='biospecimen_type',
            field=models.CharField(
                choices=[('DNA', 'DNA'), ('RNA', 'RNA'), ('BLOOD', 'BLOOD'), ('EXPECTORATION', 'EXPECTORATION'),
                         ('GARGLE', 'GARGLE'), ('PLASMA', 'PLASMA'), ('SALIVA', 'SALIVA'), ('SWAB', 'SWAB')],
                help_text='Biological material collected from study subject during the conduct of a genomic study project.',
                max_length=200),
        ),
        migrations.AlterField(
            model_name='sample',
            name='tissue_source',
            field=models.CharField(blank=True, choices=[('Blood', 'Blood'), ('Expectoration', 'Expectoration'),
                                                        ('Gargle', 'Gargle'), ('Plasma', 'Plasma'),
                                                        ('Saliva', 'Saliva'), ('Swab', 'Swab'), ('Tumor', 'Tumor'),
                                                        ('Buffy coat', 'Buffy coat'), ('Tail', 'Tail'),
                                                        ('Cells', 'Cells')],
                                   help_text='Can only be specified if the biospecimen type is DNA or RNA.',
                                   max_length=200),
        ),
    ]
