"""
bgp-summary.py
 
Displays a consolidated BGP summary across all routing instances, showing
peer state, group, AS, uptime, prefix counts (received/active/advertised),
and description in a single table per instance.
 
USAGE
-----
Remote (from any host with Python and junos-eznc installed):
    python bgp-summary.py --host <device-ip>
    python bgp-summary.py --host <device-ip> --instance <vrf>
 
On-box as a Junos op script:
    Copy to /var/db/scripts/op/ on the device, add this configuration:

    [edit system scripts op]
    file bgp-summary.py {
        command bs;
        arguments {
            instance {
                description "Show information for this instance";
            }
        }
    }

    then run:
    op bs
    op bs instance <vrf>
 
ARGUMENTS
---------
--host        Hostname or IP address of the device (omit when running as op script)
--instance    Limit output to a single routing instance (optional)
 
DEPENDENCIES
------------
    pip install junos-eznc pyyaml
"""

import argparse
import yaml
from jnpr.junos import Device
from jnpr.junos.factory import FactoryLoader

bgp_definition = """
RouteSummaryTable:
  rpc: get-route-summary-information
  item: route-table
  key: table-name
  view: RouteSummaryView

RouteSummaryView:
  fields:
    table: table-name
    destination: destination-count
    total: total-route-count
    active: active-route-count
    hidden: hidden-route-count

BgpSummaryTable:
  rpc: get-bgp-summary-information
  item: bgp-peer
  key: peer-address
  view: BgpSummaryView

BgpSummaryView:
  fields:
    peer_address: peer-address
    elapsed_time: elapsed-time

BgpNeighborTable:
  rpc: get-bgp-neighbor-information
  item: bgp-peer
  key: peer-address
  view: BgpNeighborView

BgpNeighborView:
  fields:
    peer_address: peer-address
    peer_as: peer-as
    local_address: local-address
    local_as: local-as
    description: description
    group: peer-group
    type: peer-type
    state: peer-state
    instance: peer-cfg-rti
    active_prefix: bgp-rib/active-prefix-count
    received_prefix: bgp-rib/received-prefix-count
    accepted_prefix: bgp-rib/accepted-prefix-count
    suppressed_prefix: bgp-rib/suppressed-prefix-count
    advertised_prefix: bgp-rib/advertised-prefix-count
"""

loader = FactoryLoader()
classes = loader.load(yaml.safe_load(bgp_definition))
BgpNeighborTable = classes['BgpNeighborTable']
RouteSummaryTable = classes['RouteSummaryTable']
BgpSummaryTable = classes['BgpSummaryTable']

parser = argparse.ArgumentParser(description="show bgp summary information with details")
parser.add_argument("--instance", help="Instance")
parser.add_argument("--host", help="Hostname or IP address of the device")
args = parser.parse_args()

def format_peer_row(neighbor, bgp_summary, routes):
    """Format a BGP neighbor as a table row."""
    peer_address = neighbor.peer_address.split('+')[0]
    elapsed_time = bgp_summary[peer_address].elapsed_time if peer_address in bgp_summary else "N/A"
    return f"{peer_address:<16} {neighbor.group:<10} {neighbor.peer_as:<7} {elapsed_time:<14} {neighbor.state:<6.6} {routes:<17} {neighbor.description}"

def main():
    with Device(host=args.host) as dev:
        bgp_neighbour = BgpNeighborTable(dev).get()
        route_summary = RouteSummaryTable(dev).get()
        bgp_summary = BgpSummaryTable(dev).get()

        # When running as a Junos op script, mgd consumes one \n, so we need \n\n
        newline = "\n" if args.host else "\n\n"

        header = f"{'Neighbor':<16} {'Group':<10} {'AS':<7} {'Last Up/Dwn':<14} {'State':<6} {'Rec/Acc/Adv':<17} {'Description'}"
        print(header)

        instances = sorted(set(neighbor.instance for neighbor in bgp_neighbour),
                          key=lambda x: (x != 'master', x))

        for instance in instances:
            if args.instance and instance != args.instance:
                continue
            
            route_table_name = f"{instance}.inet.0" if instance != "master" else "inet.0"
            instance_summary = route_summary[route_table_name]
            active_hidden = f"[{instance_summary.active} active, {instance_summary.hidden} hidden]" if instance_summary else ""
            print(f"{newline}Instance: {instance} {active_hidden}")

            for neighbor in bgp_neighbour:
                if neighbor.instance == instance:
                    routes = (f"{neighbor.received_prefix}/{neighbor.active_prefix}/{neighbor.advertised_prefix}" if neighbor.state == "Established" else "")
                    print(format_peer_row(neighbor, bgp_summary, routes))

if __name__ == "__main__":
    main()