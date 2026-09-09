"""Model routing with health tracking.

Scoped per provider configuration rather than to one process-wide singleton.
The previous ``get_instance()`` returned a single shared router whose model list
was replaced by ``set_models`` on *every* agent construction - once per node, per
invoke - so two runs with different provider settings in the same worker process
overwrote each other's models and reset each other's health state.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL_SECONDS = 60


class ModelRouter:
    """Holds one provider configuration's models and their health."""

    _registry: Dict[str, "ModelRouter"] = {}
    _registry_lock = threading.Lock()

    def __init__(self, key: str = "default") -> None:
        self.key = key
        self._models: List[Dict[str, Any]] = []
        self._health: Dict[int, bool] = {}
        self._last_check = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @staticmethod
    def configuration_key(settings: Any) -> str:
        """Identify a provider configuration without including any secret."""
        return "|".join(
            str(getattr(settings, attr, ""))
            for attr in ("llm_provider", "openai_base_url", "model_name")
        )

    @classmethod
    def for_configuration(cls, settings: Any, models: List[Dict[str, Any]]) -> "ModelRouter":
        """Return the router for this configuration, creating it if needed."""
        key = cls.configuration_key(settings)
        with cls._registry_lock:
            router = cls._registry.get(key)
            if router is None:
                router = cls(key)
                cls._registry[key] = router
        router.set_models(models)
        return router

    @classmethod
    def get_instance(cls) -> "ModelRouter":
        """Back-compatible accessor for the default configuration."""
        with cls._registry_lock:
            return cls._registry.setdefault("default", cls("default"))

    @classmethod
    def all_routers(cls) -> Dict[str, "ModelRouter"]:
        with cls._registry_lock:
            return dict(cls._registry)

    @classmethod
    def reset(cls) -> None:
        with cls._registry_lock:
            cls._registry.clear()

    # ------------------------------------------------------------------
    # Models and health
    # ------------------------------------------------------------------

    def set_models(self, models: List[Dict[str, Any]]) -> None:
        """Install the model list, preserving health for unchanged entries."""
        with self._lock:
            previous = {info["name"]: self._health.get(i, True) for i, info in enumerate(self._models)}
            self._models = models
            self._health = {i: previous.get(info["name"], True) for i, info in enumerate(models)}

    def check_health(self, force: bool = False) -> None:
        """Ping each model, at most once per interval.

        Blocking by design - callers must run it off the event loop.
        """
        now = time.time()
        with self._lock:
            if not force and now - self._last_check < HEALTH_CHECK_INTERVAL_SECONDS:
                return
            self._last_check = now
            models = list(enumerate(self._models))

        for index, info in models:
            try:
                info["model"].invoke([HumanMessage(content="ping")], config={"tags": ["health_check"]})
                healthy = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Model %s failed its health check: %s", info.get("name"), exc)
                healthy = False
            with self._lock:
                self._health[index] = healthy

    def get_healthy_model(self) -> BaseChatModel:
        """Return the primary model with the remaining healthy ones as fallbacks.

        Health is not probed inline: a synchronous ping on every agent
        construction would add a full round trip to each graph node.
        """
        with self._lock:
            if not self._models:
                raise ValueError("No models are configured for this router.")
            healthy = [info["model"] for i, info in enumerate(self._models) if self._health.get(i, True)]
            if not healthy:
                # Everything is marked unhealthy; try the primary anyway rather
                # than failing the run outright.
                healthy = [self._models[0]["model"]]

        primary, *fallbacks = healthy
        return primary.with_fallbacks(fallbacks) if fallbacks else primary

    def status(self) -> Dict[str, str]:
        with self._lock:
            return {
                info["name"]: "healthy" if self._health.get(i, True) else "unhealthy"
                for i, info in enumerate(self._models)
            }


def get_router_status() -> Dict[str, Any]:
    """Health of every configured router. Blocking; run it in a threadpool."""
    result: Dict[str, Any] = {}
    for key, router in ModelRouter.all_routers().items():
        router.check_health(force=True)
        result[key] = router.status()
    return result or {"detail": "No models have been configured yet."}


__all__ = ["ModelRouter", "get_router_status"]
