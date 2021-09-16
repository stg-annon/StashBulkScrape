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
        self.port = conn['Port']
        scheme = conn['Scheme']

        # Session cookie for authentication
        self.cookies = {
            'session': conn['SessionCookie']['Value']
        }

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
            if p.name.lower() == name.lower():
                return p
            if p.aliases and p.name.lower() in p.aliases.lower():
                return p

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
        return result.get('performerUpdate').get('id')


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
        return result['movieUpdate']['id']


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
            mutation SceneMarkerCreate($title: String!, $seconds: Float!, $scene_id: ID!, $primary_tag_id: ID!, $tag_ids: [ID!] = []) {
              sceneMarkerCreate(
                input: {title: $title, seconds: $seconds, scene_id: $scene_id, primary_tag_id: $primary_tag_id, tag_ids: $tag_ids}
              ) {
                id
                __typename
              }
            }
        """
        variables = {
          "tag_ids": tag_ids,
          "title": title,
          "seconds": seconds,
          "scene_id": scene_id,
          "primary_tag_id": primary_tag_id
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

    # Fragment Scrape
    def run_scene_scraper(self, scraper_id, scene):
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
    def run_gallery_scraper(self, gallery, scraper):
        
        query = """query ScrapeGallery($scraper_id: ID!, $gallery: GalleryUpdateInput!) {
           scrapeGallery(scraper_id: $scraper_id, gallery: $gallery) {
              ...scrapedGallery
            }
          }
        """
        variables = {
            "scraper_id": scraper,
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

    def run_performer_scraper(self, performer, scraper):
        
        query = """query ScrapePerformer($scraper_id: ID!, $performer: ScrapedPerformerInput!) {
           scrapePerformer(scraper_id: $scraper_id, performer: $performer) {
              ...scrapedPerformer
            }
          }
        """
        variables = {
            "scraper_id": scraper,
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
          }
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
          remote_site_id
          duration
          fingerprints{
            algorithm
            hash
            duration
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
            id
            name
            url
            stash_ids{
                endpoint
                stash_id
            }
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
    """
}