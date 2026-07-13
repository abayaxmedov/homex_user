from dataclasses import dataclass
from typing import Dict, Optional


class Common:
    """The common response structure for the Cards SDK."""

    @classmethod
    def from_dict(cls, data: Dict):
        """Prepare fields for nested dataclasses."""
        field_values = {}
        for field in cls.__dataclass_fields__:
            field_type = cls.__dataclass_fields__[field].type
            field_data = data.get(field)

            if isinstance(field_data, dict) and issubclass(field_type, Common):
                field_values[field] = field_type.from_dict(field_data)
            else:
                field_values[field] = field_data

        return cls(**field_values)


@dataclass
class Card(Common):
    """A credit card."""

    number: str
    expire: str
    token: str
    recurrent: bool
    verify: bool
    type: str
    number_hash: Optional[str] = None


@dataclass
class Result(Common):
    """The result object containing the created card."""

    card: Card


@dataclass
class CardsCreateResponse(Common):
    """The ``cards.create`` response."""

    jsonrpc: str
    result: Result


@dataclass
class VerifyResult(Common):
    """Result object for the verification response."""

    sent: bool
    phone: str
    wait: int


@dataclass
class GetVerifyResponse(Common):
    """The ``cards.get_verify_code`` response structure."""

    jsonrpc: str
    result: VerifyResult


@dataclass
class VerifyResponse(Common):
    """The ``cards.verify`` response structure."""

    jsonrpc: str
    result: Result


@dataclass
class RemoveCardResult(Common):
    """Result object for the removal response."""

    success: bool


@dataclass
class RemoveResponse(Common):
    """The ``cards.remove`` response structure."""

    jsonrpc: str
    result: RemoveCardResult


@dataclass
class CheckResponse(Common):
    """The ``cards.check`` response structure."""

    jsonrpc: str
    result: Result
