# 外部采样器 M2 验收记录

日期：2026-10-15，Australia/Adelaide。M2 本机联合故障和原生闭环验收完成，SAM-QA-02 关闭本机范围；M3 远程兼容、最低依赖组合和 Jarvis-Books 最终同步仍开放。

SDK 基线`cf924cb`/0.1.0沿用M1工作区实现；HEP验收基线`569d3865`/2.0.17加7个sampler实现文件。并行Redis/monitor发行工作与Diver等改动保留，本轮Sampler未提交或发布。M1的HEP2.0.16记录保持为历史。

## 修复与验收

新增SAM-HEP-03：reader已返回DATABASE连续prefix之外的durable索引，但运行服务未传递给采样器。prefix=2、pending={3,6,8}时，这三行被再次计算，最终22个唯一结果却等待25行，触发archive drain stalled。现由宿主保留并传递pending，FixedSet在propose/selection推进后的提交边界去重，返回实际push数。Failed与Completed同样终态；pending采用DATABASE重建的内存副本，不写checkpoint或累计全历史UUID。

CLI/YAML、插件API v1、STREAM_PROTOCOL=1、registry format=1和科学身份/安全checkpoint校验均不变。补丁覆盖外部PluginSampler及其FixedSet基类，不概括为CSV、全部内置方法或反馈算法改造。真实中断仍允许重算崩溃前未落盘的调用，不承诺物理计算exactly-once。

| 场景 | 实际结果 |
| --- | --- |
| 空洞+混合失败批次+拒绝尾段，checkpoint/DB-only×(worker1,batch3)/(worker2,batch5) | 4组真实Redis/spawn通过；只计算17个缺失点，最终22行/22唯一UUID，17 Completed+5 Failed，candidate/accepted=37/22，与不中断参考逐行一致 |
| 22 accepted全部durable，仅剩末11候选全拒绝 | 2组通过；新提交0、Worker计算0、DATABASE22不变；checkpoint draw块[3,4]，DB-only控制端重放[0..4]，无超时 |
| 运行中load v2/remove | (worker1,batch1)继续完成；(worker2,batch4)SIGINT130后无登记resume成功；每组37点，坐标/UUID完全一致，binding保持v1，用户v2工作文件保留，新run退出2 |
| 已绑定后资源启动失败 | 故障时managed Redis和两个Worker实测alive；失败退出1后均清理、0科学行；fresh明确提示--resume；reload/remove及配置/源码拒绝后按原v1恢复8点 |
| 提交/状态边界fast回归 | 6项，含pending reader、实际push数、全过滤batch安全capture、setter复制/替换、export不随pending增长、Random单槽backpressure |

## 最终门禁

| 验证 | 结果 |
| --- | --- |
| SDK源码与完整构件安装测试、Ruff | 各193 passed，Ruff通过；SDK运行实现与M1相同，M2文档已进入新构件，Twine/全依赖安装/pip check及smoke通过 |
| HEP完整fast gate | **1519 passed、478 subtests passed、3 skipped、179 slow deselected** |
| 安装包真实运行/恢复 | **13 passed**：M2新增9个slow及既有真实check/SIGINT4项 |
| 最终隔离安装包联合矩阵 | **10 passed**：6 fast+4 slow（4个slow与上一行重复） |
| 最终唯一名称的安装包启动/尾段 | **7 passed**：4 fast+3 slow（3个slow重复复验） |
| 构件与环境 | wheel/sdist、Twine、正常全依赖安装、pip check通过；7个HEP实现与源码一致，SDK全部Python源码与已安装包一致 |

上述安装包命令共30次通过，覆盖23个不同用例：19个M2新增及4个既有真实回归。重复复验不计为新增测试。新实现另有97项定向和两次独立静态审阅证据。

首轮full fast为1 failed、1518 passed：固定startup_recovery名称与并行slow验收冲突，原生全机同名scan保护正确拒绝。测试改为临时目录hash唯一名称并保留原生保护后全量重跑通过。联合矩阵早期的selection语法、并发重名，以及active测试先读到正常乱序行的观察竞态，均单列为夹具修正；产品缺陷证据是独立保留的22/25归档超时。

## 安装与复验

本机macOS arm64、Python3.13.13；完整依赖venv为HEP2.0.17、SDK0.1.0、NumPy2.5.4、jsonschema4.26.0、Operas1.5.0、PLOT2.1.10。复用M1已全依赖安装的独立venv，正常安装M2完整wheel；没有editable、--no-deps或产品PYTHONPATH注入，主子进程均由venv解释器从site-packages导入。

带Git元数据的隔离源码快照用于full fast，明确覆盖7个实现和7个M1/M2新增测试文件；保留并排除未提交Diver/package-data及审阅草稿。测试registry、项目、扫描名、scan refs和相关cache使用临时资源。

```bash
<venv>/bin/python -m pytest -q -m 'not slow' -p no:cacheprovider
# cwd在checkout外，使用完整安装包；实际绝对路径见机器记录
<venv>/bin/python -m pytest -q --import-mode=prepend -o pythonpath= -m slow <6个运行测试文件>
<venv>/bin/python -m pytest -q --import-mode=prepend -o pythonpath= -o addopts= <test_plugin_resume_fault_matrix.py>
<venv>/bin/python -m pytest -q --import-mode=prepend -o pythonpath= -o addopts= <test_plugin_startup_recovery.py> <test_plugin_rejected_tail.py>
```

RunOutcome在零新任务时submitted回退22个历史终态，保持原生统计语义；零计算验收依据actual_new_submitted=0、Worker调用记录和DATABASE对照。check的保护范围仍是正式科学DATABASE、bound source和checkpoint，通用runtime/log/summary布局保持原生行为。

持久机器证据在HEP `docs/jarvis-hep-sampler/native-parity-m2-verification.json`，含准确命令、原始失败、环境/构件/实现/测试hash及场景摘要。原始日志位于`/private/tmp/jhs-m2/`、`/private/tmp/jhs-m2-fault-matrix-hy6pjzyf/`和各agent隔离验收目录；临时目录可能被清理。[开发台账](DEVELOPMENT_LEDGER.md)维护当前状态，[M1记录](M1_VERIFICATION.md)保留前一阶段历史。
