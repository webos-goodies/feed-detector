# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

import itertools
import re

from collections import defaultdict

from .abstract   import BaseComponent
from .compat     import *


LINK_RE  = re.compile(r'\Ahttps?://', re.I)
SHORT_RE = re.compile(r'\A[\u0001-\u02ff]*\Z')
BLANK_RE = re.compile(r'\s+', re.U)

DENY_URLS = ('www.facebook.com/sharer/sharer.php',
             'twitter.com/intent/tweet')
DENY_URLS_RE = re.compile(r'\Ahttps?://(?:' +
                          '|'.join([re.escape(x) for x in DENY_URLS]) + ')')

SCORE_LINK     = 2   # normal link
SCORE_IMG      = 1   # image link
SCORE_DENY_URL = -6  # penalty of denied urls
SCORE_NO_TITLE = -2  # link without text
SCORE_LABEL    = -1  # link text looks like a label
SCORE_SHORT    = 0   # link text is too short

SCORE_DUP_URL  = -4  # penalty of url duplication (but not title)
SCORE_DUP_KEY  = -6  # penalty of url and title duplication


def cached_property(f):
    attr_name = '_' + f.__name__
    def getter(self):
        v = getattr(self, attr_name, None)
        if v is None:
            v = f(self)
            setattr(self, attr_name, v)
        return v
    return property(getter)


class Entry(object):
    __slots__ = ('score', 'element', 'url', 'title', 'paths', 'fullpath')

    def __init__(self, element):
        self.score    = SCORE_LINK
        self.element  = element
        self.title    = ((element.text_content() or u'').strip() or
                         (element.get('title') or '').strip())
        self.url      = (element.get('href') or u'').strip()
        self.paths    = self._build_paths(element)
        self.fullpath = self._build_fullpath(element)
        if not self.title:
            for img in self.element.iterdescendants('img'):
                self.title = (img.get('alt') or '').strip() or (img.get('title') or '').strip()
                if self.title:
                    self.score = SCORE_IMG
        if DENY_URLS_RE.match(self.url):
            self.score = SCORE_DENY_URL
        elif not self.title:
            self.score = SCORE_NO_TITLE
        elif SHORT_RE.match(self.title):
            l = len(BLANK_RE.findall(self.title))
            if l <= 2:
                self.score = SCORE_LABEL if l <= 1 else SCORE_SHORT
        elif len(self.title) <= 6:
            self.score = SCORE_LABEL
        elif len(self.title) <= 8:
            self.score = SCORE_SHORT

    def _build_paths(self, el, rpaths=[]):
        tag = el.tag
        if tag in ('html', 'body') or len(rpaths) > 32:
            paths = [(tag,)]
        else:
            classes = el.get('class', '').split()[:2] # important class(es) may be put first.
            paths   = [('%s.%s' % (tag, x),) for x in classes]
            tagid   = el.get('id', '').strip() if rpaths else ''
            if tagid and tag != 'a':
                paths.append(('%s#%s' % (tag, tagid),))
            paths.append((tag,))
        if rpaths:
            paths = [x + y for x, y in itertools.product(paths, rpaths)]
        parent = el.getparent()
        if parent is not None:
            paths = self._build_paths(parent, rpaths=paths)
        return paths

    def _build_fullpath(self, el):
        path = []
        for parent in reversed([x for x in el.iterancestors()]):
            tag = parent.tag
            cls = '.'.join(sorted(parent.get('class', '').split()))
            if cls:
                path.append('%s.%s' % (tag, cls))
            else:
                path.append(tag)
        path.append(el.tag) # a tag's class may indicate click behavior so should not be included.
        return '>'.join(path)

    @classmethod
    def entries_in_document(cls, doc):
        return (cls(x) for x in doc.iterdescendants('a') if LINK_RE.match(x.get(u'href', u'')))


class Path(object):
    __slots__ = ('path', 'key', '_entries', '_entry_map', '_fingerprint')

    def __init__(self, path):
        self.path         = path
        self.key          = Path.key_from(path)
        self._entries     = None
        self._entry_map   = {}
        self._fingerprint = None

    @cached_property
    def entries(self):
        return list(itervalues(self._entry_map))

    @cached_property
    def fingerprint(self):
        return frozenset(iterkeys(self._entry_map))

    def add_entry(self, entry):
        self._entry_map[id(entry)] = entry
        self._entries     = None
        self._fingerprint = None

    @classmethod
    def key_from(cls, path):
        return '>'.join(path)


class PathBuilder(object):

    def __init__(self, document):
        self._doc   = document
        self._paths = {}
        self._build_tree()

    @property
    def paths(self):
        return self._paths.values()

    def _remove_duplicated_id(self):
        dups = set()
        for el in self._doc.root.iter():
            id_attr = el.get('id', '').strip()
            if id_attr and id_attr in dups:
                del el.attrib['id']
            dups.add(id_attr)

    def _add_path(self, path, entry):
        for i in xrange(3, len(path) + 1):
            sub   = path[:i]
            key   = Path.key_from(sub)
            value = self._paths.get(key)
            if value is None:
                value = Path(sub)
                self._paths[key] = value
            value.add_entry(entry)

    def _build_tree(self):
        self._remove_duplicated_id()
        # [TODO] Nested A tags should be removed.
        for entry in Entry.entries_in_document(self._doc.root):
            for path in entry.paths:
                self._add_path(path, entry)


class EntryGroup(object):
    __slots__ = ('score', 'paths', 'entries', 'url_set')

    def __init__(self, entries):
        assert len(entries) > 0, 'Group entries must not be empty'
        self.score   = sum([x.score for x in entries])
        self.paths   = []
        self.entries = list(entries)
        self.url_set = frozenset([x.url for x in entries])
        self._score_duplication()
        self._score_fullpath()

    def add_path(self, path):
        self.paths.append(path)

    def __len__(self):
        return len(self.entries)

    def _score_duplication(self):
        urls = set()
        keys = set()
        for entry in self.entries:
            key = (entry.title, entry.url)
            if key in keys:
                self.score += SCORE_DUP_KEY
            elif entry.url in urls:
                self.score += SCORE_DUP_URL
            keys.add(key)
            urls.add(entry.url)

    def _score_fullpath(self):
        counts = defaultdict(int)
        for entry in self.entries:
            counts[entry.fullpath] += 1
        count = len([k for k, v in iteritems(counts) if v > 1])
        if count > 1:
            self.score /= count * 0.9


class Optimizer(object):

    def __init__(self, paths):
        self._groups = {}
        for path in paths:
            if len(path.entries) <= 0:
                continue
            key   = path.fingerprint
            group = self._groups.get(key)
            if group is None:
                group = self._groups[key] = EntryGroup(path.entries)
            group.add_path(path)

    def optimize(self):
        self._remove_small_groups(4)
        self._consider_inclusion()
        result = sorted([x for x in itervalues(self._groups) if x.score > 0],
                        key=lambda x:x.score, reverse=True)
        if not result and self._groups:
            result = [sorted(itervalues(self._groups), key=lambda x:x.score, reverse=True)[0]]
        return result

    def _remove_small_groups(self, threshold):
        self._groups = dict([(k, v) for k, v in iteritems(self._groups) if len(v) > threshold])

    def _consider_inclusion(self):
        for a, b in itertools.combinations(itervalues(self._groups), 2):
            if a.score <= 0 or b.score <= 0:
                continue
            lab, lba = len(a.url_set - b.url_set), len(b.url_set - a.url_set)
            if lab == 0 or lba == 0:
                (a if a.score < b.score else b).score = 0


class Detector(BaseComponent):

    def run(self, doc):
        paths  = PathBuilder(doc).paths
        result = Optimizer(paths).optimize()
        return result
