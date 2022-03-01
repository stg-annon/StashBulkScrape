import re
from datetime import datetime

# Capitalize each word in a string
def caps_string(string, delim=" "):
	string = string.strip()
	return delim.join(x.capitalize() for x in string.split(delim))

# returns dictionary where values are not None
def clean_dict(to_clean):
	return {k:v for k,v in to_clean.items() if v and "__" not in k}

def parse_timestamp(ts, format="%Y-%m-%dT%H:%M:%S%z"):
	ts = re.sub(r'\.\d+', "", ts) #remove fractional seconds
	return datetime.strptime(ts, format)
	
def merge_tags(old_tag_ids, new_tag_ids, ctrl_tag_ids=[]):
	merged_tags = set()
	merged_tags.update([t for t in old_tag_ids if t not in ctrl_tag_ids])
	if new_tag_ids:
		merged_tags.update(new_tag_ids)
	return list(merged_tags)
