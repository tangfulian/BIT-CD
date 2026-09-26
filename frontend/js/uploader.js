import { Utils } from './utils.js';
import { Modal } from './modal.js';

export const Uploader = {
    init() {
        ['upload1', 'upload2'].forEach(id => {
            const zone = document.getElementById(id);
            const input = document.getElementById(id === 'upload1' ? 'file1' : 'file2');

            zone.onclick = () => input.click();
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