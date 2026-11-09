"""A command a stage runs sees the relative imports Node will load (behind `EXTENSIONS_BEFORE_A_RUN`).

`app.stacks.import_extensions` puts the `.ts` on an import the model left without it, but only when the harness measures
the product. Measured on a small-model run of the pack that Node runs itself: the drafted tests imported
`../src/datastore.js` where `src/datastore.ts` existed, and the two testing work orders ran `npm test` against that,
read ERR_MODULE_NOT_FOUND, and spent 55 calls - 30 of them refused - writing a `datastore.js` that re-exports the `.ts`
and editing the imports of files another work order owned. The harness then added the extensions itself before its
own first measurement. Which file such an import means is not a judgement, so the same repair is made before any
command a stage runs, and the command's result says it was.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("EXTENSIONS_BEFORE_A_RUN", ON_BY_DEFAULT)


def put_right(repo_root: str | Path) -> str:
    """Add the extensions the scaffolded pack needs; the note for the command's result, or "". Never raises."""
    if not enabled():
        return ""
    try:
        from app.stacks import contract, import_extensions

        found = contract.the_pack(repo_root)
        if found is None or not contract.scaffolded(found[1]):
            return ""
        pack, record = found
        extension = getattr(pack, "relative_import_extension", "")
        project = str(record.get("project") or "")
        if not extension or not project:
            return ""
        done = import_extensions.put_the_extensions_on(Path(repo_root) / project, extension)
    except Exception:  # noqa: BLE001 - a repair that cannot run changes nothing
        logger.debug("Import extensions not put right before a command", exc_info=True)
        return ""
    if not done:
        return ""
    logger.info("Before a command: %s", "; ".join(done))
    return (f"Before this command ran, in `{project}/`: {' '.join(done)} Node loads a relative import exactly as "
            f"written, so name the `{extension}` file itself.")
