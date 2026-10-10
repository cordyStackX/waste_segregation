import random, shutil, re
from pathlib import Path

src = Path("public")
dst = Path("dataset")
val_ratio = 0.2
exts = {".jpg", ".jpeg", ".png", ".webp"}
merge = {
    "plastic_bottles": "plastic",
    "food_scraps": "organic",
    "fruit_peels": "organic",
}
random.seed(0)

if dst.exists():
    shutil.rmtree(dst)

# collect images per final class
classes = {}
for group in [d for d in src.iterdir() if d.is_dir()]:
    for cls_dir in [d for d in group.iterdir() if d.is_dir()]:
        name = re.sub(r"\s+", "_", cls_dir.name.strip().lower())
        name = merge.get(name, name)
        imgs = [p for p in cls_dir.rglob("*") if p.suffix.lower() in exts]
        classes.setdefault(name, []).extend(imgs)

for name, imgs in classes.items():
    if len(imgs) < 10:
        print(f"skip {name} ({len(imgs)} images, too few)")
        continue
    random.shuffle(imgs)
    n_val = max(2, int(len(imgs) * val_ratio))
    for i, p in enumerate(imgs):
        split = "val" if i < n_val else "train"
        out = dst / split / name
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out / f"{p.parent.name}_{p.name}")
    print(f"{name}: {len(imgs)} images")