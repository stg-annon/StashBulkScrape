import sys, time, json, datetime
from urllib.parse import urlparse
from types import SimpleNamespace

import config
import utils.tools as tools

import stashapi.log as log
from stashapi.stashapp import StashInterface
from stashapi.scrape_parser import ScrapeParser
from stashapi.types import StashItem, ScrapeType

class ScrapeController:

	def __init__(self, stash:StashInterface):
		try:
			self.delay = float(config.EXTERNAL_WEB_REQUEST_DELAY)
			self.last_wait_time = datetime.datetime.now()
		except AttributeError as e:
			log.warning(e)
			log.warning("Using defaults for missing config values")
		except ValueError as e:
			log.warning(e)
			log.warning("Using defaults for wrong values")

		self.stash = stash
		self.parse = ScrapeParser(
			stash,
			logger=log,
			create_missing_tags=config.create_missing_tags,
			create_missing_studios=config.create_missing_studios
		)

		self.stash.reload_scrapers()

		log.debug('############ Bulk Scraper ############')
		log.debug(f'create_missing_performers: {config.create_missing_performers}')
		log.debug(f'create_missing_tags: {config.create_missing_tags}')
		log.debug(f'create_missing_studios: {config.create_missing_studios}')
		log.debug(f'create_missing_movies: {config.create_missing_movies}')
		log.debug(f'delay: {self.delay}')
		log.debug('######################################')
		
	def wait(self):
		if (datetime.datetime.now()-self.last_wait_time) < datetime.timedelta(seconds=self.delay):
			time.sleep(self.delay)
			self.last_wait_time = datetime.datetime.now()

	# adds control tags to stash
	def add_tags(self):
		tags = self.list_all_control_tags()
		for tag_name in tags:
			tag_id = self.stash.find_tag_id(tag_name)
			if tag_id == None:
				tag_id = self.stash.create_tag({'name':tag_name})
				log.info(f"adding tag {tag_name}")
			else:
				log.debug(f"tag exists, {tag_name}")

	# Removes control tags from stash
	def remove_tags(self):
		tags = self.list_all_control_tags()
		for tag_name in tags:
			tag = self.stash.find_tag(tag_name)
			if tag == None:
				log.debug("Tag does not exist. Nothing to remove")
				continue
			log.info(f'Destroying tag {tag["name"]}')
			self.stash.destroy_tag(tag["id"])
	
	# Scrapes Items enabled in config by url scraper
	def bulk_url_scrape(self):
		log.info("Performing Bulk URL Scrape")
		log.info("Progress bar will reset for each item type (scene, movie, ect.)")

		# Scrape Everything enabled in config
		tag = self.stash.find_tag(config.BULK_URL_CONTROL_TAG)
		if tag is None:
			sys.exit(f'Tag "{config.BULK_URL_CONTROL_TAG}" does not exist. Please create it via the "Create scrape tags" task')
		tag_id = tag["id"]

		if StashItem.SCENE in config.BULK_URL:
			scenes = self.stash.find_scenes(f={
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

			log.info(f'Found {len(scenes)} scenes with {config.BULK_URL_CONTROL_TAG} tag')
			count = self.__scrape_scenes_with_url(scenes)
			log.info(f'Scraped data for {count} scenes')
			log.info('##############################')

		if StashItem.GALLERY in config.BULK_URL:
			galleries = self.stash.find_galleries(f={
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

			log.info(f'Found {len(galleries)} galleries with {config.BULK_URL_CONTROL_TAG} tag')
			count = self.__scrape_galleries_with_url(galleries)
			log.info(f'Scraped data for {count} galleries')
			log.info('##############################')

		if StashItem.PERFORMER in config.BULK_URL:
			performers = self.stash.find_performers(f={
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

			log.info(f'Found {len(performers)} performers with {config.BULK_URL_CONTROL_TAG} tag')
			count = self.__scrape_performers_with_url(performers)
			log.info(f'Scraped data for {count} performers')
			log.info('##############################')

		if StashItem.MOVIE in config.BULK_URL:
			movies = self.stash.find_movies(f={
				"is_missing": "front_image",
				"url": {
					"value": "",
					"modifier": "NOT_NULL"
				}
			})
			log.info(f'Found {len(movies)} movies with URLs')
			count = self.__scrape_movies_with_url(movies)
			log.info(f'Scraped data for {count} movies')
	# Scrapes Items enabled in config by fragment scraper
	def bulk_fragment_scrape(self):
		# Scrape Everything enabled in config
		for tag_name, types_tuple in self.list_all_fragment_tags().items():
			tag = self.stash.find_tag(tag_name)
			if not tag:
				log.warning(f"could not find tag '{tag_name}'")
				continue
			scraper_id, stash_items = types_tuple
			if stash_items.get(StashItem.SCENE):
				scenes = self.stash.find_scenes(f={
					"tags": {
						"value": [tag["id"]],
						"depth": 0,
						"modifier": "INCLUDES"
					}
				}, fragment="id")
				self.__scrape_scenes_with_fragment(scenes, scraper_id)

			if stash_items.get(StashItem.GALLERY):
				galleries = self.stash.find_galleries(f={
					"tags": {
						"value": [tag["id"]],
						"depth": 0,
						"modifier": "INCLUDES"
					}
				}, fragment="id")
				self.__scrape_galleries_with_fragment(galleries, scraper_id)
					
			if stash_items.get(StashItem.PERFORMER):
				performers = self.stash.find_performers(f={
					"tags": {
						"value": [tag["id"]],
						"depth": 0,
						"modifier": "INCLUDES"
					}
				}, fragment="id")
				self.__scrape_performers_with_fragment(performers, scraper_id)

		return None
	def bulk_stashbox_scrape(self):
		stashbox = None
		for i, sbox in enumerate(self.stash.list_stashboxes()):
			if config.stashbox_target in sbox.endpoint:
				stashbox = sbox
				stashbox.index = i

		if not stashbox:
			log.error(f'Could not find a stash-box config for {config.stashbox_target}')
			return None

		tag_id = self.stash.find_tag_id( config.BULK_STASHBOX_CONTROL_TAG )
		scenes = self.stash.find_scenes(f={
			"tags": {
				"value": [tag_id],
				"depth": 0,
				"modifier": "INCLUDES"
			}
		})

		log.info(f'Scraping {len(scenes)} items from stashbox')

		scene_ids = [s['id'] for s in scenes if s.get('id')]
		scraped_data  = self.stash.stashbox_scene_scraper(scene_ids, stashbox_index=stashbox.index)

		log.info(f'found {len(scraped_data)} results from stashbox')

		updated_scene_ids = self.__update_scenes_with_stashbox_data(scenes, scraped_data, stashbox)

		log.info(f'Scraped {len(updated_scene_ids)} scenes from stashbox')

		if len(updated_scene_ids) > 0 and config.stashbox_submit_fingerprints:
			log.info(f'Submitting scene fingerprints to stashbox')
			success = self.stash.stashbox_submit_scene_fingerprints(updated_scene_ids, stashbox_index=stashbox.index)
			if success:
				log.info(f'Submission Successful')
			else:
				log.info(f'Failed to submit fingerprint')

		return None

	def list_all_fragment_tags(self):
		fragment_tags = {}
		for s in self.stash.list_scrapers(config.FRAGMENT_SCRAPE):
			tag_id = f'{config.SCRAPE_WITH_PREFIX}{s["id"]}'
			for content_type in config.FRAGMENT_SCRAPE:
				type_spec = s[content_type.value.lower()]
				if type_spec and ScrapeType.FRAGMENT.value in type_spec["supported_scrapes"]:
					if tag_id in fragment_tags:
						fragment_tags[tag_id][1].append(content_type)
					else:
						fragment_tags[tag_id] = (s["id"], [content_type])
		return fragment_tags
	def list_all_control_tags(self):
		control_tags = [ config.BULK_URL_CONTROL_TAG, config.BULK_STASHBOX_CONTROL_TAG ]
		control_tags.extend(list(self.list_all_fragment_tags().keys()))
		return control_tags
	def get_control_tag_ids(self):
		control_ids = list()
		for tag_name in self.list_all_control_tags():
			tag_id = self.stash.find_tag_id(tag_name)
			if tag_id == None:
				continue
			control_ids.append(tag_id)
		return control_ids

	def __scrape_with_fragment(self, scrape_type, scraper_id, items, __scrape, __update):
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
			if not any(scraped_data.to_dict().values()):
				log.info(f"Could not get data for {scrape_type} {item.get('id')}")
				continue

			try:
				__update(item, scraped_data)
				log.debug(f"Updated data for {scrape_type} {item.get('id')}")
				count += 1
			except Exception as e:
				log.error(f"Fragment Scrape could not update {scrape_type} {item.get('id')}")
				log.error(str(e))

		return count
	def __scrape_with_url(self, scrape_type, items, __scrape, __update):
		working_scrapers = set()
		missing_scrapers = set()

		# Number of items to scrape
		count = 0
		total = len(items)

		# Scrape if url not in missing_scrapers
		for i, item in enumerate(items):
			# Update status bar
			log.progress(i/total)

			if not item:
				log.debug(f'{scrape_type} of type {type(item)} could not be used ')
				continue

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
				log.error(f"URL Scrape could not update {scrape_type} {item.get('id')}")
				log.error(str(e))

		return count

	# SCENE
	def __update_scene_with_scrape_data(self, scene, scraped_scene):
		update_data = self.parse.scene_from_scrape(scraped_scene)
		scene = self.stash.find_scene(scene["id"], fragment="id tags { id }")
		update_data["id"] = scene.get('id')

		#TODO handle stash box ids
		# if scraped_scene.get('stash_ids'):
		# 	update_data['stash_ids'] = scene.get('stash_ids').extend(scraped_scene.get('stash_ids'))

		# merge old tags with new tags
		scene_tag_ids = [t["id"] for t in scene.get("tags")]
		update_data['tag_ids'] = tools.merge_tags(scene_tag_ids, update_data.get("tag_ids", []))

		self.stash.update_scene(update_data)
	def __scrape_scenes_with_fragment(self, scenes, scraper_id):
		return self.__scrape_with_fragment(
			"scenes",
			scraper_id,
			scenes,
			self.stash.scrape_single_scene,
			self.__update_scene_with_scrape_data
		)
	def __scrape_scenes_with_url(self, scenes):
		return self.__scrape_with_url(
			"scene",
			scenes,
			self.stash.scrape_scene_url,
			self.__update_scene_with_scrape_data
		)

	# GALLERY
	def __update_gallery_with_scrape_data(self, gallery, scraped_gallery):
		gallery = self.stash.find_gallery(gallery["id"], fragment="id tags { id }")

		gallery_data = self.parse.gallery_from_scrape(scraped_gallery)
		gallery_data['id'] = gallery.get('id')

		gallery_tag_ids = [t['id'] for t in gallery['tags']]
		gallery_data['tag_ids'] = tools.merge_tags(gallery_tag_ids, gallery_data.get('tag_ids'))

		self.stash.update_gallery(gallery_data)
	def __scrape_galleries_with_fragment(self, galleries, scraper_id):
		return self.__scrape_with_fragment(
			"galleries",
			scraper_id,
			galleries,
			self.stash.scrape_single_gallery,
			self.__update_gallery_with_scrape_data
		)
	def __scrape_galleries_with_url(self, galleries):
		return self.__scrape_with_url(
			"gallery",
			galleries,
			self.stash.scrape_gallery_url,
			self.__update_gallery_with_scrape_data
		)
	
	# MOVIE
	def __update_movie_with_scrape_data(self, movie, scraped_movie):
		movie_update = self.parse.movie_from_scrape(scraped_movie)
		movie_update["id"] = movie["id"]
		self.stash.update_movie(movie_update)
	def __scrape_movies_with_url(self, movies):
		return self.__scrape_with_url(
			"movie",
			movies,
			self.stash.scrape_movie_url,
			self.__update_movie_with_scrape_data
		)
	
	# PERFORMER
	def __update_performer_with_scrape_data(self, performer, scraped_performer):
		performer_update = { 'id': performer.id }
		performer_update.update( self.parse.get_performer_input(scraped_performer) )

		if scraped_performer.get("tags"):
			performer_update["tag_ids"] = self.parse.get_tag_ids(scraped_performer.tags)

		performer_tag_ids = [t.id for t in performer.tags]
		performer_update['tag_ids'] = tools.merge_tags(performer_tag_ids, performer_update.get('tag_ids',[]))

		self.stash.update_performer(performer_update)
	def __scrape_performers_with_fragment(self, performers, scraper_id):
		return self.__scrape_with_fragment(
			"performer",
			scraper_id,
			performers,
			self.stash.scrape_single_performer,
			self.__update_performer_with_scrape_data
		)
	def __scrape_performers_with_url(self, performers):
		return self.__scrape_with_url(
			"performer",
			performers,
			self.stash.scrape_performer_url,
			self.__update_performer_with_scrape_data
		)

	def __match_scene_with_stashbox_data(self, scene, stashbox_data):
		matches = []
		for scene_data in stashbox_data:

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
				if durr_diff <= config.stashbox_allowed_durr_diff:
					id_match.duration += 1

			has_hash = (id_match.oshash or id_match.phash or id_match.checksum)
			durration_majority_match = (id_match.duration / id_match.fingerprint_count >= config.stashbox_match_percent)
			minimum_required_fingerprints = (id_match.fingerprint_count >= config.stashbox_min_fingerprint_count)
			
			if has_hash and durration_majority_match and minimum_required_fingerprints:
				matches.append(id_match)

		return matches
	def __update_scenes_with_stashbox_data(self, scenes, scraped_data, stashbox, only_stash_ids=False):

		scene_update_ids = []
		total = len(scenes)
		for i, scene in enumerate(scenes):
			# Update status bar
			log.progress(i/total)

			matches = self.__match_scene_with_stashbox_data(scene, scraped_data)

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

			# TODO Implement this option
			if only_stash_ids:
				pass

			try:
				self.__update_scene_with_scrape_data(scene, m.data)
				scene_update_ids.append(scene.get('id'))
			except Exception as e:
				log.error(str(e))

		return scene_update_ids
