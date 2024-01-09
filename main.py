import sys, json

import bulk_scrape as bulk_scrape

import stashapi.log as log
from stashapi.stashapp import StashInterface

def main():
	json_input = json.loads(sys.stdin.read())
	
	MODE = json_input['args']['mode']

	try:
		stash_connection = {"logger":log}
		stash_connection.update(json_input["server_connection"])
		stash = StashInterface(stash_connection)

		scraper = bulk_scrape.ScrapeController(stash)

		if MODE == "create_tags":
			scraper.add_tags()
		if MODE == "remove_tags":
			scraper.remove_tags()
		if MODE == "url_scrape":
			scraper.bulk_url_scrape()
		if MODE == "fragment_scrape":
			scraper.bulk_fragment_scrape()
	except Exception as e:
		log.error(e)

	log.exit()
	
if __name__ == '__main__':
	main()