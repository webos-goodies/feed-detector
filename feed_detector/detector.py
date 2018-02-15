# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

import itertools
import re
import unicodedata

from collections import defaultdict

from .abstract   import BaseComponent
from .compat     import *
from .util       import *


__all__ = ('Entry', 'Path', 'PathBuilder', 'EntryGroup', 'Optimizer', 'Detector')


SHORT_MATCH     = re.compile(r'\A[\u0001-\u02ff]*\Z').match
BLANK_FINDALL   = re.compile(r'\s+', re.U).findall
SHRINK_SUB      = re.compile(r'[\x00-\x40\x5b-\x60\x7b-\x7f]+').sub

SCORE_LINK      = 2   # normal link
SCORE_IMG       = 1   # image link
SCORE_DENY_URL  = -6  # penalty of denied urls
SCORE_NO_TITLE  = -2  # link without text
SCORE_LABEL     = -1  # link text looks like a label
SCORE_SHORT     = 0   # link text is too short

SCORE_DUP_URL   = -4  # penalty of url duplication (but not title)
SCORE_DUP_TITLE = -1  # penalty of title duplication (but not url)
SCORE_DUP_KEY   = -6  # penalty of url and title duplication

HEADER_TAGS     = frozenset(('h1', 'h2', 'h3', 'h4', 'h5', 'h6'))
GROUPING_TAGS   = frozenset(('ul', 'ol', 'dl', 'table', 'footer', 'header', 'main', 'nav'))
NEST_TAGS       = frozenset(('ul', 'ol'))

UID_ATTR        = '_fd_uid_'


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
    __slots__ = ('score', 'cbg_id', 'element', 'url', 'title', 'paths', 'fullpath')

    def __init__(self, element, cbg_id):
        self.score    = SCORE_LINK
        self.cbg_id   = cbg_id
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
        if not is_valid_url(self.url):
            self.score = SCORE_DENY_URL
        elif not self.title:
            self.score = SCORE_NO_TITLE
        elif SHORT_MATCH(self.title):
            l = len(BLANK_FINDALL(self.title))
            if l <= 2:
                self.score = SCORE_LABEL if l <= 1 else SCORE_SHORT
        else:
            title = self._shrink_title(self.title)
            if len(title) <= 6:
                self.score = SCORE_LABEL
            elif len(title) <= 8:
                self.score = SCORE_SHORT

    def _shrink_title(self, title):
        title = unicodedata.normalize('NFKD', to_unicode(title))
        return SHRINK_SUB(u'', title)

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


class Path(object):
    __slots__ = ('path', 'key', 'entries', '_entry_keys', '_fingerprint')

    def __init__(self, path):
        self.path         = path
        self.key          = Path.key_from(path)
        self.entries      = []
        self._entry_keys  = set()
        self._fingerprint = None

    @cached_property
    def fingerprint(self):
        return frozenset(self._entry_keys)

    def add_entry(self, entry):
        key = entry.element.get(UID_ATTR, '0')
        if key not in self._entry_keys:
            self._entry_keys.add(key)
            self.entries.append(entry)
            self._fingerprint = None

    @classmethod
    def key_from(cls, path):
        return '>'.join(path)


class PathBuilder(object):

    def __init__(self, document):
        self._doc     = document
        self._el_id   = 1
        self._cbg_map = {}
        self._prev_id = 0
        self._hdr_id  = self._new_id()
        self._cur_id  = self._new_id()
        self._nesting = False
        self._paths   = {}
        self.paths    = []
        self._build_tree()

    def _remove_duplicated_id(self):
        dups = set()
        for el in self._doc.root.iter():
            id_attr = el.get('id', '').strip()
            if id_attr and id_attr in dups:
                del el.attrib['id']
            dups.add(id_attr)

    def _new_id(self):
        self._prev_id += 1
        return self._prev_id

    def _cbg_anchor(self, el, tag):
        self._cbg_map[el.get(UID_ATTR, '0')] = self._cur_id
        self._context_base_grouping(el)

    def _cbg_header(self, el, tag):
        self._cur_id = self._hdr_id
        self._context_base_grouping(el)
        self._cur_id = self._new_id()

    def _cbg_grouping(self, el, tag):
        self._cur_id = self._new_id()
        self._context_base_grouping(el)
        self._cur_id = self._new_id()

    def _context_base_grouping(self, parent):
        for el in parent:
            tag = el.tag.lower()
            el.set(UID_ATTR, unicode(self._el_id))
            self._el_id += 1
            if tag == 'a':
                self._cbg_anchor(el, tag)
            elif tag in NEST_TAGS and self._nesting:
                self._context_base_grouping(el)
            elif tag in HEADER_TAGS:
                self._cbg_header(el, tag)
            elif tag in GROUPING_TAGS:
                self._cbg_grouping(el, tag)
            else:
                self._context_base_grouping(el)

    def _add_path(self, path, entry):
        for i in xrange(3, len(path) + 1):
            sub   = path[:i]
            key   = Path.key_from(sub)
            value = self._paths.get(key)
            if value is None:
                value = Path(sub)
                self._paths[key] = value
                self.paths.append(value)
            value.add_entry(entry)

    def _iter_links(self, doc):
        default_id = self._new_id()
        return (Entry(x, self._cbg_map.get(x.get(UID_ATTR, '0'), default_id))
                for x in doc.iterdescendants('a') if LINK_MATCH(x.get(u'href', u'')))

    def _build_tree(self):
        self._remove_duplicated_id()
        # [TODO] Nested A tags should be removed.
        self._context_base_grouping(self._doc.root)
        for entry in self._iter_links(self._doc.root):
            for path in entry.paths:
                self._add_path(path, entry)


class EntryGroup(object):
    __slots__ = ('score', 'cbg_score', 'paths', 'entries', 'url_set')

    def __init__(self, entries):
        assert len(entries) > 0, 'Group entries must not be empty'
        self.score     = sum([x.score for x in entries])
        self.cbg_score = self.score
        self.paths     = []
        self.entries   = list(entries)
        self.url_set   = frozenset([x.url for x in entries])
        self._score_duplication()
        self._score_fullpath()
        self._score_cbg()

    def add_path(self, path):
        self.paths.append(path)

    def __len__(self):
        return len(self.entries)

    def _score_duplication(self):
        keys   = set()
        urls   = set()
        titles = set()
        for entry in self.entries:
            key = (entry.title, entry.url)
            if key in keys:
                self.score += SCORE_DUP_KEY
            elif entry.url in urls:
                self.score += SCORE_DUP_URL
            elif entry.title in titles:
                self.score += SCORE_DUP_TITLE
            keys.add(key)
            urls.add(entry.url)
            titles.add(entry.title)

    def _score_fullpath(self):
        counts = defaultdict(int)
        for entry in self.entries:
            counts[entry.fullpath] += 1
        count = len([k for k, v in iteritems(counts) if v > 1])
        if count > 1:
            self.score /= count * 0.9

    def _score_cbg(self):
        scale = 0.6 if self.cbg_score > 0 else 1.5
        for x in xrange(1, len(frozenset([x.cbg_id for x in self.entries]))):
            self.cbg_score *= 0.6


class Optimizer(object):

    def __init__(self, paths):
        group_map    = {}
        self._groups = []
        for path in paths:
            if len(path.entries) <= 0:
                continue
            key   = path.fingerprint
            group = group_map.get(key)
            if group is None:
                group = group_map[key] = EntryGroup(path.entries)
                self._groups.append(group)
            group.add_path(path)

    def optimize(self):
        self._remove_small_groups(4)
        self._occlusion_culling()
        groups = sorted(self._groups, key=lambda x:x.score, reverse=True)
        result = [x for x in groups if x.score > 0]
        if len(result) >= 4:
            return result[:8]
        else:
            return groups[:4]

    def _remove_small_groups(self, threshold):
        self._groups = [x for x in self._groups if len(x) > threshold]

    def _occlusion_culling(self):
        for a, b in itertools.combinations(self._groups, 2):
            if a.cbg_score <= 0 or b.cbg_score <= 0:
                continue
            lab, lba = len(a.url_set - b.url_set), len(b.url_set - a.url_set)
            if lab == 0 or lba == 0:
                culled = (a if a.cbg_score < b.cbg_score else b)
                culled.score = culled.cbg_score = -65536


class Detector(BaseComponent):

    def run(self, doc):
        paths  = PathBuilder(doc).paths
        result = Optimizer(paths).optimize()
        return result
