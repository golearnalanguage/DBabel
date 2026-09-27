from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.models import (
    GenerationRequest,
    GenerationResponse,
)


class ProviderError(RuntimeError):
    pass


class TextGenerationProvider(ABC):
    @abstractmethod
    def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResponse:
        raise NotImplementedError
