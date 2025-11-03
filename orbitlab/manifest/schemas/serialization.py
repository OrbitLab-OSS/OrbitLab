"""Serialization utilities for orbitlab manifest schemas."""

from enum import StrEnum
from typing import Annotated, TypeVar

from pydantic import PlainSerializer, PlainValidator

from orbitlab.data_types import StorageContentType, StorageType

T = TypeVar("T", bound=StrEnum)

def __str_list_to_list__(string_list: str | list, enum: T | None = None) -> list[T | str]:
    if isinstance(string_list, list):
        return string_list
    
    if enum:
        if "," in string_list:
            return [enum(i) for i in string_list.split(",")]
        return enum(string_list)
    if "," in string_list:
        return string_list.split(",")
    return [string_list]

SerializeEnum = PlainSerializer(lambda v: v.value)
SerializeEnumList = PlainSerializer(lambda v: [i if isinstance(i, str) else i.value for i in v])
SerializeIP = PlainSerializer(lambda addr: str(addr))
PveBool = Annotated[bool, PlainValidator(lambda v: v if isinstance(v, bool) else bool(v))]
PveContentList = Annotated[list[StorageContentType], PlainValidator(__str_list_to_list__), SerializeEnumList]
PveStorageType = Annotated[StorageType, SerializeEnum]
