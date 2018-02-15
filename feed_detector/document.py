# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

try:
    import cchardet as chardet
except:
    import chardet

import copy
import lxml.html
import lxml.html.clean
import re
import sys

from .abstract import BaseComponent
from .compat   import *


__all__ = ('Encoding', 'Document')


# Encoding detection code from python-readability.
class Encoding(object):
    RE_CHARSET = re.compile(br'''<meta[^>]+?charset=["']?([-_0-9A-Z]+)''', flags=re.I)
    RE_PRAGMA = re.compile(br'''<meta[^>]+?content=["']?[^"'>]*?;\s*charset=([-_0-9A-Z]+)''',
                           flags=re.I)
    RE_XML = re.compile(br'''^<\?xml[^>]+?encoding=["']?([-_0-9A-Za-z]+)''')
    RE_ALL_TAGS = re.compile(br'(?:\s*</?[^>]*>)+\s*')

    CHARSETS = {
        'big5': 'big5hkscs',
        'gb2312': 'gb18030',
        'ascii': 'utf-8',
        'maccyrillic': 'cp1251',
        'win1251': 'cp1251',
        'win-1251': 'cp1251',
        'windows-1251': 'cp1251',
    }

    def fix_charset(self, encoding):
        """Overrides encoding when charset declaration
           or charset determination is a subset of a larger
           charset.  Created because of issues with Chinese websites"""
        encoding = encoding.lower()
        return self.CHARSETS.get(encoding, encoding)

    def get_encoding(self, page):
        # Regex for XML and HTML Meta charset declaration
        declared_encodings = (self.RE_CHARSET.findall(page) +
                              self.RE_PRAGMA.findall(page) +
                              self.RE_XML.findall(page))

        # Try any declared encodings
        for declared_encoding in declared_encodings:
            try:
                if sys.version_info[0] == 3:
                    # declared_encoding will actually be bytes but .decode() only
                    # accepts `str` type. Decode blindly with ascii because no one should
                    # ever use non-ascii characters in the name of an encoding.
                    declared_encoding = declared_encoding.decode('ascii', 'replace')

                encoding = self.fix_charset(declared_encoding)

                # Now let's decode the page
                page.decode(encoding)
                # It worked!
                return encoding
            except UnicodeDecodeError:
                pass

        # Fallback to chardet if declared encodings fail
        # Remove all HTML tags, and leave only text for chardet
        text = re.sub(self.RE_ALL_TAGS, b' ', page).strip()
        enc = 'utf-8'
        if len(text) < 10:
            return enc # can't guess
        res = chardet.detect(text)
        enc = res['encoding'] or 'utf-8'
        #print '->', enc, "%.2f" % res['confidence']
        enc = self.fix_charset(enc)
        return enc


class Document(BaseComponent):
    PARSER  = lxml.html.HTMLParser(encoding='utf-8')
    CLEANER = lxml.html.clean.Cleaner(
        scripts=True, javascript=True, comments=True,
        style=True, links=True, meta=False, add_nofollow=False,
        page_structure=False, processing_instructions=True, embedded=False,
        frames=False, forms=False, annoying_tags=False, remove_tags=None,
        remove_unknown_tags=False, safe_attrs_only=False)
    XPATH_PREFIX_RE = re.compile(STR_TYPE(r'/html/'))

    def __init__(self, source, url=None, tree=None, config={}):
        super(Document, self).__init__(config)
        if isinstance(source, STR_TYPE):
            self._source = source.encode('utf-8', 'replace')
        else:
            encoding = Encoding().get_encoding(source) or 'utf-8'
            self._source = source.decode(encoding, 'replace').encode('utf-8', 'replace')
        self._url = url
        self._tree = self._load_html() if tree is None else tree
        self._doc = self._tree.getroot()

    @property
    def root(self):
        return self._doc

    @property
    def tree(self):
        return self._tree

    def copy(self):
        return self.__copy__()

    def create_fragment(self, s):
        return lxml.html.fragment_fromstring(s)

    def add_xpath(self):
        tree = self._tree
        prefix = STR_TYPE('/')
        prefix_re = self.XPATH_PREFIX_RE
        for el in self._doc.iter():
            if isinstance(el, lxml.html.HtmlElement):
                el.set('x', prefix_re.sub(prefix, tree.getpath(el)))

    def html(self, element=None):
        if element is None:
            element = self._doc
        return lxml.html.tostring(element, pretty_print=True, encoding='unicode')

    def __copy__(self):
        return copy.deepcopy(self)

    def __deepcopy__(self, memo):
        tree = copy.deepcopy(self._tree, memo)
        return Document(self._source, url=self._url, tree=tree, config=self.config)

    def _load_html(self):
        doc = lxml.html.document_fromstring(self._source, parser=self.PARSER)
        doc = self.CLEANER.clean_html(doc)
        if self._url:
            try:
                # such support is added in lxml 3.3.0
                doc.make_links_absolute(self._url, resolve_base_href=True,
                                        handle_failures='discard')
            except TypeError:
                # make_links_absolute() got an unexpected keyword argument 'handle_failures'
                # then we have lxml < 3.3.0
                # please upgrade to lxml >= 3.3.0 if you're failing here!
                doc.make_links_absolute(base_href, resolve_base_href=True)
        else:
            doc.resolve_base_href()
        return doc.getroottree()
