import json
import sys
import time
import datetime
import traceback
from urllib.parse import urlparse
from types import SimpleNamespace


import log
from stash_interface import StashInterface

config = SimpleNamespace()

############################################################################
############################# CONFIG HERE ##################################
############################################################################

# Create missing performers/tags/studios
# Default: False (Prevent Stash from getting flooded with weird values)
config.create_missing_performers = False
config.create_missing_tags = True
config.create_missing_studios = True
config.create_missing_movies = True

# url scrape config
config.bulk_url_scrape_scenes = True
config.bulk_url_scrape_galleries = True
config.bulk_url_scrape_movies = True
config.bulk_url_scrape_performers = False

# fragment scrape config
config.fragment_scrape_scenes = True
config.fragment_scrape_galleries = True
config.fragment_scrape_movies = True
config.fragment_scrape_performers = False

# stashbox scrape config
config.stashbox_target = "stashdb.org"

# Delay between web requests
# Default: 5
config.delay = 5

# Name of the tag, that will be used for selecting scenes for bulk url scraping
config.bulk_url_control_tag = "blk_scrape_url"

# stash box control tag
config.bulk_stash_box_control_tag = "blk_scrape_stashbox"

# Prefix of all fragment scraper tags
config.scrape_with_prefix = "blk_scrape_"


############################################################################
############################################################################


def main():
	json_input = json.loads(sys.stdin.read())

	output = {}
	run(json_input, output)

	out = json.dumps(output)
	print(out + "\n")

def run(json_input, output):
	mode_arg = json_input['args']['mode']

	try:
		client = StashInterface(json_input["server_connection"])
		scraper = ScrapeController(client)

		if mode_arg == "create":
			scraper.add_tags()
		if mode_arg == "remove":
			scraper.remove_tags()

		if mode_arg == "url_scrape":
			scraper.bulk_url_scrape()
		if mode_arg == "fragment_scrape":
			scraper.bulk_fragment_scrape()
		if mode_arg == "stashbox_scrape":
			scraper.bulk_stashbox_scrape()


	except Exception:
		raise

	output["output"] = "ok"


class ScrapeController:

	def __init__(self, client, create_missing_performers=False, create_missing_tags=False, create_missing_studios=False, create_missing_movies=False, delay=5):
		try:
			self.delay = int(config.delay)

			self.last_wait_time = -1
		except AttributeError as e:
			log.warning(e)
			log.warning("Using defaults for missing config values")
		except ValueError as e:
			log.warning(e)
			log.warning("Using defaults for wrong values")

		self.client = client

		self.client.reload_scrapers()

		log.info('######## Bulk Scraper ########')
		log.info(f'create_missing_performers: {config.create_missing_performers}')
		log.info(f'create_missing_tags: {config.create_missing_tags}')
		log.info(f'create_missing_studios: {config.create_missing_studios}')
		log.info(f'create_missing_movies: {config.create_missing_movies}')
		log.info(f'delay: {self.delay}')
		log.info('##############################')

	# Waits the remaining time between the last timestamp and the configured delay in seconds
	def wait(self):
		if self.delay:
			time_last = int(self.last_wait_time)
			time_now = int(time.time())
			if time_now > time_last:
				if time_now - time_last < self.delay:
					time.sleep(self.delay - (time_now - time_last) + 1)
			self.last_wait_time = time.time()

	def add_tags(self):
		tags = self.list_all_control_tags()
		for tag_name in tags:
			tag_id = self.client.find_tag_id(tag_name)
			if tag_id == None:
				tag_id = self.client.create_tag({'name':tag_name})
				log.info(f"adding tag {tag_name}")
			else:
				log.debug(f"tag exists, {tag_name}")
	def remove_tags(self):
		tags = self.list_all_control_tags()
		for tag_name in tags:
			tag_id = self.client.find_tag_id(tag_name)
			if tag_id == None:
				log.debug("Tag does not exist. Nothing to remove")
				continue
			log.info(f"Destroying tag {tag_name}")
			self.client.destroy_tag(tag_id)

	def bulk_url_scrape(self):

		log.info("Performing Bulk URL Scrape")
		log.info("Progress bar will reset for each item type (scene, movie, ect.)")

		# Scrape Everything enabled in config
		tag_id = self.client.find_tag_id(config.bulk_url_control_tag)
		if tag_id is None:
			sys.exit(f'Tag "{config.bulk_url_control_tag}" does not exist. Please create it via the "Create scrape tags" task')

		if config.bulk_url_scrape_scenes:
			scenes = self.client.find_scenes(f={
				"tags": {
					"value": [tag_id],
					"depth": 0,
					"modifier": "INCLUDES"
				},
				"url": {
					"value": "",
					"modifier": "NOT_NULL"
				}
			})

			log.info(f'Found {len(scenes)} scenes with {config.bulk_url_control_tag} tag')
			count = self.__scrape_scenes_with_url(scenes)
			log.info(f'Scraped data for {count} scenes')
			log.info('##############################')

		if config.bulk_url_scrape_galleries:
			galleries = self.client.find_galleries(f={
				"tags": {
					"value": [tag_id],
					"depth": 0,
					"modifier": "INCLUDES"
				},
				"url": {
					"value": "",
					"modifier": "NOT_NULL"
				}
			})

			log.info(f'Found {len(galleries)} galleries with {config.bulk_url_control_tag} tag')
			count = self.__scrape_galleries_with_url(galleries)
			log.info(f'Scraped data for {count} galleries')
			log.info('##############################')

		if config.bulk_url_scrape_performers:
			performers = self.client.find_performers(f={
				"tags": {
					"value": [tag_id],
					"depth": 0,
					"modifier": "INCLUDES"
				},
				"url": {
					"value": "",
					"modifier": "NOT_NULL"
				}
			})

			log.info(f'Found {len(performers)} performers with {config.bulk_url_control_tag} tag')
			count = self.__scrape_performers_with_url(performers)
			log.info(f'Scraped data for {count} performers')
			log.info('##############################')

		if config.bulk_url_scrape_movies:
			movies = self.client.find_movies(f={
				"is_missing": "front_image",
				"url": {
					"value": "",
					"modifier": "NOT_NULL"
				}
			})
			log.info(f'Found {len(movies)} movies with URLs')
			count = self.__scrape_movies_with_url(movies)
			log.info(f'Scraped data for {count} movies')



		return None
	def bulk_fragment_scrape(self):
		# Scrape Everything enabled in config

		for scraper_id, types in self.list_all_fragment_tags().items():

			if config.bulk_url_scrape_scenes:
				if types.get('SCENE'):
					tag_id = self.client.find_tag_id( types.get('SCENE') )
					if tag_id:
						scenes = self.client.find_scenes(f={
							"tags": {
								"value": [tag_id],
								"depth": 0,
								"modifier": "INCLUDES"
							}
						})
						self.__scrape_scenes_with_fragment(scenes, scraper_id)

			if config.bulk_url_scrape_galleries:
				if types.get('GALLERY'):
					tag_id = self.client.find_tag_id( types.get('GALLERY') )
					if tag_id:
						galleries = self.client.find_galleries(f={
							"tags": {
								"value": [tag_id],
								"depth": 0,
								"modifier": "INCLUDES"
							}
						})
						self.__scrape_galleries_with_fragment(galleries, scraper_id)
					
			if config.bulk_url_scrape_galleries:
				if types.get('PERFORMER'):
					tag_id = self.client.find_tag_id( types.get('PERFORMER') )
					if tag_id:
						performers = self.client.find_performers(f={
							"tags": {
								"value": [tag_id],
								"depth": 0,
								"modifier": "INCLUDES"
							}
						})
						self.__scrape_performers_with_fragment(performers, scraper_id)

		return None
	def bulk_stashbox_scrape(self):

		submit_fingerprints = True

		stashbox = None
		for i, sbox in enumerate(self.client.list_stashboxes()):
			if config.stashbox_target in sbox.endpoint:
				stashbox = sbox
				stashbox.index = i

		if not stashbox:
			log.error(f'Could not find a stash-box config for {config.stashbox_target}')
			return None

		tag_id = self.client.find_tag_id( config.bulk_stash_box_control_tag )
		scenes = self.client.find_scenes(f={
			"tags": {
				"value": [tag_id],
				"depth": 0,
				"modifier": "INCLUDES"
			}
		})

		log.info(f'Scraping {len(scenes)} items from stashbox')

		scene_ids = [i.get('id') for i in scenes if i.get('id')]
		scraped_data  = self.client.stashbox_scene_scraper(scene_ids, stashbox_index=stashbox.index)

		log.info(f'found {len(scraped_data)} results from stashbox')

		updated_scene_ids = self.__update_scenes_with_stashbox_data(scenes, scraped_data, stashbox)

		log.info(f'Scraped {len(updated_scene_ids)} scenes from stashbox')

		if len(updated_scene_ids) > 0 and submit_fingerprints:
			log.info(f'Submitting scene fingerprints to stashbox')
			success = self.client.stashbox_submit_scene_fingerprints(updated_scene_ids, stashbox_index=stashbox.index)
			if success:
				log.info(f'Submission Successful')
			else:
				log.info(f'Failed to submit fingerprint')

		return None

	def list_all_fragment_tags(self):
		fragment_tags = {}

		if config.fragment_scrape_scenes:
			for s in self.client.list_scene_scrapers('FRAGMENT'):
				if s in fragment_tags:
					fragment_tags[s]['SCENE'] = f'{config.scrape_with_prefix}{s}'
				else:
					fragment_tags[s] = {'SCENE': f'{config.scrape_with_prefix}{s}'}

		if config.fragment_scrape_galleries:
			for s in self.client.list_gallery_scrapers('FRAGMENT'):
				if s in fragment_tags:
					fragment_tags[s]['GALLERY'] = f'{config.scrape_with_prefix}{s}'
				else:
					fragment_tags[s] = {'GALLERY': f'{config.scrape_with_prefix}{s}'}

		if config.fragment_scrape_movies:
			for s in self.client.list_movie_scrapers('FRAGMENT'):
				if s in fragment_tags:
					fragment_tags[s]['MOVIE'] = f'{config.scrape_with_prefix}{s}'
				else:
					fragment_tags[s] = {'MOVIE': f'{config.scrape_with_prefix}{s}'}

		if config.fragment_scrape_performers:
			for s in self.client.list_performer_scrapers('FRAGMENT'):
				if s in fragment_tags:
					fragment_tags[s]['PERFORMER'] = f'{config.scrape_with_prefix}{s}'
				else:
					fragment_tags[s] = {'PERFORMER': f'{config.scrape_with_prefix}{s}'}

		return fragment_tags
	def list_all_control_tags(self):
		control_tags = [ config.bulk_url_control_tag, config.bulk_stash_box_control_tag ]
		for supported_types in self.list_all_fragment_tags().values():
			control_tags.extend( supported_types.values() )
		return control_tags
	def get_control_tag_ids(self):
		control_ids = list()
		for tag_name in self.list_all_control_tags():
			tag_id = self.client.find_tag_id(tag_name)
			if tag_id == None:
				continue
			control_ids.append(tag_id)
		return control_ids

	def __scrape_with_fragment(self, scrape_type, scraper_id, items, __scrape, __update):
		last_request = -1
		if self.delay > 0:
			# Initialize last request with current time + delay time
			last_request = time.time() + self.delay

		# Number of scraped items
		count = 0
		total = len(items)

		log.info(f'Scraping {total} {scrape_type} with scraper: {scraper_id}')

		for i, item in enumerate(items):
			# Update status bar
			log.progress(i/total)

			self.wait()
			scraped_data = __scrape(scraper_id, item)

			if scraped_data is None:
				log.info(f"Scraper ({scraper_id}) did not return a result for {scrape_type} ({item.get('id')}) ")
				continue

			# No data has been found for this scene
			if not any(scraped_data.values()):
				log.info(f"Could not get data for {scrape_type} {item.get('id')}")
				continue

			try:
				__update(item, scraped_data)
				log.debug(f"Updated data for {scrape_type} {item.get('id')}")
				count += 1
			except Exception as e:
				log.error(traceback.format_exc(e.__traceback__))
				log.error(f"Fragment Scrape could not update {scrape_type} {item.get('id')}")
				log.error(str(e))

		return count

	def __scrape_with_url(self, scrape_type, items, __scrape, __update):
		last_request = -1
		if self.delay > 0:
			# Initialize last request with current time + delay time
			last_request = time.time() + self.delay

		working_scrapers = set()
		missing_scrapers = set()

		# Number of items to scrape
		count = 0
		total = len(items)

		# Scrape if url not in missing_scrapers
		for i, item in enumerate(items):
			# Update status bar
			log.progress(i/total)

			if item.get('url') is None or item.get('url') == "":
				log.info(f"{scrape_type} {item.get('id')} is missing url")
				continue
			netloc = urlparse(item.get("url")).netloc
			if netloc in missing_scrapers and netloc not in working_scrapers:
				continue
			
			self.wait()
			log.info(f"Scraping URL for {scrape_type} {item.get('id')}")

			scraped_data = __scrape(item.get('url'))

			# If result is null, add url to missing_scrapers
			if scraped_data is None:
				log.warning(f"Missing scraper for {urlparse(item.get('url')).netloc}")
				missing_scrapers.add(netloc)
				continue
			else:
				working_scrapers.add(netloc)
			# No data has been found for this item
			if not any(scraped_data.values()):
				log.info(f"Could not get data for {scrape_type} {item.get('id')}")
				continue

			try:
				__update(item, scraped_data)
				log.debug(f"Updated data for {scrape_type} {item.get('id')}")
				count += 1
			except Exception as e:
				log.error(traceback.format_exc(e.__traceback__))
				log.error(f"URL Scrape could not update {scrape_type} {item.get('id')}")
				log.error(str(e))

		return count

	def __scrape_scenes_with_fragment(self, scenes, scraper_id):
		return self.__scrape_with_fragment(
			"scenes",
			scraper_id,
			scenes,
			self.client.run_scene_scraper,
			self.__update_scene_with_scrape_data
		)
	def __scrape_scenes_with_url(self, scenes):
		return self.__scrape_with_url(
			"scene",
			scenes,
			self.client.scrape_scene_url,
			self.__update_scene_with_scrape_data
		)
	def __update_scene_with_scrape_data(self, scene, scraped_data):
		
		update_data = {
			'id': scene.get('id')
		}

		common_attrabutes = ['url','title','details','date']
		for c_attr in common_attrabutes:
			if scraped_data.get(c_attr):
				update_data[c_attr] = scraped_data.get(c_attr)

		if scraped_data.get('image'):
			update_data['cover_image'] = scraped_data.get('image')

		if scraped_data.tags:
			tag_ids = list()
			for tag in scraped_data.tags:
				if tag.stored_id:
					tag_ids.append(tag.stored_id)
				elif config.create_missing_tags and tag.name:
					tag_name = caps_string(tag.name)
					log.info(f'Create missing tag: {tag_name}')
					tag_ids.append(self.client.create_tag({'name':tag_name}))
			if len(tag_ids) > 0:
				update_data['tag_ids'] = tag_ids

		if scraped_data.performers:
			performer_ids = list()
			for performer in scraped_data.performers:
				if performer.stored_id:
					performer_ids.append(performer.stored_id)
				elif performer.name:
					# scraper could not match performer, try re-matching or create if enabled
					performer.name = performer.name.strip()
					performer.name = caps_string(performer.name)

					perf_in = {'name': performer.name }
					if performer.url:
						perf_in['url'] = performer.url 
						
					stash_perf = self.client.find_performer(perf_in, create_missing=config.create_missing_performers)
					if stash_perf and stash_perf.get("id"):
						performer_ids.append(stash_perf.id)
					
			if len(performer_ids) > 0:
				update_data['performer_ids'] = performer_ids

		if scraped_data.studio:
			if scraped_data.studio.stored_id:
				update_data['studio_id'] = scraped_data.studio.stored_id
			elif config.create_missing_studios:
				studio = {
					"name": caps_string(scraped_data.studio.name),
					"url": '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(scraped_data.studio.url))
				}
				log.info(f'Creating missing studio {studio.get("name")}')
				update_data['studio_id'] = self.client.create_studio(studio)

		if scraped_data.movies:
			movie_ids = list()
			for movie in scraped_data.movies:
				if movie.stored_id:
					movie_ids.append( {'movie_id':movie.stored_id, 'scene_index':None} )
				elif config.create_missing_movies and movie.name:
					log.info(f'Create missing movie: "{movie.name}"')

					movie_data = {
						'name': movie.name
					}
					for attr in ['url', 'synopsis', 'date', 'aliases']:
						if movie[attr]:
							movie_data[attr] = movie[attr]

					try:
						movie_ids.append( {'movie_id':self.client.create_movie(movie_data), 'scene_index':None} )
					except Exception as e:
						log.error('update error')

			if len(movie_ids) > 0:
				update_data['movies'] = movie_ids

		if scraped_data.get('stash_ids'):
			if scene.get('stash_ids'):
				update_data['stash_ids'] = scene.get('stash_ids').extend(scraped_data.get('stash_ids'))
			else:
				update_data['stash_ids'] = scraped_data.get('stash_ids')

		log.debug('mapped scrape data to scene fields')

		# Only accept base64 images
		if update_data.get('cover_image') and not update_data.get('cover_image').startswith("data:image"):
			del update_data['cover_image']

		scene_tag_ids = [t.id for t in scene.tags]
		update_data['tag_ids'] = self.__merge_tags(scene_tag_ids, update_data.get('tag_ids'))

		self.client.update_scene(update_data)

	def __update_scenes_with_stashbox_data(self, scenes, scraped_data, stashbox):

		# will match durations -/+ this value
		allowed_durr_diff = 25

		# % of matching fingerprints required to match
		durr_match_percnt = 0.9

		# minimum number of fingerprints a scene must have to match
		min_fingerprint_count = 5

		scene_update_ids = []

		total = len(scenes)

		for i, scene in enumerate(scenes):

			# Update status bar
			log.progress(i/total)

			matches = []

			for scene_data in scraped_data:

				id_match = SimpleNamespace()

				id_match.hash = None
				id_match.oshash = False
				id_match.phash = False
				id_match.checksum = False
				id_match.duration = 0
				id_match.fingerprint_count = len(scene_data.get('fingerprints'))
				id_match.data = scene_data

				for fingerprint in scene_data.get('fingerprints'):
					
					if scene.get('checksum') == fingerprint.get('checksum'):
						id_match.checksum = True
						id_match.hash = "checksum"
					if scene.get('phash') == fingerprint.get('hash'):
						id_match.phash = True
						id_match.hash = "phash"
					if scene.get('oshash') == fingerprint.get('hash'):
						id_match.oshash = True
						id_match.hash = "oshash"

					if not scene.get('file').get('duration') or not fingerprint.get('duration'):
						continue

					durr_diff = abs(scene.get('file').get('duration') - fingerprint.get('duration'))
					if durr_diff <= allowed_durr_diff:
						id_match.duration += 1

				if (id_match.oshash or id_match.phash or id_match.checksum) and (id_match.duration / id_match.fingerprint_count >= durr_match_percnt) and (id_match.fingerprint_count >= min_fingerprint_count):
					matches.append(id_match)


			if len(matches) <= 0:
				log.info(f"FAILED to find match for scene id:{scene['id']}")
				continue

			if len(matches) > 1:
				log.info(f"Multuple result for ({scene.get('id')}) skipping")
				continue

			m = matches[0]

			log.info(f'MATCHED: UID:{m.hash} DUR:{m.duration}/{m.fingerprint_count}')

			if m.data.remote_site_id:
				m.data['stash_ids'] = [{
					'endpoint': stashbox.endpoint,
					'stash_id': m.data.remote_site_id
				}]

			if m.data.performers:
				for p in m.data.performers:
					p.stash_ids = [{
						'endpoint': stashbox.endpoint,
						'stash_id': p.remote_site_id
					}]


			try:
				self.__update_scene_with_scrape_data(scene, m.data)
				scene_update_ids.append(scene.get('id'))
			except Exception as e:
				log.error(str(e))

		return scene_update_ids

	def __scrape_galleries_with_fragment(self, galleries, scraper_id):
		return self.__scrape_with_fragment(
			"galleries",
			scraper_id,
			galleries,
			self.client.run_gallery_scraper,
			self.__update_gallery_with_scrape_data
		)
	def __scrape_galleries_with_url(self, galleries):
		return self.__scrape_with_url(
			"gallery",
			galleries,
			self.client.scrape_gallery_url,
			self.__update_gallery_with_scrape_data
		)
	def __update_gallery_with_scrape_data(self, gallery, scraped):
		# Expecting to cast ScrapedGallery to GalleryUpdateInput
		# NOTE
		# 	ScrapedGallery.studio: {scrapedSceneStudio} => GalleryUpdateInput.scene_ids: [ID!]
		#   ScrapedGallery.tags: {ScrapedSceneTag} => GalleryUpdateInput.tag_ids: [ID!]
		#   ScrapedGallery.performers: {scrapedScenePerformer} => GalleryUpdateInput.performer_ids: [ID!]

		update_data = {
			'id': gallery.get('id')
		}

		common_attrabutes = [
			'title',
			'details',
			'url',
			'date'
		]
		for attr in common_attrabutes:
			if scraped[attr]:
				update_data[attr] = scraped[attr]

		if scraped.tags:
			tag_ids = list()
			for tag in scraped.tags:
				if tag.stored_id:
					tag_ids.append(tag.stored_id)
				elif config.create_missing_tags and tag.name:
					tag_name = caps_string(tag.name)
					log.info(f'Create missing tag: {tag_name}')
					tag_ids.append(self.client.create_tag({'name':tag_name}))
			if len(tag_ids) > 0:
				update_data['tag_ids'] = tag_ids

		if scraped.performers:
			performer_ids = list()
			for performer in scraped.performers:
				if performer.stored_id:
					performer_ids.append(performer.stored_id)
				elif performer.name:
					# scraper could not match performer, try re-matching or create if enabled
					performer.name = performer.name.strip()
					performer.name = caps_string(performer.name)

					perf_in = {'name': performer.name }
					if performer.url:
						perf_in['url'] = performer.url 
						
					stash_perf = self.client.find_performer(perf_in, create_missing=config.create_missing_performers)
					if stash_perf:
						performer_ids.append(stash_perf.id)

			if len(performer_ids) > 0:
				update_data['performer_ids'] = performer_ids

		if scraped.studio:
			if scraped.studio.stored_id:
				update_data['studio_id'] = scraped.studio.stored_id
			elif config.create_missing_studios:
				studio = {
					'name': caps_string(scraped.studio.name),
					'url': '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(scraped.studio.url))
				}
				log.info(f'Creating missing studio {studio.get("name")}')
				update_data['studio_id'] = self.client.create_studio(studio)

		gallery_tag_ids = [t.id for t in gallery.tags]
		update_data['tag_ids'] = self.__merge_tags(gallery_tag_ids, update_data.get('tag_ids'))

		self.client.update_gallery(update_data)

	def __scrape_movies_with_url(self, movies):
		return self.__scrape_with_url(
			"movie",
			movies,
			self.client.scrape_movie_url,
			self.__update_movie_with_scrape_data
		)
	def __update_movie_with_scrape_data(self, movie, scraped_data):

		# Expecting to cast ScrapedMovie to MovieUpdateInput
		# NOTE
		# 	ScrapedMovie.duration: String (HH:MM:SS) => MovieUpdateInput.duration: Int (Total Seconds)
		# 	ScrapedMovie.studio: {ScrapedMovieStudio} => MovieUpdateInput.studio_id: ID

		update_data = {
			'id': movie.id
		}
		common_attrabutes = [
			'name',
			'aliases',
			'date',
			'rating',
			'director',
			'url',
			'synopsis',
			'front_image',
			'back_image'
		]
		for attr in common_attrabutes:
			if scraped_data[attr]:
				update_data[attr] = scraped_data[attr]

		# here because durration value from scraped movie is string where update preferrs an int need to cast to and int (seconds)
		if scraped_data.duration:
			if scraped_data.duration.count(':') == 0:
				scraped_data.duration = f'00:00:{scraped_data.duration}'
			if scraped_data.duration.count(':') == 1:
				scraped_data.duration = f'00:{scraped_data.duration}'
			h,m,s = scraped_data.duration.split(':')
			durr = datetime.timedelta(hours=int(h),minutes=int(m),seconds=int(s)).total_seconds()
			update_data['duration'] = int(durr)

		if scraped_data.studio:
			update_data['studio_id'] = scraped_data.studio.id

		self.client.update_movie(update_data)

	def __scrape_performers_with_fragment(self, performers):
		return self.__scrape_with_fragment(
			"performer",
			performers,
			self.client.run_performer_scraper,
			self.__update_performer_with_scrape_data
		)
	def __scrape_performers_with_url(self, performers):
		return self.__scrape_with_url(
			"performer",
			performers,
			self.client.scrape_performer_url,
			self.__update_performer_with_scrape_data
		)
	def __update_performer_with_scrape_data(self, performer, scraped):
		# Expecting to cast ScrapedPerformer to PerformerUpdateInput
		# NOTE
		# 	ScrapedPerformer.gender: String => PerformerUpdateInput.gender: GenderEnum
		#   ScrapedPerformer.weight: String (kg?) => PerformerUpdateInput.weight: Int (kg)

		update_data = {
			'id': performer.id
		}

		common_attrabutes = [
			'name',
			'url',
			'birthdate',
			'ethnicity',
			'country',
			'eye_color',
			'height',
			'measurements',
			'fake_tits',
			'career_length',
			'tattoos',
			'piercings',
			'aliases',
			'twitter',
			'instagram',
			'image',
			'details',
			'death_date',
			'hair_color'
		]
		for attr in common_attrabutes:
			if scraped[attr]:
				update_data[attr] = scraped[attr]

		# cast String to Int, this assumes both values are the same unit and are just diffrent types
		if scraped.weight:
			update_data['weight'] = int(scraped.weight)

		GENDER_ENUM = ["MALE","FEMALE","TRANSGENDER_MALE","TRANSGENDER_FEMALE", "INTERSEX", "NON_BINARY"]

		if scraped.gender:
			gender = scraped.gender.replace(' ', '_').upper()
			if gender in GENDER_ENUM:
				update_data['gender'] = gender
			else:
				log.warning(f'Could not map {scraped.gender} to a GenderEnum for performer {performer.id}')

		self.client.update_performer(update_data)



	def __merge_tags(self, old_tag_ids, new_tag_ids):
		merged_tags = set()
		ctrl_tag_ids = self.get_control_tag_ids()
		merged_tags.update([t for t in old_tag_ids if t not in ctrl_tag_ids])
		if new_tag_ids:
			merged_tags.update(new_tag_ids)
		return list(merged_tags)

# Capitalize each word in a string
def caps_string(string, delim=" "):
	return delim.join(x.capitalize() for x in string.split(delim))


if __name__ == '__main__':
	main()