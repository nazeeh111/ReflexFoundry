from pathlib import Path
import cachetools
assert Path(cachetools.__file__).resolve().is_relative_to(Path.cwd().resolve())
from cachetools import Cache
cache = Cache(maxsize=4)
cache["different"] = 17
cache["none"] = None
cache["zero"] = 0
cache["false"] = False
before = (len(cache), cache.currsize)
assert cache["different"] == 17
assert cache["none"] is None
assert cache["zero"] == 0
assert cache["false"] is False
assert (len(cache), cache.currsize) == before
try:
    cache["absent"]
except KeyError as error:
    assert error.args == ("absent",)
else:
    raise AssertionError("missing default cache key must raise KeyError")
class Missing(Cache):
    def __missing__(self, key):
        calls.append(key)
        return ("fallback", key)
calls = []
custom = Missing(maxsize=2)
custom["stored"] = 23
assert custom["stored"] == 23
assert calls == []
before = (len(custom), custom.currsize)
assert custom["absent"] == ("fallback", "absent")
assert calls == ["absent"]
assert (len(custom), custom.currsize) == before
print("independent cachetools getitem contract passed")
