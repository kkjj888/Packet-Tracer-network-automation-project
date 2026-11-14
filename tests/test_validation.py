from __future__ import annotations

import copy
import unittest
from pathlib import Path

from pt_agent.validation import (
    CommandSafetyValidator,
    NetworkValidator,
    load_yaml_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def issue_codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


class NetworkValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = NetworkValidator()
        self.campus = load_yaml_document(
            PROJECT_ROOT / "examples" / "campus-vlan.yaml"
        )
        self.ospf = load_yaml_document(
            PROJECT_ROOT / "examples" / "ospf-routing.yaml"
        )

    def test_examples_pass_schema_and_semantics(self) -> None:
        for document in (self.campus, self.ospf):
            result = self.validator.validate(document)
            self.assertTrue(result.valid, result.to_dict())
            self.assertEqual(result.schema_issues, [])
            self.assertEqual(result.semantic_issues, [])

    def test_schema_rejects_unknown_device_type(self) -> None:
        document = copy.deepcopy(self.campus)
        document["devices"][0]["type"] = "firewall"
        result = self.validator.validate(document)
        self.assertFalse(result.valid)
        self.assertIn("SCHEMA_VALIDATION", issue_codes(result))
        self.assertTrue(
            any("$.devices[0].type" == issue.path for issue in result.issues)
        )

    def test_semantics_reject_duplicate_ip_and_bad_gateway(self) -> None:
        document = copy.deepcopy(self.ospf)
        document["ipv4"][0]["address"] = "172.16.10.10/24"
        document["ipv4"][4]["gateway"] = "172.16.30.1"
        result = self.validator.validate(document)
        codes = issue_codes(result)
        self.assertIn("DUPLICATE_IPV4_ADDRESS", codes)
        self.assertIn("GATEWAY_OUTSIDE_SUBNET", codes)

    def test_semantics_reject_unknown_vlan_and_port_reuse(self) -> None:
        document = copy.deepcopy(self.campus)
        document["vlan_assignments"][0]["vlan"] = 99
        document["links"][1]["from"] = "sw1:FastEthernet0/1"
        result = self.validator.validate(document)
        codes = issue_codes(result)
        self.assertIn("UNKNOWN_VLAN_REFERENCE", codes)
        self.assertIn("PORT_ALREADY_CONNECTED", codes)

    def test_semantics_reject_unreachable_static_next_hop(self) -> None:
        document = copy.deepcopy(self.ospf)
        document["routing"] = {
            "static": [
                {
                    "device": "r1",
                    "network": "192.168.50.0/24",
                    "next_hop": "192.168.99.1",
                    "interface": "GigabitEthernet0/1",
                }
            ]
        }
        result = self.validator.validate(document)
        self.assertIn("ROUTE_NEXT_HOP_UNREACHABLE", issue_codes(result))

    def test_ospf_rejects_host_bits_and_disconnected_network(self) -> None:
        document = copy.deepcopy(self.ospf)
        document["routing"]["ospf"]["networks"][0][
            "network"
        ] = "172.16.10.10/24"
        document["routing"]["ospf"]["networks"][1][
            "network"
        ] = "192.168.77.0/24"
        result = self.validator.validate(document)
        codes = issue_codes(result)
        self.assertIn("NON_CANONICAL_NETWORK", codes)
        self.assertIn("OSPF_NETWORK_NOT_CONNECTED", codes)

    def test_acl_rejects_invalid_wildcard(self) -> None:
        document = copy.deepcopy(self.campus)
        document["acls"] = [
            {
                "id": "10",
                "rules": [
                    {
                        "action": "deny",
                        "match": "network",
                        "address": "192.168.10.0",
                        "wildcard": "0.0.0.254",
                    }
                ],
            }
        ]
        result = self.validator.validate(document)
        self.assertIn(
            "NON_CONTIGUOUS_ACL_WILDCARD",
            issue_codes(result),
        )


class CommandSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = CommandSafetyValidator()

    def test_allowlisted_configuration_passes(self) -> None:
        commands = [
            "configure terminal",
            "vlan 10",
            "name FINANCE",
            "exit",
            "interface FastEthernet0/1",
            "switchport mode access",
            "switchport access vlan 10",
            "no shutdown",
            "exit",
            "end",
            "write memory",
            "show vlan brief",
        ]
        self.assertEqual(self.validator.validate(commands), [])

    def test_dangerous_command_is_blocked(self) -> None:
        issues = self.validator.validate(["reload"])
        self.assertEqual(issues[0].code, "DANGEROUS_COMMAND")

    def test_extended_dangerous_command_matrix_is_blocked(self) -> None:
        commands = [
            "reload",
            "reload in 5",
            "write erase",
            "wr er",
            "erase startup-config",
            "format flash:",
            "delete flash:config.text",
            "config-register 0x2102",
            "boot system flash:c2900.bin",
            "copy flash:image.bin tftp:",
            "configure replace nvram:backup.cfg force",
            "archive rollback latest",
            "crypto key zeroize rsa",
            "tclsh",
            "debug all",
            "clear ip bgp *",
            "shutdown",
            "do reload",
            "do write erase",
            "no ip routing",
            "no access-group 120 in",
            "no logging console",
        ]
        for command in commands:
            with self.subTest(command=command):
                issues = self.validator.validate([command])
                self.assertTrue(
                    any(issue.code == "DANGEROUS_COMMAND" for issue in issues),
                    issues,
                )

    def test_control_characters_are_blocked(self) -> None:
        issues = self.validator.validate(["show clock\x00reload"])
        self.assertEqual(issues[0].code, "CONTROL_CHARACTER_IN_COMMAND")

    def test_dangerous_words_in_read_only_filters_are_allowed(self) -> None:
        commands = [
            "no shutdown",
            "show running-config | include reload",
            "show logging | include delete",
            "write memory",
        ]
        self.assertEqual(self.validator.validate(commands), [])

    def test_injection_and_multiline_commands_are_blocked(self) -> None:
        issues = self.validator.validate(
            [
                "show version; reload",
                "show version\nreload",
            ]
        )
        codes = {issue.code for issue in issues}
        self.assertIn("COMMAND_INJECTION_PATTERN", codes)
        self.assertIn("NEWLINE_IN_COMMAND", codes)

    def test_unknown_command_fails_closed(self) -> None:
        issues = self.validator.validate(["apply magic profile"])
        self.assertEqual(issues[0].code, "COMMAND_NOT_ALLOWLISTED")


if __name__ == "__main__":
    unittest.main()
