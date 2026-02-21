"""Adventure and daycare path/asset constants. Extracted from pokebot.py."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

ASSETS_DIR = _ROOT / "assets"
ASSETS_CITIES = ASSETS_DIR / "cities"
ASSETS_ROUTES = ASSETS_DIR / "routes"
ASSETS_DAYCARE = ASSETS_DIR / "ui" / "daycare.png"
ASSETS_EGG_STAGES_DIR = ASSETS_DIR / "ui" / "egg-stages"
ASSETS_EGG_STAGE_1_INTACT = ASSETS_EGG_STAGES_DIR / "egg-stage-1-intact.png"
ASSETS_EGG_STAGE_2_SLIGHT = ASSETS_EGG_STAGES_DIR / "egg-stage-2-slightly-cracked.png"
ASSETS_EGG_STAGE_3_CRACKED = ASSETS_EGG_STAGES_DIR / "egg-stage-3-cracked.png"
ASSETS_EGG_STAGE_4_MORE = ASSETS_EGG_STAGES_DIR / "egg-stage-4-more-cracked.png"
ASSETS_EGG_STAGE_5_HEAVY = ASSETS_EGG_STAGES_DIR / "egg-stage-5-heavily-cracked.png"
ASSETS_EGG_STAGE_6_EXTREME = ASSETS_EGG_STAGES_DIR / "egg-stage-6-extremely-cracked.png"
ASSETS_DAYCARE_EGG = ASSETS_EGG_STAGE_1_INTACT

DAYCARE_CITY_ID = "viridian-city"
DAYCARE_AREA_ID = "pallet-daycare"
ROUTE_22_ENABLED = False
DAYCARE_EGG_CAP = 3
DAYCARE_INCUBATE_MAX = 6
DAYCARE_BREED_THRESHOLD = 22.0
DAYCARE_EGG_INTERVAL_SECONDS = 3600.0
DAYCARE_OVAL_CHARM_INTERVAL_MULT = 0.75
DAYCARE_OVAL_CHARM_BONUS_EGG_CHANCE = 0.15
DAYCARE_HATCH_MIN = 45.0
DAYCARE_HATCH_MAX = 80.0
DAYCARE_HATCH_BOOST_ABILITIES = {"flame-body", "magma-armor"}
DAYCARE_HATCH_COMMAND_BONUS_CAP = 0.18
DAYCARE_MIRROR_HERB_ITEMS = {"mirror-herb", "mirror_herb"}
DAYCARE_HATCH_BOOST_CACHE_TTL_SECONDS = 15.0
DAYCARE_OVAL_CHARM_CACHE_TTL_SECONDS = 30.0
DAYCARE_INCENSE_BABIES: dict[str, tuple[str, str]] = {
    "snorlax": ("munchlax", "full-incense"),
    "mr-mime": ("mime-jr", "odd-incense"),
    "chansey": ("happiny", "luck-incense"),
    "blissey": ("happiny", "luck-incense"),
    "roselia": ("budew", "rose-incense"),
    "roserade": ("budew", "rose-incense"),
    "sudowoodo": ("bonsly", "rock-incense"),
    "wobbuffet": ("wynaut", "lax-incense"),
    "marill": ("azurill", "sea-incense"),
    "azumarill": ("azurill", "sea-incense"),
    "chimecho": ("chingling", "pure-incense"),
    "mantine": ("mantyke", "wave-incense"),
}

DAYCARE_MAX_ANIM_FRAMES = 16
DAYCARE_GIF_MAX_SIZE: tuple[int, int] = (56, 56)
DAYCARE_BOX_MAX_SIZE: tuple[int, int] = (52, 52)
DAYCARE_STATIC_MAX_SIZE: tuple[int, int] = (52, 52)

BOX_SPRITES_DIR = _ROOT / "pvp" / "_common" / "box_sprites"
LEGACY_SPRITES_DIR = _ROOT / "pvp" / "_common" / "sprites"
POKESPRITE_MASTER_ZIP = _ROOT / "pokesprite-master.zip"
DAYCARE_ZIP_CACHE_DIR = BOX_SPRITES_DIR / "_pokesprite_zip_cache"
ASSETS_BOX_BACKGROUNDS_DIR = ASSETS_DIR / "ui" / "box-backgrounds"
BOX_SPRITES_BACKGROUNDS_DIR = BOX_SPRITES_DIR / "backgrounds"
ITEM_ICON_DIR = ASSETS_DIR / "item_icons"
BOX_BACKGROUND_FILENAMES: tuple[str, ...] = (
    "box-bg-meadow.png",
    "box-bg-space.png",
    "box-bg-pond.png",
)

# Mutable caches (populated at runtime)
_DAYCARE_HATCH_BOOST_CACHE: dict[str, tuple[bool, float]] = {}
_DAYCARE_OVAL_CHARM_CACHE: dict[str, tuple[bool, float]] = {}
