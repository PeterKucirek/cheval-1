from typing import Set, Any, Union, Dict, List, Tuple
import abc

import pandas as pd
import numpy as np

from .parsing import ChainedSymbol, ChainTuple, NAN_STR
from.expressions import Expression, ExpressionGroup


class AbstractSymbol(object, metaclass=abc.ABCMeta):

    def __init__(self, parent: 'EvaluationContext', name: str):
        self._parent = parent
        self._name = name

    @abc.abstractmethod
    def fill(self, data): pass

    @abc.abstractmethod
    def get(self, **kwargs) -> Union[float, np.ndarray]: pass

    @abc.abstractclassmethod
    def empty(self): pass


class NumberSymbol(AbstractSymbol):
    def __init__(self, parent: 'EvaluationContext', name: str):
        super().__init__(parent, name)
        self._val = None

    def fill(self, data):
        self._val = float(data)

    def get(self):
        assert self._val is not None
        return self._val

    def empty(self): self._val = None


class VectorSymbol(AbstractSymbol):

    def __init__(self, parent: 'EvaluationContext', name: str, orientation: int):
        super().__init__(parent, name)

        assert orientation in {0, 1}
        self._orientation = orientation
        self._raw_array: np.ndarray = None

    def fill(self, data):
        index_to_check = self._parent.cols if self._orientation else self._parent.rows

        if isinstance(data, pd.Series):
            assert index_to_check.equals(data.index), "Series does not match context rows or columns"
            vector = data.values
        elif isinstance(data, np.ndarray):
            assert len(data.shape) == 1, "Only 1D arrays are permitted"
            assert len(data) == len(index_to_check), "Array length does not match length of rows or columns"
            vector = data
        else:
            raise TypeError(type(data))

        self._raw_array = vector[...]  # Shallow copy
        n = len(index_to_check)

        if self._orientation: self._raw_array.shape = 1, n
        else: self._raw_array.shape = n, 1

    def get(self): return self._raw_array

    def empty(self): self._raw_array = None


class TableSymbol(AbstractSymbol):

    def __init__(self, parent: 'EvaluationContext', name: str, orientation: int, mandatory_attributes: Set[str]=None,
                 allow_links: bool=True):
        super().__init__(parent, name)
        assert orientation in {0, 1}
        self._orientation = orientation

        if mandatory_attributes is None: mandatory_attributes = set()
        self._mandatory_attributes = mandatory_attributes
        self._allow_links = bool(allow_links)

    def fill(self, data):
        raise NotImplementedError()

    def get(self, chain: ChainTuple=None):
        assert chain is not None

    def empty(self):
        raise NotImplementedError()


class MatrixSymbol(AbstractSymbol):

    def __init__(self, parent: 'EvaluationContext', name: str, allow_transpose: bool=True):
        super().__init__(parent, name)
        self._allow_transpose = bool(allow_transpose)
        self._matrix: np.ndarray = None

    def fill(self, data):
        rows = self._parent.rows
        cols = self._parent.cols

        if isinstance(data, pd.DataFrame):
            if rows.equals(data.index) and cols.equals(data.columns):
                # Orientation matches
                array = data.values.astype('f8')
            elif rows.equals(data.columns) and cols.equals(data.index):
                assert self._allow_transpose
                array = data.transpose().values.astype('f8')
            else:
                raise TypeError("Shapes do not match")
        elif isinstance(data, np.ndarray):
            assert len(data.shape) == 2
            r, c = data.shape
            if r == len(rows) and c == len(cols):
                array = data.astype('f8')
            elif r == len(cols) and c == len(rows):
                assert self._allow_transpose
                array = data.transpose().astype('f8')
            else:
                raise TypeError("Shapes do not match")
        else:
            raise TypeError(type(data))

        self._matrix = array

    def get(self): return self._matrix

    def empty(self): self._matrix = None


class EvaluationContext(object):

    def __init__(self, *, rows_index: pd.Index=None, col_index: pd.Index=None):
        self._row_index: pd.Index = rows_index
        self._col_index: pd.Index = col_index
        self._symbols: Dict[str, AbstractSymbol] = {}

    @property
    def rows(self): return self._row_index

    @property
    def cols(self): return self._col_index

    def empty(self):
        """
        Empties any symbols that have been defined, de-referencing any stored data. This can free up memory, if
        there are no other references.

        This method also gets called when the row or column indexes are changed.
        """
        for symbol in self._symbols.values():
            symbol.empty()

    def reset(self):
        """
        Completely removed any declared symbols, regardless of whether they have been defined or not.
        """
        self._symbols.clear()

    def define_rows(self, index: pd.Index):
        self.empty()
        self._row_index = pd.Index(index)

    def define_columns(self, index: pd.Index):
        self.empty()
        self._col_index = pd.Index(index)

    # region Symbol declarations

    def declare_number(self, name: str):
        self._symbols[name] = NumberSymbol(self, name)

    def declare_vector(self, name: str, orientation: int):
        self._symbols[name] = VectorSymbol(self, name, orientation)

    def declare_table(self, name: str, orientation: int, mandatory_attributes: Set[str]=None,
                      allow_links=True):
        self._symbols[name] = TableSymbol(self, name, orientation, mandatory_attributes, allow_links)

    def declare_matrix(self, name: str, allow_transpose=True):
        self._symbols[name] = MatrixSymbol(self, name, allow_transpose)

    # endregion

    def define_symbol(self, name: str, data):
        self._symbols[name].fill(data)

    def validate_expr(self, expressions: Union[str, List[str], Expression, ExpressionGroup]):
        item, _ = self._prepare_expressions(expressions)
        self._validate_decalred(item)

        return item

    def evaluate(self, expressions: Union[str, List[str], Expression, ExpressionGroup]):
        item, multile_statements = self._prepare_expressions(expressions)
        self._validate_decalred(item)
        self._validate_defined(item)

    def _prepare_expressions(self, item) -> Tuple[Union[Expression, ExpressionGroup], bool]:
        # Parse if neccessary
        if isinstance(item, str):
            return Expression(item), False
        elif isinstance(item, Expression):
            return item, False
        elif isinstance(item, ExpressionGroup):
            return item, True
        else:
            return ExpressionGroup(item), True

    def _validate_decalred(self, e: Union[Expression, ExpressionGroup]):
        for symbol in e.itersymbols():
            assert symbol in self._symbols, "Symbol '%s' is not recognized" % symbol

    def _validate_defined(self, e: Union[Expression, ExpressionGroup]):
        for name, symbol_e in e.iterchained():
            symbol_self = self._symbols[name]
            assert isinstance(symbol_self, TableSymbol)

        # TODO: Review the inverse, e.g. TableSymbols used simply

    def _eval_single(self, e: Expression):
        local_dict = self._prepare_locals(e)
        for substitution, series in e.iterdicts():
            ndarray = self._align_series(series)
            local_dict[substitution] = ndarray

    def _eval_group(self, e: ExpressionGroup):
        local_dict = self._prepare_locals(e)



    def _prepare_locals(self, e: Union[Expression, ExpressionGroup]) -> Dict[str, np.ndarray]:
        local_dict = {NAN_STR: np.nan}
        for name in e.itersimple():
            symbol = self._symbols[name]
            local_dict[name] = symbol.get()

        for name, chain in e.iterchained():
            symbol = self._symbols[name]
            local_dict[name] = symbol.get(chain=chain)

        return local_dict

    def _align_series(self, s: pd.Series) -> np.ndarray:
        return s.reindex(self._col_index, fill_value=0).values
