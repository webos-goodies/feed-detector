# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

from .abstract  import BaseComponent
from .detector  import Detector
from .filter    import BodyRemovalFilter
from .formatter import PrintFormatter


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


def main():
    import sys
    from optparse import OptionParser
    from .document import Document
    parser = OptionParser(usage="%prog: [options] [file]")
    parser.add_option('-u', '--url', default=None, help="use URL instead of a local file")
    options, args = parser.parse_args()

    if not (len(args) == 1 or options.url):
        parser.print_help()
        sys.exit(1)

    file = None
    if options.url:
        headers = {'User-Agent': 'Mozilla/5.0'}
        if sys.version_info[0] == 3:
            import urllib.request, urllib.parse, urllib.error
            request = urllib.request.Request(options.url, None, headers)
            file = urllib.request.urlopen(request)
        else:
            import urllib2
            request = urllib2.Request(options.url, None, headers)
            file = urllib2.urlopen(request)
    else:
        file = open(args[0], 'rt')

    try:
        import time
        doc = Document(file.read(), url=options.url)
        t   = time.time()
        BaseCoordinator({ 'filters':[BodyRemovalFilter], 'formatter':PrintFormatter }).run(doc)
        print("\n%f secs." % (time.time() - t))
    finally:
        file.close()


if __name__ == '__main__':
    main()
