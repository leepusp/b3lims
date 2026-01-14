from benchling_sdk.benchling import Benchling
from benchling_sdk.auth.api_key_auth import ApiKeyAuth
from benchling_sdk.models import CustomEntityCreate
from django.conf import settings

class BenchlingService:
    def __init__(self):
        # Configurações do settings.py
        self.api_key = getattr(settings, "BENCHLING_API_KEY", "SUA_KEY_AQUI")
        self.url = getattr(settings, "BENCHLING_URL", "https://SUA-INSTANCIA.benchling.com")
        
        # Na v1.23.1, a forma correta e mais segura de inicializar é:
        self.client = Benchling(
            url=self.url,
            auth_method=ApiKeyAuth(self.api_key) # Note o nome 'auth_method'
        )

    def sync_sample_to_benchling(self, sample):
        """
        Sincroniza uma amostra específica com o Registry do Benchling.
        """
        # Mapeamento de Keywords do seu Biobank para Fields do Benchling
        fields = {}
        for kv in sample.keyword_values.all():
            # No Benchling, campos customizados esperam um dicionário com {'value': ...}
            fields[kv.keyword.name] = {"value": kv.value}

        try:
            # Configure os IDs reais do seu painel Benchling aqui
            new_entity = CustomEntityCreate(
                name=sample.sample_id,
                schema_id="id_do_seu_schema",    # Geralmente começa com 'ts_'
                registry_id="id_do_seu_registry", # Geralmente começa com 'src_'
                fields=fields
            )
            
            # Execução via serviço de entidades customizadas
            created = self.client.custom_entities.create(new_entity)
            return created.id
        except Exception as e:
            # Debug no console do servidor LEEP3
            print(f"Erro na API Benchling: {str(e)}")
            return None