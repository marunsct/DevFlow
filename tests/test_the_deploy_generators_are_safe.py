"""What the deployment generators emit, checked rather than assumed.

§4.1 of `docs/harness-hardening-plan-part3.md` found four defects in
`src/app/deploy/`, all of which would ship the moment the generators were
wired into the workflow - which ADR-0003 decided to do. They are fixed here so
that wiring is not the thing that ships them.

The through-line is that the harness refuses each of these patterns everywhere
it can already reach. `docker-compose.yml` will not start without a real
password; `seeding.py` rejects `ext::` git transports because a URL should not
be able to execute code; `sandbox.py` refuses `python -c` for the same reason.
Then these generators wrote a plaintext credential, a root image, and
`curl | sh` into files that run on every push of the product they built.
"""

from __future__ import annotations

import pytest

from app.deploy.ci_generator import CIGenerator
from app.deploy.compose_generator import ComposeGenerator
from app.deploy.docker_generator import (
    SUPPORTED_LANGUAGES,
    DockerGenerator,
    UnsupportedLanguage,
)


class _Stack:
    def __init__(self, language, framework=None, database=None):
        self.language = language
        self.framework = framework
        self.database = database


def _dockerfile(tmp_path, language, framework=None) -> str:
    DockerGenerator(str(tmp_path), _Stack(language, framework)).generate()
    return (tmp_path / "Dockerfile").read_text()


class TestNoImageRunsAsRoot:
    @pytest.mark.parametrize(
        "language,framework",
        [
            ("python", None),
            ("node", None),
            ("typescript", "react"),
            ("go", None),
            ("java", None),
        ],
    )
    def test_every_template_drops_privilege(self, tmp_path, language, framework):
        content = _dockerfile(tmp_path, language, framework)

        assert "USER " in content, f"{language} image runs as root"
        # The USER must come after the install, or the build cannot write.
        assert content.rindex("USER ") > content.rindex("COPY ")

    def test_the_user_is_not_root(self, tmp_path):
        content = _dockerfile(tmp_path, "python")
        assert "USER root" not in content


class TestNothingUnwantedIsCopiedIn:
    def test_a_dockerignore_is_written_beside_the_dockerfile(self, tmp_path):
        _dockerfile(tmp_path, "node")
        assert (tmp_path / ".dockerignore").is_file()

    @pytest.mark.parametrize(
        "entry", ["node_modules", ".env", ".git", "__pycache__", ".venv"]
    )
    def test_the_things_that_break_or_leak_are_excluded(self, tmp_path, entry):
        _dockerfile(tmp_path, "node")
        ignored = (tmp_path / ".dockerignore").read_text().split()
        assert entry in ignored


class TestAnUnknownLanguageIsRefused:
    """The stack selector can choose eleven languages; this knows four."""

    @pytest.mark.parametrize("language", ["rust", "csharp", "ruby", "php", "elixir"])
    def test_it_raises_rather_than_writing_a_comment(self, tmp_path, language):
        with pytest.raises(UnsupportedLanguage) as raised:
            DockerGenerator(str(tmp_path), _Stack(language)).generate()

        assert language in str(raised.value)
        assert not (tmp_path / "Dockerfile").exists(), (
            "a Dockerfile that builds nothing is worse than none"
        )

    def test_the_message_names_what_is_supported(self, tmp_path):
        with pytest.raises(UnsupportedLanguage) as raised:
            DockerGenerator(str(tmp_path), _Stack("rust")).generate()
        assert "python" in str(raised.value) and "go" in str(raised.value)

    def test_an_empty_language_is_refused_too(self, tmp_path):
        with pytest.raises(UnsupportedLanguage):
            DockerGenerator(str(tmp_path), _Stack("")).generate()

    def test_every_supported_language_really_renders(self, tmp_path):
        for language in sorted(SUPPORTED_LANGUAGES):
            content = _dockerfile(tmp_path, language)
            assert "FROM " in content, f"{language} rendered nothing"
            assert "Unsupported language" not in content


class TestNoDefaultCredential:
    @pytest.mark.parametrize("database", ["postgres", "mysql"])
    def test_a_password_comes_from_the_environment(self, tmp_path, database):
        ComposeGenerator(str(tmp_path), _Stack("python", database=database)).generate()
        content = (tmp_path / "docker-compose.yml").read_text()

        assert "PASSWORD: password" not in content
        assert ":?" in content, "a missing credential must stop the file, not default"

    def test_it_names_the_variable_to_set(self, tmp_path):
        ComposeGenerator(str(tmp_path), _Stack("python", database="postgres")).generate()
        content = (tmp_path / "docker-compose.yml").read_text()
        assert "set POSTGRES_PASSWORD in .env" in content


class TestNothingIsPipedFromTheInternetIntoAShell:
    def test_the_ci_installs_uv_from_a_pinned_action(self, tmp_path):
        CIGenerator(str(tmp_path), _Stack("python")).generate()
        content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()

        assert "curl" not in content or "| sh" not in content
        assert "astral-sh/setup-uv@v5" in content

    def test_no_generator_emits_a_curl_pipe_shell(self):
        """Checked across the templates, not just the one branch that had it."""
        import inspect

        from app.deploy import ci_generator, compose_generator, docker_generator

        for module in (ci_generator, compose_generator, docker_generator):
            source = inspect.getsource(module)
            # The docstring quotes the line it replaced; the template must not.
            body = source.split('"""', 2)[-1]
            assert "| sh" not in body, f"{module.__name__} pipes into a shell"
            assert "| bash" not in body
