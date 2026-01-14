# core/models/events.py
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from core.models.samples.sample import Sample # Caminho absoluto

class Event(models.Model):
    EVENT_TYPES = [
        ("entry", "Entrada"),
        ("freeze", "Congelamento"),
        ("thaw", "Descongelamento"),
        ("transfer", "Transferência (Movimentação)"),
        ("qc_check", "Controle de Qualidade"),
    ]

    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Rastreio de Localização: Onde a amostra estava neste momento?
    location_snapshot = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="Snapshot da localização física (Freezer/Rack/Box)"
    )
    
    notes = models.TextField(blank=True, null=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.sample.sample_id} - {self.get_event_type_display()}"