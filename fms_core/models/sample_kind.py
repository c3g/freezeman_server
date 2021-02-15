import reversion

from django.db import models

@reversion.register()
class SampleKind(models.Model):
    name = models.CharField(max_length=200, help_text="Biological material collected from study subject "
                                                  "during the conduct of a genomic study project.")
    molecule_ontology_curie = models.CharField(
        help_text='SO ontology term to describe an molecule, such as ‘SO:0000991’ (‘genomic_DNA’)', max_length=20,
        unique=True)

    def __str__(self):
        return self.name











