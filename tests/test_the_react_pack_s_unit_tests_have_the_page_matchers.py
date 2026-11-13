"""The React pack ships the page matchers its unit tests reach for: `@testing-library/jest-dom`, registered for vitest.

Measured: 6 of 7 React runs' unit tests used `toBeInTheDocument` and the like; five runs' agents added the package by
hand, and one run's unit suite failed 16 of 26 with "Invalid Chai property: toBeInTheDocument" on a building product.
"""
import json

from app.stacks.packs import browser_react


def test_the_package_its_setup_and_the_config_that_loads_it():
    files = browser_react.PACK.files
    dev = json.loads(files["package.json"].replace("{{project}}", "p"))["devDependencies"]
    assert "@testing-library/jest-dom" in dev
    assert files["vitest.setup.ts"].strip() == "import '@testing-library/jest-dom/vitest';"
    assert "setupFiles: ['./vitest.setup.ts']" in files["vite.config.ts"]
    assert "vitest.setup.ts" in json.loads(files["tsconfig.json"])["include"]
