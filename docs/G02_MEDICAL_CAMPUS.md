# G02 Medical Campus Reproduction

## Inputs

- Source report: `D:\codex\cisco\lab final\G02_report_preview.pdf`
- Project DSL: `examples/g02-medical-campus.yaml`
- Generated Packet Tracer project: `artifacts/g02-medical-network.pkt`
- Final report: `artifacts/g02-medical-network-report.json`
- Final audit trace: `artifacts/g02-medical-network-audit.jsonl`

## Reproduced Topology

The generated project contains 28 user devices and 34 physical links:

- 2 x Cisco 3560-24PS multilayer core switches
- 6 x Cisco 2960-24TT access switches
- 3 x Cisco 2911 routers with HWIC-2T serial modules
- 2 x internal servers, 1 ISP DNS server
- 8 workstations/endpoints, 3 laptops, and 1 access point

Packet Tracer also creates two internal power-distribution objects, so the
raw device count is 30.

## Implemented Configuration

- VLAN 201-208 and dual-homed access-layer trunks
- Core SVIs, routed core ports, and `ip routing`
- HSRP active/preempt groups on both core switches
- STP primary/secondary root configuration
- Multi-area OSPF with passive interfaces and area range
- GRE tunnel between HQ and the Taipa branch
- eBGP AS 65302 to ISP AS 65500
- Guest, finance, IoT, and management ACL policies
- NAPT and static TCP NAT for the public web service
- DHCP pools for outpatient, guest, and branch exam networks
- Server, management, and ISP test addresses

## Final Verification

- Connectivity: 9/9 assertions passed, including negative isolation checks
- Routes: 4/4 assertions passed for BGP, static, and OSPF paths
- Traceroute: exact path passed
- Device-state assertions: 7/7 passed for HSRP, STP, OSPF, GRE, BGP, and NAT
- DHCP:
  - outpatient clients: `10.22.0.129-130/27`
  - guest client: `10.22.0.65/26`
  - branch exam clients: `10.22.4.1-2/27`
- Save/reopen: the final project was reopened and revalidated

## Packet Tracer Limitation

Packet Tracer 9's public Script Engine API can set AP and laptop wireless
parameters, but it does not complete the native radio association. The final
project therefore requires one manual association:

1. Open `G02-HQ-GUEST-LT1`.
2. Open `Desktop -> PC Wireless -> Connect`.
3. Select SSID `AK-GUEST-G02`.
4. Run `ipconfig /renew`.

The final PKT preserves the working association and the resulting DHCP lease.
