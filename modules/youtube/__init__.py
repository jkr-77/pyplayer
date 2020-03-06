from utilities import messagetypes

# DEFAULT MODULE VARIABLES
interpreter = client = None

# MODULE SPECIFIC VARIABLES
yt = None
download_options = {
    "format": "bestaudio/best",
	"outtmpl": "%(title)s.%(ext)s",
    "postprocessors": [{
		"key": "FFmpegExtractAudio",
		"preferredcodec": "mp3",
		"preferredquality": "320"
    }]
}

# --- MODULE HELPER FUNCTIONS ---
def ensure_yt():
	global yt, download_options
	if yt is None:
		import youtube_dl, os
		try:
			dir = client.configuration["directory"]["youtube"]["path"]
			download_options["outtmpl"] = os.path.join(dir, download_options["outtmpl"])
		except KeyError: print("WARNING", "No valid 'youtube' path detected, current directory will be used instead")
		except Exception as e: print("ERROR", "Something went wrong detting youtube download options (defaults are used instead):", e)
		yt = youtube_dl.YoutubeDL(download_options)

def _check_link(tag):
	if tag.has_attr("class"):
		if tag.name == "a": return "yt-uix-tile-link" in tag["class"]
		elif tag.name == "div": return "yt-lockup-description" in tag["class"]
	return False

def search(query):
	import requests
	query = query.replace(" ", "+")
	try: r = requests.get("https://www.youtube.com/results?search_query={}".format(query))
	except Exception as e:
		print("ERROR", "Executing Youtube request:", e)
		return None

	res = []
	if r.status_code == 200:
		from bs4 import BeautifulSoup
		html = BeautifulSoup(r.content, features="html.parser")
		ls = iter(html.find_all(_check_link))
		while True:
			try:
				header, desc = next(ls), next(ls)
				if header["href"].startswith("/"): res.append((header["title"], header["href"], str(desc.contents[0])))
			except StopIteration: break
			except KeyError: pass
			except Exception as e: print("ERROR", "Parsing youtube html tag:", e)
	else: print("WARNING", "Invalid response from server '{}':".format(r.status_code), r.reason)
	return res

def convert(url, filename=None):
	if not filename: filename = download_options["outtmpl"]

	ensure_yt()
	global yt
	try:
		yt.params["outtmpl"] = filename + ".%(ext)s"
		return yt.download([url])
	except Exception as e:
		print("INFO", "Passed argument was not a valid url:", e)
		return -1

def process_path(narg, nargc, **data):
	if nargc == 1:
		argn = " ".join(narg)
		path = client.configuration["directory"].get(argn)
		if path is not None: return process_song(**data, path=path)
		else: return messagetypes.Reply("Unknown path '{}'".format(argn))

def process_song(arg, argc, url=None, path=None):
	if path is None: return messagetypes.Question("Where should it be saved to?", process_path, arg=arg, argc=argc, text=client.configuration["default_path"], url=url)
	arg = " ".join(arg)

	try: path = path["path"]
	except KeyError: return messagetypes.Reply("No path set in '{}'".format(path))
	import os
	res = convert(url, os.path.join(path, arg))

	if res == 0: return messagetypes.Reply("Song downloaded as '{}'".format(arg))
	else: return messagetypes.Reply("Error downloading file: code {}".format(res))

def handle_url(value, data=None, path=None):
	if value is not None and data is not None:
		return messagetypes.Question("What should the file be named?", process_song, text=value, url=data, path=path)
	else: return messagetypes.Reply("Nothing found")
# --- END OF HELPER FUNCTIONS

def command_youtube_find(arg, argc, path=None):
	if argc > 0:
		if argc > 1 and arg[-1] == "all":
			scan_official = False
			arg.pop(-1)
		else: scan_official = True

		arg = " ".join(arg)
		ls = search(arg)
		if ls is None: return messagetypes.Reply("There was an error looking for file, see log for details...")

		res, officals = [], []
		for title, link, desc in ls:
			link = link[9:]
			if scan_official and desc.startswith("Provided to YouTube by"): officals.append((title, link))
			res.append((title, link))

		if len(officals) > 0: return messagetypes.Select("Found official videos:", handle_url, choices=officals, path=path)
		else: return messagetypes.Select("Found multiple videos:", handle_url, choices=res, path=path)

commands = {
	"youtube": {
		"find": command_youtube_find
	}
}