# gui.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import warnings
from PIL import Image, ImageTk

warnings.filterwarnings("ignore")

from core.config import CONFIG
from core.loader import init_model
from core.infer import infer_pair

# ---------------------- 全局变量 ----------------------
selected_t1_paths = []
selected_t2_paths = []
log_text = None
model = None
device = None

# 新增：模型权重路径
selected_ckpt_path = None

canvas_t1 = None
canvas_t2 = None
canvas_result = None

img_t1_ref = None
img_t2_ref = None
img_result_ref = None

PANEL_SIZE = 320

# ---------------------- 日志 ----------------------
def log(msg):
    if log_text:
        log_text.insert(tk.END, msg + "\n")
        log_text.see(tk.END)
        root.update_idletasks()

# ---------------------- 选择模型权重 ----------------------
def select_checkpoint():
    global selected_ckpt_path
    path = filedialog.askopenfilename(
        title="选择模型权重",
        filetypes=[("PyTorch 权重", "*.pt;*.pth"), ("所有文件", "*.*")]
    )
    if not path:
        return

    selected_ckpt_path = path
    # 显示在界面
    label_ckpt.config(text=f"当前权重：{os.path.basename(path)}")
    log(f"✅ 已选择模型：{os.path.basename(path)}")

# ---------------------- 核心修复：只更新传入的图，不传的保持不变 ----------------------
def show_images(t1_path=None, t2_path=None, res_path=None):
    global img_t1_ref, img_t2_ref, img_result_ref

    # 只在没有图的时候画占位背景
    def draw_placeholder(canvas, text):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, PANEL_SIZE, PANEL_SIZE, fill="#f5f5f5", outline="#ccc")
        canvas.create_text(PANEL_SIZE//2, PANEL_SIZE//2, text=text, font=("Arial", 14), fill="#666")

    # ====== 更新 T1 ======
    if t1_path is not None:
        if os.path.exists(t1_path):
            img = Image.open(t1_path).convert("RGB")
            img.thumbnail((PANEL_SIZE, PANEL_SIZE), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            canvas_t1.delete("all")
            x = (PANEL_SIZE - tk_img.width()) // 2
            y = (PANEL_SIZE - tk_img.height()) // 2
            canvas_t1.create_image(x, y, anchor=tk.NW, image=tk_img)
            img_t1_ref = tk_img
        else:
            draw_placeholder(canvas_t1, "T1 图像\n预览区域")
            img_t1_ref = None

    # ====== 更新 T2 ======
    if t2_path is not None:
        if os.path.exists(t2_path):
            img = Image.open(t2_path).convert("RGB")
            img.thumbnail((PANEL_SIZE, PANEL_SIZE), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            canvas_t2.delete("all")
            x = (PANEL_SIZE - tk_img.width()) // 2
            y = (PANEL_SIZE - tk_img.height()) // 2
            canvas_t2.create_image(x, y, anchor=tk.NW, image=tk_img)
            img_t2_ref = tk_img
        else:
            draw_placeholder(canvas_t2, "T2 图像\n预览区域")
            img_t2_ref = None

    # ====== 更新 结果 ======
    if res_path is not None:
        if os.path.exists(res_path):
            img = Image.open(res_path).convert("RGB")
            img.thumbnail((PANEL_SIZE, PANEL_SIZE), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            canvas_result.delete("all")
            x = (PANEL_SIZE - tk_img.width()) // 2
            y = (PANEL_SIZE - tk_img.height()) // 2
            canvas_result.create_image(x, y, anchor=tk.NW, image=tk_img)
            img_result_ref = tk_img
        else:
            draw_placeholder(canvas_result, "变化结果\n预览区域")
            img_result_ref = None

# ---------------------- 选择 T1 ----------------------
def select_t1():
    global selected_t1_paths
    paths = filedialog.askopenfilenames(
        filetypes=[("图像", "*.png;*.jpg;*.jpeg;*.tiff;*.bmp"), ("所有", "*.*")]
    )
    if not paths:
        return

    selected_t1_paths = list(paths)
    list_t1.delete(0, tk.END)
    for p in selected_t1_paths:
        list_t1.insert(tk.END, os.path.basename(p))

    log(f"📂 选中 T1：{len(selected_t1_paths)} 张")
    if selected_t1_paths:
        show_images(t1_path=selected_t1_paths[0])

# ---------------------- 选择 T2 ----------------------
def select_t2():
    global selected_t2_paths
    paths = filedialog.askopenfilenames(
        filetypes=[("图像", "*.png;*.jpg;*.jpeg;*.tiff;*.bmp"), ("所有", "*.*")]
    )
    if not paths:
        return

    selected_t2_paths = list(paths)
    list_t2.delete(0, tk.END)
    for p in selected_t2_paths:
        list_t2.insert(tk.END, os.path.basename(p))

    log(f"📂 选中 T2：{len(selected_t2_paths)} 张")
    if selected_t2_paths:
        show_images(t2_path=selected_t2_paths[0])

# ---------------------- 点击列表切换 ----------------------
def on_list_click(event):
    try:
        idx = list_t1.curselection()[0]
        if 0 <= idx < len(selected_t1_paths) and 0 <= idx < len(selected_t2_paths):
            t1 = selected_t1_paths[idx]
            t2 = selected_t2_paths[idx]
            name = os.path.splitext(os.path.basename(t1))[0]
            res = os.path.join(CONFIG["output_folder"], f"{name}.png")
            show_images(t1_path=t1, t2_path=t2, res_path=res)
    except IndexError:
        return

# ---------------------- 清空 ----------------------
def clear_selection():
    global selected_t1_paths, selected_t2_paths
    selected_t1_paths = []
    selected_t2_paths = []
    list_t1.delete(0, tk.END)
    list_t2.delete(0, tk.END)
    show_images(t1_path="", t2_path="", res_path="")
    log("🗑️ 已清空所有选择")

# ---------------------- 打开结果目录 ----------------------
def open_output_folder():
    path = os.path.abspath(CONFIG["output_folder"])
    if os.path.exists(path):
        os.startfile(path)
    else:
        messagebox.showinfo("提示", "请先完成推理生成结果")

# ---------------------- 批量推理 ----------------------
def batch_infer():
    global model, device

    if not selected_ckpt_path:
        messagebox.showwarning("提示", "请先选择模型权重！")
        return

    if not selected_t1_paths or not selected_t2_paths:
        messagebox.showwarning("提示", "请先选择 T1 和 T2 图像！")
        return

    if len(selected_t1_paths) != len(selected_t2_paths):
        messagebox.showwarning("错误", "T1 和 T2 图像数量必须一致")
        return

    btn_infer.config(state=tk.DISABLED)
    log("\n" + "="*60)
    log("🚀 开始批量推理...")
    log(f"📦 使用模型：{os.path.basename(selected_ckpt_path)}")
    log("="*60)

    def run():
        # 加载选中的权重
        global model, device
        model, device = init_model(log, ckpt_path=selected_ckpt_path)

        total = len(selected_t1_paths)
        for i, (t1, t2) in enumerate(zip(selected_t1_paths, selected_t2_paths)):
            log(f"\n[{i+1}/{total}] 处理：{os.path.basename(t1)}")
            infer_pair(t1, t2, model, device, log)

        log("\n" + "="*60)
        log("🎉 推理完成！")
        log(f"📍 结果保存至：{CONFIG['output_folder']}")
        log("="*60)

        btn_infer.config(state=tk.NORMAL)

        if selected_t1_paths:
            name = os.path.splitext(os.path.basename(selected_t1_paths[0]))[0]
            res_path = os.path.join(CONFIG["output_folder"], f"{name}.png")
            show_images(t1_path=selected_t1_paths[0],
                        t2_path=selected_t2_paths[0],
                        res_path=res_path)

        messagebox.showinfo("完成", "✅ 全部图像推理完成！")

    threading.Thread(target=run, daemon=True).start()

# ---------------------- 界面 ----------------------
def create_gui():
    global root, btn_infer, list_t1, list_t2, log_text, label_ckpt
    global canvas_t1, canvas_t2, canvas_result

    root = tk.Tk()
    root.title("SYSU-CD 双时序变化检测可视化工具")
    root.geometry("1400x850")
    root.resizable(False, False)

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - 1400) // 2
    y = (screen_height - 850) // 2
    root.geometry(f"1400x850+{x}+{y}")

    # 顶部按钮
    frame_top = ttk.Frame(root)
    frame_top.pack(pady=10, fill=tk.X, padx=20)

    # ========== 新增：选择模型权重按钮 ==========
    btn_ckpt = ttk.Button(frame_top, text="📦 选择模型权重", command=select_checkpoint, width=20)
    btn_ckpt.pack(side=tk.LEFT, padx=5)

    btn_select_t1 = ttk.Button(frame_top, text="📁 选择 T1 图像", command=select_t1, width=20)
    btn_select_t2 = ttk.Button(frame_top, text="📁 选择 T2 图像", command=select_t2, width=20)
    btn_clear = ttk.Button(frame_top, text="🗑️ 清空选择", command=clear_selection, width=18)
    btn_infer = ttk.Button(frame_top, text="🚀 开始推理", command=batch_infer, width=18)
    btn_open = ttk.Button(frame_top, text="📂 打开结果目录", command=open_output_folder, width=20)

    btn_select_t1.pack(side=tk.LEFT, padx=5)
    btn_select_t2.pack(side=tk.LEFT, padx=5)
    btn_clear.pack(side=tk.LEFT, padx=5)
    btn_infer.pack(side=tk.LEFT, padx=5)
    btn_open.pack(side=tk.LEFT, padx=5)

    # 显示当前权重
    label_ckpt = ttk.Label(root, text="当前权重：未选择", font=("Arial", 10))
    label_ckpt.pack(anchor=tk.W, padx=25, pady=2)

    # 图像面板
    frame_img = ttk.Frame(root)
    frame_img.pack(pady=15, padx=20, fill=tk.BOTH, expand=True)

    ttk.Label(frame_img, text="T1 时相图像", font="bold 12").grid(row=0, column=0, padx=10, pady=5)
    ttk.Label(frame_img, text="T2 时相图像", font="bold 12").grid(row=0, column=1, padx=10, pady=5)
    ttk.Label(frame_img, text="变化检测结果", font="bold 12").grid(row=0, column=2, padx=10, pady=5)

    canvas_t1 = tk.Canvas(frame_img, width=PANEL_SIZE, height=PANEL_SIZE, bg="#f5f5f5", relief="solid", bd=1)
    canvas_t2 = tk.Canvas(frame_img, width=PANEL_SIZE, height=PANEL_SIZE, bg="#f5f5f5", relief="solid", bd=1)
    canvas_result = tk.Canvas(frame_img, width=PANEL_SIZE, height=PANEL_SIZE, bg="#f5f5f5", relief="solid", bd=1)

    canvas_t1.grid(row=1, column=0, padx=10, pady=5)
    canvas_t2.grid(row=1, column=1, padx=10, pady=5)
    canvas_result.grid(row=1, column=2, padx=10, pady=5)

    # 列表
    frame_list = ttk.Frame(root)
    frame_list.pack(pady=10, fill=tk.BOTH, expand=True, padx=20)

    ttk.Label(frame_list, text="T1 图像列表", font="bold 11").grid(row=0, column=0, sticky="w")
    list_t1 = tk.Listbox(frame_list, width=50, height=8, font=("Arial", 10))
    list_t1.grid(row=1, column=0, padx=10, sticky=tk.NSEW)
    list_t1.bind("<<ListboxSelect>>", on_list_click)

    ttk.Label(frame_list, text="T2 图像列表", font="bold 11").grid(row=0, column=1, sticky="w")
    list_t2 = tk.Listbox(frame_list, width=50, height=8, font=("Arial", 10))
    list_t2.grid(row=1, column=1, padx=10, sticky=tk.NSEW)

    frame_list.columnconfigure(0, weight=1)
    frame_list.columnconfigure(1, weight=1)

    # 日志
    frame_log = ttk.Frame(root)
    frame_log.pack(pady=10, fill=tk.BOTH, expand=True, padx=20)
    ttk.Label(frame_log, text="运行日志", font="bold 11").pack(anchor=tk.W)
    log_text = scrolledtext.ScrolledText(frame_log, height=12, font=("Consolas", 10))
    log_text.pack(fill=tk.BOTH, expand=True, pady=5)

    # 初始化占位
    show_images(t1_path="", t2_path="", res_path="")

    root.mainloop()

if __name__ == "__main__":
    create_gui()