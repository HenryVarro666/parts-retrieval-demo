# README 配图：来源与复现

[中文](../../README.md) / [English](../../README.en.md) 使用原创说明图及真实本地浏览器截图。没有生成或修改UI来伪造结果；没有在本轮重跑识别模型。

| 资产 | 内容与范围 |
|---|---|
| `workbench.zh.jpg` / `workbench.en.jpg` | `public_gated.json` 的 `public-06` MC68000保存回放，第一张原图/选定OCR视图、文字框、三图缩略图及逐图SQL依据。未调用新模型，不是现场验证 |
| `multi-experiments.zh.jpg` / `multi-experiments.en.jpg` | 网页原生截图，显示公开三图表的前部：8组/24视图、来源复用说明、前三策略Top-1/Top-3/Recall及耗时。完整表继续向下/横向滚动 |
| `workflow.zh.svg` / `workflow.en.svg` | 原创：逐图OCR、SQLite/外观、形状/RRF、可选视觉核验 |
| `architecture.zh.svg` / `architecture.en.svg` | 原创：网页、本地标准库服务、冻结公开数据与独立可选MLX环境 |

## 照片署名

工作台截图里的查询照片和三张缩略图来自 **Evan-Amos** 的 Super A'Can 主板系列，原页面的 **Public domain (PD-self source declaration)**，裁剪方式和源像素/哈希记录在本仓库公开清单。网页上还叠加了OCR文字框及语言标签。

- [Super-Acan-Motherboard-01.jpg](https://commons.wikimedia.org/wiki/File:Super-Acan-Motherboard-01.jpg)
- [Super-Acan-Motherboard-02.jpg](https://commons.wikimedia.org/wiki/File:Super-Acan-Motherboard-02.jpg)
- [Super-Acan-Motherboard-03.jpg](https://commons.wikimedia.org/wiki/File:Super-Acan-Motherboard-03.jpg)

完整作者、来源、保存和裁剪记录：[public_triplets说明](../../data/public_triplets/README.md)、`selection.json`、`manifest.json`。Public domain不是CC0声明。截图没有目录参考照片缩略图、私人上传图、账号、路径或EXIF。其他实验图片各自许可继续适用，不能从这三张照片外推许可。

## 更新方法

```bash
python3 scripts/readme_figures.py
python3 scripts/readme_figures.py --check
uv run --frozen --extra experiments python -I -m partsid.web --port 8765
```

浏览器打开网页，在“单图/三图实验”的按需视觉公开组选择MC68000。等主图加载完成并核对来源/文字，分别切中/英截图。回放使用的单图1.17秒与三图3.43秒是保存结果，不是截图时新测得的延迟。默认浏览器视口约1280×720；JPEG实际像素可能随滚动条略有变化。

SVG由标准库再生成，无脚本或外部资源。修改生成器后重新生成并检查两种语言的排版。更换截图样例必须同步作者/许可、回放身份与[本轮验证记录](../research/2026-10-31-bilingual-readmes.md)，不能只替换图片。
