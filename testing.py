import datetime

import bulk_scrape as bulk_scrape

from stashapi.stashapp import StashInterface

stash = StashInterface({"host":"10.0.2.99"})
scraper = bulk_scrape.ScrapeController(stash)

print("Start Testing")

while True:
    print(datetime.datetime.now())
    scraper.wait()
