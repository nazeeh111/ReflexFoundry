from toolz import first
assert first('xyz') == 'x'
assert first([None, 2]) is None
source = iter([7, 8, 9])
assert first(source) == 7
assert next(source) == 8
assert first(x for x in range(4)) == 0
try:
    first([])
except StopIteration:
    pass
else:
    raise AssertionError('first(empty) must raise StopIteration')
print('public-contract grader passed')
