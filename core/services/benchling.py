from benchling_sdk.benchling import Benchling
from benchling_sdk.auth.api_key_auth import ApiKeyAuth
from benchling_sdk.models import CustomEntityCreate, CustomEntityUpdate
from django.conf import settings

class BenchlingConnector:
    def __init__(self):
        # Configurações extraídas do seu ambiente
        self.api_key = getattr(settings, "BENCHLING_API_KEY", None)
        self.url = getattr(settings, "BENCHLING_URL", None)
        
        if not self.api_key or not self.url:
            raise ValueError("Configurações do Benchling não encontradas no settings.py")
            
        self.client = Benchling(url=self.url, auth=ApiKeyAuth(self.api_key))

    def create_sample_entity(self, sample_obj, schema_id, registry_id):
        """
        Mapeia uma amostra do Biobank LIMS para uma CustomEntity do Benchling.
        """
        # Preparação dos campos baseada nas Keywords do seu banco
        # No Benchling SDK, campos são dicionários com a chave 'value'
        benchling_fields = {}
        for kv in sample_obj.keyword_values.all():
            benchling_fields[kv.keyword.name] = {"value": kv.value}

        # Conforme a estrutura da SDK: instanciamos o modelo de criação
        new_entity_data = CustomEntityCreate(
            name=sample_obj.sample_id,
            schema_id=schema_id,
            registry_id=registry_id,
            fields=benchling_fields
        )

        # Execução via serviço de custom_entities
        try:
            created_entity = self.client.custom_entities.create(new_entity_data)
            return created_entity
        except Exception as e:
            # Tratamento de erro específico para a LEEP3
            print(f"Falha na sincronização Benchling: {str(e)}")
            return None