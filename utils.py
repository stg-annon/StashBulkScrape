# Capitalize each word in a string
def caps_string(string, delim=" "):
  string = string.strip()
  return delim.join(x.capitalize() for x in string.split(delim))


def clean_dict(to_clean):
  cleaned = {}
  for attr, value in to_clean.items():
    if not value:
      continue
    cleaned[attr] = value
  return cleaned