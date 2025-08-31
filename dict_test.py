import json

keys = {}
keys["up"] = False
keys["down"] = True
keys["rotate_left"] = False
keys["rotate_right"] = False
keys["left"] = True
keys["right"] = False

print(keys)
json_string = json.dumps(keys)
encoded_string = json_string.encode()

decoded_json = encoded_string.decode(encoding="utf-8")
decoded_dict = json.loads(decoded_json)
print(decoded_dict)