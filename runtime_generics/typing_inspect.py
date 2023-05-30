from types import GenericAlias
from typing import TypeVar, Generic, List, Union, Iterable, Dict
from typing_extensions import TypeAlias

T = TypeVar('T')
S = TypeVar('S')
RT = TypeVar('RT')
_GenericAlias = type(Generic[T])  # This is due to a bug(?) where `List`'s `GenericAlias` is not the same as `Generic`'s


def get_inheritance_path_to_parent(cls: type, parent: type, with_generics: bool = True) -> \
        List[Union[type, 'GenericAlias']]:
    """
    Returns a tuple of classes representing the inheritance path from the class to the parent.
    If the class is not a subclass of the parent, raises a `ValueError`.

    Example
    -------
        >>> class A: pass
        >>> class B(A): pass
        >>> class C(B): pass
        >>> get_inheritance_path_to_parent(C, A)
        [<class 'utils.C'>, <class 'utils.B'>, <class 'utils.A'>]

        >>> class A1(Generic[T, S]): pass
        >>> class A2(Generic[T]): pass
        >>> class B1(A1[int, S]): pass
        >>> class B2: pass
        >>> class B12(A1[float, str], A2[int], B2): pass
        >>> class C(B12, B1[str], B2): pass
        >>> get_inheritance_path_to_parent(C, A1, False)
        [<class 'utils.C'>, <class 'utils.B1'>, <class 'utils.A1'>]
        >>> get_inheritance_path_to_parent(C, A1, True)
        [<class 'utils.C'>, utils.B1[str], <class 'utils.B1'>, utils.A1[int, ~S], <class 'utils.A1'>]
    """

    if cls is parent:
        return [cls]

    if not issubclass(cls, parent):
        raise ValueError(f'{cls} is not a subclass of {parent}')

    if with_generics:
        def bases_func(curr: type) -> Iterable[type]:
            if isinstance(curr, (GenericAlias, _GenericAlias)):
                return curr.__origin__,
            origin_bases = getattr(curr, '__orig_bases__', None)
            if origin_bases is not None:
                # This is a bypass for a what might be a bug where the origin bases are not the same as the bases
                if tuple(getattr(b, '__origin__', b) for b in origin_bases) == curr.__bases__:
                    return origin_bases

            return curr.__bases__
    else:
        def bases_func(cls: type) -> Iterable[type]:
            return cls.__bases__

    dead_ends = set()
    possible_paths = [(cls, [cls])]
    while possible_paths:
        current, path = possible_paths.pop()
        for base in bases_func(current):
            if base is parent:
                path.append(base)
                return path
            if base in dead_ends:
                continue
            dead_ends.add(base)
            possible_paths.append((base, path + [base]))

    raise ValueError(f'{cls} is not a subclass of {parent}. This should not happen.')


def get_typevar_matching(superclass: type, subclass: type) -> Dict[TypeVar, Union[type, TypeVar, 'TypeAlias']]:
    """
    Returns a dictionary mapping the type variables of the superclass to the types of the subclass.

    Example
    -------
        >>> class A1(Generic[T, S]): pass
        >>> class A2(Generic[T]): pass
        >>> class B1(A1[Iterable[T], Union[T, str]]): pass
        >>> class B2: pass
        >>> class B12(A1[float, str], A2[int], B2): pass
        >>> class C(B12, B1[Union[None, int]], B2): pass

        >>> get_typevar_matching(A1, B12)
        {~T: <class 'float'>, ~S: <class 'str'>}

        >>> get_typevar_matching(A1, C)
        {~T: typing.Iterable[typing.Optional[int]], ~S: typing.Union[NoneType, int, str]}

        >>> get_typevar_matching(B1, C)
        {~T: typing.Optional[int]}

        >>> get_typevar_matching(A1, B1)
        {~T: typing.Iterable[~T], ~S: typing.Union[~T, str]}
    """
    if not isinstance(superclass, type):
        raise TypeError(f'{superclass} is not a type')

    result = {p: p for p in getattr(superclass, '__parameters__', ())}
    if len(result) == 0:
        return result
    old_params = superclass.__parameters__

    path_to_parent = get_inheritance_path_to_parent(subclass, superclass, with_generics=True)
    for cls in reversed(path_to_parent[:-1]):
        if not hasattr(cls, '__args__'):
            continue
        d = dict(zip(old_params, cls.__args__))
        for p in result:
            if isinstance(result[p], TypeVar):
                result[p] = d[result[p]]
            elif len(getattr(result[p], '__parameters__', ())) > 0:
                result[p] = result[p][cls.__args__]
        old_params = cls.__parameters__
        if len(old_params) == 0:
            return result

    return result
