"""The C# pack says how a unit test gives the service its own data folder (found on the language sweep).

Measured on two of three C# runs: the unit tests shipped not compiling, each time from a hand-made "isolated" test
factory for a data folder per test (a factory class with no `CreateClient`, `AddInMemoryCollection` the test project
did not have). The guide said to use `WebApplicationFactory<Program>`, not how to give it a folder of its own.
"""
from __future__ import annotations

import re

from app.stacks.packs import csharp_aspnet_api as pack

BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_guide_names_the_one_way_and_warns_off_a_factory_of_its_own():
    guide = pack.GUIDE
    assert 'builder.Configuration["DATA_DIR"]' in guide
    assert 'WithWebHostBuilder(b => b.UseSetting("DATA_DIR"' in guide
    assert "factory class" in guide
    assert not BANNED.search(guide)
