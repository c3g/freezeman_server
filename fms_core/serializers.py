from django.contrib.auth.models import User
from rest_framework import serializers
from reversion.models import Version

from .models import Container, Sample, Individual


__all__ = [
    "ContainerSerializer",
    "ContainerExportSerializer",
    "SimpleContainerSerializer",
    "IndividualSerializer",
    "SampleSerializer",
    "SampleExportSerializer"
    "NestedSampleSerializer",
    "VersionSerializer",
    "UserSerializer",
]


class ContainerSerializer(serializers.ModelSerializer):
    children = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    samples = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Container
        fields = "__all__"


class SimpleContainerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Container
        fields = "__all__"

class ContainerExportSerializer(serializers.ModelSerializer):
    location = serializers.SlugRelatedField(slug_field='barcode', read_only=True)
    class Meta:
        model = Container
        fields = ('kind', 'name', 'barcode', 'location', 'coordinates', 'comment')


class IndividualSerializer(serializers.ModelSerializer):
    class Meta:
        model = Individual
        fields = "__all__"

class SampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sample
        fields = "__all__"

class SampleExportSerializer(serializers.ModelSerializer):
    individual_id = serializers.CharField(read_only=True, source="individual.label")
    taxon = serializers.CharField(read_only=True, source="individual.taxon")
    sex = serializers.CharField(read_only=True, source="individual.sex")
    pedigree = serializers.CharField(read_only=True, source="individual.pedigree")
    # left : mother, father, container location
    container_kind = serializers.CharField(read_only=True, source="container.kind")
    container_name = serializers.CharField(read_only=True, source="container.name")
    container_barcode = serializers.CharField(read_only=True, source="container.barcode")
    container_coordinates = serializers.CharField(read_only=True, source="container.coordinates")

    class Meta:
        model = Sample
        fields = ('biospecimen_type', 'name', 'alias', 'concentration', 'depleted', 'collection_site', 'tissue_source',
                  'reception_date', 'phenotype', 'comment', 'coordinates', 'volume_used',
                  'individual_id', 'taxon', 'sex', 'pedigree',
                  'container_kind', 'container_name', 'container_barcode', 'container_coordinates')


class NestedSampleSerializer(serializers.ModelSerializer):
    # Serialize foreign keys' objects; don't allow posting new objects (rather accept foreign keys)
    individual = IndividualSerializer(read_only=True)
    container = SimpleContainerSerializer(read_only=True)
    extracted_from = SampleSerializer(read_only=True)

    class Meta:
        model = Sample
        fields = "__all__"


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Version
        fields = "__all__"
        depth = 1


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "groups", "is_staff", "is_superuser", "date_joined")
        depth = 1
