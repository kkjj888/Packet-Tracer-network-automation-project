# Packet Tracer 配置测试报告

测试日期：2026-11-10  
环境：Cisco Packet Tracer 9.0.1，Windows，本地仿真

## 总体结果

| 测试套件 | 结果 | 说明 |
|---|---|---|
| 基础 IP 与 Ping | PASS | 预热、4 包统计、保存和重开 |
| 故障诊断与修复 | PASS | 错误掩码导致断网，自动定位并修复 |
| 接入 VLAN 与 ACL | PASS | VLAN 持久化；ACL 由 4/4 变为 0/4 |
| 双交换机 Trunk | PASS | 同 VLAN 跨交换机 4/4；跨 VLAN 0/4 |
| 静态与默认路由 | PASS | 路由表、保存、重开和 Ping 均通过 |
| RIP v1/v2 | PASS | v1 不通过，v2 + no auto-summary 通过 |
| OSPF | PASS | wildcard mask、area 0、路由表和 Ping 均通过 |

## 关键证据

### VLAN

- `VLAN 10 FINANCE`、`VLAN 20 GUEST` 创建成功。
- `Fa0/1`、`Fa0/2` 属于 VLAN 10，`Fa0/3` 属于 VLAN 20。
- `PC1 -> PC2`：4/4。
- `PC1 -> PC3`：0/4。
- 保存并重新打开后，VLAN 和端口归属保持不变。

### ACL

- 应用 ACL 前：`PC1 -> PC2` 为 4/4。
- ACL 10：`deny host 192.168.10.10`，随后 `permit any`。
- ACL 绑定到 R1 `GigabitEthernet0/1 out`。
- 应用后：4 包全部被拒绝，结果为 0/4。
- 保存并重开后，ACL 规则和接口绑定保持不变。

### Trunk

- 两台 2960 使用 `GigabitEthernet0/1` 建立 802.1Q trunk。
- `SwitchPortMode=2`，即 `ADMIN_OPERATION_TRUNK`。
- `show interfaces trunk` 显示 `trunking`、native VLAN 1、允许 VLAN 1-4094。
- `PC1 -> PC2` 同 VLAN：4/4。
- `PC1 -> PC3` 跨 VLAN：0/4。
- 保存并重开后，trunk 与同 VLAN 连通性保持不变。

### 静态与默认路由

- R1 默认路由：`0.0.0.0/0 -> 10.0.0.2`。
- R2 回程路由：`172.16.10.0/24 -> 10.0.0.1`。
- 路由表回读成功，Ping 为 4/4。
- 保存并重开后，路由仍存在，Ping 仍为 4/4。

### RIP

- RIPv1 + auto-summary：`PC1 -> PC2` 为 0/4。
- 运行配置回读：`version 1`。
- 切换 RIPv2 + `no auto-summary`：Ping 为 4/4。
- 运行配置回读：`version 2`、`no auto-summary`、`network 172.16.0.0`。
- 保存并重开后仍为 RIPv2 且 Ping 4/4。

### OSPF

- 进程号：100。
- R1：`172.16.10.0 0.0.0.255 area 0`。
- R1：`10.0.0.0 0.0.0.3 area 0`。
- R1 学到 `172.16.20.0/24`，下一跳 `10.0.0.2`，管理距离 110。
- Ping 为 4/4。
- 保存并重开后运行配置、路由表和 Ping 均保持正确。

## 测试命令

```powershell
python -m pt_agent config-ping-demo
python -m pt_agent repair-demo
python -m pt_agent config-suite-demo
python -m pt_agent routing-suite-demo
python -m pt_agent trunk-suite-demo
```

## 产物

- `artifacts/config-vlan-smoke.pkt`
- `artifacts/config-acl-smoke.pkt`
- `artifacts/config-static-routing.pkt`
- `artifacts/config-rip-v1-v2.pkt`
- `artifacts/config-ospf.pkt`
- `artifacts/config-trunk.pkt`
- 对应 JSON 报告与 JSONL 审计日志

## 尚未覆盖

- NAT/PAT、DHCP 地址池
- IPv6 与隧道
- BGP 与双出口故障切换
- Traceroute 和结构化 PDU 断言
- YAML DSL/JSON Schema 与生产级 `.pts` 鉴权

