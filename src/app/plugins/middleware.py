import os
from typing import Any, Callable, List
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.plugins.registry import get_plugin_instructions
from app.server.plugin_store import PluginStore

def _extract_stack_keywords(repo_root: str) -> List[str]:
    stack_file = Path(repo_root) / "docs" / "technology_stack.md"
    if not stack_file.is_file():
        return []
    
    try:
        content = stack_file.read_text(encoding="utf-8")
        
        from app.config import load_settings
        settings = load_settings()
        
        # Step 1: Use a lightweight LLM call to extract the primary frameworks
        llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0
        )
        extract_prompt = "You are a tech stack analyzer. Read the provided technology_stack.md and return ONLY a comma-separated list of the core programming languages and frameworks it mandates (e.g. 'react, typescript, python, postgres'). Do not include tools or generic terms. Output exactly the comma-separated list."
        response = llm.invoke([
            SystemMessage(content=extract_prompt),
            HumanMessage(content=content)
        ])
        
        detected_frameworks = [f.strip().lower() for f in response.content.split(",")]
        
        store = PluginStore.shared()
        available_frameworks = store.get_all_framework_names()
        
        final_keywords = []
        for framework in detected_frameworks:
            if not framework:
                continue
            
            # Step 2: If the framework is NOT in the database, use LLM to generate rules!
            if framework not in available_frameworks:
                gen_prompt = f"Generate 4 bullet points of strict software engineering best practices for the '{framework}' framework or language. Focus on things like concurrency, security, and architecture. Output only the instructions."
                gen_response = llm.invoke([SystemMessage(content=gen_prompt)])
                store.update_instructions(framework, gen_response.content)
            
            final_keywords.append(framework)
            
        return final_keywords
    except Exception as e:
        return []

def build_plugin_instructions_middleware(repo_root: str) -> Any:
    from langchain.agents.middleware import AgentMiddleware

    class PluginInstructionsMiddleware(AgentMiddleware):
        """Append framework-specific plugin instructions to the system prompt."""
        name = "PluginInstructionsMiddleware"

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            messages = getattr(request, "messages", None)
            if not isinstance(messages, list) or not messages:
                return handler(request)
            
            # Extract stack once per call, as it might change
            keywords = _extract_stack_keywords(repo_root)
            if not keywords:
                return handler(request)
                
            plugin_instructions = get_plugin_instructions(keywords)
            if not plugin_instructions:
                return handler(request)

            try:
                # We modify the first message (System prompt)
                first_msg = messages[0]
                if isinstance(first_msg, dict) and first_msg.get("role") == "system":
                    new_msg = {**first_msg, "content": first_msg["content"] + "\n\n" + plugin_instructions}
                    new_messages = [new_msg] + messages[1:]
                    request = request.override(messages=new_messages)
            except Exception:  # noqa: BLE001
                pass

            return handler(request)

    return PluginInstructionsMiddleware()
