"""Train the waste object detector after preparing detection_dataset/."""

from ultralytics import YOLO
from pathlib import Path


def main():
    model = YOLO("yolo11n.pt")
    model.train(
        data="detection_dataset/data.yaml",
        epochs=50,
        imgsz=640,
        batch=8,
        workers=2,
        device=0,
        project=str(Path("runs/detect").resolve()),
        name="waste_detailed",
    )


if __name__ == "__main__":
    main()
