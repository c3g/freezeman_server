import re
import reversion

from datetime import datetime
from django.db.models import Q
from import_export import resources
from import_export.fields import Field
from import_export.widgets import DateWidget, DecimalWidget, ForeignKeyWidget, JSONWidget
from reversion.models import Version

from .containers import (
    CONTAINER_SPEC_TUBE,
    CONTAINER_SPEC_TUBE_RACK_8X12,
    SAMPLE_CONTAINER_KINDS,
    SAMPLE_CONTAINER_KINDS_WITH_COORDS,
)
from .models import create_volume_history, Container, Sample, Individual


__all__ = [
    "GenericResource",
    "ContainerResource",
    "SampleResource",
    "IndividualResource",
    "ExtractionResource",
    "ContainerMoveResource",
    "SampleUpdateResource",
]


RE_WHITESPACE = re.compile(r"\s+")


def check_truth_like(string: str) -> bool:
    """
    Checks if a string contains a "truth-like" value, e.g. true, yes, etc.
    """
    return string.strip().upper() in ("TRUE", "T", "YES", "Y")


def normalize_scientific_name(name: str) -> str:
    # Converts (HOMO SAPIENS or Homo Sapiens or ...) to Homo sapiens
    return " ".join((a.title() if i == 0 else a.lower()) for i, a in enumerate(RE_WHITESPACE.split(name)))


def skip_rows(dataset, num_rows=0, col_skip=1):
    if num_rows <= 0:
        return
    dataset_headers = dataset[num_rows - 1]
    dataset_data = dataset[num_rows:]
    dataset.wipe()
    dataset.headers = dataset_headers
    for r in dataset_data:
        vals = set(r[col_skip:])
        if len(vals) == 1 and "" in vals:
            continue
        dataset.append(r)


class GenericResource(resources.ModelResource):
    clean_model_instances = True
    skip_unchanged = True

    def save_instance(self, instance, using_transactions=True, dry_run=False):
        if dry_run:
            with reversion.create_revision(manage_manually=True):
                # Prevent reversion from saving on dry runs by manually overriding the current revision
                super().save_instance(instance, using_transactions, dry_run)
        else:
            super().save_instance(instance, using_transactions, dry_run)

    def after_save_instance(self, instance, using_transactions, dry_run):
        if not dry_run:
            versions = Version.objects.get_for_object(instance)
            if len(versions) >= 1:
                reversion.set_comment("Updated from template.")
            else:
                reversion.set_comment("Imported from template.")


class ContainerResource(GenericResource):
    kind = Field(attribute='kind', column_name='Container Kind')
    name = Field(attribute='name', column_name='Container Name')
    barcode = Field(attribute='barcode', column_name='Container Barcode')
    location = Field(attribute='location', column_name='Location Barcode',
                     widget=ForeignKeyWidget(Container, 'barcode'))
    coordinates = Field(attribute='coordinates', column_name='Location Coordinate')
    comment = Field(attribute='comment', column_name='Comment')

    class Meta:
        model = Container
        import_id_fields = ('barcode',)
        fields = ('kind', 'name', 'barcode', 'location', 'coordinates',)

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        skip_rows(dataset, 6)

    def import_field(self, field, obj, data, is_m2m=False):
        if field.attribute == 'kind':
            # Normalize kind attribute to be lowercase
            data["Container Kind"] = data["Container Kind"].lower().strip()
        super().import_field(field, obj, data, is_m2m)

    def after_save_instance(self, instance, using_transactions, dry_run):
        super().after_save_instance(instance, using_transactions, dry_run)
        reversion.set_comment("Imported containers from template.")


class SampleResource(GenericResource):
    # Simple model fields
    biospecimen_type = Field(attribute='biospecimen_type', column_name='Biospecimen Type')
    name = Field(attribute='name', column_name='Sample Name')
    alias = Field(attribute='alias', column_name='Alias')

    concentration = Field(attribute='concentration', column_name='Conc. (ng/uL)', widget=DecimalWidget())
    depleted = Field(attribute='depleted', column_name='Source Depleted')

    experimental_group = Field(attribute='experimental_group', column_name='Experimental Group')
    collection_site = Field(attribute='collection_site', column_name='Collection Site')
    tissue_source = Field(attribute='tissue_source', column_name='Tissue Source')
    reception_date = Field(attribute='reception_date', column_name='Reception Data', widget=DateWidget())
    phenotype = Field(attribute='phenotype', column_name='Phenotype')

    comment = Field(attribute='comment', column_name='Comment')

    # FK fields
    container = Field(attribute='container', column_name='Container Barcode',
                      widget=ForeignKeyWidget(Container, field='barcode'))

    # Non-attribute fields
    volume = Field(column_name='Volume (uL)', widget=DecimalWidget())
    individual_name = Field(column_name='Individual Name')
    sex = Field(column_name='Sex')
    taxon = Field(column_name='Taxon')

    # Computed fields
    coordinates = Field(attribute='coordinates')
    individual = Field(attribute='individual', widget=ForeignKeyWidget(Individual, field='participant_id'))
    volume_history = Field(attribute='volume_history', widget=JSONWidget())

    class Meta:
        model = Sample
        import_id_fields = ('container',)  # TODO: Should include coordinates too, but missing field???
        fields = (
            'biospecimen_type',
            'name',
            'alias',
            'concentration',
            'collection_site',
            'container',
        )
        excluded = ('volume_history', 'individual')

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        skip_rows(dataset, 6)

    def import_field(self, field, obj, data, is_m2m=False):
        # Ugly hacks lie below

        if field.attribute == 'individual':
            # Sample import can optionally create new individuals in the system; or re-use existing ones.
            # TODO: This should throw a warning if the individual already exists
            individual, _ = Individual.objects.get_or_create(
                name=data["Individual Name"],
                sex=data["Sex"],
                taxon=data["Taxon"]
            )
            obj.individual = individual

        elif field.attribute == 'volume_history':
            # We store volume as a JSON object of historical values, so this needs to be initialized in a custom way.
            obj.volume_history = [create_volume_history("update", data["Volume (uL)"])]

        elif field.attribute == 'container':
            if data['Container Kind'] in SAMPLE_CONTAINER_KINDS:
                # Oddly enough, Location Coord is contextual - when Container Kind is one with coordinates, this
                # specifies the sample's location within the container itself. Otherwise, it specifies the location of
                # the container within the parent container.

                container_data = dict(
                    kind=data['Container Kind'],
                    name=data['Container Name'],
                    barcode=data['Container Barcode'],
                    location=Container.objects.get(barcode=data['Location Barcode']),
                )

                if data['Container Kind'] in SAMPLE_CONTAINER_KINDS_WITH_COORDS:
                    # Case where container itself has a coordinate system; in this case the SAMPLE gets the coordinates.
                    obj.coordinates = data['Location Coord']
                else:
                    # Case where the container gets coordinates within the parent.
                    container_data["coordinates"] = data['Location Coord']

                # If needed, create a sample-holding container to store the current sample; or retrieve an existing one
                # with the correct barcode. This will throw an error if the kind specified mismatches with an existing
                # barcode record in the database, which serves as an ad-hoc additional validation step.

                container, _ = Container.objects.get_or_create(**container_data)
                obj.container = container

        else:
            if field.attribute == 'taxon':
                # Normalize scientific names to have the correct capitalization
                data['Taxon'] = normalize_scientific_name(data['Taxon'])
            super().import_field(field, obj, data, is_m2m)

    def before_save_instance(self, instance, using_transactions, dry_run):
        # TODO: Don't think this is needed
        instance.individual.save()
        super().before_save_instance(instance, using_transactions, dry_run)

    def after_save_instance(self, instance, using_transactions, dry_run):
        super().after_save_instance(instance, using_transactions, dry_run)
        reversion.set_comment("Imported samples from template.")


class ExtractionResource(GenericResource):
    biospecimen_type = Field(attribute='biospecimen_type', column_name='Extraction Type')

    reception_date = Field(attribute='reception_date')
    concentration = Field(attribute='concentration', column_name='Conc. (ng/uL)', widget=DecimalWidget())
    volume_used = Field(attribute='volume_used', column_name='Volume Used (uL)', widget=DecimalWidget())

    # Non-attribute fields
    location = Field(column_name='Nucleic Acid Location Barcode', widget=ForeignKeyWidget(Container, field='barcode'))
    coordinates = Field(column_name='Nucleic Acid Location Coord')
    volume = Field(column_name='Volume (uL)', widget=DecimalWidget())
    sample_container = Field(column_name='Container Barcode')
    sample_container_coordinates = Field(column_name='Location Coord')
    source_depleted = Field(column_name='Source Depleted')

    # Computed fields
    name = Field(attribute='name')
    alias = Field(attribute='alias')
    collection_site = Field(attribute='collection_site')
    container = Field(attribute='container', widget=ForeignKeyWidget(Container, field='barcode'))
    individual = Field(attribute='individual', widget=ForeignKeyWidget(Individual, field='participant_id'))
    extracted_from = Field(attribute='extracted_from', widget=ForeignKeyWidget(Sample, field='name'))
    volume_history = Field(attribute='volume_history', widget=JSONWidget())

    class Meta:
        model = Sample
        fields = (
            'biospecimen_type',
            'reception_date',
            'volume',
            'concentration',
            'volume_used',
        )
        excluded = (
            'name',
            'alias',
            'collection_site',
            'container',
            'individual',
            'extracted_from',
            'volume_history',
        )

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        skip_rows(dataset, 7)  # Skip preamble

    def import_field(self, field, obj, data, is_m2m=False):
        # More!! ugly hacks

        if field.attribute == 'volume_history':
            # We store volume as a JSON object of historical values, so this needs to be initialized in a custom way.
            # In this case we are initializing the volume history of the EXTRACTED sample.
            obj.volume_history = [create_volume_history("update", data["Volume (uL)"])]

        elif field.attribute == 'extracted_from':
            obj.extracted_from = Sample.objects.get(
                Q(container=data['Container Barcode']) &
                Q(coordinates=data['Location Coord'])
            )
            # Cast the "Source Depleted" cell to a Python Boolean value and update the original sample if needed.
            obj.extracted_from.depleted = obj.extracted_from.depleted or check_truth_like(data['Source Depleted'])

        elif field.attribute == 'container':
            # Per Alex: We can make new tube racks (8x12) if needed for extractions

            shared_parent_info = dict(
                barcode=data['Nucleic Acid Location Barcode'],
                # TODO: Currently can only extract into tube racks 8x12 - otherwise this logic will fall apart
                kind=CONTAINER_SPEC_TUBE_RACK_8X12.container_kind_id
            )

            try:
                parent = Container.objects.get(**shared_parent_info)
            except Container.DoesNotExist:
                parent = Container(
                    **shared_parent_info,
                    # Below is creation-specific data
                    # Leave coordinates blank if creating
                    # Per Alex: Container name = container barcode if we auto-generate the container
                    name=shared_parent_info["barcode"],
                    comment=f'Automatically generated via extraction template import on '
                            f'{datetime.utcnow().isoformat()}Z'
                )

            # Per Alex: We can make new tubes if needed for extractions

            # Information that can be used to either retrieve or create a new tube container
            shared_container_info = dict(
                barcode=data['Nucleic Acid Container Barcode'],
                # TODO: Currently can only extract into tubes - otherwise this logic will fall apart
                kind=CONTAINER_SPEC_TUBE.container_kind_id,
                location=parent,
                coordinates=data['Nucleic Acid Location Coord']
            )

            try:
                obj.container = Container.objects.get(**shared_container_info)
            except Container.DoesNotExist:
                obj.container = Container(
                    **shared_container_info,
                    # Below is creation-specific data
                    # Per Alex: Container name = container barcode if we auto-generate the container
                    name=shared_container_info["barcode"],
                    comment=f'Automatically generated via extraction template import on '
                            f'{datetime.utcnow().isoformat()}Z'
                )
                obj.container.save()

        else:
            super().import_field(field, obj, data, is_m2m)

    def before_save_instance(self, instance, using_transactions, dry_run):
        instance.name = instance.extracted_from.name
        instance.alias = instance.extracted_from.alias
        instance.collection_site = instance.extracted_from.collection_site  # TODO: Check with Alex
        instance.individual = instance.extracted_from.individual

        # Update volume and depletion status of original
        instance.extracted_from.volume_history.append(create_volume_history(
            "extraction",
            instance.extracted_from.volume - instance.volume_used,
            instance.extracted_from.id
        ))

        instance.extracted_from.save()

        super().before_save_instance(instance, using_transactions, dry_run)

    def after_save_instance(self, instance, using_transactions, dry_run):
        super().after_save_instance(instance, using_transactions, dry_run)
        reversion.set_comment("Imported extracted samples from template.")


class IndividualResource(GenericResource):
    class Meta:
        model = Individual
        import_id_fields = ('name',)


# Update resources

class ContainerMoveResource(GenericResource):
    barcode = Field(attribute='barcode', column_name='Container Barcode to move')
    location = Field(attribute='location', column_name='Dest. Location Barcode',
                     widget=ForeignKeyWidget(Container, field='barcode'))
    coordinates = Field(attribute='coordinates', column_name='Dest. Location Coord')
    comment = Field(attribute='comment', column_name='Comment')

    class Meta:
        model = Container
        import_id_fields = ('barcode',)
        fields = (
            'barcode',
            'location',
            'coordinates',
            'comment',
        )

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        skip_rows(dataset, 6)  # Skip preamble

    def import_field(self, field, obj, data, is_m2m=False):
        if field.attribute == 'barcode':
            container_to_move = Container.objects.get(barcode=data["Container Barcode to move"])
            obj.barcode = container_to_move.barcode
            obj.kind = container_to_move.kind
            obj.name = container_to_move.name
            obj.location = Container.objects.get(barcode=data["Dest. Location Barcode"])
            obj.coordinates = data.get("Dest. Location Coord", "")
            # comment if empty does that mean that comment was removed? or not just not added
            obj.comment = data.get("Comment", container_to_move.comment)
            #obj.save()

        else:
            super().import_field(field, obj, data, is_m2m)

    def after_save_instance(self, instance, using_transactions, dry_run):
        super().after_save_instance(instance, using_transactions, dry_run)
        reversion.set_comment("Moved containers from template.")


class SampleUpdateResource(GenericResource):
    # fields to retrieve a sample
    id = Field(attribute='id', column_name='id')
    container = Field(attribute='container', column_name='Container Barcode',
                      widget=ForeignKeyWidget(Container, field='barcode'))
    coordinates = Field(attribute='coordinates', column_name='Coord (if plate)')
    # fields that can be updated on sample update
    # new volume
    volume_history = Field(attribute='volume_history', column_name='New Volume (uL)')
    # new concentration
    concentration = Field(attribute='concentration', column_name='New Conc. (ng/uL)')
    depleted = Field(attribute="depleted", column_name="Depleted")
    comment = Field(attribute="comment", column_name="Comment")

    class Meta:
        model = Sample
        import_id_fields = ('id',)
        fields = ('volume_history',
                  'concentration',
                  'depleted',
                  'comment',
                  )
        exclude = ('container', 'coordinates', )

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        skip_rows(dataset, 6)  # Skip preamble

        # add column 'id' with pk
        ids = []
        for d in dataset.dict:
            single_id = Sample.objects.get(
                    Q(container=d['Container Barcode']) &
                    Q(coordinates=d['Coord (if plate)'])
                )
            ids.append(single_id.pk)
        dataset.append_col(ids, header='id')

        super().before_import(dataset, using_transactions, dry_run, **kwargs)

    def import_field(self, field, obj, data, is_m2m=False):
        if field.attribute == 'id':
            obj = Sample.objects.get(pk=data['id'])
            obj.concentration = data["New Conc. (ng/uL)"]
            obj.comment = data["Comment"]
        elif field.attribute == 'volume_history':
            obj.volume_history.append(
                create_volume_history("update", data["New Volume (uL)"])
            )

        else:
            if field.attribute == 'depleted':
                # Normalize boolean attribute
                data["Depleted"] = check_truth_like(data["Depleted"])

            super().import_field(field, obj, data, is_m2m)

    def after_save_instance(self, instance, using_transactions, dry_run):
        super().after_save_instance(instance, using_transactions, dry_run)
        reversion.set_comment("Updated samples from template.")
