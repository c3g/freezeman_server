# Generated by Django 3.1 on 2021-02-09 17:53

from django.db import migrations, models
import django.db.models.deletion
import json


def create_lineage_from_extracted(apps, schema_editor):
    sample_model = apps.get_model("fms_core", "sample")
    version_model = apps.get_model("reversion", "Version")

    # Create parent lineage for each sample that had an extracted_from fk
    for sample in sample_model.objects.all():
        if sample.old_extracted_from:
            sample.child_of.add(sample.old_extracted_from)

    for version in version_model.objects.filter(content_type__model="sample"):
        # Remove the extracted_from field from the serialized_data in version
        data = json.loads(version.serialized_data)
        data[0]["fields"].pop("extracted_from", None)
        version.serialized_data = json.dumps(data)
        # Save to database
        version.save()


class Migration(migrations.Migration):

    dependencies = [
        ('fms_core', '0013_v3_0_1'),
    ]

    operations = [
        migrations.CreateModel(
            name='SampleLineage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('child', models.ForeignKey(help_text='Child sample', on_delete=django.db.models.deletion.CASCADE,
                                            related_name='child_sample', to='fms_core.sample')),
                ('parent', models.ForeignKey(help_text='Parent sample', on_delete=django.db.models.deletion.CASCADE,
                                             related_name='parent_sample', to='fms_core.sample')),
            ],
        ),
        migrations.RenameField(
            model_name='sample',
            old_name='extracted_from',
            new_name='old_extracted_from',
        ),
        migrations.AddField(
            model_name='sample',
            name='child_of',
            field=models.ManyToManyField(blank=True, related_name='parent_of', through='fms_core.SampleLineage',
                                         to='fms_core.Sample'),
        ),
        migrations.RunPython(
            create_lineage_from_extracted,
            migrations.RunPython.noop
        ),
        migrations.RemoveField(
            model_name='sample',
            name='old_extracted_from',
        ),
    ]
