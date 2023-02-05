from stashapi.types import StashItem

# Create missing performers/tags/studios/movies
# Default: False (Prevent Stash from getting flooded with weird values)
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
   StashItem.SCENE,
   StashItem.GALLERY,
   StashItem.MOVIE,
   # StashItem.PERFORMER,
]

# stashbox scrape config
stashbox_target = "stashdb.org"
stashbox_submit_fingerprints = False

# Delay between web requests (seconds)
EXTERNAL_WEB_REQUEST_DELAY = 5.0

# tag to add to stash items that are not up to date with stashbox_target
STASHBOX_UPDATE_AVAILABLE_TAG = "STASHBOX_UPDATE"
# Name of the tag, that will be used for selecting scenes for bulk url scraping
BULK_URL_CONTROL_TAG = "blk_scrape_url"
# stash box control tag
BULK_STASHBOX_CONTROL_TAG = "blk_scrape_stashbox"

# Prefix of all fragment scraper tags
SCRAPE_WITH_PREFIX = "blk_scrape_"