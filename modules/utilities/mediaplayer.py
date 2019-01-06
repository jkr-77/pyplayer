import vlc as VLCPlayer

import os, random

def get_displayname(filepath):
	return os.path.splitext(filepath)[0]

class DynamicClass:
	def __init__(self, **kwargs):
		for it in kwargs.items(): self.__setattr__(*it)
	def __str__(self): return "{}({})".format(self.__class__.__name__, ", ".join(["{}='{}'".format(*it) for it in self.__dict__.items()]))

class MediaPlayerData(DynamicClass):
	def __init__(self, path, song, **kwargs):
		self.path = path
		self.song = song
		self.display_name = get_displayname(song)
		DynamicClass.__init__(self, **kwargs)

class MediaPlayerEventUpdate(DynamicClass):
	id = 0
	def __init__(self, data, **kwargs):
		self.data = data
		DynamicClass.__init__(self, **kwargs)

class MediaPlayer():
	""" Helper class for playing music using the vlc python bindings
	 	When a new song is started when the last song is almost done,
	 	the player will start the new song without stopping the previous for smooth transitioning  """
	end_pos = 0.85

	def __init__(self):
		print("INFO", "Initializing new MediaPlayer instance...")
		self._vlc = VLCPlayer.Instance()
		self._player1 = self._vlc.media_player_new()
		self._player1.audio_output_set("mmdevice")
		self._player2 = self._vlc.media_player_new()
		self._player2.audio_output_set("mmdevice")

		self._muted = False
		self._paused = False
		self._player_one = True
		self._media = None
		self._media_data = None
		self._updated = False
		self._filter = None
		self._blacklist = None
		self._last_random = None

		self._events = {
			"end_reached": (VLCPlayer.EventType.MediaPlayerEndReached, self.on_song_end, []),
			"media_changed": (VLCPlayer.EventType.MediaPlayerMediaChanged, self.on_media_change, []),
			"paused": (VLCPlayer.EventType.MediaPlayerPaused, self.on_pause, []),
			"playing": (VLCPlayer.EventType.MediaPlayerPlaying, self.on_play, []),
			"pos_changed": (VLCPlayer.EventType.MediaPlayerPositionChanged, self.on_pos_change, []),
			"stopped": (VLCPlayer.EventType.MediaPlayerStopped, self.on_stop, [])
		}

		# register vlc event handlers
		for event in self._events.items():
			event_key, event_value = event
			self._player1.event_manager().event_attach(event_value[0], event_value[1], event_key, self._player1, True)
			self._player2.event_manager().event_attach(event_value[0], event_value[1], event_key, self._player2, False)

		# register custom event handlers
		self._events["player_updated"] = (MediaPlayerEventUpdate, self.on_update, [])

	# === PLAYER PROPERTIES ===
	@property
	def active_player(self):
		""" Returns the player that is currenty playing music, or None if nothing playing """
		return self._player1 if self._player_one else self._player2 if self._media_data is not None else None
	@property
	def current_media(self):
		""" Returns information about the current song playing, or None if nothing playing """
		return self._media_data

	@property
	def filter_path(self): return self._filter[0] if self._filter is not None else ""
	@property
	def filter_keyword(self): return self._filter[1] if self._filter is not None else ""
	def update_filter(self, path="", keyword=""):
		""" Set a filter for random song picking using path and keyword
		 	(will override the blacklist that was set on this player) """
		self._filter = [path, keyword]

	@property
	def blacklist(self): return self._blacklist
	def update_blacklist(self, blacklist):
		""" Update the player blacklist, all songs from artist in this list will not be picked as random song
		 	This list is ignored when a filter is set or when choosing a specific song """
		if blacklist is not None and not isinstance(blacklist, list): raise TypeError("Blacklist must be a list!")
		self._blacklist = blacklist

	# === PLAYER UTILITIES ===
	def list_songs(self, path, keyword="", exact_search=False):
		"""	List all items found in specified directory
			Items that match the full keyword get returned first, if no matches found returns items containing the keyword
				path: the path to search in
				keyword: [optional], returns all items matching this keyword or all items if no argument passed
				exact_search: [optional], set true to only look for songs with an exact match """
		print("INFO", "looking for songs in '{}' with keyword(s) '{}'".format(path, keyword))
		res1 = []
		res2 = []
		keyword = keyword.lower()

		if os.path.isdir(path):
			with os.scandir(path) as dir:
				for entry in dir:
					if entry.is_file():
						file = entry.name
						song = get_displayname(file.replace(" - ", " ").lower())
						if exact_search and song == keyword: return [file]
						elif " " + keyword + " " in " " + song + " ": res1.append(file)
						elif keyword == "" or keyword in song: res2.append(file)

		if len(res1) > 0: return res1
		else: return res2

	def find_song(self, path, keyword=None):
		""" Find songs in given path that contain given keyword, where keyword should be a string list separated by spaces
			- when the keyword ends with a '.' only an exact match (if it exists) is returned
			- when the keyword ends with a number, this number will be used for picking one from the found selection (if in range)
			-> Returns a list of songs found where each item is a tuple: (displayname, song) """
		exact = False
		index = -1
		if keyword and len(keyword) > 0:
			if keyword[-1].endswith("."):
				exact = True
				keyword[-1] = keyword[-1][:-1]
			else:
				try:
					index = int(keyword[-1])
					keyword.pop(-1)
				except ValueError: pass

		keyword = " ".join(keyword)
		ls = self.list_songs(path, keyword, exact_search=exact)
		if 0 <= index < len(ls): return [(get_displayname(ls[index]), ls[index])]
		else: return [(get_displayname(s), s) for s in ls]

	def play_song(self, path, song):
		""" Plays a song only when the full path and song name are known and they exist in the given path
			If successful, returns the updated media data generated by the player """
		file = os.path.join(path, song)
		print("INFO", "Preparing to play", file)
		if not os.path.isfile(file): return None

		if self._media is not None: self._media.release()
		self._media = self._vlc.media_new(file)
		self._media_data = MediaPlayerData(path, song)
		if self._paused: self.stop_player()
		player = self.active_player
		player.set_media(self._media)
		player.play()

		self.mute_player(self._muted)
		self._paused = False
		self._updated = True
		return self._media_data

	def set_position(self, pos):
		""" Update the position the player is currently at, has no effect if the player is stopped/finished
		 	Returns true if the position was updated, false otherwise"""
		if self._media is not None:
			print("INFO", "Trying to update player position to {}".format(pos))
			pl = self.active_player
			if pl is not None:
				pl.set_media(self._media)
				pl.play()
				pl.set_position(pos)
				return True
			else: return False
		else:
			print("INFO", "Cannot update position since no previous media was found")
			return False

	def mute_player(self, mute=None):
		""" Update mute status of this player to given value
			When no value is given the mute satus is toggled """
		if mute is None: mute = not self._muted
		self._muted = mute
		self._player1.audio_set_mute(mute)
		self._player2.audio_set_mute(mute)
		return self._muted

	def pause_player(self):
		""" Toggle player pause (has no effect if nothing is playing) """
		self._paused = not self._paused and self._media_data is not None
		self._player1.set_pause(self._paused)
		self._player2.set_pause(self._paused)

	def stop_player(self):
		""" Stop playback """
		self._paused = False
		self._player1.stop()
		self._player2.stop()
		self._media_data = None

# ===== OTHER FUNCTIONS =====
	def random_song(self, path="", keyword=""):
		""" Choose a random song from a directory, uses values set in player filter when no arguments are given """
		if path == "": path = self.filter_path
		if keyword == "": keyword = self.filter_keyword
		print("INFO", "Play random song from ", path, ", keyword=", keyword, sep="")
		songlist = self.list_songs(path, keyword)
		if len(songlist) > 0:
			song = None
			tries = 0
			while song is None and tries < 3:
				tries += 1
				s = random.choice(songlist)
				match = False
				if self._blacklist is not None:
					for item in self._blacklist:
						if item.lower() == s.split(" - ", maxsplit=1)[0].lower():
							match = True
							print("INFO", "Found blacklist item '{}', tried {} times now".format(item, tries))
							break
				if not match: song = s

			if song is not None:
				self._last_random = (path, song)
				self.play_song(path, song)
				return "Playing: {}".format(get_displayname(song))
			else: return "No song found that doesn't match something in blacklist, try reducing the number of blacklisted items"
		return "No songs with that filter"

	def play_last_random(self):
		if self._last_random is not None:
			return self.play_song(self._last_random[0], self._last_random[1])
		else: return None

# ===== EVENT HANDLING =====
	def attach_event(self, event, callback):
		""" Attach a new callback handle to the selected event, has no effect if handle was already attached or if it is not callable
			(The attached callback will only be called only with the player that is in foreground when the event occurred)
				event: The name of the event
				callback: The function to be called when the event occurs, must take two arguments: the event that was triggered and the VLC player that triggered the event """
		self.update_event_handler(event, callback, add=True)

	def detach_event(self, event, callback):
		""" Detach a handler that was previously attached using attach_event, has no effect if handle was never attached of if it is not callable """
		self.update_event_handler(event, callback, add=False)

	def update_event_handler(self, event, callback, add):
		if event in self._events:
			if not callable(callback): raise TypeError("'callable' argument must be callable")
			handle = self._events[event]
			if add == (not callback in handle[2]):
				if add: handle[2].append(callback)
				else: handle[2].remove(callback)
		else: print("WARNING", "Tried to register unknown event handler id '" + event + "', ignoring this call...")

	def call_attached_handlers(self, name, event, player):
		if name in self._events:
			for cb in self._events[name][2]:
				try: cb(event, player)
				except Exception as e: print("ERROR", "Calling event handler '{}':".format(name), e)

	def on_song_end(self, event, name, player, player_one):
		if not self._updated:
			self._paused = False
			self.call_attached_handlers(name, event, player)

	def on_media_change(self, event, name, player, player_one):
		if self._player_one == player_one:
			self.call_attached_handlers(name, event, player)

	def on_stop(self, event, name, player, player_one):
		if self._player_one == player_one:
			self.call_attached_handlers(name, event, player)

	def on_pause(self, event, name, player, player_one):
		if self._player_one == player_one:
			self.call_attached_handlers(name, event, player)

	def on_play(self, event, name, player, player_one):
		if self._player_one == player_one:
			self.call_attached_handlers(name, event, player)

	def on_pos_change(self, event, name, player, player_one):
		if (self._player_one == self._updated) == player_one:
			pos = event.u.new_position
			if self._updated and pos > MediaPlayer.end_pos:
				self._player_one = not self._player_one
				self._updated = False
				self.call_attached_handlers("player_updated", MediaPlayerEventUpdate(self._media_data), player)
			self.call_attached_handlers(name, event, player)

	def on_update(self, event, name, player, player_one):
		self.call_attached_handlers(name, event, player)

# ====== DESTROY PLAYER INSTANCE =====
	def on_destroy(self):
		print("INFO", "Looks like we're done here, release all player stuffs")
		self._player1.release()
		self._player2.release()
		self._vlc.release()
