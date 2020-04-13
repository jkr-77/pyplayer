from ui.qt import pywindow, pyelement
from utilities.history import History
from interpreter import Interpreter

import enum
class PyPlayerCloseReason(enum.Enum):
    NONE = 0,
    RESTART = 1,
    MODULE_CONFIGURE = 2

class PyPlayer(pywindow.PyWindow):
    def __init__(self, root, window_id):
        pywindow.PyWindow.__init__(self, root, window_id)
        self.layout.column(1, minsize=30, weight=1)
        self.layout.row(3, minsize=100, weight=1)

        self.title = "PyPlayerQt"
        self._title_song = ""
        self.icon = "assets/icon.png"

        self._command_history = History()
        self._interp = None
        self._cmd = None
        self.schedule_task(func=self._insert_reply, task_id="reply_task", reply="= Hello there =")

        @self.events.EventWindowDestroy
        def _on_destroy():
            if self._interp: self._interp.stop()
            root.destroy()

    def create_widgets(self):
        pywindow.PyWindow.create_widgets(self)
        header_left: pyelement.PyTextLabel = self.add_element("header_left", element_class=pyelement.PyTextLabel, row=0, column=0)
        header_center: pyelement.PyTextLabel = self.add_element("header_center", element_class=pyelement.PyTextLabel, row=0, column=1)
        header_right: pyelement.PyTextLabel = self.add_element("header_right", element_class=pyelement.PyTextLabel, row=0, column=2)

        header_left.text = "left"
        header_center.text = "center"
        header_center.set_alignment("center")
        header_right.text = "right"

        console = self.add_element("console", element_class=pyelement.PyTextField, row=3, columnspan=3)
        console.accept_input = False

        input: pyelement.PyTextInput = self.add_element("console_input", element_class=pyelement.PyTextInput, row=4, columnspan=3)
        @input.events.EventInteract
        def _on_input_enter():
            self._on_command_enter(input.value)
            input.value = ""

        @input.events.EventHistory
        def _set_history(direction):
            if direction > 0: input.value = self._command_history.get_next("")
            elif direction < 0:
                hist = self._command_history.get_previous()
                if hist is not None: input.value = hist
            return input.events.block_action

    def start_interpreter(self, module_cfg):
        self._interp = Interpreter(self, module_cfg)

    def _on_command_enter(self, cmd):
        if cmd:
            self["console"].text += f"{cmd}\n"
            self._command_history.add(cmd)
            self["console_input"].accept_input = False
            self._interp.put_command(cmd)

    def _insert_reply(self, reply, tags=None, prefix=None, text=None):
        if not prefix: prefix = "> "
        self["console"].text += f"{reply}\n{prefix}"
        self["console_input"].accept_input = True

    def on_reply(self, reply, tags=None, cmd=None, prefix='', text=''):
        self._cmd = cmd
        self.schedule_task(task_id="reply_task", reply=reply, tags=tags, prefix=prefix, text=text)

    def update_title(self, title, checks=None):
        if not title: title = self.title
        prefix = " ".join(f"[{c}]" for c in (checks if checks is not None else []))
        self._title_song = title
        self.title = prefix + " " + title

    def update_title_media(self, media_data):
        self.update_title(media_data.display_name)
        self["progress_bar"].progress = 0