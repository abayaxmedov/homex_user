from dataclasses import dataclass, field
from typing import Dict, List, Optional


class CommonResponse:
    """The common JSON-RPC ``result`` response structure."""

    def as_resp(self):
        response = {"result": {}}
        for key, value in self.__dict__.items():
            response["result"][key] = value
        return response


@dataclass
class Shipping(CommonResponse):
    """Shipping information for the fiscal ``detail``."""

    title: str
    price: int


@dataclass
class Item(CommonResponse):
    """A single fiscal line item (soliq/OFD receipt)."""

    title: str
    price: int
    count: int
    code: str
    vat_percent: int
    package_code: str
    discount: Optional[int] = None
    units: Optional[int] = None

    def as_resp(self):
        response = {
            "title": self.title,
            "price": self.price,
            "count": self.count,
            "code": self.code,
            "vat_percent": self.vat_percent,
            "package_code": self.package_code,
        }
        if self.discount:
            response["discount"] = self.discount
        if self.units:
            response["units"] = self.units
        return response


@dataclass
class CheckPerformTransaction(CommonResponse):
    """Response for ``CheckPerformTransaction`` (with optional fiscal detail)."""

    allow: bool
    additional: Optional[Dict[str, str]] = None
    receipt_type: Optional[int] = None
    shipping: Optional[Shipping] = None
    items: List[Item] = field(default_factory=list)

    def add_item(self, item: Item):
        self.items.append(item)

    def as_resp(self):
        detail_dict = {}
        receipt_dict = {"allow": self.allow}

        if self.additional:
            receipt_dict["additional"] = self.additional

        if isinstance(self.receipt_type, int):
            detail_dict["receipt_type"] = self.receipt_type

        if self.shipping:
            detail_dict["shipping"] = self.shipping.as_resp()

        if self.items:
            detail_dict["items"] = [item.as_resp() for item in self.items]

        if detail_dict:
            receipt_dict["detail"] = detail_dict

        return {"result": receipt_dict}


@dataclass
class CreateTransaction(CommonResponse):
    """Response for ``CreateTransaction``."""

    transaction: str
    state: int
    create_time: int


@dataclass
class PerformTransaction(CommonResponse):
    """Response for ``PerformTransaction``."""

    transaction: str
    state: int
    perform_time: int


@dataclass
class CancelTransaction(CommonResponse):
    """Response for ``CancelTransaction``."""

    transaction: str
    state: int
    cancel_time: int


@dataclass
class CheckTransaction(CommonResponse):
    """Response for ``CheckTransaction``."""

    transaction: str
    state: int
    create_time: int
    reason: Optional[int] = None
    perform_time: Optional[int] = None
    cancel_time: Optional[int] = None


@dataclass
class GetStatement(CommonResponse):
    """Response for ``GetStatement``."""

    transactions: List[dict]


@dataclass
class SetFiscalData(CommonResponse):
    """Response for ``SetFiscalData``."""

    success: bool
