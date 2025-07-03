import json
import os.path

import onnx
from ultralytics import YOLO

BASE_PATH = os.path.join(os.getcwd(), '../', "model")

for filename in os.listdir(BASE_PATH):
    if filename.endswith(".pt"):
        file_path = os.path.join(BASE_PATH, filename)
        print(f"Loading model: {file_path}")
        model = YOLO(file_path)

        # 获取模型导出前的关键信息
        model_name = os.path.splitext(filename)[0]
        imgsz = model.overrides.get("imgsz", 640)
        conf = getattr(model, "conf", 0.25)
        iou = getattr(model, "iou", 0.45)
        model.export(format="onnx", dynamic=True)
        # 写入元信息到 JSON 文件
        model = onnx.load(os.path.join(BASE_PATH, f"{model_name}.onnx"))
        meta = {p.key: p.value for p in model.metadata_props}
        # meta_info = {
        #     "model_name": model_name,
        #     "imgsz": imgsz,
        #     "conf_threshold": conf,
        #     "iou_threshold": iou,
        #     "export_format": "onnx"
        # }
        print(meta)
        print(model.graph.output)
        meta_path = os.path.join(BASE_PATH, f"{model_name}_meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=4)
        print(f"Exported {model_name}.onnx and {model_name}_meta.json")