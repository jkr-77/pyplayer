from ui import pyelement, pyconfiguration
import tkinter

class BaseWidgetContainer:
	def __init__(self, container, tk, configuration):
		if configuration is None: configuration = pyconfiguration.Configuration()
		elif isinstance(configuration, dict): configuration = pyconfiguration.Configuration(configuration)
		self._container = container
		self._tk = tk
		self._elements = {}
		self._subframes = []
		self._cfg = configuration
		self.load_configuration()

	@property
	def configuration(self): return self._cfg
	def load_configuration(self):
		try: self._tk.configure(**{key: value for key, value in self._cfg.value.items() if not isinstance(value, dict)})
		except tkinter.TclError as e: print("ERROR", "Failed to load configuration:", e)

	def row(self, index, minsize=None, padding=None, weight=None):
		""" Customize row behavior at given index:
		 		- minsize: the minimun size this row must have; this row stops shrinking when it is this size (not applied when its empty)
		 		- padding: amount of padding set to the biggest element in this row
		 		- weight: how much this row should expand when the window is resized
		 	Returns itself for simplified updating """
		self._tk.grid_rowconfigure(index, minsize=minsize, pad=padding, weight=weight)
		return self

	def column(self, index, minsize=None, padding=None, weight=None):
		""" Customize column behavior at given index:
				- minsize: the minimun size this column must have; this column stops shrinking when it is this size (not applied when its empty)
				- padding: amount of padding set to the biggest element in this column
				- weight: how much this column should expand when the window is resized
			Returns itself for simplified updating """
		self._tk.grid_columnconfigure(index, minsize=minsize, pad=padding, weight=weight)
		return self

	def place_element(self, element, row=0, column=0, rowspan=1, columnspan=1, sticky="news"):
		""" Place an element (must be a variant of PyElement) on this widget, use additional arguments to position it in this container
		 	row, rowspan: the row in the frame grid layout and how many rows it should cover
		 	column, columnspan: the column in the frame grid layout and how many columns it should cover
		 	Returns the added element """
		if isinstance(element, pyelement.PyElement):
			self._elements[element.widget_id] = element
			element._tk.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan, sticky=sticky)
			return self._elements[element.widget_id]
		else: raise ValueError("Placed element must be a 'PyElement', not '{.__name__}'".format(type(element)))

	def place_frame(self, frame, row=0, column=0, rowspan=1, columnspan=1, sticky="news"):
		""" Create another element container (must be a 'PyFrame' or any of its variants) inside this container,
			supported arguments and their behavior are the same as for elements
			Returns the index of the added container """
		if isinstance(frame, BaseWidgetContainer):
			self._subframes.append(frame)
			frame._tk.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan, sticky=sticky)
			return len(self._subframes) - 1
		else: raise ValueError("Placed frame must be a 'PyFrame', not '{.__name__}'".format(type(frame)))

	def remove_element(self, id):
		id = id.lower()
		prev_wd = self._elements.get(id)
		if prev_wd:
			try:
				prev_wd.grid_forget()
				prev_wd.destroy()
				del self._elements[id]
			except Exception as e: print("ERROR", "Destroying previously bound widget for '{}':".format(id), e)

	def show(self):
		self._tk.pack(fill="both", expand=True)

	def __getitem__(self, item):
		""" Get the element that was assigned to given name, returns this element or None if nothing bound """
		return self._elements.get(item)

	def __setitem__(self, key, value): raise AttributeError("Cannot set or replace elements directly, use 'place_element' instead!")
	def __delitem__(self, key): raise AttributeError("Cannot delete elements directly, use 'remove_element' instead!")

frame_cfg = {"background": "black"}
class PyFrame(BaseWidgetContainer):
	def __init__(self, parent, configuration=None):
		if configuration and not isinstance(configuration, pyconfiguration.Configuration): raise ValueError("Configuration, when not empty, must be a configuration object, not '{.__name__}'! Check your setup!".format(type(configuration)))
		BaseWidgetContainer.__init__(self, parent, tkinter.Frame(parent._tk, **frame_cfg), configuration)

label_cfg = {"foreground": "white"}
label_cfg.update(frame_cfg)
class PyLabelFrame(BaseWidgetContainer):
	def __init__(self, parent, configuration=None):
		BaseWidgetContainer.__init__(self, parent, tkinter.LabelFrame(parent._tk, **label_cfg), configuration)

	@property
	def label(self): return self._tk.cget("text")
	@label.setter
	def label(self, lbl): self._tk.configure(text=lbl)

class PyCanvas(BaseWidgetContainer):
	def __init__(self, parent, configuration=None):
		BaseWidgetContainer.__init__(self, parent, tkinter.Canvas(parent._tk, **frame_cfg), configuration)

class PyScrollableFrame(PyFrame):
	def __init__(self, parent, configuration=None):
		PyFrame.__init__(self, parent, configuration)
		self._scrollable = PyCanvas(self)
		self._content = PyFrame(self._scrollable)