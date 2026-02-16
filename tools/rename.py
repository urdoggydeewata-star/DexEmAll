import os
from pathlib import Path

# path to your item_icons folder
ICON_DIR = Path("C:/Users/adama/OneDrive/Bureau/myuu clone/assets/item_icons")

def rename_icons():
    for file in ICON_DIR.glob("*.png"):
        new_name = file.name.replace("-", "_")
        if new_name != file.name:
            new_path = file.with_name(new_name)
            print(f"Renaming: {file.name} -> {new_name}")
            os.rename(file, new_path)

if __name__ == "__main__":
    rename_icons()
    print("✅ Done renaming icons.")