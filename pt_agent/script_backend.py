"""JS command builders executed inside Packet Tracer's Script Engine."""

from __future__ import annotations

import json
from pathlib import Path


LOGICAL_WORKSPACE = (
    "ipc.appWindow().getActiveWorkspace().getLogicalWorkspace()"
)


def new_project_js() -> str:
    return (
        "(function(){var a=ipc.appWindow();"
        "var r=a.fileNew(false);return JSON.stringify({ok:!!r});})()"
    )


def minimal_topology_js() -> str:
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
  var pc1=lw.addDevice(8,"PC-PT",300,300);
  if(!pc1) return "ERROR:first_pc_not_created";
  var d1=net.getDevice(pc1);
  d1.setName("PC1");
  d1.setPower(true);
  var pc2=lw.addDevice(8,"PC-PT",300,600);
  if(!pc2) return "ERROR:second_pc_not_created";
  var d2=net.getDevice(pc2);
  d2.setName("PC2");
  d2.setPower(true);
  var sw=lw.addDevice(1,"2960-24TT",600,450);
  if(!sw) return "ERROR:switch_not_created";
  var ds=net.getDevice(sw);
  ds.setName("SW1");
  ds.setPower(true);
  var l1=lw.createLink("PC1","FastEthernet0","SW1","FastEthernet0/1",8100);
  var l2=lw.createLink("PC2","FastEthernet0","SW1","FastEthernet0/2",8100);
  return JSON.stringify({{
    deviceCount:net.getDeviceCount(),
    linkCount:net.getLinkCount(),
    link1:!!l1,
    link2:!!l2
  }});
}})()"""


def topology_state_js() -> str:
    return """(function(){
  var net=ipc.network();
  var devices=[];
  for(var i=0;i<net.getDeviceCount();i++){
    var d=net.getDeviceAt(i);
    if(d) devices.push({name:String(d.getName()),model:String(d.getModel())});
  }
  return JSON.stringify({devices:devices,linkCount:net.getLinkCount()});
})()"""


def configure_host_ip_js(
    device: str,
    port: str,
    ip: str,
    mask: str,
    gateway: str | None = None,
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    port_text = json.dumps(port, ensure_ascii=False)
    ip_text = json.dumps(ip, ensure_ascii=False)
    mask_text = json.dumps(mask, ensure_ascii=False)
    gateway_line = (
        f'p.setDefaultGateway({json.dumps(gateway, ensure_ascii=False)});'
        if gateway
        else ""
    )
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    try{{d.setDhcpFlag(false);}}catch(e){{}}
    var p=d.getPort({port_text});
    if(!p)return "ERROR:port_not_found";
    try{{p.setDhcpClientFlag(false);}}catch(e){{}}
    p.setIpSubnetMask({ip_text},{mask_text});
    {gateway_line}
    return JSON.stringify({{
      device:{device_text},
      port:{port_text},
      ip:String(p.getIpAddress()),
      mask:String(p.getSubnetMask())
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def host_ip_state_js(device: str, port: str) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    port_text = json.dumps(port, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var p=d.getPort({port_text});
    if(!p)return "ERROR:port_not_found";
    return JSON.stringify({{
      device:{device_text},
      port:{port_text},
      ip:String(p.getIpAddress()),
      mask:String(p.getSubnetMask())
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def configure_dhcp_client_js(device: str, port: str) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    port_text = json.dumps(port, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    try{{d.setDhcpFlag(true);}}catch(e){{}}
    var p=d.getPort({port_text});
    if(!p)return "ERROR:port_not_found";
    p.setDhcpClientFlag(true);
    return JSON.stringify({{
      device:{device_text},
      port:{port_text},
      dhcp:!!p.isDhcpClientOn(),
      ip:String(p.getIpAddress()),
      mask:String(p.getSubnetMask())
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def set_port_power_js(device: str, port: str, powered: bool) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    port_text = json.dumps(port, ensure_ascii=False)
    powered_text = "true" if powered else "false"
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var p=d.getPort({port_text});
    if(!p)return "ERROR:port_not_found";
    p.setPower({powered_text});
    return JSON.stringify({{
      device:{device_text},
      port:{port_text},
      power:!!p.getPower(),
      portUp:!!p.isPortUp(),
      protocolUp:!!p.isProtocolUp()
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def configure_router_ipv4_js(
    device: str, interfaces: dict[str, dict[str, str]]
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    interfaces_text = json.dumps(interfaces, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var configs={interfaces_text};
    var observed=[];
    for(var portName in configs){{
      var p=d.getPort(portName);
      if(!p)return "ERROR:port_not_found:"+portName;
      var cfg=configs[portName];
      p.setPower(true);
      try{{p.setDhcpClientFlag(false);}}catch(e){{}}
      p.setIpSubnetMask(cfg.ip,cfg.mask);
      observed.push({{
        port:String(portName),
        ip:String(p.getIpAddress()),
        mask:String(p.getSubnetMask()),
        portUp:!!p.isPortUp(),
        protocolUp:!!p.isProtocolUp()
      }});
    }}
    return JSON.stringify({{device:{device_text},interfaces:observed}});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def router_ipv4_state_js(
    device: str, ports: list[str]
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    ports_text = json.dumps(ports, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var names={ports_text};
    var observed=[];
    for(var i=0;i<names.length;i++){{
      var p=d.getPort(names[i]);
      if(!p)return "ERROR:port_not_found:"+names[i];
      observed.push({{
        port:String(names[i]),
        ip:String(p.getIpAddress()),
        mask:String(p.getSubnetMask()),
        portUp:!!p.isPortUp(),
        protocolUp:!!p.isProtocolUp()
      }});
    }}
    return JSON.stringify({{device:{device_text},interfaces:observed}});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def configure_switch_vlans_js(
    device: str,
    vlans: dict[int, str],
    access_ports: dict[str, int],
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    vlans_text = json.dumps(vlans, ensure_ascii=False)
    ports_text = json.dumps(access_ports, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var vm=d.getProcess("VlanManager");
    if(!vm)return "ERROR:vlan_manager_not_found";
    var definitions={vlans_text};
    var created={{}};
    for(var id in definitions){{
      var vlanNumber=Number(id);
      var existing=vm.getVlan(vlanNumber);
      if(existing){{
        vm.changeVlanName(vlanNumber,definitions[id]);
        created[id]=false;
      }}else{{
        created[id]=!!vm.addVlan(vlanNumber,definitions[id]);
      }}
    }}
    var assignments={ports_text};
    var ports={{}};
    for(var portName in assignments){{
      var p=d.getPort(portName);
      if(!p)return "ERROR:port_not_found:"+portName;
      p.setAccessPort(true);
      p.setAccessVlan(Number(assignments[portName]));
      p.setPower(true);
      ports[portName]={{
        access:!!p.isAccessPort(),
        vlan:Number(p.getAccessVlan()),
        portUp:!!p.isPortUp()
      }};
    }}
    return JSON.stringify({{
      device:{device_text},
      created:created,
      ports:ports,
      vlanCount:Number(vm.getVlanCount())
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def switch_vlan_state_js(
    device: str, ports: list[str]
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    ports_text = json.dumps(ports, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var vm=d.getProcess("VlanManager");
    if(!vm)return "ERROR:vlan_manager_not_found";
    var vlans=[];
    for(var i=0;i<vm.getVlanCount();i++){{
      var v=vm.getVlanAt(i);
      if(v){{
        vlans.push({{
          id:Number(v.getVlanNumber()),
          name:String(v.getName()),
          isDefault:!!v.isDefault()
        }});
      }}
    }}
    var portNames={ports_text};
    var observed={{}};
    for(var j=0;j<portNames.length;j++){{
      var p=d.getPort(portNames[j]);
      if(!p)return "ERROR:port_not_found:"+portNames[j];
      observed[portNames[j]]={{
        access:!!p.isAccessPort(),
        vlan:Number(p.getAccessVlan()),
        portUp:!!p.isPortUp()
      }};
    }}
    return JSON.stringify({{
      device:{device_text},
      vlans:vlans,
      ports:observed
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def configure_trunk_port_js(
    device: str,
    port: str,
    *,
    allowed_start: int = 1,
    allowed_end: int = 4094,
    native_vlan: int = 1,
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    port_text = json.dumps(port, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var p=d.getPort({port_text});
    if(!p)return "ERROR:port_not_found";
    p.setAdminOpMode(2);
    p.setAccessPort(false);
    p.addTrunkVlans({int(allowed_start)},{int(allowed_end)});
    p.setNativeVlanId({int(native_vlan)});
    p.setPower(true);
    return JSON.stringify({{
      device:{device_text},
      port:{port_text},
      access:!!p.isAccessPort(),
      adminOpMode:Number(p.getAdminOpMode()),
      adminModeSet:!!p.isAdminModeSet(),
      nativeVlan:Number(p.getNativeVlanId()),
      portUp:!!p.isPortUp(),
      protocolUp:!!p.isProtocolUp()
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def trunk_port_state_js(device: str, port: str) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    port_text = json.dumps(port, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var p=d.getPort({port_text});
    if(!p)return "ERROR:port_not_found";
    return JSON.stringify({{
      device:{device_text},
      port:{port_text},
      access:!!p.isAccessPort(),
      adminOpMode:Number(p.getAdminOpMode()),
      adminModeSet:!!p.isAdminModeSet(),
      nativeVlan:Number(p.getNativeVlanId()),
      portUp:!!p.isPortUp(),
      protocolUp:!!p.isProtocolUp()
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def configure_acl_js(
    device: str,
    acl_id: str,
    statements: list[str],
    out_port: str,
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    acl_text = json.dumps(acl_id, ensure_ascii=False)
    statements_text = json.dumps(statements, ensure_ascii=False)
    port_text = json.dumps(out_port, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var proc=d.getProcess("AclProcess");
    if(!proc)return "ERROR:acl_process_not_found";
    var aclId={acl_text};
    var existing=proc.getAcl(aclId);
    if(!existing)proc.addAcl(aclId);
    var acl=proc.getAcl(aclId);
    if(!acl)return "ERROR:acl_not_created";
    var rules={statements_text};
    var added=[];
    for(var i=0;i<rules.length;i++){{
      added.push({{rule:rules[i],ok:!!acl.addStatement(rules[i])}});
    }}
    var p=d.getPort({port_text});
    if(!p)return "ERROR:port_not_found";
    p.setAclOutID(aclId);
    return JSON.stringify({{
      device:{device_text},
      aclId:aclId,
      added:added,
      outPort:{port_text},
      aclOut:String(p.getAclOutID()||"")
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def acl_state_js(
    device: str, acl_id: str, out_port: str
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    acl_text = json.dumps(acl_id, ensure_ascii=False)
    port_text = json.dumps(out_port, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var proc=d.getProcess("AclProcess");
    if(!proc)return "ERROR:acl_process_not_found";
    var aclId={acl_text};
    var acl=proc.getAcl(aclId);
    var commands=[];
    if(acl){{
      for(var i=0;i<acl.getCommandCount();i++)commands.push(String(acl.getCommandAt(i)));
    }}
    var p=d.getPort({port_text});
    if(!p)return "ERROR:port_not_found";
    return JSON.stringify({{
      device:{device_text},
      aclId:aclId,
      exists:!!acl,
      commands:commands,
      outPort:{port_text},
      aclOut:String(p.getAclOutID()||"")
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def fast_forward_js() -> str:
    return """(function(){
  try{
    ipc.appWindow().getRealtimeToolbar().fastForwardTime();
    return JSON.stringify({ok:true});
  }catch(e){
    return JSON.stringify({ok:false,error:String(e)});
  }
})()"""


def run_ios_cli_js(
    device: str,
    commands: list[str],
    *,
    prepare_boot_dialog: bool = False,
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    commands_json = json.dumps(commands, ensure_ascii=False)
    prologue = (
        'try{d.skipBoot();}catch(e){}'
        'cl.enterCommand("");'
        'cl.enterCommand("no");'
        'cl.enterCommand("");'
        if prepare_boot_dialog
        else ""
    )
    template = """(function(){
  try{
    var d=ipc.network().getDevice(__DEVICE__);
    if(!d)return "ERROR:device_not_found";
    var cl=d.getCommandLine();
    __PROLOGUE__
    cl.enterCommand("enable");
    cl.enterCommand("terminal length 0");
    var before=cl.getOutput().length;
    var commands=__COMMANDS__;
    for(var i=0;i<commands.length;i++)cl.enterCommand(commands[i]);
    return JSON.stringify({
      commands:commands,
      outputStart:Number(before),
      output:String(cl.getOutput()||"").substring(before)
    });
  }catch(e){
    return "ERROR:"+String(e&&e.message?e.message:e);
  }
})()"""
    return (
        template.replace("__DEVICE__", device_text)
        .replace("__PROLOGUE__", prologue)
        .replace("__COMMANDS__", commands_json)
    )


def terminal_state_js(device: str) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var cl=d.getCommandLine();
    return JSON.stringify({{
      device:{device_text},
      prompt:String(cl.getPrompt()||""),
      mode:String(cl.getMode()||""),
      outputLength:Number(String(cl.getOutput()||"").length),
      booting:typeof d.isBooting==="function"?!!d.isBooting():null
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def enter_ios_command_js(device: str, command: str) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    command_text = json.dumps(command, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var cl=d.getCommandLine();
    var before=Number(String(cl.getOutput()||"").length);
    cl.enterCommand({command_text});
    return JSON.stringify({{
      device:{device_text},
      command:{command_text},
      outputStart:before,
      prompt:String(cl.getPrompt()||"")
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def routing_state_js(device: str) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var routing=d.getProcess("RoutingProcess");
    if(!routing)return "ERROR:routing_process_not_found";
    var table=routing.getRoutingTable();
    var networks=[];
    var routingNetworks=table.routingNetworks||[];
    for(var i=0;i<routingNetworks.length;i++){{
      var network=routingNetworks[i];
      var entries=[];
      var rawEntries=network.routingEntries||[];
      for(var j=0;j<rawEntries.length;j++){{
        var entry=rawEntries[j];
        entries.push({{
          protocol:String(entry.typeOfProtocol),
          network:String(entry.networkId),
          mask:String(entry.subnetMask),
          port:String(entry.portName||""),
          nextHop:String(entry.nextHop),
          adminDistance:Number(entry.adminDistance),
          metric:Number(entry.metric)
        }});
      }}
      networks.push({{
        network:String(network.network),
        mask:String(network.subnetMask),
        entries:entries
      }});
    }}
    var staticRoutes=[];
    for(var k=0;k<routing.getStaticRouteCount();k++){{
      var route=routing.getStaticRouteAt(k);
      staticRoutes.push({{
        network:String(route.networkId),
        mask:String(route.subnetMask),
        port:String(route.portName||""),
        nextHop:String(route.nextHop),
        adminDistance:Number(route.adminDistance)
      }});
    }}
    return JSON.stringify({{
      device:{device_text},
      networks:networks,
      staticRoutes:staticRoutes
    }});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def configure_static_routes_js(
    device: str,
    routes: list[dict[str, object]],
) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    routes_text = json.dumps(routes, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var routing=d.getProcess("RoutingProcess");
    if(!routing)return "ERROR:routing_process_not_found";
    var specs={routes_text};
    var added=[];
    for(var i=0;i<specs.length;i++){{
      var spec=specs[i];
      added.push({{
        network:spec.network,
        mask:spec.mask,
        nextHop:spec.nextHop,
        port:spec.port,
        adminDistance:Number(spec.admin_distance||1),
        ok:!!routing.addStaticRoute(
          spec.network,
          spec.mask,
          spec.nextHop,
          String(spec.port||""),
          Number(spec.admin_distance||1)
        )
      }});
    }}
    return JSON.stringify({{device:{device_text},added:added}});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def start_ping_js(device: str, destination: str) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    destination_text = json.dumps(destination, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var cl=d.getCommandLine();
    var before=cl.getOutput().length;
    cl.enterCommand("ping "+{destination_text});
    return JSON.stringify({{outputStart:Number(before)}});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def start_traceroute_js(device: str, destination: str) -> str:
    device_text = json.dumps(device, ensure_ascii=False)
    destination_text = json.dumps(destination, ensure_ascii=False)
    return f"""(function(){{
  try{{
    var d=ipc.network().getDevice({device_text});
    if(!d)return "ERROR:device_not_found";
    var cl=d.getCommandLine();
    var before=cl.getOutput().length;
    cl.enterCommand("tracert "+{destination_text});
    return JSON.stringify({{outputStart:Number(before)}});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def read_command_output_js(device: str, offset: int) -> str:
    template = """(function(){
  try{
    var d=ipc.network().getDevice(__DEVICE__);
    if(!d)return "ERROR:device_not_found";
    var output=String(d.getCommandLine().getOutput()||"");
    return JSON.stringify({
      output:output.substring(Math.max(0,__OFFSET__))
    });
  }catch(e){
    return "ERROR:"+String(e&&e.message?e.message:e);
  }
})()"""
    return (
        template.replace(
            "__DEVICE__", json.dumps(device, ensure_ascii=False)
        ).replace("__OFFSET__", str(int(offset)))
    )


def save_project_js(path: Path) -> str:
    path_text = json.dumps(str(path.resolve()), ensure_ascii=False)
    return f"""(function(){{
  try{{
    ipc.appWindow().fileSaveAsNoPrompt({path_text},true);
    return JSON.stringify({{ok:true}});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""


def file_size_js(path: Path) -> str:
    path_text = json.dumps(str(path.resolve()), ensure_ascii=False)
    return f"""(function(){{
  try{{
    var s=ipc.systemFileManager();
    return JSON.stringify({{
      exists:!!s.fileExists({path_text}),
      size:Number(s.getFileSize({path_text}))
    }});
  }}catch(e){{
    return JSON.stringify({{exists:false,size:0,error:String(e)}});
  }}
}})()"""


def open_project_js(path: Path) -> str:
    path_text = json.dumps(str(path.resolve()), ensure_ascii=False)
    return f"""(function(){{
  try{{
    var r=ipc.appWindow().fileOpen({path_text});
    return JSON.stringify({{result:Number(r)}});
  }}catch(e){{
    return "ERROR:"+String(e&&e.message?e.message:e);
  }}
}})()"""

