from __future__ import annotations

import os
import time
from io import BytesIO
import platform
import shutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import tempfile
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

# Uses your layout: pvp/_common/sprites/<species>/
from .sprites import find_sprite, _norm_species

_render_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="render")

# --- Pillow imports with TYPE_CHECKING-friendly shims (no Pylance warnings) ---
try:
    from PIL import Image as _PILImage, ImageSequence as _PILImageSequence, ImageDraw as _PILImageDraw
except Exception:  # Pillow not available at runtime
    _PILImage = None               # type: ignore[assignment]
    _PILImageSequence = None       # type: ignore[assignment]
    _PILImageDraw = None           # type: ignore[assignment]

if TYPE_CHECKING:
    from PIL import Image as PILImage
    from PIL.Image import Image as PILImageType
    from PIL import ImageSequence as PILImageSequence
    from PIL import ImageDraw as PILImageDraw
else:
    PILImage = Any           # type: ignore[misc,assignment]
    PILImageType = Any       # type: ignore[misc,assignment]
    PILImageSequence = Any   # type: ignore[misc,assignment]
    PILImageDraw = Any       # type: ignore[misc,assignment]

try:
    from lib import db_cache as _lib_db_cache
except ImportError:
    _lib_db_cache = None

# ------------------------------------------------------------------------------

if os.getenv("RENDER_USE_TEMP", "0").lower() in ("1", "true", "yes"):
    MEDIA_ROOT = Path(tempfile.gettempdir()) / "myuu_battle_media"
else:
    MEDIA_ROOT = Path(os.getenv("RENDER_TMP_DIR") or "tmp_battle_media")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_close(img: Optional[PILImageType]) -> None:
    """
    Safely close an image resource, handling any errors gracefully.
    
    Args:
        img: PIL Image object to close, or None
    """
    if img is None:
        return
    try:
        if hasattr(img, 'close'):
            img.close()
    except (AttributeError, OSError, IOError) as e:
        # Silently handle close errors - image may already be closed or invalid
        # In production, you might want to log these: logger.debug(f"Error closing image: {e}")
        pass
    except Exception:
        # Catch any other unexpected errors during close
        pass


def _safe_close_list(images: List[Optional[PILImageType]]) -> None:
    """
    Safely close a list of image resources.
    
    Args:
        images: List of PIL Image objects to close
    """
    for img in images:
        _safe_close(img)


@contextmanager
def _managed_image(path: Optional[Path]):
    """
    Context manager for image resources that ensures proper cleanup.
    
    Usage:
        with _managed_image(path) as img:
            if img:
                # use img
                pass
    """
    img = None
    try:
        img = _open(path)
        yield img
    finally:
        _safe_close(img)


def _open(path: Optional[Path]) -> Optional[PILImageType]:
    """Open an image file and return it (file handle will be managed by caller or closed after frame extraction)."""
    if _PILImage is None or path is None:
        return None
    try:
        # Open the image - for animated GIFs, we need to keep it open to extract frames
        # The caller (_iter_frames) will extract frames and we can close it then
        img = _PILImage.open(path)  # type: ignore[attr-defined]
        # Load the image to ensure it's fully loaded
        img.load()
        return img
    except (IOError, OSError) as e:
        # File not found, permission denied, or corrupted image
        # In production: logger.debug(f"Failed to open image {path}: {e}")
        return None
    except Exception as e:
        # Unexpected error - could be invalid image format, etc.
        # In production: logger.warning(f"Unexpected error opening {path}: {e}")
        return None


def _iter_frames(img: PILImageType) -> List[PILImageType]:
    # Animated gifs -> all frames; png -> single frame
    # Check if image is animated - need to check both is_animated attribute and n_frames
    is_animated = getattr(img, "is_animated", False)
    n_frames = getattr(img, "n_frames", 1)
    
    if is_animated and n_frames > 1 and _PILImageSequence is not None:
        try:
            frames = []
            # Use ImageSequence.Iterator to get all frames from the animated GIF
            for frame in _PILImageSequence.Iterator(img):  # type: ignore[attr-defined]
                # Convert each frame to RGBA and create a copy (so we can close the original)
                frame_copy = frame.convert("RGBA").copy()
                frames.append(frame_copy)
            return frames
        except (IOError, OSError, AttributeError) as e:
            # Fallback to single frame on error (corrupted GIF, missing attribute, etc.)
            # In production: logger.debug(f"Failed to extract animated frames: {e}")
            return [img.convert("RGBA")]
        except Exception as e:
            # Unexpected error - fallback to single frame
            # In production: logger.warning(f"Unexpected error extracting frames: {e}")
            return [img.convert("RGBA")]
    else:
        return [img.convert("RGBA")]

@lru_cache(maxsize=128)
def _load_sprite_frames_cached(path_str: str) -> Tuple[PILImageType, ...]:
    """Load and cache raw RGBA frames for a sprite path."""
    if _PILImage is None:
        return tuple()
    try:
        p = Path(path_str)
        if not p.exists():
            return tuple()
        img = _PILImage.open(p)  # type: ignore[attr-defined]
        img.load()
        frames = _iter_frames(img)
        # Do not close frames; these are cached. Close source image if possible.
        _safe_close(img)
        out = [f for f in frames if f is not None]
        return tuple(out)
    except Exception:
        return tuple()

def _get_sprite_frames(path: Optional[Path]) -> List[PILImageType]:
    """Return cached raw frames for a sprite path (or [None] if missing)."""
    if _PILImage is None or path is None:
        return [None]
    frames = _load_sprite_frames_cached(str(path))
    if not frames:
        return [None]
    return list(frames)


def _scale_to_height(img: PILImageType, max_h: int) -> PILImageType:
    """Scale image to exact target height, scaling both up and down"""
    if img.height == max_h:
        return img
    r = max_h / img.height
    return img.resize((int(img.width * r), int(img.height * r)), resample=3)


def _make_hp_gradient_image(
    fill_width: int, height: int,
    paler_color: Tuple[int, int, int], reference_color: Tuple[int, int, int],
) -> Optional[Any]:
    """Create RGBA gradient image (radial, edges lighter). Uses numpy if available."""
    if _PILImage is None or fill_width <= 0 or height <= 0:
        return None
    center_x = fill_width / 2.0
    center_y = height / 2.0
    max_dist = ((fill_width / 2.0) ** 2 + (height / 2.0) ** 2) ** 0.5

    try:
        import numpy as np
        py_arr = np.arange(height, dtype=np.float32)
        px_arr = np.arange(fill_width, dtype=np.float32)
        yy, xx = np.meshgrid(py_arr, px_arr, indexing="ij")
        dx = xx - center_x
        dy = yy - center_y
        dist = np.sqrt(dx * dx + dy * dy)
        norm = np.where(max_dist > 0, np.minimum(1.0, dist / max_dist), 0.0)
        t = np.where(norm > 0.7, 1.0 - (norm - 0.7) / 0.3, 1.0)
        t = np.clip(t, 0.0, 1.0)
        r = (paler_color[0] * (1 - t) + reference_color[0] * t).astype(np.uint8)
        g = (paler_color[1] * (1 - t) + reference_color[1] * t).astype(np.uint8)
        b = (paler_color[2] * (1 - t) + reference_color[2] * t).astype(np.uint8)
        a = np.full_like(r, 255)
        rgba = np.stack([r, g, b, a], axis=-1)
        return _PILImage.fromarray(rgba, mode="RGBA")
    except ImportError:
        # NumPy not available - fall through to pixel-by-pixel method
        pass
    except (ValueError, MemoryError) as e:
        # Invalid dimensions or out of memory - fall through to pixel-by-pixel method
        # In production: logger.debug(f"NumPy gradient failed: {e}")
        pass
    except Exception as e:
        # Unexpected error - fall through to pixel-by-pixel method
        # In production: logger.warning(f"Unexpected error in NumPy gradient: {e}")
        pass

    temp_img = _PILImage.new("RGBA", (fill_width, height), (0, 0, 0, 0))
    pixels = temp_img.load()
    for py in range(height):
        for px in range(fill_width):
            dx = px - center_x
            dy = py - center_y
            dist = (dx * dx + dy * dy) ** 0.5
            norm = min(1.0, dist / max_dist) if max_dist > 0 else 0.0
            t = (1.0 - (norm - 0.7) / 0.3) if norm > 0.7 else 1.0
            t = max(0.0, min(1.0, t))
            r = int(paler_color[0] * (1 - t) + reference_color[0] * t)
            g = int(paler_color[1] * (1 - t) + reference_color[1] * t)
            b = int(paler_color[2] * (1 - t) + reference_color[2] * t)
            pixels[px, py] = (r, g, b, 255)
    return temp_img


def _bob_positions(y: int, amplitude: int, n: int) -> List[int]:
    # simple easing up/down loop of length 8
    table = (0, 1, 2, 3, 2, 1, 0, -1)
    return [y + (table[i % 8] * amplitude // 3) for i in range(n)]


def _compose_frame(
    canvas: PILImageType,
    left: Optional[PILImageType],
    right: Optional[PILImageType],
    y_left: int,
    y_right: int,
) -> PILImageType:
    frame = canvas.copy()
    W, _ = frame.size
    if left is not None:
        x1 = int(W * 0.12)
        frame.alpha_composite(left, (x1, y_left))
    if right is not None:
        x2 = W - (right.width + int(W * 0.12))
        frame.alpha_composite(right, (x2, y_right))
    return frame


@lru_cache(maxsize=24)
def _background_master(
    size: Tuple[int, int],
    pov: str = "p1",
    nullscape_active: bool = False,
    bg_key: Optional[str] = None,
) -> PILImageType:
    """Load and cache background 'master'. Callers must use _background() which returns a copy.
    Never close the returned image — it is cached and shared."""
    if _PILImage is None:
        raise RuntimeError("Pillow is required to render battle GIFs.")

    if nullscape_active:
        nullscape_bg = Path("pvp/_common/bg/Nullscape.png")
        if nullscape_bg.exists():
            try:
                with _PILImage.open(nullscape_bg) as bg_file:  # type: ignore[attr-defined]
                    bg_img = bg_file.copy()
                    if bg_img.size != size:
                        bg_img = bg_img.resize(size, resample=_PILImage.Resampling.LANCZOS)
                    if bg_img.mode != "RGBA":
                        bg_img = bg_img.convert("RGBA")
                    return bg_img
            except (IOError, OSError) as e:
                # File not found or corrupted - try next background
                # In production: logger.debug(f"Failed to load nullscape background: {e}")
                pass
            except Exception as e:
                # Unexpected error - try next background
                # In production: logger.warning(f"Unexpected error loading nullscape background: {e}")
                pass

    # Optional override: choose background by key (ex: "pvp", "adventure") then fallback to any assets/bg image.
    override_dir = Path("assets/bg")
    if override_dir.exists():
        try:
            candidates: List[Path] = []
            if bg_key:
                key = str(bg_key).strip().lower()
                for ext in (".png", ".jpg", ".jpeg", ".gif"):
                    candidates.append(override_dir / f"{key}{ext}")
                key_dir = override_dir / key
                if key_dir.exists() and key_dir.is_dir():
                    for ext in (".png", ".jpg", ".jpeg", ".gif"):
                        candidates.extend(sorted(key_dir.glob(f"*{ext}")))
            if not candidates:
                for ext in (".png", ".jpg", ".jpeg", ".gif"):
                    candidates.extend(sorted(override_dir.glob(f"*{ext}")))
            for bg_path in candidates:
                if bg_path.exists():
                    try:
                        with _PILImage.open(bg_path) as bg_file:  # type: ignore[attr-defined]
                            bg_img = bg_file.copy()
                            if bg_img.size != size:
                                bg_img = bg_img.resize(size, resample=_PILImage.Resampling.LANCZOS)
                            if bg_img.mode != "RGBA":
                                bg_img = bg_img.convert("RGBA")
                            return bg_img
                    except (IOError, OSError):
                        continue
                    except Exception:
                        continue
        except Exception:
            pass

    bg_paths = [
        Path(f"pvp/_common/bg/battle_{pov}.png"),
        Path(f"pvp/_common/bg/battle_{pov}.jpg"),
        Path("pvp/_common/bg/battle.png"),
        Path("pvp/_common/bg/battle.jpg"),
    ]
    for bg_path in bg_paths:
        if bg_path.exists():
            try:
                with _PILImage.open(bg_path) as bg_file:  # type: ignore[attr-defined]
                    bg_img = bg_file.copy()
                    if bg_img.size != size:
                        bg_img = bg_img.resize(size, resample=_PILImage.Resampling.LANCZOS)
                    if bg_img.mode != "RGBA":
                        bg_img = bg_img.convert("RGBA")
                    return bg_img
            except (IOError, OSError):
                # File not found or corrupted - try next background
                continue
            except Exception:
                # Unexpected error - try next background
                continue

    return _PILImage.new("RGBA", size, (23, 40, 54, 255))  # type: ignore[attr-defined]


def _background(
    size: Tuple[int, int],
    pov: str = "p1",
    nullscape_active: bool = False,
    bg_key: Optional[str] = None,
) -> PILImageType:
    """Return a fresh copy of the background. Callers may close it; the cached master is never closed."""
    return _background_master(size, pov, nullscape_active, bg_key).copy()


def _overlay_text(img: PILImageType, text: str) -> PILImageType:
    if _PILImageDraw is None:
        return img
    draw = _PILImageDraw.Draw(img)
    W, H = img.size
    draw.text((10, H - 22), text, fill=(220, 230, 235, 200))
    return img

@lru_cache(maxsize=1)
def _get_pokemon_font_path() -> Optional[str]:
    """Cached Pokemon GB font path. Used by _draw_ui_elements."""
    fonts_folder = Path("pvp/_common/fonts")
    if fonts_folder.exists():
        for font_file in fonts_folder.glob("*"):
            if font_file.is_file() and font_file.suffix.lower() in (".ttf", ".otf"):
                if "pokemon" in font_file.name.lower() and "gb" in font_file.name.lower():
                    return str(font_file)
    for path in (
        "pvp/_common/fonts/Pokemon GB.ttf",
        "pvp/_common/fonts/PokemonGb-RAeo.ttf",
        "pvp/_common/fonts/pokemon-gb.ttf",
        "pvp/_common/fonts/pokemongb.ttf",
        "fonts/Pokemon GB.ttf",
        "Pokemon GB.ttf",
    ):
        if Path(path).exists():
            return path
    sys = platform.system()
    if sys == "Windows":
        candidates = [
            Path(os.path.expanduser("~")) / "AppData/Local/Microsoft/Windows/Fonts/Pokemon GB.ttf",
            Path("C:/Windows/Fonts/Pokemon GB.ttf"),
        ]
    elif sys == "Darwin":
        candidates = [
            Path("/Library/Fonts/Pokemon GB.ttf"),
            Path(os.path.expanduser("~/Library/Fonts/Pokemon GB.ttf")),
        ]
    else:
        candidates = [
            Path("/usr/share/fonts/truetype/pokemon-gb.ttf"),
            Path(os.path.expanduser("~/.fonts/Pokemon GB.ttf")),
        ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


@lru_cache(maxsize=128)
def _load_font_cached(font_path_key: str, size: int) -> Any:
    """Load font by path (or '' for fallbacks) and size. Cached. Never returns None."""
    try:
        from PIL import ImageFont
        if font_path_key:
            try:
                return ImageFont.truetype(font_path_key, size)
            except (IOError, OSError):
                # Font file not found - try fallbacks
                pass
            except Exception as e:
                # Invalid font file or other error - try fallbacks
                # In production: logger.debug(f"Failed to load font {font_path_key}: {e}")
                pass
        for name in ("arial.ttf", "calibri.ttf", "verdana.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except (IOError, OSError):
                # Font not found - try next
                continue
            except Exception:
                # Invalid font - try next
                continue
        return ImageFont.load_default()
    except ImportError:
        # PIL.ImageFont not available - return None
        return None
    except Exception:
        try:
            from PIL import ImageFont
            return ImageFont.load_default()
        except Exception:
            return None


@lru_cache(maxsize=8)
def _load_pokeball_sprite(ball_type: str) -> Optional[PILImageType]:
    """Load Pokéball sprite by type: orange, yellow, grey, outline. Cached."""
    if _PILImage is None:
        return None
    sprite_path = Path(f"pvp/_common/sprites/pokeballs/pokeball_{ball_type}.png")
    if sprite_path.exists():
        try:
            with _PILImage.open(sprite_path) as img_file:  # type: ignore[attr-defined]
                return img_file.convert("RGBA").copy()
        except (IOError, OSError) as e:
            # File not found or corrupted
            # In production: logger.debug(f"Failed to load pokeball sprite {ball_type}: {e}")
            pass
        except Exception as e:
            # Unexpected error
            # In production: logger.warning(f"Unexpected error loading pokeball sprite {ball_type}: {e}")
            pass
    return None

def _draw_text_with_stroke(draw: PILImageDraw, position: Tuple[int, int], text: str, 
                          fill_color: Tuple[int, int, int], font=None, 
                          stroke_color: Tuple[int, int, int] = (0, 0, 0), stroke_width: int = 2):
    """Draw text with stroke outline effect"""
    x, y = position
    # Ensure minimum stroke width for visibility
    stroke_width = max(stroke_width, 1)
    
    # Try using PIL's built-in stroke support (Pillow 8.0+)
    try:
        draw.text((x, y), text, fill=fill_color, font=font, stroke_width=stroke_width, stroke_fill=stroke_color)
    except TypeError:
        # Fallback for older Pillow versions: draw stroke manually
        # Draw stroke (multiple passes for thicker stroke)
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, fill=stroke_color, font=font)
        # Draw main text
        draw.text((x, y), text, fill=fill_color, font=font)

def _draw_hp_bar(draw: PILImageDraw, img: PILImageType, x: int, y: int, width: int, hp_pct: float, is_opponent: bool = False, font=None, height: Optional[int] = None, scale_y: float = 1.0):
    """Draw HP bar with rounded corners and gradient fill (no border)"""
    if height is None:
        base_height = 15  # Same height for both opponent and player (increased from 13)
        height = int(base_height * scale_y)  # Scale height to match canvas
    else:
        height = int(height * scale_y)  # Scale provided height
    
    # Calculate fill width based on HP percentage
    fill_width = int(width * max(0, min(1, hp_pct)))
    
    # Color based on HP percentage
    if hp_pct > 0.5:
        # Green: #7ac874 (RGB: 122, 200, 116) - above 50%
        reference_color = (122, 200, 116)
    elif hp_pct > 0.2:
        # Yellow: #f8e038 (RGB: 248, 224, 56) - between 20-50%
        reference_color = (248, 224, 56)
    else:
        # Red: #f85838 (RGB: 248, 88, 56) - below 20%
        reference_color = (248, 88, 56)
    
    # Create a lighter version (not white) - blend with white (20% white, 80% reference)
    # This makes the gradient subtle - edges are slightly lighter, center is full color
    paler_color = (
        int(255 * 0.2 + reference_color[0] * 0.8),
        int(255 * 0.2 + reference_color[1] * 0.8),
        int(255 * 0.2 + reference_color[2] * 0.8)
    )
    
    # Border radius for rounded corners (adjust based on height)
    radius = min(3, height // 4)  # Small radius for rounded corners
    stroke_width = 1
    
    # Draw HP fill with gradient (only if there's HP)
    if fill_width > 0 and _PILImage is not None:
        temp_img = _make_hp_gradient_image(fill_width, height, paler_color, reference_color)
        if temp_img is not None:
            mask = _PILImage.new("L", (fill_width, height), 0)
            mask_draw = _PILImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, fill_width, height], radius=radius, fill=255)
            temp_img.putalpha(mask)
            img.alpha_composite(temp_img, (x, y))
            border_box = [x, y, x + fill_width, y + height]
            draw.rounded_rectangle(border_box, radius=radius, outline=(255, 255, 255), width=1)


def _draw_exp_bar(draw: PILImageDraw, img: PILImageType, x: int, y: int, width: int, exp_pct: float, scale_y: float = 1.0) -> None:
    """Draw blue EXP bar (user only, under HP bar). exp_pct 0.0–1.0.
    Filled portion = blue gradient; remainder = white.
    To resize: change base_height below (bar height); width is passed from caller (see EXP bar call ~line 1348)."""
    if _PILImage is None:
        return
    base_height = 20  # EXP bar height (PSD-space); final height = base_height * scale_y
    height = int(base_height * scale_y)
    fill_width = int(width * max(0, min(1, exp_pct)))
    radius = min(2, height // 4)
    # Draw full bar background (white) for the remainder
    draw.rounded_rectangle([x, y, x + width, y + height], radius=radius, fill=(255, 255, 255), outline=(255, 255, 255), width=1)
    # Blue EXP bar fill (left portion)
    reference_color = (70, 130, 220)  # Steel blue
    paler_color = (
        min(255, int(255 * 0.15 + reference_color[0] * 0.85)),
        min(255, int(255 * 0.2 + reference_color[1] * 0.8)),
        min(255, int(255 * 0.25 + reference_color[2] * 0.75)),
    )
    if fill_width > 0:
        temp_img = _make_hp_gradient_image(fill_width, height, paler_color, reference_color)
        if temp_img is not None:
            mask = _PILImage.new("L", (fill_width, height), 0)
            mask_draw = _PILImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, fill_width, height], radius=radius, fill=255)
            temp_img.putalpha(mask)
            img.alpha_composite(temp_img, (x, y))


@lru_cache(maxsize=64)
def _load_icon(icon_name: str) -> Optional["PILImage.Image"]:
    """Load an icon from pvp/_common/Other or status. Cached."""
    if _PILImage is None:
        return None
    try:
        for folder in ("pvp/_common/Other", "pvp/_common/status"):
            p = Path(folder) / icon_name
            if p.exists():
                try:
                    with _PILImage.open(p) as img_file:  # type: ignore[attr-defined]
                        return img_file.convert("RGBA").copy()
                except (IOError, OSError) as e:
                    # File not found or corrupted - try next folder
                    # In production: logger.debug(f"Failed to load icon {icon_name} from {folder}: {e}")
                    continue
                except Exception as e:
                    # Unexpected error - try next folder
                    # In production: logger.warning(f"Unexpected error loading icon {icon_name} from {folder}: {e}")
                    continue
    except Exception as e:
        # Unexpected error iterating folders
        # In production: logger.warning(f"Unexpected error in _load_icon: {e}")
        pass
    return None


def _format_species_name(species: str) -> str:
    """Format species name for display, handling special cases like Ho-Oh, Mr. Mime, etc."""
    # Species with hyphens in their actual names (not forms)
    HYPHENATED_SPECIES = {
        'ho-oh', 'porygon-z', 'jangmo-o', 'hakamo-o', 'kommo-o',
        'type-null', 'tapu-koko', 'tapu-lele', 'tapu-bulu', 'tapu-fini',
        'nidoran-f', 'nidoran-m', 'mr-mime', 'mime-jr', 'mr-rime',
        'chi-yu', 'chien-pao', 'wo-chien', 'ting-lu'
    }
    
    # Extract base species name (remove form suffix like "-Pirouette" -> "Meloetta")
    # But preserve hyphenated species names like Ho-Oh
    if species.lower() in HYPHENATED_SPECIES:
        # Special capitalization for hyphenated names
        if species.lower() == 'ho-oh':
            return 'Ho-Oh'
        elif species.lower() == 'porygon-z':
            return 'Porygon-Z'
        elif species.lower().startswith('tapu-'):
            # Tapu Koko, Tapu Lele, etc.
            parts = species.split('-')
            return f"{parts[0].title()} {parts[1].title()}"
        elif species.lower() in ['mr-mime', 'mr-rime']:
            # Mr. Mime, Mr. Rime
            parts = species.split('-')
            return f"Mr. {parts[1].title()}"
        elif species.lower() == 'mime-jr':
            return 'Mime Jr.'
        elif species.lower() in ['jangmo-o', 'hakamo-o', 'kommo-o']:
            # Jangmo-o, Hakamo-o, Kommo-o
            parts = species.split('-')
            return f"{parts[0].title()}-o"
        elif species.lower() == 'type-null':
            return 'Type: Null'
        elif species.lower() in ['nidoran-f', 'nidoran-m']:
            # Nidoran♀, Nidoran♂
            gender = '♀' if species.lower().endswith('f') else '♂'
            return f'Nidoran{gender}'
        else:
            # Generic: Title case with hyphen
            return species.replace("-", " ").title()
    else:
        base_species = species.split("-")[0] if "-" in species else species
        return base_species.replace("-", " ").title()


def _get_status_icon_name(status: Optional[str]) -> Optional[str]:
    """Get the icon filename for a status condition."""
    if not status:
        return None
    status_lower = status.lower()
    if status_lower == "brn":
        return "Burned.png"
    elif status_lower == "frz":
        return "Frozen.png"
    elif status_lower == "par":
        return "Paralysis.png"
    elif status_lower == "psn":
        return "Poisoned.png"
    elif status_lower in ["tox", "badly poisoned"]:
        return "PoisonedBad.png"
    elif status_lower in ["slp", "sleep"]:
        return "Asleep.png"
    return None


def _draw_transformation_and_status_icons(
    img: PILImageType,
    icon_x_offset: int,
    icon_y: int,
    icon_size: int,
    icon_spacing: int,
    name_pos_y: int,
    text_height: int,
    scale_y: float,
    mega_evolved: bool,
    dynamaxed: bool,
    primal_reversion: Optional[str],
    status: Optional[str],
) -> int:
    """
    Draw transformation icons (Mega/Dynamax/Primal) and status icons.
    Returns the new x offset after drawing all icons.
    """
    # Transformation icons (Mega, Dynamax, Primal) - drawn FIRST (leftmost)
    if mega_evolved:
        mega_icon = _load_icon("Mega_Evolution_icon.png")
        if mega_icon:
            mega_icon = mega_icon.resize((icon_size, icon_size), resample=3)
            # Move mega icon up by 12 pixels
            mega_icon_y = icon_y - int(12 * scale_y)
            img.alpha_composite(mega_icon, (icon_x_offset, mega_icon_y))
            icon_x_offset += icon_size + icon_spacing
    elif dynamaxed:
        dynamax_icon = _load_icon("Dynamax_icon.png")
        if dynamax_icon:
            dynamax_icon = dynamax_icon.resize((icon_size, icon_size), resample=3)
            # Move dynamax icon up by 12 pixels
            dynamax_icon_y = icon_y - int(12 * scale_y)
            img.alpha_composite(dynamax_icon, (icon_x_offset, dynamax_icon_y))
            icon_x_offset += icon_size + icon_spacing
    elif primal_reversion:
        if primal_reversion.lower() == "groudon":
            primal_icon = _load_icon("Primal_Reversion_icon_Groudon.png")
        elif primal_reversion.lower() == "kyogre":
            primal_icon = _load_icon("Primal_Reversion_icon_Kyogre.png")
        else:
            primal_icon = None
        if primal_icon:
            primal_icon = primal_icon.resize((icon_size, icon_size), resample=3)
            # Move primal icon up by 12 pixels
            primal_icon_y = icon_y - int(12 * scale_y)
            img.alpha_composite(primal_icon, (icon_x_offset, primal_icon_y))
            icon_x_offset += icon_size + icon_spacing
    
    # Status icons - drawn AFTER transformation icons (rightmost)
    status_icon_name = _get_status_icon_name(status)
    if status_icon_name:
        status_icon = _load_icon(status_icon_name)
        if status_icon:
            status_icon = status_icon.resize((icon_size, icon_size), resample=3)
            # Status icons should be at the same height as the name (centered with text)
            status_icon_y = name_pos_y + (text_height - icon_size) // 2
            img.alpha_composite(status_icon, (icon_x_offset, status_icon_y))
            icon_x_offset += icon_size + icon_spacing
    
    return icon_x_offset


def _draw_team_pokeballs(
    img: PILImageType,
    ball_start: Tuple[int, int],
    ball_spacing: int,
    scale_y: float,
    team_total: int,
    team_alive: int,
    team_statuses: Optional[List[Optional[str]]],
    team_hp: Optional[List[Tuple[int, int]]],
    has_status: bool,
) -> None:
    """
    Draw team Pokéballs showing status (orange=healthy, yellow=status, grey=fainted, outline=empty).
    """
    for i in range(6):  # Always 6 slots
        ball_x = ball_start[0] + (i * ball_spacing)
        ball_y = ball_start[1]
        
        if i < team_total:
            # Check if this Pokémon is fainted by checking HP directly
            is_fainted = False
            if team_hp and i < len(team_hp):
                # Use team HP list if provided (current_hp, max_hp)
                current_hp, max_hp = team_hp[i]
                is_fainted = (current_hp <= 0 or max_hp <= 0)
            else:
                # Fallback: use team_alive count (less accurate)
                is_fainted = (i >= team_alive)
            
            if not is_fainted:
                # Check if this Pokémon has a status condition
                has_status_cond = False
                if team_statuses and i < len(team_statuses):
                    # Use team status list if provided
                    has_status_cond = bool(team_statuses[i])
                elif has_status and i == team_alive - 1:
                    # Fallback: only check active Pokémon if team statuses not provided
                    has_status_cond = True
                
                if has_status_cond:
                    # Status condition: yellow
                    ball_img = _load_pokeball_sprite("status")
                else:
                    # Healthy: orange
                    ball_img = _load_pokeball_sprite("orange")
            else:
                # Fainted: grey
                ball_img = _load_pokeball_sprite("grey")
        else:
            # Empty slot: outline
            ball_img = _load_pokeball_sprite("outline")
        
        if ball_img:
            # Use a reasonable size for the smaller canvas (proportional but with minimum visibility)
            # Scale from original 80px at 1024px height to maintain relative size
            ball_size_px = max(int(80 * scale_y), 40)  # Minimum 40px for visibility
            ball_size = (ball_size_px, ball_size_px)  # Keep square aspect
            ball_img = ball_img.resize(ball_size, resample=3)  # LANCZOS for sharp Pokéballs
            img.paste(ball_img, (ball_x, ball_y), ball_img)


def _draw_ui_elements(draw: PILImageDraw, img: PILImageType,
                     my_species: str, my_level: int, my_hp_current: int, my_hp_max: int,
                     my_team_alive: int, my_team_total: int, my_has_status: bool,
                     opp_species: str, opp_level: int, opp_hp_current: int, opp_hp_max: int,
                     opp_team_alive: int, opp_team_total: int, opp_has_status: bool,
                     my_shiny: bool = False, opp_shiny: bool = False, hide_hp_text: bool = False,
                     my_mega_evolved: bool = False, my_dynamaxed: bool = False, my_primal_reversion: Optional[str] = None,
                     opp_mega_evolved: bool = False, opp_dynamaxed: bool = False, opp_primal_reversion: Optional[str] = None,
                     my_status: Optional[str] = None, opp_status: Optional[str] = None,
                     my_team_statuses: Optional[List[Optional[str]]] = None, opp_team_statuses: Optional[List[Optional[str]]] = None,
                     my_team_hp: Optional[List[Tuple[int, int]]] = None, opp_team_hp: Optional[List[Tuple[int, int]]] = None,
                     opp_gender: Optional[str] = None):
    """Draw UI elements using exact positions from PSD design"""
    
    # Canvas is EXACT PSD size (1536x1024), so positions are 1:1 pixel mapping
    PSD_W, PSD_H = 1536, 1024
    W, H = img.size
    scale_x = W / PSD_W  # Will be 1.0 when canvas matches PSD
    scale_y = H / PSD_H  # Will be 1.0 when canvas matches PSD
    
    # Scale positions from PSD (when canvas = PSD, this is direct pixel mapping)
    def scale_pos(psd_x: int, psd_y: int) -> Tuple[int, int]:
        return (int(psd_x * scale_x), int(psd_y * scale_y))

    pokemon_font_path = _get_pokemon_font_path()
    path_key = pokemon_font_path or ""
    level_sz = int(28 * scale_y)
    hp_sz = int(32 * scale_y)
    level_font = _load_font_cached(path_key, level_sz)
    hp_font = _load_font_cached(path_key, hp_sz)
    if level_font is None:
        level_font = hp_font
    if hp_font is None:
        hp_font = level_font

    def _load_font_with_size(size: int) -> Any:
        f = _load_font_cached(path_key, size)
        return f if f is not None else _load_font_cached("", size)

    def _text_width(font_obj: Any, text: str) -> int:
        """Get text width using available font method (getbbox > getlength > getsize)."""
        try:
            bbox = font_obj.getbbox(text)
            return int(bbox[2] - bbox[0])
        except (AttributeError, TypeError):
            # getbbox not available - try getlength
            try:
                return int(font_obj.getlength(text))
            except (AttributeError, TypeError):
                # getlength not available - fallback to getsize (older PIL)
                try:
                    return font_obj.getsize(text)[0]  # type: ignore[arg-type]
                except (AttributeError, TypeError, IndexError):
                    # All methods failed - return estimated width
                    return len(text) * 10  # Rough estimate
        except Exception:
            # Unexpected error - return estimated width
            return len(text) * 10  # Rough estimate

    def _dynamic_font(text: str, base_size: int, min_size: int, max_width: int) -> Any:
        size = base_size
        font_obj = _load_font_with_size(size)
        while size > min_size and _text_width(font_obj, text) > max_width:
            size -= 2
            font_obj = _load_font_with_size(size)
        return font_obj

    # Player UI elements (bottom right) - positions from PSD
    # Player Pokémon name: x=1186, y=694
    my_species_display = _format_species_name(my_species)
    
    # Calculate icon space needed (transformation + status)
    icon_size = int(56 * scale_y)
    icon_spacing = int(4 * scale_x)
    icon_space_between = int(8 * scale_x)  # Space between name and first icon
    
    # Count how many icons will be displayed
    num_transformation_icons = 1 if (my_mega_evolved or my_dynamaxed or my_primal_reversion) else 0
    num_status_icons = 1 if my_status else 0
    total_icons = num_transformation_icons + num_status_icons
    
    # Calculate total icon space
    total_icon_width = (icon_size * total_icons) + (icon_spacing * max(0, total_icons - 1)) + icon_space_between if total_icons > 0 else 0
    
    # Player name position and level position
    my_name_pos_x = int(950 * scale_x)
    my_level_pos_x = int(1420 * scale_x)
    available_width = my_level_pos_x - my_name_pos_x
    
    # Reserve space for icons, adjust max name width accordingly
    base_max_player_name_width = int(360 * scale_x)
    if total_icons > 0:
        # Reduce max width to leave space for icons
        max_player_name_width = max(int(200 * scale_x), available_width - total_icon_width)
    else:
        max_player_name_width = base_max_player_name_width
    
    base_player_font_size = int(40 * scale_y)
    min_player_font_size = int(26 * scale_y)
    my_name_font = _dynamic_font(
        my_species_display,
        base_player_font_size,
        min_player_font_size,
        max_player_name_width,
    )

    # Player name (Marshadow): x=1181, y=664 from PSD (EXACT - 16.41in x 9.23in at 72 DPI)
    my_name_pos = scale_pos(950, 700)
    # Very thin stroke for Pokémon name - just barely noticeable
    stroke_width = max(int(0.5 * scale_x), 0)
    _draw_text_with_stroke(draw, my_name_pos, my_species_display, 
                          (255, 255, 255), my_name_font, (0, 0, 0), stroke_width)
    
    # Draw icons to the right of player name (transformation icons first, then status)
    icon_x_offset = my_name_pos[0] + _text_width(my_name_font, my_species_display) + icon_space_between
    # Get text height to center icons with text
    try:
        # Get font metrics to calculate text height
        bbox = my_name_font.getbbox(my_species_display)
        text_height = bbox[3] - bbox[1]  # bottom - top
    except (AttributeError, TypeError):
        # getbbox not available - fallback to font size
        text_height = my_name_font.size if hasattr(my_name_font, 'size') else int(40 * scale_y)
    except Exception:
        # Unexpected error - use default estimate
        text_height = int(40 * scale_y)
    # Center icon vertically with text
    icon_y = my_name_pos[1] + (text_height - icon_size) // 2
    
    # Draw transformation and status icons
    icon_x_offset = _draw_transformation_and_status_icons(
        img, icon_x_offset, icon_y, icon_size, icon_spacing,
        my_name_pos[1], text_height, scale_y,
        my_mega_evolved, my_dynamaxed, my_primal_reversion, my_status
    )
    
    # Player level: x=1392, y=685 from PSD (EXACT - 19.34in x 9.52in at 72 DPI, adjusted for alignment)
    my_level_pos = scale_pos(1420, 710)
    # Very thin stroke for level - just barely noticeable
    stroke_width = max(int(0.5 * scale_x), 1)
    _draw_text_with_stroke(draw, my_level_pos, str(my_level),  # No "Lv " prefix
                          (255, 255, 255), level_font, (0, 0, 0), stroke_width)
    
    # Player HP counter: x=1093, y=746 from PSD (EXACT - 15.19in x 10.37in at 72 DPI)
    # Only draw if not hiding HP text (for streaming)
    if not hide_hp_text:
        my_hp_pos = scale_pos(1098, 785)
        my_hp_text = f"{my_hp_current}/{my_hp_max}"
        _draw_text_with_stroke(draw, my_hp_pos, my_hp_text, 
                              (255, 255, 255), hp_font, (0, 0, 0), stroke_width)
    
    # Player HP bar (now drawn before background in main render loop, so removed from here)
    
    # Player Pokéballs: start x=958, y=887 from PSD (EXACT - first ball at 13.31in x 12.33in)
    # Second ball is at 14.31in, so spacing is 72 pixels (1 inch at 72 DPI)
    my_ball_start = scale_pos(958, 850)
    ball_spacing = int(72 * scale_x)  # EXACT spacing from PSD (72 pixels = 1 inch)
    _draw_team_pokeballs(
        img, my_ball_start, ball_spacing, scale_y,
        my_team_total, my_team_alive, my_team_statuses, my_team_hp, my_has_status
    )
    
    # Opponent UI elements (top left) - positions from PSD
    # Opponent Pokémon name: x=51, y=198 (+ gender icon ♂/♀ next to name for wild/trainer)
    # Font size adjusts based on name length (same logic as player)
    opp_species_display = _format_species_name(opp_species)
    if opp_gender and str(opp_gender).lower() in ("male", "m"):
        opp_species_display = opp_species_display + " \u2642"  # ♂
    elif opp_gender and str(opp_gender).lower() in ("female", "f"):
        opp_species_display = opp_species_display + " \u2640"  # ♀
    
    # Calculate icon space needed for opponent (transformation + status)
    opp_icon_size = int(56 * scale_y)
    opp_icon_spacing = int(4 * scale_x)
    opp_icon_space_between = int(8 * scale_x)  # Space between name and first icon
    
    # Count how many icons will be displayed for opponent
    opp_num_transformation_icons = 1 if (opp_mega_evolved or opp_dynamaxed or opp_primal_reversion) else 0
    opp_num_status_icons = 1 if opp_status else 0
    opp_total_icons = opp_num_transformation_icons + opp_num_status_icons
    
    # Calculate total icon space for opponent
    opp_total_icon_width = (opp_icon_size * opp_total_icons) + (opp_icon_spacing * max(0, opp_total_icons - 1)) + opp_icon_space_between if opp_total_icons > 0 else 0
    
    # Opponent name position and level position
    opp_name_pos_x = int(49 * scale_x)
    opp_level_pos_x = int(525 * scale_x)
    opp_available_width = opp_level_pos_x - opp_name_pos_x
    
    # Reserve space for icons, adjust max name width accordingly
    base_max_opp_name_width = int(340 * scale_x)
    if opp_total_icons > 0:
        # Reduce max width to leave space for icons
        max_opp_name_width = max(int(200 * scale_x), opp_available_width - opp_total_icon_width)
    else:
        max_opp_name_width = base_max_opp_name_width
    
    base_opp_font_size = int(38 * scale_y)
    min_opp_font_size = int(24 * scale_y)
    opp_name_font = _dynamic_font(
        opp_species_display,
        base_opp_font_size,
        min_opp_font_size,
        max_opp_name_width,
    )
    
    # Opponent name (Zygarde Complete): x=49, y=182 from PSD (EXACT - 0.68in x 2.52in at 72 DPI)
    opp_name_pos = scale_pos(49, 190)
    # Very thin stroke for Pokémon name - just barely noticeable
    stroke_width = max(int(0.5 * scale_x), 0)
    _draw_text_with_stroke(draw, opp_name_pos, opp_species_display, 
                          (255, 255, 255), opp_name_font, (0, 0, 0), stroke_width)
    
    # Draw icons to the right of opponent name (transformation icons first, then status)
    opp_icon_x_offset = opp_name_pos[0] + _text_width(opp_name_font, opp_species_display) + opp_icon_space_between
    # Get text height to center icons with text
    try:
        # Get font metrics to calculate text height
        opp_bbox = opp_name_font.getbbox(opp_species_display)
        opp_text_height = opp_bbox[3] - opp_bbox[1]  # bottom - top
    except (AttributeError, TypeError):
        # getbbox not available - fallback to font size
        opp_text_height = opp_name_font.size if hasattr(opp_name_font, 'size') else int(40 * scale_y)
    except Exception:
        # Unexpected error - use default estimate
        opp_text_height = int(40 * scale_y)
    # Center icon vertically with text
    opp_icon_y = opp_name_pos[1] + (opp_text_height - opp_icon_size) // 2
    
    # Draw transformation and status icons
    opp_icon_x_offset = _draw_transformation_and_status_icons(
        img, opp_icon_x_offset, opp_icon_y, opp_icon_size, opp_icon_spacing,
        opp_name_pos[1], opp_text_height, scale_y,
        opp_mega_evolved, opp_dynamaxed, opp_primal_reversion, opp_status
    )
    
    # Opponent level: x=497, y=171 from PSD (EXACT - 6.91in x 2.38in at 72 DPI)
    opp_level_pos = scale_pos(525, 200)
    # Very thin stroke for level - just barely noticeable
    stroke_width = max(int(0.5 * scale_x), 1)
    _draw_text_with_stroke(draw, opp_level_pos, str(opp_level),  # No "Lv " prefix
                          (255, 255, 255), level_font, (0, 0, 0), stroke_width)
    
    # Opponent HP bar (now drawn before background in main render loop, so removed from here)
    
    # Opponent Pokéballs: skip for wild encounters (no "team" of balls)
    if opp_team_total > 0:
        opp_ball_start = scale_pos(40, 240)
        ball_spacing = int(72 * scale_x)  # EXACT spacing from PSD (72 pixels = 1 inch)
        _draw_team_pokeballs(
            img, opp_ball_start, ball_spacing, scale_y,
            opp_team_total, opp_team_alive, opp_team_statuses, opp_team_hp, opp_has_status
        )


def _species_candidates_for_size(species: str) -> List[str]:
    """Build candidate names for height lookup (mega base, form variants, etc.)."""
    normalized = _norm_species(species)
    if not normalized:
        return []
    parts = normalized.split("-")
    candidates: List[str] = []
    if "mega" in normalized:
        base_parts = []
        for part in parts:
            if part.lower() == "mega":
                break
            base_parts.append(part)
        if base_parts:
            b = "-".join(base_parts).strip()
            if b and b not in candidates:
                candidates.append(b)
    for i in range(1, len(parts) + 1):
        c = "-".join(parts[:i]).strip()
        if c and c not in candidates:
            candidates.append(c)
    for i in range(len(parts), 0, -1):
        c = "-".join(parts[:i]).strip()
        if c and c not in candidates:
            candidates.append(c)
    return candidates


def _height_to_mult(height_m: float) -> float:
    if height_m < 0.5:
        return 0.65
    if height_m < 1.0:
        return 0.80
    if height_m < 2.0:
        return 1.0
    if height_m < 3.0:
        return 1.05
    return 1.10


@lru_cache(maxsize=512)
def _get_pokemon_size_multiplier(species: str) -> float:
    """Size multiplier from pokedex height_m. Cache-only (db_cache); no DB. Miss -> 1.0."""
    try:
        cand = _species_candidates_for_size(species)
        if not cand:
            return 1.0
        height_m: Optional[float] = None
        if _lib_db_cache:
            for name in cand:
                d = _lib_db_cache.get_cached_pokedex(name)
                if d and d.get("height_m") is not None:
                    height_m = float(d["height_m"])
                    break
        if height_m is not None:
            return _height_to_mult(height_m)
        return 1.0
    except (KeyError, TypeError, ValueError) as e:
        # Invalid data format - return default
        # In production: logger.debug(f"Error getting size multiplier for {species}: {e}")
        return 1.0
    except Exception as e:
        # Unexpected error - return default
        # In production: logger.warning(f"Unexpected error getting size multiplier for {species}: {e}")
        return 1.0


@lru_cache(maxsize=512)
def _get_size_multipliers_batch(my_species: str, opp_species: str) -> Tuple[float, float]:
    """Fetch both species' size multipliers. Cache-only (db_cache); no DB. Miss -> 1.0."""
    try:
        my_c = _species_candidates_for_size(my_species)
        opp_c = _species_candidates_for_size(opp_species)
        all_names = list(dict.fromkeys(my_c + opp_c))
        if not all_names:
            return (1.0, 1.0)
        name_to_height: Dict[str, float] = {}
        if _lib_db_cache:
            for name in all_names:
                d = _lib_db_cache.get_cached_pokedex(name)
                if d and d.get("height_m") is not None:
                    name_to_height[name] = float(d["height_m"])
        def first_height(cands: List[str]) -> float:
            for n in cands:
                h = name_to_height.get(n)
                if h is not None:
                    return _height_to_mult(h)
            return 1.0
        return (first_height(my_c), first_height(opp_c))
    except (KeyError, TypeError, ValueError) as e:
        # Invalid data format - return defaults
        # In production: logger.debug(f"Error getting size multipliers: {e}")
        return (1.0, 1.0)
    except Exception as e:
        # Unexpected error - return defaults
        # In production: logger.warning(f"Unexpected error getting size multipliers: {e}")
        return (1.0, 1.0)


def render_turn_gif(
    *,
    battle_id: str,
    turn: int,
    pov: str,  # "p1" or "p2" (viewer POV)
    gen: int,
    my_species: str,
    my_shiny: bool,
    my_female: bool,
    my_level: int = 100,
    my_hp_current: int = 100,
    my_hp_max: int = 100,
    my_team_alive: int = 6,
    my_team_total: int = 6,
    my_form: Optional[str] = None,
    my_has_substitute: bool = False,
    my_status: Optional[str] = None,  # Status condition: "slp", "psn", "brn", "par", "frz"
    my_mega_evolved: bool = False,
    my_dynamaxed: bool = False,
    my_primal_reversion: Optional[str] = None,  # "Groudon" or "Kyogre"
    opp_species: str,
    opp_shiny: bool,
    opp_female: bool,
    opp_level: int = 100,
    opp_hp_current: int = 100,
    opp_hp_max: int = 100,
    opp_team_alive: int = 6,
    opp_team_total: int = 6,
    opp_form: Optional[str] = None,
    opp_has_substitute: bool = False,
    opp_status: Optional[str] = None,  # Status condition
    opp_mega_evolved: bool = False,
    opp_dynamaxed: bool = False,
    opp_primal_reversion: Optional[str] = None,  # "Groudon" or "Kyogre"
    opp_gender: Optional[str] = None,  # "male", "female", or None (genderless) - shown as ♂/♀ next to name
    canvas_size: Tuple[int, int] = (512, 384),  # Reduced size for smaller files
    duration_ms: int = 100,  # 100ms per frame
    hide_hp_text: bool = False,  # Hide HP text (for streaming)
    nullscape_active: bool = False,  # Whether Nullscape is active (for background)
    my_team_statuses: Optional[List[Optional[str]]] = None,  # Status conditions for each party member
    opp_team_statuses: Optional[List[Optional[str]]] = None,  # Status conditions for each party member
    my_team_hp: Optional[List[Tuple[int, int]]] = None,  # HP values for each party member (current_hp, max_hp)
    opp_team_hp: Optional[List[Tuple[int, int]]] = None,  # HP values for each party member (current_hp, max_hp)
    bg_key: Optional[str] = None,
    my_exp_pct: Optional[float] = None,  # EXP bar fill 0.0–1.0 (user only; Gen III+ exp_requirements)
) -> Optional[Any]:
    """
    Create an animated GIF for this POV + turn and return an in-memory buffer or file path.
    Uses your on-disk layout under pvp/_common/sprites/<species>/.
    Returns None if Pillow is unavailable or both sprites are missing.
    """
    if _PILImage is None:
        return None

    # Toggle in-memory vs local save.
    use_memory = os.getenv("RENDER_IN_MEMORY", "0").lower() in ("1", "true", "yes")
    out_path = None
    if not use_memory:
        # Add timestamp + unique suffix to prevent Discord caching and concurrent-render collision
        import uuid
        timestamp = int(time.time() * 1000)
        unique = uuid.uuid4().hex[:8]
        out_dir = MEDIA_ROOT / str(battle_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"turn{turn}_{pov}_{timestamp}_{unique}.gif"

    def _resolve_my_path() -> Optional[Path]:
        if my_has_substitute:
            p = find_sprite("substitute", gen=gen, perspective="back", shiny=False, female=False, prefer_animated=True, form=None)
            if p and p.exists():
                return p
            return find_sprite(my_species, gen=gen, perspective="back", shiny=my_shiny, female=my_female, prefer_animated=True, form=my_form)
        return find_sprite(my_species, gen=gen, perspective="back", shiny=my_shiny, female=my_female, prefer_animated=True, form=my_form)

    def _resolve_opp_path() -> Optional[Path]:
        if opp_has_substitute:
            p = find_sprite("substitute", gen=gen, perspective="front", shiny=False, female=False, prefer_animated=True, form=None)
            if p and p.exists():
                return p
            return find_sprite(opp_species, gen=gen, perspective="front", shiny=opp_shiny, female=opp_female, prefer_animated=True, form=opp_form)
        return find_sprite(opp_species, gen=gen, perspective="front", shiny=opp_shiny, female=opp_female, prefer_animated=True, form=opp_form)

    log_perf = os.getenv("RENDER_LOG", "0").lower() in ("1", "true", "yes")
    t0 = time.perf_counter()

    fut_my = _render_executor.submit(_resolve_my_path)
    fut_opp = _render_executor.submit(_resolve_opp_path)
    my_sprite_path = fut_my.result()
    opp_sprite_path = fut_opp.result()
    t_paths = time.perf_counter()

    fut_my_frames = _render_executor.submit(_get_sprite_frames, my_sprite_path)
    fut_opp_frames = _render_executor.submit(_get_sprite_frames, opp_sprite_path)
    my_frames_raw = fut_my_frames.result()
    opp_frames_raw = fut_opp_frames.result()
    t_frames = time.perf_counter()
    

    # If both missing, bail (panel code will fall back to text)
    if (not my_frames_raw or my_frames_raw[0] is None) and (not opp_frames_raw or opp_frames_raw[0] is None):
        return None

    W, H = canvas_size
    
    # Background (load based on POV, with Nullscape check)
    base = _background(canvas_size, pov=pov, nullscape_active=nullscape_active, bg_key=bg_key)
    
    # Initialize frames list outside try block so it's accessible for saving
    frames: List[PILImageType] = []
    scaled_frames: List[PILImageType] = []
    
    try:
        # Scale sprites to canvas size
        base_back_h = int(H * 0.31)
        base_front_h = int(H * 0.22)

        my_size_mult, opp_size_mult = _get_size_multipliers_batch(my_species, opp_species)
        if my_dynamaxed:
            my_size_mult *= 2.0
        if opp_dynamaxed:
            opp_size_mult *= 2.0
        target_back_h = int(base_back_h * my_size_mult)
        target_front_h = int(base_front_h * opp_size_mult)

        def _frames_and_scale(raw_frames: List[Any], target_h: int) -> List[Any]:
            if not raw_frames or raw_frames[0] is None:
                return [None]
            return [_scale_to_height(f, target_h) for f in raw_frames]

        fut_my_f = _render_executor.submit(_frames_and_scale, my_frames_raw, target_back_h)
        fut_opp_f = _render_executor.submit(_frames_and_scale, opp_frames_raw, target_front_h)
        my_frames = fut_my_f.result()
        opp_frames = fut_opp_f.result()
        scaled_frames.extend([f for f in my_frames if f is not None])
        scaled_frames.extend([f for f in opp_frames if f is not None])
        t_scaled = time.perf_counter()

        # Use all animation frames from sprites
        my_frame_count = len(my_frames) if my_frames[0] is not None else 0
        opp_frame_count = len(opp_frames) if opp_frames[0] is not None else 0
        max_sprite_frames = max(my_frame_count, opp_frame_count)
        
        # Use ALL sprite frames - if sprites have animation, use all frames
        # If both are static (1 frame each), we still need at least 2 frames for GIF animation
        if max_sprite_frames > 1:
            n = max_sprite_frames  # Use all frames from animated sprites
        elif max_sprite_frames == 1:
            # Both sprites are static (1 frame each) - create 2 frames to ensure GIF animates
            n = 2
        else:
            # No sprites available - still create 2 frames for GIF
            n = 2
        
        # -----------------------------------------------------------------------
        # COORDINATES REFERENCE (PSD 1536×1024). Positions scaled by scale_x, scale_y.
        # See pvp/COORDINATES_REFERENCE.md for file locations. Summary:
        #   Sprites:     back (150, 647), front (1100, 380)
        #   My HP bar:   (1196, 745), width 289
        #   My EXP bar:  same x as My HP bar, y = my_hp_bar_y + 15*scale_y + 2*scale_y
        #   Opp HP bar:  (67, 237), width 295
        #   My name/level/HP text/balls and Opp name/level/balls → _draw_ui_elements()
        # -----------------------------------------------------------------------
        PSD_W, PSD_H = 1536, 1024
        scale_x = canvas_size[0] / PSD_W
        scale_y = canvas_size[1] / PSD_H
        
        psd_back_x, psd_back_y = 150, 647
        psd_front_x, psd_front_y = 1100, 380
        
        # Dynamax sprites go up (higher Y position) - reduce Y by 20% when Dynamaxed
        back_y_offset = 0
        front_y_offset = 0
        if my_dynamaxed:
            back_y_offset = int(psd_back_y * 0.2)  # Move up by 20% of original Y
        if opp_dynamaxed:
            front_y_offset = int(psd_front_y * 0.2)  # Move up by 20% of original Y
        
        # Pre-render UI layer once (names, icons, pokeballs, HP bars)
        ui_layer = _PILImage.new("RGBA", canvas_size, (0, 0, 0, 0))  # type: ignore[attr-defined]
        if _PILImageDraw is not None:
            try:
                draw_ui = _PILImageDraw.Draw(ui_layer)
                _draw_ui_elements(
                    draw_ui,
                    ui_layer,
                    my_species, my_level, my_hp_current, my_hp_max,
                    my_team_alive, my_team_total, bool(my_status),
                    opp_species, opp_level, opp_hp_current, opp_hp_max,
                    opp_team_alive, opp_team_total, bool(opp_status),
                    my_shiny=my_shiny, opp_shiny=opp_shiny, hide_hp_text=hide_hp_text,
                    my_mega_evolved=my_mega_evolved, my_dynamaxed=my_dynamaxed, my_primal_reversion=my_primal_reversion,
                    opp_mega_evolved=opp_mega_evolved, opp_dynamaxed=opp_dynamaxed, opp_primal_reversion=opp_primal_reversion,
                    my_status=my_status, opp_status=opp_status,
                    my_team_statuses=my_team_statuses, opp_team_statuses=opp_team_statuses,
                    my_team_hp=my_team_hp, opp_team_hp=opp_team_hp,
                    opp_gender=opp_gender,
                )

                # Draw HP bars on top of UI
                my_hp_pct = my_hp_current / my_hp_max if my_hp_max > 0 else 0.0
                opp_hp_pct = opp_hp_current / opp_hp_max if opp_hp_max > 0 else 0.0

                def scale_pos(psd_x: int, psd_y: int) -> Tuple[int, int]:
                    return (int(psd_x * scale_x), int(psd_y * scale_y))

                my_hp_bar_x, my_hp_bar_y = scale_pos(1196, 745)
                my_hp_bar_width = int(289 * scale_x)
                _draw_hp_bar(draw_ui, ui_layer, my_hp_bar_x, my_hp_bar_y, my_hp_bar_width, my_hp_pct, is_opponent=False, scale_y=scale_y)
                # Blue EXP bar (only when my_exp_pct is provided): position (1136, 836), width 350, height 20
                if my_exp_pct is not None:
                    exp_bar_x, exp_bar_y = scale_pos(1136, 836)
                    exp_bar_width = int(350 * scale_x)
                    _draw_exp_bar(draw_ui, ui_layer, exp_bar_x, exp_bar_y, exp_bar_width, my_exp_pct, scale_y=scale_y)

                opp_hp_bar_x, opp_hp_bar_y = scale_pos(67, 237)
                opp_hp_bar_width = int(295 * scale_x)
                _draw_hp_bar(draw_ui, ui_layer, opp_hp_bar_x, opp_hp_bar_y, opp_hp_bar_width, opp_hp_pct, is_opponent=True, scale_y=scale_y)
            except Exception:
                pass
        t_ui = time.perf_counter()

        for i in range(n):
            lf = my_frames[i % len(my_frames)] if my_frames[0] is not None else None
            rf = opp_frames[i % len(opp_frames)] if opp_frames[0] is not None else None
            
            # Start with background
            frame = base.copy()
            
            # Add sprites
            if lf is not None:
                sprite_x = int(psd_back_x * scale_x)
                sprite_y = int((psd_back_y - back_y_offset) * scale_y)
                frame.alpha_composite(lf, (sprite_x, sprite_y))
            if rf is not None:
                sprite_x = int(psd_front_x * scale_x)
                sprite_y = int((psd_front_y - front_y_offset) * scale_y)
                frame.alpha_composite(rf, (sprite_x, sprite_y))
            
            # Composite UI layer on top
            try:
                frame.alpha_composite(ui_layer)
            except Exception:
                pass
            
            frames.append(frame)
        t_comp = time.perf_counter()
    finally:
        pass

    # Save with fast quantization and optimization
    try:
        if _PILImage is None or len(frames) == 0:
            _safe_close(base)
            return None
        
        MAX_FILE_SIZE = 7 * 1024 * 1024  # 7MB Discord limit
        
        # Convert to RGB and quantize with MAXCOVERAGE for better color preservation
        rgb_frames = [f.convert("RGB") for f in frames]
        
        # Cleanup original frames after conversion
        _safe_close_list(frames)
        _safe_close_list(scaled_frames)
        
        # Use MAXCOVERAGE for better color preservation with max colors
        quantized_first = rgb_frames[0].quantize(
            colors=256,  # Max colors for vibrant images
            method=_PILImage.Quantize.MAXCOVERAGE,  # Better color preservation
            dither=_PILImage.Dither.NONE
        )
        quantized_frames = [quantized_first]
        for f in rgb_frames[1:]:
            q = f.quantize(palette=quantized_first, dither=_PILImage.Dither.NONE)
            quantized_frames.append(q)

        # Cleanup RGB frames after quantization
        _safe_close_list(rgb_frames)
        
        # Try saving with all frames - ensure we have at least 2 frames for animation
        if len(quantized_frames) < 2:
            # If somehow we only have 1 frame, duplicate it to create animation
            quantized_frames.append(quantized_frames[0].copy())
        
        optimize_flag = os.getenv("RENDER_OPTIMIZE", "0").lower() in ("1", "true", "yes")

        def _save_to_buffer(frames_list: List[PILImageType], duration: int) -> BytesIO:
            buf = BytesIO()
            frames_list[0].save(
                buf,
                save_all=True,
                append_images=frames_list[1:],
                duration=duration,
                loop=0,
                format="GIF",
                disposal=2,
                optimize=optimize_flag,
            )
            buf.seek(0)
            return buf

        if use_memory:
            buf = _save_to_buffer(quantized_frames, duration_ms)
            file_size = len(buf.getbuffer())
        else:
            temp_path = out_path.with_suffix(".tmp.gif")  # type: ignore[union-attr]
            quantized_frames[0].save(
                temp_path,
                save_all=True,
                append_images=quantized_frames[1:],
                duration=duration_ms,
                loop=0,  # 0 means infinite loop
                format="GIF",
                disposal=2,
                optimize=optimize_flag,
            )
            file_size = temp_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            # Reduce frames: take every 2nd frame
            reduced_frames = quantized_frames[::2]
            if len(reduced_frames) < 2:
                reduced_frames = quantized_frames[:2]
            
            if use_memory:
                buf = _save_to_buffer(reduced_frames, duration_ms * 2)
                file_size = len(buf.getbuffer())
            else:
                reduced_frames[0].save(
                    temp_path,
                    save_all=True,
                    append_images=reduced_frames[1:],
                    duration=duration_ms * 2,
                    loop=0,
                    format="GIF",
                    disposal=2,
                    optimize=optimize_flag,
                )
                file_size = temp_path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                # Still too large - reduce to 4 frames max
                reduced_frames = quantized_frames[:4]
                if len(reduced_frames) < 2:
                    reduced_frames = quantized_frames[:2]
                if use_memory:
                    buf = _save_to_buffer(reduced_frames, duration_ms * 2)
                    file_size = len(buf.getbuffer())
                else:
                    reduced_frames[0].save(
                        temp_path,
                        save_all=True,
                        append_images=reduced_frames[1:],
                        duration=duration_ms * 2,
                        loop=0,
                        format="GIF",
                        disposal=2,
                        optimize=optimize_flag,
                    )
                    file_size = temp_path.stat().st_size
        
        _safe_close(base)
        # Cleanup quantized frames
        _safe_close_list(quantized_frames)
        _safe_close(quantized_first)
        
        if use_memory:
            return buf
        # Move temp file to final location
        temp_path.replace(out_path)  # type: ignore[arg-type]
        return out_path
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Renderer] render_turn_gif failed: {e}")
        # Ensure cleanup on error
        _safe_close(base)
        _safe_close_list(frames)
        _safe_close_list(scaled_frames)
        return None


def cleanup_battle_media(battle_id: str) -> None:
    """Delete tmp_battle_media/<battle_id> recursively."""
    folder = MEDIA_ROOT / str(battle_id)
    try:
        if folder.exists():
            shutil.rmtree(folder)
    except (OSError, PermissionError) as e:
        # Permission denied or file in use - log but don't crash
        # In production: logger.warning(f"Failed to cleanup battle media {battle_id}: {e}")
        pass
    except Exception as e:
        # Unexpected error
        # In production: logger.warning(f"Unexpected error cleaning up battle media {battle_id}: {e}")
        pass

def cleanup_old_battle_media(max_age_hours: int = 24) -> None:
    """Delete battle media files older than max_age_hours."""
    if not MEDIA_ROOT.exists():
        return
    
    import time
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    try:
        for battle_folder in MEDIA_ROOT.iterdir():
            if not battle_folder.is_dir():
                continue
            
            # Check if folder is older than max_age
            folder_age = current_time - battle_folder.stat().st_mtime
            if folder_age > max_age_seconds:
                try:
                    shutil.rmtree(battle_folder)
                except (OSError, PermissionError) as e:
                    # Permission denied or file in use - skip this folder
                    # In production: logger.debug(f"Failed to cleanup old battle media {battle_folder}: {e}")
                    pass
                except Exception as e:
                    # Unexpected error - skip this folder
                    # In production: logger.warning(f"Unexpected error cleaning up {battle_folder}: {e}")
                    pass
    except (OSError, PermissionError) as e:
        # Permission denied accessing MEDIA_ROOT
        # In production: logger.warning(f"Failed to access MEDIA_ROOT for cleanup: {e}")
        pass
    except Exception as e:
        # Unexpected error
        # In production: logger.warning(f"Unexpected error in cleanup_old_battle_media: {e}")
        pass
