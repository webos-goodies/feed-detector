# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

from .abstract import BaseComponent
from .compat   import *

import re


__all__ = ('PrintFormatter',)

SPACE_SUB = re.compile(r'[ \t]+').sub
EOL_SUB   = re.compile(r'[\r\n]+').sub


class PrintFormatter(BaseComponent):

    def run(self, doc, groups):
        for i, group in enumerate(groups):
            print("\nGroup %d (%d items) %f, %f\n%s" %
                  (i + 1, len(group.entries), group.score, group.cbg_score,
                   ' > '.join(group.paths[0].path)))
            for entry in group.entries:
                title = SPACE_SUB(' ', entry.title)
                title = EOL_SUB("\n", title)
                print("  %s : %.2f\n    %s" % (title, entry.score, entry.url))
        return None
