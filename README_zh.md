# AutoGDS：基于智能体的自动光子芯片 GDS 设计器

>注:中文版README由英文版机翻而来，个别词句可能不够通顺。

## 背景与动机
**硅基光子集成电路（`PICs`）** 已成为成熟的产业平台，数据中心、通信、传感以及新兴 AI 硬件不断推动其需求增长。典型的 PIC 设计流程从物理建模（`FEM/FDTD`）开始，经过参数扫描与优化，最终走向 **光刻掩膜** 版图设计并生成可制造的 **`GDS`**。在 GDS 中，器件几何与层信息必须精确、可制造，并与代工厂的工艺设计包（`PDK`）一致。

尽管产业成熟，PIC 设计流程依旧耗费人力：许多环节需要专家把需求翻译为几何结构、验证约束并迭代。因此引入 **AI 辅助** 的需求非常强烈。已有研究多集中于某个器件或某一类器件的 **逆向设计** 神经网络，但其泛化能力有限，难以真正提升硅光产业的整体效率。

本课程项目 AutoGDS 是我本科毕业论文的第一步。长期目标是构建一个 **多智能体** 的 PIC 设计助手：从 **自然语言** 需求出发，智能体将自动理解规格、运行仿真、优化性能指标、确定几何与参数，并最终生成可制造的 `GDS` 掩膜。

当前 AutoGDS 聚焦于该愿景的最后一步：**给定以自然语言表达的几何与参数，系统通过智能体生成具体的 `GDS` 版图**，从而将工程师从最繁琐的版图环节中解放出来。

本项目目前包含约 **12,158 行 Python 代码**（不含虚拟环境），开发与测试所用的 API Key **均由本人自费**。

## 项目结构
```
AutoGDS_v1/
├── src/                             # 源码包（Python）
│   └── autogds/                     # 核心流水线模块
│       ├── cli.py                   # CLI 入口
│       ├── flow.py                  # 端到端流程编排
│       ├── topology.py              # 拓扑规划逻辑
│       ├── layout_*.py              # 布局放置/布线/导出阶段
│       ├── verify.py                # 验证检查
│       └── ...                      # 其他流水线工具与 schemas
├── KnowledgeBase/                   # 设计知识与组件
│   ├── DesignLibrary/               # 光子器件组件库
│   │   ├── mzi_2x2_heater_tin_cband.py  # 示例：MZI 组件
│   │   ├── _mmi1x2.py                # 示例：MMI 分光器
│   │   └── ...                      # 其他光子组件
│   ├── FDTD/                        # FDTD 数据资产
│   └── __init__.py                  # 包标记
├── docs/                            # 项目文档
│   ├── ARCHITECTURE.md              # 流水线概览
│   ├── PROMPT_PATTERNS.md           # Prompt 模式与技巧
│   └── TROUBLESHOOTING.md           # 排错指南
├── results/                         # 示例运行输出与图
│   ├── Figures/                     # README 使用的图片
│   ├── Level 1-1/                   # Level 1 示例输出
│   └── ...                          # 其他 Level 文件夹
├── GETTING_STARTED.md               # 教程与用户指南
├── sample_prompts.md                # 按难度分级的 prompt 示例
├── requirements.txt                 # 最小依赖
├── pyproject.toml                   # 打包与构建配置
└── README.md                        # 本文件(英文版)
└── README_zh.md                     # 本文件(中文版)
```

**使用指南见 `GETTING_STARTED.md`。**

## 已实现功能
AutoGDS 当前实现了一个端到端的 **强制输出（force-output）** 流程：即使约束不完美，每次运行仍会输出完整工件集合。该流程以 **组件为中心**，不依赖模板，只要布局后端可用，即可生成实际的 `GDS`。

系统功能包括：
- 将自然语言提示解析为结构化 `brief.json`（包含角色、数量与连线说明）。
- 生成拓扑图（`topology_plan.json`），定义端口形式与连接意图。
- 从元件库检索候选组件，并依据契约元数据（端口、标签、规格）进行排序。
- 将参数与逻辑端口绑定为具体 `blueprint.json`。
- 产出布局工件（`layout_*.json`）与最终 `layout.gds`。
- 生成验证报告，但不会中断流程。

示例（分束器树）：
- 提示词：`Layout 1x2 MMIs connected to each other for a 1x8 splitter tree`
- `brief.json` 将需求展开为 **7 个分束器**，组成 **3 级二叉树**。
- `topology_plan.json` 包含 7 个节点（`n0`–`n6`）与 6 条连接。
- `selection.json` 将每个节点解析为 `_mmi1x2`。
- `blueprint.json` 将逻辑端口（`in0/out0/out1`）映射为物理端口（`o1/o2/o3`）。
- `layout_emit.json` 报告无问题并生成非空 `layout.gds`。

这些工件保证了完整透明性：每一步决策、绑定与路由都可检查或复现。

## 架构与方法
AutoGDS 采用 **文档优先（document-first）** 的流水线：每一步产出带类型的 JSON 工件，将系统状态冻结为可机器读取的契约。这一设计对光子学尤为关键：自由文本无法可靠描述几何或端口逻辑，而结构化 schema 可以。通过强制显式工件，AutoGDS 具备 *可解释*、*可审计*、*可复现* 的特性。

1) **解释：自然语言 -> 结构化 Brief（AI 智能体）**
   - **目的：** 将人类意图转换为可执行的机器表示。
   - **为何使用结构化 JSON？** 光子设计依赖精确的端口数量、组件角色与约束。自然语言无法稳定驱动下游，而 `DesignBrief` 是带字段的 schema（角色、数量、连线说明、目标等），确保每一步输入清晰。
   - **方法：** 由 LLM 解析并归一化提示，生成 `brief.json`，作为智能体与确定性流水线之间的契约。

2) **拓扑规划：抽象图构建（确定性）**
   - **目的：** 在选择具体器件前先定义组件图。
   - **为何单独的拓扑阶段？** PIC 设计本质是 **网络问题**，拓扑应独立于具体器件。
   - **方法：** 基于规则解析端口形式（`NxM`）、端口数量与连线说明；若提示隐含标准结构（如分束器树），则实例化对应图模板。
   - **工件：** `topology_plan.json` 记录节点、意图与顶层端口。

3) **组件检索与选择：候选排序（AI 辅助）**
   - **目的：** 将抽象节点绑定到实际元件库器件。
   - **为何需要 AI？** 目录元数据半结构化，“最佳”组件往往是语义匹配而非字符串匹配。
   - **方法：** 文本相似度排序 + **基于契约的重排序**（端口形式匹配、标签/规格命中、参数签名兼容性）。
   - **工件：** `options_node_*.json`（候选列表）与 `selection.json`（最终选择）。

    **DesignLibrary 及其来源。** AutoGDS 依赖一个参数化光子组件的 `DesignLibrary`。该库以可机读的 docstring（端口、标签、规格、参数）组织，用于语义检索与确定性绑定。该组织方式借鉴并致谢 *APL Mach. Learn. 3, 046113 (2025)*。

4) **绑定：参数与端口（确定性 + AI 提示）**
   - **目的：** 将逻辑端口和参数解析为具体设计。
   - **方法：** 用 `ComponentContract` 将逻辑端口（`in0/out0`）映射到物理端口（`o1/o2/...`）；从注释中抽取数值约束（单位与同义词，如 `delta_length`），并验证参数签名。
   - **工件：** `blueprint.json`（解析后的端口、参数与链接）。

5) **验证：结构一致性检查（确定性）**
   - **目的：** 保持强制输出，同时暴露问题。
   - **方法：** 检查缺失端口、无效链接与映射冲突。错误被记录但不打断流程。
   - **工件：** `verify_report.json`。

6) **版图生成：几何与 GDS（确定性）**
   - **目的：** 将 `blueprint` 转换为物理几何。
   - **方法：** 足迹估计 -> 放置 -> 路由 -> 预检查 -> GDS 输出。
   - **算法：** 基于图深度的分层放置、曼哈顿路由与碰撞规避、基于 gdsfactory 的 GDS 后端。
   - **工件：** `layout_*.json` 与最终 `layout.gds`。

该架构确保 AI 用于不确定环节（解释与语义选择），其余环节保持确定、可检查、可复现。

## 结果
1) **提示词分级**

    为评估 AutoGDS 的性能，我们将提示词按复杂度划分为四级：
    
    - **Level 1：** 1 个组件
    - **Level 2：** 2 个组件且只有一条连接
    - **Level 3：** 3–10 个组件
    - **Level 4：** 10+ 个组件

    在 `sample_prompts.md` 中，每一等级给出 4 个样例，运行结果位于 `results` 目录。

2) **运行示例**
    
    使用 Level 3 提示词展示完整流程：

    `Four microrings with heaters, arranged in an array along the y direction, each connected to a grating coupler.`
    - 在虚拟环境中启动 AutoGDS，输入提示词

   ![运行示例提示词](results/Figures/Fig1.png)

    - 从候选列表中选择组件

    ![运行示例提示词](results/Figures/Fig2.png)
    ![运行示例提示词](results/Figures/Fig3.png)

    - 返回输出文件夹与工件

    ![运行示例提示词](results/Figures/Fig4.png)

    - 在文件管理器中打开文件夹，并用 `KLayout` 查看 GDS

    ![运行示例提示词](results/Figures/Fig5.png)

3) **样例提示词结果**
- Level 1：单组件

   `A 2x2 MZI.`

   ![运行示例提示词](results/Figures/1-1.png)

   `A four-channel WDM.`

   ![运行示例提示词](results/Figures/1-2.png)

   `Directional coupler with a 0.5um gap and 50um coupling length.`

   ![运行示例提示词](results/Figures/1-3.png)

   `A microring with coupler and heater.`

   ![运行示例提示词](results/Figures/1-4.png)

- Level 2：两组件且只有一条连接

   `Two cascaded MZIs, each with TiN heaters for C-band operation. The device should have 500 nm wide waveguides and 10 um long heaters. Both MZIs have two input/output ports.`

   ![运行示例提示词](results/Figures/2-1.png)

   `Connect a 2x2 MZI with heaters to a grating coupler. Port 1 to port 0.`

   ![运行示例提示词](results/Figures/2-2.png)

   `Connect a 2x2 MZI with heaters to a grating coupler. Port 0 to port 0.`

   ![运行示例提示词](results/Figures/2-3.png)

   `Connect a 1x2 splitter to a 1x1 microring resonator.`

   ![运行示例提示词](results/Figures/2-4.png)
    
- Level 3：3–10 个组件

   `Layout 1x2 MMIs connected to each other to for a 1x8 splitter tree.`

   ![运行示例提示词](results/Figures/3-1.png)
   
   `A power splitter connected to two 1*1 MZIs with doped heaters each with a path difference 100 um. The two output ports of the splitter are the input ports of the two MZIs respectively.`

   ![运行示例提示词](results/Figures/3-2.png)

   `Eight low loss and low power thermo optic phase shifters. The phase shifters should be arranged in parallel along the y direction in an array.`

   ![运行示例提示词](results/Figures/3-3.png)

   `Four microrings with heaters, arranged in an array along the y direction, each connected to a grating coupler.`

   ![运行示例提示词](results/Figures/3-4.png)

- Level 4：10+ 个组件

   `A 1x16 splitter tree built from 1x2 MMIs.`

   ![运行示例提示词](results/Figures/4-1.png)

   `A 3x4 mesh of 2x2 MZIs with back‑to‑back connections between adjacent nodes.`

   ![运行示例提示词](results/Figures/4-2.png)

   `Sixteen thermo‑optic phase shifters arranged in a 4x4 mesh.`

   ![运行示例提示词](results/Figures/4-3.png)

   `A 1x8 splitter tree using 1x2 MMIs, and connect each output to a grating coupler.`

   ![运行示例提示词](results/Figures/4-4.png)

4) **重复性测试**

为测试工作流的重复性，我们对 16 个样例提示词各运行 10 次，统计设计准确率并分析误差来源。

- **准确率**

| Level \\ No. | 1 | 2 | 3 | 4 |
|---:|---:|---:|---:|---:|
| 1 | 0.5 | 0.6 | 0.7 | 1.0 |
| 2 | 0.9 | 1.0 | 1.0 | 1.0 |
| 3 | 0.8 | 0.5 | 1.0 | 0.7 |
| 4 | 0.9 | 0.9 | 1.0 | 0.0 |

![运行示例提示词](results/Figures/Fig6.png)

准确率并未随复杂度等级明显下降，说明规模效应不显著。

总体准确率为 **84.4%**，且每个案例不低于 50%，显示出较好的可复现性。

- **错误来源**

![运行示例提示词](results/Figures/Fig7.png)

三类错误如下：

*组件识别错误*（9%）：目标器件未出现在候选列表中，或被要求选择多余/不足的组件。

*参数赋值错误*（5%）：提示中的参数要求未被捕获，导致使用默认参数。

*拓扑布局错误*（1%）：器件拓扑不正确，涉及空间布局或端口关系。

这些错误反映了当前流水线中仍存在的语义歧义。组件识别错误通常源于组件库词汇不全或提示中的同义词未覆盖，导致语义检索无法锁定意图。解决方式是扩展组件别名与元数据、强化角色过滤，并在高分候选相近时加入轻量级用户确认。

参数赋值错误主要来自自然语言约束嵌于长句、单位混杂或同义词表达（如“differential path length”）。可行的解决方案是更强的单位归一化、建立组件参数 schema，并在关键参数处允许结构化短语（例如 `delta_length=100um`）。

拓扑错误虽然比例低但影响大，常由“cascade”“mesh”“array”等词歧义以及端口顺序约定不一致导致。解决办法是规范拓扑模板、显式声明端口顺序，并在布局前做端口形式校验，尽早发现错误连线。

## 展望与改进
AutoGDS 可以通过加入 **实时交互闭环** 来提升可靠性：在 UI 中展示中间工件（`brief.json`、`topology_plan.json`、`selection.json`、`blueprint.json`），允许用户即时校正并从检查点继续。通过允许用户实时交互纠错，可直接提升成功率并减少重复运行。

另一个近期方向是建立 **更强的约束系统**：当前许多修复依赖启发式，若引入声明式约束层，可验证范围、统一单位并提前拒绝歧义绑定，从而避免错误的加热器长度或端口形式不匹配。

AutoGDS 还需要 **布局感知的拓扑规划**。规划器可基于粗略足迹与路由成本，在等价结构中选择更易布线的方案（如平衡/非平衡树），使拓扑决策兼顾几何可行性。

**DesignLibrary 覆盖面** 也应扩展并规范化。加入更多参数化器件（调制器、探测器、滤波器等），并统一 docstring 风格，可提升检索召回率与选择质量。带测试的版本化组件库将进一步稳定流程。

路由可以采用 **渐进式细化**：先做快速初始路由，再仅对问题连线进行局部重路由（绕行或分层通道）。这比一次性曼哈顿路由更稳健，并能扩展到大规模图。

最后，AutoGDS 需要 **自动评测与基准**。标准提示词集及通过/失败判据（非空 GDS、端口数量正确、无交叉）可量化改进，并与回归测试结合防止新改动破坏既有能力。

在本科毕业论文阶段，我希望实现一个 **全流程光子设计智能体**，覆盖器件仿真与版图的完整链路：从自然语言规格出发，选择参数化模板，运行快速代理模型（或降阶模型）评估指标，并在约束优化中迭代几何，最终输出 GDS。多阶段集成能让系统同时考虑性能与可制造性，显著减少试错并加速设计探索，使高门槛的光子设计更易于普及。

我需要经费与团队才能继续推进这一目标，因此将其留到课程结束之后。做点大事！