# core/models/samples/relationship.py
from django.db import models
from django.contrib.auth.models import User
from core.models.samples.sample import Sample

class SampleRelationship(models.Model):
    """
    Modelo de Grafo (Rede) para rastrear a filogenia e derivação entre amostras.
    Permite que uma amostra tenha múltiplos 'pais' e 'filhos'.
    """
    RELATIONSHIP_TYPES = [
        # Linhagem e Inventário Físico
        ('aliquot', 'Alíquota (Cópia exata em outro tubo)'),
        ('passage', 'Passagem / Subcultivo / Repique'),
        ('mutated_from', 'Mutação / Modificação de'),
        
        # Interações e Engenharia
        ('assembled_from', 'Montada a partir de (Vetor + Inserto)'),
        ('extracted_from', 'Extraída de (DNA/RNA)'),
        ('infects', 'Infecta (Host-Range)'),
        ('other', 'Outro Relacionamento'),
    ]

    source_sample = models.ForeignKey(
        Sample, 
        on_delete=models.CASCADE, 
        related_name='outgoing_relationships',
        help_text="A amostra de origem (Pai)"
    )
    
    target_sample = models.ForeignKey(
        Sample, 
        on_delete=models.CASCADE, 
        related_name='incoming_relationships',
        help_text="A amostra de destino (Filho/Derivada)"
    )
    
    # ATUALIZADO: O default agora é 'aliquot'
    relationship_type = models.CharField(max_length=50, choices=RELATIONSHIP_TYPES, default='aliquot')
    notes = models.TextField(blank=True, null=True, help_text="Detalhes do protocolo ou método de derivação.")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        # Evita que o usuário crie a exata mesma relação duas vezes
        unique_together = ('source_sample', 'target_sample', 'relationship_type')
        verbose_name = "Relacionamento de Amostra"
        verbose_name_plural = "Relacionamentos de Amostras"

    def __str__(self):
        return f"{self.source_sample.sample_id} [{self.get_relationship_type_display()}] -> {self.target_sample.sample_id}"
