/**
 * 模型清单的**唯一**来源（结构部分）。
 *
 * 此前这套清单在前端被手抄了 6 份（主检测下拉 / 对比复选框 / 批量下拉 /
 * 历史筛选 / 评估复选框 / evaluator 的兜底数组），而展示名已经在各处漂开：
 *
 *   BIT            「BIT 变化检测模型（推荐）」/「BIT 变化检测模型」/ 裸「BIT」
 *   DIFF           「传统差分模型（基准对比）」/「传统差分模型」/「传统差分」/ 裸「DIFF」
 *   AFCF3D         「AFCF3D-Net 3D卷积模型」/ 裸「AFCF3D」
 *   BIT_LuojiaSET  「BIT LuojiaSET（珞珈数据集）」/ 裸「BIT_LuojiaSET」
 *
 * 同一个模型在四个页面叫四个名字，用户没法判断它们是不是同一个东西；而
 * 「基准方法」与 locale 里的「基础方法」还各写各的。更要命的是这些文本都没有
 * data-i18n，切到英文后整片仍是中文。
 *
 * 所以：**本文件只放结构**（有哪些模型、顺序、是 AI 还是基准），
 * **文案一律走 locale 的 model.<VALUE>.label**，展示由下面的填充函数统一渲染。
 *
 * 与后端的关系：GET /detect/models 的 available 决定**能不能用**（权重是否部署），
 * 本表决定**怎么展示**。两者职责不同，不要拿一个替代另一个 —— 接口拿不到时
 * 仍要能渲染出完整的清单（evaluator 的兜底数组就是为此存在的）。
 */
import { I18n } from './i18n.js';
import { eventBus } from './eventBus.js';

export const MODELS = [
    { value: 'BIT', kind: 'ai' },
    { value: 'DIFF', kind: 'baseline' },
    { value: 'AFCF3D', kind: 'ai' },
    { value: 'BIT_LuojiaSET', kind: 'ai' },
];

export const MODEL_VALUES = MODELS.map((m) => m.value);

export function modelLabel(value) {
    // 拿不到 locale 时退回 value 本身，不要显示成 model.BIT.label 这种原始键
    return I18n.t('model.' + value + '.label', value);
}

export function tagLabel(kind) {
    return I18n.t(kind === 'baseline' ? 'modelCompare.basicMethod' : 'modelCompare.aiModel');
}

/** 只换 option，保留 <select> 元素本身与用户当前的选择。 */
export function fillModelSelect(select) {
    if (!select) return;
    const keep = select.value;
    select.innerHTML = '';
    MODELS.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m.value;
        opt.textContent = modelLabel(m.value);
        select.appendChild(opt);
    });
    if (keep && MODEL_VALUES.indexOf(keep) !== -1) select.value = keep;
}

/**
 * 填一组复选框。
 *
 * 只动自己这一类（.className 所在的 label），不碰容器里的其它内容 ——
 * 对比区那个容器里还有一个说明用的 <span>。
 *
 * **已经渲染过就只更新文案，不替换元素。** 复选框本身的显示文本就是模型名
 * （语言无关），随语言变的只有后面那个标签（AI模型 / 基础方法）。整体重建会
 * 把调用方绑在复选框上的 onchange 一起丢掉 —— Detector 靠它保存设置，
 * 表现为切完语言再改勾选就不保存了。
 */
export function fillModelChecks(container, opts) {
    if (!container) return;
    const className = opts.className;
    const existing = Array.from(container.querySelectorAll('.' + className));

    const sameShape =
        existing.length === MODELS.length &&
        existing.every((cb, i) => cb.value === MODELS[i].value);

    if (sameShape) {
        if (opts.withTag) {
            MODELS.forEach((m, i) => {
                const label = existing[i].closest('label');
                const small = label && label.querySelector('small');
                if (small) {
                    small.textContent = tagLabel(m.kind);
                    small.className = m.kind === 'baseline' ? 'model-tag-basic' : 'model-tag-ai';
                }
            });
        }
        return;
    }

    // 首次渲染：建元素。
    // 「一个都没勾」也是合法状态，所以判断是不是首渲染看的是元素在不在，
    // 不是「当前勾选是否为空」。
    const checked = new Set(opts.checkedValues || []);
    existing.forEach((cb) => {
        const label = cb.closest('label');
        (label || cb).remove();
    });

    MODELS.forEach((m) => {
        const label = document.createElement('label');
        label.className = 'model-check-label';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = className;
        cb.value = m.value;
        if (checked.has(m.value)) cb.checked = true;
        label.appendChild(cb);
        label.appendChild(document.createTextNode(' ' + m.value + ' '));
        if (opts.withTag) {
            const small = document.createElement('small');
            small.className = m.kind === 'baseline' ? 'model-tag-basic' : 'model-tag-ai';
            small.textContent = tagLabel(m.kind);
            label.appendChild(small);
        }
        container.appendChild(label);
    });
}

/** 上一次渲染时用的语言，用来判断 lang-change 是不是真的换了语言。 */
let _renderedLocale = null;

/** 渲染所有出现模型清单的界面。幂等，可在语言切换后重复调用。 */
export function renderModelUIs() {
    _renderedLocale = I18n.getLocale();
    fillModelSelect(document.getElementById('model_type'));
    fillModelSelect(document.getElementById('batch_model'));
    fillModelChecks(document.getElementById('modelCompareCheckboxes'), {
        className: 'model-compare-check',
        checkedValues: ['BIT'],   // 对比区默认只勾 BIT
        withTag: true,
    });
    fillModelChecks(document.getElementById('evalModelChecks'), {
        className: 'eval-model-check',
        checkedValues: MODEL_VALUES,   // 评估区默认全勾
    });
}

export const ModelRegistry = {
    init() {
        renderModelUIs();
        // 模型名此前不随语言变化（没有 data-i18n）。文案搬进 locale 之后，
        // 切语言必须重渲染一遍，否则这一块会停在旧语言。
        //
        // 但**只在语言真的变了时才重渲染**：I18n.init() 内部会调 setLocale()，
        // 而 setLocale 无条件 emit 'lang-change' —— 那一次发生在模型控件已经
        // 渲染、且 Detector 已经把 onchange 绑好之后。无条件重渲染会把元素整个
        // 换掉，绑定随之丢失（表现为：改完勾选再刷新，勾选状态没被保存）。
        eventBus.on('lang-change', () => {
            if (I18n.getLocale() !== _renderedLocale) renderModelUIs();
        });
    },
};
