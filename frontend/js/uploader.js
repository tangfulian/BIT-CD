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