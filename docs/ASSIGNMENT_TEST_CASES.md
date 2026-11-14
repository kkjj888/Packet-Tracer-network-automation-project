# Assignment UC Test Cases

## Scope

This document maps the assignment scenarios UC-01 through UC-12 to executable YAML cases and records the real Packet Tracer verification result.

Current result:

- Deployable scenarios: 13/13 passed.
- Negative scenario: UC-12 rejected with the expected validation error.
- Latest unit test result: 101 tests passed.

## Source Mapping

| Assignment case | YAML source | Verification focus |
| --- | --- | --- |
| UC-01 | `examples/assignment/uc01-ripv2-triangle.yaml` | RIPv2 convergence and three-router reachability |
| UC-02 | `examples/assignment/uc02-ospf-triangle.yaml` | Single-area OSPF neighbors and routes |
| UC-03 | `examples/assignment/uc03-multiarea-ospf.yaml` | Backbone/area routing and inter-area reachability |
| UC-04a | `examples/assignment/uc04a-public-route-no-nat.yaml` | Public routed access without NAT |
| UC-04b | `examples/assignment/uc04b-nat-pat.yaml` | PAT overload and translated traffic |
| UC-05a | `examples/assignment/uc05a-router-on-a-stick.yaml` | VLAN trunks and subinterfaces |
| UC-05b | `examples/assignment/uc05b-multilayer-svi.yaml` | Multilayer-switch SVIs and routed VLANs |
| UC-06 | `examples/assignment/uc06-home-office-switch.yaml` | Basic switched LAN connectivity |
| UC-07 | `examples/assignment/uc07-guest-cashier-policy.yaml` | Guest/cashier policy and denied paths |
| UC-08 | `examples/assignment/uc08-dual-isp-failover.yaml` | Floating static route failover |
| UC-09 | `examples/assignment/uc09-ebgp-partner.yaml` | eBGP session state and prefix reachability |
| UC-10 | `examples/assignment/uc10-ipv6-over-ipv4.yaml` | IPv6 over an IPv4 underlay |
| UC-11 | `examples/assignment/uc11-office-test-secure.yaml` | VLANs, DHCP, PAT, ACLs, and 20-endpoint scaling |
| UC-12 | `examples/assignment/uc12-invalid-allocation.yaml` | Negative addressing and security review |

## Interpretation Notes

- UC-04 is split into `04a` and `04b` so routed public access and PAT are independently observable.
- UC-05 is split into `05a` and `05b` because Router-on-a-Stick and multilayer-switch SVI are distinct implementation patterns.
- UC-05a and UC-05b use a connectivity matrix, producing 30 directed host-to-host checks each.
- UC-08 validates the primary path before failure, the backup path after failure, route changes, Traceroute, and the saved failure state after reopening.
- UC-10 uses `tunnel mode ipv6ip` because Packet Tracer 9.0.1 rejects `tunnel mode gre ipv6`. The case proves IPv6-over-IPv4 transport but is not protocol-level GRE.
- UC-11 uses static endpoints for deterministic policy checks and 18 additional DHCP clients for pool scaling. Final acceptance reads all leases after reopening; any unspecified, link-local, or out-of-pool address fails the run.
- UC-12 is intentionally not deployable. A successful test means validation exits with code `1` and reports `CHILD_NETWORK_OUTSIDE_PARENT`.

## Troubleshooting Guidance

The reusable model guidance learned from this run is documented in
[`LLM_TROUBLESHOOTING_PLAYBOOK.md`](LLM_TROUBLESHOOTING_PLAYBOOK.md),
especially section 4.14 and the Assignment UC knowledge table in section 5.2.

Those rules cover:

- forward and return-route checks;
- Traceroute expected-hop construction;
- connected versus learned BGP routes;
- verifying persisted failover state after reopening;
- IPv6-over-IPv4 dependency ordering and PT limitations;
- NAT on VLAN subinterfaces;
- DHCP traffic through ACLs and lease-completion checks;
- distinguishing implementation defects from incorrect test expectations.

## Manual Inspection Bundle

The complete review package is:

`artifacts/assignment-uc-suite-2026-11-14/`

For each deployable case, inspect the `.json` report for:

- `status`
- `verification`
- `verification_after_failure`, when applicable
- `advanced_verification`
- `verification_after_reopen`
- `output_assertions`
- `dhcp_clients_after_reopen`, when applicable

Open the corresponding `.pkt` file to inspect the saved topology and configuration. Use the `-audit.jsonl` file to review every Script Engine command in execution order.

## Reproduce

```powershell
cd D:\codex\bonus
python -m unittest discover -s tests
python -m pt_agent validate-dsl examples\assignment\uc12-invalid-allocation.yaml
python -m pt_agent deploy-dsl examples\assignment\uc11-office-test-secure.yaml
```

The first two commands should pass by validation semantics; UC-12 intentionally returns exit code `1`.
