# 外部采样器 M1 验收记录

日期：2026-10-15，Australia/Adelaide。SDK 基线 `cf924cb` / 0.1.0，HEP 基线 `ef6c223a` / 2.0.16，加本轮未提交修改。SDK 开发分支为 `codex/sampler-native-parity`，HEP 保持 `feat/sampler-plugins-s1`。本轮没有公开发布或调整版本。

后续本机联合故障、运行中登记管理及资源失败重试已在[M2验收](M2_VERIFICATION.md)完成；本文保留M1当时的基线和范围。

## 结论与验收范围

`Jarvis sampler load <file>` 后的本机原生工作流已跑通：新 CLI 进程可发现方法，查询不执行用户代码，连续两次 check 后可正式 run；更新影响新 scan，失败更新保留原登记，移除后旧 scan 仍按原源码恢复。空 registry 的 pack/fetch→显式 load→原生运行也通过。

修复项为台账 SAM-HEP-01/02、SAM-SDK-01–06。新增的 SAM-HEP-02 来自真实中断验收：indexed 中断保存不安全 live cursor，以及 prefix 重放后重复导入旧 payload，均转为确定性回归并修复。正式科学配置、源码与 checkpoint 的严格拒绝保持；feedback/nested 的原有恢复行为保留。

check 的保护范围是正式科学 DATABASE、绑定源码和 checkpoint。通用 runtime.json、日志、run_summary 仍沿用内置方法的共享布局。资源启动失败后已发布绑定的重试组合、DATABASE 空洞/部分失败/拒绝尾段的联合矩阵、运行中并发移除、远程 OS/Python 矩阵和 Books 最终教程仍在[开发台账](DEVELOPMENT_LEDGER.md)中开放。

## 实际结果

| 验证 | 结果 |
| --- | --- |
| SDK 全部源码测试 | **193 passed**，含 5 组固定 PCG64 raw 向量与 registry/错误边界回归 |
| SDK Ruff | `ruff check --no-cache .` 通过 |
| SDK 完整构件 helper | wheel/sdist、Twine、全依赖干净安装、pip check、重启 checker/registry smoke 通过；安装包 **193 passed** |
| HEP 定向回归 | **78 passed**；新专项含默认/自定义输出路径、indexed 安全保存/重放及非 indexed 兼容 |
| HEP 原生 check 真实集成 | **2 passed**；默认 CLI 与自定义输出 API 均完成 check→check→run→已有结果再 check，并核对正式科学文件 hash |
| 源码环境完整 CLI 生命周期 | **2 passed**，27 个独立 CLI 进程；管理、更新、失败保护、绑定恢复及分享迁移 |
| 安装包 CLI 回归 | **4 passed**，31 个独立 CLI 子进程；生命周期加提交后清理告警与重试 |
| 安装包真实 SIGINT 恢复 | **2 passed**；checkpoint 与 DATABASE-only 两条路径各归档 **169 点、169 个唯一 UUID**，逐项核对坐标及绑定来源，并验证 seed/坏源码/坏 checkpoint 的拒绝 |
| HEP 最终 fast gate | **1416 passed、478 subtests passed、3 skipped、170 slow deselected**，235.69 秒；含 Git 元数据的隔离基线加本轮修改，在完整依赖 venv 运行 |
| 完整 LHS 示例 | 实际安装的 `Jarvis` console 原样执行 load→validate→check→run，4 条命令 exit 0；归档 **32 点、32 个唯一 UUID**，两维分层 0–31 各一次且偏移均为 0.5 |

最初不含 Git 元数据的 archive 快照 fast gate 为 1403 passed、1 failed：monitor 测试要求展示 Git 分支符号，目录没有 `.git`。最终改用有 Git 元数据的隔离 checkout，并纳入新增恢复修复后得到上表全通过结果；没有改产品或放宽断言来绕过这个环境条件。

## 安装与源码隔离

本机为 macOS arm64、Python 3.13.13。SDK 源码测试使用 NumPy 2.5.0；完整安装使用 NumPy 2.5.4、jsonschema 4.26.0，HEP 完整依赖解析包括 Jarvis-Operas 1.5.0、JarvisPLOT 2.1.10、torch 2.14.1。构建和测试工具单独安装，不产生另一种用户包。

HEP 安装测试快照来自已提交 HEAD，仅覆盖以下五个实现文件和三个新测试文件；没有带入并行 Redis/Diver/pyproject 工作区改动。SDK/HEP 均从临时 venv 的 site-packages 导入，无 editable 或 PYTHONPATH 注入，主子进程使用同一解释器，pip check 通过。五个 HEP 实现文件在已安装 wheel 内与工作源码 SHA-256 一致。

- HEP 实现：`sampling/plugin_identity.py`、`sampling/plugin_sampler.py`、`sampling/runtime_checkpoint.py`、`runtime/_resume_service.py`、`runtime/_runtime_supervisor.py`。
- HEP 新测试：`test_plugin_check_layout.py`、`test_sampler_cli_lifecycle.py`、`test_sampler_registry_cli.py`。
- SDK 实现：`registry.py`、`metadata.py`、`session.py`、`output.py`。API v1、STREAM_PROTOCOL=1 和 registry format=1 保持不变；待清理记录为 SDK 私有文件。

注册、cache、CLI notice、项目与 Redis 端口均使用临时测试资源。完整示例复制到临时项目后执行，没有在 SDK 目录生成扫描结果。

## 复验入口与证据

SDK：

```bash
python -m pytest -q --import-mode=importlib -o pythonpath= -p no:cacheprovider
ruff check --no-cache .
./jhsrel --output <新的空构件目录>
```

HEP 的 final fast gate 在隔离 checkout 中使用完整依赖环境执行：

```bash
<venv>/bin/python -m pytest -q -m 'not slow' -p no:cacheprovider --junitxml=<结果.xml>
```

安装包专项从 checkout 外的目录运行，测试文件使用绝对路径，主子进程均使用 venv 解释器：

```bash
<venv>/bin/python -m pytest -q --import-mode=importlib -o pythonpath= -o addopts= \
  <HEP测试根>/test_sampler_cli_lifecycle.py <HEP测试根>/test_sampler_registry_cli.py
<venv>/bin/python -m pytest -q --import-mode=importlib -m slow \
  <HEP测试根>/test_plugin_resume_runtime.py
```

机器验收记录存于 HEP 仓库 `docs/jarvis-hep-sampler/native-parity-m1-verification.json`，包含具体命令、环境、构件/源码 hash 和实际结果。本文件和台账保留持久摘要。原始临时日志位于 `/private/tmp/jhs-m1-package/`、`/private/tmp/jhs-m1-installed-cli-tests/`、`/private/tmp/jhs-m1-installed-resume/` 与 `/private/tmp/jhs-m1-installed-example/`；临时目录可能被系统清理。
