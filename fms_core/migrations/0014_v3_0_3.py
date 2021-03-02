# Generated by Django 3.1 on 2021-03-02 15:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fms_core', '0013_v3_0_1'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sample',
            name='biospecimen_type',
            field=models.CharField(choices=[('DNA', 'DNA'), ('RNA', 'RNA'), ('BAL', 'BAL'), ('BLOOD', 'BLOOD'), ('CELLS', 'CELLS'), ('EXPECTORATION', 'EXPECTORATION'), ('GARGLE', 'GARGLE'), ('PLASMA', 'PLASMA'), ('SALIVA', 'SALIVA'), ('SWAB', 'SWAB')], help_text='Biological material collected from study subject during the conduct of a genomic study project.', max_length=200),
        ),
        migrations.AlterField(
            model_name='sample',
            name='tissue_source',
            field=models.CharField(blank=True, choices=[('BAL', 'BAL'), ('Blood', 'Blood'), ('Cells', 'Cells'), ('Expectoration', 'Expectoration'), ('Gargle', 'Gargle'), ('Plasma', 'Plasma'), ('Saliva', 'Saliva'), ('Swab', 'Swab'), ('Tumor', 'Tumor'), ('Buffy coat', 'Buffy coat'), ('Tail', 'Tail')], help_text='Can only be specified if the biospecimen type is DNA or RNA.', max_length=200),
        ),
    ]
