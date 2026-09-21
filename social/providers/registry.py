"""Explicit provider factories owned by the social domain."""
from .youtube import YouTubeAdapter
from .twitch import TwitchAdapter
from .tiktok import TikTokAdapter
from .x import XAdapter
from .instagram import InstagramAdapter

ADAPTERS = (YouTubeAdapter, TwitchAdapter, TikTokAdapter, XAdapter, InstagramAdapter)
if len({item.provider for item in ADAPTERS}) != len(ADAPTERS):
    raise ValueError('Duplicate social provider')

def build_adapters(settings, client):
    return {item.provider: item(settings, client) for item in ADAPTERS}
