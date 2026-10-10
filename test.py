import sys
from ultralytics import YOLO

model = YOLO("runs/classify/runs/waste/experiment-3/weights/best.pt")

for path in sys.argv[1:]:
    r = model.predict(path, device=0, verbose=False)[0]
    print(f"\n{path}")
    for i in r.probs.data.argsort(descending=True).tolist():
        print(f"  {r.names[i]:10s} {float(r.probs.data[i]):.1%}")