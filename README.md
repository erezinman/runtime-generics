# Runtime Generics in Python (WIP)

1. [Preface](#preface)
2. [Part 1: Static Generics](#part-1-static-generics)
3. [Part 2: Dynamic Generics](#part-2-dynamic-generics)
4. [Part 3: Strict Generics (default values for type-vars)](#part-3-strict-generics-default-values-for-type-vars)
5. [Part 4: Changes to syntax](#part-4-changes-to-syntax)

## Preface

Many languages support generics (e.g. Java, C#, C++, Rust, Go, etc.).
Following [PEP 560](https://www.python.org/dev/peps/pep-0560/) and [PEP 563](https://www.python.org/dev/peps/pep-0563/),
generics are now supported in Python. However, these duck-typed generics and are mostly used for type-checking and
documentation. They are not available at runtime (or at least hardly usable).

This aims package provides a way to use generics at runtime. It is an ongoing process, and is currently in an initial
state of the implementation (albeit the design is mostly complete). This package is inspired by the use of generics in
Java and C#, by the way generics are currently implemented in Python, and by the way `pydantic` uses generics
(see [here](https://docs.pydantic.dev/latest/usage/types/#generic-classes-as-types)). The changes/additions in this
package are divided into 4 parts:

1. [Static Generics](#part-1-static-generics): The ability to easily query types of generic classes and their type-vars.
   This is mostly when implementing generic ABCs. (e.g. `class TextResponse(Respone[str]): ...`).
2. [Part 2: Dynamic Generics (AKA Runtime Generics)](#part-2-dynamic-generics): The ability to create generic classes at
   runtime. These classes can be used as normal classes, but carry their type-vars with them (e.g.
   `type(Response[str]) == Response[str]`). This is mostly useful when creating generic classes at runtime without
   deriving from them. The main idea here is that we treat non-concrete types (i.e. `TypeVar`s) as ABCs, and concrete
   types as normal classes.
3. [Strict Generics](#part-3-strict-generics-default-values-for-type-vars): The ability to specify default values for
   type-vars. This is mostly for standardization of the concept of unspecified type arguments
   (e.g. `list == list[Any]`).
4. [Changes to syntax](#part-4-changes-to-syntax): The ability to specify type-vars and generic classes in a more
   concise way (e.g. `class A(Generic[T, S], List[S]): ...` -> `class A[T, S](List[S]): ...`).

These parts can be viewed as separate, and can be implemented separately. However, they are all related to each other
and work together. Most of these parts can be packaged and can be used to extend Python. However, the last part
is a bit more complicated and requires a custom Python interpreter (will not be a part of that repository).

It should be noted that since "MyPy" is the de-facto standard for type-checking and generic-resolution in Python, at
least some of the code might be taken from there, or at least inspired by it and written with it in mind.

Few important caveats before we start:

1. This package only supports generics for classes, not for functions. However, they should be addressed in the scope of
   this package in the future (at least in part 1).
2. At least so far, "generics" here are only meant to be used with simple `TypeVar`s. Variadic generics and
   parameter-specification are not considered, yet they should be relatively straightforward to address. What is
   considered is the ability to specify a union of types (and other type-vars) as the "type-argument".

## Part 1: Static Generics

Actually, static generics are already supported in Python during runtime (at least partially). However, the main
hindrance to using them is that they are not easily accessible. For example, if we have the following code:

```python 
from typing import Mapping


class MyDict(Mapping[str, int]): ...
```

Then it is possible to know what type-vars `MyDict` has, but it is not easy. To do that, we need to access  
`MyDict`'s `__orig_bases__`, find `Mapping[str, int]`, and match its `__args__` with  `Mapping.__parameters__`. This is
not very convenient, and requires specific knowledge of how generics are implemented in Python. Another use-case exists
in `pydantic`, where one might wish to parse a configuration in a generic way. For example:

```python
from typing import Generic, TypeVar, Type, Dict, Any, Union
from pydantic import BaseModel

T = TypeVar('T')


class MultiConfigs(BaseModel, Generic[T]):
    configs: Dict[str, T]


class ConfigPart(BaseModel):
    ...


class MainPart(ConfigPart):
    one_or_many: Union[ConfigPart, MultiConfigs[ConfigPart]]
```

[This is actually a real example, but in the real case, one must use `pydantic.generics.GenericModel` (which is
implemented differently from regular `Generic` classes) instead of `pydantic.BaseModel`.]

We suggest in this part to add `inspect`-like functionality to `typing`/`inspect` that will allow us to easily query the
type-vars of a generic
class, and other similar information. This package currently implements the following functions (in `typing_inspect`):

1. `get_inheritance_path_to_parent(cls: type, parent: type, with_generics: bool = True)`
2. `get_typevar_matching(superclass: type, subclass: type)`

See the docstrings for more information and examples.

More functions (such as `resolve_generic_signature(cls: type, method: FunctionType) -> inspect.Signature`) should be 
added in the future, but these are the most important ones to the requirement I mentioned above.

## Part 2: Dynamic Generics (AKA Runtime Generics)

This part is the main part of this package. The idea is to allow the creation of generic classes at runtime that retain
their generic information. Consider the case:

```python
from typing import Generic, TypeVar

TData = TypeVar('TData')


class Request(Generic[TData]):
    def __init__(self, data: TData): ...


class Server:
    def handle_request(self, request: Request) -> None:
        ...

    def handle_string_request(self, request: Request[str]) -> None:
        ...

    def handle_int_request(self, request: Request[int]) -> None:
        ...


server = Server()
server.handle_request(Request[str]("I came here for an argument!"))
server.handle_request(Request[int](13))


class HTMLRequest(Request[str]): ...  # A special case of Request[str]


server.handle_request(HTMLRequest('<html>...</html>'))
```

Then in order for the `Server` to be able to handle requests according to their data-type (without accessing their
content), we need to know the type-vars of `Request`. However, this is not possible in Python nowadays without
requiring to pass the type-vars explicitly into the `Request.__init__` (for instance,

```python
class Request(Generic[TData]):
    def __init__(self, data: TData, tdata: Type[TData]): ...
```

).

We suggest to add a generic base class called, for example, `RuntimeGeneric` that will allow us to create generic
classes at runtime. For example:

```python
from runtime_generics import RuntimeGeneric, TypeVar

TData = TypeVar('TData')


class Request(RuntimeGeneric[TData]):
    def __init__(self, data: TData): ...


assert type(Request[str]) != type(Request[int])
```

To do that, one must also address the following issues:

1. **Instantiation of non-"exact" types** (e.g. `Class[T]()`) should raise an exception exactly like an ABC with an
   abstract method does. This is because the type-vars are not known, and therefore the class cannot be instantiated.
2. **`isintance(obj, Class[int, T])` should return `True` if `obj` is an instance of `Class` with `int` as the first
   type-var** regardless of the second type-var. It should also work when deriving from `Class`
   (e.g. `class Derived(Class[int, T]): ...`). Note that currently `isinstance` does not work with generics at all.
3. **`Class[T]` should be the same as `Class[U]`**. This is because the type-vars are not known, and therefore the
   classes are the same even so they are differently named.
4. **Order of parameter specification should not matter** (
   e.g. `Class[int, T][str] == Class[int, str] == Class[str, S][int]`).

These issues lead to the following implementation details:

1. When the class variables are fully specified (e.g. `Class[int, str]`), then the class is created as a regular
   class. That is, `type(Class[int, str]) == type` (or some other metaclass).
2. Otherwise, we should declare a different kind of `GenericAlias` then the one that exists today. That `GenericAlias`
   should itself be a type, so it can be used with `isinatnce` and `issubclass`.
3. The new `GenericAlias`'s metaclass should implement the `__instancecheck__` and `__subclasscheck__` methods to
   support the new behavior.
4. The `__class_getitem__` should work similar to today, with the exception that when specifying all the type-vars, the
   class should be created as a regular class (as mentioned in 1), even if coming from a `GenericAlias`.
5. Even though they are now types, `GenericAlias` should be collected when they are not referenced anymore (just like 
   today's `GenericAlias`). This is because they are not regular classes and can not be instantiated anyway.

The issue of unions is not addressed here yet (e.g. `isinstance(Class[int](), Class[Union[int, str]])`?) but it should
be addressed in the future (I tend towards answering "no" to that question).

## Part 3: Strict Generics (default values for type-vars)

This part is mostly for standardization of the concept of unspecified type arguments. Currently, one is allowed to
write `list` instead of `list[Any]`. This is not very consistent, and can lead to confusion. Because generics are not
enforced, the idea of checking the type-vars of a generic class is not always possible. For example, the following code
is valid:

```python
from typing import Generic, TypeVar
from runtime_generics import typing_inspect

T = TypeVar('T')


class Parent(Generic[T]): ...


class Child(Parent): ...


typing_inspect.get_typevar_matching(Parent, Child)  # Raises an exception?
```

To address this, we suggest to add a new argument to the declaration of `TypeVar` that will specify the default value
for the type-var. For example:

```python
from typing import Generic, TypeVar

T = TypeVar('T', default_type=int)


class Parent(Generic[T]): ...


assert Parent == Parent[int]
```

This will allow us to know the type-vars of a generic class even if they are not specified. If the `default_type`
parameter is unspecified, then the default value will be the `bound` or the union of the `constraints` (if they exist),
or `Any` otherwise. In the above example:

```python
from typing import Generic, TypeVar, Any
from runtime_generics import typing_inspect

T = TypeVar('T')


class Parent(Generic[T]): ...


class Child(Parent): ...


assert typing_inspect.get_typevar_matching(Parent, Child) == {T: Any}
```

### Relation to Part 2  

If implemented along with the previous part, then the `RuntimeGeneric` class becomes almost the same as the `Generic`
class. That is because now `Parent()` is the same as `Parent[Any]()`. To obtain the same behavior as the last part 
(where not specifying the type-vars will raise an exception on exception), one can use 
`T = TypeVar("T", default_type=None)`, in which case there will not be a default value for the type-var, and therefore
`Parent()` will raise an exception.


## Part 4: Changes to syntax

This part is mostly for convenience. Currently, the syntax for declaring generic classes is a bit verbose - there's the
"explicit" way (always specify deriving from `Generic`), and the "implicit" way (without it). For example:

```python

from typing import Generic, TypeVar, List

T = TypeVar('T')


class Explicit(Generic[T], List[T]): ...


class Implicit(List[T]): ...
```

Both cases are equivalent, but both have their shortcomings. The first one is rigorous, but verbose and contains
redundant information (it is obvious that the class is generic, so why do we need to specify it?). The second one is
less verbose and more intuitive with one type-var, but becomes increasingly less intuitive the more type-vars we have.
For example, consider the following code:

 ```python
from typing import Protocol, TypeVar

T1 = TypeVar('T1')
T2 = TypeVar('T2')
TResult = TypeVar('TResult')


class Reducer(Protocol[T1, T2, TResult]):
    def __call__(self, a: T1, b: T2) -> TResult: ...


class SameTypeReducer(Reducer[T1, T1, T1]): ...  # Implicitly has one type-var (T1)


class ChainReducer(Reducer[T1, T2, T1]): ...  # Implicitly has two type-vars (T1, T2)? Not very intuitive


```

Another example could be:

```python
from typing import Generic, TypeVar, Mapping, ContextManager, Collection

T = TypeVar('T')
S = TypeVar('S')
U = TypeVar('U')


class ExplicitParent(Generic[T, S], Mapping[T, S], Collection[T]): ...
class ImplicitParent(Mapping[T, S], Collection[T]): ...

class ExplicitPartialChild(Generic[T, S, U], ExplicitParent[T, U], ContextManager[S]): ...
class ImplicitPartialChild(ExplicitParent[T, U], ContextManager[S]): ...

class ExplicitFullChild(Generic[T], ExplicitParent[T, T], ContextManager[T]): ...
class ImplicitFullChild(ExplicitParent[T, T], ContextManager[T]): ...
``` 

We see that when using the explicit syntax, we always know for sure what type-vars the class has, and what's their
order, while when using the implicit syntax, we must "look" at the base-classes to know what type-vars the class has.
Also, the order of the type-vars in the implicit syntax is determined by the order of derivation from the base-classes,
which by itself has other meanings (e.g. the MRO, order of method resolution, etc.), and so might lead to "absurd" cases
where the order of the type-parameters is counter-intuitive (e.g. `Class[KT, TReturn, VT]`).

To that end, we suggest to add a new syntax for declaring generic classes, which will be a simplified version of the
explicit syntax. For example:

```python
class Parent[T, S]: ...
```

is equivalent to:

```python
from typing import Generic, TypeVar

T = TypeVar('T')
S = TypeVar('S')


class Parent(Generic[T, S]): ...


del T, S
```

Also, when the type-vars are not invariant, the syntax can change to:

```python
class Parent[+T, -S, ~U]: ...  # Covariant T, Contravariant S, Invariant U (modifier optional).
```

This is the same as:

```python

from typing import Generic, TypeVar

T = TypeVar('T', covariant=True)
S = TypeVar('S', contravariant=True)
U = TypeVar('U')


class Parent(Generic[T, S, U]): ...


del T, S, U
```

Note that `+`, `-` and `~` are currently the representation of the variance modifiers for type-vars, so this syntax
is in line with it.

If we wish to declare bound of a type-var, no problem! We can do it like we do it today:

```python
from typing import TypeVar, Mapping

TNum = TypeVar('T', bound=int)


class NumericKeyMap[TNum, S](Mapping[TNum, S]): ...
```

Note that using this syntax, we do not have redeclare the type-vars at every module that uses generic classes (I repeat
the line `T = TypeVar('T')` in every package I write many-many times).
