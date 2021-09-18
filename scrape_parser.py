import datetime
from urllib.parse import urlparse

import log
import utils
import config

class ScrapeParser:

  def __init__(self, client):
    self.client = client

  def __multi_item_list(self, __callback, items):
    item_ids = [__callback(i) for i in items]
    return [ item_id for item_id in item_ids if item_id ]

  def get_common_atttrs(self, scrape_data, attr_list):
    common_dict = {}
    for attr in attr_list:
      if scrape_data.get(attr):
        common_dict[attr] = scrape_data[attr]
    return common_dict

  def get_studio_id(self, studio):
    if studio.stored_id:
      return studio.stored_id

    studio.name = utils.caps_string(studio.name)
    if studio.url:
      studio.url = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(studio.url))

    stash_studio = self.client.find_studio(studio, create_missing=config.create_missing_studios)
    if stash_studio:
      return stash_studio.id

  def get_tag_ids(self, tags):
    return self.__multi_item_list(self.get_tag_id, tags)
  def get_tag_id(self, tag):
    if tag.stored_id:
      return tag.stored_id
    elif config.create_missing_tags and tag.name:
      tag_name = utils.caps_string(tag.name)
      log.info(f'Create missing tag: {tag_name}')
      return self.client.create_tag({'name':tag_name})
      
  def get_performer_ids(self, performers):
    return self.__multi_item_list(self.get_performer_id, performers)
  def get_performer_id(self, performer):
    if performer.stored_id:
      return performer.stored_id
    elif performer.name:
      log.debug(f'Stash could not match {performer.name} doing custom match')
      # scraper could not match performer, try re-matching or create if enabled
      performer.name = utils.caps_string(performer.name)
      
      stash_performer = self.client.find_performer( self.get_performer_input(performer), create_missing=config.create_missing_performers )
      if stash_performer and stash_performer.get("id"):
        return stash_performer.id

  def get_performer_input(self, performer):
        # Expecting to cast ScrapedPerformer to PerformerCreate/UpdateInput 
        # NOTE
        # 	ScrapedPerformer.gender: String => PerformerCreateInput.gender: GenderEnum
        #   ScrapedPerformer.weight: String (kg?) => PerformerCreateInput.weight: Int (kg)
        performer_data = {}
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
          if performer.get(attr):
            performer_data[attr] = performer[attr]

        # cast String to Int, this assumes both values are the same unit and are just diffrent types
        if performer.weight:
          performer_data['weight'] = int(performer.weight)

        GENDER_ENUM = ["MALE","FEMALE","TRANSGENDER_MALE","TRANSGENDER_FEMALE", "INTERSEX", "NON_BINARY"]

        if performer.gender:
          gender = performer.gender.replace(' ', '_').upper()
          if gender in GENDER_ENUM:
            performer_data['gender'] = gender
          else:
            log.warning(f'Could not map {performer.gender} to a GenderEnum for performer {performer.id}')
        
        return performer_data

  def get_movie_ids(self, movies):
    return self.__multi_item_list(self.get_movie_id, movies)
  def get_movie_id(self, movie):
    if movie.stored_id:
      return {'movie_id':movie.stored_id, 'scene_index':None}
    elif config.create_missing_movies and movie.name:
      log.info(f'Create missing movie: "{movie.name}"')
      try:
        stash_movie = self.client.create_movie(self.get_movie_input(movie))
        return {'movie_id':stash_movie.id, 'scene_index':None}
      except Exception as e:
        raise Exception(f'Movie create error {e}')
  def get_movie_input(self, movie):
    # NOTE
    #  duration: String (HH:MM:SS) => duration: Int (Total Seconds)
    #  studio: {ScrapedMovieStudio} => studio_id: ID

    movie_data = {
      'name': movie.name
    }
    common_attr = [
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
    movie_data.update( self.get_common_atttrs( movie, common_attr) )
    
    # here because durration value from scraped movie is string where update preferrs an int need to cast to an int (seconds)
    if movie.duration:
      if movie.duration.count(':') == 0:
        movie.duration = f'00:00:{movie.duration}'
      if movie.duration.count(':') == 1:
        movie.duration = f'00:{movie.duration}'
      h,m,s = movie.duration.split(':')
      durr = datetime.timedelta(hours=int(h),minutes=int(m),seconds=int(s)).total_seconds()
      movie_data['duration'] = int(durr)

    if movie.studio:
      movie_data['studio_id'] = self.get_studio_id(movie.studio)

    movie_data = utils.clean_dict(movie_data)
    return movie_data
