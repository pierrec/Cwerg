#!/usr/bin/python3

"""AST Nodes and SExpr reader/writer for the Cwerg frontend"""

import sys
import dataclasses
import logging
import enum

from typing import List, Dict, Set, Optional, Union, Any

logger = logging.getLogger(__name__)

SRCLOC_GENERATED = -1

_ID_PATH_SEPARATOR = "::"


def GetQualifierIfPresent(name: str) -> Optional[str]:
    tokens = name.split(_ID_PATH_SEPARATOR)
    if len(tokens) == 2:
        return tokens[0]
    assert 1 == len(tokens)
    return None


def GetSymbolName(name: str) -> str:
    return name.split(_ID_PATH_SEPARATOR)[-1]


def IsQualifiedName(name: str) -> bool:
    return _ID_PATH_SEPARATOR in name

############################################################
# Enums
############################################################


@enum.unique
class BASE_TYPE_KIND(enum.Enum):
    """basic scalar types"""
    INVALID = 0

    SINT = 10
    S8 = 11
    S16 = 12
    S32 = 13
    S64 = 14

    UINT = 20
    U8 = 21
    U16 = 22
    U32 = 23
    U64 = 24

    R32 = 30  # real
    R64 = 31  # real

    VOID = 40
    NORET = 41
    BOOL = 42
    TYPEID = 43


@enum.unique
class NF(enum.Flag):
    """Node Flags"""
    NONE = 0
    MAY_BE_LHS = enum.auto()
    TYPE_ANNOTATED = enum.auto()   # node has a type (x_type)
    VALUE_ANNOTATED = enum.auto()  # node may have a comptime value (x_value)
    FIELD_ANNOTATED = enum.auto()  # node reference a struct field (x_field)
    SYMBOL_ANNOTATED = enum.auto()  # node reference a XXX_SYM_DEF node (x_symbol)
    # node reference the imported module or the qualifier  (x_module)
    MODULE_ANNOTATED = enum.auto()
    MODNAME_ANNOTATED = enum.auto()

    TYPE_CORPUS = enum.auto()
    CONTROL_FLOW = enum.auto()
    GLOBAL_SYM_DEF = enum.auto()
    LOCAL_SYM_DEF = enum.auto()
    TOP_LEVEL = enum.auto()
    MACRO_BODY_ONLY = enum.auto()
    TO_BE_EXPANDED = enum.auto()
    # all non-core nodes will be stripped or converted to core nodes before code-gen
    NON_CORE = enum.auto()


@enum.unique
class GROUP(enum.IntEnum):
    """Node Family"""
    Misc = enum.auto()
    Type = enum.auto()
    Statement = enum.auto()
    Value = enum.auto()
    Expression = enum.auto()
    Macro = enum.auto()
    Ephemeral = enum.auto()  # should only exist during intermediate steps and in macros


@enum.unique
class BINARY_EXPR_KIND(enum.Enum):
    """same type two operand expressions"""
    INVALID = 0
    ADD = 1
    SUB = 2
    DIV = 3
    MUL = 4
    REM = 5
    MIN = 6
    MAX = 7

    AND = 10
    OR = 11
    XOR = 12

    EQ = 20
    NE = 21
    LT = 22
    LE = 23
    GT = 24
    GE = 25

    ANDSC = 30  # && (SC = short circuit)
    ORSC = 31   # || (SC = short circuit)

    SHR = 40    # >>
    SHL = 41    # <<

    PDELTA = 52  # pointer delta result is sint


BINARY_EXPR_SHORTCUT = {
    ">=": BINARY_EXPR_KIND.GE,
    ">": BINARY_EXPR_KIND.GT,
    "<=": BINARY_EXPR_KIND.LE,
    "<": BINARY_EXPR_KIND.LT,
    "==": BINARY_EXPR_KIND.EQ,
    "!=": BINARY_EXPR_KIND.NE,
    #
    "+": BINARY_EXPR_KIND.ADD,
    "-": BINARY_EXPR_KIND.SUB,
    "*": BINARY_EXPR_KIND.MUL,
    "/": BINARY_EXPR_KIND.DIV,
    "%": BINARY_EXPR_KIND.REM,
    "max": BINARY_EXPR_KIND.MAX,
    "min": BINARY_EXPR_KIND.MIN,
    #
    "&&": BINARY_EXPR_KIND.ANDSC,
    "||": BINARY_EXPR_KIND.ORSC,
    #
    "<<": BINARY_EXPR_KIND.SHL,
    ">>": BINARY_EXPR_KIND.SHR,
    #
    "and": BINARY_EXPR_KIND.AND,
    "or": BINARY_EXPR_KIND.OR,
    "xor": BINARY_EXPR_KIND.XOR,
    #
    "pdelta": BINARY_EXPR_KIND.PDELTA,
}

BINARY_EXPR_SHORTCUT_INV = {v: k for k, v in BINARY_EXPR_SHORTCUT.items()}


@enum.unique
class POINTER_EXPR_KIND(enum.Enum):
    """pointer and int two operand expressions"""
    INVALID = 0
    INCP = 1   # pointer add int
    DECP = 2   # pointer sub int


POINTER_EXPR_SHORTCUT = {
    #
    "incp": POINTER_EXPR_KIND.INCP,
    "decp": POINTER_EXPR_KIND.DECP,
}

POINTER_EXPR_SHORTCUT_INV = {v: k for k, v in POINTER_EXPR_SHORTCUT.items()}


@enum.unique
class ASSIGNMENT_KIND(enum.Enum):
    """Compound Assignment Kinds"""
    INVALID = 0
    ADD = 1
    SUB = 2
    DIV = 3
    MUL = 4
    REM = 5
    #
    AND = 10
    OR = 11
    XOR = 12
    #
    SHR = 20    # >>
    SHL = 31    # <<


ASSIGNMENT_SHORTCUT = {
    #
    "+=": ASSIGNMENT_KIND.ADD,
    "-=": ASSIGNMENT_KIND.SUB,
    "*=": ASSIGNMENT_KIND.MUL,
    "/=": ASSIGNMENT_KIND.DIV,
    "%=": ASSIGNMENT_KIND.REM,
    #
    "and=": ASSIGNMENT_KIND.AND,
    "or=": ASSIGNMENT_KIND.OR,
    "xor=": ASSIGNMENT_KIND.XOR,
    #
    "<<=": ASSIGNMENT_KIND.SHL,
    ">>=": ASSIGNMENT_KIND.SHR,
}

ASSIGMENT_SHORTCUT_INV = {v: k for k, v in ASSIGNMENT_SHORTCUT.items()}

COMPOUND_KIND_TO_EXPR_KIND = {
    ASSIGNMENT_KIND.ADD: BINARY_EXPR_KIND.ADD,
    ASSIGNMENT_KIND.SUB: BINARY_EXPR_KIND.SUB,
    ASSIGNMENT_KIND.DIV: BINARY_EXPR_KIND.DIV,
    ASSIGNMENT_KIND.MUL: BINARY_EXPR_KIND.MUL,
    ASSIGNMENT_KIND.REM: BINARY_EXPR_KIND.REM,
    #
    ASSIGNMENT_KIND.AND: BINARY_EXPR_KIND.AND,
    ASSIGNMENT_KIND.OR: BINARY_EXPR_KIND.OR,
    ASSIGNMENT_KIND.XOR: BINARY_EXPR_KIND.XOR,
    #
    ASSIGNMENT_KIND.SHR: BINARY_EXPR_KIND.SHR,
    ASSIGNMENT_KIND.SHL: BINARY_EXPR_KIND.SHL,
}


@enum.unique
class UNARY_EXPR_KIND(enum.Enum):
    """Unary Expression Kind for basic types"""
    INVALID = 0
    NOT = 1
    MINUS = 2


UNARY_EXPR_SHORTCUT = {
    "!": UNARY_EXPR_KIND.NOT,
    "~": UNARY_EXPR_KIND.MINUS,
}

UNARY_EXPR_SHORTCUT_INV = {v: k for k, v in UNARY_EXPR_SHORTCUT.items()}


@enum.unique
class MOD_PARAM_KIND(enum.Enum):
    """Module Parameter Kind"""
    INVALID = 0
    CONST = 1
    MOD = 2
    TYPE = 3


@enum.unique
class MACRO_PARAM_KIND(enum.Enum):
    """Macro Parameter Kinds"""
    INVALID = 0
    ID = 1
    STMT_LIST = 2
    EXPR_LIST = 3
    EXPR = 4
    STMT = 5
    FIELD = 6
    TYPE = 7

############################################################
# Field attributes of Nodes
#
# the fields of nodes are subject to a lot of invariants which must be enforced
#
# There are two kinds of fields:
# * regular fields - typically populated directly from source
# * x-fields - typically populated by later analyses
#
# Regular fields follow these rules
#
# All fields belong to one of these categories:
# * FLAG_FIELDS: bools
# * STR_FIELDS: strings
# * INT_FIELDS: ints
# * KIND_FIELDS: enums
# * NODE_FIELD: a single AST Node
# * LIST_FIELDS: zero or more AST Nodes
#
# The order of fields in the Node is:
#
# * fields from FLAG_FIELDS
# * fields from other categories
# If fields are in OPTIONAL_FIELDS they must come last
############################################################


@enum.unique
class NFK(enum.Enum):
    """Node Field Descriptor Kind"""
    INT = 1
    STR = 2
    ATTR_BOOL = 3
    ATTR_STR = 4
    KIND = 5
    NODE = 6
    LIST = 7
    STR_LIST = 8


@dataclasses.dataclass()
class NFD:
    """Node Field Descriptor"""
    kind: NFK
    name: str
    doc: str
    extra: Any = None


NODES_PARAMS = ("FunParam")
NODES_PARAMS_T = Union[NODES_PARAMS]

NODES_BODY_MOD = ("DefFun", "DefRec", "DefEnum", "DefVar", "DefMacro", "DefType",
                  "DefGlobal", "StmtStaticAssert", "Import")
NODES_BODY_MOD_T = Union[NODES_BODY_MOD]

NODES_PARAMS_MOD = ("ModParam")
NODES_PARAMS_MOD_T = Union[NODES_PARAMS_MOD]

NODES_PARAMS_MACRO = ("MacroParam")
NODES_PARAMS_MACRO_T = Union[NODES_PARAMS_MACRO]

NODES_BODY = ("StmtDefer", "StmtIf", "StmtBreak", "StmtContinue", "StmtReturn", "StmtExpr",
              "StmtCompoundAssignment", "StmtBlock", "StmtCond", "DefVar", "MacroInvoke",
              "StmtAssignment", "StmtTrap")
NODES_BODY_T = Union[NODES_BODY]

NODES_BODY_MACRO = ("StmtDefer", "StmtIf", "StmtBreak",
                    "StmtContinue", "StmtReturn", "StmtExpr",
                    "StmtBlock", "StmtCond")
NODES_BODY_MACRO_T = Union[NODES_BODY_MACRO]

NODES_TYPES = ("TypeBase",
               "TypeSlice", "TypeArray", "TypePtr", "TypeFun", "Id", "TypeSum", "TypeOf", "TypeSumDelta")
NODES_TYPES_T = Union[NODES_TYPES]

NODES_TYPES_OR_AUTO = ("TypeBase", "TypeSlice", "TypeArray", "TypePtr", "TypeFun", "Id",
                       "TypeSum", "TypeOf", "TypeSumDelta", "TypeAuto")
NODES_TYPES_OR_AUTO_T = Union[NODES_TYPES_OR_AUTO]

NODES_ITEMS = ("EnumVal")
NODES_ITEMS_T = Union[NODES_ITEMS]

NODES_INITS_ARRAY = ("IndexVal")
NODES_INITS_ARRAY_T = Union[NODES_INITS_ARRAY]

NODES_INITS_REC = ("FieldVal")
NODES_INITS_REC_T = Union[NODES_INITS_REC]

NODES_FIELDS = ("RecField")
NODES_FIELDS_T = Union[NODES_FIELDS]

NODES_CASES = ("Case")
NODES_CASES_T = Union[NODES_CASES]

NODES_EXPR = ("ValFalse", "ValTrue", "ValNum",
              "ValVoid", "ValArray", "ValString", "ValRec", "ValSlice",
              #
              "MacroInvoke",
              #
              "Id", "ExprAddrOf", "ExprDeref", "ExprIndex",
              "ExprField", "ExprCall", "ExprParen",
              "Expr1", "Expr2", "Expr3", "ExprPointer",
              "ExprLen", "ExprFront",
              "ExprTypeId", "ExprSizeof", "ExprOffsetof", "ExprStmt",
              "ExprStringify",
              "ExprSumTag", "ExprSumUntagged",
              "ExprIs", "ExprAs", "ExprWrap", "ExprUnwrap", "ExprNarrow", "ExprBitCast")


NODES_EXPR_T = Union[NODES_EXPR]

NODES_EXPR_OR_UNDEF = NODES_EXPR + ("ValUndef",)

NODES_EXPR_INIT = NODES_EXPR + ("ValAuto", "ValUndef")

NODES_COND = ("ValFalse", "ValTrue",
              #
              "Id", "ExprDeref", "ExprIndex",
              "ExprField", "ExprCall", "ExprParen",
              "Expr1", "Expr2", "Expr3",
              "ExprStmt", "ExprIs")
NODES_COND_T = Union[NODES_COND]

NODES_LHS = ("Id", "ExprDeref", "ExprIndex", "ExprField", "MacroInvoke")
NODES_LHS_T = Union[NODES_LHS]

ALL_FIELDS = [
    NFD(NFK.STR, "number", "a number"),
    NFD(NFK.STR, "name", "name of the object"),

    NFD(NFK.STR, "name_list", "name of the object list"),

    NFD(NFK.STR, "string", "string literal"),
    NFD(NFK.STR, "comment", "comment"),
    NFD(NFK.STR, "message", "message for assert failures"),
    NFD(NFK.STR, "field", "record field"),
    NFD(NFK.STR, "label", "block  name (if not empty)"),
    NFD(NFK.STR, "target",
        "name of enclosing while/for/block to brach to (empty means nearest)"),
    NFD(NFK.STR, "init_field", "initializer field or empty (empty means next field)"),
    NFD(NFK.STR, "path", "TBD"),
    NFD(NFK.STR, "alias", "name of imported module to be used instead of given name"),
    NFD(NFK.STR_LIST, "gen_ids",
        "name placeholder ids to be generated at macro instantiation time"),
    #
    NFD(NFK.ATTR_BOOL, "pub", "has public visibility"),
    NFD(NFK.ATTR_BOOL, "extern", "is external function (empty body)"),
    NFD(NFK.ATTR_BOOL, "mut", "is mutable"),
    NFD(NFK.ATTR_BOOL, "ref", "address may be taken"),
    NFD(NFK.ATTR_BOOL, "colon", "colon style list"),
    NFD(NFK.ATTR_BOOL, "cdecl", "use c-linkage (no module prefix)"),
    NFD(NFK.ATTR_BOOL, "wrapped", "is wrapped type (forces type equivalence by name)"),
    NFD(NFK.ATTR_BOOL, "discard", "ignore non-void expression"),
    NFD(NFK.ATTR_BOOL, "init", "run function at startup"),
    NFD(NFK.ATTR_BOOL, "fini", "run function at shutdown"),
    NFD(NFK.ATTR_BOOL, "polymorphic", "function definition or call is polymorphic"),
    NFD(NFK.ATTR_BOOL, "unchecked", "array acces is not checked"),
    NFD(NFK.ATTR_BOOL, "untagged", "sum type is untagged"),
    NFD(NFK.ATTR_BOOL, "arg_ref", "in parameter was converted for by-val to pointer"),
    NFD(NFK.ATTR_BOOL, "res_ref", "in parameter was converted for by-val to pointer"),
    NFD(NFK.ATTR_BOOL, "builtin", "module is the builtin module"),
    NFD(NFK.ATTR_BOOL, "triplequoted", "string is using 3 double quotes"),
    NFD(NFK.ATTR_STR, "doc", "comment"),
    NFD(NFK.ATTR_STR, "strkind", "raw: ignore escape sequences in string, hex:"),

    #
    NFD(NFK.KIND, "unary_expr_kind",
        "see [Expr1 Kind](#expr1-kind) below", UNARY_EXPR_KIND),
    NFD(NFK.KIND, "binary_expr_kind",
        "see [Expr2 Kind](#expr2-kind) below", BINARY_EXPR_KIND),
    NFD(NFK.KIND, "base_type_kind",
        "see [Base Type Kind](#base-type-kind) below", BASE_TYPE_KIND),
    NFD(NFK.KIND, "mod_param_kind",
        "see [ModParam Kind](#modparam-kind) below",  MOD_PARAM_KIND),
    NFD(NFK.KIND, "assignment_kind",
        "see [StmtCompoundAssignment Kind](#stmtcompoundassignment-kind) below", ASSIGNMENT_KIND),
    NFD(NFK.KIND,  "macro_param_kind",
        "type of a macro parameter node, see [MacroParam Kind](#macroparam-kind) below",  MACRO_PARAM_KIND),
    NFD(NFK.KIND,  "macro_result_kind",
        "type of the macro result node,  see [MacroParam Kind](#macroparam-kind) below",  MACRO_PARAM_KIND),
    NFD(NFK.KIND, "pointer_expr_kind",
        "see [PointerOp Kind](#pointerop-kind) below", POINTER_EXPR_KIND),
    #
    # TODO: fix all the None below
    NFD(NFK.LIST, "params", "function parameters and/or comments", NODES_PARAMS),
    NFD(NFK.LIST, "params_mod", "module template parameters", NODES_PARAMS_MOD),
    NFD(NFK.LIST, "params_macro", "macro parameters", NODES_PARAMS_MACRO),
    NFD(NFK.LIST, "args", "function call arguments", None),
    NFD(NFK.LIST, "items", "enum items and/or comments", NODES_ITEMS),
    NFD(NFK.LIST, "fields", "record fields and/or comments", NODES_FIELDS),
    NFD(NFK.LIST, "types", "union types", NODES_TYPES),
    NFD(NFK.LIST, "inits_array",
        "array initializers and/or comments", NODES_INITS_ARRAY),
    NFD(NFK.LIST, "inits_field",
        "record initializers and/or comments", NODES_INITS_REC),
    #
    NFD(NFK.LIST, "body_mod",
        "toplevel module definitions and/or comments", NODES_BODY_MOD),
    NFD(NFK.LIST, "body", "new scope: statement list and/or comments", NODES_BODY),
    NFD(NFK.LIST, "body_t",
        "new scope: statement list and/or comments for true branch", NODES_BODY),
    NFD(NFK.LIST, "body_f",
        "new scope: statement list and/or comments for false branch", NODES_BODY),
    NFD(NFK.LIST, "body_for", "statement list for macro_loop", NODES_BODY),
    NFD(NFK.LIST, "body_macro",
        "new scope: macro statments/expression", None),
    NFD(NFK.LIST, "cases", "list of case statements", NODES_CASES),

    #
    NFD(NFK.NODE, "init_index",
        "initializer index or empty (empty mean next index)", None),
    NFD(NFK.NODE, "type", "type expression", NODES_TYPES),
    NFD(NFK.NODE, "subtrahend", "type expression", NODES_TYPES),
    NFD(NFK.NODE, "type_or_auto", "type expression", NODES_TYPES_OR_AUTO),
    NFD(NFK.NODE, "result", "return type", None),
    NFD(NFK.NODE, "size", "compile-time constant size", NODES_EXPR),
    NFD(NFK.NODE, "expr_size", "expression determining the size or auto", None),
    NFD(NFK.NODE, "expr_index",
        "expression determining the index to be accessed", NODES_EXPR),
    NFD(NFK.NODE, "expr", "expression", NODES_EXPR),
    NFD(NFK.NODE, "cond", "conditional expression must evaluate to a boolean", NODES_COND),
    NFD(NFK.NODE, "expr_t",
        "expression (will only be evaluated if cond == true)", NODES_EXPR),
    NFD(NFK.NODE, "expr_f",
        "expression (will only be evaluated if cond == false)", NODES_EXPR),
    NFD(NFK.NODE, "expr1", "left operand expression", NODES_EXPR),
    NFD(NFK.NODE, "expr2", "righ operand expression", NODES_EXPR),
    NFD(NFK.NODE, "expr_bound_or_undef", "", NODES_EXPR_OR_UNDEF),
    NFD(NFK.NODE, "expr_rhs", "rhs of assignment", NODES_EXPR),
    NFD(NFK.NODE, "expr_ret", "result expression (ValVoid means no result)", NODES_EXPR),
    NFD(NFK.NODE, "pointer", "pointer component of slice", None),
    NFD(NFK.NODE, "container", "array and slice", None),
    NFD(NFK.NODE, "callee", "expression evaluating to the function to be called", None),
    NFD(NFK.NODE, "value", "", NODES_EXPR),
    NFD(NFK.NODE, "value_or_auto", "enum constant or auto", None),
    NFD(NFK.NODE, "value_or_undef", "", NODES_EXPR_OR_UNDEF),
    NFD(NFK.NODE, "lhs", "l-value expression", NODES_LHS),
    NFD(NFK.NODE, "expr_lhs", "l-value expression", NODES_LHS),
    NFD(NFK.NODE, "initial_or_undef_or_auto", "initializer", NODES_EXPR_INIT),
]

NEW_SCOPE_FIELDS = set(["body", "body_f", "body_t", "body_macro"])

ALL_FIELDS_MAP: Dict[str, NFD] = {nfd.name: nfd for nfd in ALL_FIELDS}


# Optional fields must come last in a dataclass
_OPTIONAL_FIELDS = {
    "expr_ret": "@ValVoid",
    "value_or_auto": "@ValAuto",
    "target": "",
    "path": "",
    "alias": "",
    "message": "",
    "initial_or_undef_or_auto": "@ValAuto",
    "init_index": "@ValAuto",
    "init_field": "",
    "inits_array": "@EmptyList",
    "expr_bound_or_undef": "@ValUndef",
}


def GetOptional(field: str, srcloc):
    e = _OPTIONAL_FIELDS.get(field)
    if e is None:
        return e

    assert isinstance(e, str)
    if e == "@EmptyList":
        return []
    elif e == "":
        return ""
    elif e == "@ValVoid":
        return ValVoid(x_srcloc=srcloc)
    elif e == "@ValAuto":
        return ValAuto(x_srcloc=srcloc)
    elif e == "@ValUndef":
        return ValUndef(x_srcloc=srcloc)
    else:
        assert False


def IsFieldWithDefaultValue(field, val):
    e = _OPTIONAL_FIELDS.get(field)
    if e is None:
        return False

    assert isinstance(e, str)
    if e == "@EmptyList":
        return len(val) == 0
    elif e == "":
        return val == ""
    elif e == "@ValVoid":
        return isinstance(val, ValVoid)
    elif e == "@ValAuto":
        return isinstance(val, ValAuto)
    elif e == "@ValUndef":
        return isinstance(val, ValUndef)
    else:
        assert False


X_FIELDS = {
    "x_srcloc": None,  # set by cwast.py
    # set by mod_pool.py
    "x_module": NF.MODULE_ANNOTATED,  # containing module for symbol resolution
    "x_modname": NF.MODNAME_ANNOTATED,  # unique module name
    # set by symbolize.py,
    "x_symbol": NF.SYMBOL_ANNOTATED,  # contains node from
                                      # GLOBAL_SYM_DEF/LOCAL_SYM_DEF group
    "x_target": NF.CONTROL_FLOW,
    # set by typify.py
    "x_field": NF.FIELD_ANNOTATED,
    "x_type": NF.TYPE_ANNOTATED,
    "x_offset": NF.TYPE_CORPUS,   # oddball, should be moved into types
    # set by eval.py
    "x_value": NF.VALUE_ANNOTATED,
}


def _NAME(node):
    if node.ALIAS is not None:
        return "[" + node.ALIAS + "]"
    return "[" + node.__class__.__name__ + "]"


def _FLAGS(node):
    out = []
    for c, _ in node.__class__.ATTRS:
        if getattr(node, c):
            out.append("@" + c)
    outs = " ".join(out)
    return " " + outs if outs else outs


# maps node class name and aliases to class
NODES_ALIASES = {}

ALL_NODES = set()


def _CheckNodeFieldOrder(cls):
    """
    order is
    * regular
    * optional
    * flags
    * x_
    """
    optionals = 0
    regulars = 0
    flags = 0
    xs = 0
    for field, type in cls.__annotations__.items():
        if field.startswith("x_"):
            assert field in X_FIELDS, f"unexpected x-field: {field} in node {type}"
            if field != "x_srcloc":
                flag_kind = X_FIELDS[field]
                assert flag_kind in cls.FLAGS, f"{cls}: {field} {flag_kind}"
            xs += 1
            continue
        nfd = ALL_FIELDS_MAP[field]
        if field in _OPTIONAL_FIELDS:
            optionals += 1
            assert flags + xs == 0, f"{cls}: {field}"
        elif nfd.kind is NFK.ATTR_BOOL or nfd.kind is NFK.ATTR_STR:
            flags += 0
            assert xs == 0
        else:
            regulars += 1
            assert optionals + flags + xs == 0


def NodeCommon(cls):
    cls.__eq__ = lambda a, b: id(a) == id(b)
    cls.__hash__ = lambda a: id(a)

    assert hasattr(cls, "ALIAS") and hasattr(
        cls, "FLAGS") and hasattr(cls, "GROUP")
    assert hasattr(cls, "x_srcloc")
    _CheckNodeFieldOrder(cls)

    ALL_NODES.add(cls)
    NODES_ALIASES[cls.__name__] = cls

    if cls.ALIAS is not None:
        NODES_ALIASES[cls.ALIAS] = cls
    cls.FIELDS = []
    cls.ATTRS = []
    for field, _ in cls.__annotations__.items():
        if not field.startswith("x_"):
            nfd = ALL_FIELDS_MAP[field]
            if nfd.kind is NFK.ATTR_BOOL or nfd.kind is NFK.ATTR_STR:
                cls.ATTRS.append((field, nfd))
            else:
                cls.FIELDS.append((field, nfd))
    return cls

############################################################
# Typing
############################################################


@dataclasses.dataclass()
class CanonType:
    """Canonical Type"""
    node: Any
    name: str
    #
    mut: bool = False
    dim: int = -1
    untagged: bool = False
    base_type_kind: BASE_TYPE_KIND = BASE_TYPE_KIND.INVALID
    children: List["CanonType"] = dataclasses.field(default_factory=list)
    #
    ast_node: Optional[Any] = None
    #
    alignment: int = -1
    size: int = -1
    register_types: List[Any] = dataclasses.field(default_factory=list)
    typeid: int = -1
    original_type: Optional["CanonType"] = None

    def __hash__(self):
        return hash(self.name)

    def is_bool(self) -> bool:
        return self.base_type_kind is BASE_TYPE_KIND.BOOL

    def is_void(self) -> bool:
        return self.base_type_kind is BASE_TYPE_KIND.VOID

    def is_int(self) -> bool:
        return self.base_type_kind in BASE_TYPE_KIND_INT

    def is_uint(self) -> bool:
        return self.base_type_kind in BASE_TYPE_KIND_UINT

    def is_sint(self) -> bool:
        return self.base_type_kind in BASE_TYPE_KIND_SINT

    def is_real(self) -> bool:
        return self.base_type_kind in BASE_TYPE_KIND_REAL

    def is_number(self) -> bool:
        return self.base_type_kind in BASE_TYPE_KIND_REAL or self.base_type_kind in BASE_TYPE_KIND_INT

    def is_wrapped(self) -> bool:
        return self.node is DefType

    def underlying_wrapped_type(self) -> "CanonType":
        assert self.is_wrapped()
        return self.children[0]

    def is_fun(self) -> bool:
        return self.node is TypeFun

    def is_rec(self) -> bool:
        return self.node is DefRec

    def parameter_types(self) -> List["CanonType"]:
        assert self.is_fun()
        return self.children[:-1]

    def result_type(self) -> "CanonType":
        assert self.is_fun()
        return self.children[-1]

    def is_pointer(self) -> bool:
        return self.node is TypePtr

    def is_slice(self) -> bool:
        return self.node is TypeSlice

    def is_enum(self) -> bool:
        return self.node is DefEnum

    def is_base_type(self) -> bool:
        return self.node is TypeBase

    def is_base_or_enum_type(self) -> bool:
        return self.node is TypeBase or self.node is DefEnum

    def is_sum(self) -> bool:
        return self.node is TypeSum

    def is_untagged_sum(self) -> bool:
        return self.node is TypeSum and self.untagged

    def is_tagged_sum(self) -> bool:
        return self.node is TypeSum and not self.untagged

    def sum_types(self) -> List["CanonType"]:
        assert self.is_sum()
        return self.children

    def is_array(self) -> bool:
        return self.node is TypeArray

    def is_void_or_wrapped_void(self) -> bool:
        if self.node is DefType:
            return self.children[0].is_void()
        return self.is_void()

    def underlying_pointer_type(self) -> "CanonType":
        assert self.is_pointer()
        return self.children[0]

    def underlying_slice_type(self) -> "CanonType":
        assert self.is_slice()
        return self.children[0]

    def underlying_array_type(self) -> "CanonType":
        assert self.is_array()
        return self.children[0]

    def is_array_or_slice(self) -> bool:
        return self.node is TypeArray or self.node is TypeSlice

    def underlying_array_or_slice_type(self) -> "CanonType":
        assert self.is_array() or self.is_slice()
        return self.children[0]

    def contained_type(self) -> "CanonType":
        if self.node is TypeArray or self.node is TypeSlice:
            return self.children[0]
        else:
            assert False, f"unexpected type: {self.name}"

    def array_dim(self):
        assert self.is_array()
        return self.dim

    def array_element_size(self):
        assert self.is_array()
        return self.size // self.dim

    def is_mutable(self) -> bool:
        return self.mut

    def fits_in_register(self) -> bool:
        reg_type = self.register_types
        return reg_type is not None and len(reg_type) == 1

    def get_single_register_type(self) -> str:
        reg_type = self.register_types
        assert reg_type is not None and len(reg_type) == 1
        return reg_type[0]

    def __str__(self):
        return self.name
############################################################
# Emphemeral
############################################################


@NodeCommon
@dataclasses.dataclass()
class EphemeralList:
    """Only exist temporarily after a replacement strep

    will removed (flattened) in the next cleanup step
    """
    ALIAS = None
    GROUP = GROUP.Macro
    FLAGS = NF.NON_CORE
    #
    args: List[NODES_EXPR_T]
    #
    colon: bool = False  # colon style list
    #
    x_srcloc: Optional[Any] = None

############################################################
# Identifier
############################################################


@NodeCommon
@dataclasses.dataclass()
class Id:
    """Refers to a type, variable, constant, function, module by name.

    Ids may contain a path component indicating which modules they reference.
    """
    ALIAS = "id"
    GROUP = GROUP.Misc
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.SYMBOL_ANNOTATED | NF.MAY_BE_LHS | NF.MODULE_ANNOTATED
    #
    name: str          # id or mod::id or enum::id or mod::enum::id
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None
    x_symbol: Optional[Any] = None
    x_module: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name}"


@NodeCommon
@dataclasses.dataclass()
class TypeAuto:
    """Placeholder for an unspecified (auto derived) type

    My only occur where explicitly allowed.
    """
    ALIAS = "auto"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


############################################################
# TypeNodes
############################################################
@NodeCommon
@dataclasses.dataclass()
class FunParam:
    """Function parameter

    """
    ALIAS = "param"
    GROUP = GROUP.Type
    FLAGS = NF.LOCAL_SYM_DEF
    #
    name: str      # empty str means no var specified (fun proto type)
    type: NODES_TYPES_T
    #
    arg_ref: bool = False
    res_ref: bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name}: {self.type}"


BASE_TYPE_KIND_UINT = set([
    BASE_TYPE_KIND.U8,
    BASE_TYPE_KIND.U16,
    BASE_TYPE_KIND.U32,
    BASE_TYPE_KIND.U64,
])

BASE_TYPE_KIND_SINT = set([
    BASE_TYPE_KIND.S8,
    BASE_TYPE_KIND.S16,
    BASE_TYPE_KIND.S32,
    BASE_TYPE_KIND.S64,
])

BASE_TYPE_KIND_INT = BASE_TYPE_KIND_UINT | BASE_TYPE_KIND_SINT

BASE_TYPE_KIND_REAL = set([
    BASE_TYPE_KIND.R32,
    BASE_TYPE_KIND.R64,
])


BASE_TYPE_KIND_TO_SIZE: Dict[BASE_TYPE_KIND, int] = {
    BASE_TYPE_KIND.U8: 1,
    BASE_TYPE_KIND.U16: 2,
    BASE_TYPE_KIND.U32: 4,
    BASE_TYPE_KIND.U64: 8,

    BASE_TYPE_KIND.S8: 1,
    BASE_TYPE_KIND.S16: 2,
    BASE_TYPE_KIND.S32: 4,
    BASE_TYPE_KIND.S64: 8,
    BASE_TYPE_KIND.R32: 4,
    BASE_TYPE_KIND.R64: 8,
    BASE_TYPE_KIND.TYPEID: 2,
    BASE_TYPE_KIND.BOOL: 1,
    #
    BASE_TYPE_KIND.VOID: 0,
    BASE_TYPE_KIND.NORET: 0,

}


@NodeCommon
@dataclasses.dataclass()
class TypeBase:
    """Base type

    One of: void, bool, r32, r64, u8, u16, u32, u64, s8, s16, s32, s64
    """
    ALIAS = None
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.TYPE_CORPUS
    #
    base_type_kind: BASE_TYPE_KIND
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.base_type_kind.name}"


@NodeCommon
@dataclasses.dataclass()
class TypePtr:
    """Pointer type
    """
    ALIAS = "ptr"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.TYPE_CORPUS
    #
    type: NODES_TYPES_T
    #
    mut: bool = False  # pointee is mutable
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}{_FLAGS(self)} {self.type}"


@NodeCommon
@dataclasses.dataclass()
class TypeSlice:
    """A view/slice of an array with compile-time unknown dimensions

    Internally, this is tuple of `start` and `length`
    (mutable/non-mutable)
    """
    ALIAS = "slice"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.TYPE_CORPUS | NF.NON_CORE
    #
    type: NODES_TYPES_T
    #
    mut: bool = False  # slice is mutable
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        mod = "-MUT" if self.mut else ""
        return f"{_NAME(self)}{mod}({self.type})"


@NodeCommon
@dataclasses.dataclass()
class TypeArray:
    """An array of the given type and `size`

    """
    ALIAS = "array"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.TYPE_CORPUS
    #
    size: "NODES_EXPR_T"      # must be const and unsigned
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} ({self.type}) {self.size}"


@NodeCommon
@dataclasses.dataclass()
class TypeFun:
    """A function signature

    The `FunParam.name` field is ignored and should be `_`
    """
    ALIAS = "sig"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.TYPE_CORPUS
    #
    params: List[NODES_PARAMS_T]
    result: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        t = [str(t) for t in self.params]
        return f"{_NAME(self)} {' '.join(t)} -> {self.result}"


@NodeCommon
@dataclasses.dataclass()
class TypeSum:
    """Sum types (tagged unions)

    Sums are "auto flattening", e.g.
    Sum(a, Sum(b,c), Sum(a, d)) = Sum(a, b, c, d)
    """
    ALIAS = "union"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.TYPE_CORPUS
    #
    types: List[NODES_TYPES_T]
    #
    untagged: bool = False
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        t = [str(t) for t in self.types]
        extra = "-untagged" if self.untagged else ""
        return f"{_NAME(self)}{extra} {' '.join(t)}"


@NodeCommon
@dataclasses.dataclass()
class TypeSumDelta:
    """Type resulting from the difference of SumType and a non-empty subset sets of its elements
    """
    ALIAS = "sumdelta"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED
    #
    type: NODES_TYPES_T
    subtrahend: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}{self.type} - {self.subtrahend}"


@NodeCommon
@dataclasses.dataclass()
class TypeOf:
    """Type of the expression
    """
    ALIAS = "typeof"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.NON_CORE
    #
    expr: NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"
############################################################
# Val Nodes
############################################################


@NodeCommon
@dataclasses.dataclass()
class ValAuto:
    """Placeholder for an unspecified (auto derived) value

    Used for: array dimensions, enum values, chap and range
    """
    ALIAS = "auto_val"
    GROUP = GROUP.Value
    FLAGS = NF.VALUE_ANNOTATED | NF.TYPE_ANNOTATED
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


@NodeCommon
@dataclasses.dataclass()
class ValTrue:
    """Bool constant `true`"""
    ALIAS = "true"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


@NodeCommon
@dataclasses.dataclass()
class ValFalse:
    """Bool constant `false`"""
    ALIAS = "false"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


@NodeCommon
@dataclasses.dataclass()
class ValNum:
    """Numeric constant (signed int, unsigned int, real

    Underscores in `number` are ignored. `number` can be explicitly typed via
    suffices like `_u64`, `_s16`, `_r32`.
    """
    ALIAS = "num"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    number: str   # maybe a (unicode) character as well
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.number}"


@NodeCommon
@dataclasses.dataclass()
class ValUndef:
    """Special constant to indiciate *no default value*
    """
    ALIAS = "undef"
    GROUP = GROUP.Value
    FLAGS = NF.VALUE_ANNOTATED
    #
    x_srcloc: Optional[Any] = None
    x_value: Optional[Any] = None    # this is always a ValUndef() object

    def __str__(self):
        return f"{_NAME(self)}"


@NodeCommon
@dataclasses.dataclass()
class ValVoid:
    """Only value inhabiting the `TypeVoid` type

    It can be used to model *null* in nullable pointers via a sum type.
     """
    ALIAS = "void_val"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


@NodeCommon
@dataclasses.dataclass()
class IndexVal:
    """Part of an array literal

    e.g. `.1 = 5`
    If index is empty use `0` or `previous index + 1`.
    """
    ALIAS = "index_val"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    value_or_undef: "NODES_EXPR_T"
    init_index: "NODES_EXPR_T"  # compile time constant
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} [{self.init_index}] = {self.value_or_undef}"


@NodeCommon
@dataclasses.dataclass()
class FieldVal:
    """Part of rec literal

    e.g. `.imag = 5`
    If field is empty use `first field` or `next field`.
    """
    ALIAS = "field_val"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.FIELD_ANNOTATED
    #
    value_or_undef: "NODES_EXPR_T"
    init_field: str
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None
    x_field: Optional["RecField"] = None

    def __str__(self):
        return f"{_NAME(self)} {self.init_field}={self.value_or_undef}"


@NodeCommon
@dataclasses.dataclass()
class ValArray:
    """An array literal

    `[10]int{.1 = 5, .2 = 6, 77}`

    `expr_size` must be constant or auto
    """
    ALIAS = "array_val"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    expr_size: Union["NODES_EXPR_T", ValAuto]
    type: NODES_TYPES_T
    inits_array: List[NODES_INITS_ARRAY_T]
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} type={self.type} size={self.expr_size}"


@NodeCommon
@dataclasses.dataclass()
class ValSlice:
    """A slice value comprised of a pointer and length

    type and mutability is defined by the pointer
    """
    ALIAS = "slice_val"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    pointer: "NODES_EXPR_T"
    expr_size: "NODES_EXPR_T"
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.pointer} {self.expr_size}"


@NodeCommon
@dataclasses.dataclass()
class ValString:
    """An array value encoded as a string

    type is `[strlen(string)]u8`. `string` may be escaped/raw
    """
    ALIAS = None
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    string: str
    #
    strkind: str = ""   # or raw or hex
    triplequoted: bool = False
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.string}"


@NodeCommon
@dataclasses.dataclass()
class ValRec:
    """A record literal

    `E.g.: complex{.imag = 5, .real = 1}`
    """
    ALIAS = "rec_val"
    GROUP = GROUP.Value
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    type: NODES_TYPES_T
    inits_field: List[NODES_INITS_REC_T]
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        t = [str(i) for i in self.inits_field]
        return f"{_NAME(self)} [{self.type}] {' '.join(t)}"


############################################################
# ExprNode
############################################################


@NodeCommon
@dataclasses.dataclass()
class ExprDeref:
    """Dereference a pointer represented by `expr`"""
    ALIAS = "^"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.MAY_BE_LHS
    #
    expr: NODES_EXPR_T  # must be of type AddrOf
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.expr}"


@NodeCommon
@dataclasses.dataclass()
class ExprAddrOf:
    """Create a pointer to object represented by `expr`

    Pointer can optionally point to a mutable object if the
    pointee is mutable.
    """
    ALIAS = "&"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    expr_lhs: NODES_EXPR_T
    #
    mut: bool = False
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}{_FLAGS(self)} {self.expr_lhs}"


@NodeCommon
@dataclasses.dataclass()
class ExprCall:
    """Function call expression.
    """
    ALIAS = "call"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    callee: NODES_EXPR_T
    args: List[NODES_EXPR_T]
    #
    polymorphic: bool = False
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.callee}"


@NodeCommon
@dataclasses.dataclass()
class ExprParen:
    """Used for preserving parenthesis in the source
    """
    ALIAS = None
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    expr: NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None


@NodeCommon
@dataclasses.dataclass()
class ExprField:
    """Access field in expression representing a record.
    """
    ALIAS = "."
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.FIELD_ANNOTATED | NF.MAY_BE_LHS
    #
    container: NODES_EXPR_T  # must be of type rec
    field: str
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None
    x_field: Optional["RecField"] = None

    def __str__(self):
        return f"{_NAME(self)} {self.container} . {self.field}"


@NodeCommon
@dataclasses.dataclass()
class Expr1:
    """Unary expression."""
    ALIAS = None
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    unary_expr_kind: UNARY_EXPR_KIND
    expr: NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.unary_expr_kind} {self.expr}"


@NodeCommon
@dataclasses.dataclass()
class ExprPointer:
    """Pointer arithmetic expression - optionally bound checked.."""
    ALIAS = None
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    pointer_expr_kind: POINTER_EXPR_KIND
    expr1: NODES_EXPR_T
    expr2: NODES_EXPR_T
    expr_bound_or_undef: NODES_EXPR_T

    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{self.pointer_expr_kind.name}({self.expr1}, {self.expr2}, {self.expr_bound_or_undef})"


@NodeCommon
@dataclasses.dataclass()
class Expr2:
    """Binary expression."""
    ALIAS = None
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    binary_expr_kind: BINARY_EXPR_KIND
    expr1: NODES_EXPR_T
    expr2: NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{self.binary_expr_kind.name}({self.expr1}, {self.expr2})"


@NodeCommon
@dataclasses.dataclass()
class Expr3:
    """Tertiary expression (like C's `? :`)
    """
    ALIAS = "?"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    cond: NODES_EXPR_T  # must be of type  bool
    expr_t: NODES_EXPR_T
    expr_f: NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"? {self.cond} {self.expr_t} {self.expr_f}"

# Array/Slice Expressions


@NodeCommon
@dataclasses.dataclass()
class ExprIndex:
    """Optionally unchecked indexed access of array or slice
    """
    ALIAS = "at"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.MAY_BE_LHS | NF.NON_CORE
    #
    container: NODES_EXPR_T  # must be of type slice or array
    expr_index: NODES_EXPR_T  # must be of int type
    #
    unchecked: bool = False
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"AT {self.container} {self.expr_index}"


@NodeCommon
@dataclasses.dataclass()
class ExprLen:
    """Length of array or slice

    Result type is `uint`.
    """
    ALIAS = "len"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    container: NODES_EXPR_T   # must be of type slice or array
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return self.__class__.__name__
# Cast Like Expressions


@NodeCommon
@dataclasses.dataclass()
class ExprFront:
    """Address of the first element of an array or slice

    Similar to `(& (at container 0))` but will not fail if container has zero size
    """
    ALIAS = "front"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    container: NODES_EXPR_T   # must be of type slice or array
    #
    mut: bool = False
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return self.__class__.__name__


# Cast Like Expressions
@NodeCommon
@dataclasses.dataclass()
class ExprIs:
    """Test actual expression type


    Typically used when `expr` is a tagged sum type.

    """
    ALIAS = "is"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    expr: NODES_EXPR_T
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.expr} {self.type}"


@NodeCommon
@dataclasses.dataclass()
class ExprWrap:
    """Cast: underlying type -> enum/wrapped
    """
    ALIAS = "wrap"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    expr: NODES_EXPR_T
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{self.expr} WRAP {self.type}"


@NodeCommon
@dataclasses.dataclass()
class ExprUnwrap:
    """Cast: enum/wrapped -> underlying type
    """
    ALIAS = "unwrap"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    expr: NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{self.__class__.__name__} {self.expr}"


@NodeCommon
@dataclasses.dataclass()
class ExprAs:
    """Safe Cast (Conversion)

    Allowed:
    u8-u64, s8-s64 <-> u8-u64, s8-s64
    u8-u64, s8-s64 -> r32-r64  (note: one way only)
    """
    ALIAS = "as"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    expr: NODES_EXPR_T
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{self.expr} AS {self.type}"


@NodeCommon
@dataclasses.dataclass()
class ExprNarrow:
    """Narrowing Cast (for unions)

    """
    ALIAS = "narrowto"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    expr: NODES_EXPR_T
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{self.expr} NARROW_TO {self.type}"


@NodeCommon
@dataclasses.dataclass()
class ExprUnsafeCast:
    """Unsafe Cast

    Allowed:
    ptr a <-> ptr b

    """
    ALIAS = "cast"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED
    #
    expr: NODES_EXPR_T
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.type}"


@NodeCommon
@dataclasses.dataclass()
class ExprBitCast:
    """Bit cast.

    Type must have same size and alignment as type of item

    s32,u32,f32 <-> s32,u32,f32
    s64,u64, f64 <-> s64,u64, f64
    sint, uint <-> ptr

    It is also ok to bitcase complex objects like recs
    """
    ALIAS = "bitcast"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    expr: NODES_EXPR_T
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.type}"


@NodeCommon
@dataclasses.dataclass()
class ExprTypeId:
    """TypeId of type

    Result has type is `typeid`"""
    ALIAS = "typeid"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.type}"


@NodeCommon
@dataclasses.dataclass()
class ExprSumTag:
    """Typetage of tagged sum type

    result has type is `typeid`"""
    ALIAS = "sumtypetag"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    expr: NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.expr}"


@NodeCommon
@dataclasses.dataclass()
class ExprSumUntagged:
    """Untagged sum portion of tagged sum type

    Result has type untagged sum"""
    ALIAS = "sumuntagged"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    expr: NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.expr}"


@NodeCommon
@dataclasses.dataclass()
class ExprSizeof:
    """Byte size of type

    Result has type is `uint`"""
    ALIAS = "sizeof"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.NON_CORE
    #
    type: NODES_TYPES_T
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.type}"


@NodeCommon
@dataclasses.dataclass()
class ExprOffsetof:
    """Byte offset of field in record types

    Result has type `uint`"""
    ALIAS = "offsetof"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED | NF.FIELD_ANNOTATED | NF.NON_CORE
    #
    type: NODES_TYPES_T  # must be rec
    field: str
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None
    x_field: Optional["RecField"] = None

    def __str__(self):
        return f"{_NAME(self)} {self.type} {self.field}"


@NodeCommon
@dataclasses.dataclass()
class ExprStmt:
    """Expr with Statements

    The body statements must be terminated by a StmtReturn
    """
    ALIAS = "expr"
    GROUP = GROUP.Expression
    FLAGS = NF.TYPE_ANNOTATED | NF.VALUE_ANNOTATED
    #
    body: List[NODES_BODY_T]  # new scope
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


############################################################
# Stmt
############################################################
@NodeCommon
@dataclasses.dataclass()
class StmtBlock:
    """Block statement.

    if `label` is non-empty, nested break/continue statements can target this `block`.
    """
    ALIAS = "block"
    GROUP = GROUP.Statement
    FLAGS = NF(0)
    #
    label: str
    body: List[NODES_BODY_T]  # new scope
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.label}"


@NodeCommon
@dataclasses.dataclass()
class StmtDefer:
    """Defer statement

    Note: defer body's containing return statments have
    non-straightforward semantics.
    """
    ALIAS = "defer"
    GROUP = GROUP.Statement
    FLAGS = NF.NON_CORE
    #
    body:  List[NODES_BODY_T]  # new scope, must NOT contain RETURN
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


@NodeCommon
@dataclasses.dataclass()
class StmtIf:
    """If statement"""
    ALIAS = "if"
    GROUP = GROUP.Statement
    FLAGS = NF(0)
    #
    cond: NODES_EXPR_T        # must be of type bool
    body_t: List[NODES_BODY_T]  # new scope
    body_f: List[NODES_BODY_T]  # new scope
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.cond}"


@NodeCommon
@dataclasses.dataclass()
class Case:
    """Single case of a Cond statement"""
    ALIAS = "case"
    GROUP = GROUP.Statement
    FLAGS = NF.NON_CORE
    #
    cond: NODES_EXPR_T        # must be of type bool
    body: List[NODES_BODY_T]  # new scope
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.cond}"


@NodeCommon
@dataclasses.dataclass()
class StmtCond:
    """Multicase if-elif-else statement"""
    ALIAS = "cond"
    GROUP = GROUP.Statement
    FLAGS = NF.NON_CORE
    #
    cases: List[NODES_CASES_T]
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


@NodeCommon
@dataclasses.dataclass()
class StmtBreak:
    """Break statement

    use "" if the target is the nearest for/while/block """
    ALIAS = "break"
    GROUP = GROUP.Statement
    FLAGS = NF.CONTROL_FLOW
    #
    target: str  # use "" for no value
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_target: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.target}"


@NodeCommon
@dataclasses.dataclass()
class StmtContinue:
    """Continue statement

    use "" if the target is the nearest for/while/block """
    ALIAS = "continue"
    GROUP = GROUP.Statement
    FLAGS = NF.CONTROL_FLOW
    #
    target: str  # use "" for no value
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_target: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.target}"


@NodeCommon
@dataclasses.dataclass()
class StmtReturn:
    """Return statement

    Returns from the first enclosing ExprStmt node or the enclosing DefFun node.
    Uses void_val if the DefFun's return type is void
    """
    ALIAS = "return"
    GROUP = GROUP.Statement
    FLAGS = NF.CONTROL_FLOW
    #
    expr_ret: NODES_EXPR_T
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_target: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.expr_ret}"


@NodeCommon
@dataclasses.dataclass()
class StmtExpr:
    """Expression statement

    Turns an expression (typically a call) into a statement
    """
    ALIAS = "stmt"
    GROUP = GROUP.Statement
    FLAGS = NF.NONE
    #
    expr: ExprCall
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.expr}"


@NodeCommon
@dataclasses.dataclass()
class StmtStaticAssert:
    """Static assert statement (must evaluate to true at compile-time"""
    ALIAS = "static_assert"
    GROUP = GROUP.Statement
    FLAGS = NF.TOP_LEVEL | NF.NON_CORE
    #
    cond: NODES_EXPR_T  # must be of type bool
    message: str     # should this be an expression?
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.cond}"


@NodeCommon
@dataclasses.dataclass()
class StmtTrap:
    """Trap statement"""
    ALIAS = "trap"
    GROUP = GROUP.Statement
    FLAGS = NF.NONE
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}"


@NodeCommon
@dataclasses.dataclass()
class StmtCompoundAssignment:
    """Compound assignment statement"""
    ALIAS = None
    GROUP = GROUP.Statement
    FLAGS = NF.NON_CORE
    #
    assignment_kind: ASSIGNMENT_KIND
    lhs: NODES_LHS_T
    expr_rhs: NODES_EXPR_T
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} [{self.assignment_kind.name}] {self.lhs} = {self.expr_rhs}"


@NodeCommon
@dataclasses.dataclass()
class StmtAssignment:
    """Assignment statement"""
    ALIAS = "="
    GROUP = GROUP.Statement
    FLAGS = NF.NONE
    #
    lhs: NODES_LHS_T
    expr_rhs: NODES_EXPR_T
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.lhs} = {self.expr_rhs}"


############################################################
# Definitions
############################################################
@NodeCommon
@dataclasses.dataclass()
class RecField:  #
    """Record field

    All fields must be explicitly initialized. Use `ValUndef` in performance
    sensitive situations.
    """
    ALIAS = "field"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.TYPE_CORPUS
    #
    name: str
    type: NODES_TYPES_T
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_offset: int = -1

    def __str__(self):
        return f"{_NAME(self)} {self.name}: {self.type}"


@NodeCommon
@dataclasses.dataclass()
class DefRec:
    """Record definition"""
    ALIAS = "defrec"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_CORPUS | NF.TYPE_ANNOTATED | NF.GLOBAL_SYM_DEF | NF.TOP_LEVEL
    #
    name: str
    fields: List[NODES_FIELDS_T]
    #
    pub:  bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}{_FLAGS(self)} {self.name}"


@NodeCommon
@dataclasses.dataclass()
class EnumVal:
    """ Enum element.

     `value: ValAuto` means previous value + 1"""
    ALIAS = "entry"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_ANNOTATED | NF.GLOBAL_SYM_DEF | NF.VALUE_ANNOTATED
    #
    name: str
    value_or_auto: Union["ValNum", ValAuto]
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name}: {self.value_or_auto}"


@NodeCommon
@dataclasses.dataclass()
class DefEnum:
    """Enum definition"""
    ALIAS = "enum"
    GROUP = GROUP.Type
    FLAGS = NF.TYPE_CORPUS | NF.TYPE_ANNOTATED | NF.GLOBAL_SYM_DEF | NF.TOP_LEVEL | NF.VALUE_ANNOTATED
    #
    name: str
    base_type_kind: BASE_TYPE_KIND   # must be integer
    items: List[NODES_ITEMS_T]
    #
    pub:  bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_value: Optional[Any] = None  # used to guide the evaluation of EnumVal

    def __str__(self):
        return f"{_NAME(self)}{_FLAGS(self)} {self.name}"


@NodeCommon
@dataclasses.dataclass()
class DefType:
    """Type definition

    A `wrapped` gives the underlying type a new name that is not type compatible.
    To convert between the two use an `as` cast expression.
    """
    ALIAS = "type"
    GROUP = GROUP.Statement
    FLAGS = NF.TYPE_ANNOTATED | NF.TYPE_CORPUS | NF.GLOBAL_SYM_DEF | NF.TOP_LEVEL
    #
    name: str
    type: NODES_TYPES_T
    #
    pub:  bool = False
    wrapped: bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}{_FLAGS(self)} {self.name} = {self.type}"


@NodeCommon
@dataclasses.dataclass()
class DefVar:
    """Variable definition at local scope (DefGlobal is used for global scope)

    Allocates space on stack (or in a register) and initializes it with `initial_or_undef_or_auto`.
    `mut` makes the allocated space read/write otherwise it is readonly.
    `ref` allows the address of the  variable to be taken and prevents register allocation.

    """
    ALIAS = "let"
    GROUP = GROUP.Statement
    FLAGS = NF.LOCAL_SYM_DEF
    #
    name: str
    type_or_auto: NODES_TYPES_OR_AUTO_T
    initial_or_undef_or_auto: NODES_EXPR_T
    #
    mut: bool = False
    ref: bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}{_FLAGS(self)} {self.name} {self.type_or_auto} {self.initial_or_undef_or_auto}"


@NodeCommon
@dataclasses.dataclass()
class DefGlobal:
    """Variable definition at global scope (DefVar is used for local scope)

    Allocates space in static memory and initializes it with `initial_or_undef`.
    `mut` makes the allocated space read/write otherwise it is readonly.
    """
    ALIAS = "global"
    GROUP = GROUP.Statement
    FLAGS = NF.GLOBAL_SYM_DEF | NF.TOP_LEVEL
    #
    name: str
    type_or_auto: NODES_TYPES_OR_AUTO_T
    initial_or_undef_or_auto: NODES_EXPR_T
    #
    pub: bool = False
    mut: bool = False
    cdecl: bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}{_FLAGS(self)} {self.name} {self.type_or_auto} {self.initial_or_undef_or_auto}"


@NodeCommon
@dataclasses.dataclass()
class DefFun:
    """Function definition

    `init` and `fini` indicate module initializer/finalizers

    `extern` indicates a prototype and hence the function body must be empty.
    """
    ALIAS = "fun"
    GROUP = GROUP.Statement
    FLAGS = NF.TYPE_ANNOTATED | NF.GLOBAL_SYM_DEF | NF.TOP_LEVEL | NF.MODULE_ANNOTATED
    #
    name: str
    params: List[NODES_PARAMS_T]
    result: NODES_TYPES_T
    body: List[NODES_BODY_T]  # new scope
    #
    polymorphic: bool = False
    init: bool = False
    fini: bool = False
    pub: bool = False
    extern: bool = False
    cdecl: bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_type: Optional[Any] = None
    x_module: Optional["DefMod"] = None  # only use for polymorphic function

    def __str__(self):
        params = ', '.join(str(p) for p in self.params)
        return f"{_NAME(self)}{_FLAGS(self)} {self.name} [{params}]->{self.result}"


@NodeCommon
@dataclasses.dataclass()
class ModParam:
    """Module Parameters"""
    ALIAS = None
    GROUP = GROUP.Statement
    FLAGS = NF.GLOBAL_SYM_DEF | NF.NON_CORE
    #
    name: str
    mod_param_kind: MOD_PARAM_KIND
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name} {self.mod_param_kind.name}"


@NodeCommon
@dataclasses.dataclass(order=True)
class DefMod:
    """Module Definition

    The module is a template if `params` is non-empty

    ordering is used to put the modules in a deterministic order
    """
    ALIAS = "module"
    GROUP = GROUP.Statement
    FLAGS = NF.GLOBAL_SYM_DEF | NF.MODNAME_ANNOTATED
    #
    name: str
    params_mod: List[NODES_PARAMS_MOD_T]
    body_mod: List[NODES_BODY_MOD_T]
    #
    doc: str = ""
    builtin: bool = False
    #
    x_srcloc: Optional[Any] = None
    x_modname: str = ""

    def __str__(self):
        params = ', '.join(str(p) for p in self.params_mod)
        return f"{_NAME(self)}{_FLAGS(self)} {self.name} [{params}]"


@NodeCommon
@dataclasses.dataclass()
class Import:
    """Import another Module from `path` as `name`"""
    ALIAS = "import"
    GROUP = GROUP.Statement
    FLAGS = NF.GLOBAL_SYM_DEF | NF.NON_CORE | NF.MODULE_ANNOTATED
    #
    name: str
    alias: str
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None
    x_module: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name}"


############################################################
# Macro Like
############################################################
@NodeCommon
@dataclasses.dataclass()
class ExprSrcLoc:
    """Source Location encoded as u32"""
    ALIAS = "src_loc"
    GROUP = GROUP.Expression
    FLAGS = NF.TO_BE_EXPANDED | NF.NON_CORE
    #
    x_srcloc: Optional[Any] = None


@NodeCommon
@dataclasses.dataclass()
class ExprStringify:
    """Human readable representation of the expression

    This is useful to implement for assert like features
    """
    ALIAS = "stringify"
    GROUP = GROUP.Expression
    FLAGS = NF.TO_BE_EXPANDED | NF.NON_CORE
    #
    expr:  NODES_EXPR_T
    #
    x_srcloc: Optional[Any] = None

############################################################
# Macro
############################################################


@NodeCommon
@dataclasses.dataclass()
class MacroId:
    """Placeholder for a parameter

    This node will be expanded with the actual argument
    """
    ALIAS = "macro_id"
    GROUP = GROUP.Macro
    FLAGS = NF.NON_CORE
    #
    name: str
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name}"


@NodeCommon
@dataclasses.dataclass()
class MacroVar:
    """Macro Variable definition whose name stems from a macro parameter or macro_gen_id"

    `name` must start with a `$`.

    """
    ALIAS = "macro_let"
    GROUP = GROUP.Macro
    FLAGS = NF.TYPE_ANNOTATED | NF.LOCAL_SYM_DEF | NF.MACRO_BODY_ONLY | NF.NON_CORE
    #
    name: str
    type_or_auto: NODES_TYPES_OR_AUTO_T
    initial_or_undef_or_auto: NODES_EXPR_T
    #
    mut: bool = False
    ref: bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)}{_FLAGS(self)} {self.name} {self.initial_or_undef_or_auto}"


@NodeCommon
@dataclasses.dataclass()
class MacroFor:
    """Macro for-loop like statement

    loops over the macro parameter `name_list` which must be a list and
    binds each list element to `name` while expanding the AST nodes in `body_for`.
    """
    ALIAS = "macro_for"
    GROUP = GROUP.Macro
    FLAGS = NF.MACRO_BODY_ONLY | NF.NON_CORE
    #
    name: str
    name_list: str
    body_for: List[Any]
    #
    x_srcloc: Optional[Any] = None


@NodeCommon
@dataclasses.dataclass()
class MacroParam:
    """Macro Parameter"""
    ALIAS = "mparam"
    GROUP = GROUP.Macro
    FLAGS = NF.LOCAL_SYM_DEF | NF.NON_CORE
    #
    name: str
    macro_param_kind: MACRO_PARAM_KIND
    #
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name} {self.macro_param_kind.name}"


@NodeCommon
@dataclasses.dataclass()
class MacroInvoke:
    """Macro Invocation"""
    ALIAS = "macro_invoke"
    GROUP = GROUP.Macro
    FLAGS = NF.TO_BE_EXPANDED | NF.NON_CORE | NF.MODULE_ANNOTATED
    #
    name: str
    args: List[NODES_EXPR_T]
    #
    x_srcloc: Optional[Any] = None
    x_module: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name}"


@NodeCommon
@dataclasses.dataclass()
class DefMacro:
    """Define a macro

    A macro consists of
    * a name
    * the type of AST node (list) it create
    * a parameter list. A parameter name must start with a '$'
    * a list of additional identifiers used by the macro (also starimg with '$')
    * a body containing both regular and macro specific AST node serving as a template
    """
    ALIAS = "macro"
    GROUP = GROUP.Statement
    FLAGS = NF.GLOBAL_SYM_DEF | NF.TOP_LEVEL | NF.NON_CORE
    #
    name: str
    macro_result_kind: MACRO_PARAM_KIND
    params_macro: List[NODES_PARAMS_MACRO_T]
    gen_ids: List[str]
    body_macro: List[Any]  # new scope
    #
    pub: bool = False
    doc: str = ""
    #
    x_srcloc: Optional[Any] = None

    def __str__(self):
        return f"{_NAME(self)} {self.name}"


BINOP_BOOL = {
    BINARY_EXPR_KIND.GE,
    BINARY_EXPR_KIND.GT,
    BINARY_EXPR_KIND.LE,
    BINARY_EXPR_KIND.LT,
    BINARY_EXPR_KIND.EQ,
    BINARY_EXPR_KIND.NE,
    BINARY_EXPR_KIND.ANDSC,
    BINARY_EXPR_KIND.ORSC,
}

BINOP_OPS_HAVE_SAME_TYPE = {
    BINARY_EXPR_KIND.GE,
    BINARY_EXPR_KIND.GT,
    BINARY_EXPR_KIND.LE,
    BINARY_EXPR_KIND.LT,
    BINARY_EXPR_KIND.EQ,
    BINARY_EXPR_KIND.NE,
    #
    BINARY_EXPR_KIND.ADD,
    BINARY_EXPR_KIND.SUB,
    BINARY_EXPR_KIND.MUL,
    BINARY_EXPR_KIND.DIV,
    BINARY_EXPR_KIND.REM,
    BINARY_EXPR_KIND.MIN,
    BINARY_EXPR_KIND.MAX,
    #
    BINARY_EXPR_KIND.ANDSC,
    BINARY_EXPR_KIND.ORSC,
    #
    BINARY_EXPR_KIND.SHL,
    BINARY_EXPR_KIND.SHR,
    #
    BINARY_EXPR_KIND.AND,
    BINARY_EXPR_KIND.OR,
    BINARY_EXPR_KIND.XOR,
}


############################################################
#
############################################################
def VisitAstRecursively(node, visitor, field=None):
    visitor(node, field)

    for f, nfd in node.__class__.FIELDS:
        if nfd.kind is NFK.NODE:
            child = getattr(node, f)
            VisitAstRecursively(child, visitor, f)
        elif nfd.kind is NFK.LIST:
            for child in getattr(node, f):
                VisitAstRecursively(child, visitor, f)


def VisitAstRecursivelyWithParent(node, visitor, parent, field=None):
    visitor(node, parent, field)

    for f, nfd in node.__class__.FIELDS:
        if nfd.kind is NFK.NODE:
            child = getattr(node, f)
            VisitAstRecursivelyWithParent(child, visitor, node, f)
        elif nfd.kind is NFK.LIST:
            for child in getattr(node, f):
                VisitAstRecursivelyWithParent(child, visitor, node, f)


def VisitAstRecursivelyPost(node, visitor, field=None):
    for f, nfd in node.__class__.FIELDS:
        if nfd.kind is NFK.NODE:
            child = getattr(node, f)
            VisitAstRecursivelyPost(child, visitor, f)
        elif nfd.kind is NFK.LIST:
            for child in getattr(node, f):
                VisitAstRecursivelyPost(child, visitor, f)

    visitor(node, field)


def VisitAstRecursivelyWithAllParents(node, parents: List[Any], visitor):
    if visitor(node, parents):
        return
    parents.append(node)
    for c, nfd in node.__class__.FIELDS:
        if nfd.kind is NFK.NODE:
            VisitAstRecursivelyWithAllParents(
                getattr(node, c), parents, visitor)
        elif nfd.kind is NFK.LIST:
            for child in getattr(node, c):
                VisitAstRecursivelyWithAllParents(child, parents, visitor)
    parents.pop(-1)


def MaybeReplaceAstRecursively(node, replacer):
    """Note: the root node will not be replaced"""
    for f, nfd in node.__class__.FIELDS:
        if nfd.kind is NFK.NODE:
            child = getattr(node, f)
            new_child = replacer(child, f)
            if new_child:
                setattr(node, f, new_child)
            else:
                MaybeReplaceAstRecursively(child, replacer)
        elif nfd.kind is NFK.LIST:
            children = getattr(node, f)
            for n, child in enumerate(children):
                new_child = replacer(child, f)
                if new_child:
                    children[n] = new_child
                else:
                    MaybeReplaceAstRecursively(child, replacer)


def MaybeReplaceAstRecursivelyPost(node, replacer):
    """Note: the root node will not be replaced"""
    for f, nfd in node.__class__.FIELDS:
        # print ("replace: ", node.__class__.__name__, c)
        if nfd.kind is NFK.NODE:
            child = getattr(node, f)
            MaybeReplaceAstRecursivelyPost(child, replacer)
            new_child = replacer(child, f)
            if new_child:
                setattr(node, f, new_child)
        elif nfd.kind is NFK.LIST:
            children = getattr(node, f)
            for n, child in enumerate(children):
                MaybeReplaceAstRecursivelyPost(child, replacer)
                new_child = replacer(child, f)
                if new_child:
                    children[n] = new_child


def _MaybeFlattenEphemeralList(nodes: List[Any]):
    has_ephemeral = False
    for n in nodes:
        if isinstance(n, EphemeralList):
            has_ephemeral = True
            break
    if not has_ephemeral:
        return nodes
    out = []
    for c in nodes:
        if isinstance(c, EphemeralList):
            out += _MaybeFlattenEphemeralList(c.args)
        else:
            out.append(c)
    return out


def EliminateEphemeralsRecursively(node):
    for f, nfd in node.__class__.FIELDS:
        if nfd.kind is NFK.NODE:
            child = getattr(node, f)
            if isinstance(child, EphemeralList):
                new_child = _MaybeFlattenEphemeralList([child])
                assert len(new_child) == 1
                setattr(node, f, new_child[0])
            EliminateEphemeralsRecursively(child)
        elif nfd.kind is NFK.LIST:
            children = getattr(node, f)
            new_children = _MaybeFlattenEphemeralList(children)
            if new_children is not children:
                setattr(node, f, new_children)
            for child in children:
                EliminateEphemeralsRecursively(child)


def CloneNodeRecursively(node, var_map, block_map):
    clone = dataclasses.replace(node)
    if isinstance(clone, DefVar):
        var_map[node] = clone
    elif isinstance(clone, (StmtBlock, ExprStmt)):
        block_map[node] = clone

    if NF.SYMBOL_ANNOTATED in clone.FLAGS:
        clone.x_symbol = var_map.get(clone.x_symbol, clone.x_symbol)
    if NF.CONTROL_FLOW in clone.FLAGS:
        clone.x_taget = var_map.get(clone.x_target, clone.x_target)
    for f, nfd in node.__class__.FIELDS:
        if nfd.kind is NFK.NODE:
            setattr(clone, f, CloneNodeRecursively(
                getattr(node, f), var_map, block_map))
        elif nfd.kind is NFK.LIST:
            out = [CloneNodeRecursively(cc, var_map, block_map)
                   for cc in getattr(node, f)]
            setattr(clone, f, out)
    return clone


############################################################
# Helpers
############################################################


def StripFromListRecursively(node, cls):
    for f, nfd in node.__class__.FIELDS:
        if nfd.kind is NFK.NODE:
            child = getattr(node, f)
            StripFromListRecursively(child, cls)
        elif nfd.kind is NFK.LIST:
            children = getattr(node, f)
            for child in children:
                StripFromListRecursively(child, cls)
            new_children = [c for c in children if not isinstance(c, cls)]
            if len(new_children) != len(children):
                setattr(node, f, new_children)


############################################################
# AST Checker
############################################################


def CompilerError(srcloc, msg):
    print(f"{srcloc} ERROR: {msg}", file=sys.stdout)
    assert False


def _CheckMacroRecursively(node, seen_names: Set[str]):
    def visitor(node, _):
        if isinstance(node, (MacroParam, MacroFor)):
            assert node.name.startswith("$")
            assert node.name not in seen_names, f"duplicate name: {node.name}"
            seen_names.add(node.name)
    VisitAstRecursively(node, visitor)


def CheckAST(node, disallowed_nodes, allow_type_auto=False):
    # this forces a pre-order traversal
    toplevel_node = None

    def visitor(node, field):
        nonlocal disallowed_nodes
        nonlocal toplevel_node
        # print (f"@@@@ field={field}: {node.__class__.__name__}")

        if type(node) in disallowed_nodes:
            CompilerError(
                node.x_srcloc, f"Disallowed node: {type(node)} in {toplevel_node}")

        assert node.x_srcloc is not None, f"Node without srcloc node {node} for field {field}"

        if NF.TOP_LEVEL in node.FLAGS:
            if field != "body_mod":
                CompilerError(
                    node.x_srcloc, f"only allowed at toplevel [{field}]: {node}")
            toplevel_node = node
        if NF.MACRO_BODY_ONLY in node.FLAGS:
            assert isinstance(
                toplevel_node, DefMacro), f"only allowed in macros: {node}"
        if node.GROUP is GROUP.Ephemeral:
            assert isinstance(
                toplevel_node, DefMacro), f"only allowed in macros: {node}"
        if isinstance(node, DefMacro):
            for p in node.params_macro:
                if isinstance(p, MacroParam):
                    assert p.name.startswith("$")
            for i in node.gen_ids:
                assert i.startswith("$")
            _CheckMacroRecursively(node, set())
        elif isinstance(node, Id):
            # when we synthesize Ids later we do not bother with x_module anymore
            assert node.x_symbol is not None or isinstance(
                node.x_module, DefMod)
        elif isinstance(node, (MacroInvoke, DefFun, Import)):
            assert isinstance(node.x_module, DefMod)
        elif isinstance(node, DefMod):
            assert node.x_modname, f"missing x_modname {node}"
        if field is not None:
            nfd = ALL_FIELDS_MAP[field]
            permitted = nfd.extra
            if permitted and not isinstance(toplevel_node, DefMacro):
                if node.__class__.__name__ not in permitted:
                    if not (allow_type_auto and isinstance(node, TypeAuto)):
                        CompilerError(
                            node.x_srcloc, f"unexpected node for field={field}: {node.__class__.__name__}")

    VisitAstRecursively(node, visitor)


##########################################################################################
# Doc Generation
##########################################################################################
PROLOG = """## Abstract Syntax Tree (AST) Nodes used by Cwerg

"""


def _RenderKindSimple(name, kind, fout):
    print(f"\n### {name} Kind\n", file=fout)
    print("|Kind|", file=fout)
    print("|----|", file=fout)
    for x in kind:
        if x is kind.INVALID:
            continue
        print(f"|{x.name:10}|", file=fout)


def _RenderKind(name, kind, inv, fout):
    print(f"\n### {name} Kind\n", file=fout)
    print("|Kind|Abbrev|", file=fout)
    print("|----|------|", file=fout)
    for x in kind:
        if x is kind.INVALID:
            continue
        assert x in inv, f"No custom name defined for emnum {x}"
        print(f"|{x.name:10}|{inv[x]}|", file=fout)


def MakeAnchor(name, alias):
    out = name.lower()
    if alias:
        out += "-" + alias
    tab = str.maketrans(" ", "-", "?,^&=@#$%")
    return out.lower().translate(tab)


def GenerateDocumentation(fout):
    print(PROLOG, file=fout)
    nodes = sorted((node.__name__, node) for node in ALL_NODES)
    print("\n## Node Overview (Core)",  file=fout)
    n = 0
    for name, cls in nodes:
        if NF.NON_CORE in cls.FLAGS:
            continue
        n += 1
        alias = ""
        if cls.ALIAS:
            alias = f"&nbsp;({cls.ALIAS})"
        anchor = MakeAnchor(name, cls.ALIAS)
        print(f"[{name}{alias}](#{anchor}) &ensp;", file=fout)
    print(f"({n} nodes)", file=fout)

    print("\n## Node Overview (Non-Core)",  file=fout)
    n = 0
    for name, cls in nodes:
        if NF.NON_CORE not in cls.FLAGS:
            continue
        n += 1
        alias = ""
        if cls.ALIAS:
            alias = f"&nbsp;({cls.ALIAS})"
        anchor = MakeAnchor(name, cls.ALIAS)
        print(f"[{name}{alias}](#{anchor}) &ensp;", file=fout)
    print(f"({n} nodes)", file=fout)

    print("\n## Enum Overview",  file=fout)
    for cls in ["Expr1", "Expr2", "StmtCompoundAssignment", "Base Type",
                "ModParam", "MacroParam"]:
        name = cls + " Kind"
        anchor = MakeAnchor(name, None)
        print(f"[{name}](#{anchor}) &ensp;", file=fout)

    nodes = sorted((node.GROUP, node.__name__, node) for node in ALL_NODES)
    last_group = ""
    for group, name, cls in nodes:
        if last_group != group:
            print(f"\n## {group.name} Node Details",  file=fout)
            last_group = group
        print("", file=fout)
        alias = ""
        if cls.ALIAS:
            alias = f" ({cls.ALIAS})"
        print(f"### {name}{alias}", file=fout)

        print(cls.__doc__,  file=fout)

        if NF.TOP_LEVEL in cls.FLAGS:
            print("", file=fout)
            print("Allowed at top level only", file=fout)
        if len(cls.__annotations__):
            print("", file=fout)
            print("Fields:",  file=fout)

            for field, nfd in cls.FIELDS:
                kind = nfd.kind
                extra = ""
                optional_val = GetOptional(field, 0)
                if optional_val is not None:
                    if optional_val == "":
                        extra = ' (default "")'
                    elif isinstance(optional_val, ValNum):
                        extra = f' (default {optional_val.number})'
                    else:
                        extra = f' (default {optional_val.__class__.__name__})'
                print(f"* {field} [{kind.name}]{extra}: {nfd.doc}", file=fout)
            if cls.ATTRS:
                print("", file=fout)
                print("Flags:",  file=fout)
                for field, nfd in cls.ATTRS:
                    print(f"* {field}: {nfd.doc}", file=fout)
            print("", file=fout)

    print("## Enum Details",  file=fout)

    _RenderKind(Expr1.__name__,  UNARY_EXPR_KIND,
                UNARY_EXPR_SHORTCUT_INV, fout)
    _RenderKind(Expr2.__name__,  BINARY_EXPR_KIND,
                BINARY_EXPR_SHORTCUT_INV, fout)
    _RenderKind(ExprPointer.__name__,  POINTER_EXPR_KIND,
                POINTER_EXPR_SHORTCUT_INV, fout)
    _RenderKind(StmtCompoundAssignment.__name__,
                ASSIGNMENT_KIND, ASSIGMENT_SHORTCUT_INV, fout)
    _RenderKindSimple("Base Type",
                      BASE_TYPE_KIND, fout)
    _RenderKindSimple("ModParam",
                      MOD_PARAM_KIND, fout)
    _RenderKindSimple("MacroParam",
                      MACRO_PARAM_KIND, fout)


##########################################################################################
if __name__ == "__main__":
    logging.basicConfig(level=logging.WARN)
    logger.setLevel(logging.INFO)
    GenerateDocumentation(sys.stdout)
