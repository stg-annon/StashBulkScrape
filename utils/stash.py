import re, sys, requests
from collections import defaultdict

from dataclasses import dataclass

from enum import Enum, IntEnum

from utils.stash_types import StashItem


class BulkUpdateIdMode(Enum):
	SET = "SET"
	ADD = "ADD"
	REMOVE = "REMOVE"

class ScrapeType(Enum):
	NAME = "NAME"
	FRAGMENT = "FRAGMENT"
	URL = "URL"

class PhashDistance(IntEnum):
	EXACT = 0
	HIGH = 4
	MEDIUM = 8
	LOW = 10

class StashInterface:
	port = ""
	url = ""
	headers = {
		"Accept-Encoding": "gzip, deflate",
		"Content-Type": "application/json",
		"Accept": "application/json",
		"Connection": "keep-alive",
		"DNT": "1"
	}
	cookies = {}

	def __init__(self, conn={}, fragments={}):
		global log

		if conn.get("Logger"):
			log = conn.get("Logger")
		else:
			raise Exception("No Logger Provided")


		self.port = conn.get('Port', 9999)
		scheme = conn.get('Scheme','http')

		# Session cookie for authentication
		self.cookies = {}
		if conn.get("SessionCookie"):
			self.cookies['session'] = conn['SessionCookie']['Value']

		domain = conn.get('Domain', 'localhost')

		# Stash GraphQL endpoint
		self.url = f'{scheme}://{domain}:{self.port}/graphql'

		try:
			# test query to ensure good connection
			self.call_gql("query Configuration {configuration{general{stashes{path}}}}")
			log.debug(f"Connected to Stash GraphQL endpoint at {self.url}")
		except Exception:
			log.error(f"Could not connect to Stash at {self.url}")
			sys.exit()

		self.fragments = fragments
		self.fragments.update(gql_fragments)

		# create flags
		self.create_on_missing_tag = False
		self.create_on_missing_performer = False

	def __resolveFragments(self, query):

		fragmentReferences = list(set(re.findall(r'(?<=\.\.\.)\w+', query)))
		fragments = []
		for ref in fragmentReferences:
			fragments.append({
				"fragment": ref,
				"defined": bool(re.search("fragment {}".format(ref), query))
			})

		if all([f["defined"] for f in fragments]):
			return query
		else:
			for fragment in [f["fragment"] for f in fragments if not f["defined"]]:
				if fragment not in self.fragments:
					raise Exception(f'GraphQL error: fragment "{fragment}" not defined')
				query += self.fragments[fragment]
			return self.__resolveFragments(query)

	def __callGraphQL(self, query, variables=None):

		query = self.__resolveFragments(query)

		json_request = {'query': query}
		if variables is not None:
			json_request['variables'] = variables

		response = requests.post(self.url, json=json_request, headers=self.headers, cookies=self.cookies)
		
		if response.status_code == 200:
			result = response.json()

			if result.get("errors"):
				for error in result["errors"]:
					log.debug(f"GraphQL error: {error}")
			if result.get("error"):
				for error in result["error"]["errors"]:
					log.debug(f"GraphQL error: {error}")
			if result.get("data"):
				scraped_markers = defaultdict(lambda: None)
				scraped_markers.update(result)
				return scraped_markers['data']
		elif response.status_code == 401:
			sys.exit("HTTP Error 401, Unauthorized. Cookie authentication most likely failed")
		else:
			raise ConnectionError(
				"GraphQL query failed:{} - {}. Query: {}. Variables: {}".format(
					response.status_code, response.content, query, variables)
			)

	def call_gql(self, query, variables={}):
		return self.__callGraphQL(query, variables)

	def __match_alias_item(self, search, items):
		item_matches = {}
		for item in items:
			if re.match(rf'{search}$', item["name"], re.IGNORECASE):
				# log.debug(f'matched "{search}" to "{item["name"]}" ({item["id"]}) using primary name')
				item_matches[item["id"]] = item
			if not item["aliases"]:
				continue
			for alias in item["aliases"]:
				if re.match(rf'{search}$', alias.strip(), re.IGNORECASE):
					log.debug(f'matched "{search}" to "{alias}" ({item["id"]}) using alias')
					item_matches[item["id"]] = item
		return list(item_matches.values())

	def __match_performer_alias(self, search, performers):
		item_matches = {}
		for item in performers:
			if re.match(rf'{search}$', item["name"], re.IGNORECASE):
				log.info(f'matched "{search}" to "{item["name"]}" ({item["id"]}) using primary name')
				item_matches[item["id"]] = item
			if not item["aliases"]:
				continue
			for alias in item["aliases"]:
				parsed_alias = alias.strip()
				if ":" in alias:
					parsed_alias = alias.split(":")[-1].strip()
				if re.match(rf'{search}$', parsed_alias, re.IGNORECASE):
					log.info(f'matched "{search}" to "{alias}" ({item["id"]}) using alias')
					item_matches[item["id"]] = item
		return list(item_matches.values())

	def graphql_configuration(self):
		query = """
			query Configuration {
				configuration {
					...ConfigData
				}
			}
			fragment ConfigData on ConfigResult {
				general {
					...ConfigGeneralData
				}
				interface {
					...ConfigInterfaceData
				}
				dlna {
					...ConfigDLNAData
				}
			}
			fragment ConfigGeneralData on ConfigGeneralResult {
				stashes {
					path
					excludeVideo
					excludeImage
				}
				databasePath
				generatedPath
				configFilePath
				cachePath
				calculateMD5
				videoFileNamingAlgorithm
				parallelTasks
				previewAudio
				previewSegments
				previewSegmentDuration
				previewExcludeStart
				previewExcludeEnd
				previewPreset
				maxTranscodeSize
				maxStreamingTranscodeSize
				apiKey
				username
				password
				maxSessionAge
				logFile
				logOut
				logLevel
				logAccess
				createGalleriesFromFolders
				videoExtensions
				imageExtensions
				galleryExtensions
				excludes
				imageExcludes
				scraperUserAgent
				scraperCertCheck
				scraperCDPPath
				stashBoxes {
					name
					endpoint
					api_key
				}
			}
			fragment ConfigInterfaceData on ConfigInterfaceResult {
				menuItems
				soundOnPreview
				wallShowTitle
				wallPlayback
				maximumLoopDuration
				autostartVideo
				showStudioAsText
				css
				cssEnabled
				language
				slideshowDelay
				handyKey
			}
			fragment ConfigDLNAData on ConfigDLNAResult {
				serverName
				enabled
				whitelistedIPs
				interfaces
			}
		"""
		
		result = self.__callGraphQL(query)
		return result['configuration']

	def metadata_scan(self, paths=[]):
		query = """
		mutation metadataScan($input:ScanMetadataInput!) {
			metadataScan(input: $input)
		}
		"""
		variables = {
			'input': {
				'paths' : paths,
				'useFileMetadata': False,
				'stripFileExtension': False,
				'scanGeneratePreviews': False,
				'scanGenerateImagePreviews': False,
				'scanGenerateSprites': False,
				'scanGeneratePhashes': True
			}
		}
		result = self.__callGraphQL(query, variables)
		return result

	# Tag CRUD
	def find_tag(self, name_in, create=False):
		name = name_in
		if isinstance(name, dict):
			if not name.get("name"):
				return
			name = name["name"]

		if not isinstance(name, str):
			log.warning(f'find_tag expects str or dict not {type(name_in)} "{name_in}"')
			return

		for tag in self.find_tags(q=name):
			if tag["name"].lower() == name.lower():
				return tag
			if any(name.lower() == a.lower() for a in tag["aliases"] ):
				return tag
		if create:
			return self.create_tag({"name":name})
	def create_tag(self, tag):
		query = """
			mutation tagCreate($input:TagCreateInput!) {
				tagCreate(input: $input){
					...stashTag
				}
			}
		"""
		variables = {'input': tag}
		result = self.__callGraphQL(query, variables)
		return result["tagCreate"]
	#TODO update_tag
	def destroy_tag(self, tag_id):
		query = """
			mutation tagDestroy($input: TagDestroyInput!) {
				tagDestroy(input: $input)
			}
		"""
		variables = {'input': {
			'id': tag_id
		}}

		self.__callGraphQL(query, variables)

	# Tags CRUD
	def find_tags(self, q="", f={}):
		query = """
			query FindTags($filter: FindFilterType, $tag_filter: TagFilterType) {
				findTags(filter: $filter, tag_filter: $tag_filter) {
					count
					tags {
						...stashTag
					}
				}
			}
		"""

		variables = {
		"filter": {
			"direction": "ASC",
			"per_page": -1,
			"q": q,
			"sort": "name"
		},
		"tag_filter": f
		}
		
		result = self.__callGraphQL(query, variables)
		return result["findTags"]["tags"]

	# Performer CRUD
	def find_performer(self, performer_data, create_missing=False):
		if isinstance(performer_data, str):
			performer_data["name"] = performer_data
		if not performer_data.get("name"):
			return None

		name = performer_data["name"]
		name = name.strip()

		performer_data["name"] = name

		performers = self.find_performers(q=name)

	
		for p in performers:
			if not p.get("aliases"):
				continue
			alias_delim = re.search(r'(\/|\n|,)', p["aliases"])
			if alias_delim:
				p["aliases"] = p["aliases"].split(alias_delim.group(1))
			elif len(p["aliases"]) > 0:
				p["aliases"] = [p["aliases"]]
			else:
				log.debug(f'Could not determine delim for aliases "{p["aliases"]}"')

		performer_matches = self.__match_performer_alias(name, performers)

		# none if multuple results from a single name performer
		if len(performer_matches) > 1 and name.count(' ') == 0:
			return None
		elif len(performer_matches) > 0:
			return performer_matches[0] 


		if create_missing:
			log.info(f'Create missing performer: "{name}"')
			return self.create_performer(performer_data)
	def create_performer(self, performer_data):
		query = """
			mutation($input: PerformerCreateInput!) {
				performerCreate(input: $input) {
					id
				}
			}
		"""

		variables = {'input': performer_data}

		result = self.__callGraphQL(query, variables)
		return result['performerCreate']['id']
	def update_performer(self, performer_data):
		query = """
			mutation performerUpdate($input:PerformerUpdateInput!) {
				performerUpdate(input: $input) {
					id
				}
			}
		"""
		variables = {'input': performer_data}

		result = self.__callGraphQL(query, variables)
		return result['performerUpdate']['id']
	#TODO delete performer

	# Performers CRUD
	def find_performers(self, q="", f={}):
		query =  """
			query FindPerformers($filter: FindFilterType, $performer_filter: PerformerFilterType) {
				findPerformers(filter: $filter, performer_filter: $performer_filter) {
					count
					performers {
						...stashPerformer
					}
				}
			}
		"""

		variables = {
			"filter": {
				"q": q,
				"per_page": -1,
				"sort": "name",
				"direction": "ASC"
			},
			"performer_filter": f
		}

		result = self.__callGraphQL(query, variables)
		return result['findPerformers']['performers']

	# Studio CRUD
	def find_studio(self, studio, create_missing=False, domain_pattern=r'[^.]*\.[^.]{2,3}(?:\.[^.]{2,3})?$'):
		if not studio.get("name"):
			return None

		name = studio["name"]

		studio_matches = []

		if re.match(domain_pattern, name):
			url_search = self.find_studios(f={
				"url":{ "value": name, "modifier": "INCLUDES" }
			})
			for s in url_search:
				if re.search(rf'{name}',s["url"]):
					log.info(f'matched "{name}" to {s["url"]} using URL')
					studio_matches.append(s)

		name_results = self.find_studios(q=name)
		studio_matches.extend(self.__match_alias_item(name, name_results))

		if len(studio_matches) > 1 and name.count(' ') == 0:
			return None
		elif len(studio_matches) > 0:
			return studio_matches[0] 

		if create_missing:
			log.info(f'Create missing studio: "{name}"')
			return self.create_studio(studio)
	def create_studio(self, studio):
		query = """
			mutation($name: String!) {
				studioCreate(input: { name: $name }) {
					id
				}
			}
		"""
		variables = {
			'name': studio['name']
		}

		result = self.__callGraphQL(query, variables)
		studio['id'] = result['studioCreate']['id']

		return self.update_studio(studio)
	def update_studio(self, studio):
		query = """
			mutation StudioUpdate($input:StudioUpdateInput!) {
				studioUpdate(input: $input) {
					id
				}
			}
		"""
		variables = {'input': studio}

		result = self.__callGraphQL(query, variables)
		return result["studioUpdate"]["id"]
	# TODO delete_studio()

	def get_studio(self, studio, get_root_parent=False):
		query =  """
		query FindStudio($studio_id: ID!) {
			findStudio(id: $studio_id) {
				...stashStudio
			}
		}
		"""
		variables = {
			"studio_id": studio.get("id")
		}
		result = self.__callGraphQL(query, variables)
		studio = result['findStudio']

		if get_root_parent and studio and studio.get("parent_studio"):
			return self.get_studio(studio["parent_studio"], get_root_parent=True)
		return studio
		

	def find_studios(self, q="", f={}):
		query =  """
		query FindStudios($filter: FindFilterType, $studio_filter: StudioFilterType) {
			findStudios(filter: $filter, studio_filter: $studio_filter) {
			count
			studios {
				...stashStudio
			}
			}
		}
		"""

		variables = {
			"filter": {
			"q": q,
			"per_page": -1,
			"sort": "name",
			"direction": "ASC"
			},
			"studio_filter": f
		}

		result = self.__callGraphQL(query, variables)
		return result['findStudios']['studios']

	# Movie CRUD
	def find_movie(self, movie, create_missing=False):

		name = movie["name"]
		movies = self.find_movies(q=name)

		movie_matches = self.__match_alias_item(name, movies)

		if len(movie_matches) > 0:
			if len(movie_matches) == 1:
				return movie_matches[0]
			else:
				log.warning(f'Too many matches for movie "{name}"')
				return None

		if create_missing:
			log.info(f'Creating missing Movie "{name}"')
			return self.create_movie(movie)
	def create_movie(self, movie):
		name = movie["name"]
		query = """
			mutation($name: String!) {
				movieCreate(input: { name: $name }) {
					id
				}
			}
		"""
		variables = {'name': name}
		result = self.__callGraphQL(query, variables)
		movie['id'] = result['movieCreate']['id']
		return self.update_movie(movie)
	def update_movie(self, movie):
		query = """
			mutation MovieUpdate($input:MovieUpdateInput!) {
				movieUpdate(input: $input) {
					id
				}
			}
		"""
		variables = {'input': movie}

		result = self.__callGraphQL(query, variables)
		return result['movieUpdate']['id']
	#TODO delete movie

	# Movies CRUD
	def find_movies(self, q="", f={}):
		query = """
			query FindMovies($filter: FindFilterType, $movie_filter: MovieFilterType) {
				findMovies(filter: $filter, movie_filter: $movie_filter) {
					count
					movies {
						...stashMovie
					}
				}
			}
		"""

		variables = {
			"filter": {
				"per_page": -1,
				"q": q
			},
			"movie_filter": f
		}
		
		result = self.__callGraphQL(query, variables)
		return result['findMovies']['movies']

	#Gallery CRUD
	# create_gallery() done by scan see metadata_scan()
	# TODO find_gallery()
	def update_gallery(self, gallery_data):
		query = """
			mutation GalleryUpdate($input:GalleryUpdateInput!) {
				galleryUpdate(input: $input) {
					id
				}
			}
		"""
		variables = {'input': gallery_data}

		result = self.__callGraphQL(query, variables)
		return result["galleryUpdate"]["id"]
	# TODO delete_gallery

	# BULK Gallery
	def find_galleries(self, q="", f={}):
		query = """
			query FindGalleries($filter: FindFilterType, $gallery_filter: GalleryFilterType) {
				findGalleries(gallery_filter: $gallery_filter, filter: $filter) {
					count
					galleries {
						...stashGallery
					}
				}
			}
		"""
		variables = {
			"filter": {
				"q": q,
				"per_page": -1,
				"sort": "path",
				"direction": "ASC"
			},
			"gallery_filter": f
		}

		result = self.__callGraphQL(query, variables)
		return result['findGalleries']['galleries']


	# Scene CRUD
	# create_scene() done by scan see metadata_scan()
	def find_scene(self, id:int, scene_fragment="...stashScene"):
		query = """
		query FindScene($scene_id: ID) {
			findScene(id: $scene_id) {
				__SCENE_FRAGMENT__
			}
		}
		""".replace("__SCENE_FRAGMENT__", scene_fragment)
		variables = {"scene_id": id}

		result = self.__callGraphQL(query, variables)
		return result['findScene']
	def update_scene(self, update_input):
		query = """
			mutation sceneUpdate($input:SceneUpdateInput!) {
				sceneUpdate(input: $input) {
					id
				}
			}
		"""
		variables = {'input': update_input}
		result = self.__callGraphQL(query, variables)
		return result["sceneUpdate"]["id"]
	def destroy_scene(self, scene_id, delete_file=False):
		query = """
		mutation SceneDestroy($input:SceneDestroyInput!) {
			sceneDestroy(input: $input)
		}
		"""
		variables = {
			"input": {
				"delete_file": delete_file,
				"delete_generated": True,
				"id": scene_id
			}
		}
			
		result = self.__callGraphQL(query, variables)
		return result['sceneDestroy']
	
	# BULK Scenes
	# scenes created by scan see metadata_scan()
	def find_scenes(self, f={}, filter={"per_page": -1}):
		query = """
		query FindScenes($filter: FindFilterType, $scene_filter: SceneFilterType, $scene_ids: [Int!]) {
			findScenes(filter: $filter, scene_filter: $scene_filter, scene_ids: $scene_ids) {
				count
				scenes {
					...stashScene
				}
			}
		}
		"""
		variables = {
			"filter": filter,
			"scene_filter": f
		}
			
		result = self.__callGraphQL(query, variables)
		return result['findScenes']['scenes']
	def update_scenes(self, updates_input):
		query = """
			mutation BulkSceneUpdate($input:BulkSceneUpdateInput!) {
				bulkSceneUpdate(input: $input) {
					id
				}
			}
		"""
		variables = {'input': updates_input}

		result = self.__callGraphQL(query, variables)
		return result["bulkSceneUpdate"]
	def destroy_scenes(self, scene_ids, delete_file=False):
		query = """
		mutation ScenesDestroy($input:ScenesDestroyInput!) {
			scenesDestroy(input: $input)
		}
		"""
		variables = {
			"input": {
				"delete_file": delete_file,
				"delete_generated": True,
				"ids": scene_ids
			}
		}
			
		result = self.__callGraphQL(query, variables)
		return result['scenesDestroy']

	# Scraper Operations
	def reload_scrapers(self):
		query = """ 
			mutation ReloadScrapers {
				reloadScrapers
			}
		"""
		
		result = self.__callGraphQL(query)
		return result["reloadScrapers"]
	
	def list_item_scrapers(self, item:StashItem, type:ScrapeType):
		match item:
			case StashItem.PERFORMER:
				return self.list_performer_scrapers(type)
			case StashItem.SCENE:
				return self.list_scene_scrapers(type)
			case StashItem.GALLERY:
				return self.list_gallery_scrapers(type)
			case StashItem.MOVIE:
				return self.list_movie_scrapers(type)
	def list_performer_scrapers(self, type:ScrapeType):
		query = """
		query ListPerformerScrapers {
			listPerformerScrapers {
			  id
			  name
			  performer {
				supported_scrapes
			  }
			}
		  }
		"""
		result = self.__callGraphQL(query)["listPerformerScrapers"]
		return [r["id"] for r in result if type.value in r["performer"]["supported_scrapes"]]
	def list_scene_scrapers(self, type:ScrapeType):
		query = """
		query listSceneScrapers {
			listSceneScrapers {
			  id
			  name
			  scene{
				supported_scrapes
			  }
			}
		  }
		"""
		result = self.__callGraphQL(query)["listSceneScrapers"]
		return [r["id"] for r in result if type.value in r["scene"]["supported_scrapes"]]
	def list_gallery_scrapers(self, type:ScrapeType):
		query = """
		query ListGalleryScrapers {
			listGalleryScrapers {
			  id
			  name
			  gallery {
				supported_scrapes
			  }
			}
		  }
		"""
		ret = []
		result = self.__callGraphQL(query)["listGalleryScrapers"]
		return [r["id"] for r in result if type.value in r["gallery"]["supported_scrapes"]]
	def list_movie_scrapers(self, type:ScrapeType):
		query = """
		query listMovieScrapers {
			listMovieScrapers {
			  id
			  name
			  movie {
				supported_scrapes
			  }
			}
		  }
		"""
		ret = []
		result = self.__callGraphQL(query)["listMovieScrapers"]
		return [r["id"] for r in result if type.value in r["gallery"]["supported_scrapes"]]

	# Fragment Scrape
	def scrape_scene(self, scraper_id:int, scene):
		
		if not isinstance(scene, dict) or not scene.get("id"):
			log.warning('Unexpected Object passed to scrape_single_scene')
			log.warning(f'Type: {type(scene)}')
			log.warning(f'{scene}')

		query = """query ScrapeSingleScene($source: ScraperSourceInput!, $input: ScrapeSingleSceneInput!) {
			scrapeSingleScene(source: $source, input: $input) {
			  ...scrapedScene
			}
		  }
		"""
		
		variables = {
			"source": {
				"scraper_id": scraper_id
			},
			"input": {
				"query": None,
				"scene_id": scene["id"],
				"scene_input": {
					"title": scene["title"],
					"details": scene["details"],
					"url": scene["url"],
					"date": scene["date"],
					"remote_site_id": None
				}
			}
		}
		result = self.__callGraphQL(query, variables)
		if not result:
			return None
		scraped_scene_list = result["scrapeSingleScene"]
		if len(scraped_scene_list) == 0:
			return None
		else:
			return scraped_scene_list[0]
	def scrape_gallery(self, scraper_id:int, gallery):
		query = """query ScrapeGallery($scraper_id: ID!, $gallery: GalleryUpdateInput!) {
		   scrapeGallery(scraper_id: $scraper_id, gallery: $gallery) {
			  ...scrapedGallery
			}
		  }
		"""
		variables = {
			"scraper_id": scraper_id,
			"gallery": {
				"id": gallery["id"],
				"title": gallery["title"],
				"url": gallery["url"],
				"date": gallery["date"],
				"details": gallery["details"],
				"rating": gallery["rating"],
				"scene_ids": [],
				"studio_id": None,
				"tag_ids": [],
				"performer_ids": [],
			}
		}

		result = self.__callGraphQL(query, variables)
		return result["scrapeGallery"]
	def scrape_performer(self, scraper_id:int, performer):
		query = """query ScrapePerformer($scraper_id: ID!, $performer: ScrapedPerformerInput!) {
		   scrapePerformer(scraper_id: $scraper_id, performer: $performer) {
			  ...scrapedPerformer
			}
		  }
		"""
		variables = {
			"scraper_id": scraper_id,
			"performer": {
			"name": performer["name"],
			"gender": None,
			"url": performer["url"],
			"twitter": None,
			"instagram": None,
			"birthdate": None,
			"ethnicity": None,
			"country": None,
			"eye_color": None,
			"height": None,
			"measurements": None,
			"fake_tits": None,
			"career_length": None,
			"tattoos": None,
			"piercings": None,
			"aliases": None,
			"tags": None,
			"image": None,
			"details": None,
			"death_date": None,
			"hair_color": None,
			"weight": None,
		}
		}
		result = self.__callGraphQL(query, variables)
		return result["scrapePerformer"]

	# URL Scrape
	def scrape_scene_url(self, url):
		query = """
			query($url: String!) {
				scrapeSceneURL(url: $url) {
					...scrapedScene
				}
			}
		"""
		variables = { 'url': url }
		result = self.__callGraphQL(query, variables)
		return result['scrapeSceneURL']
	def scrape_movie_url(self, url):
		query = """
			query($url: String!) {
				scrapeMovieURL(url: $url) {
					...scrapedMovie
				}
			}
		"""
		variables = { 'url': url }
		result = self.__callGraphQL(query, variables)

		return result['scrapeMovieURL']
	def scrape_gallery_url(self, url):
		query = """
			query($url: String!) {
				scrapeGalleryURL(url: $url) {
					...scrapedGallery 
				}
			}
		"""
		variables = { 'url': url }
		result = self.__callGraphQL(query, variables)
		return result['scrapeGalleryURL']        
	def scrape_performer_url(self, url):
		query = """
			query($url: String!) {
				scrapePerformerURL(url: $url) {
					...scrapedPerformer
				}
			}
		"""
		variables = { 'url': url }
		result = self.__callGraphQL(query, variables)
		return result['scrapePerformerURL']

	# Stash Box
	def stashbox_scene_scraper(self, scene_ids, stashbox_index:int=0):
		query = """
			query QueryStashBoxScene($input: StashBoxSceneQueryInput!) {
				queryStashBoxScene(input: $input) {
					...scrapedScene
				}
			}
		"""
		variables = {
			"input": {
				"scene_ids": scene_ids,
				"stash_box_index": stashbox_index
			}
		}

		result = self.__callGraphQL(query, variables)

		return result["queryStashBoxScene"]
	def stashbox_submit_scene_fingerprints(self, scene_ids, stashbox_index:int=0):
		query = """
			mutation SubmitStashBoxFingerprints($input: StashBoxFingerprintSubmissionInput!) {
				submitStashBoxFingerprints(input: $input)
			}
		"""
		variables = {
			"input": {
				"scene_ids": scene_ids,
				"stash_box_index": stashbox_index
			}
		}

		result = self.__callGraphQL(query, variables)
		return result['submitStashBoxFingerprints']


	def get_identify_config(self):
		query= """
		query getIdentifyConfig{
			configuration {
				defaults {
					identify {
						options {
							fieldOptions {
								field
								strategy
								createMissing
							}
							setCoverImage
							setOrganized
							includeMalePerformers
						}
					}
				}
			}
		}"""

		result = self.__callGraphQL(query)
		return result['configuration']['defaults']['identify']['options']

	def get_identify_source_config(self, source_identifier):
		query= """
		query getIdentifySourceConfig{
			configuration {
				defaults {
					identify {
						sources {
							source {
								stash_box_endpoint
								scraper_id
							}
							options {
								fieldOptions {
									field
									strategy
									createMissing
								}
								setCoverImage
								setOrganized
								includeMalePerformers
							}
						}
					}
				}
			}
		}"""

		configs = self.__callGraphQL(query)['configuration']['defaults']['identify']['sources']
		for c in configs:
			if c['source']['stash_box_endpoint'] == source_identifier:
				return c['options']
			if c['source']['scraper_id'] == source_identifier:
				return c['options']
		return None

	def stashbox_identify_task(self, scene_ids):
		query = """
			mutation MetadataIdentify($input: IdentifyMetadataInput!) {
  				metadataIdentify(input: $input)
			}
		"""
		variables = {}
		variables["input"] = {
			"options": self.get_identify_config(),
			"sceneIDs": scene_ids,
			"sources": [
				{
					"options": self.get_identify_source_config("https://stashdb.org/graphql"),
					"source": {
						"stash_box_endpoint": "https://stashdb.org/graphql"
					}
				}
			]
		}

		return self.__callGraphQL(query, variables)


	def find_duplacate_scenes(self, distance: PhashDistance=PhashDistance.EXACT):
		query = """
			query FindDuplicateScenes($distance: Int) {
				  findDuplicateScenes(distance: $distance) {
					...SlimSceneData
					__typename
				  }
			}

				fragment SlimSceneData on Scene {
				  id
				  title
				  path
				  phash
				  file {
					size
					duration
					video_codec
					width
					height
					framerate
					bitrate
					__typename
				  }
				  __typename
				}
		"""

		variables = { "distance": distance }
		result = self.__callGraphQL(query, variables)
		return result['findDuplicateScenes']


gql_fragments = {
	"scrapedScene":"""
		fragment scrapedScene on ScrapedScene {
		  title
		  details
		  url
		  date
		  image
		  studio{
			...scrapedStudio
		  }
		  tags{
			...scrapedTag
		  }
		  performers{
			...scrapedPerformer
		  }
		  movies{
			...scrapedMovie
		  }
		  duration
		  __typename
		}
	""",
	"scrapedGallery":"""
		fragment scrapedGallery on ScrapedGallery {
		  title
		  details
		  url
		  date
		  studio{
			...scrapedStudio
		  }
		  tags{ ...scrapedTag }
		  performers{
			...scrapedPerformer
		  }
		  __typename
		}
	""",
	"scrapedPerformer":"""
		fragment scrapedPerformer on ScrapedPerformer {
		  stored_id
		  name
		  gender
		  url
		  twitter
		  instagram
		  birthdate
		  ethnicity
		  country
		  eye_color
		  height
		  measurements
		  fake_tits
		  career_length
		  tattoos
		  piercings
		  aliases
		  tags { ...scrapedTag }
		  images
		  details
		  death_date
		  hair_color
		  weight
		  remote_site_id
		  __typename
		}
	""",
	"scrapedTag": """
		fragment scrapedTag on ScrapedTag {
			stored_id
			name
			__typename
		}
	""",
	"scrapedMovie": """
		fragment scrapedMovie on ScrapedMovie {
			stored_id
			name
			aliases
			duration
			date
			rating
			director
			synopsis
			url
			studio {
				...scrapedStudio
			}
			front_image
			back_image
			__typename
		}
	""",
	"scrapedStudio": """
		fragment scrapedStudio on ScrapedStudio {
			stored_id
			name
			url
			remote_site_id
			__typename
		}
	""",
	"stashScene":"""
		fragment stashScene on Scene {
		  id
		  checksum
		  oshash
		  phash
		  title
		  details
		  url
		  date
		  rating
		  organized
		  o_counter
		  path
		  tags {
			...stashTag
		  }
		  file {
			size
			duration
			video_codec
			audio_codec
			width
			height
			framerate
			bitrate
			__typename
		  }
		  galleries {
			id
			checksum
			path
			title
			url
			date
			details
			rating
			organized
			studio {
			  id
			  name
			  url
			  __typename
			}
			image_count
			tags {
			  ...stashTag
			}
		  }
		  performers {
			...stashPerformer
		  }
		  scene_markers { 
			...stashSceneMarker
		  }
		  studio{
			...stashStudio
		  }
		  stash_ids{
			endpoint
			stash_id
			__typename
		  }
		  created_at
		  updated_at
		  __typename
		}
	""",
	"stashGallery":"""
		fragment stashGallery on Gallery {
			id
			checksum
			path
			title
			date
			url
			details
			rating
			organized
			image_count
			cover {
				paths {
					thumbnail
				}
			}
			studio {
				id
				name
				__typename
			}
			tags {
				...stashTag
			}
			performers {
				...stashPerformer
			}
			scenes {
				id
				title
				__typename
			}
			__typename
		}
	""",
	"stashPerformer":"""
		fragment stashPerformer on Performer {
			id
			checksum
			name
			url
			gender
			twitter
			instagram
			birthdate
			ethnicity
			country
			eye_color
			height
			measurements
			fake_tits
			career_length
			tattoos
			piercings
			aliases
			favorite
			tags { ...stashTag }
			image_path
			scene_count
			image_count
			gallery_count
			stash_ids {
				stash_id
				endpoint
				__typename
			}
			rating
			details
			death_date
			hair_color
			weight
			__typename
		}
	""",
	"stashSceneMarker":"""
		fragment stashSceneMarker on SceneMarker {
			id
			scene { id }
			title
			seconds
			primary_tag { ...stashTag }
			tags { ...stashTag }
			__typename
		}
	""",
	"stashMovie":"""
		fragment stashMovie on Movie {
			id
			name
			aliases
			duration
			date
			rating
			studio { id }
			director
			synopsis
			url
			created_at
			updated_at
			scene_count
			__typename
		}
	""",
	"stashTag":"""
		fragment stashTag on Tag {
			id
			name
			aliases
			image_path
			scene_count
			__typename
		}
	""",
	"stashStudio":"""
		fragment stashStudio on Studio {
			id
			name
			url
			aliases
			rating
			details
			stash_ids{
				endpoint
				stash_id
				__typename
			}
			parent_studio {
				id
				name
			}
			__typename
		}
	"""
}