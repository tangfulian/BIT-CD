import { CONFIG } from './config.js';
import { Utils } from './utils.js';

function _absUrl(url) {
    if (!url || url.startsWith('http') || url.startsWith('blob:') || url.startsWith('data:')) return url;
    return (CONFIG.API_BASE_URL + '/' + url.replace(/^\//, '')).replace(/([^:]);$/, '$1');
}

export const ReportGenerator = {
    async generateSingleReport(detectResult) {
        const { jsPDF } = window.jspdf;
        if (!jsPDF) {
            console.error('jsPDF 未加载');
            return;
        }

        // 使用隐藏的报告容器渲染 HTML（包含中文）
        const container = document.getElementById('reportContainer');
        if (!container) return;

        // 构建报告 HTML（用 div 布局，包含所有图片和 AI 解读）
        container.innerHTML = `
            <div style="font-family: 'Inter', 'Microsoft YaHei', sans-serif; line-height: 1.8; color: #333; padding: 20px;">
                <h1 style="text-align:center; color:#1e293b; margin-bottom:20px;">黑土地变化检测报告</h1>
                <table style="width:100%; border-collapse: collapse; margin-bottom:20px; font-size:14px;">
                    <tr><td style="padding:4px 8px;"><strong>地块位置</strong></td><td>${detectResult.location || '未填写'}</td></tr>
                    <tr><td style="padding:4px 8px;"><strong>变化类型</strong></td><td>${detectResult.change_type || '未知'}</td></tr>
                    <tr><td style="padding:4px 8px;"><strong>检测模型</strong></td><td>${detectResult.model || 'BIT'}</td></tr>
                    <tr><td style="padding:4px 8px;"><strong>变化比例</strong></td><td>${detectResult.change_area_ratio}%</td></tr>
                    <tr><td style="padding:4px 8px;"><strong>变化像素</strong></td><td>${detectResult.change_pixel} / ${detectResult.total_pixel}</td></tr>
                    ${detectResult.actual_area != null ? `<tr><td style="padding:4px 8px;"><strong>实际变化面积</strong></td><td>${detectResult.actual_area} 亩</td></tr>` : ''}
                    <tr><td style="padding:4px 8px;"><strong>置信度阈值</strong></td><td>${detectResult.threshold}</td></tr>
                    <tr><td style="padding:4px 8px;"><strong>影像时间</strong></td><td>${detectResult.t1_time} → ${detectResult.t2_time}</td></tr>
                </table>

                <h3 style="color:#1e293b;">检测结果图片</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom:20px;">
                    ${detectResult.t1_url ? `<div><p>T1 时相</p><img src="${_absUrl(detectResult.t1_url)}" style="width:100%; border:1px solid #e2e8f0;" crossorigin="anonymous"/></div>` : ''}
                    ${detectResult.t2_url ? `<div><p>T2 时相</p><img src="${_absUrl(detectResult.t2_url)}" style="width:100%; border:1px solid #e2e8f0;" crossorigin="anonymous"/></div>` : ''}
                    ${detectResult.mask_url ? `<div><p>变化掩膜</p><img src="${_absUrl(detectResult.mask_url)}" style="width:100%; border:1px solid #e2e8f0;" crossorigin="anonymous"/></div>` : ''}
                    ${detectResult.heat_url ? `<div><p>热力图</p><img src="${_absUrl(detectResult.heat_url)}" style="width:100%; border:1px solid #e2e8f0;" crossorigin="anonymous"/></div>` : ''}
                    ${detectResult.fusion_url ? `<div><p>叠加图</p><img src="${_absUrl(detectResult.fusion_url)}" style="width:100%; border:1px solid #e2e8f0;" crossorigin="anonymous"/></div>` : ''}
                </div>

                ${detectResult.ai_analysis ? `
                    <h3 style="color:#1e293b; margin-top:20px;">AI 专业解读</h3>
                    <p style="white-space: pre-wrap; font-size:14px;">${detectResult.ai_analysis}</p>
                ` : ''}
            </div>
        `;

        // 等待图片加载
        const images = container.querySelectorAll('img');
        const loadPromises = Array.from(images).map(img => {
            return new Promise((resolve) => {
                if (img.complete) resolve();
                else {
                    img.onload = resolve;
                    img.onerror = resolve;
                }
            });
        });
        await Promise.all(loadPromises);

        // 使用 html2canvas 截图
        if (typeof html2canvas === 'undefined') {
            console.error('html2canvas 未加载');
            return;
        }
        const canvas = await html2canvas(container, {
            scale: 2,
            useCORS: true,
            logging: false,
            backgroundColor: '#ffffff'
        });

        const imgData = canvas.toDataURL('image/png');

        // 生成 PDF（A4 纵向）
        const doc = new jsPDF('p', 'mm', 'a4');
        const pageWidth = doc.internal.pageSize.getWidth();
        const pageHeight = doc.internal.pageSize.getHeight();
        const imgWidth = pageWidth - 20;       // 左右留白 10mm
        const imgHeight = (canvas.height * imgWidth) / canvas.width;

        let heightLeft = imgHeight;
        let position = 10;

        // 添加第一页
        doc.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight);
        heightLeft -= (pageHeight - 20);

        // 如果内容超过一页，循环添加
        while (heightLeft > 0) {
            position = -(imgHeight - (pageHeight - 20));   // 计算偏移量让内容接上
            doc.addPage();
            doc.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight);
            heightLeft -= (pageHeight - 20);
        }

        doc.save(`黑土地检测报告_${new Date().toISOString().slice(0, 10)}.pdf`);

        // 清空临时容器
        container.innerHTML = '';
    },

    /**
     * 导出一份外部拼好的报告 HTML 为 PDF（灾害定损测算单等）。
     *
     * footer 刻意用 doc.text 逐页盖章，而不是写进 HTML：上面的分页是把同一张
     * 长图反复平移叠加实现的，写进 HTML 的免责声明只会在正文里出现一次，
     * 翻到第二页的人根本看不到。而定损单的免责声明必须每页都在。
     *
     * @param {string} html     完整报告 HTML（自带样式与字体声明）
     * @param {string} filename
     * @param {string} [footer] 每页底部固定文字
     */
    async generateDisasterReport(html, filename, footer) {
        const container = document.getElementById('reportContainer');
        if (!container) return;
        container.innerHTML = html;

        const images = container.querySelectorAll('img');
        await Promise.all(Array.from(images).map(img => new Promise((resolve) => {
            if (img.complete) resolve();
            else { img.onload = resolve; img.onerror = resolve; }
        })));

        if (typeof html2canvas === 'undefined') {
            console.error('html2canvas 未加载');
            return;
        }
        const canvas = await html2canvas(container, {
            scale: 2, useCORS: true, logging: false, backgroundColor: '#ffffff'
        });
        const imgData = canvas.toDataURL('image/png');

        const { jsPDF } = window.jspdf;
        const doc = new jsPDF('p', 'mm', 'a4');
        const pageWidth = doc.internal.pageSize.getWidth();
        const pageHeight = doc.internal.pageSize.getHeight();
        const imgWidth = pageWidth - 20;
        const imgHeight = (canvas.height * imgWidth) / canvas.width;

        let heightLeft = imgHeight;
        let position = 10;
        doc.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight);
        heightLeft -= (pageHeight - 20);
        while (heightLeft > 0) {
            position = -(imgHeight - (pageHeight - 20));
            doc.addPage();
            doc.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight);
            heightLeft -= (pageHeight - 20);
        }

        if (footer) {
            const pages = doc.internal.getNumberOfPages();
            for (let i = 1; i <= pages; i++) {
                doc.setPage(i);
                doc.setFontSize(8);
                doc.setTextColor(196, 69, 54);
                doc.text(footer, 10, pageHeight - 6);
            }
        }

        doc.save(filename);
        container.innerHTML = '';
    },

    async generateBatchReport(batchResults) {
        const { jsPDF } = window.jspdf;
        if (!jsPDF) {
            console.error('jsPDF 未加载');
            return;
        }
        const container = document.getElementById('reportContainer');
        if (!container || batchResults.length === 0) return;

        const completed = batchResults.filter(r => r.status === 'done' || r.status === '完成');
        const avgRatio = completed.length > 0
            ? (completed.reduce((s, r) => s + (r.ratio || 0), 0) / completed.length).toFixed(2)
            : '0';
        const models = [...new Set(completed.map(r => r.model))].join('、');

        // 封面页
        container.innerHTML = `
            <div style="font-family: 'Inter', 'Microsoft YaHei', sans-serif; line-height: 1.8; color: #333; padding: 60px 20px; text-align: center;">
                <h1 style="color:#1b4332; margin-bottom:8px; font-size:28px;">黑土地变化检测报告</h1>
                <p style="color:#475569; font-size:14px; margin-bottom:40px;">BATCH DETECTION REPORT</p>
                <div style="background:#f1f8f4; border-radius:12px; padding:30px; display:inline-block; text-align:left; min-width:300px;">
                    <p style="margin:8px 0;"><strong>检测总数：</strong>${batchResults.length} 组</p>
                    <p style="margin:8px 0;"><strong>成功完成：</strong>${completed.length} 组</p>
                    <p style="margin:8px 0;"><strong>平均变化率：</strong>${avgRatio}%</p>
                    <p style="margin:8px 0;"><strong>使用模型：</strong>${models || 'N/A'}</p>
                    <p style="margin:8px 0;"><strong>导出时间：</strong>${new Date().toLocaleString('zh-CN')}</p>
                </div>
            </div>
        `;

        const coverCanvas = await html2canvas(container.querySelector('div'), {
            scale: 2, useCORS: true, logging: false, backgroundColor: '#ffffff'
        });
        const coverImg = coverCanvas.toDataURL('image/png');

        const doc = new jsPDF('p', 'mm', 'a4');
        const pageWidth = doc.internal.pageSize.getWidth();
        const pageHeight = doc.internal.pageSize.getHeight();
        const imgWidth = pageWidth - 20;

        // 封面
        let imgH = (coverCanvas.height * imgWidth) / coverCanvas.width;
        doc.addImage(coverImg, 'PNG', 10, 10, imgWidth, Math.min(imgH, pageHeight - 20));

        // 每一条结果页
        for (let i = 0; i < completed.length; i++) {
            const r = completed[i];
            container.innerHTML = `
                <div style="font-family: 'Inter', 'Microsoft YaHei', sans-serif; line-height: 1.6; color: #333; padding: 15px;">
                    <h2 style="text-align:center; color:#1e293b; font-size:18px; margin-bottom:10px;">#${i + 1} ${r.name || '检测结果'}</h2>
                    <table style="width:100%; border-collapse:collapse; font-size:13px; margin-bottom:10px;">
                        <tr><td style="padding:3px 6px;"><strong>变化率</strong></td><td>${r.ratio}%</td><td><strong>模型</strong></td><td>${r.model}</td></tr>
                        ${r.actualArea != null ? `<tr><td style="padding:3px 6px;"><strong>实际变化面积</strong></td><td colspan="3">${r.actualArea} 亩</td></tr>` : ''}
                        <tr><td style="padding:3px 6px;"><strong>变化像素</strong></td><td>${r.changePixel} / ${r.totalPixel}</td><td><strong>阈值</strong></td><td>${r.threshold}</td></tr>
                        <tr><td style="padding:3px 6px;"><strong>耗时</strong></td><td colspan="3">${r.time || 'N/A'}</td></tr>
                    </table>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                        ${r.maskUrl ? `<img src="${_absUrl(r.maskUrl)}" style="width:100%; border:1px solid #e2e8f0;" crossorigin="anonymous"/>` : ''}
                        ${r.heatUrl ? `<img src="${_absUrl(r.heatUrl)}" style="width:100%; border:1px solid #e2e8f0;" crossorigin="anonymous"/>` : ''}
                    </div>
                </div>
            `;

            const imgs = container.querySelectorAll('img');
            await Promise.all(Array.from(imgs).map(img => new Promise(resolve => {
                if (img.complete) resolve(); else { img.onload = resolve; img.onerror = resolve; }
            })));

            const canvas = await html2canvas(container.querySelector('div'), {
                scale: 2, useCORS: true, logging: false, backgroundColor: '#ffffff'
            });
            const imgData = canvas.toDataURL('image/png');
            imgH = (canvas.height * imgWidth) / canvas.width;

            doc.addPage();
            let hLeft = imgH, position = 10;
            doc.addImage(imgData, 'PNG', 10, position, imgWidth, imgH);
            hLeft -= (pageHeight - 20);
            while (hLeft > 0) {
                position = -(imgH - (pageHeight - 20));
                doc.addPage();
                doc.addImage(imgData, 'PNG', 10, position, imgWidth, imgH);
                hLeft -= (pageHeight - 20);
            }
        }

        doc.save(`黑土地批量检测报告_${new Date().toISOString().slice(0, 10)}.pdf`);
        container.innerHTML = '';
    }
};