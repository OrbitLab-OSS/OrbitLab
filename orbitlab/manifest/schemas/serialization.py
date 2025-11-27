"""Serialization utilities for orbitlab manifest schemas."""

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, TypeVar

from pydantic import PlainSerializer, PlainValidator

from orbitlab.data_types import StorageContentType, StorageType

T = TypeVar("T", bound=StrEnum)


def __str_list_to_enum__(enum: T) -> Callable[[T], list[T]]:
    def wrapped(string_list: str | list) -> list[T]:
        if not isinstance(string_list, list):
            string_list = string_list.split(",")
        return [enum(i) for i in string_list]

    return wrapped


def __serialize_enum_list__(enums: list[StrEnum]):
    return [enum.value for enum in enums]


SerializeEnum = PlainSerializer(lambda v: v.value)
SerializeEnumList = PlainSerializer(__serialize_enum_list__)
SerializePath = PlainSerializer(lambda v: str(v))
SerializeIP = PlainSerializer(lambda addr: str(addr))
PveBool = Annotated[bool, PlainValidator(lambda v: v if isinstance(v, bool) else bool(v))]
PveContentList = Annotated[
    list[StorageContentType],
    PlainValidator(__str_list_to_enum__(StorageContentType)),
    SerializeEnumList,
]
PveStorageType = Annotated[StorageType, SerializeEnum]
