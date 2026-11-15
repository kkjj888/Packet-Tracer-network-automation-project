# Packet Tracer Agent CLI

一个面向 Agent 的 Packet Tracer 网络自动化后端。Agent 生成 YAML 网络描述，通过 `pt-agent` CLI 完成校验、编译、部署、验收、保存和重新打开。

当前版本是基于windows平台，包含后端代码与skill，不包含 MCP Server、后台 Job 系统或内嵌 Agent。

## 功能

- YAML 网络 DSL
- JSON Schema、网络语义和 IOS 危险命令三层校验
- Packet Tracer Script Engine 自动化
- 设备、模块和链路的自动创建
- IPv4、IPv6、VLAN、Trunk、SVI、静态路由、RIP、OSPF、BGP、ACL、NAT、DHCP 和 Tunnel
- Ping、全有向连通矩阵、路由表、Traceroute、NAT、DHCP 和设备输出验收
- 链路故障注入和故障后验收
- PKT 保存、重新打开和持久化复验
- JSON 运行报告和 JSONL 审计日志
- Agent 可调用的 `pt-network-automation` Skill

## 架构

```text
Agent
  -> Shell
  -> pt-agent CLI
  -> Windows Packet Tracer Runtime
  -> PT Bridge
  -> PT Script Engine
  -> Cisco Packet Tracer
```

详细说明见 [CLI + Skill Architecture](docs/CLI_SKILL_ARCHITECTURE.md)。

## 环境要求

- Windows
- Python 3.11+
- Cisco Packet Tracer 9.0.1
- [vendor/mcp-bridge.pts](vendor/mcp-bridge.pts)

安装 Python 依赖和 CLI：

```powershell
python -m pip install -e .
```

如果 `pt-agent` 不在 `PATH` 中，可使用：

```powershell
python -m pt_agent
```

## 安装 PT Script Module

在 Packet Tracer 中执行：

```text
Extensions
-> Scripting
-> Configure PT Script Modules
-> Add
-> 选择 vendor/mcp-bridge.pts
-> Launch
```

保持 `MCP Bridge` 窗口处于运行状态。这里的 `mcp-bridge.pts` 是本地 Script Module 和 HTTP Bridge，不是 Model Context Protocol Server。

## 快速开始

```powershell
# 1. 检查 PT、Script Module 和 Bridge
pt-agent doctor --wait-bridge 5

# 2. 校验 YAML
pt-agent validate-dsl examples\assignment\uc01-ripv2-triangle.yaml

# 3. 查看编译后的命令与验收计划
pt-agent compile-dsl examples\assignment\uc01-ripv2-triangle.yaml

# 4. 部署、验收、保存并重新打开
pt-agent deploy-dsl examples\assignment\uc01-ripv2-triangle.yaml
```

成功的部署会生成：

```text
artifacts/dsl-<project>.pkt
artifacts/dsl-<project>.json
artifacts/dsl-<project>-audit.jsonl
```

## Agent Skill

Skill 位于 [skills/pt-network-automation](skills/pt-network-automation/SKILL.md)。

基本流程：

```text
doctor
-> validate-dsl
-> compile-dsl
-> deploy-dsl
-> 读取 JSON report 和 JSONL audit
```

Skill 规定 Agent：

- 只通过 CLI 操作后端
- 不直接执行内部 Python 或 PT JavaScript
- 不为通过测试随意修改预期值
- 失败时先读取报告和审计日志
- 遇到平台限制时明确记录，而不是伪造成功

## YAML DSL

支持的顶层字段：

```text
devices
links
ipv4
ipv6
ipv6_tunnels
vlans
vlan_assignments
switch_routing
svis
hsrp
stp
routing
dhcp
dhcp_clients
nat
link_failures
acls
acl_bindings
management
wireless
verification
addressing_constraint
```

详见 [DSL Validation](docs/DSL_VALIDATION.md) 和 [Network Schema](schema/network.schema.json)。

## 测试

```powershell
python -m unittest discover -s tests
```

当前测试覆盖 Schema、语义、安全、命令模板、YAML 编译、验收解析、Script Bridge、Windows Runtime 和作业案例。

## 安全

- 原始 IOS 命令必须经过 allowlist 和危险命令黑名单
- 模型不直接调用 PT JavaScript API
- 危险操作不会暴露为 Agent 工作流
- 每次部署写入 JSONL 审计日志

详见 [Command Safety](docs/COMMAND_SAFETY.md)。

## 故障排查

Agent 和开发者可参考 [LLM Troubleshooting Playbook](docs/LLM_TROUBLESHOOTING_PLAYBOOK.md)。

## 已知限制

- 仅支持 Windows
- 当前部署命令前台运行，耗时取决于场景规模
- 固定输出到 `artifacts/`
- 不支持 DSL 之外的任意 IOS 配置
- 通用故障诊断和修复由 Agent 按 Skill 执行，后端不提供通用 Repair Engine

## 目录

```text
pt_agent/     Python 后端与 CLI
schema/       YAML JSON Schema
examples/     DSL 示例和作业用例
skills/       Agent Skill
docs/         架构、安全、测试和故障排查文档
tests/        自动化测试
vendor/       PT Script Module 及其许可证
```
