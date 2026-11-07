"""Opt-in `rest` std module: an HTTP/1.1 server over stdin/stdout (spec/std-rest.md). Not registered by the default Registry."""
from .controller import HANDLER_INTERFACE, RestController, register_rest
from .http import Request, Response
from .router import METHODS, RouteTable, parse_route, percent_decode

__all__ = ["HANDLER_INTERFACE", "METHODS", "Request", "Response", "RestController", "RouteTable", "parse_route",
           "percent_decode", "register_rest"]
