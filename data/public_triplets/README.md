# 公开同一实物三视图：来源与冻结记录

本批 8 组 / 24 张目标裁剪，新增 7 组，保留 1 组 I80286 历史对照。所有组均为 `visually_supported`，并无实物持有人或专家确认；这是探索性难例集合。新增的是三图实物分组，不等于所有拍摄都此前未收集：24 个来源拍摄中，16 个不在原 209 条原始库，8 个已存在（UA741 1、ATMEGA328P 1、Z80 3、I80286 对照 3）；其中只有前两张属于原 44 查询。Z80 三张为首次完成同一实物核验与成组测试。

数据选择和裁剪在运行新批次推理前冻结。新组按拍摄时间排序，视频按时间码排序；历史对照保持原顺序。第一张作为配对单图基线，另外逐张测量全部 24 张单图。不会根据结果更换顺序或剔除失败样例。

| 组 | 目录型号 / 观察到的变体 | 来源（原图页面） | 作者 / 许可 | 特别说明 |
|---|---|---|---|---|
| public-01 | UA741 / National Semiconductor LM741CN | [56426658](https://commons.wikimedia.org/wiki/File:DOV-1X_-_printed_circuit_board-9784.jpg) / [56426698](https://commons.wikimedia.org/wiki/File:DOV-1X_-_National_Semiconductor_LM741CN_on_printed_circuit_board-9801.jpg) / [56426711](https://commons.wikimedia.org/wiki/File:DOV-1X_-_Philips_3H1_RM_cores_on_printed_circuit_board-9805.jpg) | Raimond Spekking / CC BY-SA 4.0 | DOV-1X 同一焊接位置、M8930、白色端条；第 2 张复用旧 44 查询的一个拍摄。 |
| public-02 | ULN2003 / ULN2003A | [114335035](https://commons.wikimedia.org/wiki/File:Revox_B215_-_implanting_signal_relays_03_-_the_implant.jpg) / [114335037](https://commons.wikimedia.org/wiki/File:Revox_B215_-_implanting_signal_relays_04_-_implant_in_place.jpg) / [114517910](https://commons.wikimedia.org/wiki/File:Revox_B215_-_implanting_signal_relays_07_-_implant_in_place.jpg) | Retired electrician / CC0 | Revox 手工植入板；第 3 张遮挡、字样不清，明确纳入困难视角，不当作清晰芯片特写。 |
| public-03 | ATMEGA328P / ATMEGA328P-PU | [149126951](https://commons.wikimedia.org/wiki/File:ArduTouch_Music_Synthesizer_kit_assembly_March-2016_-_41_(25731304436).jpg) / [149126936](https://commons.wikimedia.org/wiki/File:ArduTouch_Music_Synthesizer_kit_assembly_March-2016_-_50_(25757382705).jpg) / [149126939](https://commons.wikimedia.org/wiki/File:ArduTouch_Music_Synthesizer_kit_assembly_March-2016_-_52_(25130773273).jpg) | Mitch Altman from Berlin, Germany / CC BY-SA 2.0 | ArduTouch 同一芯片裸件到安装过程；第 3 张反光，第 1 张复用旧查询。上方批次字符不做精确转录。 |
| public-04 | I8088 / Intel P8088 | [156176792](https://commons.wikimedia.org/wiki/File:RETRO;_Pierwszy_komputer_PC_(2160p_30fps_VP9_LQ-128kbit_AAC)-00.00.22.800.png) / [156176818](https://commons.wikimedia.org/wiki/File:RETRO;_Pierwszy_komputer_PC_(2160p_30fps_VP9_LQ-128kbit_AAC)-00.04.38.000.png) / [156176867](https://commons.wikimedia.org/wiki/File:RETRO;_Pierwszy_komputer_PC_(2160p_30fps_VP9_LQ-128kbit_AAC)-00.16.34.800.png) | ZMASLO / CC BY 3.0 | 同一 IBM5150 视频中 22.8 / 278.0 / 994.8 秒的实际不同视角；独立于静态照片组统计，并非三个拍摄场次。 |
| public-05 | Z80 / Zilog Z0840004PSC Z80 CPU | [41018750](https://commons.wikimedia.org/wiki/File:Neo-Geo-AES-Opened-FL.jpg) / [41018739](https://commons.wikimedia.org/wiki/File:Neo-Geo-AES-Opened-BL.jpg) / [41018754](https://commons.wikimedia.org/wiki/File:Neo-Geo-AES-Opened-FR.jpg) | Evan-Amos / Public domain (PD-self source declaration) | NeoGeo 同一主板和焊接位置；BL 严重受连接器遮挡，保留为困难视角。 |
| public-06 | MC68000 / Motorola MC68000P10 | [31983614](https://commons.wikimedia.org/wiki/File:Super-Acan-Motherboard-01.jpg) / [70574276](https://commons.wikimedia.org/wiki/File:Super-Acan-Motherboard-02.jpg) / [70574301](https://commons.wikimedia.org/wiki/File:Super-Acan-Motherboard-03.jpg) | Evan-Amos / Public domain (PD-self source declaration) | SuperAcan 同一主板，4C91E 标记、焊点和检查印记一致；当前 2018 年三次拍摄。 |
| public-07 | ESP8266 / ESP8266EX | [110929858](https://commons.wikimedia.org/wiki/File:SparkFun13711-01.jpg) / [110929856](https://commons.wikimedia.org/wiki/File:SparkFun13711-02.jpg) / [110929857](https://commons.wikimedia.org/wiki/File:SparkFun13711-04.jpg) | SparkFun Electronics / CC BY 2.0 | SparkFun13711 红板，实际 ESP8266 芯片而非前面的 FTDI；第三图明显失焦。匹配的作者站点 600px 文件，可能重新压缩。 |
| anchor-01 | I80286 / Intel N80286-10 | [158840809](https://commons.wikimedia.org/wiki/File:Intel_chips_286_386_387_486_pentium_size_comparison_01.jpg) / [158840810](https://commons.wikimedia.org/wiki/File:Intel_chips_286_386_387_486_size_comparison.jpg) / [158840814](https://commons.wikimedia.org/wiki/File:Intel_chips_286_386_486_size_comparison.jpg) | Sgroey / CC BY-SA 4.0 | 保留上一轮有限视角的对照组，不将其算作本轮新增。 |

公开许可仅适用于对应来源图片；裁剪属于所标明的修改，CC BY-SA 图片及裁剪保留原许可。Public domain 来自作者在 Commons 页面的声明，不冒充 CC0。完整逐图署名、许可链接、来源 URL、下载 URL、原 SHA1、保存 SHA256、时间及整数 ROI 见 `selection.json` / `manifest.json`。源文件原样保存，没有合成视角或叠加型号提示。

## 排除与复核

- 同型号不等于同一实物。UA741PC T/T1/T2/T3 为不同 IC1–IC4，排除；某些 741 系列图实际是 LF412，排除。
- Oligopolism IBM PC 多个裁剪/缩放图共享 OriginalDocumentID，仅两次芯片正面拍摄；不填充为三图。
- SparkFun 蓝色 ESP-01 的带硬币图与斜拍图疑似复用同一曝光，保守排除。ESP-M2 可能是 ESP8285，不改标为 ESP8266。
- Xerox/Emerson LM317/ULN 电源板系列未找到三张可核实目标可见图，排除；2N3055 闭合/破坏性开盖不当作普通角度变化。
- 目录参考的包装、批次、板卡与新增组逐一目视比较；参考文件与哈希及排除依据保存在各组 `catalog_exclusion`。不将原图页面 ID 不同视为充分的独立拍摄证据。
- 使用原 DocumentID、EXIF 时间、透视/引脚/遮挡变化及板卡细节共同审核。EXIF 无时区时保留未知；视频实际传感器拍摄日期未知。

## 复现

```bash
uv run --frozen python scripts/prepare_public_triplets.py
uv run --frozen --extra experiments python -I -m partsid.multi_image_experiments run data/public_triplets/manifest.json --all-single-views --output results/multi_image/public_retrieval.json
uv run --frozen --extra experiments python -I -m partsid.multi_image_experiments run data/public_triplets/manifest.json --all-single-views --visual --output results/multi_image/public_gated.json
uv run --frozen --extra experiments python -I -m partsid.multi_image_experiments run data/public_triplets/manifest.json --all-single-views --visual --force-visual --output results/multi_image/public_visual.json
uv run --frozen python -I -m partsid.multi_image_experiments report
```

准备脚本离线从已保存来源重建裁剪；首次模型运行需要下载固定版本权重。三个实验串行运行，共享各命令内已加载的检索模型，单图优先，三图其次，然后第 2、3 张独立单图。总耗时包含实际请求的 VLM 进程启动/加载，不含检索模型初始化（另存）。不在浏览器同时发起推理。模型、目录、prompt 与融合阈值保持原样。

结果目录保留历史实验。本批覆盖的旧错误类型为 UA741、ULN2003、ATMEGA328P、I8088、Z80、ESP8266，加上原 I80286 对照；MC68000 用于扩展包装类型。每类一个实物假设，不能当作每类准确率估计。
