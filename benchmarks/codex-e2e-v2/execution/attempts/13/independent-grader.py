from pathlib import Path
import funcy
assert Path(funcy.__file__).resolve().is_relative_to(Path.cwd().resolve())
from funcy import first
assert first("xyz") == "x"
assert first([]) is None
assert first([None, 2]) is None
assert first([0, 1]) == 0
assert first([False, True]) is False
source = iter([7, 8, 9])
assert first(source) == 7
assert next(source) == 8
assert first(iter(())) is None
source = (value for value in range(3))
assert first(source) == 0
assert next(source) == 1
print("independent Funcy first contract passed")
