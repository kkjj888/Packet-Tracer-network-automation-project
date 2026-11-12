# LLM 驱动的网络拓扑自动生成与安全部署

## 项目进度与技术架构

更新日期：2026-11-12  
当前分支：`main`  
当前状态：后端 YAML 到 Packet Tracer 的配置与自动验收闭环已打通

## 1. 项目目标

项目最终目标是让 Agent 根据自然语言需求完成：

```text
自然语言需求
→ 生成结构化网络意图
→ 静态校验和安全校验
→ 生成可执行配置
→ 在本地 Packet Tracer 中部署
→ 自动连通性、路由和路径验收
→ 自动定位并修复错误
→ 输出可复现的报告和审计日志
```

项目只操作本地 Packet Tracer 仿真环境，不连接真实网络设备、校园网或公网地址。

## 2. 当前阶段结论

当前已完成不依赖 Agent 的后端基础设施：

- YAML 网络 DSL
- JSON Schema 校验
- 网络语义校验
- IOS 命令安全校验
- 拓扑和主机配置
- 各配置模块的确定性命令模板
- YAML 编译为部署计划
- Packet Tracer 实际部署
- Ping 正反验收
- 路由表断言
- Traceroute 路径断言
- DHCP 租约回读
- NAT 转换表回读
- 链路故障和浮动静态路由切换
- PKT 保存、重新打开和再次验收
- JSON 报告与 JSONL 审计

Agent 层、前端、通用 RepairEngine 和定量评估尚未完成。

## 3. 端到端技术路线

```text
用户需求
    │
    ▼
YAML DSL
    │
    ├── PyYAML 解析
    ├── JSON Schema 结构校验
    ├── 网络语义校验
    └── 命令安全校验
    │
    ▼
DSL Compiler
    │
    ├── TopologySpec
    ├── HostAddressConfig
    ├── DHCPClientConfig / LinkFailure
    ├── CommandPlan[]
    ├── RouteAssertionSpec[]
    └── TracerouteSpec[]
    │
    ▼
Packet Tracer 部署器
    │
    ├── Python HTTP Bridge
    ├── PT Script Module
    ├── PT Script Engine
    └── PT 原生 ipc.* JavaScript API
    │
    ▼
自动验收
    │
    ├── 静态 IP / DHCP 租约回读
    ├── Ping 正反矩阵
    ├── 路由表结构化断言
    ├── Traceroute 完整路径断言
    ├── NAT 转换表
    ├── 保存和重新打开
    └── 重开后再次执行验收
```

## 4. 代码架构

```text
bonus/
├── pt_agent/
│   ├── cli.py                  # CLI、场景编排、部署与验收
│   ├── script_bridge.py        # 本地 HTTP 桥
│   ├── script_backend.py       # PT JavaScript / ipc.* 调用生成
│   ├── validation.py           # Schema、语义、安全校验
│   ├── dsl_compiler.py         # YAML → 部署计划
│   ├── dsl_deployment.py       # 验收结果计算
│   ├── diagnostics.py          # 主机地址确定性诊断
│   ├── audit.py                # JSONL 审计日志
│   ├── config_suite.py         # 固定场景与旧集成测试辅助
│   └── compiler/
│       ├── base.py             # CommandPlan、统一配置包装
│       ├── interface.py        # 接口和 dot1Q 子接口
│       ├── vlan.py             # VLAN 与 access 端口
│       ├── trunk.py            # 802.1Q Trunk
│       ├── acl.py              # 标准 ACL
│       ├── static_routing.py   # 静态和默认路由
│       ├── rip.py              # RIPv1 / RIPv2
│       ├── ospf.py             # OSPFv2 和 wildcard mask
│       ├── dhcp.py             # DHCP Pool
│       └── nat.py              # NAT/PAT
├── schema/
│   └── network.schema.json     # YAML DSL JSON Schema
├── examples/                   # 10 个可部署 YAML 场景
├── tests/                      # 单元与示例测试
├── docs/
│   └── DSL_VALIDATION.md       # DSL 和验收说明
├── artifacts/                  # PKT、JSON 报告和 JSONL 审计（Git 忽略）
├── vendor/                     # 验证用 PT Script Module
├── README.md
├── CONFIGURATION_TEST_REPORT.md
└── PROJECT_STATUS.md
```

## 5. YAML DSL

当前 DSL 支持：

- `devices`
- `links`
- `ipv4`
- `vlans`
- `vlan_assignments`
- `routing.static`
- `routing.rip`
- `routing.ospf`
- `acls`
- `acl_bindings`
- `dhcp.pools`
- `dhcp_clients`
- `nat.pat`
- `link_failures`
- `verification.connectivity`
- `verification.route_assertions`
- `verification.traceroute_tests`

其中 Router-on-a-Stick 子接口通过以下字段表达：

```yaml
- device: r1
  port: GigabitEthernet0/0.10
  parent_port: GigabitEthernet0/0
  dot1q_vlan: 10
  address: 192.168.10.1/24
```

## 6. 三层校验

### Schema 校验

检查：

- 必填字段
- 字段类型
- 枚举值
- 数值范围
- 标识符与端点格式
- 顶层和嵌套对象的未知字段

### 网络语义校验

检查：

- 设备和链路引用
- 重复设备、IP 和端口
- 网络地址、广播地址误用
- 网关是否在子网内
- VLAN 和 ACL 引用
- 静态路由 next-hop 可达性
- OSPF network 连续性及连接接口
- Trunk allowed/native VLAN
- DHCP Pool、排除地址和连接网段
- NAT inside/outside 接口
- 链路故障端口是否真实连接
- 验收来源、目标、路由和跳点

### 命令安全校验

当前安全机制：

- IOS 命令允许列表
- 危险命令黑名单
- 多行命令拦截
- Shell 类注入字符拦截
- 命令数量上限
- 命令模板输出自动再次校验

已拦截的危险命令包括：

- `reload`
- `write erase`
- `erase startup-config`
- `format`
- `delete`
- `confreg`
- `debug all`
- `no ip routing`

## 7. 命令模板

LLM 不直接生成并执行原始命令。配置由确定性编译器生成：

```text
结构化参数
→ 参数合法性检查
→ 命令模板
→ CommandSafetyValidator
→ CommandPlan
```

已实现：

- Router IPv4 接口
- Router-on-a-Stick 子接口
- VLAN 和 access 端口
- Trunk
- 标准 ACL 和接口绑定
- 静态/默认路由
- RIP v1/v2
- OSPF process、wildcard mask、area
- DHCP Pool
- NAT/PAT

## 8. 自动部署与验收

主要命令：

```powershell
python -m pt_agent validate-dsl examples\campus-vlan.yaml
python -m pt_agent compile-dsl examples\campus-vlan.yaml
python -m pt_agent deploy-dsl examples\campus-vlan.yaml
```

`deploy-dsl` 当前流程：

1. 加载和校验 YAML
2. 编译部署计划
3. 新建 PKT
4. 创建拓扑和链路
5. 配置静态主机地址
6. 逐设备执行 CommandPlan
7. 配置 DHCP 客户端
8. 等待协议收敛
9. 执行 Ping 验收
10. 执行路由表断言
11. 执行 Traceroute 断言
12. 读取 DHCP 租约
13. 读取 NAT 转换表
14. 注入链路故障并再次验收
15. 保存 PKT
16. 重新打开 PKT
17. 重开后重复验收
18. 输出 JSON 报告和 JSONL 审计

## 9. 验收类型

### 连通性

支持预期成功和预期失败：

```yaml
verification:
  connectivity:
    - name: expected-pass
      source: pc1
      destination: pc2
      expected: pass
```

### 路由表

```yaml
route_assertions:
  - device: r1
    destination: 172.16.20.0/24
    protocol: ospf
    next_hop: 10.0.0.2
    admin_distance: 110
```

支持协议：

- `connected`
- `local`
- `static`
- `rip`
- `ospf`

### Traceroute

```yaml
traceroute_tests:
  - name: path-check
    source: pc1
    destination: pc2
    expected_hops:
      - 172.16.10.1
      - 10.0.0.2
      - 172.16.20.20
```

要求 `Trace complete` 且实际跳点与期望序列完全一致。

## 10. 当前 YAML 场景

| 场景 | 主要内容 | 当前状态 |
|---|---|---|
| `campus-vlan.yaml` | VLAN access、跨交换机 Trunk、隔离 | PASS |
| `inter-vlan-routing.yaml` | 单臂路由、dot1Q 子接口 | PASS |
| `acl-routing.yaml` | ACL deny 与 permit | PASS |
| `static-routing.yaml` | 默认与回程静态路由 | PASS |
| `ripv1-routing.yaml` | RIPv1 自动汇总限制 | PASS |
| `ripv2-routing.yaml` | RIPv2 + no auto-summary | PASS |
| `ospf-routing.yaml` | OSPF wildcard 和 area | PASS |
| `dhcp-lan.yaml` | DHCP Pool、租约和静态服务器 | PASS |
| `nat-pat.yaml` | 内网经 PAT 访问公网侧服务器 | PASS |
| `floating-static-failover.yaml` | 主备默认路由和链路故障切换 | PASS |

10 份真实 PT 部署报告均为 `passed`。

## 11. 关键测试证据

- VLAN：同 VLAN 4/4，跨 VLAN 0/4
- ACL：拒绝源 0/4，允许源 4/4
- Inter-VLAN：Ping 4/4，路径 `192.168.10.1 → 192.168.20.20`
- Static：Ping 4/4，路径 `172.16.10.1 → 10.0.0.2 → 172.16.20.20`
- RIPv1：预期失败 0/4
- RIPv2：Ping 4/4，RIP 路由 AD 120
- OSPF：Ping 4/4，OSPF 路由 AD 110
- DHCP：PC1 获取 `192.168.10.2/24`
- NAT：`192.168.0.1` 转换为 `203.0.113.253`
- Floating Static：基线、主链路断开后、重开后均为 4/4

## 12. 测试和 Git

当前：

- 79 个单元测试全部通过
- 10 个 YAML 端到端场景全部通过
- Git 工作区干净
- 尚未配置 GitHub/Gitee 远程仓库

当前提交规范：

```text
测试前：
Test project: <当前测试项目> - test <序号>

完成模块：
Complete module: <模块名称>

修复 Bug：
Fix: <修复内容>

测试结束：
Test completed: <测试项目>
```

## 13. 对照评分标准

| 维度 | 当前状态 | 主要缺口 |
|---|---|---|
| A. 拓扑 DSL 与意图生成 | DSL、Schema 已完成 | Agent 自然语言生成未接 |
| B. 配置生成与静态校验 | 配置模板、语义与安全检查已完成 | Batfish 语义分析和更多复杂场景 |
| C. 安全部署与验证 | 部署、Ping、路由、Traceroute、重开已完成 | 通用自动修复和更多故障类型 |
| D. 定量评估与报告 | 已有 10 个场景 | 指标汇总、失败案例和最终报告 |
| E. 安全护栏 | 白名单、黑名单、审计已完成 | Agent 部署前 CONFIRM 门 |

## 14. 尚未完成

### 通用 RepairEngine

当前只对主机掩码错误进行了自动修复。尚未覆盖：

- 主机 IP 和网关
- 路由器接口
- VLAN 和 Trunk
- ACL 规则与方向
- 静态路由
- RIP/OSPF network
- DHCP
- NAT

目标修复闭环：

```text
验收失败
→ 读取 PT 状态
→ 结构化诊断
→ 最小修复计划
→ 安全校验
→ 修复
→ 最多 3 轮复验
→ 审计
```

### Agent

尚未实现：

- 自然语言 → YAML
- Schema/语义错误反馈给 Agent
- Agent 最多 3 轮 YAML 修正
- Agent 失败案例记录
- Agent 与 RepairEngine 协作

### 定量评估

尚未实现统一基准运行器：

```powershell
python -m pt_agent benchmark-dsl examples
```

需要统计：

- 拓扑生成正确率
- 配置一次通过率
- Ping/路由/Traceroute 验收通过率
- 平均故障修复轮数
- Agent YAML 一次生成成功率

### 其他配置范围

- IPv6
- IPv6 over IPv4 隧道
- BGP
- DHCP Relay
- 路由协议认证
- HSRP/VRRP
- 更复杂的 ACL 和 NAT 规则

### 生产级 Script Module

当前 `vendor/mcp-bridge.pts` 只用于本地验证，尚缺：

- token 鉴权
- request ID 与结果关联
- 更严格命令白名单
- 文件邮箱回退
- 超时和重试策略

### 前端与交付

- Agent 前端
- 5 分钟演示流程
- 最终 PDF 报告
- 10 个需求的定量汇总
- 2 个 LLM 失败案例分析
- GitHub/Gitee 私有远程仓库

## 15. 下一阶段建议

推荐顺序：

```text
1. 通用 RepairEngine
2. 故障注入和自动修复测试
3. 10 场景定量基准
4. Agent 自然语言 → YAML
5. 部署前 CONFIRM 门
6. 失败案例分析
7. 前端和最终报告
8. 生产级 Script Module
```

当前最具体的下一项是：

> 建立 `pt_agent/repair/`，先实现主机地址、网关、路由器接口和 VLAN 四类确定性修复，并为每类建立“注入故障 → 检测 → 最小修复 → 复验”的测试。

## 16. 常用命令

```powershell
python -m pt_agent --help
python -m pt_agent doctor
python -m pt_agent validate-dsl examples\campus-vlan.yaml
python -m pt_agent compile-dsl examples\campus-vlan.yaml
python -m pt_agent deploy-dsl examples\campus-vlan.yaml
python -m unittest discover -s tests -v
```

## 17. 工程风险

- `cli.py` 仍包含较多场景编排代码，后续可拆分 deployment、acceptance、scenario 模块。
- PT Script Module 是验证组件，不应直接作为最终安全边界。
- PT 首启配置对话框会阻塞转发，部署器已经处理该问题。
- OSPF 重开后需要等待收敛，部署器已使用可配置收敛轮数。
- `artifacts/` 被 Git 忽略，提交代码时不会包含 PKT 和测试报告。
- 当前仓库没有远程地址，需要后续创建私有仓库并推送。
