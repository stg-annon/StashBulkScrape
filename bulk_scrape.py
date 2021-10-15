import json
from scrape_parser import ScrapeParser
import sys
import time
import datetime
import traceback
from urllib.parse import urlparse
from types import SimpleNamespace


import log
import config
import utils
from stash_interface import StashInterface

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
		
		if mode_arg == "import_movies":
			scraper.import_movie_urls()


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
		self.parse = ScrapeParser(client)

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

	# adds control tags to stash
	def add_tags(self):
		tags = self.list_all_control_tags()
		for tag_name in tags:
			tag_id = self.client.find_tag_id(tag_name)
			if tag_id == None:
				tag_id = self.client.create_tag({'name':tag_name})
				log.info(f"adding tag {tag_name}")
			else:
				log.debug(f"tag exists, {tag_name}")

	# Removes control tags from stash
	def remove_tags(self):
		tags = self.list_all_control_tags()
		for tag_name in tags:
			tag_id = self.client.find_tag_id(tag_name)
			if tag_id == None:
				log.debug("Tag does not exist. Nothing to remove")
				continue
			log.info(f"Destroying tag {tag_name}")
			self.client.destroy_tag(tag_id)

	# Scrapes Items enabled in config by url scraper
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

		if len(updated_scene_ids) > 0 and config.stashbox_submit_fingerprints:
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
				log.error(traceback.format_exc())
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
				log.error(traceback.format_exc())
				log.error(f"URL Scrape could not update {scrape_type} {item.get('id')}")
				log.error(str(e))

		return count

	def __scrape_scenes_with_fragment(self, scenes, scraper_id):
		return self.__scrape_with_fragment(
			"scenes",
			scraper_id,
			scenes,
			self.client.scrape_single_scene,
			self.__update_scene_with_scrape_data
		)
	def __scrape_scenes_with_url(self, scenes):
		return self.__scrape_with_url(
			"scene",
			scenes,
			self.client.scrape_scene_url,
			self.__update_scene_with_scrape_data
		)
	def __update_scene_with_scrape_data(self, scene, scraped_scene):
		
		update_data = {
			'id': scene.get('id')
		}

		common_attrabutes = ['url','title','details','date']
		update_data.update( self.parse.get_common_atttrs( scraped_scene, common_attrabutes ) )

		if scraped_scene.get('image'):
			update_data['cover_image'] = scraped_scene.get('image')

		if scraped_scene.tags:
			update_data['tag_ids'] = self.parse.get_tag_ids(scraped_scene.tags)

		if scraped_scene.performers:
			update_data['performer_ids'] = self.parse.get_performer_ids(scraped_scene.performers)

		if scraped_scene.studio:
			update_data['studio_id'] = self.parse.get_studio_id(scraped_scene.studio)

		if scraped_scene.movies:
			update_data['movies'] = self.parse.get_movie_ids(scraped_scene.movies)

		# handle stash box ids
		if scraped_scene.get('stash_ids'):
			update_data['stash_ids'] = scene.get('stash_ids').extend(scraped_scene.get('stash_ids'))

		# Only accept base64 images
		if update_data.get('cover_image') and not update_data.get('cover_image').startswith("data:image"):
			del update_data['cover_image']

		scene_tag_ids = [t.id for t in scene.tags]
		update_data['tag_ids'] = self.__merge_tags(scene_tag_ids, update_data.get('tag_ids'))

		update_data = utils.clean_dict(update_data)
		self.client.update_scene(update_data)

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

			# TODO Immplament this option
			if only_stash_ids:
				pass

			try:
				self.__update_scene_with_scrape_data(scene, m.data)
				scene_update_ids.append(scene.get('id'))
			except Exception as e:
				log.error(str(e))

		return scene_update_ids

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

	def __scrape_galleries_with_fragment(self, galleries, scraper_id):
		return self.__scrape_with_fragment(
			"galleries",
			scraper_id,
			galleries,
			self.client.scrape_single_gallery,
			self.__update_gallery_with_scrape_data
		)
	def __scrape_galleries_with_url(self, galleries):
		return self.__scrape_with_url(
			"gallery",
			galleries,
			self.client.scrape_gallery_url,
			self.__update_gallery_with_scrape_data
		)
	def __update_gallery_with_scrape_data(self, gallery, scraped_gallery):
		update_data = {
			'id': gallery.get('id')
		}

		common_attrabutes = ['title','details','url','date']
		update_data.update( self.parse.get_common_atttrs( scraped_gallery, common_attrabutes ) )

		if scraped_gallery.tags:
			update_data['tag_ids'] = self.parse.get_tag_ids(scraped_gallery.tags)

		if scraped_gallery.performers:
			update_data['performer_ids'] = self.parse.get_performer_ids(scraped_gallery.performers)

		if scraped_gallery.studio:
			update_data['studio_id'] = self.parse.get_studio_id(scraped_gallery.studio)

		gallery_tag_ids = [t.id for t in gallery.tags]
		update_data['tag_ids'] = self.__merge_tags(gallery_tag_ids, update_data.get('tag_ids'))

		update_data = utils.clean_dict(update_data)
		self.client.update_gallery(update_data)

	def __scrape_movies_with_url(self, movies):
		return self.__scrape_with_url(
			"movie",
			movies,
			self.client.scrape_movie_url,
			self.__update_movie_with_scrape_data
		)
	def __update_movie_with_scrape_data(self, movie, scraped_movie):
		movie_update = { 'id': movie.id }
		movie_update.update( self.parse.get_movie_input(scraped_movie) )
		self.client.update_movie(movie_update)

	def __scrape_performers_with_fragment(self, performers, scraper_id):
		return self.__scrape_with_fragment(
			"performer",
			scraper_id,
			performers,
			self.client.scrape_single_performer,
			self.__update_performer_with_scrape_data
		)
	def __scrape_performers_with_url(self, performers):
		return self.__scrape_with_url(
			"performer",
			performers,
			self.client.scrape_performer_url,
			self.__update_performer_with_scrape_data
		)
	def __update_performer_with_scrape_data(self, performer, scraped_performer):
		performer_update = { 'id': performer.id }
		performer_update.update( self.parse.get_performer_input(scraped_performer) )

		if scraped_performer.get("tags"):
			performer_update["tag_ids"] = self.parse.get_tag_ids(scraped_performer.tags)

		performer_tag_ids = [t.id for t in performer.tags]
		performer_update['tag_ids'] = self.__merge_tags(performer_tag_ids, performer_update.get('tag_ids',[]))

		self.client.update_performer(performer_update)

	def __merge_tags(self, old_tag_ids, new_tag_ids):
		merged_tags = set()
		ctrl_tag_ids = self.get_control_tag_ids()
		merged_tags.update([t for t in old_tag_ids if t not in ctrl_tag_ids])
		if new_tag_ids:
			merged_tags.update(new_tag_ids)
		return list(merged_tags)


	def import_movie_urls(self):
		def create_movie(movie, scraped_movie):
			self.client.find_or_create_movie(scraped_movie, update_movie=True)

		url_list = [ url for url in open('movie_urls.txt', 'r').readlines()]
		url_list = list(set(url_list))
		movie_urls = [ {'url':url } for url in url_list]
		return self.__scrape_with_url(
			"movie",
			movie_urls,
			self.client.scrape_movie_url,
			create_movie
		)

if __name__ == '__main__':
	main()