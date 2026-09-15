"""Cross-source navigation uses audited identities, never name guesses."""
from vm_metrics import VERIFIED_BINDINGS

# LXC eth0 address/MAC verified through read-only pct exec on proxmox-ii.
LXC_BINDINGS = {
    101: ('mediaservers', '680f79cd6a6313ac1f9f2ab3', 'https://192.168.2.205:8120'),
    128: ('minecraft-controller', '689481c037b774df4b04ea0f', 'https://192.168.3.12:8120'),
}


def link_ranked_hosts(summary, servers):
    by_id = {s['id']: s for s in servers}
    guests = {(g['type'], g['id']): g for g in summary['pve'].get('guest_inventory') or []}
    links = {}
    for kind, bindings in [('qemu', VERIFIED_BINDINGS), ('lxc', LXC_BINDINGS)]:
        for vmid, binding in bindings.items():
            guest = guests.get((kind, vmid))
            server = by_id.get(binding[1], {})
            if (guest and guest['name'] == binding[0]
                    and server.get('info', {}).get('address') == binding[2]):
                links[binding[1]] = guest.get('url')
    for row in summary['top_disk']:
        row['url'] = links.get(row.get('server_id'))
        row['navigation_source'] = 'Proxmox' if row['url'] else 'Unverified Proxmox identity'
