# infer_engine.py
import torch
import os  # 这里补上 os
from PIL import Image
from torchvision import transforms
from core.config import CONFIG

transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

def infer_pair(t1_path, t2_path, model, device, log):
    try:
        img_t1 = Image.open(t1_path).convert("RGB").resize((CONFIG["img_size"], CONFIG["img_size"]), Image.BILINEAR)
        img_t2 = Image.open(t2_path).convert("RGB").resize((CONFIG["img_size"], CONFIG["img_size"]), Image.BILINEAR)

        t1 = transform(img_t1).unsqueeze(0).to(device)
        t2 = transform(img_t2).unsqueeze(0).to(device)

        batch = {
            'A': t1,
            'B': t2,
            'name': [os.path.basename(t1_path)],
            'ori_size': [img_t1.size]
        }

        with torch.no_grad():
            score_map = model._forward_pass(batch)
            model._save_predictions()

        log(f"✅ 成功: {os.path.basename(t1_path)}")
        return True

    except Exception as e:
        log(f"❌ 失败: {str(e)}")
        return False