import sys, json


import bulk_scrape
import stashbox_update
import utils.log as log
from utils.stash import StashInterface
from utils.stashbox import StashBoxInterface


def main():
	json_input = json.loads(sys.stdin.read())
	output = {}
	
	mode_arg = json_input['args']['mode']

	try:
		sbox = StashBoxInterface({"Logger": log})
		stash_connection = json_input["server_connection"]
		stash_connection["Logger"] = log
		stash = StashInterface(stash_connection)

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