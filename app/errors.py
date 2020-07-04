from rest_framework.exceptions import APIException


class AssetNotOwned(APIException):
    status_code = 450
    default_detail = 'An entity cannot sell an asset they do not own.'
    default_code = 'asset_not_owned'

class XChangeException(Exception):
    title = "Unknown error"
    desc = ""

    def __init__(self, desc=None):
        self.desc = desc

    def __str__(self):
        return "{}: {}".format(self.title, self.desc)


class InsufficientShares(XChangeException):
    title = "Insufficient shares"
    desc = ""

    def __init__(self, desc=None):
        super().__init__(desc)


class NoActionPermission(XChangeException):
    title = "Not allowed to perform action"
    desc = ""

    def __init__(self, desc=None):
        super().__init__(desc)


class InsufficientFunds(XChangeException):
    title = "Insufficient funds"
    desc = ""

    def __init__(self, desc=None):
        super().__init__(desc)


class NoBuyerOrSeller(XChangeException):
    title = "No buyer or seller found"
    desc = ""

    def __init__(self, desc=None):
        super().__init__(desc)


class TradeNotPending(XChangeException):
    title = "Trade is no longer pending"
    desc = ""

    def __init__(self, desc=None):
        super().__init__(desc)


class InvalidAsset(XChangeException):
    title = "Invalid asset"
    desc = ""

    def __init__(self, desc=None):
        super().__init__(desc)


class AthleteDoesNotExist(XChangeException):
    title = "Athlete does not exist"
    desc = ""

    def __init__(self, desc=None):
        super().__init__(desc)

    
class OfferExpired(XChangeException):
    title = "Offer expired"
    desc = ""

    def __init__(self, desc=None):
        super().__init__(desc)

