import datetime
import time

def flatten(l):
    return [item for sublist in l for item in sublist]


def normalize_none(attr):
    if attr is None:
        attr = ""
    return attr


def yes_no(arg, type=bool):
    if not arg:
        arg = 'n'
    arg_lower = arg.lower()
    if type == bool:
        if arg_lower == "y" or arg_lower == "yes":
            return True
        return False
    if type == int:
        if arg_lower == "y" or arg_lower == "yes":
            return 1
        return 0


def gib_round(x):
    return round(x / 1024 ** 3, 3)


def datetime_to_local_timezone(dt):
    epoch = dt.timestamp()  # Get POSIX timestamp of the specified datetime.
    st_time = time.localtime(
        epoch
    )  #  Get struct_time for the timestamp. This will be created using the system's locale and it's time zone information.
    tz = datetime.timezone(
        datetime.timedelta(seconds=st_time.tm_gmtoff)
    )  # Create a timezone object with the computed offset in the struct_time.
    return dt.astimezone(tz)  # Move the datetime instance to the new time zone.


class ProgressCounter():
    def __init__(self, final, step):
        super().__init__()
        self.final = final
        self.counter = 0
        self.last_progress = 0
        self.step = step

    def iterate(self):
        self.counter += 1
        self.progress = round(100 * self.counter / self.final, 0)
        if self.progress % self.step == 0 and self.last_progress != self.progress:
            self.last_progress = self.progress
            return self.progress
        return False

    def deflogger_skip(self):
        pass

