# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

from .abstract  import BaseComponent
from .detector  import Detector


__all__ = ('BaseCoordinator',)


class BaseCoordinator(BaseComponent):

    def __init__(self, config={}):
        super(BaseCoordinator, self).__init__(config)
        self._filters   = [x(config) for x in config.get('filters') or []]
        self._detector  = Detector(config)
        self._formatter = config.get('formatter')(config)

    def run(self, doc):
        tmp_doc = doc.copy()
        for f in self._filters:
            self.apply_filter(tmp_doc, f)
        groups = self.detect(tmp_doc)
        return self.format(doc, groups)

    def apply_filter(self, doc, f):
        return f.run(doc)

    def detect(self, doc):
        return self._detector.run(doc)

    def format(self, doc, groups):
        return self._formatter.run(doc, groups)


