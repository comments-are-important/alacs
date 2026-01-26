import math
import sys

from . import TimedALACS, TimedRuamel, unit_tests
from .equals import diff_any, diff_translate, diff_ruamel
from .generate import Random

if unit_tests.problem_count():
    sys.exit()

random = Random()
memory = TimedALACS()
ruamel = TimedRuamel(memory)

loops = range(1000)
progress = -1
for loop in loops:
    pct = math.floor(loop * 100.0 / loops.stop)
    if pct != progress:
        progress = pct
        print(f"\r{progress}%", end="")

    file = memory.separated(random.file())

    if diff_any(file.alacs, memory.file(file.python)):
        sys.exit("FAILED to python and back")

    with memory.encode(file.alacs) as buffer:
        if diff_any(file, memory.separated(memory.decode(buffer))):
            sys.exit("FAILED encode then decode")

    yaml = ruamel.translate(file.alacs)
    if diff_translate(file, yaml):
        sys.exit("FAILED YAML translate")
    if diff_ruamel(yaml, ruamel.roundtrip(yaml)):
        print("--- # was")
        print(file.yaml.decode())
        print("--- # now")
        print(bytes(ruamel).decode())
        sys.exit("FAILED YAML roundtrip")

print("\r100%")
memory.timers()
ruamel.timers()
