"""Netconf Bulk Operations

This script is reading or writing data from/to multiple network devices using NETCONF.
"""

import click
import os
import logging
from ncclient import manager
from lxml import etree
import concurrent.futures
from jinja2 import Environment, FileSystemLoader
from datetime import datetime


logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


def render_jinja(template, **kwargs):
    """
    Dynamically renders and returns a jinja template.
    """
    env = Environment(
        lstrip_blocks=True,
        trim_blocks=True,
        loader=FileSystemLoader("templates"),
    )
    templ = env.get_template(template)
    return templ.render(**kwargs)


def pretty_print_xml(xml):
    """
    Pretty formats and returns an XML string
    """
    return etree.tostring(xml, pretty_print=True).decode()


def string_to_file(string, file):
    """
    Saves a string to a file
    """
    with open(file, "w") as fo:
        fo.write(string)


def get_and_save(device, filter_mode, filter_):
    """
    Connects to a device using NETCONF, uses get with a subtree filter and stores the result
    to a file.
    """
    try:
        manager.HUGE_TREE_DEFAULT = True
        with manager.connect(
            host=device,
            port=830,
            username=username,
            password=password,
            hostkey_verify=False,
        ) as m:
            res = m.get(filter=(filter_mode, filter_))
            if res.ok:
                string_to_file(
                    pretty_print_xml(res.data), f"output/out_read_{device}.xml"
                )
                return True
            else:
                raise Exception(f"Unable to proceed NETCONF ops on {device}")
    except Exception as e:
        logger.error(f"Unable to complete get operation on {device}: {e}")
    return False


def edit_config(device, cfg):
    """
    Connects to a device using NETCONF and performs edit-config to the running datastore using the provided configuration.
    """
    result = {"device": device, "ok": False}
    try:
        with manager.connect(
            host=device,
            port=830,
            username=username,
            password=password,
            hostkey_verify=False,
        ) as m:
            res = m.edit_config(target="running", config=cfg)
            if res.ok:
                result["ok"] = True
    except Exception as e:
        logger.error(f"Unable to complete edit-config operation on {device}: {e}")
    return result


@click.group()
def cli():
    pass


@cli.command("read", short_help="NETCONF 'get' bulk job (subtree filter)")
@click.argument("filter", type=click.File("r"), default="bulk_filter.xml")
@click.argument("devices", type=click.File("r"), default="devices.txt")
def nc_get(filter, devices):
    """
    Retrive configuration and state information from all devices in the
    DEVICES file according the subtree filter in the FILTER file.
    """
    filter_ = filter.read()
    devs = devices.readlines()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        [executor.submit(get_and_save, dev.strip(), "subtree", filter_) for dev in devs]


@cli.command("xpath", short_help="NETCONF 'get' bulk job (xpath filter)")
@click.argument("xpath")
@click.argument("devices", type=click.File("r"), default="devices.txt")
def nc_get(xpath, devices):
    """
    Retrive configuration and state information from all devices in the
    DEVICES file according the XPATH filter.
    """
    devs = devices.readlines()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        [executor.submit(get_and_save, dev.strip(), "xpath", xpath) for dev in devs]


@cli.command("write", short_help="NETCONF 'edit-config' bulk job")
@click.argument("config", type=click.File("r"), default="bulk_config.xml")
@click.argument("devices", type=click.File("r"), default="devices.txt")
def nc_edit_config(config, devices):
    """
    Loads the configuration specified in the CONFIG file to the running datastore
    of all devices in the DEVICES file.
    """
    cfg = etree.parse(config)
    root = cfg.getroot()
    root_tag = "{urn:ietf:params:xml:ns:netconf:base:1.0}config"
    if root.tag != root_tag:
        root.tag = root_tag

    devs = devices.readlines()
    now = datetime.now()
    date_time = now.strftime("%d/%m/%Y %H:%M:%S")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = [executor.submit(edit_config, dev.strip(), root) for dev in devs]
        report_results = [f.result() for f in concurrent.futures.as_completed(results)]
        report_results = sorted(report_results, key=lambda x: x["device"])
        report = render_jinja(
            template="config_report.j2",
            config=etree.tostring(root, pretty_print=True).decode(),
            date_time=date_time,
            results=report_results,
        )
        string_to_file(report, f"output/config_report.html")


if __name__ == "__main__":
    username = os.getenv("NCBO_USER", False)
    password = os.getenv("NCBO_PASSWORD", False)

    if not username or not password:
        logger.error(
            "username and/or password not set. Make sure to set the NCBO_USER and NCBO_PASSWORD environment variables."
        )
        exit(1)

    outputdir = "output"
    if not os.path.exists(outputdir):
        os.makedirs(outputdir)

    cli()
