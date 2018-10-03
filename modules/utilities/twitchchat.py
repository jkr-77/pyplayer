from collections import OrderedDict
from multiprocessing import Queue

from ui import pyelement
from utilities import history

import re, threading, time, datetime
import io, socket, requests, random
import os, json

re_emote_translation = {
	"\\:-?\\)": ":)", "\\:-?\\(": ":(",
	"\\:-?D": ":D", "\\&gt\\;\\(": ">(",
	"\\:-?[z|Z|\\|]": ":z", "[oO](_|\\.)[oO]": "O_o",
	"B-?\\)": "B)", "\\:-?(o|O)": ":o",
	"\\&lt\\;3": "<3", "\\:-?[\\\\/]": ":/",
	"\\;-?\\)": ";)", "\\:-?(p|P)": ":P",
	"\\;-?(p|P)": ";p", "R-?\\)": "R)"
}
class IRCClient(threading.Thread):
	def __init__(self, message_queue, extra_info=False):
		super().__init__()
		self.socket = None
		self.message_queue = message_queue
		self.extra_info = extra_info

	def start_client(self, server, port, username, auth, channel):
		self.server = server
		self.port = port
		self.username = username
		self.auth = auth
		self.channel_name = channel
		super().start()

	def connect(self):
		print("INFO", "connecting to", self.server, ":", self.port)
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.connect((self.server, self.port))
		self.send("PASS {!s}".format(self.auth))
		self.send("NICK {!s}".format(self.username))
		if self.extra_info:
			self.send("CAP REQ :twitch.tv/tags")
			self.send("CAP REQ :twitch.tv/commands")
		self.send("JOIN #{}".format(self.channel_name))

	def disconnect(self):
		print("INFO", "disconnecting from", self.server)
		if self.socket is not None:
			try:
				self.socket.shutdown(socket.SHUT_RDWR)
				self.socket.close()
			except Exception as e: print("ERROR", "closing socket:", e)
			print("INFO", "disconnected")
		self.socket = None

	def send(self, message):
		self.socket.send(bytes("{!s}\r\n".format(message), "UTF-8"))

	def run(self):
		self.connect()
		while self.socket is not None:
			try:
				rec = self.socket.recv(1024)
				if not rec:
					print("INFO", "Connection was terminated, shutting down socket")
					break

				rec = rec.decode("UTF-8").split("\r\n")
				for data in rec: self.message_queue.put_nowait(data.split(" ", maxsplit=4))
			except UnicodeDecodeError: pass
			except Exception as e: print("ERROR", "receiving from IRC socket:", e)

class TwitchChat(pyelement.PyTextfield):
	chat_server = "irc.chat.twitch.tv"
	chat_port = 6667
	twitch_badge_url = "https://api.twitch.tv/kraken/chat/{channel}/badges?client_id={client_id}"
	channel_badge_url = "https://badges.twitch.tv/v1/badges/channels/{channel_id}/display"
	twitch_emote_url = "http://static-cdn.jtvnw.net/emoticons/v1/{emote_id}/1.0"
	bit_url = "https://api.twitch.tv/kraken/bits/actions?api_version=5&client_id={client_id}&channel_id={channel_id}"
	bit_format = re.compile(r"(.+?)([0-9]+)")
	bttv_emote_list = "https://api.betterttv.net/2/emotes"
	bttv_emote_url = "https://cdn.betterttv.net/emote/{id}/1x"

	emote_cache_folder = "twitch/emotecache"
	emotemap_cache_file = "twitch/emotemap_cache"
	emotemap_url = "https://api.twitch.tv/kraken/users/{user}/emotes"

	def __init__(self, master, limited_mode=False):
		self._window = master
		pyelement.PyTextfield.__init__(self, master, accept_input=False)
		self._callback = None
		self._irc_client = None
		self._chat_size = 0
		self._enable_scroll = True
		self._limited_mode = limited_mode

		self._user_meta = None
		self._emotecache = {}
		self._bttv_emotecache = {}
		self._bitcache = {}
		self._badgecache = {}
		self._emotenamecache = {}
		self._versioned_badges = []
		self._timestamp = None

		self._message_queue = Queue()
		self.configure(cursor="left_ptr", wrap="word", spacing1=3, padx=5)
		self.bind("<End>", self.adjust_scroll).bind("<Enter>&&<Leave>", self.set_scroll)
		self.update_time()
		if not os.path.isdir(self.emote_cache_folder): os.mkdir(self.emote_cache_folder)

	@property
	def command_callback(self): return self._callback
	@command_callback.setter
	def command_callback(self, callback):
		if callable(callback): self._callback = callback
		else: print("ERROR", "Tried to set queue callback to non-callable type", callback)

	def update_time(self):
		self._timestamp = datetime.datetime.today()
		self.after(1, self.update_time)

	def adjust_scroll(self, event):
		self.see("end")

	def set_scroll(self, event):
		self._enable_scroll = (event.x < 0 or event.x > event.widget.winfo_width()) or (event.y < 0 or event.y > event.widget.winfo_height())
		if self._enable_scroll: self.adjust_scroll(event)

	def connect(self, channel_meta, login):
		if self._irc_client is None:
			if isinstance(login, dict):
				self._channel_meta = channel_meta
				self._irc_client = IRCClient(self._message_queue, extra_info=True)
				self._irc_client.start_client(TwitchChat.chat_server, TwitchChat.chat_port, login["username"], login["oauth"], self._channel_meta["name"])

				self._load_badges(login)
				self._load_local_emote()
				self._load_bttv()
				self._load_bits(login)
				self._load_emotemap(login)
				self.add_text(text=" - Joined channel: {} -".format(self._channel_meta["display_name"]), tags=("notice",))
			else: raise TypeError("Login should be a 'dict', not '{}'".format(type(login).__name__))
		else: print("INFO", "Tried to connect again when the IRC client was already started")

	def disconnect(self):
		if self._irc_client is not None:
			self._irc_client.send("PART #{}".format(self._channel_meta["name"]))
			self._irc_client.send("QUIT")
			self._irc_client.disconnect()
			self._irc_client.join()
			self._irc_client = None

	# ===== BUILT-IN HELPER METHODS =====
	# === BTTV emote support ===
	def _load_bttv(self):
		u = requests.get(self.bttv_emote_list).json()
		for emote in u["emotes"]:
			if emote["imageType"] != "gif": self._bttv_emotecache[emote["code"]] = emote["id"]

	def _get_bttv_emote(self, name):
		img = self._bttv_emotecache.get(name)
		if img is None: return None

		if isinstance(img, str):
			try: self._bttv_emotecache[name] = pyelement.PyImage(url=self.bttv_emote_url.format(id=img))
			except Exception as e:
				print("ERROR", "Cannot load bttv emote '{}':".format(name), e)
				del self._bttv_emotecache[name]
				return
		return self._bttv_emotecache[name]

	# === Bit support ===
	def _load_bits(self, login):
		bit_motes = requests.get(self.bit_url.format(client_id=login["client-id"],channel_id=self._channel_meta["_id"])).json()
		self.tag_configure("cheer1", font=self.bold_font, foreground="gray")
		self.tag_configure("cheer100", font=self.bold_font, foreground="purple")
		self.tag_configure("cheer1000", font=self.bold_font, foreground="cyan")
		self.tag_configure("cheer5000", font=self.bold_font, foreground="blue")
		self.tag_configure("cheer10000", font=self.bold_font, foreground="red")
		for emote in bit_motes["actions"]:
			list = []
			for tier in emote["tiers"]:
				list.append((int(tier["min_bits"]), tier["images"]["dark"]["static"]["1"]))
			self._bitcache[emote["prefix"].lower()] = OrderedDict(list)

	def _get_bit_emote(self, name, amount):
		if not name in self._bitcache: return None

		try: amount = int(amount)
		except ValueError: return None

		emote = None
		for (min_amount, img) in self._bitcache[name].items():
			if min_amount > amount: break
			emote = (min_amount, img)

		if emote is None: return None
		if isinstance(emote[1], str):
			try: self._bitcache[name][emote[0]] = pyelement.PyImage(url=emote[1])
			except Exception as e:
				print("ERROR", "Loading bit emote", name, "->", e)
				del self._bitcache[name]
				return None
		return (emote[0], self._bitcache[name][emote[0]])

	# === MULTI TIERED SUBSCRIPTION + DEFAULT BADGE SUPPORT ===
	def _load_badges(self, login):
		badges = requests.get(self.twitch_badge_url.format(channel=self._channel_meta["name"], client_id=login["client-id"])).json()
		self._badgecache["global_mod"] = badges["global_mod"]["alpha"]
		self._badgecache["admin"] = badges["admin"]["alpha"]
		self._badgecache["broadcaster"] = badges["broadcaster"]["alpha"]
		self._badgecache["staff"] = badges["staff"]["alpha"]
		self._badgecache["moderator"] = badges["mod"]["alpha"]

		if self._channel_meta["partner"]:
			badges = requests.get(self.channel_badge_url.format(channel_id=self._channel_meta["_id"])).json()
			badge_set = badges["badge_sets"]
			if "subscriber" in badge_set:
				self._versioned_badges.append("subscriber")
				for version, url in badge_set["subscriber"]["versions"].items():
					self._badgecache["subscriber/" + version] = url["image_url_1x"]

			if "bits" in badge_set:
				self._versioned_badges.append("bits")
				for version, url in badge_set["bits"]["versions"].items():
					self._badgecache["bits/" + version] = url["image_url_1x"]

		for badge_id, badge_url in self._badgecache.items():
			try: self._badgecache[badge_id] = pyelement.PyImage(url=badge_url)
			except Exception as e:
				print("ERROR", "Loading badge", badge_id, "->", e)
				del self._badgecache[badge_id]

	# === Twitch emote support ===
	def _load_local_emote(self):
		try: self._emotecache["25"] = pyelement.PyImage(file="twitch/kappa.png")
		except: pass
		try: self._emotecache["36"] = pyelement.PyImage(file="twitch/pjsalt.png")
		except: pass
		try: self._emotecache["66"] = pyelement.PyImage(file="twitch/onehand.png")
		except: pass

	def _load_emote(self, emote_id):
		file = self.emote_cache_folder + "/" + emote_id + ".bin"
		if os.path.isfile(file):
			try:
				img = pyelement.PyImage(file=file)
				self._emotecache[emote_id] = img
				return img
			except Exception as e: print("ERROR", "Getting emote", emote_id, "from cache:", e)

		url = self.twitch_emote_url.format(emote_id=emote_id)
		try: img = pyelement.PyImage(url=url)
		except Exception as e:
			print("ERROR", "Getting emote", emote_id, "from url:", e)
			return None
		self._emotecache[emote_id] = img

		try: img.write(file)
		except Exception as e: print("ERROR", "Writing emote", emote_id, "to cache:", e)
		return img

	def get_emoteimage_from_cache(self, emote_id):
		if emote_id in self._emotecache: return self._emotecache[emote_id]

		emote = self._load_emote(emote_id)
		if emote is not None:
			self._emotecache[emote_id] = emote
			return emote
		else: return None

	@property
	def emotemap_cache(self): return self._emotenamecache
	def _load_emotemap(self, login):
		if os.path.isfile(self.emotemap_cache_file) and time.time() - os.path.getmtime(self.emotemap_cache_file) < 86400:
			try:
				jfile = open(self.emotemap_cache_file, "r")
				self._emotenamecache = json.load(jfile)
				jfile.close()
				return
			except Exception as e: print("ERROR", "Parsing previously written emote name cache:", e)

		try:
			emote_map = requests.get(self.emotemap_url.format(user=login["username"]), headers={"Client-ID": login["client-id"], "Authorization": "OAuth " + login["access-token"]}).json()
			if "error" in emote_map: raise ConnectionError(emote_map["message"])

			for set, emotes in emote_map["emoticon_sets"].items():
				for emote in emotes:
					if emote["code"] in re_emote_translation: self._emotenamecache[re_emote_translation[emote["code"]]] = str(emote["id"])
					else: self._emotenamecache[emote["code"]] = str(emote["id"])

			jfile = open(self.emotemap_cache_file, "w")
			json.dump(self._emotenamecache, jfile)
			jfile.close()
		except Exception as e:
			if "access-token" in str(e):
				print("ERROR", "No access token found, get one from https://id.twitch.tv/oauth2/authorize?client_id=" +
					login["client-id"] + "&redirect_uri=http://localhost&response_type=code&scope=user_subscriptions")
				raise ConnectionError("No access token found, see log for details...")
			else: print("ERROR", "Getting emote cache:", e)

	# ===== END OF BUILT-IN HELPER METHODS =====
	def send_message(self, msg):
		if self._irc_client is not None:
			self._irc_client.send("PRIVMSG #" + self._channel_meta["name"] + " :" + msg)
			if msg.startswith("/me"): msg = "\x01ACTION" + msg[3:]
			if self._user_meta is None:
				self.insert("end", "\n You: ", ("notice",))
				self.insert("end", msg.rstrip("\n"))
			else: self.on_privmsg(self._user_meta, msg.rstrip("\n"))

	def on_privmsg(self, meta, data):
		if meta is None: return
		for line in self._window["message_blacklist"]:
			if line in data: return

		user = meta["display-name"]
		color = meta["color"]
		if len(color) == 0:
			try: color = self.tag_cget(user.lower(), "foreground")
			except: color = "#" + "".join("{:02x}".format(n) for n in [random.randrange(75,255), random.randrange(75,255), random.randrange(75,255)])
		self.tag_configure(user.lower(), foreground=color, font=self.bold_font)

		emotes = meta.get("emotes", "").split("/")
		emote_list = {}
		for emote in emotes:
			emote = emote.split(":")
			if len(emote) == 2: emote_list[emote[0]] = emote[1]

		badges = meta["badges"].split(",")
		self.insert("end", "\n")
		if self._window["enable_timestamp"]: self.insert("end", self._timestamp.strftime("%I:%M "), ("notice",))
		for badge in badges:
			is_versioned = False
			for b in self._versioned_badges:
				if badge.startswith(b): is_versioned = True; break

			if not is_versioned: badge = badge.split("/")[0]

			if badge in self._badgecache:
				self.image_create(index="end", image=self._badgecache[badge])
				self.insert("end", " ")

		self.add_text(user=user, text=data, emotes=emote_list, bits="bits" in meta)

	def add_text(self, text, user="", emotes=None, bits=False, tags=()):
		text = "".join([c for c in text if ord(c) <= 65536])
		if text.startswith("\x01ACTION"):
			text = text.lstrip("\x01ACTION ").rstrip("\x01")
			tags = (user.lower())
		elif text == "": return

		if self._chat_size >= self._window["chat_limit"]: self.delete("2.0", "3.0")
		else: self._chat_size += 1
		if user != "": self.insert("end", user + " ", (user.lower(),))

		emote_map = {}
		if emotes is not None:
			for emote_id, emote_index in emotes.items():
				self.get_emoteimage_from_cache(emote_id)

				emote_index = emote_index.split(",")[0].split("-")
				emote_begin = int(emote_index[0])
				emote_end = int(emote_index[1]) + 1
				emote_map[text[emote_begin:emote_end]] = emote_id

		text = text.split(" ")
		for word in text:
			if not self._limited_mode and self._window["enable_triggers"] and word in self._window["chat_triggers"]:
				if callable(self._callback): self._callback(self._window["chat_triggers"][word])

			if word in emote_map:
				try: self.image_create(index="end", image=self._emotecache[emote_map[word]])
				except Exception as e: print("ERROR", "Creating emote for word '{}' from id:".format(word), e)
				continue

			elif word in self._emotenamecache:
				if not self._emotenamecache[word] in self._emotecache: self._load_emote(self._emotenamecache[word])
				try: self.image_create(index="end", image=self._emotecache[self._emotenamecache[word]])
				except Exception as e: print("ERROR", "Creating emote for word '{}' from name: ", e)
				continue

			elif bits:
				bit = self.bit_format.findall(word)
				if len(bit) > 0:
					try:
						im = self._get_bit_emote(name=bit[0][0], amount=bit[0][1])
						self.image_create("end", image=im[1])
						self.insert("end", str(bit[0][1]), "cheer"+str(im[0]))
					except Exception: pass
					continue

			elif word in self._bttv_emotecache:
				try: self.image_create("end", image=self._get_bttv_emote(word))
				except Exception as e: print("ERROR", "Error creating image for bttv emote '{}':".format(word), e)
				continue

			self.insert("end", word + " ", tags)

		if self._enable_scroll: self.see("end")

	def get_meta(self, data):
		if not data.startswith("@"): return None
		else: data = data.lstrip("@")

		data = data.split(";")
		res = {}
		for line in data:
			line = line.split("=")
			if len(line) == 2: res[line[0]] = line[1]
		return res

	def on_usernotice(self, meta, data):
		if meta is None or self._limited_mode: return
		type = meta["msg-id"]
		if type == "resub": text = meta["display-name"] + " resubscribed for " + meta["msg-param-months"] + " months"
		elif type == "sub": text = meta["display-name"] + " subscribed"
		elif type == "subgift": text = meta["display-name"] + " gifted a subscription to " + meta["msg-param-recipient-display-name"]
		else: return

		if meta["msg-param-sub-plan"] == "Prime": level = " with Prime"
		elif meta["msg-param-sub-plan"] == "1000": level = ""
		elif meta["msg-param-sub-plan"] == "2000": level = " at tier 2"
		else: level = " at tier 3"
		self.insert("end", "\n" + text + level, ("notice",))
		self.configure(state="disabled")
		if len(data) > 0: self.on_privmsg(meta, data)

	def on_notice(self, meta, data):
		self.insert("end", "\n" + data, ("notice",))

	def on_clearchat(self, user):
		tag = user.lower() + ".last"
		try: self.tag_add("deleted", tag, tag + " lineend")
		except: pass

	def on_userstate(self, meta):
		if meta is not None: self._user_meta = meta

	def run(self):
		if self._irc_client is not None:
			if not self._message_queue.empty(): self.process_data(self._message_queue.get_nowait())
			self.after(.1, self.run)

	def process_data(self, data):
		try:
			if data[0] == "PING": self._irc_client.send("PONG " + "".join(data[1:]))
			elif data[2] == "PRIVMSG": self.on_privmsg(meta=self.get_meta(data[0]), data=data[4][1:])
			elif data[2] == "NOTICE": self.on_notice(meta=self.get_meta(data[0]), data=data[4][1:])
			elif data[2] == "USERNOTICE": self.on_usernotice(meta=self.get_meta(data[0]), data="".join(data[4:])[1:])
			elif data[2] == "CLEARCHAT": self.on_clearchat(data[4][1:])
			elif data[2] == "USERSTATE": self.on_userstate(self.get_meta(data[0]))
		except IndexError: pass

class TwitchChatTalker(pyelement.PyTextfield):
	def __init__(self, root, send_message_callback):
		if not callable(send_message_callback): raise TypeError("Callback not callable!")
		pyelement.PyTextfield.__init__(self, root)
		self.bind("<Escape>", self.clear_text)
		self.bind("<Return>", self.on_send_message)
		self.bind("<Up>", self.set_history)
		self.bind("<Down>", self.set_history)
		self.configure(height=5, wrap="word", spacing1=3, padx=5)
		self.message_callback = send_message_callback
		self._chathistory = history.History()

	def is_empty(self): return len(self.text) == 0

	def set_history(self, event):
		if event.keysym == "Up": last_cmd = self._chathistory.get_previous(self._chathistory.head)
		elif event.keysym == "Down": last_cmd = self._chathistory.get_next()
		else: return

		if last_cmd is not None: self.text = last_cmd
		else: self.clear_text(event)
		return self.block_action

	def add_emote(self, emote):
		if self.get("insert-1c") != " ": emote = " " + emote
		if not emote.endswith(" "): emote += " "
		self.insert("insert", emote)

	def on_send_message(self, event):
		if callable(self.message_callback):
			message = self.text
			if len(message) > 0:
				self.message_callback(message)
				self._chathistory.add(message)
			self.clear_text(event)
		else:
			self.message_callback = None
			print("ERROR", "Chat message sender has invalid callback, messages will not be sent")
		return self.block_action

	def clear_text(self, event):
		self.delete("0.0", "end")
		self.mark_set("insert", "0.0")