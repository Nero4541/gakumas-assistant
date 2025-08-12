from ultralytics import YOLO

# Load a model
model = YOLO("yolo11n.pt")  # load a pretrained model (recommended for training)

# Train the model with the two most idle GPUs
results = model.train(
    epochs=150,
    batch=70,
    workers=8,
    data="data.yaml",
    device=[0,1],
    imgsz=640,
    multi_scale=True,
    # amp=False,
    hsv_h=0.015,
    hsv_s=0.5,
    hsv_v=0.5
)
