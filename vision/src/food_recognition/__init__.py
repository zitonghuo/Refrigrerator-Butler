"""Image-based food recognition for Fridge Butler."""

from .hybrid import HybridFoodRecognizer
from .service import FoodRecognizer, RecognitionError

__all__ = [
    "FoodRecognizer",
    "HybridFoodRecognizer",
    "OpenVocabularyRecognizer",
    "RecognitionError",
]


def __getattr__(name: str):
    if name == "OpenVocabularyRecognizer":
        from .open_vocab import OpenVocabularyRecognizer

        return OpenVocabularyRecognizer
    raise AttributeError(name)
