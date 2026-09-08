import os
from dotenv import load_dotenv
open(".env.test", "w").write("VAR='value'\n")
load_dotenv(".env.test", override=True)
print(repr(os.environ.get("VAR")))
