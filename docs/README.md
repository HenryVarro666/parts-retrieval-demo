# 文档总目录

当前状态从[交接入口](HANDOFF.md)开始；历史问题从[问题与改进台账](ISSUES_AND_IMPROVEMENTS.md)查找。每次新问题、失败尝试和改进按[保存流程与模板](DOCUMENTATION_WORKFLOW.md)记录。

## 先读这几项

- [当前交接与未解决事项](HANDOFF.md)：工程边界、最近验证版本、下一步。
- [问题与改进台账](ISSUES_AND_IMPROVEMENTS.md)：已补录PR-001至PR-023及GEO对接项，链接到原始审查/结果。
- [文档保存与交接约定](DOCUMENTATION_WORKFLOW.md)：从发现到验证、同步的必要记录。
- [点云与真实尺寸接续](RECONSTRUCTION_HANDOFF.md)：三维工程实际已到V3，后续修复和尺度验证路线。
- [公开三图实测结论](research/2026-10-31-public-triplets-results.md)及[交付验证](research/2026-10-31-public-triplets-verification.md)。

## 数据与运行入口

- [仓库README](../README.md)：安装、网页、模型环境和各阶段实验。
- [多图使用与自建清单](MULTI_IMAGE_GUIDE.md)。
- [公开三图来源、许可与冻结清单](../data/public_triplets/README.md)。
- [多图完整比较](../results/multi_image/comparison.md)、[SQLite阶段比较](../results/candidates/comparison.md)、[早期组合比较](../results/ensembles/comparison.md)。

## 历史记录如何阅读

2026-10-30/31同一天包含多轮实验。旧报告的样本数、测试数和模型选择只对应其记录的提交/输入，不代表当前全局状态。保留旧结论与失败证据，当前快照在HANDOFF；方案不等于已实现，测试通过不等于领域准确率。

## 设计、计划与审查索引

### 设计规格

- [OCR and VLM combination experiment](superpowers/specs/2026-10-30-ensemble-design.md)
- [OCR experiments and evidence demo](superpowers/specs/2026-10-30-ocr-rerank-demo.md)
- [同一元件多图识别](superpowers/specs/2026-10-31-multi-image.md)
- [SQLite keyword candidates, shape evidence and visual verification](superpowers/specs/2026-10-31-sqlite-candidates.md)

### 实施计划

- [OCR/VLM combination implementation plan](superpowers/plans/2026-10-30-ensemble.md)
- [OCR experiments and evidence demo implementation plan](superpowers/plans/2026-10-30-ocr-rerank-demo.md)
- [Multi-image identification implementation plan](superpowers/plans/2026-10-31-multi-image.md)
- [Public same-object triplet expansion](superpowers/plans/2026-10-31-public-triplets.md)
- [SQLite candidate pipeline implementation plan](superpowers/plans/2026-10-31-sqlite-candidates.md)

### 研究、审查与验证

- [本轮文档补录与跨项目交接](research/2026-10-31-documentation-handoff.md)
- [OCR, frozen Top-10 VLM and evidence workbench review](research/2026-10-30-code-review.md)
- [OCR/VLM ensemble review · 2026-10-30](research/2026-10-30-ensemble-code-review.md)
- [Ensemble and private-repository verification](research/2026-10-30-ensemble-verification.md)
- [17 个 EasyOCR 错误样例的视觉复核](research/2026-10-30-error-review.md)
- [GitHub OCR 仓库调研与本地实验选择](research/2026-10-30-github-ocr-survey.md)
- [Integration notes: retained OCR evidence and local VLM](research/2026-10-30-integration-notes.md)
- [Implementation verification, 2026-10-30](research/2026-10-30-verification.md)
- [Three-language UI code review](research/2026-10-31-i18n-code-review.md)
- [Chinese, English and Spanish UI verification](research/2026-10-31-i18n-verification.md)
- [Independent multi-image branch review](research/2026-10-31-multi-image-code-review.md)
- [data/ 中的同一实物多图核对](research/2026-10-31-multi-image-data-audit.md)
- [多图融合交付验证 — 2026-10-31](research/2026-10-31-multi-image-verification.md)
- [Analysis and review-prose translation review](research/2026-10-31-prose-translation-review.md)
- [Model analysis and review-note translation verification](research/2026-10-31-prose-translation-verification.md)
- [Independent review: public same-object triplets](research/2026-10-31-public-triplets-code-review.md)
- [公开三图扩展实测 — 2026-10-31](research/2026-10-31-public-triplets-results.md)
- [公开三图扩展交付验证 — 2026-10-31](research/2026-10-31-public-triplets-verification.md)
- [SQLite candidate pipeline code review](research/2026-10-31-sqlite-code-review.md)
- [SQLite candidate pipeline verification, 2026-10-31](research/2026-10-31-sqlite-verification.md)

