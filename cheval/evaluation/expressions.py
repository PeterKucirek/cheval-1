import ast
import astor

import pandas as pd

from .parsing import ExpressionParser, ChainedSymbol

from typing import Dict, Set, Iterable, List


class Expression(object):
    """Single expression"""

    def __init__(self, expression: str):
        self._raw: str = expression

        tree = ast.parse(expression, mode='eval').body
        transformer = ExpressionParser()
        new_tree = transformer.visit(tree)
        self._transformed: str = astor.to_source(new_tree)

        self._simple_symbols: Set[str] = transformer.simple_symbols
        self._chained_symbols: Dict[str, ChainedSymbol] = transformer.chained_symbols
        self._dict_literals: Dict[str, pd.Series] = transformer.dict_literals

    def itersymbols(self):
        yield from self._simple_symbols
        yield from self._chained_symbols.keys()

    def iterchained(self):
        yield from self._chained_symbols.items()

    def itersimple(self):
        yield from self._simple_symbols

    def iterdicts(self):
        yield from self._dict_literals.items()

    @property
    def raw(self) -> str: return self._raw

    @property
    def transformed(self) -> str: return self._transformed


class ExpressionGroup(object):
    """Collection of related, consistent expressions"""

    def __init__(self, expressions: Iterable[str]):
        self._raw = []
        self._transformed = []
        self._simple_symbols: Set[str] = set()
        self._shared_chains: Set[str] = set()
        self._chained_symbols: List[Dict[str, ChainedSymbol]] = []
        self._dict_literals: List[Dict[str, pd.Series]] = []

        for expression in expressions:
            self._raw.append(expression)

            tree = ast.parse(expression, mode='eval').body
            transformer = ExpressionParser(self._simple_symbols, self._shared_chains)
            new_tree = transformer.visit(tree)
            self._transformed.append(astor.to_source(new_tree))

            self._dict_literals.append(transformer.dict_literals)
            self._chained_symbols.append(transformer.chained_symbols)

    def itersymbols(self):
        yield from self._simple_symbols
        yield from self._shared_chains

    def iterchained(self, i: int):
        yield from self._chained_symbols[i].items()

    def itersimple(self):
        yield from self._simple_symbols

    def iterdicts(self, i: int):
        yield from self._dict_literals[i].items()

    @property
    def raw(self) -> List[str]: return self._raw[...]

    @property
    def transformed(self) -> List[str]: return self._transformed[...]