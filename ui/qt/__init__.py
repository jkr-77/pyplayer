__all__ = ["pyelement", "pyevents", "pyimage", "pylauncher", "pylayout", "pynetwork", "pywindow", "pyworker", "log_exception", "network_manager"]

# pyqt documentation:
# https://doc.qt.io/qtforpython/modules.html

def log_exception(e): print("ERROR", "An error occured:", e)

try:
    from . import pywindow, pyelement, pynetwork
    network_manager = pynetwork.NetworkManager()
except ImportError: network_manager = None