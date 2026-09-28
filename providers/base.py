from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.models import (
    GenerationRequest,
    GenerationResponse,
)


class ProviderError(RuntimeError):
    pass


class ProviderTransientError(ProviderError):
    """A request can be retried without changing the submitted content."""


class ProviderResponseInterrupted(ProviderTransientError):
    """A response was cut off; a smaller translation batch may succeed."""


class TextGenerationProvider(ABC):
    @abstractmethod
    def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResponse:
        raise NotImplementedError
