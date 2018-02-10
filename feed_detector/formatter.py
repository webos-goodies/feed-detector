# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

from .abstract import BaseComponent
from .compat   import *


class PrintFormatter(BaseComponent):

    def run(self, doc, groups):
        for i, group in enumerate(groups):
            print("\nGroup %d : %f" % (i + 1, group.score))
            for entry in group.entries:
                print("  %s\n    %s" % (entry.title, entry.url))
        return None
