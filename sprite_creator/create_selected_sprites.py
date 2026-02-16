"""
Create sprites only for the files you specify.

Inputs are the same sheet format as other tools (horizontal frame strips) and
the source folder layout:
  C:\\Users\\adama\\Downloads\\Animated Pokemon Sprites\\Animated Pokemon Sprites\\Graphics\\Pokemon
    Front/  Back/  Front shiny/  Back shiny/

Usage examples:
  python sprite_creator/create_selected_sprites.py --only LYCANROC_1 GRENINJA_2
  python sprite_creator/create_selected_sprites.py --only-file names.txt

Outputs are written to pvp/_common/sprites/<folder>/ with the standard names:
  animated-front.gif, front.png, animated-back.gif, back.png,
  animated-shiny-front.gif, shiny-front.png, animated-shiny-back.gif, shiny-back.png

This script never processes anything not explicitly listed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

try:
    import form_mapping  # type: ignore
except Exception:
    form_mapping = None


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
FPS = 12
LOOP = 0


def parse_name(stem: str) -> tuple[str, Optional[str], bool]:
    s = stem.lower()
    is_female = s.endswith("_female")
    if is_female:
        s = s[:-7]
    if "_" in s:
        base, num = s.rsplit("_", 1)
        if num.isdigit():
            return base.upper(), num, is_female
    return s.upper(), None, is_female


def resolve_folder(base_upper: str, form_number: Optional[str]) -> str:
    base = base_upper.lower()
    if base == "pikachu":
        return "pikachu"  # explicitly avoid regional mis-maps
    if form_mapping and hasattr(form_mapping, "get_form_folder_name"):
        key = base_upper if form_number is None else f"{base_upper}_{form_number}"
        try:
            mapped = form_mapping.get_form_folder_name(key)
            if mapped:
                return mapped
        except Exception:
            pass
    return base


def detect_and_split(im: Image.Image) -> List[Image.Image]:
    w, h = im.size
    # Prefer ratio-based (square frames)
    if h > 0 and w % h == 0:
        n = w // h
        if n >= 2:
            fw = h
            return [im.crop((i * fw, 0, (i + 1) * fw, h)) for i in range(n)]
    # Fallback to content-checked divisors
    best_n = 1
    for n in range(12, 1, -1):
        if w % n != 0:
            continue
        fw = w // n
        if list(im.crop((0, 0, fw, h)).getdata()) != list(im.crop(((n - 1) * fw, 0, n * fw, h)).getdata()):
            best_n = n
            break
    fw = w // best_n
    return [im.crop((i * fw, 0, (i + 1) * fw, h)) for i in range(best_n)]


def save_pair(frames: List[Image.Image], out_dir: Path, gif_name: str, png_name: str, overwrite: bool) -> List[str]:
    out: List[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    png_p = out_dir / f"{png_name}.png"
    gif_p = out_dir / f"{gif_name}.gif"
    if overwrite or not png_p.exists():
        # Save ONLY the first frame for static
        frames[0].save(png_p)
        out.append(str(png_p))
    if overwrite or not gif_p.exists():
        frames[0].save(gif_p, save_all=True, append_images=frames[1:], loop=LOOP, duration=int(1000 / FPS), disposal=2)
        out.append(str(gif_p))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Create sprites only for specified names")
    ap.add_argument("--src", default=DEFAULT_SRC_ROOT)
    ap.add_argument("--only", nargs="*", default=None, help="Names/stems or filenames (.png)")
    ap.add_argument("--only-file", type=str, default=None, help="Text file with one name per line")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    allow: set[str] = set()
    if args.only:
        for it in args.only:
            allow.add(Path(it).stem.lower())
    if args.only_file:
        p = Path(args.only_file)
        if p.exists():
            for ln in p.read_text(encoding="utf-8").splitlines():
                s = ln.strip()
                if s:
                    allow.add(Path(s).stem.lower())
    if not allow:
        print("Nothing to do: provide --only or --only-file")
        return

    src_root = Path(args.src)
    created_total = 0
    report: List[dict] = []

    touched_folders: set[str] = set()

    for bucket_key, sub in SRC_SUBFOLDERS.items():
        kind = "back" if bucket_key.startswith("back") else "front"
        shiny = bucket_key.endswith("shiny")
        for file in sorted((src_root / sub).glob("*.png")):
            stem = file.stem.lower()
            if stem.endswith("_female"):
                stem = stem[:-7]
            if stem not in allow:
                continue
            base_u, num, is_female = parse_name(file.stem)
            folder = resolve_folder(base_u, num)

            try:
                with Image.open(file).convert("RGBA") as im:
                    frames = detect_and_split(im)
            except Exception as e:
                print(f"ERR {file.name}: {e}")
                continue

            out_dir = TARGET_ROOT / folder
            touched_folders.add(folder)
            if kind == "front" and not shiny:
                made = save_pair(frames, out_dir, "animated-front", "front", args.overwrite)
            elif kind == "back" and not shiny:
                made = save_pair(frames, out_dir, "animated-back", "back", args.overwrite)
            elif kind == "front" and shiny:
                made = save_pair(frames, out_dir, "animated-shiny-front", "shiny-front", args.overwrite)
            else:
                made = save_pair(frames, out_dir, "animated-shiny-back", "shiny-back", args.overwrite)

            if made:
                report.append({
                    "source": str(file),
                    "folder": folder,
                    "bucket": bucket_key,
                    "created": made,
                })
                created_total += len(made)
                print(f"OK  {file.name} -> {folder} ({len(made)} files)")
            else:
                print(f"SKIP {file.name} -> {folder} (exists)")

    # Duplicate back sprites when shiny versions are missing (e.g., Ogerpon mask backs)
    import shutil
    for folder in touched_folders:
        out_dir = TARGET_ROOT / folder
        if not out_dir.is_dir():
            continue
        normal_static = out_dir / "back.png"
        shiny_static = out_dir / "shiny-back.png"
        if normal_static.exists() and not shiny_static.exists():
            shutil.copy2(normal_static, shiny_static)
            created_total += 1
        normal_anim = out_dir / "animated-back.gif"
        shiny_anim = out_dir / "animated-shiny-back.gif"
        if normal_anim.exists() and not shiny_anim.exists():
            shutil.copy2(normal_anim, shiny_anim)
            created_total += 1

    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    (TARGET_ROOT / "sprite_creation_selected.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Created {created_total} files. Summary -> {TARGET_ROOT / 'sprite_creation_selected.json'}")


if __name__ == "__main__":
    main()


