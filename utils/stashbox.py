import re, sys, requests
from tkinter import Variable
from collections import defaultdict


STASHDB_TEST_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJhZTA1NmQ0ZC0wYjRmLTQzNmMtYmVhMy0zNjNjMTQ2MmZlNjMiLCJpYXQiOjE1ODYwNDAzOTUsInN1YiI6IkFQSUtleSJ9.5VENvrLtJXTGcdOhA0QC1SyPQ59padh1XiQRDQelzA4"

class StashBoxInterface:
	port = None
	url = None
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

		self.endpoint = conn.get('Endpoint', "https://stashdb.org/graphql")
		self.headers['ApiKey'] = conn.get('ApiKey', STASHDB_TEST_KEY)
		try:
			# test query to check connection
			r = self.__callGraphQL("query Me{me {name email}}")
			log.info(f'Connected to "{self.endpoint}" as {r["me"]["name"]} ({r["me"]["email"]})')
		except Exception:
			log.error(f"Could not connect to Stash-Box at {self.endpoint}")
			sys.exit()

		self.fragments = fragments
		self.fragments.update(gql_fragments)


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

		response = requests.post(self.endpoint, json=json_request, headers=self.headers, cookies=self.cookies)
		
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

	def get_scene_last_updated(self, scene_id):
		query = """query sceneLastUpdated($id: ID!) {
			findScene(id: $id) {
				updated
			}
		}"""

		result = self.__callGraphQL(query, {"id": scene_id})
		return result["findScene"]["updated"]




gql_fragments = {
	"URLFragment":"""fragment URLFragment on URL {
		url
		type
	}""",
	"ImageFragment":"""fragment ImageFragment on Image {
		id
		url
		width
		height
	}""",
	"StudioFragment":"""fragment StudioFragment on Studio {
		name
		id
		urls {
			...URLFragment
		}
		images {
			...ImageFragment
		}
	}""",
	"TagFragment":"""fragment TagFragment on Tag {
		name
		id
	}""",
	"FuzzyDateFragment":"""fragment FuzzyDateFragment on FuzzyDate {
		date
		accuracy
	}""",
	"MeasurementsFragment":"""fragment MeasurementsFragment on Measurements {
		band_size
		cup_size
		waist
		hip
	}""",
	"BodyModificationFragment":"""fragment BodyModificationFragment on BodyModification {
		location
		description
	}""",
	"PerformerFragment":"""fragment PerformerFragment on Performer {
		id
		name
		disambiguation
		aliases
		gender
		merged_ids
		urls {
			...URLFragment
		}
		images {
			...ImageFragment
		}
		birthdate {
			...FuzzyDateFragment
		}
		ethnicity
		country
		eye_color
		hair_color
		height
		measurements {
			...MeasurementsFragment
		}
		breast_type
		career_start_year
		career_end_year
		tattoos {
			...BodyModificationFragment
		}
		piercings {
			...BodyModificationFragment
		}
	}""",
	"PerformerAppearanceFragment":"""fragment PerformerAppearanceFragment on PerformerAppearance {
		as
		performer {
			...PerformerFragment
		}
	}""",
	"FingerprintFragment":"""fragment FingerprintFragment on Fingerprint {
		algorithm
		hash
		duration
	}""",
	"SceneFragment":"""fragment SceneFragment on Scene {
		id
		title
		details
		duration
		date
		urls {
			...URLFragment
		}
		images {
			...ImageFragment
		}
		studio {
			...StudioFragment
		}
		tags {
			...TagFragment
		}
		performers {
			...PerformerAppearanceFragment
		}
		fingerprints {
			...FingerprintFragment
		}
	}"""
}