import json
import math
import os
import re
import sys
import time
import random
import uuid
import glob

from dateutil import parser
from pyzabbix.api import ZabbixAPI, ZabbixAPIException
from pyzabbix import ZabbixMetric, ZabbixSender

import vfzsync

import debugtoolkit.debugtoolkit as debugtoolkit
from debugtoolkit.debugtoolkit import (
    init_logger,
    crash_me,
    debug_exception,
    deflogger,
    deflogger_module,
    dry_request,
    handle_exception,
    measure,
    measure_class,
)
from .extrafuncs import *
from .fntapi import *
from .vpollerapi import *
from .zabbixapi import *

# globals

VPOLLER_FNT_TRANSFORM_MAP = [
    ("config.instanceUuid", "cUuid"),
    ("name", "visibleId"),
    ("config.hardware.numCPU", "cCpu"),
    ("config.hardware.memoryMB", "cRam"),
    ("runtime.powerState", "cSdiStatus"),
    ("config.annotation", "remark"),
    ("last_backup", "cSdiLastBackup"),
    ("vc_host", "datasource"),
    ("summary.storage.committed.gb", "cSdiHddUsed"),
    ("summary.storage.provisioned.gb", "cSdHddTotal"),
    ("summary.guest.hostName", "cSdiHostname"),
    ("summary.config.guestFullName", "virtualMachineType"),
    # ("summary.guest.guestFullName", "virtualMachineType"),
]

FNT_VS_LINKED_IP_TRANSFORM_MAP = [("ipAddress", "ipAddress")]
FNT_VS_LINKED_FS_TRANSFORM_MAP = [
    ("diskPath", "mountpoint"),
    # ("capacity", "capacityGb"),
    ("capacityGb", "capacityGb"),
    ("usedGb", "usedGb"),
]
FNT_VS_LINKED_ENTITIES = {
    "vmIpAddress": {
        "index": "ipAddress",
        "class_name": "vmIpAddress",
        "class_custom": True,
        "relation_class_name": "CustomVmIpAddress",
        "relation_class_name_plural": "CustomVmIpAddresses",
        "transform_map": FNT_VS_LINKED_IP_TRANSFORM_MAP,
    },
    "fileSystem": {
        "index": "mountpoint",
        "class_name": "fileSystem",
        "class_custom": False,
        "relation_class_name": "FileSystem",
        "relation_class_name_plural": "FileSystems",
        "transform_map": FNT_VS_LINKED_FS_TRANSFORM_MAP,
    },
}

VPOLLER_VM_ATTRIBUTES = [
    "name",
    "config.instanceUuid",
    "config.hardware.numCPU",
    "config.hardware.memoryMB",
    "runtime.powerState",
    "config.annotation",
    # "summary.storage.unshared",
    "summary.storage.committed",
    "summary.storage.uncommitted",
    "summary.guest.hostName",
    "summary.config.guestFullName"
    # "summary.guest.guestFullName"
]
VPOLLER_VM_NET_ATTRIBUTES = ["ipAddress"]
VPOLLER_VM_DISK_ATTRIBUTES = ["diskPath", "capacity", "freeSpace", "freeSpacePercentage"]

FNT_VS_FILTER_VPOLLER_FNT = {
    # "cUuid": {"operator": "like", "value": "*-*-*-*-*"},
    "datasource": {"operator": "=", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
    # "cCSdiDelConfirmed": {"operator": "like", "value": "N"},
    # "cSdiDeleted": {"operator": "like", "value": "N"},
}

FNT_VS_FILTER_FNT_ZABBIX = {
    # "cUuid": {"operator": "like", "value": "*-*-*-*-*"},
    "datasource": {"operator": "=", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
    "cSdiNewServer": {"operator": "like", "value": "N"},
}

FNT_VS_FILTER_FNT_NEW_SERVERS = {
    # "cUuid": {"operator": "like", "value": "*-*-*-*-*"},
    "datasource": {"operator": "=", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
    "cSdiNewServer": {"operator": "like", "value": "Y"},
}

FNT_VS_FILTER_FNT_DELETED_UNCONFIRMED_SERVERS = {
    # "cUuid": {"operator": "like", "value": "*-*-*-*-*"},
    "datasource": {"operator": "=", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
    "cSdiDeleted": {"operator": "like", "value": "Y"},
    "cCSdiDelConfirmed": {"operator": "like", "value": "N"},
}

FNT_VS_FILTER_FNT_UPDATE = {
    # "cUuid": {"operator": "like", "value": "*-*-*-*-*"},
    "datasource": {"operator": "=", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
    # "cSdiNewServer": {"operator": "like", "value": "N"},
    "cSdiDeleted": {"operator": "like", "value": "N"},
}

FNT_VS_FILTER_STATS = {
    # "cUuid": {"operator": "like", "value": "*-*-*-*-*"},
    "datasource": {"operator": "=", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
}

FNT_VS_ATTRIBUTES = [
    "id",
    "visibleId",
    "elid",
    "cCpu",
    "cRam",
    "cManagementInterface",
    "cCommunityName",
    "cSdiNewServer",
    "cSdiMonitoring",
    "cSdiDeleted",
    "cCSdiDelConfirmed",
    "cUuid",
    "cSdiStatus",
    "cSdHddTotal",
    "cSdiHddUsed",
    "cSdiBackupNeeded",
    "cSdiLastBackup",
    "cSdiMonitoringSnmp",
    "cSdiNoShutdown",
    "remark",
    "datasource",
    "cSdiHostname",
    "cSdiPurpose",
    "virtualMachineType",
    "cServerWithHistory",
]

FNT_ZABBIX_FLAG_TRIGGERS = [
    "cSdiMonitoring",
    "cSdiMonitoringSnmp",
    "cSdiNoShutdown",
    "cSdiBackupNeeded",
]

ZABBIX_MACROS = ["{$SNMP_COMMUNITY}", "{$HOST_PURPOSE}", "{$VSPHERE.HOST}"]


class VFZException(Exception):
    pass


def init_tracing():
    if debugtoolkit.TRACE:
        for module in [
            "vfzsync",
            "vfzsync.lib.fntapi",
            "vfzsync.lib.vpollerapi",
            "vfzsync.lib.zabbixapi",
            "vfzsync.lib.vfzlib",
        ]:
            if module in sys.modules:
                deflogger_module(sys.modules[module], deflogger, deflogger_class)
                # deflogger_module(sys.modules[module], measure, measure_class)
                deflogger_module(sys.modules[module], measure(operation=sum))


def test_config():
    # print(vfzsync.CONFIG)
    print("test_config")


def get_vpoller_vms(vpoller):
    vpoller_resp = vpoller.run(method="vm.discover", vc_host=vfzsync.CONFIG["vpoller"]["vc_host"])
    vm_names = [vm["name"] for vm in vpoller_resp]
    vms = []

    # progress counter
    counter = ProgressCounter(len(vm_names), 10, 60)

    for vm_name in vm_names:
        progress = counter.iterate()
        if progress:
            logger.info(f"{sys._getframe().f_code.co_name} progress: {counter.progress}%")

        try:
            vm = vpoller.run(
                method="vm.get",
                vc_host=vfzsync.CONFIG["vpoller"]["vc_host"],
                name=vm_name,
                properties=VPOLLER_VM_ATTRIBUTES,
            )[0]

            nets = vpoller.run(
                method="vm.guest.net.get",
                vc_host=vfzsync.CONFIG["vpoller"]["vc_host"],
                name=vm_name,
                properties=VPOLLER_VM_NET_ATTRIBUTES,
            )

            disks_discovery = vpoller.run(
                method="vm.disk.discover", vc_host=vfzsync.CONFIG["vpoller"]["vc_host"], name=vm_name
            )

            disks_indexed = {}
            for disk_obj in disks_discovery[0]["disk"]:
                disk = vpoller.run(
                    method="vm.disk.get",
                    vc_host=vfzsync.CONFIG["vpoller"]["vc_host"],
                    name=vm_name,
                    key=disk_obj["diskPath"],
                    properties=VPOLLER_VM_DISK_ATTRIBUTES,
                )[0]["disk"]
                disks_indexed[disk_obj["diskPath"]] = disk
            # disks_indexed = {disk['diskPath']:disk for disk in disks}
            ips = flatten([net["ipAddress"] for net in nets["net"]])
            ips_v4 = [ip for ip in ips if re.match(r"(\d+\.){3}\d+", ip)]
            ips_indexed = {ip: {"ipAddress": ip} for ip in ips_v4}
            vm["ipAddress"] = ips_indexed
            vm["mountpoint"] = disks_indexed
            vm["summary.storage.provisioned"] = (
                vm["summary.storage.committed"] + vm["summary.storage.uncommitted"]
            )
            (vm["summary.storage.committed.gb"], vm["summary.storage.provisioned.gb"],) = list(
                map(gib_round, [vm["summary.storage.committed"], vm["summary.storage.provisioned"]])
            )

            vms.append(vm)
        except vPollerException:
            logger.exception(f"Failed to get VM {vm_name} properties.")
            raise VFZException("Failed to get VM data from vPoller")

    vms_indexed = {vm["config.instanceUuid"]: vm for vm in vms}

    return vms, vms_indexed


#%%
def get_fnt_vs(command, index, restrictions, related_entities=False):

    virtualservers = command.get_entities(
        "virtualServer", attributes=FNT_VS_ATTRIBUTES, restrictions=restrictions
    )
    virtualservers_indexed = {vs[index]: vs for vs in virtualservers}

    # get linked entities
    if related_entities:
        for vs in virtualservers:
            for entity_class_name in FNT_VS_LINKED_ENTITIES:
                relation_class_name = FNT_VS_LINKED_ENTITIES[entity_class_name]["relation_class_name_plural"]
                entities = command.get_related_entities(
                    "virtualServer", entity_elid=vs["elid"], relation_type=relation_class_name
                )
                index = FNT_VS_LINKED_ENTITIES[entity_class_name]["index"]
                entities_indexed = {entity["entity"][index]: entity for entity in entities}
                vs[entity_class_name] = entities_indexed

    return virtualservers, virtualservers_indexed


def sync_fnt_vs(command, vpoller_vms, fnt_virtualservers_indexed):

    # progress counter
    counter = ProgressCounter(len(vpoller_vms), 25, 60)

    # create/update vs
    for vm in vpoller_vms:
        progress = counter.iterate()
        if progress:
            logger.info(f"{sys._getframe().f_code.co_name} progress: {counter.progress}%")

        vm_uuid = vm["config.instanceUuid"]
        vm_annotation = vm["config.annotation"]

        # do we have a matching vs?
        vs = fnt_virtualservers_indexed.get(vm_uuid, {})

        vs_attr_updateset = {}

        # populate extra vm attributes
        # vm["last_backup"] = "1970-01-01T00:00:00Z"  # default backup date
        vm["last_backup"] = None
        vm["vc_host"] = vfzsync.CONFIG["vpoller"]["vc_host"]
        if m := re.match(r".*Time: \[(\d\d\.\d\d\.\d\d\d\d .*?)\].*", vm_annotation):  # noqa
            last_backup = m.group(1)
            last_backup = re.sub(
                r"(\d{1,2})\.(\d{1,2})\.(\d{4}) (\d{1,2}:\d{1,2}:\d{1,2})",
                f'\\3-\\2-\\1T\\4{( time.strftime("%z", time.localtime() ) )}',
                last_backup,
            )
            # validate date
            last_backup = parser.parse(last_backup).strftime("%Y-%m-%dT%H:%M:%S%z")
            vm["last_backup"] = last_backup
            if vs.get("cSdiLastBackup"):
                last_backup_local = datetime_to_local_timezone(parser.parse(vs["cSdiLastBackup"])).strftime(
                    "%Y-%m-%dT%H:%M:%S%z"
                )
                vs["cSdiLastBackup"] = last_backup_local

        # compare and update attributes
        for tm_entry in VPOLLER_FNT_TRANSFORM_MAP:
            vm_attr, vs_attr = tm_entry
            if normalize_none(vm.get(vm_attr, "")) != normalize_none(vs.get(vs_attr)):
                vs_attr_updateset[vs_attr] = normalize_none(vm.get(vm_attr, ""))

        if vs:
            # undelete vs if discovered again
            if yes_no(vs["cSdiDeleted"]):
                if yes_no(vs["cCSdiDelConfirmed"]):
                    vs_attr_updateset["cSdiNewServer"] = "Y"
                vs_attr_updateset["cSdiDeleted"] = "N"
                vs_attr_updateset["cCSdiDelConfirmed"] = "N"

            # update linked entities
            sync_fnt_vs_entities(command, vs=vs, vm=vm, vs_attr_updateset=vs_attr_updateset)

        # do we have attributes to create/update
        if vs_attr_updateset:
            create_update_fnt_vs(command, vs=vs, vs_attr_updateset=vs_attr_updateset)


def sync_fnt_vs_entities(command, vs, vm, vs_attr_updateset):
    vs_elid = vs["elid"]
    vs_name = vs["visibleId"]
    hdd_total = hdd_used = 0

    for entity_class_name in FNT_VS_LINKED_ENTITIES:
        vs_entities = vs.get(entity_class_name)
        # entity_class_name = FNT_VS_LINKED_ENTITIES[entity_class_name]["class_name"]
        entity_definition = FNT_VS_LINKED_ENTITIES[entity_class_name]
        entity_class_custom = entity_definition["class_custom"]
        entity_relation_class_name = entity_definition["relation_class_name"]
        entity_index = entity_definition["index"]
        entity_transform_map = entity_definition["transform_map"]
        vm_entities = vm.get(entity_index, [])
        # safety: do not sync if no vm data and not marked for deletion
        if not vm_entities and not yes_no(vs_attr_updateset.get("cSdiDeleted", "N")):
            continue

        for entity_key in vm_entities:
            vm_entity = vm[entity_index][entity_key]
            vs_entity = vs_entities.get(entity_key, {}).get("entity", {})
            entity_attr_updateset = {}
            if entity_class_name == "fileSystem":
                vm_entity["capacityGb"] = gib_round(vm_entity["capacity"])
                vm_entity["usedGb"] = gib_round(vm_entity["capacity"] - vm_entity["freeSpace"])
                hdd_total += vm_entity["capacity"]
                hdd_used += vm_entity["capacity"] - vm_entity["freeSpace"]
            for tm_entry in entity_transform_map:
                vm_attr, vs_attr = tm_entry
                if vm_entity[vm_attr] != normalize_none(vs_entity.get(vs_attr)):
                    entity_attr_updateset[vs_attr] = vm_entity[vm_attr]

            if entity_attr_updateset:
                try:
                    if vs_entity:
                        command.update_entity(
                            entity_type=entity_class_name,
                            entity_elid=vs_entity["elid"],
                            **entity_attr_updateset,
                        )
                        logger.debug(
                            f"VirtualServer {vs_name}: Updated {entity_class_name}: {entity_attr_updateset}."
                        )
                    # new entity
                    else:
                        new_entity = command.create_entity(
                            entity_type=entity_class_name,
                            entity_custom=entity_class_custom,
                            **entity_attr_updateset,
                        )
                        new_entity_elid = new_entity["elid"]
                        new_entity_link = command.create_related_entities(
                            entity_type="virtualServer",
                            entity_elid=vs_elid,
                            relation_type=entity_relation_class_name,
                            linked_elid=new_entity_elid,
                        )
                        logger.info(
                            f"VirtualServer {vs_name}: Created {entity_class_name}: {entity_attr_updateset}."
                        )

                except FNTException:
                    logger.exception(
                        f"VirtualServer {vs_name}: Failed to create/update {entity_class_name}: {entity_attr_updateset}."
                    )

        cleanup_fnt_vs_entities(
            command,
            vs,
            vm,
            vs_entities,
            entity_class_name,
            vs_attr_updateset,
            entity_index,
            entity_class_custom,
        )


# def create_update_fnt_vs_entities(command, entity_attr_updateset, vs_entity=None,
# entity_class_name=None, entity_class_custom=False):
#     try:
#         if not vs_entity:
#             command.create_entity(entity_type="virtualServer", **entity_attr_updateset)
#             logger.info(f'Created VirtualServer {entity_attr_updateset["visibleId"]}.')
#         else:
#             command.update_entity(entity_type="virtualServer", entity_elid=vs_entity["elid"], **entity_attr_updateset)
#             logger.info(f'Updated VirtualServer {vs_entity["visibleId"]}.')
#         logger.debug(f"VirtualServer attributes: {entity_attr_updateset}")
#     except FNTException:
#         logger.error(f"Failed to create/update VirtualServer: {entity_attr_updateset}.")


def cleanup_fnt_vs_entities(
    command,
    vs,
    vm,
    vs_entities,
    entity_class_name,
    vs_attr_updateset,
    entity_index,
    entity_class_custom,
    # delete_if_empty=False,
):

    for entity in vs_entities:
        linked_entity = vs_entities[entity]["entity"][entity_index]
        vm_entities = vm.get(entity_index, [])
        # safety check
        # if not delete_if_empty and not vm_entities:
        if not vm_entities and not yes_no(vs_attr_updateset.get("cSdiDeleted", "N")):
            return
        if linked_entity not in vm_entities:
            # link_elid = entities[entity]["relation"]["linkElid"]
            linked_elid = vs_entities[entity]["entity"]["elid"]

            # deprecated
            # if entity_class_name == "vmIpAddress":
            #     if vs["cManagementInterface"] == linked_entity:
            #         vs_attr_updateset["cManagementInterface"] = ""
            #         # disable monitoring if mgmt ip changes and vm not deleted
            #         if not yes_no(vs_attr_updateset.get("cSdiDeleted", "N")):
            #             vs_attr_updateset["cSdiMonitoring"] = "N"
            #             vs_attr_updateset["cSdiMonitoringSnmp"] = "N"

            command.delete_entity(
                entity_type=entity_class_name, entity_custom=entity_class_custom, entity_elid=linked_elid,
            )
            # command.delete_related_entities(
            #     "virtualServer", vs_elid, entity_relation_class_name, link_elid
            # )
            logger.info(
                f"VirtualServer {vs['visibleId']}: Deleted entity {entity_class_name}: {linked_entity}"
            )


def create_update_fnt_vs(command, vs_attr_updateset, vs=None):
    try:
        if not vs:
            vs_attr_updateset["cSdiNewServer"] = "Y"
            return_data = command.create_entity(entity_type="virtualServer", **vs_attr_updateset)
            logger.info(f'Created VirtualServer {vs_attr_updateset["visibleId"]}.')

        else:
            return_data = command.update_entity(
                entity_type="virtualServer", entity_elid=vs["elid"], **vs_attr_updateset
            )
            logger.info(f'Updated VirtualServer {vs["visibleId"]}.')

        logger.debug(f"VirtualServer attributes: {vs_attr_updateset}")
        return return_data
    except FNTException as e:
        logger.exception(e)
        logger.error(f"Failed to create/update VirtualServer: {vs_attr_updateset}.")


def cleanup_fnt_vs(command, fnt_virtualservers, vpoller_vms_indexed):
    for vs in fnt_virtualservers:
        vs_uuid = vs["cUuid"]
        vs_attr_updateset = {}
        # safety: do not sync if no vms received
        if vpoller_vms_indexed and not vpoller_vms_indexed.get(vs_uuid) and not yes_no(vs["cSdiDeleted"]):
            vs_attr_updateset = {"cSdiDeleted": "Y", "cSdiNewServer": "N", "cCSdiDelConfirmed": "N"}
            try:
                sync_fnt_vs_entities(command, vs=vs, vm={}, vs_attr_updateset=vs_attr_updateset)

                action = "update"
                if yes_no(vs["cSdiNewServer"]):
                    if yes_no(vs["cServerWithHistory"]):
                        vs_attr_updateset["cCSdiDelConfirmed"] = "Y"
                    else:
                        action = "delete"

                if action == "update":
                    command.update_entity(
                        entity_type="virtualServer", entity_elid=vs["elid"], **vs_attr_updateset
                    )
                    logger.info(f'Updated VirtualServer {vs["visibleId"]}.')
                    logger.debug(f'VirtualServer {vs["visibleId"]} update set: {vs_attr_updateset}')
                if action == "delete":
                    command.delete_entity(entity_type="virtualServer", entity_elid=vs["elid"])
                    logger.info(f'Deleted VirtualServer {vs["visibleId"]}.')

            except FNTException as e:
                logger.error(f"Failed to create/update/delete VirtualServer: {vs_attr_updateset}.")
                logger.exception(str(e))


def sync_zabbix_hosts(zapi, fnt_virtualservers, zabbix_hosts_indexed_by_host):
    zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(zapi, vfzsync.CONFIG["zabbix"]["hostgroup"])
    zabbix_template_id = get_zabbix_templateid_by_name(zapi, vfzsync.CONFIG["zabbix"]["template"])
    zabbix_proxy_id = get_zabbix_proxyid_by_name(zapi, vfzsync.CONFIG["zabbix"]["proxy"])

    hostids = [zabbix_hosts_indexed_by_host[hostname]["hostid"] for hostname in zabbix_hosts_indexed_by_host]
    triggers, triggers_indexed_by_hostids = get_zabbix_triggers(
        zapi=zapi, mode="sync", groupids=zabbix_hostgroup_id
    )
    items, items_indexed_by_hostids = get_zabbix_items(zapi=zapi, groupids=zabbix_hostgroup_id)

    counter = ProgressCounter(len(fnt_virtualservers), 25, 60)
    for vs in fnt_virtualservers:
        progress = counter.iterate()
        if progress:
            logger.info(f"{sys._getframe().f_code.co_name} progress: {counter.progress}%")

        # skip new servers
        if yes_no(vs["cSdiNewServer"]):
            continue
        host = zabbix_hosts_indexed_by_host.get(vs["id"], {})
        host_updateset = {}
        hostinterface_updateset = {}
        hostmacros_updateset = [
            {"macro": "{$SNMP_COMMUNITY}", "value": vs["cCommunityName"]},
            {"macro": "{$VSPHERE.HOST}", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
            {"macro": "{$HOST_PURPOSE}", "value": vs["cSdiPurpose"]},
        ]
        if not host:
            # create host
            if (
                vs["cManagementInterface"]
                and not yes_no(vs["cSdiDeleted"])
                # and vs["cManagementInterface"] != "0.0.0.0"
            ):
                # name = f'{vs["visibleId"]} [{vs["id"]}]',
                host_updateset = {
                    "host": vs["id"],
                    "name": vs["visibleId"],
                    "groups": [{"groupid": zabbix_hostgroup_id}],
                    "interfaces": [
                        {
                            "type": 2,
                            "main": 1,
                            "useip": 1,
                            "ip": vs["cManagementInterface"],
                            "dns": "",
                            "port": "161",
                            "details": {"version": 2, "community": "{$SNMP_COMMUNITY}", "bulk": 0},
                        }
                    ],
                    "macros": hostmacros_updateset,
                    "templates": [{"templateid": zabbix_template_id}],
                    "proxy_hostid": str(zabbix_proxy_id),
                }

                try:
                    newhost = zapi.host.create(**host_updateset)
                    newhost_id = newhost["hostids"][0]
                    app_updateset = {"name": f'elid_{vs["elid"]}', "hostid": newhost_id}
                    elid_app = zapi.application.create(**app_updateset)
                except ZabbixAPIException:
                    logger.exception(
                        f'Failed to create Zabbix host {vs["visibleId"]}.\nHost updateset: {host_updateset}'
                    )
                else:
                    logger.info(f'Created Zabbix host {vs["visibleId"]}.')
        else:
            # update/delete host
            host_id = host["hostid"]
            host_macros = {}
            if host["macros"]:
                for macro in host["macros"]:
                    host_macros[macro["macro"]] = macro["value"]

            host_purpose = host_macros.get("{$HOST_PURPOSE}", "")
            host_community = host_macros.get("{$SNMP_COMMUNITY}", "public")
            host_vsphere_host = host_macros.get("{$VSPHERE.HOST}", "")

            host_interface = host["interfaces"][0]
            host_interface_id = host_interface["interfaceid"]
            host_ip = host_interface["ip"]
            host_name = host["name"]
            host_description = host["description"]

            host_triggers = triggers_indexed_by_hostids[host_id]
            host_triggers_by_tag = {
                trigger["tag"]: trigger for trigger in host_triggers if trigger.get("tag")
            }
            host_items = items_indexed_by_hostids[host_id]
            host_items_indexed_by_app = {}
            for item in host_items:
                for app in item["applications"]:
                    if not host_items_indexed_by_app.get(app["name"]):
                        host_items_indexed_by_app[app["name"]] = []
                    host_items_indexed_by_app[app["name"]].append(item)

            if host_name != vs["visibleId"]:
                host_updateset["name"] = vs["visibleId"]

            if vs["cManagementInterface"] and host_ip != vs["cManagementInterface"]:
                hostinterface_updateset = {"interfaceid": host_interface_id, "ip": vs["cManagementInterface"]}

            if (
                (host_community != vs["cCommunityName"])
                or (host_purpose != vs["cSdiPurpose"])
                or (host_vsphere_host != vfzsync.CONFIG["vpoller"]["vc_host"])
            ):
                host_updateset["macros"] = hostmacros_updateset

            host_status = "1"
            hostitems_updateset = []
            hosttriggers_updateset = []
            host_senderset = []

            for vs_flag in FNT_ZABBIX_FLAG_TRIGGERS:
                # enable host if has active checks
                if yes_no(vs[vs_flag]):
                    host_status = "0"
                trigger = host_triggers_by_tag[vs_flag]
                vs_flag_status = int(not yes_no(vs[vs_flag]))
                items = host_items_indexed_by_app[vs_flag]
                for item in items:
                    if vs_flag_status != int(item["status"]):
                        hostitems_updateset.append({"itemid": item["itemid"], "status": vs_flag_status})
                if vs_flag_status != int(trigger["status"]):
                    hosttriggers_updateset.append(
                        {"triggerid": host_triggers_by_tag[vs_flag]["triggerid"], "status": vs_flag_status}
                    )
                    trigger_status = int(yes_no(vs[vs_flag])) - 1
                    metric = ZabbixMetric(host["host"], f"trigger.status[{vs_flag}]", trigger_status)
                    host_senderset.append(metric)

            if host_senderset:
                result = zabbix_send(host_senderset)

            # disable host if no triggers enabled
            if host_status != host["status"]:
                host_updateset["status"] = host_status

            try:
                if hostitems_updateset:
                    logger.debug(f'Zabbix host {vs["visibleId"]} update set: {hostitems_updateset}')
                    zapi.item.update(*hostitems_updateset)

                if hosttriggers_updateset:
                    logger.debug(f'Zabbix host {vs["visibleId"]} update set: {hosttriggers_updateset}')
                    zapi.trigger.update(*hosttriggers_updateset)

                if hostinterface_updateset:
                    logger.debug(f'Zabbix host {vs["visibleId"]} update set: {hostinterface_updateset}')
                    zapi.hostinterface.update(**hostinterface_updateset)

                if host_updateset:
                    host_updateset["hostid"] = host_id
                    logger.debug(f'Zabbix host {vs["visibleId"]} update set: {host_updateset}')
                    result = zapi.host.update(**host_updateset)

            except ZabbixAPIException:
                logger.exception(f'Failed to update Zabbix host {vs["visibleId"]}.')

            if any([hostitems_updateset, hosttriggers_updateset, hostinterface_updateset, host_updateset]):
                logger.info(f'Updated Zabbix host {vs["visibleId"]}.')


def cleanup_zabbix_hosts(zapi, zabbix_hosts, fnt_virtualservers_indexed):
    for host in zabbix_hosts:
        host_id = host["hostid"]
        vs = fnt_virtualservers_indexed.get(host["host"], {})
        # don't delete if no data from FNT
        if fnt_virtualservers_indexed and (yes_no(vs.get("cSdiDeleted", "N")) or not vs):
            try:
                zapi.host.delete(host_id)
            except ZabbixAPIException:
                logger.exception(f'Failed to delete Zabbix host {host["host"]}.')
            else:
                logger.info(f'Deleted Zabbix host {host["host"]}.')


def zabbix_send(senderset):
    sender = ZabbixSender(zabbix_server=vfzsync.CONFIG["zabbix"]["proxy"], zabbix_port=10051)
    result = sender.send(senderset)
    if result.failed > 0:
        logger.debug(f"Send started with args: {senderset} and has failed: {result}")

    return result


class VFZSync:
    def __init__(self, init_mode=["vpoller", "fnt", "zabbix"]):
        super().__init__()

        # Initiate vPoller
        if "vpoller" in init_mode:
            try:
                self._vpoller = vPollerAPI(
                    vpoller_endpoint=vfzsync.CONFIG["vpoller"]["endpoint"],
                    vpoller_retries=vfzsync.CONFIG["vpoller"]["retries"],
                    vpoller_timeout=vfzsync.CONFIG["vpoller"]["timeout"],
                )
                self._vpoller.run(method="about", vc_host=vfzsync.CONFIG["vpoller"]["vc_host"])
            except vPollerException:
                message = "vPoller initialization failed"
                logger.exception(message)
                raise vPollerException(message)

        # Initiate FNT API
        if "fnt" in init_mode:
            try:
                self._command = FNTCommandAPI(
                    url=vfzsync.CONFIG["command"]["url"],
                    username=vfzsync.CONFIG["command"]["username"],
                    password=vfzsync.CONFIG["command"]["password"],
                )
            except FNTNotAuthorized:
                message = "FNT Command authorization failed"
                logger.exception(message)
                raise FNTNotAuthorized(message)

        # Initiate ZabbixAPI
        if "zabbix" in init_mode:
            try:
                self._zapi = ZabbixAPI(
                    url=vfzsync.CONFIG["zabbix"]["url"],
                    user=vfzsync.CONFIG["zabbix"]["username"],
                    password=vfzsync.CONFIG["zabbix"]["password"],
                )
                self._zapi.session.verify = False
                zabbix_hostgroup_name = vfzsync.CONFIG["zabbix"]["hostgroup"]
                zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(self._zapi, zabbix_hostgroup_name)
                if not zabbix_hostgroup_id:
                    zabbix_hostgroup_id = self._zapi.hostgroup.create(name=zabbix_hostgroup_name)
                    logger.info(f"Created Zabbix host group {zabbix_hostgroup_name}.")

            except ZabbixAPIException:
                message = "Zabbix authorization failed"
                logger.exception(message)
                raise ZabbixAPIException(message)

    def run_sync(self, mode, args=None):
        logger.info(f"{mode} sync started.")
        if mode in ["all", "vpoller-fnt"]:
            self.run_vpoller_fnt_sync()
        if mode in ["all", "fnt-zabbix"]:
            self.run_fnt_zabbix_sync()
        logger.info(f"{mode} sync completed.")

    def run_vpoller_fnt_sync(self):
        """ vPoller -> FNT """
        try:
            vpoller_vms, vpoller_vms_indexed = get_vpoller_vms(self._vpoller)
            fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_vs(
                command=self._command,
                index="cUuid",
                related_entities=True,
                restrictions=FNT_VS_FILTER_VPOLLER_FNT,
            )
            if not vpoller_vms:
                logger.warn(f"No VMs received from vpoller/vCenter, aborting sync.")
                return False

            sync_fnt_vs(self._command, vpoller_vms, fnt_virtualservers_indexed)
            cleanup_fnt_vs(self._command, fnt_virtualservers, vpoller_vms_indexed)

        except VFZException as e:
            logger.exception(str(e))

    def run_fnt_zabbix_sync(self):
        """ FNT -> Zabbix """

        fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_vs(
            command=self._command, index="id", related_entities=False, restrictions=FNT_VS_FILTER_FNT_ZABBIX
        )
        if not fnt_virtualservers:
            logger.warn(f"No VirtualServers received from FNT, aborting sync.")
            return False

        zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(
            self._zapi, vfzsync.CONFIG["zabbix"]["hostgroup"]
        )
        zabbix_hosts, zabbix_hosts_indexed_by_host = get_zabbix_hosts(self._zapi, zabbix_hostgroup_id)

        # cleanup
        cleanup_zabbix_hosts(
            self._zapi, zabbix_hosts=zabbix_hosts, fnt_virtualservers_indexed=fnt_virtualservers_indexed
        )

        zabbix_hosts, zabbix_hosts_indexed_by_host = get_zabbix_hosts(self._zapi, zabbix_hostgroup_id)

        sync_zabbix_hosts(
            self._zapi,
            fnt_virtualservers=fnt_virtualservers,
            zabbix_hosts_indexed_by_host=zabbix_hosts_indexed_by_host,
        )

    def get_fnt_vs_stats(self):
        fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_vs(
            command=self._command, index="id", related_entities=False, restrictions=FNT_VS_FILTER_STATS
        )
        stats_new = len(
            [
                vs
                for vs in fnt_virtualservers
                if (yes_no(vs["cSdiNewServer"]) and not yes_no(vs["cSdiDeleted"]))
            ]
        )
        stats_deleted = len(
            [
                vs
                for vs in fnt_virtualservers
                if yes_no(vs["cSdiDeleted"]) and not yes_no(vs["cCSdiDelConfirmed"])
            ]
        )
        stats = {"vs_new": stats_new, "vs_deleted": stats_deleted}
        return stats

    def run_update(self, mode, args):
        logger.info("Update started.")

        update_ips = bool(args.get("cManagementInterface", False))
        percent = int(args.get("percent", 0))

        fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_vs(
            command=self._command,
            index="id",
            related_entities=update_ips,
            restrictions=FNT_VS_FILTER_FNT_UPDATE,
        )
        create_fake_percent = int(args.get("create_fake", 0))
        fnt_virtualservers_monitored = len([vs for vs in fnt_virtualservers if not yes_no(vs["cSdiDeleted"])])
        create_fake = int(fnt_virtualservers_monitored * create_fake_percent / 100)

        # create fake servers
        for i in range(0, create_fake):
            vs_uuid = str(uuid.uuid4())
            vs_attr_updateset = {
                "cUuid": vs_uuid,
                "visibleId": "fake_" + vs_uuid,
                "cCpu": 666,
                "cRam": 666666,
                "cSdiStatus": "poweredOn",
                "datasource": vfzsync.CONFIG["vpoller"]["vc_host"],
                "cManagementInterface": "127.0.0.1",
            }
            for arg in args:
                if re.match(r"^c[A-Z].*$", arg):
                    arg_percent = int(args[arg])
                    vs_attr_updateset[arg] = random.choice(
                        list("N" * (100 - arg_percent) + "Y" * arg_percent)
                    )

            vs_attr_updateset_ = vs_attr_updateset.copy()
            vs = create_update_fnt_vs(command=self._command, vs_attr_updateset=vs_attr_updateset_, vs=None)
            vs_attr_updateset["elid"] = vs["elid"]
            vs = vs_attr_updateset.copy()
            del vs_attr_updateset["elid"]
            return_data = create_update_fnt_vs(
                command=self._command, vs_attr_updateset=vs_attr_updateset, vs=vs
            )

        vs_attr_updateset = {}
        for vs in fnt_virtualservers:
            for arg in args:
                if re.match(r"^c[A-Z].*$", arg):
                    arg_percent = int(args[arg])
                    vs_attr_updateset[arg] = random.choice(
                        list("N" * (100 - arg_percent) + "Y" * arg_percent)
                    )

            if update_ips:
                ips = vs.get("vmIpAddress", {}).keys()
                if ips:
                    ip = list(ips)[0]
                    vs_attr_updateset["cManagementInterface"] = ip
                else:
                    vs_attr_updateset["cManagementInterface"] = "0.0.0.0"

            if vs_attr_updateset and random.randint(1, 100) <= percent:
                create_update_fnt_vs(self._command, vs=vs, vs_attr_updateset=vs_attr_updateset)

        logger.info("Update completed.")

    def run_send(self, mode, args):
        # logger.debug(f"Send started with args: {args}")

        host_senderset = []

        if mode == "trapper":
            metric = ZabbixMetric(args["host"], args["key"], args["status"])
            host_senderset.append(metric)

        if mode == "groupupdate":
            logger.debug(f"Send started in {mode} mode.")

            zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(
                self._zapi, vfzsync.CONFIG["zabbix"]["hostgroup"]
            )
            zabbix_hosts, zabbix_hosts_indexed_by_host = get_zabbix_hosts(self._zapi, zabbix_hostgroup_id)
            zabbix_hostgroups = {}
            hostids_by_flag = {}
            for flag in FNT_ZABBIX_FLAG_TRIGGERS:
                zabbix_hostgroups[flag] = get_zabbix_hostgroupid_by_name(
                    self._zapi, f'{vfzsync.CONFIG["zabbix"]["hostgroup"]}/{flag}'
                )
                hostids_by_flag[flag] = []

            hostids = [
                zabbix_hosts_indexed_by_host[hostname]["hostid"] for hostname in zabbix_hosts_indexed_by_host
            ]
            zabbix_proxy_id = get_zabbix_proxyid_by_name(self._zapi, vfzsync.CONFIG["zabbix"]["proxy"])

            triggers, triggers_indexed_by_hostids = get_zabbix_triggers(
                zapi=self._zapi, mode="groupupdate", groupids=zabbix_hostgroup_id
            )

            for trigger in triggers:
                host = trigger["hosts"][0]["host"]
                hostid = trigger["hosts"][0]["hostid"]
                tag = trigger["tag"]
                status = int(trigger["status"])
                value = int(trigger["value"])
                if value and not status:
                    hostids_by_flag[tag].append(hostid)
                status_send = value if not status else -1
                metric = ZabbixMetric(host, f"trigger.status[{tag}]", status_send)
                host_senderset.append(metric)

            for flag in FNT_ZABBIX_FLAG_TRIGGERS:
                self._zapi.hostgroup.massupdate(
                    groups=[{"groupid": zabbix_hostgroups[flag]}], hosts=hostids_by_flag[flag]
                )

        zabbix_send(host_senderset)

        if mode == "groupupdate":
            logger.debug(f"Send completed in {mode} mode.")

    def run_report(self, mode=None, args=None):
        from .prob_report import create_report
        logger.info("Report started.")
        # cleanup folder
        try:
            files = glob.glob('reports/*')
            for f in files:
                os.remove(f)
        except Exception as e:
            logger.warn(f'Failed to delete {f}. Reason: {e}')
        report = create_report(self._zapi, self._command, mode=mode, args=args)
        logger.info("Report completed.")
        return report


logger = init_logger()
logger.debug(f"{__name__} init done.")
init_tracing()
