# config.py
CONFIG = {
    "project_name": "test",
    "gpu_ids": "0",
    "checkpoint_root": "checkpoints",
    "output_folder": "samples/predict",
    "num_workers": 0,
    "dataset": "CDDataset",
    "data_name": "SYSU",
    "batch_size": 1,
    "split": "test",
    "img_size": 256,
    "n_class": 2,
    "net_G": "base_transformer_pos_s4_dd8",
    "checkpoint_name": "best_ckpt.pt",
    "backbone": "resnet18"
}