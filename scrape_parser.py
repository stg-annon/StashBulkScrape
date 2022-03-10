from enum import Enum
from datetime import datetime

import config
import utils.log as log
import utils.tools as tools
from utils.stash import StashInterface

class Gender(Enum):
	MALE="MALE"
	FEMALE="FEMALE"
	TRANSGENDER_MALE="TRANSGENDER_MALE"
	TRANSGENDER_FEMALE="TRANSGENDER_FEMALE"
	INTERSEX="INTERSEX"
	NON_BINARY="NON_BINARY"

class ScrapeParser:

	def __init__(self, stash:StashInterface):
		self.stash = stash

	def detect(self, scraped_item):

		if not scraped_item.get("__typename"):
			return None
		
		if scraped_item["__typename"] == "ScrapedTag":
			return self.tag_from_scape(scraped_item)
		if scraped_item["__typename"] == "ScrapedGallery":
			return self.gallery_from_scrape(scraped_item)
		if scraped_item["__typename"] == "ScrapedStudio":
			return self.studio_from_scrape(scraped_item)
		if scraped_item["__typename"] == "ScrapedMovie":
			return self.movie_from_scraped(scraped_item)
		if scraped_item["__typename"] == "ScrapedPerformer":
			return self.performer_from_scrape(scraped_item)
		if scraped_item["__typename"] == "ScrapedScene":
			return self.scene_from_scrape(scraped_item)

	def tag_from_scape(self, tag):
		"""
		v0.12.0-40
		type ScrapedTag {
			stored_id: ID
			name: String!
		}

		type TagUpdateInput {
			id: ID!
			name: String
			aliases: [String!]
			image: String
			parent_ids: [ID!]
			child_ids: [ID!]
		}
		"""

		if tag.get("stored_id"):
			tag["id"] = tag["stored_id"]
			del tag["stored_id"]
		elif config.create_missing_tags:
			return self.stash.create_tag(tag)

		return tools.clean_dict(tag)

	def gallery_from_scrape(self, gallery):
		"""
		v0.12.0-40
		type ScrapedGallery {
			title: String
			details: String
			url: String
			date: String
			studio: ScrapedStudio
			tags: [ScrapedTag!]
			performers: [ScrapedPerformer!]
		}

		type GalleryUpdateInput {
			clientMutationId: String
			id: ID!
			title: String
			url: String
			date: String
			details: String
			rating: Int
			organized: Boolean
			scene_ids: [ID!]
			studio_id: ID
			tag_ids: [ID!]
			performer_ids: [ID!]
		}
		"""

		if gallery.get("tags"):
			gallery["tag_ids"] = [self.tag_from_scape(t)["id"] for t in gallery["tags"]]
			del gallery["tags"]
		if gallery.get("performers"):
			gallery["performer_ids"] = [self.performer_from_scrape(p)["id"] for p in gallery["performers"]]
			del gallery["performers"]
		if gallery.get("studio"):
			gallery["studio_id"] = self.studio_from_scrape(gallery["studio"]).get("id", None)
			del gallery["studio"]
			
		return tools.clean_dict(gallery)

	def studio_from_scrape(self, studio):
		"""
		v0.12.0-40
		type ScrapedStudio {
			stored_id: ID
			name: String!
			url: String
			image: String
			remote_site_id: String
		}

		type StudioUpdateInput {
			id: ID!
			name: String
			url: String
			parent_id: ID
			image: String
			stash_ids: [StashIDInput!]
			rating: Int
			details: String
			aliases: [String!]
		}
		"""
		# ignore field
		if studio.get("remote_site_id"):
			del studio["remote_site_id"]
		
		if studio.get("stored_id"):
			studio["id"] = studio["stored_id"]
			del studio["stored_id"]
		elif config.create_missing_studios:
			return self.stash.create_studio(studio)

		return tools.clean_dict(studio)

	def movie_from_scraped(self, movie):
		"""
		v0.12.0-40
		type ScrapedMovie {
				stored_id: ID
				name: String
				aliases: String
				duration: String
				date: String
				rating: String
				director: String
				url: String
				synopsis: String
				studio: ScrapedStudio
				front_image: String
				back_image: String
		}
		
		type MovieUpdateInput {
				id: ID!
				name: String
				aliases: String
				duration: Int
				date: String
				rating: Int
				studio_id: ID
				director: String
				synopsis: String
				url: String
				front_image: String
				back_image: String
		}
		"""
		# NOTE
		#  duration: String (HH:MM:SS) => duration: Int (Total Seconds)
		#  studio: {ScrapedMovieStudio} => studio_id: ID
		
		if movie.get("studio"):
			movie["studio_id"] = self.studio_from_scrape(movie["studio"])["id"]
			del movie["studio"]

		# duration value from scraped movie is string, update expects an int
		if movie.get("duration"):
			if movie.duration.count(':') == 0:
				movie.duration = f'00:00:{movie["duration"]}'
			if movie.duration.count(':') == 1:
				movie.duration = f'00:{movie["duration"]}'
			h,m,s = movie.duration.split(':')
			duration = datetime.timedelta(hours=int(h),minutes=int(m),seconds=int(s)).total_seconds()
			movie['duration'] = int(duration)

		return tools.clean_dict(movie)

	def performer_from_scrape(self, performer):
		"""
		v0.12.0-40
		type ScrapedPerformer {
				stored_id: ID
				name: String
				gender: String
				url: String
				twitter: String
				instagram: String
				birthdate: String
				ethnicity: String
				country: String
				eye_color: String
				height: String
				measurements: String
				fake_tits: String
				career_length: String
				tattoos: String
				piercings: String
				aliases: String
				tags: [ScrapedTag!]
				images: [String!]
				details: String
				death_date: String
				hair_color: String
				weight: String
				remote_site_id: String

				# Deprecated: use images instead
				image: String
		}

		type PerformerUpdateInput {
				id: ID!
				name: String
				url: String
				gender: GenderEnum
				birthdate: String
				ethnicity: String
				country: String
				eye_color: String
				height: String
				measurements: String
				fake_tits: String
				career_length: String
				tattoos: String
				piercings: String
				aliases: String
				twitter: String
				instagram: String
				favorite: Boolean
				tag_ids: [ID!]
				image: String
				stash_ids: [StashIDInput!]
				rating: Int
				details: String
				death_date: String
				hair_color: String
				weight: Int
		}
		"""
		# NOTE
		# 	ScrapedPerformer.gender: String => PerformerCreateInput.gender: GenderEnum
		#   ScrapedPerformer.weight: String (kg?) => PerformerCreateInput.weight: Int (kg)

		if performer.get("stored_id"):
			performer["id"] = performer["stored_id"]
			del performer["stored_id"]

		if performer.get("images") and len(performer["images"]) > 0:
			performer["image"] = performer["images"][0]
			
		if performer.get("tags"):
			performer["tag_ids"] = [self.tag_from_scape(t)["id"] for t in performer.get("tags")]
			del performer["tags"]

		if performer.get("weight"):
			try:
				performer["weight"] = int(performer["weight"])
			except:
				del performer["weight"]
				log.warning(f'Could not parse performer weight "{performer["weight"]}" it Int for {performer["name"]}')

		if performer.get("gender"):
			try:
				performer["gender"] = Gender[performer["gender"]].value
			except:
				del performer["gender"]
				log.warning(f'Cannot map performer Gender "{performer["gender"]}" for {performer["name"]}')

		return tools.clean_dict(performer)

	def scene_from_scrape(self, scene):
		"""
		v0.12.0-40
		type ScrapedScene {
			title: String
			details: String
			url: String
			date: String
			image: String
			file: SceneFileType
			studio: ScrapedStudio
			tags: [ScrapedTag!]
			performers: [ScrapedPerformer!]
			movies: [ScrapedMovie!]
			remote_site_id: String
			duration: Int
			fingerprints: [StashBoxFingerprint!]
		}
		type SceneUpdateInput {
			clientMutationId: String
			id: ID!
			title: String
			details: String
			url: String
			date: String
			rating: Int
			organized: Boolean
			studio_id: ID
			gallery_ids: [ID!]
			performer_ids: [ID!]
			movies: [SceneMovieInput!]
			tag_ids: [ID!]
			cover_image: String
			stash_ids: [StashIDInput!]
		}
		"""

		# ignore field
		if scene.get("file"):
			del scene["file"]
		# ignore field
		if scene.get("remote_site_id"):
			del scene["remote_site_id"]
		# ignore field
		if scene.get("duration"):
			del scene["duration"]
		# ignore field
		if scene.get("fingerprints"):
			del scene["fingerprints"]

		if scene.get("image"):
			scene["cover_image"] = scene["image"]
			del scene["image"]

		if scene.get("studio"):
			scene["studio"] = self.studio_from_scrape(scene["studio"])

		if scene.get("tags"):
			scene["tags_ids"] = [self.tag_from_scape(t)["id"] for t in scene["tags"]]
			del scene["tags"]

		if scene.get("performers"):
			scene["performer_ids"] = [self.performer_from_scrape(p)["id"] for p in scene["performers"]]
			del scene["performers"]

		if scene.get("movies"):
			scene["movies"] = [self.movie_from_scraped(m) for m in scene["movies"]]

		return tools.clean_dict(scene)