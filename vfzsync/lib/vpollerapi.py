import json

from vpoller.client import VPollerClient

from debugtoolkit.debugtoolkit import deflogger, deflogger_class, init_logger


# @deflogger_class
class vPollerAPI:
    def deflogger_skip(self):
        pass

    def __init__(self, vpoller_endpoint, vpoller_retries, vpoller_timeout):
        super().__init__()
        self.client = VPollerClient(endpoint=vpoller_endpoint, retries=vpoller_retries, timeout=vpoller_timeout)

    def run(self, vc_host, method, name=None, key=None, properties=None):
        msg = {"method": method, "hostname": vc_host}
        for prop in ['name', 'properties', 'key']:
            if eval(prop) is not None:
                msg[prop] = eval(prop)

        response = json.loads(self.client.run(msg))
        if response["success"] == 0:
            result = response["result"]
            return result
        else:
            logger.error(f'Failed to execute method "{method}": {msg}')
            raise vPollerException(f'{response["msg"]}')


class vPollerException(Exception):
    """ vPoller Exception """
    pass


logger = init_logger()
