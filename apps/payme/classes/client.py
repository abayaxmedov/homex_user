from typing import Union

from apps.payme.classes.cards import Cards
from apps.payme.classes.initializer import Initializer
from apps.payme.classes.receipts import Receipts
from apps.payme.const import Networks


class Payme:
    """Facade over the Payme SDK: checkout links + cards + receipts."""

    def __init__(
        self,
        payme_id: str,
        fallback_id: Union[str, None] = None,
        payme_key: Union[str, None] = None,
        is_test_mode: bool = False,
        checkout_url: Union[str, None] = None,
    ):
        url = Networks.PROD_NET.value
        if is_test_mode is True:
            url = Networks.TEST_NET.value

        self.cards = Cards(url=url, payme_id=payme_id)
        self.initializer = Initializer(
            payme_id=payme_id,
            fallback_id=fallback_id,
            is_test_mode=is_test_mode,
            checkout_url=checkout_url,
        )
        self.receipts = Receipts(url=url, payme_id=payme_id, payme_key=payme_key)
