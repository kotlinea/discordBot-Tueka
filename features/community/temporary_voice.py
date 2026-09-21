"""temporary_voice metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("temporary_voice", "community", "feature.temporary_voice", "feature.temporary_voice.description", "microphone", "/docs/features/temporary-voice", ("temp_voice_trigger_id", "temp_voice_category_id", "temp_voice_name"), ("temp_voice_trigger_id",), ("manage_channels", "move_members"), copy_ja=("一時的な音声チャンネル", "トリガー参加時に専用VCを作成し、空になると削除します。"), order=13,
    bindings=(Binding('temporary_voice_bot', 'bot', 'cogs.community.temporary_voice:setup', 8), ))
