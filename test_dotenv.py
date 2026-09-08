import os
import dotenv

dotenv_file = os.path.join(os.getcwd(), ".env")
with open(dotenv_file, "w") as f:
    f.write("OPENAI_MODEL=gpt-4\n")

dotenv.set_key(dotenv_file, "OPENAI_MODEL", "claude-3")
print("after set_key", open(dotenv_file).read())

dotenv.load_dotenv(dotenv_file, override=True)
print("os.environ", os.environ.get("OPENAI_MODEL"))
