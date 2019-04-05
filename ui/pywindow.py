import os
import sys
import tkinter
import weakref

from ui import pyelement, pyconfiguration, pycontainer

def warn_deprecation():
	import warnings
	warnings.warn("Deprecated!")

class PyWindow(tkinter.Toplevel):
	""" Framework class for windows, they have to be created with a valid root """
	block_action = "break"

	def __init__(self, parent, id, initial_cfg=None, cfg_file=None):
		tkinter.Toplevel.__init__(self, parent)
		self._windowid = id
		self.title = "PyWindow: " + self._windowid
		self.icon = ""

		self._children = weakref.WeakValueDictionary()
		self._tick_operations = {}
		self._autosave, self._autosave_delay = None, 0

		if cfg_file is None: cfg_file = ".cfg/" + self._windowid.lower()
		elif not cfg_file.startswith(".cfg/"): cfg_file = ".cfg/" + cfg_file
		self._configuration = pyconfiguration.ConfigurationFile(cfg_file, initial_cfg)
		self.load_configuration()

	# ===== Window Properties =====
	@property
	def window_id(self):
		""" The (unique) identifier for this window, this cannot change once the window is created """
		return self._windowid
	@property
	def is_alive(self):
		""" Returns true when this window has not been closed """
		return self.winfo_exists()
	@property
	def floating(self): return None
	@floating.setter
	def floating(self, value):
		""" Sets this window to be transient, connected to its parent and is minimized when the parent is minimized
		 	* update: this is equal to the 'transient' parameter in the previous version """
		if value:
			try: self.wm_transient(self.master)
			except Exception as e: print("ERROR", "Failed to set window as transient, caused by:", e)

	@property
	def decorator(self):
		""" Set true to prevent the window from being decorated; only the content will be visible
		 	Useful for making custom window decorators """
		return self.wm_overrideredirect()
	@decorator.setter
	def decorator(self, vl):
		self.wm_overrideredirect(not vl)

	@property
	def hidden(self):
		""" Returns True if the window is currently hidden """
		return self.wm_state() == "withdrawn"
	@hidden.setter
	def hidden(self, value):
		""" Hide/unhide the window, if the window is hidden all traces are removed. Can only be unhidden by updating this property """
		if value: self.wm_withdraw()
		else: self.wm_deiconify()
	def toggle_hidden(self): self.hidden = not self.hidden

	@property
	def autosave_delay(self):
		""" Time interval (in minutes) between automatic save of window configuration to file, returns 0 if disabled """
		return self._autosave_delay
	@autosave_delay.setter
	def autosave_delay(self, value):
		""" Set time interval (in minutes) between autosaves (if dirty), set to 0 to disable """
		#todo: unfinished
		pass

	@property
	def screen_height(self):
		""" Get the height in pixels for the display the window is on """
		return self.winfo_screenheight()
	@property
	def screen_width(self):
		""" Get the width in pixels for the display the window is on """
		return self.winfo_screenwidth()

	@property
	def width(self):
		""" Get the width of this window in pixels """
		return self.winfo_width()
	@width.setter
	def width(self, vl):
		""" Customize the width of this window, in most cases this value does not need to be set:
				it automatically updates to fit all widgets and the previously set value (when resized)
			* update: width clamped between 0 and screen_width """
		self.configure(width=max(0, min(vl, self.screen_width)))

	@property
	def height(self):
		""" Get the height of this window in pixels """
		return self.winfo_height()
	@height.setter
	def height(self, vl):
		""" Customize the height of this window, in most cases this value does not need to be set:
				it automatically updates to fit all widgets and the previously set value (when resized)
		 	* update: height clamped between 0 and screen_height """
		self.configure(height=max(0, min(vl, self.screen_height)))

	@property
	def window_title(self):
		""" Get current window title """
		return self.wm_title()
	@window_title.setter
	def window_title(self, value):
		""" Update current window title """
		self.wm_title(value)

	@property
	def icon(self):
		""" Get current window icon """
		return self.wm_iconbitmap()

	@icon.setter
	def icon(self, value):
		""" Set window icon, this must be a valid path to an image
			(file extension may be omitted, it is automatically selected based on platform: .iso (Windows), .png (Linux))
		 	* update: errors are no longer raised, instead they are only written to log (aside from also not being updated) """
		if not value: value = "assets/blank"

		try:
			if "linux" in sys.platform:
				path = os.path.dirname(os.path.realpath(__file__))
				self.tk.call("wm", "iconphoto", self._w,
									pyelement.PyImage(file=os.path.join(path, os.pardir, value + ".png")))
			elif "win" in sys.platform: self.iconbitmap(value + ".ico")
		except Exception as e: print("ERROR", "Setting icon bitmap {}".format(e)); raise

	# ===== Base Operations =====
	def load_configuration(self):
		""" (Re)load configuration from file """
		self._configuration.load()
		self.wm_geometry(self._configuration.get("geometry"))
		self.autosave_delay = self._configuration.get_or_create("autosave_delay", 5)

	def write_configuration(self):
		""" Write window configuration to file (if dirty) """
		self._configuration["geometry"] = self.wm_geometry()
		self._configuration["autosave_delay"] = self._autosave_delay
		self._configuration.save()

	def open_window(self, id, window):
		""" Adds new child window to this window using passed (unique) identifier
		 	(any window already assigned to this identifier will be destroyed)
		 	Returns the bound window if successful, None otherwise
		 	* update: it is no longer an error if a previously open window cannot be closed
		 	* update: now returns None instead of False """
		id = id.lower()
		self.close_window(id)
		window.id = id
		self._children[id] = window
		return self.children.get(id)

	def close_window(self, id):
		""" Destroy and remove window assigned to passed identifier (has no effect if identifier was not bound)
		 	Returns True if call was successful, False otherwise """
		id = id.lower()
		wd = self.children.get(id)
		if self._children is not None and wd is not None:
			try: wd.destroy()
			except Exception as e: print("ERROR", "Couldn't destroy window '{}' properly: ".format(id), e); return False
		return True

	@property
	def always_on_top(self):
		""" If true this window will always display be displayed above others """
		return bool(self.wm_attributes("-topmost"))
	@always_on_top.setter
	def always_on_top(self, value):
		""" Set this window to be always above others """
		self.wm_attributes("-topmost", "1" if value else "0")

	def focus_followsmouse(self):
		""" The widget under mouse will get focus, cannot be disabled once set """
		self.tk_focusFollowsMouse()

	def center_window(self, width, height):
		self.wm_geometry("{}x{}+{}+{}".format(width, height, (self.screen_width // 2) - (width // 2), (self.screen_height // 2) - (height // 2)))

	def after(self, *args, **kwargs):
		raise DeprecationWarning("No longer directly usable, call 'schedule' instead!")

	def schedule(self, min=0, sec=0, ms=0, func=None, loop=False, **kwargs):
		""" Schedule an operation to be executed at least after the given time, all registered callbacks will stop when the window is closed
		 	 -	Amount of time to wait can be specified with minutes (keyword 'min'), seconds (keyword 'sec') and/or milliseconds (keyword 'ms')
		 	 -	The argument passed to func must be callable and accept the extra arguments passed to this function
		 	 -	The function can be called repeatedly by setting 'loop' to true;
		 	 		in this case it will be called repeatedly after the given time until an error occurs or the callback returns False
			* update: delay is allowed to be 0, in this case the callback is executed as soon as possible """
		if not callable(func): raise ValueError("'func' argument must be callable!")
		delay = (min * 60000) + (sec * 1000) + ms
		if delay < 0: raise ValueError("Delay cannot be smaller than 0")

		if loop:
			self._tick_operations[func.__name__] = delay, func
			tkinter.Toplevel.after(self, delay, self._run_tickoperation, func.__name__, kwargs)
		else: tkinter.Toplevel.after(self, delay, func, *kwargs.values())

	def _run_tickoperation(self, name, kwargs):
		operation = self._tick_operations.get(name)
		if operation:
			delay, func = operation
			try:
				res = func(**kwargs)
				if res is not False: self.after(delay, self._run_tickoperation, name, kwargs)
				else: print("INFO", "Callback '{}' returned False, it will not be rescheduled".format(name))
			except Exception as e:
				print("ERROR", "Calling scheduled operation '{}', it will not be rescheduled\n".format(name), e)
				del self._tick_operations[name]
		else: print("WARNING", "Got operation callback for '{}', but no callback was found!".format(name))

class PyTkRoot(tkinter.Tk):
	""" Root window for this application (should be the first created window and should only be created once, for additional windows use 'PyWindow' instead) """
	def __init__(self, name="pyroot"):
		tkinter.Tk.__init__(self, name)
		self.wm_overrideredirect(True)

	def center_window(self, width, height):
		self.wm_geometry("{}x{}+{}+{}".format(width, height, (self.winfo_screenwidth() // 2) - (width // 2), (self.winfo_screenmmheight() // 2) - (height // 2)))

	def start(self):
		""" Initialize and start GUI """
		try: self.mainloop()
		except KeyboardInterrupt:
			print("INFO", "Received keyboard interrupt, closing program...")
			self.destroy()