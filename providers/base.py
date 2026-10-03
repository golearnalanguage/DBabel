from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.models import (
    GenerationRequest,
    GenerationResponse,
)


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status: int = None, retry_after: float = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


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
