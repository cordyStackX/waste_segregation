from ultralytics import YOLO

def main():
    model = YOLO("yolo11n-cls.pt")
    model.train(
        data="dataset",
        epochs=30,
        imgsz=224,
        batch=16,
        workers=2,
        device=0,
        project="runs/waste",
        name="experiment",
    )

if __name__ == "__main__":
    main()