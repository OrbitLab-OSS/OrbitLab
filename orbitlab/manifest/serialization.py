"""Serialization utilities for orbitlab manifest schemas."""

import base64
import binascii
from collections.abc import Callable
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Annotated, TypeVar

from pydantic import PlainSerializer, PlainValidator

from orbitlab.data_types import StorageContentType, StorageType

T = TypeVar("T", bound=StrEnum)


def str_list_to_enum(enum: T) -> Callable[[T], list[T]]:
    """Convert a list of strings to the specified Enums."""

    def wrapped(string_list: str | list) -> list[T]:
        if not isinstance(string_list, list):
            string_list = string_list.split(",")
        return [enum(i) for i in string_list]  # pyright: ignore[reportCallIssue]

    return wrapped


def peer_list_str(peer_list: str) -> list[IPv4Address]:
    """Convert a comma-separated string of IP addresses to a list of IPv4Address objects."""
    return [IPv4Address(addr) for addr in peer_list.split(sep=",")]


def serialize_enum_list(enums: list[StrEnum]) -> list[str]:
    """Serialize a list of Enums to list of strings."""
    return [enum.value for enum in enums]


def base64_to_str(data: str) -> str:
    """Decode a base64-encoded string to its original string value."""
    try:
        return base64.b64decode(data, validate=True).decode()
    except binascii.Error:
        return data


def to_base64(data: str) -> str:
    """Encode a string to base64."""
    return base64.b64encode(data.encode()).decode()


SerializeEnum = PlainSerializer(lambda v: v.value)
SerializeEnumList = PlainSerializer(serialize_enum_list)
SerializePath = PlainSerializer(lambda v: str(v))
SerializeIP = PlainSerializer(lambda addr: str(addr))
SerializeIPList = PlainSerializer(lambda addrs: [str(addr) for addr in addrs])
PveBool = Annotated[bool, PlainValidator(lambda v: v if isinstance(v, bool) else bool(v))]
PveContentList = Annotated[
    list[StorageContentType],
    PlainValidator(func=str_list_to_enum(enum=StorageContentType)),
    SerializeEnumList,
]
PeerList = Annotated[list[IPv4Address], PlainValidator(func=peer_list_str), SerializeIPList]
PveStorageType = Annotated[StorageType, SerializeEnum]
CertificateData = Annotated[str, PlainValidator(base64_to_str), PlainSerializer(to_base64)]
