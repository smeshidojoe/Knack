"""
Заглушки тяжёлых зависимостей argostranslate. Выполняется до основного кода.

`argostranslate.sbd` импортирует spacy и stanza на верхнем уровне, а
`ctranslate2` — свои конвертеры моделей, которые тянут transformers и torch.
Ни то, ни другое при переводе готовой моделью не нужно, но в сборку они утащили
бы почти полтора гигабайта, из них torch — 1.2 ГБ.

Все четыре используются только внутри методов, до которых мы не доходим:
разбиение на предложения принудительно переведено на minisbd
(ARGOS_CHUNK_TYPE), а конвертация моделей нам не нужна вовсе. Поэтому подставляем
пустые модули — импорт проходит, вес остаётся снаружи.
"""

import sys
import types
from importlib.machinery import ModuleSpec

# Всё это подтягивается через argostranslate и конвертеры ctranslate2, но при
# переводе готовой моделью не работает ни одно. Проверено: перевод en->ru идёт
# с полным набором заглушек.
_STUBS = (
    "torch", "transformers", "spacy", "stanza",
    "openai", "huggingface_hub", "gradio",
    "pandas", "scipy", "numba", "sqlalchemy", "openpyxl", "gevent",
)


def _stub(name):
    module = types.ModuleType(name)
    # __spec__ обязателен: чужой код проверяет наличие пакета через find_spec,
    # и модуль без спецификации роняет проверку с ValueError.
    module.__spec__ = ModuleSpec(name, loader=None)
    module.__path__ = []
    module.__version__ = "0.0.0"
    module.__knack_stub__ = True
    return module


for _name in _STUBS:
    if _name not in sys.modules:
        sys.modules[_name] = _stub(_name)
