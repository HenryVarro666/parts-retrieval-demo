# GitHub OCR 仓库调研与本地实验选择

调研日期：2026-10-30（America/Chicago）。GitHub 元数据抓取于 **2026-10-31 03:08:39 UTC / 2026-10-30 22:08:39 CDT**；后续源码、PyPI 和模型卡核验在同次会话完成。仓库元数据通过已连接 GitHub 的 GET API 取得；包与模型信息来自 PyPI/Hugging Face 官方 API、维护者 README、源码及论文。这里只记录研究和拟议接口，没有安装、下载模型权重、执行推理或产生新的准确率结果。

## 1. 哪些高关注仓库值得比较

### Takeaway

应借鉴场景文字 OCR 的检测、矫正、裁剪与识别管线，再把通用视觉模型用于候选核验。文档 VLM 的页级解析成绩与元件铭文转写、精确型号检索是不同任务。Star 数只表示社区关注，不是本任务的性能排序。

### Cited Findings

以下 `stars` 是该时刻 GitHub API 的 `stargazers_count`，不是网页取整显示。`pushed_at` 仅作仓库有更新的证据，不代表最近一次 OCR 算法更新。

| 官方仓库 | stars / 元数据来源 | 最近 release 或维护证据 | 代码许可 | 模型权重许可须单独看 |
|---|---:|---|---|---|
| [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | **92,008** · [API](https://api.github.com/repos/PaddlePaddle/PaddleOCR) | [v3.7.0](https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.7.0)，2026-06-11；pushed 2026-09-16 | Apache-2.0 | 官方 PP-OCRv6 small [det](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det) / [rec](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec) 卡均标 Apache-2.0；不由此推断所有历史 checkpoint |
| [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) | **77,257** · [API](https://api.github.com/repos/tesseract-ocr/tesseract) | [5.5.4](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.4)，2026-10-28 | Apache-2.0 | 官方 [tessdata_fast LICENSE](https://github.com/tesseract-ocr/tessdata_fast/blob/main/LICENSE) 为 Apache-2.0；其他 traineddata 另查 |
| [JaidedAI/EasyOCR](https://github.com/JaidedAI/EasyOCR) | **30,127** · [API](https://api.github.com/repos/JaidedAI/EasyOCR) | [v1.7.2](https://github.com/JaidedAI/EasyOCR/releases/tag/v1.7.2)，2024-09-24；pushed 2025-12-05 | Apache-2.0 | [README](https://github.com/JaidedAI/EasyOCR/blob/master/README.md) 指向模型 hub，并说明使用 CRAFT 预训练模型；本次未逐个核验 checkpoint 单独许可 |
| [deepseek-ai/DeepSeek-OCR](https://github.com/deepseek-ai/DeepSeek-OCR) | **24,100** · [API](https://api.github.com/repos/deepseek-ai/DeepSeek-OCR) | GitHub releases 为空；[README](https://github.com/deepseek-ai/DeepSeek-OCR/blob/main/README.md) 记录 2025-10-20 发布和 2026-01-27 OCR2 后继工作 | [MIT](https://github.com/deepseek-ai/DeepSeek-OCR/blob/main/LICENSE) | 官方 [模型卡](https://huggingface.co/deepseek-ai/DeepSeek-OCR) / [API](https://huggingface.co/api/models/deepseek-ai/DeepSeek-OCR) 标 MIT |
| [datalab-to/surya](https://github.com/datalab-to/surya) | **21,564** · [API](https://api.github.com/repos/datalab-to/surya) | [v0.23.0 / Surya 2.5](https://github.com/datalab-to/surya/releases/tag/v0.23.0)，2026-10-29 | Apache-2.0 | [README](https://github.com/datalab-to/surya/blob/master/README.md) 明确权重为修改版 AI Pubs Open Rail-M；研究、个人及一定规模以下企业条件与代码许可不同 |
| [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) | **8,393** · [API](https://api.github.com/repos/RapidAI/RapidOCR) | [v3.10.0](https://github.com/RapidAI/RapidOCR/releases/tag/v3.10.0)，2026-10-08；pushed 2026-10-30 | Apache-2.0 | 固定版本 [MODEL_LICENSES.md](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/MODEL_LICENSES.md) 将代码与 PaddleOCR 来源权重区分，并声明所列模型均 Apache-2.0 |
| [Ucas-HaoranWei/GOT-OCR2.0](https://github.com/Ucas-HaoranWei/GOT-OCR2.0) | **8,226** · [API](https://api.github.com/repos/Ucas-HaoranWei/GOT-OCR2.0) | releases 为空；pushed 2025-02-10；[README](https://github.com/Ucas-HaoranWei/GOT-OCR2.0/blob/main/README.md) 记录 2025-02-01 Transformers 集成 | README 徽章称 Apache-2.0，但链接指向其他项目；本仓库 API license=null，未找到 LICENSE，故不视为已完整核验 | 官方 [HF API](https://huggingface.co/api/models/stepfun-ai/GOT-OCR2_0) 明确 metadata 为 Apache-2.0；不要把 README 的 data-license 徽章误当权重许可 |
| [mindee/doctr](https://github.com/mindee/doctr) | **6,404** · [API](https://api.github.com/repos/mindee/doctr) | [v1.1.0](https://github.com/mindee/doctr/releases/tag/v1.1.0)，2026-08-21；pushed 2026-10-30 | [Apache-2.0](https://github.com/mindee/doctr/blob/main/LICENSE) | 本次未逐个验证预训练下载产物的单独声明；代码许可不作为权重来源证明 |

动态名称重新核验：**PP-OCRv6 确实存在**，不只来自搜索摘要；官方 release API 的 `published_at=2026-06-11T12:09:14Z`，release body 明确发布 PP-OCRv6。[官方 release](https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.7.0) 此前提及的 `gemini-3.8-flash` 也能在 [Google 官方模型页](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) 核验，但本轮选择本地路径，不依赖云模型。

### Inferences

- 优先采用 **RapidOCR 的 ONNX 工程路径 + PaddleOCR 的 scene-text 模型**，可以减少 macOS 上 Paddle/MPS 安装分歧，同时保持检测与识别可分别检查。
- 暂不优先引入 Surya / DeepSeek-OCR 的完整文档解析栈；它们对版面、表格、阅读顺序的能力不直接对应当前细小铭文问题。

### Gaps

本表没有运行统一元件照片基准，也不是所有 GitHub OCR 仓库的穷尽排名。许可栏只记录维护者声明与核验缺口，不把代码许可自动扩展到所有权重、数据与依赖。

## 2. 它们怎么实现，哪些做法适合小元件铭文

### Takeaway

最值得借鉴的是把错误定位到“文字检测 → 方向/透视矫正 → 字符识别 → 型号匹配”，并保留每一阶段的框、原文与分数。整张图一次推理后只保留字符串，会丢掉很多诊断信息。

### Cited Findings

| 仓库 | 实现路线与主要来源 | 对小元件铭文的适配判断（本研究推断） | 本项目可借鉴的具体方法 |
|---|---|---|---|
| PaddleOCR | PP-OCRv6 用 LCNetV4、检测 neck RepLKFPN、识别 neck LightSVTR；small 检测器 2.48M、识别器 5.2M 参数。[det 卡](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det)、[rec 卡](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec) | 工业文字方向较相关；官方多场景分数不代表元件最终型号准确率 | 分别检查检测框与 crop 识别结果；先测 small，后决定是否需要 medium；与 PaddleOCR-VL 的文档解析路线分开 |
| EasyOCR | CRAFT 检测 + CRNN，包含卷积特征、LSTM 和 CTC。[实现说明](https://github.com/JaidedAI/EasyOCR/blob/master/README.md) | 合适的已有基线；模型较旧不等于所有失败需换模型 | 已有 [API 源码](https://github.com/JaidedAI/EasyOCR/blob/v1.7.2/easyocr/easyocr.py) 支持 rotation_info、mag_ratio、contrast_ths、allowlist、不同 decoder；可先独立消融这些参数 |
| Tesseract | LSTM 行识别，另保留 legacy engine。[README](https://github.com/tesseract-ocr/tesseract/blob/main/README.md) | 预先裁切成清晰单行时有价值；随意拍摄的小散字难度更大 | 用标准化 ROI 做单行基线；把版面模式和图像前处理显式记录，不只比较引擎名称 |
| RapidOCR | PaddleOCR 模型转为 ONNX，管线执行检测、旋转裁剪、方向分类、识别与原图坐标映射。[README](https://github.com/RapidAI/RapidOCR/blob/main/README.md)、[固定版本 main.py](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/main.py) | 本轮最易形成可复现 CPU 对照的选择；质量仍依赖实际模型与输入 | 使用内置检测框进行 crop；固定模型路由与 SHA256；输出 boxes/txts/scores；开启单字符框时再核验其含义 |
| docTR | 两阶段检测/识别，支持 DBNet/FAST 和 CRNN/PARSeq/ViTSTR 等组合；可返回旋转框。[README](https://github.com/mindee/doctr/blob/main/README.md) | 可研究不同 recognizer 对铭文的影响，后续对照价值较高 | 保持同一 crop，替换识别器；把模型组合与旋转框设置记录为实验配置，避免一次同时换所有环节 |
| GOT-OCR2.0 | 高压缩视觉 encoder + 长上下文 decoder；支持区域/颜色提示、动态分辨率与 multi-crop；论文称 580M。[论文](https://arxiv.org/abs/2409.01704)、[官方 README](https://github.com/Ucas-HaoranWei/GOT-OCR2.0/blob/main/README.md) | 能处理 scene/document，但页级/复杂格式输出并非本任务主要需求；原仓库安装以 CUDA/FlashAttention 为主 | 借鉴 ROI 指定与 multi-crop 的试验设计；不把论文参数口径等同实际完整权重文件参数量 |
| DeepSeek-OCR | 视觉 token 压缩 + 自回归生成；支持多种固定尺寸和动态多 crop；官方示例依赖 CUDA、FlashAttention/vLLM。[README](https://github.com/deepseek-ai/DeepSeek-OCR/blob/main/README.md) | 文档压缩能力不保证细小字符保真；本轮 Mac 集成成本较高 | 借鉴固定分辨率与动态 crop 的明确配置、重复生成抑制；避免无记录地把整图压缩到很小 |
| Surya 2.5 | 当前 README 描述 689M 文档 OCR 模型，布局/HTML 输出，另有检测/错误检测模型；新版本提供实验 MLX 后端。[README](https://github.com/datalab-to/surya/blob/master/README.md) | 文档模型可作后续探索，当前流程和权重许可比新专用 OCR 更复杂 | 借鉴结构化位置输出、检测 heatmap 与 OCR 错误检测；不把页吞吐当小元件单图延迟 |

### Inferences

建议保留 4 个独立实验条件：

1. **已有 EasyOCR 原样**，作固定基线。
2. **RapidOCR 全图**，仅更换引擎/模型，保持原有型号匹配和融合。
3. **RapidOCR + ROI / 旋转处理**，单独测前处理收益。不同旋转应合并为一条 query 的证据，不能当独立测试样本。
4. **固定 Top10 + 本地视觉重排**，与 OCR 升级分开。记录正确答案是否进入 Top10；候选缺失不能归咎重排器。

应留存检测框、最终实际送入模型的 crop、OCR 原文、各旋转输出、模型分数、型号匹配候选与最终排序。对疑似 O/0、I/1 的位置允许多个候选；不能先用真值把字符纠正，再当作模型进步。模型自报置信度也不等于经验证的概率。

### Gaps

没有本项目新引擎的 accuracy/latency 数据。旋转、对比度、放大、ROI 都是应控制的实验变量，不能预设每种前处理必然提高准确率。

## 3. 本轮建议安装什么，如何接入

### Takeaway

OCR 首选 **RapidOCR 3.10.0 + ONNX Runtime CPU**。视觉重排首选 **MLX-VLM + Qwen3-VL-4B-Instruct 4bit**；小一些的 2B 可作降档。24GB M4 Pro 是否满足目标延迟，须实际运行记录，不从权重大小推导实时表现。

### Cited Findings

**OCR 版本、模型与接口。** [PyPI rapidocr](https://pypi.org/project/rapidocr/3.10.0/) 确有 3.10.0（2026-10-08）；[PyPI onnxruntime](https://pypi.org/project/onnxruntime/1.31.1/) 确有 1.31.1（2026-10-26），其发布文件有 CPython 3.12 / macOS 14 ARM64 wheel。建议作为本机候选 pin，仍需实际 smoke test：

```sh
pip install rapidocr==3.10.0 onnxruntime==1.31.1
```

[v3.10.0 固定配置](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/config.yaml) 确认默认 Det/Rec 为 `PP-OCRv6` / `small` / `onnxruntime`，Cls 为 PP-OCRv4 的 0/180° 分类器。90/270° 全图尝试不能假称该分类器已经覆盖。

[固定模型路由](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml) 给出默认 ONNX 产物的预期 hash：

| 模型 key | SHA256 |
|---|---|
| `multi_PP-OCRv6_det_small` | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| `multi_PP-OCRv6_rec_small` | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |

Paddle 官方 ONNX 文件树给出的体积约为检测 **9.88MB**、识别 **21.16MB**，另有分类器/字典/配置；这不等同于安装包总大小或内存占用。[det 文件树 API](https://huggingface.co/api/models/PaddlePaddle/PP-OCRv6_small_det_onnx/tree/main)、[rec 文件树 API](https://huggingface.co/api/models/PaddlePaddle/PP-OCRv6_small_rec_onnx/tree/main)

按 [RapidOCR 输出类](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/utils/output.py) 与 [调用接口](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/main.py)：

```python
from rapidocr import RapidOCR

engine = RapidOCR()
result = engine("query.jpg")
# 空结果时这些字段可能为 None。
print(result.txts, result.boxes, result.scores)
```

**本地视觉模型。** 官方转换仓可验证到以下固定 revision、许可 metadata 和文件体积；转换 checkpoint 来自 mlx-community，基础模型来自 Qwen 官方，两者不是同一个发布主体。[4B 模型卡](https://huggingface.co/mlx-community/Qwen3-VL-4B-Instruct-4bit)、[2B 模型卡](https://huggingface.co/mlx-community/Qwen3-VL-2B-Instruct-4bit)、[Qwen 官方模型卡](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct)

| 候选 | 固定 HF revision | 单个模型权重文件大小 | 声明许可 |
|---|---|---:|---|
| `mlx-community/Qwen3-VL-4B-Instruct-4bit` | `2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b` | 3,093,767,283 bytes，约 3.09GB；另加 tokenizer/config | Apache-2.0 |
| `mlx-community/Qwen3-VL-2B-Instruct-4bit` | `9c4f5209e57b31f4b9dfba735de3fb983739c9cc` | 1,782,040,921 bytes，约 1.78GB；另加 tokenizer/config | Apache-2.0 |

体积来源：[4B API](https://huggingface.co/api/models/mlx-community/Qwen3-VL-4B-Instruct-4bit/tree/main)、[2B API](https://huggingface.co/api/models/mlx-community/Qwen3-VL-2B-Instruct-4bit/tree/main)；revision 来源各自模型 API。转换卡均说明由 mlx-vlm 转换并给出带 `--image` 的调用方式。[固定 4B 卡](https://huggingface.co/mlx-community/Qwen3-VL-4B-Instruct-4bit/blob/2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b/README.md)

[mlx-vlm 0.7.11](https://pypi.org/project/mlx-vlm/0.7.11/) 确有发布（2026-10-28）；它依赖较新的 Transformers，因此建议隔离环境避免改动原评测依赖。[固定 v0.7.11 README](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.11/README.md) 提供 `load`、`apply_chat_template`、`generate` 和多图路径列表接口。

```sh
pip install mlx-vlm==0.7.11
```

以下是基于维护者接口的集成草案，**本研究没有执行**。固定下载 revision 后把本地目录交给 loader，可避免版本漂移与 loader 参数差异：

```python
from huggingface_hub import snapshot_download
from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template

model_path = snapshot_download(
    "mlx-community/Qwen3-VL-4B-Instruct-4bit",
    revision="2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b",
)
model, processor = load(model_path)
images = ["query.jpg", "top10_contact_sheet.jpg"]
prompt_text = "Compare image 1 with labeled candidates in image 2 and the catalog below."
formatted = apply_chat_template(
    processor, model.config, prompt_text, num_images=len(images)
)
output = generate(
    model, processor, formatted,
    image=images, max_tokens=256, temperature=0.0, verbose=False,
    max_pixels=1048576, min_pixels=65536,
)
print(output.text)
```

`generate` 返回结果对象，其文本字段是 `.text`，不能未经核对就把整个对象当字符串。上述每图像素预算是拟议的受控起点，不是该模型的最优设置或实测值；在这一版 MLX 的 BaseImageProcessor 路径，单用 `resize_shape` 可能被忽略，应检查处理器实际尺寸。[固定 generate 实现](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.11/mlx_vlm/generate.py)、[固定 utils 实现](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.11/mlx_vlm/utils.py)

### Inferences

- Top10 视觉核验输入可固定为 query 原图 + 1 张带候选 ID 的 contact sheet + 目录文本；输出只允许这些 ID 或 unknown，并返回简短的可见证据。不要传入正确标签，不让模型自己扩展到不存在的库存型号。
- 拼图可能缩小铭文：须保存拼图、记录实际 resize/像素配置；若任务主要依赖字符，query 应保留独立原图/ROI，不能只喂缩小拼图。
- 先做全量固定候选的重排消融，再讨论仅在低置信时触发的策略；否则无法分辨模型能力与触发策略收益。
- 24GB M4 Pro 首先顺序处理、短输出、复用已加载模型，避免与其他大模型同时占用内存。权重约 3GB 不能直接推出总内存、p95 延迟或“肯定实时”。
- 使用 CPU ONNX 是明确的兼容路径；不能把它称为 MPS 加速。RapidOCR 有可选 CoreML/Torch MPS 配置，也应独立测试后才报告启用。

### Gaps

以上 pin、模型下载 ID 和源码接口已网络核验；本机安装成功、模型加载成功、JSON 输出遵循程度、Top10 视觉重排增益及端到端耗时仍待实际实验。任何后续实测结果应另存，避免覆盖本调研的“研究未运行”状态。
