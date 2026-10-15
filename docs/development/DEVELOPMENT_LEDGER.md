# Jarvis-HEP-Sampler 开发台账

更新日期：2026-10-16，Australia/Adelaide。当前阶段：M2 本机原生闭环与联合故障验收完成。发行版本是 1.0.0；插件 `api_version`、`STREAM_PROTOCOL` 和 registry 格式仍是 1。本阶段解释器只验收 pyenv 的 Python 3.13.13；其余 OS/Python 与最低依赖等到开发结束后统一测。M3 的两种 check 已写入教程，pyenv 3.13.13 的性能证据已记入下方「性能证据」，20 μs 仍是待校准目标。PyPI 上传是单独的一步。

2026-10-16 确定首发范围：用户用外部 Sampler 得到和内置 Sampler 一样的使用体验。内置 Sampler 没有的行为，外部 Sampler 也不要有。`Jarvis sampler load` 之后，validate、check、run、resume、man 的命令和参数与内置方法相同，不再新增任何 CLI。`--accept-plugin-change` 不进入首发，不实现。续跑继续使用该 scan 已绑定的源码。用户更新 NumPy、Python 或 SDK 后接着原来的 scan 跑，保持现有行为：警告，然后按用户当前环境继续。这和内置 Sampler 一样，不另加科学正确性拦截。插件算法是否正确由用户负责。

已经存在的 `Jarvis sampler init|check|load|list|info|remove` 只负责把一个文件登记成 Method。它们不是扫描用法，也不再扩展。

用户通过 `Jarvis sampler load <file.py>` 登记一个符合 SDK 契约的文件，之后在 task card 中使用 `Sampling.Method: <Method>`，沿用内置采样器的验证、检查、运行、监控、恢复和项目分享流程。外部采样器的创建、检查、加载、查询、更新与移除统一由 `Jarvis sampler` 管理。

这项对等要求覆盖用户工作流和运行基础设施。首轮交付支持 `independent` profile；依赖计算反馈的算法归后续 generational 阶段，不能把其名称预留写成已支持执行。

## 用户使用合约

已经有插件文件时，唯一必需的登记步骤是：

```bash
Jarvis sampler load MySampler.py
```

对等验收路径如下。`task.yaml` 是完整扫描卡，包含原有 Scan、环境和计算配置，并将 `Sampling.Method` 设为 `MySampler`。SAM-HEP-01 已修复 check 隔离，独立 CLI 的连续两次 check 后正式运行已通过。

```bash
Jarvis sampler init MySampler                       # 可选，生成模板后编辑
Jarvis sampler check MySampler.py --card task.yaml   # 可选，离线检查插件
Jarvis sampler load MySampler.py
Jarvis sampler list
Jarvis sampler info MySampler
Jarvis man sampler.MySampler
Jarvis validate task.yaml
Jarvis check task.yaml                              # 原生 calculator smoke
Jarvis run task.yaml
# 扫描中断后，按原生方式恢复：
Jarvis run task.yaml --resume
```

`Jarvis sampler check` 是离线插件一致性检查，`Jarvis check` 是原生计算链检查，两者有不同作用。前者不应成为 `load` 的强制前置步骤，后者必须与正式扫描隔离。

| 管理操作 | 用户命令 | 必须维持的行为 |
| --- | --- | --- |
| 创建 | `Jarvis sampler init <Method>` | 生成可编辑模板；已有文件不覆盖，内置名称受保护 |
| 离线检查 | `Jarvis sampler check <file或Method>` | 文件可在未登记时检查；报告参数、输出、可重复性和重启检查结果 |
| 登记与更新 | `Jarvis sampler load <file>` | 执行导入和结构检查，成功后保存源码快照及登记；同名再次 load 即更新，无独立 reload 命令 |
| 列表与详情 | `Jarvis sampler list`、`info <Method>` | 不执行用户插件代码；准确展示已加载版本、来源及快照状态，区分工作文件修改与登记损坏 |
| 移除 | `Jarvis sampler remove <Method>` | 交互确认；非交互使用已有 `--yes`。保留用户源文件和既有 scan 的独立绑定 |

加载后的卡片沿用现有 `Sampling.Method`、`Variables`、`Bounds`、Mapper 与 selection 约定，不增加插件路径、factory 或注册模块字段，不要求用户修改 HEP 源码、手动操作 registry、Redis 或 Worker。

登记属于当前用户与机器。快照固定入口 `.py` 文件；插件依赖的库仍需安装到运行 Jarvis 的 Python 环境，兄弟模块与资源文件当前不随入口快照复制。迁移项目时，通过原生 pack/fetch 携带源码并提示目标机器显式 load。

### 更新和移除的扫描语义

- 修改工作文件但未 load：后续新 scan 继续使用已登记快照，list/info 显示工作文件状态。
- 同名重新 load：之后的新 scan 使用新版本；已经运行或中断的 scan 保持原源码、完整 hash 与科学配置绑定。
- 移除登记：新 scan 不再能通过该用户登记找到方法；已有绑定 scan 的运行与恢复不依赖当前登记。
- 载入失败：原可用登记保持可用。提交成功后清理旧文件失败时，命令应准确区分已生效的登记与待重试清理。
- 内置名称不能被覆盖或移除；只差大小写的外部名称冲突应拒绝。当前已实现这些名称保护，后续保持回归。

## 当前实现基线

| 范围 | 核对基线 | 当前状态 |
| --- | --- | --- |
| SDK | `cf924cb54b2bdf4e3281430789eb5a68b0b0c649` + 本轮修复，发行版本 1.0.0 / Alpha | 单文件契约和统一 IndependentSession 保持；registry、hook、输出错误及名称诊断已修复，协议版本不变 |
| Jarvis-HEP | M2 验收基线 `569d3865f60486da048b69c74c4ef3730713265d` + sampler overlay，2.0.17，`feat/sampler-plugins-s1` | M1 修复保留，M2 新修 prefix 外 durable 终态行重复提交；保留并行 Redis/monitor/Diver 工作。M1 的 2.0.16 验收为历史 |
| 原生对等交付 | 下方 AC 验收矩阵 | M1 管理/pack/fetch 闭环保留；M2 空洞/混合失败/拒绝尾段、运行中管理及资源故障重试通过，远程矩阵归 M3 |
| 后续算法能力 | generational | 元数据预留，执行协议与适配尚未交付 |

SDK 继续负责插件格式、登记、随机流、输出约束和离线驱动。HEP 继续负责 CLI、卡片、参数映射、selection、UUID、队列、Worker、归档、日志监控、checkpoint 与项目打包。离线与原生运行共用 `IndependentSession`。

本文跟踪本轮交付任务和验收；插件 API 的设计决定仍进入 HEP 仓库 `docs/jarvis-hep-sampler/technical-design.md`，HEP 总体维护遵循其五份 canonical 文档。下文 `SDK/` 表示本仓根目录，`HEP/` 表示 Jarvis-HEP 仓根目录。当前未以源码或本机验收推断公开发行状态。

## 原生使用对等验收矩阵

“已有实现”表示当前存在代码和分项覆盖，不能替代本轮完整链路验收。

| ID | 用户行为与通过标准 | 当前状态 | 对应任务 |
| --- | --- | --- | --- |
| AC01 | load 成功后，新 CLI 进程直接发现并使用方法；错误 load 保留旧登记；list/info 不执行用户插件 | 本机独立 CLI 闭环通过 | SAM-SDK-01/02/05、SAM-QA-01 |
| AC02 | 相同完整卡结构，只替换 Method 和其 Bounds；未知方法或参数给出原生路径诊断；man 可查插件说明 | 本机完整卡及查询闭环通过，保留 schema 定向回归 | SAM-QA-01 |
| AC03 | 连续两次 `Jarvis check` 均成功，随后 fresh run 成功；已有正式 scan 的 check 不改变科学 DATABASE、源码绑定和 checkpoint | 已修复；默认 CLI 和自定义输出 API 均通过 | SAM-HEP-01 |
| AC04 | 映射、selection、Redis、backpressure、Worker 与 Archiver 走原生链；全拒绝有界结束 | 实际 Redis/spawn 运行通过，保留全拒绝等已有分项回归 | SAM-QA-01/02 |
| AC05 | 日志、run metadata、monitor 正确显示方法、实际源码与进度；报告 hook 失败只告警并跳过 | hook 边界已修复，NumPy 标量已支持，既有观测回归保留 | SAM-SDK-03/06、SAM-QA-01 |
| AC06 | seed/索引决定随机流；不同 batch/worker 设置不改变坐标与 UUID；块边界和非整块尾段正确 | 5 组固定 PCG64 参考与既有批次回归保留；M2 块模式覆盖 block=8/N=37、workers=1/2与batch=3/5，运行中管理另覆盖batch=1/4 | SAM-QA-02 |
| AC07 | 真实中断后 resume 与未中断结果一致；科学配置、源码或 checkpoint 损坏在写入资源前拒绝 | 真实中断两路径及严格拒绝保留；M2 四组空洞/混合 Failed/拒绝尾段和两组全 durable 零计算尾段通过 | SAM-HEP-02、SAM-QA-02 |
| AC08 | load v1 后建立 A，load v2 后建立 B；A 保持 v1，B 使用 v2；remove 后两者仍能恢复，源文件保留 | 本机通过；M2 运行中 reload/remove 后继续完成及 SIGINT→无登记恢复，两组各37点的坐标/UUID一致 | SAM-SDK-01/02/05、SAM-QA-01/02 |
| AC09 | pack/fetch 保留准确源码与完整 hash；fetch 不导入或自动登记；空 registry 上显式 load 后可原生运行 | 本机空 registry 的完整 CLI 链通过，跨 OS/Python 留在 M3 | SAM-QA-01/03 |
| AC10 | 计算异常准确退出并清理资源，不回退其他算法；插件错误保留 cause 和定位；完整 wheel 安装可复现上述流程 | 本机完整依赖安装与故障清理/绑定重试通过；7个HEP实现和全部SDK源码与安装包一致，远程矩阵归M3 | SAM-SDK-03/04/06、SAM-QA-02/03 |

## 开发任务

P1 为直接阻断正常用户流程；P2 为正确性、数据保护或错误合约缺陷；P3 为低优先级完善。责任列表示所属仓库，不指定个人。完成状态指工作区实现与对应本机回归，不代表已提交或公开发行。

| ID | 优先级与责任 | 工作内容与完成标准 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| SAM-HEP-01 | P1，HEP | 统一 check 的 database、身份、源码与 checkpoint 路径。`check → check → run` 成功，check 不改已有正式 scan 的科学与恢复状态；保持正式 resume 的严格校验 | 无 | 已完成 |
| SAM-HEP-02 | P1，HEP | indexed 中断只保存 durable prefix 允许的安全批快照；bootstrap 对齐 prefix 后不得再次导入旧游标。非 indexed/反馈与 nested 保留原行为 | 真实恢复验收发现；不放宽严格恢复校验 | 已完成 |
| SAM-HEP-03 | P2，HEP | 保留 DATABASE prefix 外已 durable 的 pending sample_index，FixedSet 提交跳过这些终态并返回实际新增数；缺失点补算，Failed 不重算，不把目标22超计为25。pending 不写 checkpoint，科学游标与严格恢复不变 | M2 联合故障发现，SAM-HEP-02 | 已完成 |
| SAM-SDK-01 | P2，SDK | 在读写协调下取得 entry 与 payload，只验证并执行同一份 bytes；锁外执行用户代码。并发 reload/remove 不执行错版源码、不泄漏裸文件异常 | 无 | 已完成 |
| SAM-SDK-02 | P2，SDK | 校验所有受管快照路径，统一应用于读、remove 和 reload 清理；拒绝绝对路径、`..` 与规范化后越界路径，确保 registry 外源文件保留 | 无 | 已完成 |
| SAM-SDK-03 | P2，SDK，HEP 回归 | 将 hook 调用、返回值迭代、类型检查和转换纳入同一错误边界；离线检查给出 hooks FAIL，原生 scan 对报告错误只告警并继续 | 无 | 已完成 |
| SAM-SDK-04 | P2，SDK | float64 转换溢出统一包装为 PluginOutputError，保留 cause、方法及候选位置；draw/draw_block 的 checker 输出 FAIL 而非裸异常 | 无 | 已完成 |
| SAM-SDK-05 | P2，SDK 与 HEP CLI | 明确 registry 提交点与清理失败结果。提交前失败保留旧状态；提交后旧快照清理失败准确报告操作已生效及清理待重试，重试可恢复 | SAM-SDK-02 | 已完成 |
| SAM-SDK-06 | P3，SDK | 完整匹配方法名以拒绝尾换行；非 UTF-8 registry 包装 RegistryError；将常见 NumPy 标量指标规范化后再校验有限性 | SAM-SDK-02/03 | 已完成 |
| SAM-QA-01 | P2，两仓 | 用独立 CLI 进程覆盖管理、原生运行、同名更新、移除与空 registry 的 fetch/load 路径；对应 AC01–05、08–09 | SAM-HEP-01、SAM-SDK-01/02/03/05 | 本机闭环已通过 |
| SAM-QA-02 | P2，两仓 | 补固定随机流参考、中间块恢复、真实中断、稀疏 selection、DATABASE 空洞、部分 batch 失败与拒绝尾段组合；核对资源初始化失败后的绑定及重试语义 | SAM-HEP-01/02、SAM-SDK-01/03/04 | 本机已完成；包含 SAM-HEP-03 修复和联合故障矩阵 |
| SAM-QA-03 | P2，两仓 | 明确 HEP/SDK/API/STREAM_PROTOCOL/registry 格式兼容组合；完整 wheel/sdist、全依赖干净安装、Linux/macOS 与声明支持的 Python 矩阵跑原生闭环 | SAM-QA-01/02 | 兼容组合已写明。本阶段只保留 pyenv Python 3.13.13 的 wheel 测试。其余 OS/Python 与最低依赖等到开发结束后统一测 |
| SAM-DOC-01 | P2，两仓与用户手册 | M1/M2 随实现同步相关作者指南、HEP canonical/API 设计和 CLI 说明；M3 补齐完整卡、Jarvis-Books 教程与最终证据，准确区分两种 check、同名更新及旧 scan 恢复 | 与实现各阶段同步；最终收尾依赖 SAM-QA-01–03 | 教程正文已写入。pyenv 3.13.13 上的命令证据见下方「教程命令」 |
| SAM-FUT-01 | 后续设计，两仓 | 定义反馈算法 ask/tell 状态归属、逐 proposal 终态、空代预算和 barrier/checkpoint 原子边界，toy 故障验收后再开放 generational | independent 对等闭环 | 后续阶段 |

### 修复依据与回归入口

1. **SAM-HEP-01**：`HEP/jarvishep2/sampling/plugin_identity.py` 的 `identity_path` 固定正式 `DATABASE/sampler_identity.json`，未跟随 `runtime/_scan_driver.py` 的 `DATABASE/test` 布局；`plugin_sampler.py` 随后拒绝已有身份。官方 LatinHypercube 也受影响。增加真实 CLI 的 check 隔离回归，并覆盖自定义输出目录和已有正式结果。
2. **SAM-SDK-01**：`SDK/src/jarvis_hep_sampler/registry.py::load_snapshot` 先经 `problems` 校验，再读文件执行。受控交错已复现执行 hash 与登记不符、正常 reload 删除旧文件后裸 FileNotFoundError。扩展 `tests/test_registry.py`；HEP preflight 当前核验同一 payload，不把 SDK 缺陷直接归因于 HEP 执行路径。
3. **SAM-SDK-02**：RegistryEntry 对 snapshot 只做字符串转换，清理直接 unlink。修改临时 registry 的 snapshot 为外部临时源文件绝对路径后，remove 删除了该文件。回归使用哨兵文件验证损坏 registry 不造成额外删除；这是本用户注册数据损坏时的保护缺口。
4. **SAM-SDK-03**：`session.py::_rows/status/stop_reason` 部分返回值处理位于保护范围外。yield 型 rows 中途抛错会使 checker 抛原始异常；status 映射迭代异常可使 HEP adapter 初始化失败。普通 rows 异常通常有 HEP lifecycle 外层兜底，不能概括为所有 hook 都会中止 scan。扩展 `tests/test_session.py`、`test_template_and_testing.py` 和 HEP 插件初始化测试。
5. **SAM-SDK-04**：`output.py::_as_float_array` 未包装 OverflowError，`draw` 返回 `[10**400]` 可使 checker 直接退出。扩展 `tests/test_streams_output.py` 与 checker 回归。
6. **SAM-SDK-05**：故障注入确认 `_write_store` 失败保留旧登记；但 `_delete_snapshot` 失败时 registry 已提交，load/remove 却抛 PermissionError。扩展 registry 故障注入及 CLI 结果验证，区分提交与垃圾清理，不将其笼统描述为已有写锁失效。
7. **SAM-HEP-02**：真实中断曾保存 accepted=54 而 durable prefix=52 的不安全 live 状态；改选安全快照后又暴露 bootstrap 在 prefix 重放后再次导入旧状态，造成重复提交及归档等待。两处分别用确定性失败回归修复；真实 checkpoint 与 DATABASE-only 恢复均完成 169 个 accepted 点的坐标和 UUID 核对。

8. **SAM-HEP-03**：DATABASE 有 prefix=2、pending={3,6,8} 时，reader 的 pending 被丢弃，恢复重复计算三行，归档等待目标25而实际唯一行22。将故障转为6个fast回归及4组真实矩阵；宿主传递 pending 到 FixedSet，仅提交缺失点，Failed 终态保留，不改 candidate/accepted 或 checkpoint 合约。

上述条目保留修复前触发条件。当前实现、通过结果与范围见任务状态和下方本轮验收记录。

现有回归入口：SDK 的 `test_registry.py`、`test_session.py`、`test_streams_output.py`、`test_template_and_testing.py`；HEP 的 `test_sampler_plugins.py`、`test_sampler_logging_contract.py`、`test_plugin_resume.py`、`test_plugin_resume_runtime.py`、`test_project_samplers.py`。现有 casefold 冲突、内置保留名、正常同名替换和失败导入保护应保持通过。

## 实施顺序与交付门槛

| 阶段 | 内容 | 状态与结束门槛 |
| --- | --- | --- |
| M0 目标与台账 | 固定用户合约、责任边界、现状和验收矩阵 | 已完成 |
| M1 可靠性修复 | SAM-HEP-01/02 与 SAM-SDK-01–06，SAM-DOC-01 随变更同步 | 已实施并通过对应本机回归；保留严格恢复与原生非 indexed 行为 |
| M2 原生闭环 | SAM-QA-01/02，补齐 AC01–10 的本机原生链路证据，SAM-DOC-01 同步结果 | 已完成本机范围；联合恢复、全 durable 拒绝尾段、运行中登记管理及资源失败清理/重试全部验收，详见 M2 记录 |
| M3 兼容与文档 | SAM-QA-03、SAM-DOC-01 的最终教程与证据收尾 | 本阶段只测 pyenv 3.13.13，其余版本后置。教程命令与性能证据已在该解释器上记录，见下方。20 μs 仍是待校准目标 |

每项完成记录源码基线或实现 commit、有效测试命令、结果与证据位置；未提交改动以文件 hash 留存。重跑应标明环境与实际收集范围。不为新增 profile 复制一套采样运行时，具体发行版本与公开发布另按发行流程确定。

独立 CLI 验收至少包含以下串联场景，所有源文件、registry、项目和运行缓存使用临时目录：

1. load v1 → 新进程 list/info/man/validate → check → 再次 check → run；不编辑 HEP、不手动注册 factory。
2. 修改工作文件而不 load → 新 scan 仍使用 v1；load v2 → 新 scan 使用 v2；失败 reload → v2 仍可运行。
3. A 在 v1 下中断 → load v2 并运行 B → remove → A/B 按各自绑定恢复；比较坐标、UUID、源码 hash 和归档结果，保留工作源文件。
4. project pack → 空 registry 的另一环境 fetch → 按提示 load → validate/check/run；同名不同 hash 有明确提示，损坏包在执行前拒绝。
5. 运行异常、报告 hook 异常、资源初始化失败分别验证退出/继续语义，确保资源清理与原生行为一致。

## 验证证据基线

下列结果来自 2026-10-15 的本次 review，早于台账文档变更。环境为 macOS、Python 3.13.13；源码测试使用 NumPy 2.5.0，干净安装包测试使用 NumPy 2.5.4、jsonschema 4.26.0。

| 验证 | 实际结果 | 适用范围 |
| --- | --- | --- |
| SDK `python -m pytest -q --import-mode=importlib -o pythonpath= -p no:cacheprovider` | 146 passed | 当前 SDK 源码基线 |
| SDK `ruff check --no-cache .` | 通过 | 当前 SDK 源码基线 |
| `./jhsrel --output <临时空目录>` | wheel/sdist 构建、Twine、完整依赖安装、pip check、模板/重启 checker/registry smoke 通过；安装包测试 146 passed | 本机完整安装路径，未上传 |
| HEP `test_plugin_resume.py` 与 `test_project_samplers.py` | 28 passed | 恢复与项目打包定向回归 |
| 真实 CLI，官方 LatinHypercube，6 点，隔离项目/registry/cache | 首次 check exit 0；随后 run exit 1；再次 check exit 1 | SAM-HEP-01 的失败证据；不是完成后的通过结果 |
| SDK 隔离复现与故障注入 | 快照读取交错、越界删除、hook 返回值异常、数值溢出、提交后清理失败均观察到上述行为 | SAM-SDK-01–05 的修复输入 |

check 失败序列中，首轮检查已生成 `DATABASE/test/samples.hdf5`，同时留下正式 `DATABASE/sampler_identity.json`；后续两条命令均报告 `existing scan has no usable source binding`。这个结果需要由修复后的成功序列取代，并保留旧失败事实。

本次构件 SHA-256：wheel `e749675a37a3b371b632786b5fffde26a82d877916cc06d835ded6a54cac0897`；sdist `43e171685043e71a66d6300ca9e86f76c77b8eea8fcaa56df28034ca77bfe750`。原始临时附件位于 `/private/tmp/jhs-review-20261015-cf924cb/` 和 `/private/tmp/jhs-native-check-review-jdy7j7h9/`；本节保留持久摘要，后续验收须归档新的原始证据。

上述 review 基线当时未重跑 HEP 全仓或远程 OS/Python 矩阵；后续 M1 的有效结果见下一节。大预算 checker 的流式比较、插件依赖环境清单属于后续改进；部分检查若增加上限，须保留真实 context 总预算，不能悄悄改变 LHS 等算法的设计。

## M1 实施验收

SDK 全部源码与完整安装包测试各 **193 passed**，Ruff 和构件检查通过。HEP 定向 **78 passed**；最终隔离 checkout fast gate 为 **1416 passed、478 subtests passed、3 skipped、170 slow deselected**。安装包的独立 CLI 测试 **4 passed**，真实 SIGINT checkpoint / DATABASE-only 恢复 **2 passed**，主子进程均从独立 venv 的 site-packages 使用同一构件。

新增[完整示例卡](../../examples/MyLatinHypercube.task.yaml)与现有 LHS 插件配套，安装包真实 console 的 load→validate→check→run 验证32个居中分层点。五份 HEP canonical 文档、技术设计与 SDK 作者文档均同步；构件版本和插件协议不变。详细命令、环境、初始失败与最终范围见 [M1 验收记录](M1_VERIFICATION.md)。

提交后的清理重试使用私有 `.pending_cleanup.json`，只记录明确退役快照及完整 hash；保护源文件，不扫描目录回收未知文件。提交前失败的无登记孤儿保守保留；重试记录损坏或无法保存时给出准确警告，不把已完成登记回报为失败。


## M3 兼容组合

这些编号在 0.1.x SDK 与依赖它的 HEP 2.0.17 sampler 工作区之间一起生效。对不上就拒绝加载或拒绝续跑，不在运行中协商。

| 面 | 当前值 | 不匹配时 |
| --- | --- | --- |
| HEP 依赖 | `Jarvis-HEP-Sampler>=1.0.0,<2` | 安装期拒绝 2.0 及以上 |
| 插件 `api_version` | `1` | `PluginLoadError` |
| `STREAM_PROTOCOL` | `1` | 进入硬身份；改变后再续跑会被科学身份拒绝 |
| registry `sources.json` | `version` `1` | `RegistryError` |
| scan binding | `binding_version` `1` | `PluginResumeMismatch`，要求新 scan 名 |
| 硬身份 | `identity_version` `2` | 同上，按科学字段逐项拒绝 |
| 解释器与库 | Python `>=3.10`；NumPy `>=1.24`；jsonschema `>=4.18` | 低于下限不在支持声明内。已绑定 scan 上这三项变化只警告，不改写绑定 |

支持声明仍是 Linux 与 macOS、Python 3.10–3.13，外加 Python 3.10 上 NumPy 1.24 与 jsonschema 4.18。逐位比较只在同一环境内成立。本阶段只测 pyenv 的 3.13.13；其余格子等到开发结束后统一测，因此 SAM-QA-03 现在不关闭。

2026-10-15 用 `python -m build` 打出的 wheel `jarvis_hep_sampler-0.1.0-py3-none-any.whl`（SHA-256 `ad5a8136e2ba4de7b7b131f90daa5c8564ccd5c11db61d7158701e6084d8762e`）在独立 venv 里安装后跑 SDK 测试，`--import-mode=importlib`，不把源码目录放进 `PYTHONPATH`：

| 环境 | 依赖 | 结果 |
| --- | --- | --- |
| macOS arm64，pyenv Python 3.13.13 | NumPy 2.5.4，jsonschema 4.26.0 | 193 passed，2.65s；`pip check` 通过。这是本阶段唯一计入的解释器 |

Homebrew Python 3.11.15 也曾跑过同一 wheel 并得到 193 passed。它不是 pyenv，不计入本阶段。Linux、3.10、3.11、3.12 和最低依赖组合等到开发结束后，再用 pyenv 统一测。

## 教程命令

2026-10-15，pyenv Python 3.13.13 的独立 venv（`base_prefix` 为 `/Users/p.zhu/.pyenv/versions/3.13.13`，HEP 2.0.17）。`JARVIS_SAMPLERS_HOME` 和工作目录都在 `/tmp/jhs-doc01`，用的是 `examples/MyLatinHypercube.py` 和完整卡 `examples/MyLatinHypercube.task.yaml`。

`Jarvis sampler check --card` 按卡上的 32 个候选点通过，并报告 fresh process 从候选 16 重放尾段。`load` 登记 0.1.0，快照 `5efc4751a17e`。`Jarvis validate` 通过。`Jarvis run` 为 32 submitted、32 completed、0 failed。随后把工作文件改成 0.2.0 再 `load`，登记被替换为 `54d87e885532`。`Jarvis run --resume` 仍打印 `resuming with the scan's own copy 5efc4751a17e`，DATABASE 前缀保持 32。

这次正式扫描完成之后再跑 `Jarvis check`：正式 `DATABASE/sampler_identity.json` 和 `checkpoints/.../plugin/` 的 SHA-256 不变，身份仍是 0.1.0 / `5efc4751a17e`。smoke 写到 `DATABASE/test/` 和 `checkpoints/.../check/plugin/`，用的是当时已登记的 0.2.0 / `54d87e885532`。`run_summary` 仍写在正式扫描目录，和原生共享布局一致。

## 性能证据

2026-10-15，macOS 27.0.1，Apple M4 Pro，14 核，24 GiB。解释器是 pyenv Python 3.13.13（`/Users/p.zhu/.pyenv/versions/3.13.13`），测量进程用独立 venv 里的 HEP 2.0.17 与 SDK 0.1.0，NumPy 2.5.4。20 μs 仍是待校准目标，下面的数不是通过门槛。

适配器开销，每个维度 10⁵ 次。中位数 / p95：

| 维度 | `stream` + `rng.random` + `check_point` | `IndependentSession.point` | 无 Mapper 的 `physical_from_u` |
| --- | --- | --- | --- |
| 2 | 11.21 / 13.71 μs | 11.96 / 14.38 μs | 0.75 / 0.88 μs |
| 20 | 15.38 / 17.96 μs | 16.00 / 18.00 μs | 3.71 / 4.38 μs |
| 200 | 55.54 / 62.88 μs | 55.67 / 65.08 μs | 33.75 / 38.75 μs |

`session.point` 含一次常数 `draw`。这组数不含 selection、Sample、UUID 和 Redis。2 维和 20 维的点生成加分布映射低于 20 μs，200 维高于它。

物理计算吞吐用同一个 `MyLatinHypercube`，1 个 Worker，`batch_size` 1，`max_inflight` 4，24 个点。Worker 里的算子是 `sleepbox.hold`，只按 `JHS_PHYS_SEC` 睡觉。四次都是 24 completed、0 failed。采样进度走到 24/24 的时间，以及整次扫描的 wall：

| 物理耗时 | 采样进度 24/24 | 这段吞吐 | 整次 wall | wall 吞吐 |
| --- | --- | --- | --- | --- |
| 0 | 0.265 s | 90.6 /s | 5.399 s | 4.45 /s |
| 1 ms | 0.269 s | 89.2 /s | 5.565 s | 4.31 /s |
| 100 ms | 2.191 s | 11.0 /s | 6.711 s | 3.58 /s |
| 1 s | 20.256 s | 1.18 /s | 28.36 s | 0.85 /s |

1 ms 和 0 落在同一段采样时间里，框架开销盖过这 1 ms。100 ms 和 1 s 被单个 Worker 串行睡觉卡住：进度时钟分别约每点 0.1 s 和 1 s，开头 4 个在飞点先提交出去。wall 含 Redis 启动、收尾和作图，所以低于采样窗口里的吞吐。

报告 hook 连续失败用 `IndependentSession` 直接调用。`settings_rows`、`summary_rows`、`stop_reason`、`status` 各抛错 1000 次，共 4000 次。日志在第一轮之后是 312 字节、4 行，1000 轮之后仍是 312 字节、4 行。`hook_errors` 保留 4 条。进程 RSS 从 75024 KiB 到 75360 KiB。重复报错没有随调用次数长日志。

## M2 联合故障验收

SAM-QA-02 本机范围完成，并新增、关闭 SAM-HEP-03。四组 checkpoint/DB-only × worker/batch=(1,3)/(2,5) 的真实 Redis/spawn 恢复均与不中断参考相同：37候选、22 accepted、17 Completed+5 Failed、22唯一UUID，只计算17个缺失点；末11个拒绝候选不进入物理计算。稀疏 DATABASE 是明确构造的 crash-state，真实 SIGINT 中断证据另行保留。

全22个accepted已durable时，两种恢复均只完成selection拒绝尾段，新提交/Worker计算均0、科学行22不变。运行中reload/remove两组各37点通过，含移除后SIGINT及无登记恢复。实际Redis和两个Worker启动后注入失败，退出后全部清理、0科学行，fresh提示`--resume`；更新/移除、漂移拒绝之后仍按原v1成功恢复8点。

SDK源码与完整构件安装测试各 **193 passed**、Ruff通过；HEP最终fast gate为 **1519 passed、478 subtests passed、3 skipped、179 slow deselected**。安装包 **23个不同定向用例** 通过（19个M2新增、4个既有真实check/SIGINT）；具体命令有重复矩阵与夹具复验，数量不相加作为唯一用例数。wheel/sdist、Twine、完整依赖安装、pip check及7个实现源码hash一致均核验。两次独立实现审阅无阻断。

命令、实际环境、产品失败与夹具修正、完整包和证据范围见 [M2验收记录](M2_VERIFICATION.md)，机器证据在HEP `docs/jarvis-hep-sampler/native-parity-m2-verification.json`。不调整插件API或版本、不提交/发布；M3远程OS/Python/最低依赖组合、Books最终同步及性能证据仍开放。显式改源恢复、内置身份推广与generational保持后续范围。

RunOutcome在当次零新增任务时仍可能回显历史终态的submitted=22，保留原生统计语义；零新增计算依据实际提交返回值、Worker调用和科学行对照。恢复仍是at-least-once，不承诺崩溃前未落盘的物理调用恰好执行一次。

## 文档同步规则

本台账作为本轮任务和状态入口；[开发文档](DEVELOPMENT.md)维护模块边界，[作者指南](PLUGIN_AUTHORING.md)维护插件合约。HEP 实现阶段同时更新其五份 canonical 文档及 `docs/jarvis-hep-sampler/technical-design.md`，用链接引用任务和证据，避免分散维护冲突状态。

技术设计首页已明确更正“五份 canonical 文档不存在”和旧维护权限层级，更新当前基线并保留具日期的历史验证。技术设计也澄清：插件 prepare 失败不发布绑定，后续资源启动失败可能保留已发布绑定。M2 已用真实 managed Redis/两 Worker 启动后故障验证清理与原绑定 `--resume`；prepare 单测仅证明其资源启动前的边界。
