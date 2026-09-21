"""Persistence model catalog. No dependency on Bot/API feature registration."""
from .community.registry import MODELS as COMMUNITY
from .engagement.registry import MODELS as ENGAGEMENT
from .moderation.registry import MODELS as MODERATION
from .defaults import SettingsModel

MODELS = {}
for category in (COMMUNITY, ENGAGEMENT, MODERATION):
    if MODELS.keys() & category.keys():
        raise ValueError('Duplicate settings model')
    MODELS.update(category)
DEFAULT = SettingsModel()

def normalize(module_id, values):
    return MODELS.get(module_id, DEFAULT).read(values)
