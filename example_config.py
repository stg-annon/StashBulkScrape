
# Create missing performers/tags/studios/movies
# Default: False (Prevent Stash from getting flooded with weird values)
create_missing_performers = False
create_missing_tags = False
create_missing_studios = False
create_missing_movies = False

# url scrape config
bulk_url_scrape_scenes = True
bulk_url_scrape_galleries = True
bulk_url_scrape_movies = True
bulk_url_scrape_performers = False

# fragment scrape config
fragment_scrape_scenes = True
fragment_scrape_galleries = True
fragment_scrape_movies = True
fragment_scrape_performers = False

# stashbox scrape config
stashbox_target = "stashdb.org"
stashbox_submit_fingerprints = False

# Delay between web requests (seconds)
delay = 5.0

# Name of the tag, that will be used for selecting scenes for bulk url scraping
bulk_url_control_tag = "blk_scrape_url"

# stash box control tag
bulk_stash_box_control_tag = "blk_scrape_stashbox"

# Prefix of all fragment scraper tags
scrape_with_prefix = "blk_scrape_"