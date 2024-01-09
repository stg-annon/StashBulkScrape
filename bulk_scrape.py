import sys, time, traceback
from urllib.parse import urlparse
from types import SimpleNamespace

import datetime as dt

import config

import stashapi.log as log
from stashapi.stashapp import StashInterface
from stashapi.scrape_parser import ScrapeParser
from stashapi.stash_types import StashItem, ScrapeType

class ScrapeController:

	def __init__(self, stash_in:StashInterface):
		global stash

		try:
			self.delay = float(config.EXTERNAL_WEB_REQUEST_DELAY)
			self.last_wait_time = dt.datetime.now()
		except AttributeError as e:
			log.warning(e)
			log.warning("Using defaults for missing config values")
		except ValueError as e:
			log.warning(e)
			log.warning("Using defaults for wrong values")

		stash = stash_in
		self.parse = ScrapeParser(
			stash,
			logger=log,
			create_missing_tags=config.create_missing_tags,
			create_missing_studios=config.create_missing_studios
		)

		stash.reload_scrapers()

		log.debug('############ Bulk Scraper ############')
		log.debug(f'create_missing_performers: {config.create_missing_performers}')
		log.debug(f'create_missing_tags: {config.create_missing_tags}')
		log.debug(f'create_missing_studios: {config.create_missing_studios}')
		log.debug(f'create_missing_movies: {config.create_missing_movies}')
		log.debug(f'delay: {self.delay}')
		log.debug('######################################')
		
	def wait(self):
		if (dt.datetime.now()-self.last_wait_time) < dt.timedelta(seconds=self.delay):
			time.sleep(self.delay)
			self.last_wait_time = dt.datetime.now()

	# adds control tags to stash
	def add_tags(self):
		for tag_name in self.list_all_control_tags():
			stash.find_tag(tag_name, create=True)

	# Removes control tags from stash
	def remove_tags(self):
		tags = self.list_all_control_tags()
		for tag_name in tags:
			tag = stash.find_tag(tag_name)
			if tag == None:
				log.debug("Tag does not exist. Nothing to remove")
				continue
			log.info(f'Destroying tag {tag["name"]}')
			stash.destroy_tag(tag["id"])
	
	# Scrapes Items enabled in config by url scraper
	def bulk_url_scrape(self):
		log.info("Performing Bulk URL Scrape")
		log.info("Progress bar will reset for each item type (scene, movie, ect.)")

		# Scrape Everything enabled in config
		tag_id = stash.find_tag(config.BULK_URL_CONTROL_TAG, create=True).get("id")

		if StashItem.SCENE in config.BULK_URL:
			scenes = stash.find_scenes(f={
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
			galleries = stash.find_galleries(f={
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
			performers = stash.find_performers(f={
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
			movies = stash.find_movies(f={
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
			tag = stash.find_tag(tag_name)
			if not tag:
				log.warning(f"could not find tag '{tag_name}'")
				continue
			scraper_id, supported_content_types = types_tuple
			if StashItem.SCENE in supported_content_types:
				scenes = stash.find_scenes(f={
					"tags": {
						"value": [tag["id"]],
						"depth": 0,
						"modifier": "INCLUDES"
					}
				}, fragment="id")
				self.__scrape_scenes_with_fragment(scenes, scraper_id)

			if StashItem.GALLERY in supported_content_types:
				galleries = stash.find_galleries(f={
					"tags": {
						"value": [tag["id"]],
						"depth": 0,
						"modifier": "INCLUDES"
					}
				}, fragment="id")
				self.__scrape_galleries_with_fragment(galleries, scraper_id)
					
			if StashItem.PERFORMER in supported_content_types:
				performers = stash.find_performers(f={
					"tags": {
						"value": [tag["id"]],
						"depth": 0,
						"modifier": "INCLUDES"
					}
				}, fragment="id")
				self.__scrape_performers_with_fragment(performers, scraper_id)

		return None
	def list_all_fragment_tags(self):
		fragment_tags = {}
		for s in stash.list_scrapers(config.FRAGMENT_SCRAPE):
			tag_id = f'{config.FRAGMENT_SCRAPE_PREFIX}{s["id"]}'
			for content_type in config.FRAGMENT_SCRAPE:
				type_spec = s[content_type.value.lower()]
				if type_spec and ScrapeType.FRAGMENT.value in type_spec["supported_scrapes"]:
					if tag_id in fragment_tags:
						fragment_tags[tag_id][1].append(content_type)
					else:
						fragment_tags[tag_id] = (s["id"], [content_type])
		return fragment_tags
	def list_all_control_tags(self):
		control_tags = [ config.BULK_URL_CONTROL_TAG ]
		control_tags.extend(list(self.list_all_fragment_tags().keys()))
		return control_tags
	def get_control_tag_ids(self):
		control_ids = list()
		for tag_name in self.list_all_control_tags():
			tag = stash.find_tag(tag_name)
			if not tag:
				continue
			control_ids.append(tag["id"])
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
			if not any(scraped_data.values()):
				log.info(f"Could not get data for {scrape_type} {item.get('id')}")
				continue

			try:
				__update(item, scraped_data)
				log.debug(f"Updated data for {scrape_type} {item.get('id')}")
				count += 1
			except Exception as e:
				log.error(f"Fragment Scrape could not update {scrape_type} {item.get('id')}")
				log.error(str(e))
				log.error(traceback.format_exc())

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

			item_url = None
			if item.get('url') and item.get('url') != "":
				item_url = item['url']
			elif item.get('urls') and item.get('urls') != []:
				item_url = item['urls'][0]
			if not item_url:
				log.info(f"{scrape_type} {item.get('id')} is missing url")
				continue
			netloc = urlparse(item_url).netloc
			if netloc in missing_scrapers and netloc not in working_scrapers:
				continue
			
			self.wait()
			log.info(f"Scraping URL for {scrape_type} {item.get('id')}")

			scraped_data = __scrape(item_url)

			# If result is null, add url to missing_scrapers
			if scraped_data is None:
				log.warning(f"Missing scraper for {urlparse(item_url).netloc}")
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
		scene_update = self.parse.scene_from_scrape(scraped_scene)
		scene_update["id"] = scene["id"]

		#TODO handle stash box ids
		# if scraped_scene.get('stash_ids'):
		# 	update_data['stash_ids'] = scene.get('stash_ids').extend(scraped_scene.get('stash_ids'))

		# Merge Tags
		stash.update_scenes({
			"ids": [scene_update["id"]],
			"tag_ids": {
				"ids": scene_update["tag_ids"],
				"mode":"ADD"
			}
		})
		del scene_update["tag_ids"]

		stash.update_scene(scene_update)
	def __scrape_scenes_with_fragment(self, scenes, scraper_id):
		return self.__scrape_with_fragment(
			"scenes",
			scraper_id,
			scenes,
			stash.scrape_scene,
			self.__update_scene_with_scrape_data
		)
	def __scrape_scenes_with_url(self, scenes):
		return self.__scrape_with_url(
			"scene",
			scenes,
			stash.scrape_scene_url,
			self.__update_scene_with_scrape_data
		)

	# GALLERY
	def __update_gallery_with_scrape_data(self, gallery, scraped_gallery):
		gallery_update = self.parse.gallery_from_scrape(scraped_gallery)
		gallery_update['id'] = gallery["id"]

		# Merge Tags
		stash.update_galleries({
			"ids": [gallery_update["id"]],
			"tag_ids": {
				"ids": gallery_update["tag_ids"],
				"mode":"ADD"
			}
		})
		del gallery_update["tag_ids"]

		stash.update_gallery(gallery_update)
	def __scrape_galleries_with_fragment(self, galleries, scraper_id):
		return self.__scrape_with_fragment(
			"galleries",
			scraper_id,
			galleries,
			stash.scrape_gallery,
			self.__update_gallery_with_scrape_data
		)
	def __scrape_galleries_with_url(self, galleries):
		return self.__scrape_with_url(
			"gallery",
			galleries,
			stash.scrape_gallery_url,
			self.__update_gallery_with_scrape_data
		)
	
	# MOVIE
	def __update_movie_with_scrape_data(self, movie, scraped_movie):
		movie_update = self.parse.movie_from_scrape(scraped_movie)
		movie_update["id"] = movie["id"]
		stash.update_movie(movie_update)
	def __scrape_movies_with_url(self, movies):
		return self.__scrape_with_url(
			"movie",
			movies,
			stash.scrape_movie_url,
			self.__update_movie_with_scrape_data
		)
	
	# PERFORMER
	def __update_performer_with_scrape_data(self, performer, scraped_performer):
		performer_update = self.parse.performer_from_scrape(scraped_performer)
		performer_update["id"] = performer["id"]
		
		# Merge Tags
		stash.update_performers({
			"ids": [performer_update["id"]],
			"tag_ids": {
				"ids": performer_update["tag_ids"],
				"mode":"ADD"
			}
		})
		del performer_update["tag_ids"]

		stash.update_performer(performer_update)
	def __scrape_performers_with_fragment(self, performers, scraper_id):
		return self.__scrape_with_fragment(
			"performer",
			scraper_id,
			performers,
			stash.scrape_performer,
			self.__update_performer_with_scrape_data
		)
	def __scrape_performers_with_url(self, performers):
		return self.__scrape_with_url(
			"performer",
			performers,
			stash.scrape_performer_url,
			self.__update_performer_with_scrape_data
		)
