#!/usr/bin/env python

"""
    Script to generate Problem Report Email
    Though the function to email isn't included it's not hard to create one
"""

import datetime
import time

import pandas as pd
import plotly
import plotly.graph_objs as go

from jinja2 import Environment, PackageLoader
from .vfzlib import (
    get_fnt_vs,
    FNT_VS_FILTER_FNT_NEW_SERVERS,
    FNT_VS_FILTER_FNT_DELETED_UNCONFIRMED_SERVERS,
    FNT_ZABBIX_FLAG_TRIGGERS
)

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


SEVERITY_COLOR_MAP = {
    "Not Classified": "#97AAB3",
    "Information": "#7499FF",
    "Warning": "#FFC859",
    "Average": "#FFA059",
    "High": "#E97659",
    "Disaster": "#E45959",
}

SEVERITY_LEVEL_MAP = {
    "0": "Not Classified",
    "1": "Information",
    "2": "Warning",
    "3": "Average",
    "4": "High",
    "5": "Disaster",
}


def retrieve_data(zapi, mode="problemsactive"):
    """ Function to retrieve Problem data from Zabbix API """

    # Generate Today's date (MM/DD/YYYY) into Unix time (##########)
    todays_date = int(time.mktime(datetime.date.today().timetuple()))

    if mode == "problemsactive":
        # problems = zapi.problem.get(source=0, recent=False, output="extend")
        # eventids = set([int(p["eventid"]) for p in problems])
        # events = zapi.event.get(
        #     source=0,
        #     selectHosts=["name", "status"],
        #     output="extend",
        #     eventids=list(eventids),
        #     sortfield=["clock", "eventid"],
        #     sortorder="DESC",
        # )
        # events = [event for event in events if event['hosts'][0]['status'] == '0'] #todo
        # objectids = [(p["objectid"]) for p in problems]

        triggers = zapi.trigger.get(
            skipDependent=1,
            filter={"value": 1, "status": 0},
            selectHosts=["name"],
            output=["description", "priority"],
            selectLastEvent=["clock", "severity"],
            monitored=True,
        )

        for trigger in triggers:
            trigger["name"] = trigger["description"]
            trigger["clock"] = trigger["lastEvent"]["clock"]
            trigger["severity"] = trigger["lastEvent"]["severity"]

        events = triggers

    else:
        events = zapi.event.get(
            time_from=todays_date - 604800,
            time_till=todays_date,
            selectHosts=["name"],
            output="extend",
            sortfield=["clock", "eventid"],
            sortorder="ASC",
        )

    return pd.DataFrame(events)


def clean_data(args, mode="problemsactive"):
    """ Function to clean the data within the dataframe """
    dataframe = pd.DataFrame(args)

    if mode == "problemsactive":
        dataframe = dataframe.sort_values(["severity", "clock"], ascending=[0, 0])

    # Drop unnecessary columns from the dataframe
    if mode == "problemsactive":
        # dropped_frame = dataframe.drop(
        #     ["acknowledged", "correlationid", "ns", "object", "objectid", "source", "suppressed", "userid"],
        #     axis=1,
        # )
        dropped_frame = dataframe
    else:
        dropped_frame = dataframe.drop(
            [
                "acknowledged",
                "c_eventid",
                "correlationid",
                "ns",
                "object",
                "objectid",
                "source",
                "suppressed",
                "userid",
                "value",
            ],
            axis=1,
        )

    # Move resolved problems to a new column associated with original problem
    def create_resolution_time_dataframe(args):
        resolution_time = args[["r_eventid"]].copy()
        resolution_time["eventid"] = resolution_time["r_eventid"]
        resolution_time.drop("r_eventid", axis=1, inplace=True)
        event_time = args[["eventid", "clock"]].copy()
        merged_frame = resolution_time.merge(event_time, on="eventid")
        return merged_frame

    def restructure_dataframe():
        merged_frame = create_resolution_time_dataframe(dropped_frame)
        merged_frame["r_eventid"] = merged_frame["eventid"]
        merged_frame["r_clock"] = merged_frame["clock"]
        merged_frame.drop(["eventid", "clock"], axis=1, inplace=True)
        return merged_frame

    if mode != "problemsactive":
        adjusted_frame = dropped_frame.merge(restructure_dataframe(), on="r_eventid")

    # Create new column with Resolved Time in seconds rts_clock
    def create_resolved_time(args):
        dataframe = pd.DataFrame(args)
        dataframe["clock"] = pd.Series(dataframe["clock"]).astype(int)
        dataframe["r_clock"] = pd.Series(dataframe["r_clock"]).astype(int)
        dataframe = dataframe.assign(rts_clock=lambda x: x.r_clock - x.clock)
        return dataframe

    if mode != "problemsactive":
        resolved_frame = create_resolved_time(adjusted_frame)
    else:
        resolved_frame = dropped_frame

    # Drop the empty 'Hosts' and 'r_eventid' rows, reformat dataframe
    def host_series_adjustment(args, mode="problemsactive"):
        dataframe = pd.DataFrame(args)
        host_frame = pd.DataFrame(dataframe["hosts"])
        # host_frame["hosts"] = pd.Series(host_frame["hosts"]).astype(str).str.upper() #fix
        host_frame["hosts"] = pd.Series(host_frame["hosts"]).astype(str)
        host_frame["hosts"] = host_frame["hosts"].str.strip("[]").str.strip("{}")
        host_frame = host_frame["hosts"].str.split(" ", n=3, expand=True)
        host_frame[3] = host_frame[3].str.strip("''")
        dataframe["hosts"] = host_frame[3]
        # dataframe = dataframe.dropna().drop(["r_eventid", "r_clock"], axis=1).reset_index(drop=True) #fix
        return dataframe

    adjusted_dataframe = host_series_adjustment(resolved_frame)

    # Correct column datatypes
    def correct_datatypes(args):
        from datetime import datetime
        import time

        dataframe = pd.DataFrame(args)
        # dataframe["clock"] = pd.to_datetime(dataframe["clock"], unit="s").dt.strftime("%m/%d/%Y %H:%M:%S") #fix
        dataframe["clock"] = pd.to_datetime(dataframe["clock"], unit="s", utc=True)
        dataframe["clock"] = dataframe.apply(lambda x: x["clock"].tz_convert("Europe/Moscow"), axis=1)
        dataframe["clock"] = pd.to_datetime(dataframe["clock"]).dt.strftime("%Y-%m-%d %H:%M:%S")

        dataframe["severity"] = pd.Series(dataframe["severity"]).map(SEVERITY_LEVEL_MAP)
        if mode != "problemsactive":
            dataframe["eventid"] = pd.Series(dataframe["eventid"]).astype(int)
            dataframe["rts_clock"] = pd.to_datetime(dataframe["rts_clock"], unit="s").dt.strftime("%H:%M:%S")

        return dataframe

    cleaned_data = correct_datatypes(adjusted_dataframe)

    return cleaned_data


def problems_by_severity(args):
    """ Generate a Pie Chart representing percentage of all problems """
    dataframe = pd.DataFrame(args["severity"])
    dataframe["colors"] = dataframe["severity"].copy()

    # Map color associations
    dataframe["colors"] = pd.Series(dataframe["colors"]).map(SEVERITY_COLOR_MAP)

    labels = list(dataframe["severity"].value_counts().keys().tolist())
    values = list(dataframe["severity"].value_counts().tolist())
    colors = list(dataframe["colors"].value_counts().keys().tolist())
    colors = [SEVERITY_COLOR_MAP[severity] for severity in labels]

    trace = go.Pie(
        labels=labels,
        values=values,
        showlegend=False,
        hoverinfo="label+value",
        textinfo="label",
        # textinfo="label+percent",
        textfont=dict(size=12),
        hole=0.2,
        marker=dict(colors=colors, line=dict(color="rosybrown", width=1)),
    )

    layout = go.Layout(
        title=dict(text="Проблемы по важности", font=dict(size=18), xanchor="left", x=0),
        width=350,
        height=450,
        margin=dict(l=30, r=30, t=50, b=50),
    )
    # layout = go.Layout(title=dict(text="Problems by Severity:", font=dict(size=18), xanchor="left", x = 0))

    fig = go.Figure(data=[trace], layout=layout)

    # plotly.offline.plot(fig, filename="problems_by_severity.html")
    return plotly.offline.plot(fig, output_type="div", include_plotlyjs=False)


def time_and_frequency(args):
    """ Generate Line chart showing total problems throughout the day """
    dataframe = pd.DataFrame(args["clock"])
    dataframe["clock"] = pd.to_datetime(dataframe["clock"]).dt.strftime("%H:%M")
    dataframe = dataframe["clock"].value_counts().sort_index()

    data = go.Scatter(x=dataframe.keys().tolist(), y=dataframe.tolist(), mode="lines", connectgaps=True,)

    # layout = go.Layout(title=dict(text="Time of Frequency:", font=dict(size=18), xanchor="left", x = 0)) #fix
    layout = go.Layout(
        title=dict(text="Проблемы по времени суток", font=dict(size=18), xanchor="left", x=0),
        width=500,
        height=400,
    )

    fig = go.Figure(data=[data], layout=layout)

    # plotly.offline.plot(fig, filename='time_and_frequency.html')
    return plotly.offline.plot(fig, include_plotlyjs=False, output_type="div")


def problems_per_day(args, mode):
    """ Generate Bar Graph representing issues per day """
    dataframe = pd.DataFrame(args["clock"])
    series_data = pd.to_datetime(dataframe["clock"]).dt.normalize()
    series_data = series_data.value_counts().sort_index()

    dates = series_data.keys().tolist()
    counts = series_data.tolist()

    data = [
        go.Bar(
            x=dates,
            y=counts,
            marker=dict(color="red", line=dict(color="rosybrown", width=1)),
            name="Проблемы",
        )
    ]
    # layout = go.Layout(title="Problems per Day") #fix
    if mode == "problemsactive":
        title = "Хронология активных проблем"
    else:
        title = "Хронология закрытых за неделю проблем"

    layout = go.Layout(
        title=dict(text=title, font=dict(size=18), xanchor="left", x=0),
        width=800,
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="gainsboro",
        margin=dict(l=30, r=30, t=50, b=5),
    )
    # plot_bgcolor='rgba(0,0,0,0)'

    fig = go.Figure(data=data, layout=layout)

    # plotly.offline.plot(fig, filename='problems_per_day.html')
    return plotly.offline.plot(fig, include_plotlyjs=False, output_type="div")


def generate_table(args, mode):
    """ Generate Visual table for report """

    if mode != "problemsactive":
        dataframe = pd.DataFrame(
            # args[["eventid", "clock", "rts_clock", "severity", "hosts", "name"]] #fix
            args[["eventid", "clock", "severity", "hosts", "name"]]
        )
    else:
        dataframe = args

    dataframe["color"] = dataframe["severity"].map(SEVERITY_COLOR_MAP)

    cols_to_show = ["clock", "severity", "hosts", "name"]
    fill_color = []
    n = len(dataframe)
    for col in cols_to_show:
        if col != "severity":
            fill_color.append(["white"] * n)
        else:
            fill_color.append(dataframe["color"].to_list())

    trace = go.Table(
        name="Отчёт о проблемах",
        # columnwidth=[6, 11, 9, 8, 26, 40], #fix
        columnwidth=[13, 7, 18, 40],
        header=dict(
            # values=["Event ID", "Timestamp", "Resolution Time", "Severity", "Host", "Event",], #fix
            values=["Время", "Важность", "Узел", "Проблема"],
            line=dict(width=2, color="pink"),
            fill=dict(color="rgb(255, 113, 113)"),
            align=["center"],
            font=dict(size=14, color="white"),
        ),
        cells=dict(
            # values=[
            #     # dataframe.eventid, #fix
            #     dataframe.clock,
            #     # dataframe.rts_clock, #fix
            #     dataframe.severity,
            #     dataframe.hosts,
            #     dataframe.name,
            # ],
            values=dataframe[cols_to_show].values.T,
            fill_color=fill_color,
            # fill=dict(color="white"),
            align=["left"] * 5,
            line=dict(width=1, color="pink"),
        ),
    )
    if mode == "problemsactive":
        title = "Список активных проблем"
    else:
        title = "Список закрытых за неделю проблем"
    layout = go.Layout(
        title=dict(text=title, font=dict(size=18), xanchor="left", x=0), margin=dict(l=30, r=30, t=30, b=20)
    )

    fig = go.Figure(data=[trace], layout=layout)

    # plotly.offline.plot(data, filename="generate_table.html")
    return plotly.offline.plot(fig, output_type="div", include_plotlyjs=False)


def fnt_zabbix_stats(zapi, command, args):
    """ Generate Visual table for report """

    fnt_virtualservers_new, fnt_virtualservers_new_indexed = get_fnt_vs(
        command=command, index="id", related_entities=False, restrictions=FNT_VS_FILTER_FNT_NEW_SERVERS,
    )
    fnt_virtualservers_deleted, fnt_virtualservers_deleted_indexed = get_fnt_vs(
        command=command,
        index="id",
        related_entities=False,
        restrictions=FNT_VS_FILTER_FNT_DELETED_UNCONFIRMED_SERVERS,
    )

    stats = {}
    for tag in FNT_ZABBIX_FLAG_TRIGGERS:
        stats[tag] = zapi.trigger.get(tags=[{"tag": "FNT_Flag", "value": tag, 'operator': 1}], filter={"value": 1, "status": 0}, monitored=True, countOutput=True, skipDependent=True)
    
    dataframe = pd.DataFrame(
        [
            ["Новые серверы", len(fnt_virtualservers_new)],
            ["Удаленные серверы", len(fnt_virtualservers_deleted)],
            ["Старый бэкап", stats["cSdiBackupNeeded"]],
            ["Недопустимо выключено", stats["cSdiNoShutdown"]],
            ["Не доступно по ICMP", stats["cSdiMonitoring"]],
            ["Не доступно по SNMP", stats["cSdiMonitoringSnmp"]],
        ],
        columns=["category", "value"],
    )

    trace = go.Table(
        name="Статистика",
        columnwidth=[11, 3],
        header=dict(
            values=[""],
            line=dict(width=1),
            fill=dict(color="rosybrown"),
            # fill=dict(color="rgb(255, 113, 113)"),
            align=["center"],
            font=dict(size=14, color="white"),
            height=10,
        ),
        cells=dict(
            values=[dataframe.category, dataframe.value],
            fill=dict(color="white"),
            align=["left"] * 2,
            line=dict(width=1, color="pink"),
        ),
    )

    layout = go.Layout(
        title=dict(text="Статистика", font=dict(size=18), xanchor="left", x=0, yanchor="top"),
        width=350,
        height=242,
        margin=dict(l=30, r=30, t=60, b=50),
    )

    fig = go.Figure(data=[trace], layout=layout)
    fig.layout["template"]["data"]["table"][0]["header"]["fill"]["color"] = "rgba(0,0,0,0)"

    # plotly.offline.plot(data, filename="generate_table.html")
    return plotly.offline.plot(fig, output_type="div", include_plotlyjs=False)


def fnt_zabbix_stats_servers(zapi, command, args):

    """ Generate Visual table for report """
    if args == "new":
        fnt_virtualservers_new, fnt_virtualservers_new_indexed = get_fnt_vs(
            command=command, index="id", related_entities=False, restrictions=FNT_VS_FILTER_FNT_NEW_SERVERS
        )
        # report_vars = {}
        servers = [vs["visibleId"] for vs in fnt_virtualservers_new]
        # report_vars['new_servers'] = ', '.join(servers)
        # report_vars['new_servers_count'] = len(servers)

        title = "Новые узлы"
    else:
        fnt_virtualservers_deleted, fnt_virtualservers_deleted_indexed = get_fnt_vs(
            command=command,
            index="id",
            related_entities=False,
            restrictions=FNT_VS_FILTER_FNT_DELETED_UNCONFIRMED_SERVERS,
        )
        servers = [vs["visibleId"] for vs in fnt_virtualservers_deleted]
        # report_vars['deleted_servers'] = ', '.join(servers)
        # report_vars['deleted_servers_count'] = len(servers)

        title = "Удалённые узлы"

    trace = go.Table(
        name="Статистика узлов СДИ Базис",
        columnwidth=[11],
        header=dict(
            values=[""],
            line=dict(width=1),
            fill=dict(color="rosybrown"),
            # fill=dict(color="#C2D4FF"),
            # fill=dict(color="rgb(255, 113, 113)"),
            align=["center"],
            font=dict(size=14, color="white"),
            height=10,
        ),
        cells=dict(
            values=[servers,], fill=dict(color="white"), align=["left"] * 2, line=dict(width=1, color="pink"),
        ),
    )

    layout = go.Layout(
        title=dict(text=title, font=dict(size=18), xanchor="left", x=0, yanchor="top"),
        height=242,
        width=350,
        margin=dict(l=30, r=30, t=60, b=50),
    )

    fig = go.Figure(data=[trace], layout=layout)
    fig.layout["template"]["data"]["table"][0]["header"]["fill"]["color"] = "rgba(0,0,0,0)"

    # plotly.offline.plot(data, filename="generate_table.html")
    return plotly.offline.plot(fig, output_type="div", include_plotlyjs=False)


def generate_report(zapi, command, args, mode, filename=None):

    """ Generate report to be emailed out """
    env = Environment(loader=PackageLoader("vfzsync", "templates"))
    comprise_template = env.get_template("problem_report.html")

    if mode == "problemsactive":
        title = "Отчёт об активных проблемах"
    else:
        title = "Отчёт о закрытых за 7д. проблемах"

    data = {
        "fnt_zabbix_stats": fnt_zabbix_stats(zapi, command, args),
        "fnt_zabbix_stats_new": fnt_zabbix_stats_servers(zapi, command, "new"),
        "fnt_zabbix_stats_deleted": fnt_zabbix_stats_servers(zapi, command, "deleted"),
        "percentage_pie": problems_by_severity(args),
        "frequency_line": time_and_frequency(args),
        "per_day_bar": problems_per_day(args, mode),
        "generated_table": generate_table(args, mode),
        "title": title,
    }

    compiled_report = comprise_template.render(page=data)

    if filename:
        with open(filename, "w") as file:
            file.write(compiled_report)

    return compiled_report


def create_report(zapi, command, mode):
    """ Applicaton Logic """
    data = retrieve_data(zapi=zapi, mode=mode)
    if not data.empty:
        dataframe = clean_data(data, mode)
        report = generate_report(zapi, command, dataframe, mode)
    else:
        report = 'No problems found'
    return report


if __name__ == "__main__":
    create_report()
