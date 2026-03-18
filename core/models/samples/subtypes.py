from django.db import models
from django.core.validators import MinValueValidator
from .sample import Sample

# =========================================================
# 1. BACTERIA (Hosts)
# =========================================================
class Bacteria(Sample):
    official_name = models.CharField(max_length=200, blank=True, null=True, help_text="Official/Standard Name")
    aliases = models.TextField(blank=True, null=True, help_text="Alternative names or common aliases")
    genus = models.CharField(max_length=100, blank=True, null=True, help_text="Genus. Ex: Escherichia")
    species = models.CharField(max_length=150, help_text="Scientific name. Ex: Escherichia coli")
    strain = models.CharField(max_length=100, blank=True, null=True, help_text="Strain (Ex: BL21, MG1655)")
    genotype = models.TextField(blank=True, null=True, help_text="Genetic markers")
    resistance_markers = models.JSONField(default=list, blank=True, help_text="List of antibiotic resistance markers")
    isolation_source = models.CharField(max_length=200, blank=True, null=True)
    additional_info = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Bacteria"
        verbose_name_plural = "Bacteria"


# =========================================================
# 2. PHAGES (Viruses)
# =========================================================
class Phage(Sample):
    MORPHOTYPE_CHOICES = [
        ('myovirus', 'Myovirus'),
        ('siphovirus', 'Siphovirus'),
        ('podovirus', 'Podovirus'),
        ('other', 'Other'),
    ]
    LIFESTYLE_CHOICES = [
        ('lytic', 'Lytic'),
        ('lysogenic', 'Lysogenic'),
    ]
    GENOME_CHOICES = [
        ('dsDNA', 'dsDNA'),
        ('ssDNA', 'ssDNA'),
        ('dsRNA', 'dsRNA'),
        ('ssRNA', 'ssRNA'),
    ]

    official_name = models.CharField(max_length=200, blank=True, null=True, help_text="Official/Standard Name")
    aliases = models.TextField(blank=True, null=True, help_text="Alternative names or common aliases")
    phage_name = models.CharField(max_length=100, blank=True, null=True, help_text="Phage Name. Ex: T4")
    genus = models.CharField(max_length=100, blank=True, null=True, help_text="Genus. Ex: Tequatrovirus")
    morphotype = models.CharField(max_length=50, choices=MORPHOTYPE_CHOICES, blank=True, null=True)
    taxonomy = models.CharField(max_length=100, blank=True, null=True, help_text="Ex: Autographiviridae, Straboviridae")
    lifestyle = models.CharField(max_length=50, choices=LIFESTYLE_CHOICES, blank=True, null=True)
    isolation_source = models.CharField(max_length=255, blank=True, null=True, help_text="Ex: Sewage, soil, clinical sample")
    isolation_method = models.CharField(max_length=100, blank=True, null=True)
    genome_type = models.CharField(max_length=20, choices=GENOME_CHOICES, blank=True, null=True)
    genome_size_bp = models.PositiveIntegerField(blank=True, null=True, help_text="Size in base pairs (bp)")
    ncbi_accession = models.CharField(max_length=100, blank=True, null=True, help_text="GenBank Link/ID")
    temp_C = models.DecimalField(max_digits=4, decimal_places=1, blank=True, null=True, help_text="Optimal growth temperature")

    class Meta:
        verbose_name = "Phage"


# =========================================================
# 3. HOST RANGE (The Junction Table / Graph)
# =========================================================
class HostRange(models.Model):
    phage = models.ForeignKey(Phage, on_delete=models.CASCADE, related_name='host_interactions')
    bacteria = models.ForeignKey(Bacteria, on_delete=models.CASCADE, related_name='phage_interactions')
    is_isolation_host = models.BooleanField(default=False, help_text="Defines if this is the isolation host bacteria")
    efficiency_eop = models.FloatField(blank=True, null=True, validators=[MinValueValidator(0.0)])
    plaque_morphology = models.ImageField(upload_to='plaque_images/', blank=True, null=True)
    notes = models.TextField(blank=True, null=True, help_text="Specific details about this infection/interaction")

    class Meta:
        unique_together = ('phage', 'bacteria')
        verbose_name = "Host Range Interaction"


# =========================================================
# 4. PLASMIDS (Unified: Backbone + Insert)
# =========================================================
class Plasmid(Sample):
    VECTOR_TYPE_CHOICES = [
        ('expression', 'Expression'),
        ('suicide', 'Suicide'),
        ('conjugation', 'Conjugation'),
        ('cloning', 'Cloning'),
    ]

    # --- Backbone Info ---
    backbone_name = models.CharField(max_length=150, help_text="Ex: pET28a(+)")
    backbone_aliases = models.TextField(blank=True, null=True, help_text="Alternative names")
    vector_type = models.CharField(max_length=50, choices=VECTOR_TYPE_CHOICES, blank=True, null=True)
    induction_system = models.CharField(max_length=100, blank=True, null=True, help_text="Ex: T7, lac, araBAD")
    origin_of_replication = models.CharField(max_length=100, blank=True, null=True, help_text="Ex: pBR322, pUC")
    backbone_size_bp = models.PositiveIntegerField(default=0)
    backbone_resistance_markers = models.JSONField(default=list, blank=True)

    # --- State Toggle ---
    is_empty_vector = models.BooleanField(default=True, help_text="Is this circulating as an empty backbone?")

    # --- Insert Info ---
    insert_name = models.CharField(max_length=150, blank=True, null=True, help_text="Ex: eGFP")
    purpose = models.CharField(max_length=255, blank=True, null=True, help_text="Purpose / Function of the insert")
    insert_size_bp = models.PositiveIntegerField(default=0)
    insert_resistance_markers = models.JSONField(default=list, blank=True)
    construction_name = models.CharField(max_length=200, blank=True, null=True, help_text="Ex: pET28a-GFP")

    total_size_bp = models.PositiveIntegerField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Auto-calcula o tamanho total
        self.total_size_bp = (self.backbone_size_bp or 0) + (self.insert_size_bp or 0)
        
        # Limpa os dados do inserto se o toggle for marcado como "Empty Vector"
        if self.is_empty_vector:
            self.insert_name = ""
            self.purpose = ""
            self.insert_size_bp = 0
            self.insert_resistance_markers = []
            self.construction_name = ""
            
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Plasmid"
