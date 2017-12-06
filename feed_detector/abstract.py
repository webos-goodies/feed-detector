# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals


class BaseComponent(object):
    DEFAULT_CONFIG = {}

    def __init__(self, config={}):
        self.config = dict(self.DEFAULT_CONFIG, **config)


class AbstractFilter(BaseComponent):

    def run(self, doc):
        raise NotImplementedError('run method should be overridden')


class AbstractOptimizer(BaseComponent):

    def run(self, doc, result):
        raise NotImplementedError('run method should be overridden')
