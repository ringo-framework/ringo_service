#!/usr/bin/env python
# -*- coding: utf-8 -*-
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


def _get_request_path():
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
    request = connexion.request
    return request.method


def _get_service_parameters(service, parameters):
    service_wants = inspect.getargspec(service)[0]
    service_send = {}
    for param in parameters:
        if param in service_wants:
            value = parameters[param]
            if not isinstance(value, int):
                service_send[param] = voorhees.from_json(value)
            else:
                service_send[param] = value
        else:
            try:
                subparameters = voorhees.from_json(parameters[param])
            except:
                print("ERROR:", parameters[param], type(parameters[param]))
                continue
            for subparam in subparameters:
                if subparam in inspect.getargspec(service)[0]:
                    value = subparameters[subparam]
                    service_send[subparam] = value
    return service_send


class Registry(object):
    def __init__(self):
        self.apis = []
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


def config_service_endpoint(path, method="GET", endpoint=None):
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
#                            CRUD Endpoints                            #
########################################################################


class NotFound(Exception):
    pass


def generic(*args, **kwargs):
    service = registry.get_endpoint(_get_request_path(), _get_request_method())
    try:
        result = service(**_get_service_parameters(service, kwargs))
        if result:
            return voorhees.to_json(result), 200
        else:
            return NoContent, 204
    except NotFound:
        return NoContent, 404
    except Exception:
        raise
