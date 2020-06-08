import threading
import time

import vfzsync
from vfzsync import app

from debugtoolkit.debugtoolkit import (
    crash_me,
    debug_exception,
    deflogger,
    deflogger_module,
    dry_request,
    handle_exception,
    init_logger,
    killer_loop,
    measure,
)
from vfzsync.lib.vfzlib import VFZSync

#todo #dev #test
from flask_mail import Message
from flask_mail import Mail

class AsyncTask(threading.Thread):
    def __init__(self, task_id, proc, params=None):
        super().__init__()
        self.task_id = task_id
        self.params = params
        self.proc = proc

    def run(self):
        ## Do processing
        ## store the result in table for id = self.task_id
        self.proc(*self.params)


def get_sync_stats():

    result = {}

    try:
        sync = VFZSync(init_mode="fnt")
        result = sync.get_fnt_vs_stats()

    except Exception as e:
        logger.exception(f"Stats failed.")
        result["message"] = "Stats failed."
        result["exception"] = str(e)
        result["success"] = False

    return result


def get_sync_status():
    return state


def run_action(resource, verb, mode, async_run, args=None):
    if (verb == 'run' or verb =='send') and state[resource][mode]["status"] == "running":
        result = {"success": False, "message": "running"}
        return result

    if async_run is not None:
        # f"{action.capitalize()} started."
        result = {"success": True, "message": "running"}
        async_task = AsyncTask(task_id=1, proc=run_action_do, params=(resource, verb, mode, args))
        async_task.start()
    else:
        result = run_action_do(resource, verb, mode, args)

    return result


def send_email(subject, sender, recipients, text_body, html_body, attachment=None):
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    # msg.html = html_body

    # with app.open_resource("/tmp/problem_report.html") as fp:
        # msg.attach("problem_report.html", "text/html", fp.read())
    # try:
    msg.attach("problem_report.html", "text/html", attachment)
    mail.send(msg)
    return True
    # except Exception as e:
    #     return e.with_traceback


def run_action_do(resource, verb, mode, args=None):

    if resource == "sync":
        if verb == 'stats': 
            return get_sync_stats()
        if verb == 'status': 
            return get_sync_status()
        init_mode = mode.split("-")
    if resource == "update":
        init_mode = "fnt"
    if resource == "report":
        init_mode = ["fnt", "zabbix"]
    if resource == "send":
        init_mode = "zabbix"
    if resource == "test":
        # init_mode = "test"
        # time.sleep(60)
        state[resource][mode]["status"] = "completed"
        return {'success': True, 'message': "Тест ок"}
        return 'ok'

    result = {}

    # report/run is stateless; trapper is non-blocking
    if (verb == 'run' and resource != 'report') or verb == 'send':
        state[resource][mode]["status"] = "running"
        state[resource][mode]["date"] = int(time.time())
    if resource == "send" and mode == "trapper":
        state[resource][mode]["status"] = "running (non-blocking)"


    try:
        sync = VFZSync(init_mode=init_mode)
        run_result = getattr(sync, f"run_{resource}")(mode, args)

        if resource == "report":
            if verb == 'send':
                send_email(vfzsync.CONFIG["mail"]["subject"], vfzsync.CONFIG["mail"]["sender"], [vfzsync.CONFIG["mail"]["recipient"]], "", "", run_result)
            if verb == 'run':
                return run_result

        state[resource][mode]["status"] = "completed"
        result["success"] = True
        result["message"] = "completed"

    except Exception as e:
        state[resource][mode]["status"] = "failed"
        result["success"] = False
        result["message"] = f"{resource.capitalize()} {verb} failed."
        result["exception"] = str(e)
        logger.exception(f"{resource.capitalize()} {verb} failed.")

    state[resource][mode]["date"] = int(time.time())
    return result


state = {
    "sync": {
        "vpoller-fnt": {"status": "initialized", "date": int(time.time())},
        "fnt-zabbix": {"status": "initialized", "date": int(time.time())},
    },
    "update": {"random": {"status": "initialized", "date": int(time.time())}},
    "send": {
        "trapper": {"status": "initialized", "date": int(time.time())},
        "groupupdate": {"status": "initialized", "date": int(time.time())},
    },
    "test": {"test": {"status": "initialized", "date": int(time.time())}},
    "report": {
        "problemsactive": {"status": "initialized", "date": int(time.time())},
        "problemsclosed": {"status": "initialized", "date": int(time.time())},
    },
}

logger = init_logger()
logger.debug(f"{__name__} init done.")

app.config.update(
    MAIL_SERVER=vfzsync.CONFIG["mail"]["server"],
    MAIL_PORT=vfzsync.CONFIG["mail"]["port"],
    MAIL_USE_TLS=vfzsync.CONFIG["mail"]["use_tls"],
    MAIL_USE_SSL=vfzsync.CONFIG["mail"]["use_ssl"],
    MAIL_USERNAME=vfzsync.CONFIG["mail"]["username"],
    MAIL_PASSWORD=vfzsync.CONFIG["mail"]["password"]
)
mail = Mail(app)
