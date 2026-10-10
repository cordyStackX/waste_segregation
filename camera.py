import cv2
from ultralytics import YOLO

model = YOLO("runs/classify/runs/waste/experiment-3/weights/best.pt")
cap = cv2.VideoCapture(0)  # 0 = default webcam; try 1 if it doesn't open

if not cap.isOpened():
    raise SystemExit("Can't open camera. Try index 1, or check permissions.")

while True:
    ok, frame = cap.read()
    if not ok:
        break

    r = model.predict(frame, device=0, imgsz=224, verbose=False)[0]
    conf = float(r.probs.top1conf)
    label = r.names[r.probs.top1] if conf >= 0.6 else "unsure"

    cv2.putText(frame, f"{label} {conf:.0%}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
    cv2.imshow("Waste classifier (q to quit)", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()