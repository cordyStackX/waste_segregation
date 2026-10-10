import random, shutil, re
from pathlib import Path

src = Path("public")
dst = Path("dataset")
MODE = "group"        # "group" = 3 classes, "leaf" = detailed classes (cans, plastic, ...)
val_ratio = 0.2
exts = {".jpg", ".jpeg", ".png", ".webp"}

# captured frames: folder name under public/captured/ -> group
captured_map = {
    "plastic": "non_biodegradable",
    "cans": "non_biodegradable",
    "glass": "non_biodegradable",
    "paper": "non_biodegradable",
    "organic": "biodegradable",
    "residual": "residual_special_waste",
}
merge = {"plastic_bottles": "plastic", "food_scraps": "organic", "fruit_peels": "organic"}  # leaf mode only
random.seed(0)

def images(folder):
    return [p for p in folder.rglob("*") if p.suffix.lower() in exts]

items = {}
def add(label, paths):
    items.setdefault(label, []).extend(paths)

for group in [d for d in src.iterdir() if d.is_dir()]:
    if group.name == "captured":
        for leaf in [d for d in group.iterdir() if d.is_dir()]:
            g = captured_map.get(leaf.name.lower())
            if g is None:
                print(f"skip captured/{leaf.name} (not in captured_map)")
                continue
            add(g if MODE == "group" else leaf.name.lower(), images(leaf))
    elif MODE == "group":
        add(group.name, images(group))          # includes loose images in the group folder
    else:
        for leaf in [d for d in group.iterdir() if d.is_dir()]:
            name = re.sub(r"\s+", "_", leaf.name.strip().lower())
            add(merge.get(name, name), images(leaf))

if dst.exists():
    shutil.rmtree(dst)

for label, imgs in items.items():
    if len(imgs) < 10:
        print(f"skip {label} ({len(imgs)} images, too few)")
        continue
    random.shuffle(imgs)
    n_val = max(2, int(len(imgs) * val_ratio))
    for i, p in enumerate(imgs):
        split = "val" if i < n_val else "train"
        out = dst / split / label
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out / f"{p.parent.name}_{p.name}")
    print(f"{label}: {len(imgs)} images")