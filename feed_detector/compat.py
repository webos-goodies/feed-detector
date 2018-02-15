from __future__ import absolute_import, division, print_function, unicode_literals

import sys


__all__ = (('STR_TYPE', 'to_unicode', 'iterkeys', 'itervalues', 'iteritems', 'viewkeys') +
           (('xrange',) if sys.version_info[0] >= 3 else ()))


if sys.version_info[0] >= 3:
    xrange = range
    STR_TYPE = str
else:
    STR_TYPE = unicode


def to_unicode(s):
    if isinstance(s, bytes):
        return unicode(s)
    else:
        return s


if sys.version_info[0] == 3:
    def iterkeys(d):
        return d.keys()
    def itervalues(d):
        return d.values()
    def iteritems(d):
        return d.items()
    def viewkeys(d):
        return d.keys()
else:
    def iterkeys(d):
        return d.iterkeys()
    def itervalues(d):
        return d.itervalues()
    def iteritems(d):
        return d.iteritems()
    def viewkeys(d):
        return d.viewkeys()
