# 问题与改进台账

补录日期：2026-10-31。以下历史条目由现有结果、审查和验证记录回填，不虚构当时未记录的过程；每项链接到详细依据。后续继续追加同一问题的进展，不能把未验证方案改记为已完成。

状态“已修复/已验证”指对应记录的检查范围；模型/数据限制可以保持开放。每次任务按[保存流程](DOCUMENTATION_WORKFLOW.md)更新，并同步[当前交接](HANDOFF.md)。

## 识别、数据和模型效果

| ID | 问题 / 观察 | 已做改进及结果 | 状态 / 接续 | 证据 |
|---|---|---|---|---|
| PR-001 | 基线17个Top-1错误，铭文检测/转写覆盖不足；不能只靠相似封装确定型号 | 复核17例（非专家金标），保留框/视图证据；RapidOCR多视图使27/44→38/44 | 部分改善；仍需独立实物和更好拍摄 | [错误复核](research/2026-10-30-error-review.md)、[OCR验证](research/2026-10-30-verification.md) |
| PR-002 | 噪声文字与相关OCR分支会一起投错；增加票数不保证提高准确率 | 比较等票、家族票、RRF和门控；五路等票37/44，原RapidOCR38/44，早期门控组合40/44 | 已测出限制；新组合需冻结并独立验证 | [组合对照](../results/ensembles/comparison.md)、[组合验证](research/2026-10-30-ensemble-verification.md) |
| PR-003 | 仅靠OCR关键词会漏召回；正确类不在Top-10时受限VLM无法选中 | SQLite多关键词＋图像补充＋形状＋新池VLM：36/38/38/42正确（44图）；UA741、ULN2003两个余错仍未召回 | 遗留；召回与重排分别评估 | [SQLite比较](../results/candidates/comparison.md)、[流程说明](research/2026-10-31-sqlite-verification.md) |
| PR-004 | OCR误读可碰巧成为另一合法强别名，门控会提前接受错误 | 原44图门控41/44，低于全量VLM42/44；新三图组ATmega第一张接受ATMEGA8，联合VLM纠正为ATMEGA328P | 遗留；不要把别名分数当正确概率 | [公开三图逐组结果](research/2026-10-31-public-triplets-results.md) |
| PR-005 | 启发式形状在复杂背景/裁剪中经常不可用，也不能估真实尺寸或引脚数 | 原查询仅10/44有可用形状；公开三图24张仅1张可用；未知不按零分惩罚 | 已记录能力边界；更可靠形状另作消融 | [SQLite验证](research/2026-10-31-sqlite-verification.md)、[三图解释](research/2026-10-31-public-triplets-results.md) |
| PR-006 | 最初仅一个80286实物假设，难以评估多角度收益 | 补充公开分组至8组/24视图，7静态组＋1视频组；冻结身份/裁剪/顺序/许可并公布来源复用 | 部分改善；0组物主确认，仍非盲测/代表性样本 | [数据审计](research/2026-10-31-multi-image-data-audit.md)、[公开来源](../data/public_triplets/README.md) |
| PR-007 | 加照片后的融合也可能干扰名次 | 新集检索Top-1 6/8→6/8，Top-3 8/8→7/8；按需7/8→8/8，强制8/8→8/8；三种都更慢 | 已验证本批限制；保留退步，不外推总体收益 | [三图完整分析](research/2026-10-31-public-triplets-results.md)、[原始比较](../results/multi_image/comparison.md) |
| PR-008 | VLM即使选对类，解释仍可能错读批次、误数引脚、把参考图当查询 | 保留原判断/观察与可展开原文；网页标明解释局限；没有用生成解释修正GT | 遗留能力限制；需像素/实测/专家独立核对 | [三图模型解释问题](research/2026-10-31-public-triplets-results.md) |

## 软件、来源和显示问题

| ID | 问题 / 触发 | 改进和验证 | 状态 | 证据 |
|---|---|---|---|---|
| PR-009 | 不完整模型JSON或重复字段可能绕过不确定/弃权规则 | 严格结构/候选约束和重复键拒绝，失败保留原排序；回归覆盖 | 已修复并验证 | [初期代码审查及修复](research/2026-10-30-code-review.md) |
| PR-010 | 视觉缓存若未包含参考图像素会复用失效判断 | 缓存身份加入全部视觉输入及提示/模型指纹；真实多图评测使用新命名空间并记录cache_reused | 已修复并验证 | [缓存审查](research/2026-10-30-code-review.md)、[三图验证](research/2026-10-31-public-triplets-verification.md) |
| PR-011 | 实时OCR已有文字框却不能展示；切到照片2仍显示照片1标识符 | 保留几何并按当前图取OCR/框/ID依据，整组排名维持融合语义；消费者测试＋浏览器核查 | 已修复并验证 | [初期审查](research/2026-10-30-code-review.md)、[多图审查及修复](research/2026-10-31-multi-image-code-review.md) |
| PR-012 | 分阶段相加、门控回放估计和端到端时间曾显示为同类耗时 | 明示每种计时口径；新配对路径独立提取，实际VLM进程/加载计入，初始化单列 | 已修复显示；不同口径仍不可直接混比 | [计时审查](research/2026-10-30-code-review.md)、[SQLite计时说明](research/2026-10-31-sqlite-verification.md) |
| PR-013 | SQL有记录但0候选被当作缺记录；完整阶段未强制精确对齐44查询 | 分开记录存在与候选存在；拒绝缺/重/未知查询、标签错配；空候选算失败，部分checkpoint不冒充完整 | 已修复并验证 | [SQLite审查](research/2026-10-31-sqlite-code-review.md) |
| PR-014 | 运行/报告来源指纹未覆盖目录、DB、全部查询/参考等依赖 | 工厂及评测前后验证规范目录和完整数据指纹；发现变化拒绝复用 | 已修复并验证 | [来源审查](research/2026-10-31-sqlite-code-review.md) |
| PR-015 | 翻译未匹配实时形状错误原句；无预设数据时上传页语言未重绘 | 按真实后端消息建立三语映射；上传页独立重绘、错误重置与行为测试 | 已修复并验证 | [三语审查](research/2026-10-31-i18n-code-review.md) |
| PR-016 | 模型分析/复核笔记需随语言切换，但型号/OCR原文不能变；翻译也会漏/重复标记 | 源文精确缓存、保护标记和原文展开；148源/444条；新翻译2条结构失败后助手修订，另25条润色，均留模型草稿 | 已验证当前保存集；新实时分析需另验证 | [原翻译验证](research/2026-10-31-prose-translation-verification.md)、[新条目验证](research/2026-10-31-public-triplets-verification.md) |
| PR-017 | 保存结果只信scope，可能将探索组/重复控制改称确认实物 | scope与哈希manifest及精确分组绑定；控制组验证重复像素，目视推断不能提升为确认身份 | 已修复并验证 | [多图审查及修复](research/2026-10-31-multi-image-code-review.md) |
| PR-018 | 同一曝光的不同裁剪/缩放可能被计成3张独立拍摄；存在目录泄漏风险 | 校验裁剪/父图像素、拍摄ID、OriginalDocumentID、页面ID及目录参考；三次相同输入不增加独立票 | 已修复验证规则；物理身份仍需来源核实 | [多图审查](research/2026-10-31-multi-image-code-review.md)、[新增来源审查](research/2026-10-31-public-triplets-code-review.md) |
| PR-019 | 正在读取有效上传时收到非法批次，可能永久停在读取状态 | 原子性文件验证、读取序号和失败状态修复；可控异步FileReader回归 | 已修复并验证 | [多图审查及修复](research/2026-10-31-multi-image-code-review.md) |
| PR-020 | 按需视觉被标成强制视觉，且固定探索标签忽略确认scope | 保留force_visual/scope/实际执行字段；展示检索、按需、强制、控制、探索和确认的区别 | 已修复并验证 | [多图审查及修复](research/2026-10-31-multi-image-code-review.md) |
| PR-021 | `public_*.json`普通结果没有可选all-single字段时，报告发生KeyError | 详细公开段落只在cohort＋all_single_views均具备时生成；普通配对仍正常报告；先失败后修复 | 已修复并独立复查 | [公开集审查](research/2026-10-31-public-triplets-code-review.md) |
| PR-022 | 扩集后每次来源解码约2.6秒；初版缓存会漏掉哈希遗漏/符号链接改向 | 完整依赖覆盖；逐逻辑路径＋解析目标＋SHA256，验证前后再检查；暖读取约0.13秒；共享目标和验证中变更也独立复查 | 已修复并独立接受 | [缓存复查](research/2026-10-31-public-triplets-code-review.md)、[最终验证](research/2026-10-31-public-triplets-verification.md) |
| PR-023 | 早期研究仍写“尚无网页”；同名2Dto3D研究目录被误当作三维工程 | 本次补历史快照提示、总目录、接续文件和工程地图；读取实际三维README/代码及4组报告，不把旧V2建议当当前实现 | 本次文档修复；后续任务按流程维护 | [当前交接](HANDOFF.md)、[三维接续](RECONSTRUCTION_HANDOFF.md)、[保存约定](DOCUMENTATION_WORKFLOW.md) |

## 跨项目问题：转交三维工程追踪

这部分是只读核查后的对接，不在元件仓库宣称三维修复已经完成。三维原始照片、网格、点云、掩码和日志继续保存在其本地工程，当前活动分支由另一个聊天负责。

| 对接ID | 已观察问题 | 当前处理 / 验证要求 | 依据 |
|---|---|---|---|
| GEO-001 | 同一主机多视角未合成同一全局组件；观察数不能当实物数 | 三维聊天正在修复；同4组输入比较正确关联与错误合并，保留同视角不自动合并保护 | 下述本地原报告/关联指标 |
| GEO-002 | 细线有完整SAM区域，经过336网格、置信过滤、区域分配及体素仍大量丢点 | 按阶段审计点保留/误留和线连续性；不只增加总点数或盲目放松过滤 | 下述本地原报告及CSV |
| GEO-003 | 插接件误作支架，线槽/背景误作机壳；新增角度不改变逐图检测类别 | 三维聊天正在改进类别/候选；必须回归原4组及新增误检 | 下述原报告、issues.json |
| GEO-004 | 真实尺寸未知，schema仍只允许unknown尺度 | 待加入独立尺度依据与留出测量；几何质量未验证时不输出工程精度承诺 | [三维接续/测量方案](RECONSTRUCTION_HANDOFF.md) |

GEO-001至003原始证据统一位于 `/Users/caochao/Documents/2Dto3D/data/collections/sungrow/evaluation/runs/2026-10-31_v3_multiview_real_4groups/` 的 `report.md`、`issues.json`、`mask_point_audit.csv`及逐组产物。本地导航见研究工作区README；该目录按三维工程规则不随本仓库同步。4组共9张图，包含SH10RT早/晚安装状态，约3个候选实物；没有尺寸或人工gold真值。

## 追加进展模板

```markdown
### PR-xxx / GEO-xxx — YYYY-MM-DD 本次进展
- 现象与复现：
- 已证实原因 / 假设：
- 实际改动或失败尝试：
- 同输入前后结果及新增退步：
- 测试、模型实跑、浏览器检查范围：
- 详细记录 / 输入 / 输出 / 提交：
- 状态及下一步：
```
