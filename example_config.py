from stashapi.stash_types import StashItem

# Create missing performers/tags/studios/movies
# Default: False (Prevent Stash from getting flooded with scraped values)
create_missing_performers = False
create_missing_tags = False
create_missing_studios = False
create_missing_movies = False

# url scrape config, comment out unwanted scrapes
BULK_URL = [
   StashItem.SCENE,
   StashItem.GALLERY,
   StashItem.MOVIE,
   # StashItem.PERFORMER,
]
# fragment scrape config, comment out unwanted scrapes
FRAGMENT_SCRAPE = [
   # StashItem.SCENE, # Use scene tagger or identify task for a better experience
   StashItem.GALLERY,
   StashItem.MOVIE,
   # StashItem.PERFORMER, # Use performer tagger
]

# Delay between web requests (seconds)
EXTERNAL_WEB_REQUEST_DELAY = 2.5

# Name of the tag, that will be used for selecting scenes for bulk url scraping
BULK_URL_CONTROL_TAG = "[BULK] Scrape URL"

# Prefix of all fragment scraper tags
FRAGMENT_SCRAPE_PREFIX = "[BULK] "