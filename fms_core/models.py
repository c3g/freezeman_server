import re
import reversion

from decimal import Decimal
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from .containers import (
    CONTAINER_SPEC_TUBE,
    CONTAINER_SPEC_TUBE_RACK_8X12,
    CONTAINER_KIND_SPECS,
    CONTAINER_KIND_CHOICES,
    SAMPLE_CONTAINER_KINDS,
    PARENT_CONTAINER_KINDS,
)
from .coordinates import CoordinateError, check_coordinate_overlap
from .schema_validators import JsonSchemaValidator, VOLUME_VALIDATOR, EXPERIMENTAL_GROUP_SCHEMA
from .utils import str_normalize


__all__ = [
    "Container",
    "ContainerMove",
    "Sample",
    "ExtractedSample",
    "SampleUpdate",
    "Individual",
]


def add_error(errors: dict, field: str, error: ValidationError):
    errors[field] = [*errors.get(field, []), error]


barcode_name_validator = RegexValidator(re.compile(r"^[a-zA-Z0-9.-_]+$"))


@reversion.register()
class Container(models.Model):
    """ Class to store information about a sample. """
    # TODO class for choices
    kind = models.CharField(
        max_length=20,
        choices=CONTAINER_KIND_CHOICES,
        help_text="What kind of container this is. Dictates the coordinate system and other container-specific "
                  "properties."
    )
    # TODO: Trim and normalize any incoming values to prevent whitespace-sensitive names
    name = models.CharField(unique=True, max_length=200, help_text="Unique name for the container.",
                            validators=[barcode_name_validator])
    barcode = models.CharField(primary_key=True, max_length=200, help_text="Unique container barcode.",
                               validators=[barcode_name_validator])

    # In which container is this container located? i.e. its parent.
    location = models.ForeignKey("self", blank=True, null=True, on_delete=models.PROTECT, related_name="children",
                                 help_text="An existing (parent) container this container is located inside of.",
                                 limit_choices_to={"kind__in": PARENT_CONTAINER_KINDS})

    # Where in the parent container is this container located, if relevant?
    coordinates = models.CharField(max_length=20, blank=True,
                                   help_text="Coordinates of this container within the parent container.")
    comment = models.TextField(blank=True, help_text="Other relevant information about the container.")

    def __str__(self):
        return self.barcode

    def normalize(self):
        # Normalize any string values to make searching / data manipulation easier
        self.kind = str_normalize(self.kind).lower()
        self.name = str_normalize(self.name)
        self.barcode = str_normalize(self.barcode)
        self.coordinates = str_normalize(self.coordinates)
        self.comment = str_normalize(self.comment)

    def clean(self):
        errors = {}

        self.normalize()

        if self.coordinates != "" and self.location is None:
            add_error(errors, "coordinates", ValidationError("Cannot specify coordinates in non-specified container"))

        if self.location is not None:
            if self.location.barcode == self.barcode:
                add_error(errors, "location", ValidationError("Container cannot contain itself"))

            else:
                parent_spec = CONTAINER_KIND_SPECS[self.location.kind]

                # Validate that this container is allowed to be located in the parent container specified
                if not parent_spec.can_hold_kind(self.kind):
                    add_error(
                        errors,
                        "location",
                        ValidationError(f"Parent container kind {parent_spec.container_kind_id} cannot hold container "
                                        f"kind {self.kind}")
                    )

                if not errors.get("coordinates", None) and not errors.get("location", None):
                    # Validate coordinates against parent container spec
                    try:
                        self.coordinates = parent_spec.validate_and_normalize_coordinates(self.coordinates)
                    except CoordinateError as e:
                        add_error(errors, "coordinates", ValidationError(str(e)))

                if not errors.get("coordinates", None) and not errors.get("location", None) \
                        and not parent_spec.coordinate_overlap_allowed:
                    # Check for coordinate overlap with existing child containers of the parent
                    try:
                        check_coordinate_overlap(self.location.children, self, self.location)
                    except CoordinateError as e:
                        add_error(errors, "coordinates", ValidationError(str(e)))
                    except Container.DoesNotExist:
                        # Fine, the coordinates are free to use.
                        pass

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Normalize and validate before saving, always!
        self.normalize()
        self.full_clean()
        super().save(*args, **kwargs)  # Save the object


class ContainerMoveManager(models.Manager):
    # noinspection PyMethodMayBeStatic
    def get_queryset(self):
        return Container.objects.all()


class ContainerMove(Container):
    class Meta:
        proxy = True

    manager = ContainerMoveManager()


@reversion.register()
class Sample(models.Model):
    """ Class to store information about a sample. """

    BIOSPECIMEN_TYPE_DNA = "DNA"
    BIOSPECIMEN_TYPE_RNA = "RNA"
    BIOSPECIMEN_TYPE_BLOOD = "BLOOD"
    BIOSPECIMEN_TYPE_SALIVA = "SALIVA"

    NA_BIOSPECIMEN_TYPES = (BIOSPECIMEN_TYPE_DNA, BIOSPECIMEN_TYPE_RNA)
    NA_BIOSPECIMEN_TYPE_CHOICES = (
        (BIOSPECIMEN_TYPE_DNA, BIOSPECIMEN_TYPE_DNA),
        (BIOSPECIMEN_TYPE_RNA, BIOSPECIMEN_TYPE_RNA),
    )

    BIOSPECIMEN_TYPE_CHOICES = (
        *NA_BIOSPECIMEN_TYPE_CHOICES,
        (BIOSPECIMEN_TYPE_BLOOD, BIOSPECIMEN_TYPE_BLOOD),
        (BIOSPECIMEN_TYPE_SALIVA, BIOSPECIMEN_TYPE_SALIVA)
    )

    TISSUE_SOURCE_CHOICES = (
        ("Blood", "Blood"),
        ("Saliva", "Saliva"),
        ("Tumor", "Tumor"),
        ("Plasma", "Plasma"),
        ("Buffy coat", "Buffy coat"),
        ("Tail", "Tail"),
        ("Cells", "Cells"),
    )

    # TODO add validation if it's extracted sample then it can be of type DNA or RNA only
    biospecimen_type = models.CharField(max_length=200, choices=BIOSPECIMEN_TYPE_CHOICES,
                                        help_text="Biological material collected from study subject "
                                                  "during the conduct of a genomic study project.")
    # TODO: Trim and normalize any incoming values to prevent whitespace-sensitive names
    name = models.CharField(max_length=200, validators=[barcode_name_validator], help_text="Sample name.")
    alias = models.CharField(max_length=200, blank=True, help_text="Alternative sample name given by the "
                                                                   "collaborator or customer.")
    # TODO in case individual deleted should we set the value to default e.g. the individual record was deleted ?
    individual = models.ForeignKey('Individual', on_delete=models.PROTECT, help_text="Individual associated "
                                                                                     "with the sample.")
    volume_history = JSONField("volume history in µL", validators=[VOLUME_VALIDATOR],
                               help_text="Volume of the sample in µL.")

    # Concentration is REQUIRED if biospecimen_type in {DNA, RNA}.
    concentration = models.DecimalField(
        "concentration in ng/µL",
        max_digits=20,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Concentration in ng/µL. Required for nucleic acid samples."
    )

    depleted = models.BooleanField(default=False, help_text="Whether this sample has been depleted.")

    experimental_group = JSONField(blank=True, default=list,
                                   validators=[JsonSchemaValidator(EXPERIMENTAL_GROUP_SCHEMA)],
                                   help_text="Sample group having some common characteristics. "
                                             "It is the way to designate a subgroup within a study.")
    collection_site = models.CharField(max_length=200, help_text="The facility designated for the collection "
                                                                 "of samples.")
    tissue_source = models.CharField(max_length=200, blank=True, choices=TISSUE_SOURCE_CHOICES,
                                     help_text="Can only be specified if the biospecimen type is DNA or RNA.")
    reception_date = models.DateField(default=timezone.now, help_text="Date of the sample reception.")
    phenotype = models.CharField(max_length=200, blank=True, help_text="Sample phenotype.")
    comment = models.TextField(blank=True, help_text="Other relevant information about the sample.")

    # In what container is this sample located?
    # TODO: I would prefer consistent terminology with Container if possible for this heirarchy
    container = models.ForeignKey(Container, on_delete=models.PROTECT, related_name="samples",
                                  limit_choices_to={"kind__in": SAMPLE_CONTAINER_KINDS},
                                  help_text="Designated location of the sample.")
    # Location within the container, specified by coordinates
    # TODO list of choices ?
    coordinates = models.CharField(max_length=10, blank=True,
                                   help_text="Coordinates of the sample in a parent container. Only applicable for "
                                             "containers that directly store samples with coordinates, e.g. plates.")

    # TODO Collection site (Optional but for big study, a choice list will be included in the Submission file) ?

    # fields only for extracted samples
    extracted_from = models.ForeignKey("self", blank=True, null=True, on_delete=models.PROTECT,
                                       related_name="extractions",
                                       help_text="The sample this sample was extracted from. Can only be specified for "
                                                 "extracted nucleic acid samples.")
    volume_used = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True,
                                      help_text="Volume of the original sample used for the extraction, in µL. Must "
                                                "be specified only for extracted nucleic acid samples.")

    class Meta:
        unique_together = ('container', 'coordinates')

    @property
    def is_depleted(self) -> str:
        return "yes" if self.depleted else "no"

    # noinspection PyUnresolvedReferences
    @property
    def volume(self) -> Decimal:
        return (Decimal("{:.3f}".format(Decimal(self.volume_history[-1]["volume_value"]))) if self.volume_history
                else Decimal("0.000"))

    # Computed properties for individuals

    @property
    def individual_name(self) -> str:
        return self.individual.name if self.individual else ""

    @property
    def individual_sex(self):
        return self.individual.sex if self.individual else ""

    @property
    def individual_taxon(self):
        return self.individual.taxon if self.individual else ""

    @property
    def individual_cohort(self) -> str:
        return self.individual.cohort if self.individual else ""

    @property
    def individual_pedigree(self):
        return self.individual.pedigree if self.individual else ""

    @property
    def individual_mother(self):
        return self.individual.mother if self.individual else None

    @property
    def individual_father(self):
        return self.individual.father if self.individual else None

    # Computed properties for containers

    @property
    def container_kind(self):
        return self.container.kind if self.container else None

    @property
    def container_name(self):
        return self.container.name if self.container else None

    @property
    def container_location(self):
        return self.container.location if self.container else None

    @property
    def context_sensitive_coordinates(self):
        return self.coordinates if self.coordinates else (self.container.coordinates if self.container else "")

    # Representations

    def __str__(self):
        return f"{self.name} ({'extracted, ' if self.extracted_from else ''}" \
               f"{self.container}{f' at {self.coordinates }' if self.coordinates else ''})"

    # ORM Methods

    def normalize(self):
        # Normalize any string values to make searching / data manipulation easier
        self.name = str_normalize(self.name)
        self.alias = str_normalize(self.alias)
        self.collection_site = str_normalize(self.collection_site)
        self.tissue_source = str_normalize(self.tissue_source)
        self.phenotype = str_normalize(self.phenotype)
        self.comment = str_normalize(self.comment)

    def clean(self):
        errors = {}

        self.normalize()

        biospecimen_type_choices = (Sample.NA_BIOSPECIMEN_TYPE_CHOICES if self.extracted_from
                                    else Sample.BIOSPECIMEN_TYPE_CHOICES)
        if self.biospecimen_type not in frozenset(c[0] for c in biospecimen_type_choices):
            add_error(
                errors,
                "biospecimen_type",
                ValidationError(f"Biospecimen type {self.biospecimen_type} not valid for"
                                f"{' extracted' if self.extracted_from else ''} sample {self.name}"),
            )

        if self.extracted_from:
            if self.extracted_from.biospecimen_type in Sample.NA_BIOSPECIMEN_TYPES:
                add_error(
                    errors,
                    "extracted_from",
                    ValidationError(f"Extraction process cannot be run on sample of type "
                                    f"{self.extracted_from.biospecimen_type}")
                )

            if self.volume_used is None:
                add_error(errors, "volume_used", ValidationError("Extracted samples must specify volume_used"))

            elif self.volume_used <= Decimal("0"):
                add_error(errors, "volume_used", ValidationError("volume_used must be positive"))

        if self.volume_used is not None and not self.extracted_from:
            add_error(errors, "volume_used", ValidationError("Non-extracted samples cannot specify volume_used"))

        # Check concentration fields given biospecimen_type

        if self.biospecimen_type in Sample.NA_BIOSPECIMEN_TYPES and self.concentration is None:
            add_error(
                errors,
                "concentration",
                ValidationError("Concentration must be specified if the biospecimen_type is DNA or RNA")
            )

        # Check tissue source given extracted_from

        if self.tissue_source and self.biospecimen_type not in Sample.NA_BIOSPECIMEN_TYPES:
            add_error(
                errors,
                "tissue_source",
                ValidationError("Tissue source can only be specified for a nucleic acid sample.")
            )

        # Validate container consistency

        if self.container_id is not None:
            parent_spec = CONTAINER_KIND_SPECS[self.container.kind]

            #  - Validate that parent can hold samples
            if not parent_spec.sample_holding:
                add_error(
                    errors,
                    "container",
                    ValidationError(f"Parent container kind {parent_spec.container_kind_id} cannot hold samples")
                )

            #  - Currently, extractions can only output tubes in a TUBE_RACK_8X12
            if self.extracted_from is not None and any((
                    parent_spec != CONTAINER_SPEC_TUBE,
                    self.container.location is None,
                    CONTAINER_KIND_SPECS[self.container.location.kind] != CONTAINER_SPEC_TUBE_RACK_8X12
            )):
                add_error(
                    errors,
                    "container",
                    ValidationError("Extractions currently must be conducted on a tube in an 8x12 tube rack")
                )

            #  - Validate coordinates against parent container spec
            if not errors.get("container"):
                try:
                    self.coordinates = parent_spec.validate_and_normalize_coordinates(self.coordinates)
                except CoordinateError as e:
                    add_error(errors, "container", ValidationError(str(e)))

            # TODO: This isn't performant for bulk ingestion
            # - Check for coordinate overlap with existing child containers of the parent
            if not errors.get("container", None) and not parent_spec.coordinate_overlap_allowed:
                try:
                    check_coordinate_overlap(self.container.samples, self, self.container, obj_type="sample")
                except CoordinateError as e:
                    add_error(errors, "container", ValidationError(str(e)))
                except Sample.DoesNotExist:
                    # Fine, the coordinates are free to use.
                    pass

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Normalize and validate before saving, always!
        self.normalize()
        self.full_clean()
        super().save(*args, **kwargs)  # Save the object


class ExtractedSampleManager(models.Manager):
    # noinspection PyMethodMayBeStatic
    def get_queryset(self):
        return Sample.objects.filter(extracted_from__isnull=False)


class ExtractedSample(Sample):
    class Meta:
        proxy = True

    manager = ExtractedSampleManager()


class SampleUpdateManager(models.Manager):
    # noinspection PyMethodMayBeStatic
    def get_queryset(self):
        return Sample.objects.all()


class SampleUpdate(Sample):
    class Meta:
        proxy = True

    manager = SampleUpdateManager()


@reversion.register()
class Individual(models.Model):
    """ Class to store information about an Individual. """

    TAXON_HOMO_SAPIENS = "Homo sapiens"
    TAXON_MUS_MUSCULUS = "Mus musculus"

    TAXON_CHOICES = (
        (TAXON_HOMO_SAPIENS, TAXON_HOMO_SAPIENS),
        (TAXON_MUS_MUSCULUS, TAXON_MUS_MUSCULUS),
    )

    SEX_MALE = "M"
    SEX_FEMALE = "F"
    SEX_UNKNOWN = "Unknown"

    SEX_CHOICES = (
        (SEX_MALE, SEX_MALE),
        (SEX_FEMALE, SEX_FEMALE),
        (SEX_UNKNOWN, SEX_UNKNOWN),
    )

    name = models.CharField(primary_key=True, max_length=200, help_text="Unique identifier for the individual.")
    taxon = models.CharField(choices=TAXON_CHOICES, max_length=20, help_text="Taxonomic group of a species.")
    sex = models.CharField(choices=SEX_CHOICES, max_length=10, help_text="Sex of the individual.")
    pedigree = models.CharField(max_length=200, blank=True, help_text="Common ID to associate children and parents.")
    mother = models.ForeignKey("self", blank=True, null=True, on_delete=models.PROTECT, related_name="mother_of",
                               help_text="Mother of the individual.")
    father = models.ForeignKey("self", blank=True, null=True, on_delete=models.PROTECT, related_name="father_of",
                               help_text="Father of the individual.")
    # required ?
    cohort = models.CharField(max_length=200, blank=True, help_text="Label to group some individuals in "
                                                                    "a specific study.")

    def __str__(self):
        return self.name

    def normalize(self):
        # Normalize any string values to make searching / data manipulation easier
        self.name = str_normalize(self.name)
        self.pedigree = str_normalize(self.pedigree)
        self.cohort = str_normalize(self.cohort)

    def clean(self):
        errors = {}

        self.normalize()

        if self.mother is not None and self.father is not None and self.mother == self.father:
            e = ValidationError("Mother and father IDs can't be the same.")
            add_error(errors, "mother", e)
            add_error(errors, "father", e)

        if self.mother and self.mother.name == self.name:
            add_error(errors, "mother", ValidationError("Mother can't be same as self."))

        if self.father and self.father.name == self.name:
            add_error(errors, "father", ValidationError("Father can't be same as self."))

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Normalize and validate before saving, always!
        self.normalize()
        self.full_clean()
        super().save(*args, **kwargs)  # Save the object
