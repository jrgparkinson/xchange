

class XChangeException(Exception):
    desc = "Unknown error"
    
class InsufficientShares(XChangeException):
    desc = "Insufficient shares"
    
class NoActionPermission(XChangeException):
    desc = "Not allowed to perform action"
    
class InsufficientFunds(XChangeException):
    desc = "Insufficient funds"
    
class NoBuyerOrSeller(XChangeException):
    desc = "No buyer or seller found"

class TradeNotPending(XChangeException):
    desc = "Trade is no longer pending"
    