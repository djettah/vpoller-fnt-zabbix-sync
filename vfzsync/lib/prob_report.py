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
REPORT_TEMPLATE = 'problem_report.html'

def retrieve_data(zapi, mode="problemsactive"):
    """ Function to retrieve Problem data from Zabbix API """

    # Generate Today's date (MM/DD/YYYY) into Unix time (##########)
    todays_date = int(time.mktime(datetime.date.today().timetuple()))

    if mode == "problemsactive":
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


def zbx_problems_by_severity(args):
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
    title = "Проблемы по важности"
    layout = go.Layout(
        title=dict(
            # text=title, 
            font=dict(size=18), xanchor="left", x=0),
        width=350,
        height=450,
        margin=dict(l=30, r=30, t=10, b=50),
    )
    # layout = go.Layout(title=dict(text="Problems by Severity:", font=dict(size=18), xanchor="left", x = 0))

    fig = go.Figure(data=[trace], layout=layout)

    # plotly.offline.plot(fig, filename="problems_by_severity.html")
    plotly.io.write_image(fig, file=f"reports/problems_by_severity.png", format='png', scale=2)
    return plotly.offline.plot(fig, output_type="div", include_plotlyjs=False), title


def zbx_problems_time_and_frequency(args):
    """ Generate Line chart showing total problems throughout the day """
    dataframe = pd.DataFrame(args["clock"])
    dataframe["clock"] = pd.to_datetime(dataframe["clock"]).dt.strftime("%H:%M")
    dataframe = dataframe["clock"].value_counts().sort_index()

    data = go.Scatter(x=dataframe.keys().tolist(), y=dataframe.tolist(), mode="lines", connectgaps=True,)
    title = "Проблемы по времени суток"
    # layout = go.Layout(title=dict(text="Time of Frequency:", font=dict(size=18), xanchor="left", x = 0)) #fix
    layout = go.Layout(
        title=dict(text=title, font=dict(size=18), xanchor="left", x=0),
        width=500,
        height=400,
    )

    fig = go.Figure(data=[data], layout=layout)

    # plotly.offline.plot(fig, filename='time_and_frequency.html')
    plotly.io.write_image(fig, file=f"reports/frequency_line.png", format='png', scale=2)
    return plotly.offline.plot(fig, include_plotlyjs=False, output_type="div"), title


def zbx_problems_per_day(args, mode):
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
        title=dict(
            # text=title, 
            font=dict(size=18), xanchor="left", x=0),
        width=800,
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="gainsboro",
        margin=dict(l=30, r=30, t=0, b=5),
    )
    # plot_bgcolor='rgba(0,0,0,0)'

    fig = go.Figure(data=data, layout=layout)

    # plotly.offline.plot(fig, filename='problems_per_day.html')
    plotly.io.write_image(fig, file="reports/per_day_bar.png", format='png', scale=2, width=1000)
    return plotly.offline.plot(fig, include_plotlyjs=False, output_type="div"), title


def zbx_problems_table(args, mode):
    """ Generate Visual table for report """

    if mode != "problemsactive":
        dataframe = pd.DataFrame(
            # args[["eventid", "clock", "rts_clock", "severity", "hosts", "name"]] #fix
            args[["eventid", "clock", "severity", "hosts", "name"]]
        )
        title = "Закрытые за неделю проблемы"
    else:
        dataframe = args
        title ="Активные проблемы"

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
        # name="Отчёт о проблемах",
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
        title=dict(
            # text=title, 
            font=dict(size=18), xanchor="left", x=0), margin=dict(l=30, r=30, t=0, b=20),
        height= 200 + 20 * n,
        # width = 1000
        #, autosize=True
    )

    fig = go.Figure(data=[trace], layout=layout)

    # plotly.offline.plot(data, filename="generate_table.html")
    plotly.io.write_image(fig, file="reports/generated_table.png", format='png', scale=2, width=1000)
    return plotly.offline.plot(fig, output_type="div", include_plotlyjs=False), title


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
    title = "Статистика"
    trace = go.Table(
        # name=title,
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
        # title=dict(text="Статистика", font=dict(size=18), xanchor="left", x=0, yanchor="top"),
        width=350,
        height=242,
        margin=dict(l=30, r=30, t=0, b=50),
    )

    fig = go.Figure(data=[trace], layout=layout)
    fig.layout["template"]["data"]["table"][0]["header"]["fill"]["color"] = "rgba(0,0,0,0)"

    # plotly.offline.plot(fig, filename="generate_fnt_zabbix_stats.html")
    plotly.io.write_image(fig, file="reports/fnt_zabbix_stats.png", format='png', scale=2)
    return plotly.offline.plot(fig, output_type="div", include_plotlyjs=False), title


def fnt_zabbix_servers_table(zapi, command, args):

    """ Generate Visual table for report """
    if args == "new":
        fnt_virtualservers_new, fnt_virtualservers_new_indexed = get_fnt_vs(
            command=command, index="id", related_entities=False, restrictions=FNT_VS_FILTER_FNT_NEW_SERVERS
        )
        # report_vars = {}
        servers = [vs["visibleId"] for vs in fnt_virtualservers_new]
        # report_vars['new_servers'] = ', '.join(servers)
        # report_vars['new_servers_count'] = len(servers)
        title =  "Новые серверы" if len(servers) else "Новые серверы отсутствуют"
    elif args == "deleted":
        fnt_virtualservers_deleted, fnt_virtualservers_deleted_indexed = get_fnt_vs(
            command=command,
            index="id",
            related_entities=False,
            restrictions=FNT_VS_FILTER_FNT_DELETED_UNCONFIRMED_SERVERS,
        )
        servers = [vs["visibleId"] for vs in fnt_virtualservers_deleted]
        # report_vars['deleted_servers'] = ', '.join(servers)
        # report_vars['deleted_servers_count'] = len(servers)
        title =  "Удалённые серверы" if len(servers) else "Удалённые серверы отсутствуют"
    elif args == "problems":
        servers = []
        title = "Проблемы отсутствуют"

    # servers = [f"<tr><td>Server {n}</td></tr>" for n in range(20)]
    # servers = [f"<tr><td>{server}</td></tr>" for server in servers]
    # text = title + '<p>' + "<p>".join(servers)
    text = f"<table>{''.join(servers)}</table>"

    # return text
    # servers=[]
    trace = go.Table(
        #name="Статистика серверов СДИ Базис",
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
        title=dict(
            #text=title, 
            font=dict(size=18), xanchor="left", x=0, yanchor="top"),
        # height=70,
        # height=242,
        height= 130 + 20 * len(servers),
        width=350,
        margin=dict(l=30, r=30, t=0, b=50),
        # autosize=True
    )

    fig = go.Figure(data=[trace], layout=layout)
    fig.layout["template"]["data"]["table"][0]["header"]["fill"]["color"] = "rgba(0,0,0,0)"

    # plotly.offline.plot(fig, filename="generate_fnt_zabbix_stats_servers.html")
    plotly.io.write_image(fig, file=f"reports/fnt_zabbix_stats_servers_{args}.png", format='png', scale=2)
    return plotly.offline.plot(fig, output_type="div", include_plotlyjs=False), title # + text


def generate_report(zapi, command, dataframe, mode, noproblemsdata=False, filename=None, args=None):

    """ Generate report to be emailed out """
    env = Environment(loader=PackageLoader("vfzsync", "templates"))
    comprise_template = env.get_template(REPORT_TEMPLATE)

    title = 'Отчёт о мониторинге серверов'
    stat1, header1 = fnt_zabbix_stats(zapi, command, dataframe)
    stat2, header2 = fnt_zabbix_servers_table(zapi, command, "new")
    stat3, header3 = fnt_zabbix_servers_table(zapi, command, "deleted")

    data = {
            "title": title,
            "fnt_zabbix_stats": stat1,
            "fnt_zabbix_stats_header": header1,
            "fnt_zabbix_stats_new": stat2,
            "fnt_zabbix_stats_new_header": header2,
            "fnt_zabbix_stats_deleted": stat3,
            "fnt_zabbix_stats_deleted_header": header3,
        }
    if not noproblemsdata:
        stat4, header4 = zbx_problems_by_severity(dataframe)
        stat5, header5 = zbx_problems_per_day(dataframe, mode)
        stat6, header6 = zbx_problems_table(dataframe, mode)
        data = {
            **data,
            "percentage_pie": stat4,
            "percentage_pie_header": header4,
            # "frequency_line": time_and_frequency(dataframe),
            "per_day_bar": stat5,
            "per_day_bar_header": header5,
            "generated_table": stat6,
            "generated_table_header": header6,

        }
    else:
        stat7, header7 =  fnt_zabbix_servers_table(zapi, command, "problems")
        data = {**data,
            "generated_table": stat7,
            "generated_table_header": header7,
            }

    if filename:
        compiled_report = comprise_template.render(page=data)
        with open(f"reports/{filename}", "w") as file:
            file.write(compiled_report)
        
    if args == 'email':
        data = {
            "title": title,
            "fnt_zabbix_stats":         '<img src="cid:fnt_zabbix_stats.png"/>',
            "fnt_zabbix_stats_new":     '<img src="cid:fnt_zabbix_stats_servers_new.png"/>',
            "fnt_zabbix_stats_deleted": '<img src="cid:fnt_zabbix_stats_servers_deleted.png"/>',
            "fnt_zabbix_stats_header": header1,
            "fnt_zabbix_stats_new_header": header2,
            "fnt_zabbix_stats_deleted_header": header3,

        }
        if not noproblemsdata:
            data = {
                **data,
                "percentage_pie":   '<img src="cid:problems_by_severity.png"/>',
                # "frequency_line":   '<img src="cid:frequency_line.png"/>',
                "per_day_bar":      '<img src="cid:per_day_bar.png"/>',
                "generated_table":  '<img src="cid:generated_table.png"/>',
                "percentage_pie_header": header4,
                "per_day_bar_header": header5,
                "generated_table_header": header6,

            }
        else:
            data = {**data,
                "generated_table": '<img src="cid:fnt_zabbix_stats_servers_problems.png"/>',
                "generated_table_header": header7,
            }

    compiled_report = comprise_template.render(page=data)

    return compiled_report


def create_report(zapi, command, mode, args=None):
    """ Applicaton Logic """
    data = retrieve_data(zapi=zapi, mode=mode)
    if not data.empty:
        dataframe = clean_data(data, mode)
        report = generate_report(zapi, command, dataframe, mode, noproblemsdata=False, filename='problems_report.html', args=args)
    else:
        report = generate_report(zapi, command, data, mode, noproblemsdata=True, filename='problems_report.html', args=args)
    return report


if __name__ == "__main__":
    create_report()
