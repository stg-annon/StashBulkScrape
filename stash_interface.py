import requests
import sys
import log
import re

from box import Box

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

    def __init__(self, conn, fragments={}):
        self.port = conn['Port'] if conn.get('Port') else '9999'
        scheme = conn['Scheme'] if conn.get('Scheme') else 'http'

        # Session cookie for authentication

        self.cookies = {}
        if conn.get('SessionCookie'):
            self.cookies.update({
                'session': conn['SessionCookie']['Value']
            })

        domain = conn['Domain'] if conn.get('Domain') else 'localhost'

        # Stash GraphQL endpoint
        self.url = f'{scheme}://{domain}:{self.port}/graphql'
        log.debug(f"Using stash GraphQl endpoint at {self.url}")

        self.fragments = fragments
        self.fragments.update(stash_gql_fragments)

    def __resolveFragments(self, query):

        fragmentRefrences = list(set(re.findall(r'(?<=\.\.\.)\w+', query)))
        fragments = []
        for ref in fragmentRefrences:
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
                return Box(result['data'])
        elif response.status_code == 401:
            sys.exit("HTTP Error 401, Unauthorised. Cookie authentication most likely failed")
        else:
            raise ConnectionError(
                "GraphQL query failed:{} - {}. Query: {}. Variables: {}".format(
                    response.status_code, response.content, query, variables)
            )

    def __match_alias_item(self, search, items):
        item_matches = {}
        for item in items:
            if re.match(rf'{search}$', item.name, re.IGNORECASE):
                log.debug(f'matched "{search}" to "{item.name}" ({item.id}) using primary name')
                item_matches[item.id] = item
            if not item.aliases:
                continue
            for alias in item.aliases:
                if re.match(rf'{search}$', alias.strip(), re.IGNORECASE):
                    log.debug(f'matched "{search}" to "{alias}" ({item.id}) using alias')
                    item_matches[item.id] = item
        return list(item_matches.values())

    def scan_for_new_files(self):
        try:
            query = """
                    mutation {
                        metadataScan (
                            input: {
                                useFileMetadata: true 
                                scanGenerateSprites: false
                                scanGeneratePreviews: false
                                scanGenerateImagePreviews: false
                                stripFileExtension: false
                            }
                        ) 
                    }
            """
            result = self.__callGraphQL(query)
        except ConnectionError:
            query = """
                    mutation {
                        metadataScan (
                            input: {
                                useFileMetadata: true
                            }
                        ) 
                    }
            """
            result = self.__callGraphQL(query)
        log.debug("ScanResult" + str(result))

    def list_stashboxes(self):
        query = """
            query Configuration {
                configuration {
                    general{
                        stashBoxes{
                            name
                            endpoint
                            api_key
                        }
                    }
                }
            }
        """

        result = self.__callGraphQL(query)
        return result['configuration']['general']['stashBoxes']

    def find_tag_id(self, name):
        for tag in self.find_tags(q=name):
            if tag["name"] == name:
                return tag["id"]
            if any(name == a for a in tag["aliases"] ):
                return tag["id"]
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
    def find_tag(self, tag, create_missing=False):
        if not tag.get('name'):
            return
        
        name = tag.get('name')

        stash_tags = self.find_tags(q=name)
        tag_matches = self.__match_alias_item(name, stash_tags)

        # none if multuple results from a one word name
        if len(tag_matches) > 1 and name.count(' ') == 0:
            return None
        elif len(tag_matches) > 0:
            return tag_matches[0]

        if create_missing:
            log.info(f'Create missing tag: {name}')
            self.create_tag(tag)


    def create_tag(self, tag):
        query = """
            mutation tagCreate($input:TagCreateInput!) {
                tagCreate(input: $input){
                    id
                }
            }
        """

        variables = {'input': {
            'name': tag['name']
        }}

        result = self.__callGraphQL(query, variables)
        return result["tagCreate"]["id"]
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
    def find_performer(self, performer_data, create_missing=False):
        if not performer_data.get("name"):
            return None

        name = performer_data["name"]
        name = name.strip()

        performer_data["name"] = name

        performers = self.find_performers(q=name)

    
        for p in performers:
            if not p.aliases:
                continue
            alias_delim = re.search(r'(\/|\n|,)', p.aliases)
            if alias_delim:
                p.aliases = p.aliases.split(alias_delim.group(1))
            elif len(p.aliases) > 0:
                p.aliases = [p.aliases]
            else:
                log.debug(f'Could not determine delim for aliases "{p.aliases}"')

        performer_matches = self.__match_alias_item(name, performers)

        # none if multuple results from a one word name
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
                    ...stashPerformer
                }
            }
        """

        variables = {'input': performer_data}

        result = self.__callGraphQL(query, variables)
        return result.get('performerCreate')
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
        return result['performerUpdate']


    def find_or_create_movie(self, movie_data, update_movie=False):
        movie_stashid = self.find_movie(movie_data)
        if movie_stashid:
            if update_movie:
                movie_data['id'] = movie_stashid
                self.update_movie(movie_data)
            return movie_stashid
        else:
            return self.create_movie(movie_data)
    def create_movie(self, movie_data):
        name = movie_data.get("name")
        query = """
            mutation($name: String!) {
                movieCreate(input: { name: $name }) {
                    id
                }
            }
        """

        variables = {
            'name': name
        }

        result = self.__callGraphQL(query, variables)
        movie_data['id'] = result['movieCreate']['id']
        return self.update_movie(movie_data)

    def update_movie(self, movie_data):
        query = """
            mutation MovieUpdate($input:MovieUpdateInput!) {
                movieUpdate(input: $input) {
                    id
                }
            }
        """
        variables = {'input': movie_data}

        result = self.__callGraphQL(query, variables)
        return result['movieUpdate']

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
    def find_studio(self, studio, create_missing=False):
        if not studio.get("name"):
            return None

        name = studio["name"]
        stash_studios = self.find_studios(q=name)
        studio_matches = self.__match_alias_item(name, stash_studios)

        # none if multuple results from a one word name
        if len(studio_matches) > 1 and name.count(' ') == 0:
            return None
        elif len(studio_matches) > 0:
            return studio_matches[0] 

        if create_missing:
            log.info(f'Create missing studio: "{name}"')
            return self.create_studio(studio)

    def create_studio(self, studio_data):
        query = """
            mutation($name: String!) {
                studioCreate(input: { name: $name }) {
                    id
                }
            }
        """
        variables = {
            'name': studio_data['name']
        }

        result = self.__callGraphQL(query, variables)
        studio_data['id'] = result['studioCreate']['id']

        return self.update_studio(studio_data)
    def update_studio(self, studio_data):
        query = """
            mutation StudioUpdate($input:StudioUpdateInput!) {
                studioUpdate(input: $input) {
                    id
                }
            }
        """
        variables = {'input': studio_data}

        result = self.__callGraphQL(query, variables)
        return result.studioUpdate.id


    def find_movie(self, movie):
        movies = self.find_movies(q=movie['name'])
        for m in movies:
            if movie.get('name') and m.get('name') and movie['name'] == m['name']:
                return m
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


    def reload_scrapers(self):
        query = """ 
            mutation ReloadScrapers {
                reloadScrapers
            }
        """
        
        result = self.__callGraphQL(query)
        return result["reloadScrapers"]
    def list_performer_scrapers(self, type):
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
        ret = []
        result = self.__callGraphQL(query)
        for r in result["listPerformerScrapers"]:
            if type in r["performer"]["supported_scrapes"]:
                ret.append(r["id"])
        return ret
    def list_scene_scrapers(self, type):
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
        ret = []
        result = self.__callGraphQL(query)
        for r in result["listSceneScrapers"]:
            if type in r["scene"]["supported_scrapes"]:
                ret.append(r["id"])
        return ret
    def list_gallery_scrapers(self, type):
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
        result = self.__callGraphQL(query)
        for r in result["listGalleryScrapers"]:
            if type in r["gallery"]["supported_scrapes"]:
                ret.append(r["id"])
        return ret
    def list_movie_scrapers(self, type):
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
        result = self.__callGraphQL(query)
        for r in result["listMovieScrapers"]:
            if type in r["movie"]["supported_scrapes"]:
                ret.append(r["id"])
        return ret


    def create_scene_marker(self, seconds, scene_id, primary_tag_id, title="", tag_ids=[]):
        query = """
            mutation SceneMarkerCreate($input: SceneMarkerCreateInput!) {
              sceneMarkerCreate(input: $input) {
                id
                __typename
              }
            }
        """
        
        variables = {
            "input": {
                "tag_ids": tag_ids,
                "title": title,
                "seconds": seconds,
                "scene_id": scene_id,
                "primary_tag_id": primary_tag_id
            }
        }
        
        result = self.__callGraphQL(query, variables)
        return result.sceneMarkerCreate

    def find_scene_markers(self, sceneID):
        query = """
            query { findScene(id: $sceneID) {
                title
                date
                scene_markers {
                  primary_tag {id, name}
                  seconds
                  __typename
                }
              }
            }
        """

        variables = {
            'sceneID': sceneID
        }

        result = self.__callGraphQL(query, variables)
        return result['findScene']['scene_markers']


    # This method will overwrite all provided data fields
    def update_scene(self, scene_data):
        query = """
            mutation sceneUpdate($input:SceneUpdateInput!) {
                sceneUpdate(input: $input) {
                    id
                }
            }
        """
        variables = {'input': scene_data}

        result = self.__callGraphQL(query, variables)
        return result["sceneUpdate"]["id"]

    def find_scenes(self, f={}):
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
            "filter": { "per_page": -1 },
            "scene_filter": f
        }
            
        result = self.__callGraphQL(query, variables)
        scenes = result['findScenes']['scenes']

        return scenes


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

    # Stash Box
    def stashbox_scene_scraper(self, scene_ids, stashbox_index=0):
        query = """
            query ScrapeMultiScenes($source: ScraperSourceInput!, $input: ScrapeMultiScenesInput!) {
                scrapeMultiScenes(source: $source, input: $input) {
                    ...scrapedScene
                    __typename
                }
            }
        """
        variables = {
            "source": {
                "stash_box_index": stashbox_index
            },
            "input": {
                "scene_ids": scene_ids,
            }
        }

        result = self.__callGraphQL(query, variables)

        return result["scrapeMultiScenes"]

    def stashbox_submit_scene_fingerprints(self, scene_ids, stashbox_index=0):
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


    def depracated_scrape_scene(self, scraper_id, scene):
        query = """query ScrapeScene($scraper_id: ID!, $scene: SceneUpdateInput!) {
           scrapeScene(scraper_id: $scraper_id, scene: $scene) {
              ...scrapedScene
            }
          }
        """
        variables = {
            "scraper_id": scraper_id,
            "scene": {
                "id": scene["id"],
                "title": scene["title"],
                "date": scene["date"],
                "details": scene["details"],
                "gallery_ids": [],
                "movies": None,
                "performer_ids": [],
                "rating": scene["rating"],
                "stash_ids": scene["stash_ids"],
                "studio_id": None,
                "tag_ids": None,
                "url": scene["url"]
            }
        }
        result = self.__callGraphQL(query, variables)
        return result["scrapeScene"]

    def scrape_single_scene(self, scraper_id, scene):
        
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
            
    def scrape_single_gallery(self, scraper_id, gallery):

        if not isinstance(gallery, dict) or not gallery.get("id"):
            log.warning('Unexpected Object passed to scrape_single_gallery')
            log.warning(f'Type: {type(gallery)}')
            log.warning(f'{gallery}')
        
        query = """query ScrapeSingleGallery($source: ScraperSourceInput!, $input: ScrapeSingleGalleryInput!) {
           scrapeSingleGallery(source: $source, input: $input) {
              ...scrapedGallery
            }
          }
        """
        variables = {
            "source":{
                "scraper_id": scraper_id
            },
            "input":{
                "gallery_id": gallery["id"],
                "gallery_input": {
                    "title": gallery["title"],
                    "details": gallery["details"],
                    "url": gallery["url"],
                    "date": gallery["date"]
                }
            }
        }

        result = self.__callGraphQL(query, variables)
        if not result:
            return None
        scraped_gallery_list = result["scrapeSingleGallery"]
        if len(scraped_gallery_list) == 0:
            return None
        else:
            return scraped_gallery_list[0]

    def scrape_single_performer(self, scraper_id, performer):

        if not isinstance(performer, dict) or not performer.get("id"):
            log.warning('Unexpected Object passed to scrape_single_gallery')
            log.warning(f'Type: {type(performer)}')
            log.warning(f'{performer}')
        
        query = """query ScrapeSinglePerformer($scraper_id: ID!, $performer: ScrapedPerformerInput!) {
           scrapeSinglePerformer(scraper_id: $scraper_id, performer: $performer) {
              ...scrapedPerformer
            }
          }
        """
        variables = {
            "source":{
                "scraper_id": scraper_id
            },
            "input":{
                "performer_id": performer["id"],
                "performer_input": {
                    "name": performer["name"],
                    "url": performer["url"]
                }
            }
        }

        result = self.__callGraphQL(query, variables)
        if not result:
            return None
        scraped_performer_list = result["scrapeSinglePerformer"]
        if len(scraped_performer_list) == 0:
            return None
        else:
            return scraped_performer_list[0]

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

stash_gql_fragments = {
    "scrapedScene":"""
        fragment scrapedScene on ScrapedScene {
          title
          details
          url
          date
          image
          file{
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
          studio{
            ...scrapedStudio
            __typename
          }
          tags{
            ...scrapedTag
            __typename
          }
          performers{
            ...scrapedPerformer
            __typename
          }
          movies{
            ...scrapedMovie
            __typename
          }
          remote_site_id
          duration
          fingerprints{
            algorithm
            hash
            duration
            __typename
          }
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
    "stashSceneUpdate":"""
        fragment stashSceneExit on Scene {
            id
            title
            details
            url
            date
            rating
            gallery_ids
            studio_id
            performer_ids
            movies
            tag_ids
            stash_ids
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
            }
            image_count
            tags {
              ...stashTag
            }
          }
          performers {
            ...stashPerformer
          }
          studio{
            ...stashStudio
          }
          stash_ids{
            endpoint
            stash_id
          }
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
            scene
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
            }
        }
    """
}