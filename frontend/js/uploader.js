import { Utils } from './utils.js';
import { Modal } from './modal.js';
import { I18n } from './i18n.js';

export const Uploader = {
    init() {
        ['upload1', 'upload2'].forEach(id => {
            const zone = document.getElementById(id);
            const input = document.getElementById(id === 'upload1' ? 'file1' : 'file2');

            // 上传区是个 div，默认既不可聚焦也不响应键盘 —— 键盘用户在整个
            // 系统主流程（单张检测）里根本无法选择影像（WCAG 2.1.1 键盘可达，A 级）。
            // 补上 tabindex/role 与 Enter/Space 处理，行为与鼠标点击一致。
            zone.setAttribute('tabindex', '0');
            zone.setAttribute('role', 'button');
            zone.setAttribute('aria-label',
                (I18n && I18n.t && I18n.t(id === 'upload1' ? 'detect.t1Label' : 'detect.t2Label'))
                || (id === 'upload1' ? '选择 T1 影像' : '选择 T2 影像'));

            zone.onclick = () => input.click();
            zone.onkeydown = (e) => {
                if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
                    e.preventDefault();   // 空格默认会滚动页面
                    input.click();
                }
            };
            zone.ondragover = (e) => { e.preventDefault(); zone.classList.add('drag-over'); };
            zone.ondragleave = () => zone.classList.remove('drag-over');
            zone.ondrop = (e) => {
                e.preventDefault();
                zone.classList.remove('drag-over');
                if (e.dataTransfer.files.length) {
                    input.files = e.dataTransfer.files;
                    this.handleFileSelect(id === 'upload1' ? 1 : 2, input);
                }
            };
            input.onchange = () => this.handleFileSelect(id === 'upload1' ? 1 : 2, input);
        });
        this._initPaste();
    },

    /**
     * 在单张检测页支持直接 Ctrl/Cmd+V 粘贴截图。
     *
     * 只对「单张检测」页生效：批量检测与 Agent 的上传区各有自己的状态机，
     * 在全局 paste 里同时照顾三套逻辑只会让耦合变复杂，收益也不抵。
     * 粘贴目标取「第一个还空着的输入框」—— T1 空就填 T1，T1 有图就填 T2。
     */
    _initPaste() {
        document.addEventListener('paste', (e) => {
            const page = document.getElementById('page-single');
            if (!page || !page.classList.contains('active')) return;

            const items = e.clipboardData && e.clipboardData.items;
            if (!items) return;

            let blob = null;
            for (let i = 0; i < items.length; i++) {
                if (items[i].kind === 'file' && items[i].type.indexOf('image/') === 0) {
                    blob = items[i].getAsFile();
                    break;
                }
            }
            if (!blob) return;

            const target = ['file1', 'file2']
                .map((id) => document.getElementById(id))
                .find((inp) => inp && inp.files.length === 0);
            if (!target) {
                // 两张都满了：交给页面自己处理，不静默吞掉
                e.preventDefault();
                Modal.alert(I18n.t('detect.pasteFull', 'T1 与 T2 都已选择影像，请先移除一张再粘贴。'));
                return;
            }

            // 剪贴板的图片没有有意义的名字（多为 image.png），按 MIME 补一个，
            // 下游的格式校验看的是类型不是名字，但日志与列表里可读性更好。
            const ext = (blob.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
            const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
            const file = new File([blob], '粘贴影像-' + stamp + '.' + ext, { type: blob.type });

            const dt = new DataTransfer();
            dt.items.add(file);
            target.files = dt.files;
            this.handleFileSelect(target.id === 'file1' ? 1 : 2, target);
            e.preventDefault();
        });
    },

    handleFileSelect(num, input) {
        const file = input.files[0];
        if (!file) return;

        const validation = Utils.validateFile(file);
        if (!validation.valid) {
            Modal.alert(validation.msg);
            input.value = '';
            return;
        }

        const nameEl = document.getElementById(`f${num}name`);
        const imgEl = document.getElementById(`img${num}`);
        const zone = document.getElementById(`upload${num}`);

        nameEl.textContent = file.name;
        nameEl.classList.remove("hidden");
        if (zone) zone.classList.add('has-file');

        if (imgEl.src) Utils.releaseObjectURL(imgEl.src);
        Utils.createImagePreview(file).then(function(url) {
            imgEl.src = url;
            imgEl.classList.remove('hidden');
        });
    }
};