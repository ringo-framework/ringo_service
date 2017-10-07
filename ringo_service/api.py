#!/usr/bin/env python
# -*- coding: utf-8 -*-
from past.builtins import basestring
import inspect
import re
import logging
import venusian
import voorhees
import connexion
from connexion import NoContent

logger = logging.getLogger(__name__)

########################################################################
#                           Service registry                           #
########################################################################


class Registry(object):
    def __init__(self):
        self.models = []
        self.endpoints = {}

    def add_endpoint(self, path, method, function):
        if path not in self.endpoints:
            self.endpoints[path] = {}
        if method not in self.endpoints[path]:
            self.endpoints[path][method] = {}
            self.endpoints[path][method]["function"] = function

    def get_endpoint(self, path, method):
        service = None
        for _path in self.endpoints:
            if path == _path:
                endpoint = self.endpoints[path]
                for _method in endpoint:
                    if _method == method:
                        service = endpoint[method]["function"]
                        break
        return service

    def add_model(self, name, clazz):
        self.models.append((name, clazz))


registry = Registry()

########################################################################
#        Decorators to configure a service in the domain model         #
########################################################################


def config_service_endpoint(path, method="GET"):
    def real_decorator(function):
        def callback(scanner, name, ob):
            scanner.registry.add_endpoint(path, method, function)
        venusian.attach(function, callback)
        return function
    return real_decorator


def config_service_model():
    def real_decorator(clazz):
        def callback(scanner, name, ob):
            scanner.registry.add_model(name, clazz)
        venusian.attach(clazz, callback)
        return clazz
    return real_decorator

########################################################################
#                               Endpoint                               #
########################################################################


class NotFound(Exception):
    pass


def endpoint_proxy(*args, **kwargs):
    """Proxy for all configured service endpoints.

    The method will forward the request to the configured service in the
    registry.

    :args: Currently ignored
    :kwargs: Dictionary with function arguments preparsed as defined by the swagger config.
    :returns: Response sent to the client.
    """
    # Get the configured service from the registry.
    path = _get_request_path()
    method = _get_request_method()
    service = registry.get_endpoint(path, method)

    # Build params for the service
    params = _get_service_parameters(service, kwargs)

    try:
        # Call the service TODO: Do we need to handle more return codes
        # like 201? What is a good way to distiguish between 200 and 201
        # based on the return value? (ti) <2017-10-07 09:55>
        result = service(**params)

        # Result. Return it with status code 200
        if result:
            return voorhees.to_json(result), 200
        # No Result. Return it with status code 204
        else:
            return NoContent, 204
    except NotFound:
        # Item could not befound. Return 404
        return NoContent, 404
    except Exception:
        # General Error. Will result in a 500
        raise


def _get_request_path():
    """Will return the path of the current request."""
    request = connexion.request
    url_rule = request.url_rule
    # `url_rule` comes from request.url_rule and has a different
    # notation than the path definitions in the swagger config. To be
    # able to find the appropriate function to call in a request we need
    # to transform the url_rule into the form swagger uses.

    # Remove type information e.g. <int:foo> -> <foo>
    url_rule = re.sub("<.+:", "<", str(url_rule))
    return url_rule.replace("<", "{").replace(">", "}")


def _get_request_method():
    """Will return the method (GET, POST...) of the current request."""
    request = connexion.request
    return request.method


def _get_service_parameters(service, parameters):
    """Will return parameters suitable to call the given service.

    Example::

        {'values': '{"password": "Password", "id": 1, "name": "User1"}'}

    :service: Service callable.
    :parameters: Dictionary with function arguments preparsed as defined
                 by the swagger config.
    :returns: Dictionary of service parameters.
    """

    def looks_like_json(value):
        if isinstance(value, basestring) and (value.startswith("{") or value.startswith("[")):
            return True
        return False

    # First check which parameters are wanted by the given service.
    service_wants = inspect.getargspec(service)[0]
    service_send = {}

    # Iterate over all function arguments and check if any of those
    # arguments matches on of the argumentsthe service wants.
    for param in parameters:
        value = parameters[param]
        if looks_like_json(value):
            value = voorhees.from_json(value)
        if param in service_wants:
            service_send[param] = value
        elif isinstance(value, dict):
            for subparam in value:
                if subparam in service_wants:
                    service_send[subparam] = value[subparam]
    return service_send
