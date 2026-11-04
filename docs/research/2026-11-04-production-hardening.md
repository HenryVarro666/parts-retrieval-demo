# 2026-11-04：生产化加固与全面代码审查

- 关联ID：PR-025 至 PR-036
- 状态：PR-025–PR-033 已实现并验证；PR-034–PR-036 已观察、未改动（涉及冻结对照或需用户决策）
- 工程、分支、代码提交：`parts-retrieval-demo`，分支 `claude/exciting-ride-xaa0qp`，基线 `025a477`
- 输入manifest / 文件哈希 / 数据分区：全部冻结数据、目录 SQLite、标签与已保存结果未改动；`multi_image_experiments report` 重建后 `results/` 无差异
- 模型revision、配置、硬件与依赖：本轮未运行任何 OCR/嵌入/VLM 模型；Linux 容器，Python 3.12.3，PyPI torch 2.15（仅安装），Node 22.23

## 问题与复现

本轮由通读代码加一位只读审查代理的对抗复现组成；每条均在修复前用脚本或真实回环服务复现（端口随机）。

1. **PR-025** 仓库没有 CI，也没有 ruff/pytest 配置；`uv.lock` 在 Linux 固定 CUDA 轮子，普通 CI 机器无法合理安装。
2. **PR-026** `partsid/web.py`：`do_GET` 只捕获 `ValueError/FileNotFoundError`，其余异常（如 `KeyError`）使连接被直接关闭且无响应；`urlparse(self.path)` 与 `urlparse(origin)` 在 `try` 之外，`GET http://[abc]/api/data` 或 `Origin: http://[::1` 触发回溯；发送错误响应时的断管异常未处理；没有 socket 超时（半开连接可永久占用处理线程）；用 `print` 记录失败；`Server` 头暴露 Python 版本；HTML 无 CSP。
3. **PR-027** CSRF 防护把 `Origin` 与可由攻击者控制的 `Host` 比较：DNS 重绑定页面以 `Host: evil.example:8765` + 同名 `Origin` 发送 POST 即通过；GET `/api/data`、`/api/image` 完全无来源检查。复现：构造请求到达翻译代码（503），而错配 Origin 得到 403。
4. **PR-028** `results/multi_image/*.json` 或 `results/experiments/*.json` 中任何一个半写/损坏文件会使 `/api/data` 返回 400、整个网页显示“记录不可用”，且 `/api/predict` 在推理完成后再因此失败；`report()` 与配对结果写入非原子。
5. **PR-029** `predict()` 为取目录调用完整 `web_payload()`（冷 17.3s、暖 1.1s，含全部保存实验校验），并计入 `request_ms`，与“实测实时耗时”的口径不符。
6. **PR-030** `/api/image?file=未知文件` 每次触发全部已保存多图实验的完整校验（冷约 17s）；这是无成本的放大攻击面。
7. **PR-031** `run_visual_requests` 的 VLM 子进程无超时。
8. **PR-032** 浏览器按扩展名放行 `file.type` 为空的文件，服务端只接受三种 `data:image/*;base64` 前缀，用户得到泛化的 400；服务端又未校验解码后的真实容器格式。
9. **PR-033** 每次勾选视觉核验的实时请求创建唯一命名空间 `data/cache/multi_live/<uuid>/`，永不清理，也永远无法命中缓存。
10. **PR-034（观察）** `shape_rerank`/多图 `shape_scores` 中“形状未知”不是中性：有任何形状分数（哪怕 0.0）的候选在 RRF 中额外得到 `1/(60+rank)`，无参考形状的 8 个目录类（ATMEGA8、ESP32、ESP8266、I8080、LM317、UA741、ULN2003、Z80）在查询形状可用时被结构性压低。单元可复现：`shape_rerank(["A","B"], [], {"A": None, "B": 0.0}) == ["B","A"]`。
11. **PR-035（观察）** identifier 通道把 ≥4 位别名出现在纯数字批号中视为精确命中（`rank("LOT 180861")` → I8086 1.0），SQLite 通道则忽略纯数字词；两通道对“强证据”定义不一致，影响 `evidence_ocr` 的视图选择与冲突判断。
12. **PR-036（观察）** `/api/translate` 把任意客户端文本永久写入 `data/cache/prose_translations/runtime.json`，并在每次 `/api/data`/翻译时重新校验整份文件（仅在存在 `.venv-vlm` 时发生）。

## 原因与尝试

- 2–9 为实现缺口，无需假设；修复均为局部改动，不触及排序、OCR、目录或已保存结果的语义。
- 10/11 属于已冻结对照中的排序规则。按[实验边界](../../AGENTS.md)“冻结比较内保留策略”，本轮不改排序，只记录可复现用例，留待新版本对照中评估。
- `allowed_images` 缓存的首版键用文件 mtime/size；考虑过按内容哈希，但那正是要避免的开销。缓存只影响“允许服务哪些文件”，不绕过已保存实验的校验。

## 实际改进

- `partsid/web.py`：`Host` 允许列表（回环名 + 绑定地址 + `--allowed-host`，否则 421）；`Origin` 必须同在允许列表且与 `Host` 一致，`null` 拒绝；解析放入 `try`；`_safe_respond` 包住错误路径；`Handler.timeout=120`、`server_version`、`Content-Security-Policy`、`Referrer-Policy`；`logging` 替代 `print`；`--host/--log-level/--allowed-host`，非回环绑定打印警告；损坏结果文件记录警告并跳过；`catalog_payload()` 代替完整 `web_payload()`，`request_ms` 在构造响应前取值；实时缓存只保留最近 50 个命名空间；上传按解码后的 `image.format` 校验并接受浏览器空 MIME 的 data URL。
- `partsid/candidate_pipeline.py`：VLM 子进程超时 600s + 每请求 120s。
- `partsid/multi_image_experiments.py`：`report.json`、`comparison.md`、配对结果改为临时文件 + `replace`。
- `pyproject.toml`：ruff（显式规则集、长行 140）、pytest 配置、dev 组加入 ruff；`.editorconfig`；`.github/workflows/ci.yml`（CPU torch；lint、离线测试、report 重建无差异、README 图校验、Node 行为测试）。
- ruff 自动修复 34 处仅限导入排序/未用导入/`datetime.UTC`；评估脚本的紧凑单行风格显式豁免。

## 验证与前后对照

```text
.venv/bin/python -m pytest -q                      191 passed（基线 178 + 新增 13）
node --test tests/web_*.test.cjs                   16 pass
.venv/bin/ruff check partsid tests scripts         All checks passed
python -I -m partsid.multi_image_experiments report  results/ 无 git 差异
python -I scripts/readme_figures.py --check        4 SVG diagrams verified
git diff --check                                   通过
```

浏览器核查：真实服务（`--port 28765`）+ 无头 Chromium 加载首页，44 个样本、中英切换、图片渲染正常，CSP 下无 console error / pageerror / requestfailed。新增 13 个测试覆盖：CSP 与头、路径穿越、POST 限制、未知异常→500 JSON、Host/DNS 重绑定 421、畸形目标行→400、损坏结果文件跳过、按容器格式校验上传、缓存裁剪、允许列表缓存、`--host` 默认回环。

没有重新运行模型；44 图与 8 组结果的准确率/耗时表保持原值，口径未变。

## 剩余问题与下一步

- PR-034/PR-035 需要在新的冻结对照中评估“未知形状中性化”和“纯数字批号不作精确命中”，与现有 44 图/8 组结果并列保存，不覆盖。
- PR-036 建议为 `runtime.json` 设条目上限或只缓存保存集相关源文，需产品决策。
- `uv.lock` 的 Linux CUDA 索引与 CI 的 CPU 安装路径并存：CI 不验证锁文件本身；若要锁文件级 CI，需要为 Linux 提供 CPU 索引变体。
- 服务仍无认证；`--host` 非回环只应与带认证的反向代理一起使用。

## 保存与同步

本文件、台账 PR-025–036、`docs/HANDOFF.md` 与 `docs/README.md` 已更新；提交到 `claude/exciting-ride-xaa0qp`。原始上传、权重、`.venv` 与运行缓存仍不入库。
