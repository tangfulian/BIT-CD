import torch
import os
from argparse import Namespace
from core.config import CONFIG

model = None
device = None

# ====================== 修改点：增加 ckpt_path 参数 ======================
def init_model(log, ckpt_path=None):
    global model, device
    try:
        from core import utils
        args = Namespace(**CONFIG)
        utils.get_device(args)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        args.device = device

        args.checkpoint_dir = os.path.join(args.checkpoint_root, args.project_name)
        os.makedirs(args.output_folder, exist_ok=True)

        from models.basic_model import CDEvaluator
        model = CDEvaluator(args)

        # ====================== 核心修改 ======================
        if ckpt_path is not None:
            # 使用 GUI 选择的自定义权重
            log(f"📦 加载自定义权重：{os.path.basename(ckpt_path)}")
            model.load_checkpoint(ckpt_path)  # 直接传入路径
        else:
            # 使用默认配置权重
            log(f"📦 加载配置文件默认权重")
            model.load_checkpoint(args.checkpoint_name)

        model.eval()

        log("✅ 模型初始化成功！")
        log(f"🔧 使用设备: {device}")
        log(f"🔧 模型: {args.net_G} | 尺寸: {args.img_size}x{args.img_size}")
        log(f"🔧 结果保存: {args.output_folder}\n")
        return model, device

    except Exception as e:
        log(f"❌ 模型加载失败: {str(e)}")
        return None, None