"""
Create animated and static sprites from pre-organized source folders.

Input structure (Windows path provided by user):
  C:\\Users\\adama\\Downloads\\Animated Pokemon Sprites\\Animated Pokemon Sprites\\Graphics\\Pokemon\\
    Front\\
    Back\\
    Front shiny\\
    Back shiny\\

Rules:
- Use pre-sliced horizontal sprite sheets where each frame is side-by-side.
- Auto-detect frame count; fall back to best guess when ambiguous.
- Generate both animated GIFs and static PNGs (first frame) for:
    - front:   animated-front.gif, front.png
    - back:    animated-back.gif,  back.png
    - shiny front:   animated-shiny-front.gif, shiny-front.png
    - shiny back:    animated-shiny-back.gif,  shiny-back.png
- Respect female variants when the source filename ends with "_female" (case-insensitive).
- Resolve forms with mapping in form_mapping.py when possible; otherwise derive from numbered suffixes (e.g., LYCANROC_1 -> lycanroc-midnight).
- Skip invalid forms explicitly: e.g., Pikachu must not produce an Alolan form.

Target structure:
  pvp/_common/sprites/<folder>/
    animated-front.gif
    front.png
    animated-back.gif
    back.png
    animated-shiny-front.gif
    shiny-front.png
    animated-shiny-back.gif
    shiny-back.png

This script is idempotent: existing files are preserved unless --overwrite is used.
It prints a detailed summary of created files.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

# Optional mapping utilities
try:
    import form_mapping  # type: ignore
except Exception:
    form_mapping = None  # fall back to local heuristics


# ---------- CONFIG ----------

DEFAULT_SRC_ROOT = (
    r"C:\\Users\\adama\\Downloads\\Animated Pokemon Sprites\\Animated Pokemon Sprites\\Graphics\\Pokemon"
)

SRC_SUBFOLDERS = {
    "front": "Front",
    "back": "Back",
    "front_shiny": "Front shiny",
    "back_shiny": "Back shiny",
}

# Write outputs next to this script in a local "output" folder
TARGET_ROOT = Path(__file__).resolve().parent / "output"

# GIF parameters
DEFAULT_FPS = 12  # frames per second
DEFAULT_LOOP = 0  # loop forever


@dataclass
class SourceSheet:
    base_name: str             # e.g., LYCANROC
    form_number: Optional[str] # e.g., "1" or None
    is_female: bool
    path: Path


def parse_source_filename(file: Path) -> SourceSheet:
    name = file.stem  # without extension
    # Female suffix
    is_female = name.lower().endswith("_female")
    if is_female:
        name = name[:-7]

    # Numbered form suffix: NAME_<num>
    form_number = None
    if "_" in name:
        base, maybe_num = name.rsplit("_", 1)
        if maybe_num.isdigit():
            return SourceSheet(base_name=base, form_number=maybe_num, is_female=is_female, path=file)
    return SourceSheet(base_name=name, form_number=None, is_female=is_female, path=file)


def get_form_folder(base_upper: str, form_number: Optional[str]) -> Optional[str]:
    """Resolve target folder name using form_mapping when available.
    Falls back to lowercased base name if no mapping.
    """
    base_clean = base_upper.lower()
    # Special rule: Pikachu should not have an Alolan form
    if base_clean == "pikachu":
        # Always return base folder; never build regional variants here
        return "pikachu"

    # Prefer mapping module if present
    if form_mapping and hasattr(form_mapping, "get_form_folder_name"):
        try:
            # form_mapping often expects e.g., "LYCANROC_1" -> "lycanroc-midnight"
            key = base_upper if form_number is None else f"{base_upper}_{form_number}"
            mapped = form_mapping.get_form_folder_name(key)
            if mapped:
                return mapped
        except Exception:
            pass

    # Fallbacks: basic lowercased base folder
    return base_clean


def detect_frames(im: Image.Image) -> Tuple[int, int]:
    """Detect number of frames and frame width for a horizontal strip.
    Detection order:
      1) Preferred: ratio = width // height (typical sheets are N*H by H)
      2) Fallback: try divisors from 12..2 with content check
    Returns (num_frames, frame_width).
    """
    w, h = im.size
    # 1) Ratio-based detection (most common: each frame is square HxH)
    if h > 0 and w % h == 0:
        n = max(1, min(16, w // h))
        if n >= 2:
            return n, h
    # 2) Content-checked divisors
    best_n = 1
    for n in range(12, 1, -1):
        if w % n != 0:
            continue
        fw = w // n
        box0 = (0, 0, fw, h)
        boxN = ((n - 1) * fw, 0, n * fw, h)
        f0 = im.crop(box0)
        fN = im.crop(boxN)
        if list(f0.getdata()) != list(fN.getdata()):
            best_n = n
            break
    return best_n, (w // best_n)


def extract_frames(im: Image.Image) -> List[Image.Image]:
    n, fw = detect_frames(im)
    w, h = im.size
    frames: List[Image.Image] = []
    for i in range(n):
        box = (i * fw, 0, (i + 1) * fw, h)
        frames.append(im.crop(box))
    return frames or [im]


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def save_animated_and_static(frames: List[Image.Image], out_dir: Path, base: str) -> List[str]:
    created: List[str] = []
    ensure_dir(out_dir)
    # Static from first frame ONLY
    static_path = out_dir / f"{base}.png"
    if not static_path.exists():
        frames[0].save(static_path)
        created.append(str(static_path))

    # Animated GIF
    gif_path = out_dir / f"{base}.gif"
    if not gif_path.exists():
        duration_ms = int(1000 / DEFAULT_FPS)
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:] if len(frames) > 1 else [],
            loop=DEFAULT_LOOP,
            duration=duration_ms,
            disposal=2,
            optimize=False,
            transparency=0,
        )
        created.append(str(gif_path))
    return created


def process_sheet(sheet: SourceSheet, kind: str, shiny: bool, overwrite: bool = False) -> Tuple[str, List[str]]:
    """Process a single source sheet into target outputs.
    kind in {"front","back"}; shiny bool.
    Returns target folder and list of created file paths.
    """
    with Image.open(sheet.path).convert("RGBA") as im:
        frames = extract_frames(im)

    folder = get_form_folder(sheet.base_name, sheet.form_number)
    if not folder:
        folder = sheet.base_name.lower()

    # Skip invalid: Pikachu Alolan (already prevented by get_form_folder)
    # Female suffix handled by separate subfolder naming convention: we create into the same folder,
    # but output filename uses the standard names the bot expects.

    out_dir = TARGET_ROOT / folder

    # Build base filename
    if kind == "front" and not shiny:
        # animated-front.gif + front.png
        base_gif = "animated-front"
        base_png = "front"
    elif kind == "back" and not shiny:
        base_gif = "animated-back"
        base_png = "back"
    elif kind == "front" and shiny:
        base_gif = "animated-shiny-front"
        base_png = "shiny-front"
    else:  # back shiny
        base_gif = "animated-shiny-back"
        base_png = "shiny-back"

    created: List[str] = []
    # Static
    static_path = out_dir / f"{base_png}.png"
    gif_path = out_dir / f"{base_gif}.gif"

    ensure_dir(out_dir)

    with Image.open(sheet.path).convert("RGBA") as im2:
        frames2 = extract_frames(im2)
        if overwrite or not static_path.exists():
            frames2[0].save(static_path)
            created.append(str(static_path))
        if overwrite or not gif_path.exists():
            duration_ms = int(1000 / DEFAULT_FPS)
            frames2[0].save(
                gif_path,
                save_all=True,
                append_images=frames2[1:] if len(frames2) > 1 else [],
                loop=DEFAULT_LOOP,
                duration=duration_ms,
                disposal=2,
                optimize=False,
                transparency=0,
            )
            created.append(str(gif_path))

    return folder, created


def scan_sources(src_root: Path) -> Dict[str, List[Path]]:
    result: Dict[str, List[Path]] = {k: [] for k in SRC_SUBFOLDERS}
    for key, sub in SRC_SUBFOLDERS.items():
        d = src_root / sub
        if d.exists():
            result[key] = sorted([p for p in d.glob("*.png") if p.is_file()])
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Create animated/static sprites from source frames")
    ap.add_argument("--src", default=DEFAULT_SRC_ROOT, help="Source root path containing Front/Back/etc")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    ap.add_argument("--only", nargs="*", default=None,
                    help="Only process these sprite sheet names (filename or stem, case-insensitive)."
                         " Example: LYCANROC_1.png GRENINJA_2.png or just LYCANROC_1 GRENINJA_2")
    ap.add_argument("--only-file", type=str, default=None,
                    help="Path to a text file with one name per line to process (filename or stem).")
    ap.add_argument("--limit", type=int, default=0, help="Process only first N per bucket (debug)")
    args = ap.parse_args()

    src_root = Path(args.src)
    if not src_root.exists():
        print(f"ERROR: Source root not found: {src_root}")
        sys.exit(1)

    buckets = scan_sources(src_root)
    total_created = 0
    report: List[Dict[str, object]] = []

    # Build allowlist if provided
    allow: Optional[set] = None
    if args.only_file:
        p = Path(args.only_file)
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                items = [ln.strip() for ln in f.readlines() if ln.strip()]
            allow = {it.lower().removesuffix('.png') for it in items}
    if args.only:
        allow = allow or set()
        for it in args.only:
            allow.add(it.lower().removesuffix('.png'))

    def maybe_limit(paths: List[Path]) -> List[Path]:
        return paths[: args.limit] if args.limit and args.limit > 0 else paths

    for bucket_key in ("front", "back", "front_shiny", "back_shiny"):
        files = buckets.get(bucket_key, [])
        # Allowlist filter
        if allow is not None:
            filtered: List[Path] = []
            for pth in files:
                stem_lower = pth.stem.lower()
                if stem_lower.endswith("_female"):
                    stem_lower = stem_lower[:-7]
                if stem_lower in allow or f"{stem_lower}.png" in allow:
                    filtered.append(pth)
            files = filtered
        files = maybe_limit(files)
        shiny = bucket_key.endswith("shiny")
        kind = "back" if bucket_key.startswith("back") else "front"
        for file in files:
            try:
                meta = parse_source_filename(file)
                folder, created = process_sheet(meta, kind=kind, shiny=shiny, overwrite=args.overwrite)
                if created:
                    total_created += len(created)
                    report.append({
                        "source": str(file),
                        "target_folder": folder,
                        "kind": bucket_key,
                        "created": created,
                    })
                    print(f"OK  {file.name} -> {folder} ({len(created)} files)")
                else:
                    print(f"SKIP {file.name} -> {folder} (exists)")
            except Exception as e:
                print(f"ERR {file.name}: {e}")

    # Write summary
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    summary_path = TARGET_ROOT / "sprite_creation_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nCreated {total_created} files. Summary -> {summary_path}")


if __name__ == "__main__":
    main()


