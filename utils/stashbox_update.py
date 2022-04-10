
import datetime, math

import config
from utils.tools import parse_timestamp

import stashapi.log as log
from stashapi.stashbox import StashBoxInterface
from stashapi.stashapp import StashInterface
from stashapi.types import BulkUpdateIdMode

def bulk_stashbox_scrape(self):
    stashbox = None
    for i, sbox in enumerate(self.client.list_stashboxes()):
        if config.stashbox_target in sbox.endpoint:
            stashbox = sbox
            stashbox.index = i

    if not stashbox:
        log.error(f'Could not find a stash-box config for {config.stashbox_target}')
        return None

    tag_id = self.client.find_tag_id( config.bulk_stash_box_control_tag )
    scenes = self.client.find_scenes(f={
        "tags": {
            "value": [tag_id],
            "depth": 0,
            "modifier": "INCLUDES"
        }
    })

    log.info(f'Scraping {len(scenes)} items from stashbox')

    scene_ids = [i.get('id') for i in scenes if i.get('id')]
    scraped_data  = self.client.stashbox_scene_scraper(scene_ids, stashbox_index=stashbox.index)

    log.info(f'found {len(scraped_data)} results from stashbox')

    updated_scene_ids = self.__update_scenes_with_stashbox_data(scenes, scraped_data, stashbox)

    log.info(f'Scraped {len(updated_scene_ids)} scenes from stashbox')

    if len(updated_scene_ids) > 0 and config.stashbox_submit_fingerprints:
        log.info(f'Submitting scene fingerprints to stashbox')
        success = self.client.stashbox_submit_scene_fingerprints(updated_scene_ids, stashbox_index=stashbox.index)
        if success:
            log.info(f'Fingerprints Submission Successful')
        else:
            log.warning(f'Failed to submit fingerprints')

    return None


def get_scenes_with_stash_id(stash:StashInterface, page=1, per_page=60):
    query = """
    query FindScenes($filter: FindFilterType, $scene_filter: SceneFilterType, $scene_ids: [Int!]) {
        findScenes(filter: $filter, scene_filter: $scene_filter, scene_ids: $scene_ids) {
            count
            scenes {
                id
                updated_at
                stash_ids { endpoint stash_id }
            }
        }
    }
    """
    vars = {
        "filter":{
            "page": page,
            "per_page": per_page
        },
        "scene_filter":{
            "stash_id": {
                "modifier": "NOT_NULL",
                "value": ""
            }
        }
    }
    return stash.call_gql(query, vars)["findScenes"]

def find_updates(stash:StashInterface, sbox:StashBoxInterface, scenes_per_page=60, max_page=None):

    if config.STASHBOX_UPDATE_AVAILABLE_TAG:
        stashbox_update_tag_id = stash.find_tag(config.STASHBOX_UPDATE_AVAILABLE_TAG, create=True).get("id", None)


    scenes_with_update = []
    scene_count = 0
    processed_scenes = 0
    total_scenes = 0

    def check_scenes(scenes):
        nonlocal processed_scenes, scene_count, scenes_with_update
        for scene in scenes:
            try:
                if scene_has_update(sbox, scene):
                    scenes_with_update.append(scene["id"])
                    add_tracking_tag(stash, scene["id"], stashbox_update_tag_id)
            except:
                log.warning(f"Issue checking scene {scene['id']}")
                pass
            processed_scenes += 1
            log.progress(processed_scenes/total_scenes)
            # log.info(f"{processed_scenes}/{total_scenes}")

    resp = get_scenes_with_stash_id(stash, page=1, per_page=scenes_per_page)
    scene_count = resp["count"]

    if max_page:
        total_scenes = scenes_per_page*max_page
    else:
        total_scenes = scene_count
    
    check_scenes(resp["scenes"])

    for page_number in range(2, math.ceil(scene_count/scenes_per_page)):
        if max_page and page_number > max_page:
            break
        resp = get_scenes_with_stash_id(stash, page=page_number, per_page=scenes_per_page)
        check_scenes(resp["scenes"])
    
    log.info(f"{len(scenes_with_update)} out of {total_scenes} scenes need to be updated")
    return scenes_with_update

def find_tag_updates(stash:StashInterface):
    if not config.STASHBOX_UPDATE_AVAILABLE_TAG:
        return []
    control_tag = stash.find_tag(config.STASHBOX_UPDATE_AVAILABLE_TAG)
    if not control_tag:
        return []

    query = """
    query FindScenes($filter: FindFilterType, $scene_filter: SceneFilterType, $scene_ids: [Int!]) {
        findScenes(filter: $filter, scene_filter: $scene_filter, scene_ids: $scene_ids) {
            count
            scenes {
                id
            }
        }
    }
    """
    vars = {
        "filter":{
            "per_page": -1
        },
        "scene_filter":{
            "tags": {
                "depth": 0,
                "modifier": "INCLUDES_ALL",
                "value": [
                    control_tag["id"]
                ]
            }
        }
    }

    result = stash.call_gql(query, vars)
    return [s["id"] for s in result["findScenes"]["scenes"]]
    

def scene_has_update(sbox:StashBoxInterface, scene, allowed_update_at_diff=30):
    stash_ids = [sid["stash_id"] for sid in scene["stash_ids"] if sid["endpoint"] == sbox.endpoint]
    if len(stash_ids) > 1:
        log.warning("scene has multuple stash_ids for this endpoint")
        return False

    sbox_updated_at = sbox.get_scene_last_updated(stash_ids[0])

    stash_updated_at = parse_timestamp(scene["updated_at"]) 
    sbox_updated_at = parse_timestamp(sbox_updated_at)

    delta = sbox_updated_at - stash_updated_at
    if delta < datetime.timedelta(seconds=allowed_update_at_diff):
        # log.debug("scene is up to date")
        return False
    elif stash_updated_at > sbox_updated_at:
        # log.debug("scene info is newer than Stash-Box")
        return False
    elif stash_updated_at < sbox_updated_at:
        log.info(f"scene {scene['id']} needs update Δ:{delta}")
        return True


def add_tracking_tag(stash:StashInterface, scene_id, tag_id):
    if config.STASHBOX_UPDATE_AVAILABLE_TAG:
        stash.update_scenes({
            "ids": [scene_id],
            "tag_ids": {
                "ids": [tag_id],
                "mode": "ADD"
            }
        })

def update_scenes(stash:StashInterface, scene_ids=None):

    if scene_ids == None:
        scene_ids = find_tag_updates(stash)
    
    stash.stashbox_identify_task(scene_ids)

    if config.STASHBOX_UPDATE_AVAILABLE_TAG:
        stashbox_update_tag_id = stash.find_tag(config.STASHBOX_UPDATE_AVAILABLE_TAG, create=True).get("id", None)
        stash.update_scenes({
            "ids": scene_ids,
            "tag_ids": {
                "ids": [stashbox_update_tag_id],
                "mode": BulkUpdateIdMode.REMOVE.value
            }
        })