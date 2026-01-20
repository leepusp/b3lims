# core/models/__init__.py

# Sub-pacotes existentes
from .biobanks.biobank import Biobank
from .biobanks.biobank_user_role import BiobankUserRole
from .collections.collection import Collection
from .collections.collection_user_role import CollectionUserRole
from .samples.sample import Sample
from .samples.sample_files import SampleFile

# Novos Sub-pacotes (Organizados)
from .tags.model import Tag
from .keywords.model import Keyword, KeywordValue
from .events.model import Event
from .research_groups.model import ResearchGroup