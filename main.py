import sys, json

import config
import utils.bulk_scrape as bulk_scrape
import utils.stashbox_update as stashbox_update

import stashapi.log as log
from stashapi.stashapp import StashInterface
from stashapi.stashbox import StashBoxInterface

def main():
	json_input = json.loads(sys.stdin.read())
	output = {}
	
	mode_arg = json_input['args']['mode']

	try:
		stash_connection = {"logger":log}
		stash_connection.update(json_input["server_connection"])
		stash = StashInterface(stash_connection)
		
		sbox_config = {"logger": log}
		sbox_config.update(stash.get_stashbox_connection(config.stashbox_target))
		sbox = StashBoxInterface(sbox_config)

		if "endpoint" not in sbox_config:
			log.warning(f'Could not source stash-box config for "{config.stashbox_target}"')

		scraper = bulk_scrape.ScrapeController(stash)

		match mode_arg:
			case "stashbox_find_updates":
				stashbox_update.find_updates(stash, sbox)
			case "stashbox_identify_tagged":
				stashbox_update.update_scenes(stash)
			case "create":
				scraper.add_tags()
			case "remove":
				scraper.remove_tags()
			case "url_scrape":
				scraper.bulk_url_scrape()
			case "fragment_scrape":
				scraper.bulk_fragment_scrape()
			case "stashbox_scrape":
				scraper.bulk_stashbox_scrape()
		


	except Exception:
		raise

	output["output"] = "ok"
	out = json.dumps(output)
	print(out + "\n")
	
if __name__ == '__main__':
	main()