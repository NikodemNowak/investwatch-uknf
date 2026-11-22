"""Name -> collector lookup used by the scheduler.

Only compliant collectors exist (ADR 0008): the crawler for websites, official APIs for
platforms, and file replays. `tests/test_compliance.py` keeps it that way.
"""

from __future__ import annotations

from collections.abc import Callable

from investwatch.collectors.base import Collector
from investwatch.collectors.manual import ManualCollector
from investwatch.collectors.official.meta_ads_api import MetaAdLibraryCollector
from investwatch.collectors.official.microsoft_ad_library import MicrosoftAdLibraryCollector
from investwatch.collectors.official.tiktok_ccl_api import TikTokCommercialContentCollector
from investwatch.collectors.official.youtube_api import YouTubeApiCollector
from investwatch.collectors.sample import SampleCollector
from investwatch.collectors.site import SiteCollector
from investwatch.collectors.web import WebCollector

COLLECTORS: dict[str, Callable[[], Collector]] = {
    "manual": ManualCollector,
    "web": WebCollector,
    "site": SiteCollector,
    "sample": SampleCollector,
    "youtube": YouTubeApiCollector,
    "meta_ad_library": MetaAdLibraryCollector,
    "tiktok": TikTokCommercialContentCollector,
    "microsoft_ad_library": MicrosoftAdLibraryCollector,
}


def get_collector(name: str) -> Collector:
    """Instantiate the collector registered under `name`."""
    try:
        factory = COLLECTORS[name]
    except KeyError as exc:
        raise ValueError(f"unknown collector: {name}") from exc
    return factory()
