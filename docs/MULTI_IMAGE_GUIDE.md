# 同一元件多图使用与复现实验

## 网页怎么用

1. 在仓库目录执行 `uv sync --frozen --extra experiments`，再运行 `uv run --frozen --extra experiments python -I -m partsid.web --port 8765`。打开 http://127.0.0.1:8765/。
2. 选“上传图片”，一次选择同一实物的 1–3 张照片。第一张就是单图基准；重新选择会替换整批。JPEG / PNG / WebP，每张 ≤10 MB、≤16 MP。
3. 默认 SQLite + RapidOCR。原多路检索只支持单图。旧“多视图 OCR”是每张图的固定裁剪/旋转，与真正多张拍摄照片是两回事。
4. 点击识别。两张以上会分别运行第一张和整组，显示各自 Top-3、Top-10、实际耗时、是否执行视觉模型。可选“已知型号”只给浏览器评分，不进入推理。
5. 点击缩略图或逐图依据按钮，查看对应照片的 OCR 文字框、原文、形状和单图候选。右侧最终候选是整组融合；没有可靠形状时显示不可用。
6. 如需核验难例，勾选视觉核验，需要 README 的本地 Apple Silicon `.venv-vlm` 环境。多图至少两个独立组支持唯一强型号且无冲突时可跳过视觉模型。联合视觉判断仍可能错读、幻觉或弃权，可展开原文检查。
7. 页面下方“单图 / 三图实验”可查看保存的实测组，不会重新调用模型。中英西切换保留图号和结果；OCR、型号、数值保持原文。

## 怎么拍才有信息

第一张清晰拍丝印，第二张轻微斜拍或调整光照以避开反光，第三张拍有线索的侧面/背面。保持同一实物，尽量保留整个元件并让文字有足够像素。三张同角度、同反光照片不会凭空增加信息；完全相同像素只提取一次，近乎相同的照片合并计票。

单图基准固定使用第一张，没有根据评估标签挑选“最好”一张。真实比较应固定拍摄顺序，增加实物数量，保留所有成功和失败组。最初只有 80286 一个实物假设。新增公开组见下节；样本仍小且经过筛选，不能据此推断一般多角度收益。

## 公开扩展测试集

[来源与许可](../data/public_triplets/README.md)记录本轮 7 个新实物假设和原 80286 对照，共 8 组 /24 张。涵盖 UA741、ULN2003、ATMEGA328P、I8088、Z80、MC68000、ESP8266 和 I80286。I8088 是同一视频中三个实际摄像视角，独立于 7 个静态照片组统计。所有组仅为可见特征支持的同一实物推断，未经物主确认；UA741、ATMEGA328P 各有一张来自原 44 查询。

网页实验表区分公开扩展与此前实验，提供检索融合、按需视觉、强制视觉三种策略。可展开分层统计，按型号打开实测组，查看逐图来源、许可、模糊/遮挡标记，以及每张照片独立运行的 Top-1 和耗时。单图分析与联合分析同样随中英西切换；OCR 原文与元件型号保持原文。

```bash
# 离线重建精确裁剪与清单，不重新下载原图。
uv run --frozen python scripts/prepare_public_triplets.py
# 重测：固定第一张 vs 三张，再单独测第2、3张。
uv run --frozen --extra experiments python -I -m partsid.multi_image_experiments run data/public_triplets/manifest.json --all-single-views --output results/multi_image/public_retrieval.json
# 在上述命令中加 --visual 测按需核验；再加 --force-visual 测全部核验。
# 三份保存结果均可离线重算指标和校验来源。
uv run --frozen python -I -m partsid.multi_image_experiments report
```

[完整比较](../results/multi_image/comparison.md)同时公布 8 组配对基准与全部 24 张独立单图。24 张属于 8 个实物组，不能当作 24 个独立实物。第一张按事先固定顺序选定，没有按识别结果挑选最好或最差照片。输入是预先裁剪的元件区域，本轮没有评价整块电路板上自动定位元件的能力。

## 给自己的三图建清单

将照片保存在 `data/my_pairs/unit-01/` 等目录，另建 `data/my_pairs/manifest.json`，参考现有 `data/multi_image/manifest.json`。

```json
{
  "schema": 1,
  "scope": "confirmed_same_object",
  "groups": [{
    "object_id": "my-unit-01",
    "part_id": "NE555",
    "identity_basis": {
      "status": "user_confirmed",
      "evidence": "Same physical component photographed in order; marking manually checked."
    },
    "photos": [
      {"file": "my_pairs/unit-01/front.png", "sha256": "完整64位SHA256"},
      {"file": "my_pairs/unit-01/angle.png", "sha256": "完整64位SHA256"},
      {"file": "my_pairs/unit-01/side.png", "sha256": "完整64位SHA256"}
    ]
  }]
}
```

`file` 相对于 `data/`；用 `shasum -a 256 文件路径` 计算哈希。`part_id` 必须在现有目录中。只有根据可见特征推断同一实物时，使用 `scope: exploratory_same_object` 和 `status: visually_supported`，并写清依据。不要凭相同文件夹、型号或拍摄背景就声称物主确认。

```bash
uv run --frozen --extra experiments python -I -m partsid.multi_image_experiments run data/my_pairs/manifest.json --output results/multi_image/my_pairs.json
uv run --frozen python -I -m partsid.multi_image_experiments report
```

加 `--all-single-views` 另测每一张的独立单图输出；第一张测量会复用为配对基准，不额外重跑第一张。加 `--visual` 测试按需视觉核验；加 `--visual --force-visual` 强制单图/多图都执行视觉模型。推理只收到图片和公开候选，清单型号仅在外层评分。每次命令使用新的 VLM 缓存命名空间；结果包含原始模型输出与输入/提示/模型指纹。

## 常见情况

- 三张照片仍识别错：先看正确型号是否在融合 Top-10 内。未召回时，视觉重排不能选出目录外/候选外型号。
- 两张支持不同型号：页面会显示冲突，阻止直接接受；检查是否混入不同实物或 OCR 错读。
- 没有形状分数：当前前景分割不能可靠处理所有背景，未知不会当成零分惩罚。
- 更改了清单、原图、裁剪或目录：旧结果的来源校验将失败，需要重跑；不要手改结果里的哈希。
- 别的机器只看结果：按 README 克隆私有 `main`，启动页面即可回放。模型环境和权重不在 Git 中；CUDA 的联合 VLM 路径尚未实现。
