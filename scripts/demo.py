from argparse import ArgumentParser
import logging
from core import utils
import torch
from models.basic_model import CDEvaluator
import os

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    parser = ArgumentParser()

    # ===================== 👇 这里全部改成你的 SYSU 配置 👇 =====================
    parser.add_argument('--project_name', default='test', type=str)  # 你的训练文件夹名
    parser.add_argument('--gpu_ids', type=str, default='0', help="cuda:0")
    parser.add_argument('--checkpoint_root', default='checkpoints', type=str)
    parser.add_argument('--output_folder', default='predict', type=str)

    parser.add_argument('--num_workers', default=0, type=int)
    parser.add_argument('--dataset', default='CDDataset', type=str)
    parser.add_argument('--data_name', default='SYSU', type=str)  # 改成 SYSU

    parser.add_argument('--batch_size', default=1, type=int)
    parser.add_argument('--split', default="test", type=str)  # 测试集
    parser.add_argument('--img_size', default=256, type=int)

    parser.add_argument('--n_class', default=2, type=int)
    parser.add_argument('--net_G', default='base_transformer_pos_s4_dd8', type=str)  # 你的模型结构
    parser.add_argument('--checkpoint_name', default='best_ckpt.pt', type=str)
    parser.add_argument('--backbone', default='resnet18', type=str,
                        help='resnet18 | resnet34 | resnet50 | resnet101')
    # ==========================================================================

    args = parser.parse_args()

    # 设备配置
    utils.get_device(args)
    device = torch.device("cuda")
    args.checkpoint_dir = os.path.join(args.checkpoint_root, args.project_name)
    os.makedirs(args.output_folder, exist_ok=True)

    # 加载测试数据
    data_loader = utils.get_loader(
        args.data_name,
        img_size=args.img_size,
        batch_size=args.batch_size,
        split=args.split,
        is_train=False,
    )

    # 加载模型
    model = CDEvaluator(args)
    model.load_checkpoint(args.checkpoint_name)
    model.eval()

    logger.info("开始推理 SYSU-CD 测试集图片...")

    for i, batch in enumerate(data_loader):
        name = batch['name']
        logger.info("处理成功：%s", name[0])
        score_map = model._forward_pass(batch)
        model._save_predictions()

    logger.info("全部推理完成 — 结果保存在 samples/predict/")