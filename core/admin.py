from django.contrib import admin
from core.models import (
    Biobank,
    Collection,
    Sample,
    SampleFile,
    Event,
    CollectionUserRole,
    Tag,
    Keyword,
    KeywordValue,
)

# ============================================================
# TAGS
# ============================================================
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)

# ============================================================
# KEYWORDS
# ============================================================
@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)

@admin.register(KeywordValue)
class KeywordValueAdmin(admin.ModelAdmin):
    list_display = (
        "keyword",
        "value",
        "biobanks_list",
        "collections_list",
        "samples_list",
    )
    list_filter = ("keyword",)
    search_fields = ("keyword__name", "value")
    ordering = ("keyword__name", "value")

    def biobanks_list(self, obj):
        return ", ".join(b.name for b in obj.biobanks.all())
    biobanks_list.short_description = "Biobanks"

    def collections_list(self, obj):
        return ", ".join(c.name for c in obj.collections.all())
    collections_list.short_description = "Collections"

    def samples_list(self, obj):
        return ", ".join(s.sample_id for s in obj.samples.all())
    samples_list.short_description = "Samples"

# ============================================================
# INLINES
# ============================================================
class SampleFileInline(admin.TabularInline):
    model = SampleFile
    extra = 0
    # Campos que existem no modelo SampleFile
    readonly_fields = ("uploaded_at", "mime_type", "file_size")

class CollectionUserRoleInline(admin.TabularInline):
    model = CollectionUserRole
    extra = 0

# ============================================================
# BIOBANK
# ============================================================
@admin.register(Biobank)
class BiobankAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "institution",
        "location_label",
        "visibility",
        "is_active",
        "created_at",
    )
    search_fields = ("name", "institution", "location_label")
    list_filter = ("visibility", "is_active")
    ordering = ("name",)
    filter_horizontal = ("tags", "keywords")
    readonly_fields = ("created_at", "latitude", "longitude")

# ============================================================
# COLLECTION
# ============================================================
@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "biobank", "owners_display")
    search_fields = ("name", "description")
    list_filter = ("biobank",)
    inlines = [CollectionUserRoleInline]
    filter_horizontal = ("tags", "keywords")

# ============================================================
# SAMPLE
# ============================================================
@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    # Adicionado 'status' para controle de qualidade e 'uuid' para rastreio
    list_display = (
        "sample_id",
        "status",
        "sample_type",
        "organism_name",
        "collection",
        "biobank",
        "created_at",
    )
    list_filter = ("status", "collection", "biobank", "is_active")
    search_fields = ("sample_id", "organism_name", "sample_type", "uuid")
    ordering = ("-created_at",)
    inlines = [SampleFileInline]
    filter_horizontal = ("tags", "keywords")
    # UUID deve ser apenas leitura
    readonly_fields = ("uuid", "created_at", "updated_at")

# ============================================================
# SAMPLE FILE (CORRIGIDO)
# ============================================================
@admin.register(SampleFile)
class SampleFileAdmin(admin.ModelAdmin):
    # Alterado 'file_type' para 'category' e 'mime_type' que existem no modelo
    list_display = ("file", "sample", "category", "mime_type", "uploaded_at")
    list_filter = ("category", "uploaded_at")
    search_fields = ("file", "description")

# ============================================================
# EVENTS
# ============================================================
@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    # Adicionado 'location_snapshot' para o mapa de rastreabilidade
    list_display = ("sample", "event_type", "location_snapshot", "timestamp")
    list_filter = ("event_type", "timestamp")
    search_fields = ("sample__sample_id", "notes", "location_snapshot")
    readonly_fields = ("timestamp",)