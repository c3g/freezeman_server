from django.db import migrations, models

SAMPLE_KINDS = ['DNA', 'RNA', 'BLOOD', 'CELLS', 'EXPECTORATION', 'GARGLE', 'PLASMA', 'SALIVA', 'SWAB']


class Migration(migrations.Migration):

    def create_sample_kinds(apps, schema_editor):
        SampleKind = apps.get_model("fms_core", "SampleKind")
        for kind in SAMPLE_KINDS:
            SampleKind.objects.create(name=kind, molecule_ontology_curie=kind)

    def copy_samples_kinds(apps, schema_editor):
        Sample = apps.get_model("fms_core", "Sample")
        SampleKind = apps.get_model("fms_core", "SampleKind")
        sample_kind_ids_by_name = {sample_kind.name: sample_kind.id for sample_kind in SampleKind.objects.all()}

        for sample in Sample.objects.all():
            name = sample.biospecimen_type
            sample.sample_kind_id = sample_kind_ids_by_name[name]
            sample.save()

    #TODO: versions

    dependencies = [
        ('fms_core', '0013_v3_0_1'),
    ]

    operations = [
        migrations.CreateModel(
            name='SampleKind',
            fields=[
                ('name', models.CharField(choices=[('DNA', 'DNA'), ('RNA', 'RNA'), ('BLOOD', 'BLOOD'), ('CELLS', 'CELLS'),
                                                   ('EXPECTORATION', 'EXPECTORATION'), ('GARGLE', 'GARGLE'), ('PLASMA', 'PLASMA'),
                                                   ('SALIVA', 'SALIVA'), ('SWAB', 'SWAB')],
                                          help_text='Biological material collected from study subject during the conduct of a genomic study project.',
                                          max_length=200,
                                          unique=True)
                 ),
                ('molecule_ontology_curie', models.CharField(help_text='SO ontology term to describe an molecule, such as ‘SO:0000991’ (‘genomic_DNA’)', max_length=20, unique=True)),
            ],
        ),
        migrations.AddField(
            model_name='sample',
            name='sample_kind',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="samples",
                help_text="Sample kind.",
                to="fms_core.SampleKind",
            ),
        ),
        migrations.RunPython(
            create_sample_kinds,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            copy_samples_kinds,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
