"""minigames metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("minigames", "engagement", "feature.minigames", "feature.minigames.description", "gamepad", "/docs/features/minigames", (), copy_ja=("ミニゲーム", "コミュニティ向けの軽量ゲームを提供します。"), order=17,
    bindings=(Binding('minigames_bot', 'bot', 'cogs.engagement.minigames:setup', 10), ))
