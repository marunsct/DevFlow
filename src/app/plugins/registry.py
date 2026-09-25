from typing import List
from app.server.plugin_store import PluginStore

def get_plugin_instructions(stack_keywords: List[str]) -> str:
    """Returns aggregated instructions for the given stack keywords from the database."""
    instructions = []
    
    store = PluginStore.shared()
    
    for keyword in stack_keywords:
        key = keyword.lower()
        content = store.get_instructions(key)
        if content:
            instructions.append(f"[{key.upper()} MODULE]\n" + content.strip())
    
    if not instructions:
        return ""
    
    return "\n\n=== FRAMEWORK CAPABILITIES ===\n" + "\n\n".join(instructions)


