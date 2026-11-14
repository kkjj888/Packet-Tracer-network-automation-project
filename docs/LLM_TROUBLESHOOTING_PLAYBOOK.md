# LLM Network Troubleshooting Playbook

本文件是给大模型和诊断 Agent 使用的故障排查指导。它不替代项目规范，
而是规定模型在 Packet Tracer 网络项目中如何收集证据、定位原因、提出修复
和验证结果。

核心原则：

```text
先证明故障
-> 再缩小范围
-> 用一条有区分度的探测排除假设
-> 做最小修复
-> 跑完整回归
-> 保存并重开验证
```

## 1. 模型的行为边界

模型可以：

- 阅读 YAML、编译计划、PT 状态、JSON 报告和 JSONL 审计日志
- 执行安全的只读 `show` 命令
- 根据证据生成结构化诊断
- 在明确授权范围内生成修复计划
- 调用后端已有能力执行配置和验收

模型不可以：

- 仅凭最终报告中的一行失败直接猜测根因
- 看到 Ping 失败就直接删除 ACL、NAT 或路由
- 为“让测试通过”修改预期结果
- 使用 `reload`、`erase startup-config`、`write erase` 等破坏性操作
- 直接生成未经校验的原始 IOS 命令
- 把某个局部 Ping 成功当成整个项目通过
- 把“命令已经下发”当成“配置已经生效”
- 忽略保存、重开后再次验证

如果缺少关键证据、需要改变需求或连续三轮没有获得新信息，应停止并向
用户说明阻塞点。

## 2. 证据可信度顺序

按以下优先级判断事实：

1. Packet Tracer 当前实时状态，例如端口、VLAN、路由表、邻居状态
2. 实际 Ping、Traceroute 和设备状态输出
3. 保存后重新打开得到的持久化状态
4. JSON 验收报告
5. JSONL 审计日志中的命令和结果
6. YAML 与编译计划
7. 用户描述或历史聊天

高优先级证据可以覆盖低优先级推断，不能反过来。

特别注意：

- `getLink()` 返回对象不代表无线关联可以转发流量
- 命令没有报错不代表设备已经承载流量
- `show ip bgp summary` 的状态列可能显示前缀数而不是 `Established`
- `--More--` 表示输出被分页截断，不能把缺失内容判断为配置不存在
- 首次打开设备时，初始配置对话框会阻止数据转发

## 3. 标准诊断流程

### 3.1 建立问题快照

先记录：

```yaml
project:
test:
expected:
actual:
first_failure_step:
last_successful_step:
affected_devices:
affected_ports:
affected_vlans:
affected_networks:
artifacts:
```

不要跳过 `expected` 和 `actual`。没有精确的预期值与实际值，后面的诊断
很容易变成猜测。

### 3.2 判断故障阶段

| 阶段 | 典型错误 | 首要调查 |
|---|---|---|
| 加载 DSL | YAML、Schema、语义校验失败 | DSL 和校验报告 |
| 创建拓扑 | `add_device`、`add_module`、`create_link` | 设备、模块、端口名和 PT 状态 |
| 配置 CLI | `Invalid input`、超时、字符丢失 | 当前提示符、前一条命令、PT 桥接 |
| 业务验收 | 预期成功却失败，或预期隔离却成功 | 物理、L2、L3、策略、服务 |
| 保存重开 | 配置或地址丢失 | 保存结果、持久化配置、关联状态 |

### 3.3 判断影响范围

用最小比较找出共性和差异：

- 只有一台设备失败：先看该设备和接入端口
- 同一 VLAN 全部失败：先看 SVI、Trunk、VLAN、网关
- 一个子网全部失败：先看网关和路由
- 两条独立路径同时失败：先看公共核心、出口或测试方式
- 预期失败却成功：先检查 ACL 是否绑定、方向是否正确、是否存在旁路
- 配置成功但重开失败：先检查启动配置和人工状态是否被保存

### 3.4 生成有限假设

每次最多保留 3 个可行假设，并为每个假设写出：

```yaml
hypothesis:
supporting_evidence:
contradicting_evidence:
discriminating_probe:
expected_if_true:
expected_if_false:
```

不能区分假设的检查没有诊断价值。

### 3.5 执行单项探测

一次只执行一个能区分假设的检查。常见顺序：

```text
端口是否 up/up
-> 链路两端是否对应
-> VLAN/Trunk 是否连续
-> SVI/网关是否可用
-> 路由表是否有预期路径
-> ACL/NAT 是否改变流量
-> 服务是否正常
-> 客户端配置是否正确
```

### 3.6 最小修复

修复范围按以下顺序扩大：

```text
单个主机地址
-> 单个接入端口
-> 单个 VLAN
-> 单台三层设备
-> 单条路由或协议邻居
-> 成对冗余设备
```

每个修复动作必须对应一个已证实的原因。禁止顺手修改无关配置。

### 3.7 修复后验证

至少执行：

1. 原失败用例
2. 相邻正例
3. 相邻反例
4. 路由或设备状态断言
5. 保存
6. 重新打开
7. 重跑上述验收

只有原问题修复但回归失败，不能标记完成。

## 4. 分类排查树

### 4.1 桥接、扩展和进程问题

症状：

- `Script Engine returned no result`
- `extension did not poll`
- 命令长时间不返回

检查顺序：

1. Packet Tracer 进程是否存在
2. `MCP Bridge` 窗口是否存在且没有最小化
3. 本地 `127.0.0.1:54321` 是否收到轮询
4. PT 是否弹出模态对话框
5. 是否存在多个残留 PT 进程
6. 当前 `ipc.network()` 中是否有重复同名设备

处理原则：

- 临时桥接停顿可等待并对同一只读操作重试
- 出现重复拓扑或残留进程时，应重启 PT
- 不要假设 `fileNew` 一定清除所有失败运行留下的对象

### 4.2 `device_not_found`

先区分瞬时索引问题和真实缺失：

```text
第一次 device_not_found
-> 同名查询立即重试
-> 连续三次都失败才是真实缺失
```

如果连续失败，检查：

- 设备名是否有拼写或首字符丢失
- 当前是否仍有上一轮同名设备
- 设备是否创建成功但尚未进入名称索引
- 是否误用了端口名作为设备名

### 4.3 拓扑创建失败

#### `add_device`

检查设备类型 ID、模型名、画布位置和当前项目。

#### `add_module`

检查：

- 型号是否支持该模块
- 插槽路径是否正确
- 插槽当前是否已有真实模块
- 安装前后是否需要断电/上电
- 模块安装后端口名是否符合预期

2911 的 `HWIC-2T` 安装在 `0/0` 后通常出现：

```text
Serial0/0/0
Serial0/0/1
```

#### `create_link`

检查：

- 设备是否已成功命名
- 端口名是否完全一致，包括空格
- 端口是否真实存在
- 是否需要先安装模块
- 线缆类型是否兼容

`AccessPoint-PT` 的端口名包含空格，例如：

```text
Port 0
Port 1
```

不是 `Port0` 或 `Port1`。

### 4.4 IOS CLI 输入异常

#### 字符被吞

典型现象：

```text
configure terminal
```

变成：

```text
figure terminal
```

这说明不是命令本身错误，而是输入通道尚未准备好。处理方式：

1. 确认当前提示符
2. 先执行一个无副作用的预热命令
3. 等待 PT 接收
4. 再执行配置计划
5. 检查整组输出是否出现 `% Invalid input`

不能简单提高超时时间来解决字符丢失。

#### 设备正在启动或显示初始配置对话框

此时结构化 API 可能仍能写入配置，但数据转发不会工作。

处理：

- 等待提示符出现
- 回答 `no` 跳过初始配置对话框
- 再进入 enable/config 模式

#### `--More--`

PT 的某些版本不支持 `terminal length 0`。输出被分页时：

- 使用范围更窄的 `show ... | include ...`
- 主动发送空格翻页并读取后续输出
- 不要根据当前一页缺少内容判断配置不存在

### 4.5 物理层和链路

检查：

```text
show ip interface brief
show interfaces <port>
```

必须区分：

- administratively down
- down/down
- up/down
- up/up

再核对链路两端。只有 `up/up` 才能继续做 L2 判断。

### 4.6 VLAN 和 Trunk

按以下顺序：

```text
VLAN 是否存在
-> 接入端口是否在正确 VLAN
-> Trunk 两端是否 trunking
-> allowed VLAN 是否包含业务 VLAN
-> STP 是否在 forward 状态
-> SVI 是否 up/up
```

常用命令：

```text
show vlan brief
show interfaces trunk
show spanning-tree vlan <id>
show ip interface brief
show standby brief
```

重点检查：

- 接入端口与末端设备是否使用同一 VLAN
- 双上联是否都放行相同业务 VLAN
- Native VLAN 是否一致
- SVI VLAN 与网关地址是否属于同一子网
- HSRP Group、VIP、优先级是否成对一致

### 4.7 IPv4、路由和协议

检查顺序：

```text
接口地址
-> 直连路由
-> 静态/默认路由
-> IGP 邻居
-> BGP 邻居
-> 端到端 Traceroute
```

常用命令：

```text
show ip interface brief
show ip route
show ip ospf neighbor
show ip bgp summary
show ip bgp neighbors
```

判断 BGP 时要区分：

- summary 中的状态列可能显示前缀数
- 要证明 Established，应读取 `show ip bgp neighbors` 的
  `BGP state = Established`

路由断言必须同时匹配：

- 目标网络和掩码
- 协议
- 下一跳或出接口
- Administrative Distance

“有默认路由能到目标”不等于“目标网络存在一条精确路由”。

### 4.8 GRE

检查：

```text
show ip interface brief
show interfaces tunnel 0
```

重点：

- Tunnel 是否 up/up
- source/destination 是否可达
- Tunnel 地址是否正确
- 封包路径是否经过正确的 underlay

PT 可能自动计算 GRE transport MTU。显式 `mtu 1476` 若被拒绝，不应该
因此判断隧道 MTU 错误。

### 4.9 ACL

检查：

- ACL 是否存在
- 是否绑定到正确接口和方向
- 规则顺序是否符合意图
- 是否有隐式或显式 `deny ip any any`
- 命中计数是否说明流量走了预期规则

常用：

```text
show access-lists <id>
show running-config | include access-group|access-class
```

如果“预期隔离却成功”，不能直接判定 ACL 无害，要检查：

- 流量根本没有经过 ACL 所在接口
- ACL 绑定方向错误
- 路由选择了另一条旁路
- 测试源地址或目标地址写错
- Ping 来自错误设备

临时移除 ACL 只能作为隔离实验，实验结束后必须恢复并重新验收。

### 4.10 DHCP

按以下顺序：

```text
客户端是否在正确 VLAN
-> 接口是否 up/up
-> 同网段是否有可用 DHCP 池
-> 地址是否被排除
-> ACL 是否放行 DHCP
-> 客户端是否执行 renew
-> 是否拿到子网内地址
```

注意：

- `169.254.x.x` 通常表示 DHCP 失败，不是有效租约
- `dhcp: true` 只表示客户端打开了 DHCP 标志，不表示拿到租约
- 有线同 VLAN 测试可以区分 DHCP 问题与无线关联问题
- 设置 DHCP 后应执行 `ipconfig /renew` 并等待租约

### 4.11 NAT

分别验证：

- PAT 的 ACL 是否匹配内网源
- inside/outside 接口是否配置正确
- 默认路由和回程路由是否存在
- 静态 NAT 的内外地址和端口是否完整
- `show ip nat translations` 是否有实际会话

NAT 失败可能是路由问题，不应直接归因于 NAT。

### 4.12 无线

检查：

- AP 是否有有线 up 上联
- 交换机端口 VLAN 是否正确
- AP 和客户端 SSID 是否一致
- 认证和加密类型是否一致
- 客户端是否拿到 DHCP 地址

PT 9 的特殊限制：

- 公开 JS IPC 可以设置 SSID 等参数
- 它不能可靠触发原生无线射频关联
- 客户端 `getLink()` 返回对象不等于已经可以转发流量

如果后端设置成功但 DHCP 和业务流量均失败，应检查是否需要在 GUI 中：

```text
Laptop -> Desktop -> PC Wireless -> Connect
```

人工建立关联后，必须重新执行 DHCP 和端到端验收，并再次保存 PKT。

### 4.13 Ping 和 Traceroute 断言

Ping 通过条件：

- 输出完整
- `Sent = 4`
- `Received = 4`
- `Lost = 0`

只有 1 至 3 个回复不能算成功。

预期失败：

- 必须确认失败是由目标策略造成
- 不能仅凭任意超时就证明隔离正确

Traceroute：

- 路由器返回的地址可能是 HSRP 物理接口地址，而不是 VIP
- 必须比较实际路径，不应凭经验修改预期
- 路径收敛后可能需要在重开项目中再次确认

### 4.14 Assignment UC 实战验收陷阱

以下问题来自 UC-01 至 UC-12 的真实 Packet Tracer 部署。模型应先按证据判断
问题属于配置、平台限制还是验收预期错误，禁止为了让报告变绿直接放宽断言。

#### 双向连通和回程路由

症状：

- 源主机能发出流量，Traceroute 能到达公网侧的最后一跳
- 目标主机或服务器却没有 Ping 回复

需要同时检查：

```text
源主机默认网关
-> 源侧出口默认路由
-> 中间路由器到目标的转发路径
-> 目标侧到源网段或 NAT 外网地址的回程路由
```

判断规则：

- 默认路由只证明“去程”有路，不证明返回流量有路
- 目标与源地址不同网段时，必须检查目标侧路由或确认已正确执行 NAT
- 如果目标在公网模拟器中，要检查 ISP 路由器是否知道如何返回私网汇总网段
- 在确认回程路由前，不要用延长超时掩盖故障

#### Traceroute 预期跳数

PT 输出的 Traceroute 可能包含超时行（`*`），但结构化解析只保留实际返回地址。
因此预期跳数应只列有回包的路径地址，并保证最后一个地址是目标本身。

禁止：

- 把 `Request timed out` 当成一个地址写入期望
- 直接把实际输出复制成预期而不核对拓扑
- 为了通过测试随意删除中间设备地址

允许修改预期的前提是：能够从拓扑、路由表或控制面输出解释为什么该地址应该出现或
不应该出现。

#### BGP 本地路由和邻居学习路由

BGP `network` 语句只负责宣告前缀，不会改变该路由器对本地直连网的选路。
同一个前缀在不同设备上的正确协议可能不同：

- 前缀发起路由器：通常仍是从 connected 或本地静态路由进入路由表
- 对端 BGP 路由器：通常应学到 BGP 路由

诊断时应分别读取两端的 `show ip route` 和 `show ip bgp neighbors`，
不能把“对端学到了 BGP”误写成“发起端也必须显示 BGP”。

#### 故障切换后的保存重开

带 `link_failures` 的项目保存后，故障端口状态也会一并持久化。重开项目后：

- 不应继续等待原主路径恢复
- 应验证备用路径、备份默认路由和故障态下的 Traceroute
- 同时保留故障前主路径证据，形成 before/after 两组验收结果

如果重开后按“初始拓扑”检查，容易把正确的故障持久化误判为失败。

#### IPv6 over IPv4 的依赖顺序

正确配置顺序：

```text
IPv4 物理接口
-> IPv4 underlay 静态路由
-> Tunnel 接口
-> IPv6 overlay 接口和静态路由
```

Tunnel 接口 `up/up` 只证明封装接口状态，不证明数据面可用。至少分三层验证：

```text
Tunnel 接口 up/up
-> 两端 Tunnel IPv6 地址可互 Ping
-> 两端业务 IPv6 网段可端到端 Ping
```

PT 9.0.1 实测限制：

- `tunnel mode gre ipv6` 被拒绝
- `tunnel mode ipv6ip` 可用
- 纯接口形式的路由可能被拒绝；优先使用 Tunnel 对端的 IPv6 地址作为 next hop

如果平台只能完成 IPv6/IP 而不能完成协议级 GRE，报告必须明确写成平台偏差，
不能把 `ipv6ip` 描述成 GRE。

#### VLAN 子接口上的 NAT

Router-on-a-Stick 场景中，NAT inside 应绑定在拥有业务 IP 的 VLAN 子接口，
不要只绑定没有 IP 的物理父接口。典型配置：

```text
interface GigabitEthernet0/0.10
 ip nat inside

interface GigabitEthernet0/2
 ip nat outside
```

验证时不能只看 NAT 配置是否存在，还应在产生流量后读取
`show ip nat translations`，确认 inside local 到 inside global 的实际转换。

#### ACL 与 DHCP

子接口入站 ACL 若以 `deny ip any any` 结束，会同时阻断源地址为
`0.0.0.0` 的 DHCP Discover。必须在该兜底规则之前显式允许 DHCP：

```text
access-list <id> permit udp any any eq bootps
```

DHCP 状态应按以下顺序判断：

```text
客户端已启用 DHCP
-> 实际 IP 不是 0.0.0.0
-> 实际 IP 不是 169.254.x.x
-> IP 属于预期地址池
-> 保存重开后租约仍存在
```

`dhcp: true` 只表示客户端启用了 DHCP，不代表已经拿到租约。PT 中首次请求后可能
短暂保持 `0.0.0.0`，应区分“收敛中”和“持续失败”；不要仅凭一次采样下结论，
也不要通过电源重启伪造成功。最终验收必须以实际地址池租约为准。

#### CLI 字符丢失、初始化对话框和分页

当出现以下现象时，先判断为终端时序问题：

- `configure terminal` 被截成 `figure terminal`
- 命令已发送但输出区长度不变
- 当前提示符仍停留在旧模式
- 设备启动后弹出初始配置对话框

处理顺序：

1. 回读当前 prompt/mode
2. 执行无副作用的预热命令
3. 必要时回答 `no` 关闭初始配置对话框
4. 一次只执行一条配置命令
5. 用命令前后输出偏移读取新增结果
6. 检查是否出现 `% Invalid input`
7. 最后才考虑增加等待时间

遇到 `--More--` 时，应使用窄范围 `| include` 或逐页读取；不能把当前页缺失的
内容直接判定为配置不存在。

#### 验收器本身也可能是故障源

如果 Ping、邻居状态、路由表和接口状态都已经正确，只剩一条断言失败，应优先检查：

- 期望协议是否使用了设备角色对应的协议
- Traceroute 是否漏写真实下一跳
- 重开后的验收是否仍按初始状态而不是保存后的状态判断
- DHCP 是否在租约完成前就被读取
- 预期的 source 是否误用了本机直连接口

只有证据证明实现错误时才修改代码；如果只是期望值错误，应提交单独的测试修复，
并在说明中记录原错误和纠正依据。

## 5. 项目故障知识库

### 5.1 G02 故障知识库

| 现象 | 根因 | 正确处理 |
|---|---|---|
| `addModuleAt` 参数无效 | 模块被序列化为数组 | 序列化为 `{name, slot}` 对象 |
| `create_link` 找不到 AP 端口 | AP 端口是 `Port 0` | 使用包含空格的真实端口名 |
| Core 配置首条命令变短 | PT 输入通道尚未准备 | 预热输入后再发送命令 |
| 首轮大型拓扑很慢 | 每条命令单独等待 | 降低调度间隔，但保留输入时序保护 |
| HSRP track 被拒绝 | PT 不支持 decrement 写法 | 使用 `standby ... track <port>` |
| ACL 的 `https` 被拒绝 | PT ACL 不接受该端口名 | 使用数字端口 `443` |
| GRE 的 `mtu 1476` 被拒绝 | PT GRE transport MTU 自动计算 | 不显式下发 MTU |
| Tunnel OSPF p2p 被拒绝 | PT 不允许该接口显式设置 | 依赖 Tunnel 自身的点对点属性 |
| BGP 状态断言失败 | summary 状态列显示前缀数 | 用 neighbor 详细状态检查 Established |
| Traceroute 首要跳点不符 | HSRP 返回物理地址 | 使用实际 `10.22.0.60`，不是 VIP 推测值 |
| 重开后 Ward 首次 Ping 失败 | STP/HSRP/路由尚未收敛 | 延长收敛时间后复测 |
| Guest 无线无 DHCP | PT IPC 不触发无线关联 | GUI 人工连接，再 renew 和验收 |
| 重复失败后出现多套同名设备 | 同一 PT 会话残留项目状态 | 重启 PT，使用干净工作区 |

### 5.2 Assignment UC 补充知识库

| 症状 | 根因 | 正确判断/修复 |
|---|---|---|
| 公网最后一跳可达但 Ping 超时 | 目标侧没有回程路由，或 NAT inside 绑定错误 | 同时检查去程、回程和 `show ip nat translations` |
| Traceroute 少一个期望地址 | 期望值漏掉了实际响应的 ISP/下一跳 | 从拓扑和路由表构造期望，不复制超时行 |
| 发起端未显示 BGP 路由 | 该前缀在本地可能仍是 connected | 按发起端/接收端角色分别断言协议 |
| 故障切换项目重开后主路径断言失败 | 链路故障已随 PKT 持久化 | 重开后继续验收备用路径 |
| IPv6 隧道 up/up 但不能 Ping | 只有隧道状态，没有数据面或 overlay 路由 | 分别测试 Tunnel 对端和业务网段 |
| `tunnel mode gre ipv6` 报 Invalid input | PT 9.0.1 不支持该模式 | 记录平台偏差；可用 `tunnel mode ipv6ip` |
| `ipv6 route ... Tunnel0` 被拒绝 | PT 对纯接口路由支持不完整 | 使用 Tunnel 对端 IPv6 地址作为 next hop |
| VLAN 终端无法访问公网 | NAT inside 只绑定在没有 IP 的父接口 | 绑定业务 VLAN 子接口 |
| DHCP 客户端全部拿不到地址 | 子接口 ACL 的兜底 deny 丢弃 DHCP | 在 deny 前 permit UDP `bootps` |
| DHCP 偶发显示 `0.0.0.0` | 租约尚未收敛或报告采样过早 | 等待并检查实际地址池租约，最终以重开后持久化状态验收 |

## 6. 允许的自动修复

当前可以确定性自动修复：

- 主机 IP 错误
- 主机掩码错误
- 修复后重新执行 Ping、保存和重开验证

可以生成修复计划但仍应谨慎执行：

- 单个接入端口 VLAN 错误
- 单个 Trunk allowed VLAN 缺失
- 单个 SVI 地址错误
- 单条静态路由错误
- OSPF network 语句缺失
- DHCP pool 参数错误
- NAT 内外接口错误

必须先获得更多证据，不能自动修复：

- 多区域 OSPF 设计问题
- HSRP/STP 成对不一致
- 大范围 ACL 语义冲突
- BGP 路由策略问题
- 无线关联
- PT 版本兼容性未知问题

## 7. 修复计划格式

大模型提出修复时必须使用以下结构：

```json
{
  "diagnosis": {
    "code": "SINGLE_VALUE",
    "confidence": 0.0,
    "summary": "one sentence",
    "evidence": [
      {
        "source": "pt_state|report|audit|dsl",
        "fact": "exact observed fact"
      }
    ]
  },
  "repair": {
    "scope": "host|port|vlan|device|route|policy|platform",
    "device": "device id",
    "target": "port/interface/process",
    "changes": [
      "structured change"
    ],
    "expected_effect": "what should change",
    "risk": "low|medium|high",
    "requires_confirmation": false
  },
  "verification": {
    "primary": "original failing assertion",
    "regression": [
      "adjacent positive test",
      "adjacent negative test",
      "state assertion"
    ],
    "save_and_reopen": true
  }
}
```

不能把多个互不相关的修复塞进同一个计划。每个修复必须说明它对应的
证据和预期效果。

## 8. 最终回答格式

诊断完成后，模型应按以下格式回答：

```markdown
## 结论
一句话说明根因和当前状态。

## 已确认事实
- 只列可验证的事实
- 注明来自 PT 状态、报告、审计还是 DSL

## 根因
区分已证实根因和剩余假设。

## 最小修复
说明改了哪个设备的哪个对象，以及为什么只改这里。

## 验证结果
- 原失败用例
- 相邻正例和反例
- 路由/协议状态
- 保存与重开

## 未解决风险
没有就写“无”；存在平台限制时必须明确写出。
```

## 9. 可直接使用的 Agent 提示词

```text
你是 Packet Tracer 网络项目的诊断 Agent。

你的任务不是猜测，而是根据证据定位一个最小根因，并在授权范围内完成
最小修复。

必须遵守：
1. 先读取失败断言、编译计划、报告和审计日志。
2. 按物理层、二层、三层、策略、服务、平台的顺序缩小范围。
3. 一次只执行一个能区分假设的探测。
4. 不得通过修改预期值、删除 ACL、重载设备或重跑整个随机流程来掩盖问题。
5. 修复范围优先限制在单个主机、端口、VLAN、设备或路由。
6. 修复后必须执行原用例、相邻正例、相邻反例、保存和重开验证。
7. 连续三轮没有新证据时停止，并报告缺失的信息。
8. 如果属于 Packet Tracer API 限制，应明确标记为平台限制，不要伪报成功。

输出必须包含：已确认事实、根因、证据、最小修复、回归结果、剩余风险。
```

## 10. 检查清单

提交诊断前确认：

- [ ] 已记录 expected 和 actual
- [ ] 已定位首次失败步骤
- [ ] 已确认失败影响范围
- [ ] 至少有一个区分性探测
- [ ] 根因和证据一一对应
- [ ] 修复是当前最小范围
- [ ] 没有删除无关配置
- [ ] 原问题已经复测
- [ ] 正例和反例都通过
- [ ] 保存并重开通过
- [ ] 平台限制已明确记录
