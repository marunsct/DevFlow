"""The image each pack's commands run in when every command has a container of its own (LR.30).

In container mode (`SANDBOX_EXECUTION_MODE=container`) a command once got its
image from its executable alone: Node's, Python's, Go's or Rust's, else a bare
Debian. A pack whose acceptance suite runs under Playwright while its product
needs another toolchain could not pass there: the suite's web server ran the
product's `start.sh` (`cargo`, `dotnet`, `mvn`, `php`, `ruby`) inside the
Playwright image, `cargo nextest` was not in the Rust image, and Java, .NET,
PHP and Ruby fell to an image with no toolchain at all.

So each pack names one image holding its toolchain, its test runners, Node and
the browsers: the Playwright image itself for a pack that needs only Node, and
otherwise an image built from it by `scripts/loop/build_sandbox_images.sh`
from `deploy/sandbox-images/<toolchain>/Dockerfile`. The tag carries the
Playwright release every pack pins, so a new release names images that must be
built again rather than reusing ones whose browsers no longer match.
"""

from __future__ import annotations

from app.stacks.packs._javascript import PLAYWRIGHT

#: The Playwright release's own image: Node and the browsers, nothing else.
PLAYWRIGHT_IMAGE = f"mcr.microsoft.com/playwright:v{PLAYWRIGHT}-noble"

#: Where the Dockerfile of each built image lives, one folder per toolchain, from the repository root.
DOCKERFILES = "deploy/sandbox-images"

#: The prefix of every image the build script tags.
IMAGE_PREFIX = "harness-sandbox-"


def built_image(toolchain: str) -> str:
    """The tag `build_sandbox_images.sh` gives the image built from `DOCKERFILES/<toolchain>/Dockerfile`."""
    return f"{IMAGE_PREFIX}{toolchain}:pw{PLAYWRIGHT}"


NODE = PLAYWRIGHT_IMAGE
PYTHON = built_image("python")
GO = built_image("go")
RUST = built_image("rust")
JAVA = built_image("java")
DOTNET = built_image("dotnet")
PHP = built_image("php")
RUBY = built_image("ruby")
