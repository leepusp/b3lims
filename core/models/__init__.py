# core/models/__init__.py

# Sub-pacotes
from .biobanks.biobank import Biobank
from .biobanks.biobank_user_role import BiobankUserRole
from .collections.collection import Collection
from .collections.collection_user_role import CollectionUserRole
from .samples.sample import Sample
from .samples.sample_files import SampleFile  # CORRIGIDO

# Arquivos na raiz de models
from .tags import Tag
from .keywords import Keyword, KeywordValue
from .events import Event
from .research_group import ResearchGroup