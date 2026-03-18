from django.contrib import admin
from django.db.models import Q
from django.utils.html import format_html

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from core.models import (
    Biobank,
    Collection,
    Sample,
    SampleFile,
    Event,
    Tag,
    Keyword,
    KeywordValue,
    Bacteria,
    Phage,
    HostRange,
    Plasmid
)

class SampleResource(resources.ModelResource):
    class Meta:
        model = Sample
        fields = ('id', 'sample_id', 'sample_type', 'organism_name', 'status', 'owner__username', 'created_at')

class SampleFileInline(admin.TabularInline):
    model = SampleFile
    extra = 0
    readonly_fields = ("uploaded_at", "mime_type", "file_size")

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)

@admin.register(Biobank)
class BiobankAdmin(admin.ModelAdmin):
    list_display = ("name", "location_label", "is_public", "is_active")
    filter_horizontal = ("tags", "keywords")

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "is_public")
    filter_horizontal = ("tags", "keywords")

@admin.register(Sample)
class SampleAdmin(ImportExportModelAdmin):
    resource_classes = [SampleResource]
    list_display = ("sample_id", "sample_type", "organism_name", "status", "owner", "created_at")
    list_filter = ("status", "sample_type", "is_public")
    search_fields = ("sample_id", "organism_name")
    inlines = [SampleFileInline]
    filter_horizontal = ("collections", "tags", "keywords")

@admin.register(Bacteria)
class BacteriaAdmin(admin.ModelAdmin):
    list_display = ("sample_id", "species", "strain", "owner")
    search_fields = ("sample_id", "species", "strain")
    filter_horizontal = ("collections", "tags", "keywords")

@admin.register(Phage)
class PhageAdmin(admin.ModelAdmin):
    list_display = ("sample_id", "taxonomy", "morphotype", "lifestyle")
    list_filter = ("morphotype", "lifestyle")
    filter_horizontal = ("collections", "tags", "keywords")

@admin.register(HostRange)
class HostRangeAdmin(admin.ModelAdmin):
    list_display = ("phage", "bacteria", "is_isolation_host", "efficiency_eop")
    list_filter = ("is_isolation_host",)

@admin.register(Plasmid)
class PlasmidAdmin(admin.ModelAdmin):
    # Atualizado com os novos campos unificados
    list_display = ("sample_id", "backbone_name", "insert_name", "construction_name", "total_size_bp", "is_empty_vector")
    search_fields = ("sample_id", "backbone_name", "insert_name", "construction_name")
    readonly_fields = ("total_size_bp",) 
    filter_horizontal = ("collections", "tags", "keywords")

@admin.register(SampleFile)
class SampleFileAdmin(admin.ModelAdmin):
    list_display = ("file", "sample", "category", "uploaded_at")

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("sample", "event_type", "timestamp", "performed_by")
    readonly_fields = ("timestamp",)
