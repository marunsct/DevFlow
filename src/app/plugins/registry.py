from typing import List
from app.server.plugin_store import PluginStore

def get_plugin_instructions(stack_keywords: List[str]) -> str:
    """Returns aggregated instructions for the given stack keywords from the database."""
    instructions = []
    
    store = PluginStore.shared()
    
    # A block several modules share is given once. The seed appends the same
    # JavaScript testing notes to `javascript`, `typescript`, `node` and every
    # JavaScript framework, so a stack naming two of them carried the block
    # twice - 1,500 characters of the specialist prompt said again.
    given: set[str] = set()
    for keyword in stack_keywords:
        key = keyword.lower()
        content = store.get_instructions(key)
        if not content:
            continue
        blocks = []
        for block in content.strip().split("\n\n"):
            normalised = " ".join(block.split())
            if normalised and normalised not in given:
                given.add(normalised)
                blocks.append(block.strip())
        if blocks:
            instructions.append(f"[{key.upper()} MODULE]\n" + "\n\n".join(blocks))
    
    if not instructions:
        return ""
    
    return "\n\n=== FRAMEWORK CAPABILITIES ===\n" + "\n\n".join(instructions)


