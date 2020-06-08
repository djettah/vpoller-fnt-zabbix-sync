from debugtoolkit.debugtoolkit import deflogger, dry_request, init_logger, measure


def get_zabbix_hosts(zapi, zabbix_hostgroup_id):
    hosts = zapi.host.get(
        output=["name", "host", "status", "description"],
        selectInterfaces=["ip", "interfaceid", "dns", "type"],
        groupids=zabbix_hostgroup_id,
        selectMacros="extend",
    )
    hosts_indexed_by_host = {host["host"]: host for host in hosts}
    return hosts, hosts_indexed_by_host


def get_zabbix_hostgroupid_by_name(zapi, name):
    groups = zapi.hostgroup.get(filter={"name": name})
    if groups:
        return int(groups[0]["groupid"])
    else:
        return None


def get_zabbix_templateid_by_name(zapi, name):
    return int(zapi.template.get(filter={"host": name})[0]["templateid"])


def get_zabbix_proxyid_by_name(zapi, name):
    return int(zapi.proxy.get(filter={"host": name})[0]["proxyid"])


# def get_zabbix_host_triggers(zapi, hostids):
#     triggers = zapi.trigger.get(
#         hostids=hostids,
#         output=["description", "status"],
#         selectTags="extend",
#         selectFunctions=["itemid"]
#     )
#     for trigger in triggers:
#         for tag in trigger['tags']:
#             if tag['tag'] == 'FNT_Flag':
#                 trigger['tag'] = tag['value']
#     # tag_flag = [tag['value'] for trigger in triggers for tag in trigger['tags'] if tag['tag'] == 'FNT_Flag']
#     triggers_indexed_by_tag = {trigger['tag']: trigger for trigger in triggers if trigger.get('tag')}
#     return triggers, triggers_indexed_by_tag


# def get_zabbix_host_items(zapi, hostids):
#     items = zapi.item.get(
#         hostids=hostids,
#         output=["status"],
#         selectApplications="extend",
#     )
#     # apps = []
#     items_indexed_by_app ={}
#     for item in items:
#         for app in item['applications']:
#             # apps.append(app['name'])
#             if not items_indexed_by_app.get(app['name']):
#                 items_indexed_by_app[app['name']] = []
#             items_indexed_by_app[app['name']].append(item)

#     # items_indexed_by_app = {app: item for item in items if item['applications'].get(app)}
#     return items, items_indexed_by_app

@deflogger
def get_zabbix_triggers(zapi, mode, groupids):
    if mode == 'groupupdate':
        triggers = zapi.trigger.get(
            # hostids=hostids,
            groupids=groupids,
            output=["status", "value"],
            selectTags="extend",
            # selectFunctions=["itemid"],
            selectHosts=['host']
        )

    if mode == 'sync':
        triggers = zapi.trigger.get(
            # hostids=hostids,
            groupids=groupids,
            output=["status"],
            selectTags="extend",
            # selectFunctions=["itemid"],
            selectHosts=['host']
        )
    triggers_indexed_by_hostids = {}

    for trigger in triggers:
        for tag in trigger['tags']:
            if tag['tag'] == 'FNT_Flag':
                trigger['tag'] = tag['value']
        hostid = trigger['hosts'][0]['hostid']
        if not triggers_indexed_by_hostids.get(hostid):
            triggers_indexed_by_hostids[hostid] = []
        triggers_indexed_by_hostids[hostid].append(trigger)

    # purge disabled hosts
    if mode == 'groupupdate':
        disabled_list = []
        for hostid in triggers_indexed_by_hostids:
            disabled = all([ int(trigger['status']) for trigger in triggers_indexed_by_hostids[hostid] ])
            if disabled:
                disabled_list.append(hostid)
        for hostid in disabled_list:
            del triggers_indexed_by_hostids[hostid]
    triggers = []
    for hostid in triggers_indexed_by_hostids:
        triggers.extend(triggers_indexed_by_hostids[hostid])

    return triggers, triggers_indexed_by_hostids


@deflogger
def get_zabbix_items(zapi, groupids):
    items = zapi.item.get(
        # hostids=hostids,
        groupids=groupids,
        output=["status"],
        selectApplications="extend",
        selectHosts=['hostid']
    )

    items_indexed_by_hostids = {}
    for item in items:
        hostid = item['hosts'][0]['hostid']
        if not items_indexed_by_hostids.get(hostid):
            items_indexed_by_hostids[hostid] = []
        items_indexed_by_hostids[hostid].append(item)

    return items, items_indexed_by_hostids


logger = init_logger()
