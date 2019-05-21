# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals
import re

from .abstract import AbstractFilter
from .compat   import to_unicode


__all__ = ('BodyRemovalFilter',)


DIV_TO_P_TAGS = (u'a', u'blockquote', u'dl', u'div', u'img', u'ol', u'p', u'pre', u'table', u'ul')
UNLIKELY_CANDIDATES_RE = re.compile(u'combx|comment|community|disqus|extra|foot|header|menu|remark|rss|shoutbox|sidebar|sponsor|ad-break|agegate|pagination|pager|popup|tweet|twitter', re.I)
MAYBE_CANDIDATE_RE = re.compile(u'and|article|body|column|main|shadow', re.I)
CLEAN_LF_RE = re.compile(to_unicode(r'\s*\n\s*'))
CLEAN_TAB_RE = re.compile(to_unicode(r'\t|[ \t]{2,}'))
POSITIVE_RE = re.compile(u'article|body|content|entry|hentry|main|page|pagination|post|text|blog|story', re.I)
NEGATIVE_RE = re.compile(u'combx|comment|com-|contact|foot|footer|footnote|masthead|media|meta|outbrain|promo|related|scroll|shoutbox|sidebar|sponsor|shopping|tags|tool|widget', re.I)


def _clean_text(text):
    text = CLEAN_LF_RE.sub("\n", text)
    text = CLEAN_TAB_RE.sub(' ', text)
    return text.strip()

def _get_text_length(el):
    return len(_clean_text(el.text_content() or ''))

def _get_link_density(el):
    link_length = 0
    for i in el.iterdescendants('a'):
        link_length += _get_text_length(i)
    return link_length / max(_get_text_length(el), 1)

def _score_text(text):
    return text.count(u',') + text.count(u"\u3001") / 2.0 + 1

def _class_weight(el):
    weight = 0
    for feature in (el.get('class', None), el.get('id', None)):
        if feature:
            if NEGATIVE_RE.search(feature):
                weight -= 25
            if POSITIVE_RE.search(feature):
                weight -= 25
    return weight

def _score_node(el):
    score = _class_weight(el)
    name = el.tag.lower()
    if name == 'div':
        score += 5
    elif name in ('pre', 'blockquote'):
        score += 3
    elif name in ("address", "ol", "ul", "dl", "dd", "dt", "li", "td", "form"):
        score -= 3
    elif name in ("h1", "h2", "h3", "h4", "h5", "h6", "th"):
        score -= 5
    return { 'score':score, 'element':el }


class BodyRemovalFilter(AbstractFilter):

    def run(self, doc):
        self._prepare(doc)
        self._remove_unlikely_candidates()
        self._inappropriate_div_to_p()
        self._score_paragraphs()
        scores = self._reduce_candidates()
        if scores:
            drop_list = []
            for score in scores:
                self._collect_exclude_elements(score['element'])
                if score['element'].get('x', '') not in self._excludes:
                    self._collect_drop_paths(drop_list, score['element'])
            self._drop_text_elements(doc, drop_list)

    def _prepare(self, doc):
        self._doc  = doc.copy()
        self._root = self._doc.root
        self._doc.add_xpath()
        self._scores = {}
        self._excludes = set()
        self._done = set()

    def _remove_unlikely_candidates(self):
        except_tags = (u'html', u'body')
        for el in self._root.iter():
            s = u"%s %s" % (el.get(u'class', ''), el.get(u'id', u''))
            if ( len(s) >= 2 and
                 UNLIKELY_CANDIDATES_RE.search(s) and
                 not MAYBE_CANDIDATE_RE.search(s) and
                 el.tag not in except_tags):
                el.drop_tree()

    def _inappropriate_div_to_p(self):
        # transform <div>s that do not contain other block elements into <p>s
        for el in self._root.iterdescendants('div'):
            if next(el.iterdescendants(*DIV_TO_P_TAGS), None) is None:
                el.tag = 'p'

        # wrap texts under <div>s by <p>
        for el in self._root.iterdescendants('div'):
            if el.text and el.text.strip():
                p = self._doc.create_fragment('<p/>')
                p.text = el.text
                el.text = None
                el.insert(0, p)

            for pos, child in reversed(list(enumerate(el))):
                if child.tail and child.tail.strip():
                    p = self._doc.create_fragment('<p/>')
                    p.text = child.tail
                    child.tail = None
                    el.insert(pos + 1, p)
                if child.tag == 'br':
                    child.drop_tree()

    def _score_paragraphs(self):
        min_len = self.config.get('body_minimum_length', 0)
        scores  = self._scores
        ordered = []
        for el in self._root.iterdescendants('p', 'pre'):
            parent_el = el.getparent()
            if parent_el is None:
                continue
            grand_parent_el = parent_el.getparent()

            inner_text = _clean_text(el.text_content() or '')
            inner_text_len = len(inner_text)
            if inner_text_len < min_len:
                continue

            if parent_el not in scores:
                scores[parent_el] = _score_node(parent_el)
                ordered.append(parent_el)

            if grand_parent_el is not None and grand_parent_el not in scores:
                scores[grand_parent_el] = _score_node(grand_parent_el)
                ordered.append(grand_parent_el)

            score = 1.0 + _score_text(inner_text) + min((inner_text_len / 100), 3)
            scores[parent_el]['score'] += score
            if grand_parent_el is not None:
                scores[grand_parent_el]['score'] += score / 2.0

        for el in ordered:
            ld = _get_link_density(el)
            scores[el]['link_density'] = ld
            scores[el]['score'] *= 1 - ld

    def _reduce_candidates(self):
        if not self._scores:
            return []
        scores = sorted([x for x in self._scores.values() if x['element'].get('x', '')],
                        key=lambda x:x['score'], reverse=True)
        reduced = []
        added = set()
        denial = set()
        for score in scores:
            el = score['element']
            if score['score'] < 15.0 or score['link_density'] > 0.33 or el in denial:
                continue
            if el.tag in ('html', 'head', 'body'):
                continue
            if any((x in added for x in el.iterancestors())):
                continue
            reduced.append(score)
            added.add(el)
            denial.add(el)
            for ancestor in el.iterancestors():
                denial.add(ancestor)
        return reduced

    def _collect_exclude_elements(self, element):
        for el in element.iter("h1", "h2", "h3", "h4", "h5", "h6"):
            if _class_weight(el) < 0 or _get_link_density(el) > 0.33:
                self._excludes.add(el.get('x', u''))

        min_len = self.config.get('body_minimum_length', 0)
        done = self._done
        scores = self._scores
        for el in reversed(list(element.iter('table', 'ul', 'div', 'p'))):
            if el in done:
                continue
            done.add(el)

            weight = _class_weight(el)
            score = scores[el]['score'] if el in scores else 0
            tag = el.tag

            if weight + score < 0:
                self._excludes.add(el.get('x', u''))
            elif _score_text(el.text_content() or u'') < 10:
                counts = {}
                for kind in ('p', 'img', 'li', 'a', 'embed', 'input'):
                    counts[kind] = len(el.findall('.//%s' % kind))
                counts["input"] -= len(el.findall('.//input[@type="hidden"]'))

                parent_node = el.getparent()
                if parent_node is not None:
                    score = scores[parent_node]['score'] if parent_node in scores else 0

                content_length = _get_text_length(el)
                link_density = _get_link_density(el)
                to_remove = False
                if tag == 'ul' or tag == 'ol':
                    to_remove = counts['li'] == counts['a']
                else:
                    to_remove = counts['li'] - 100 > counts['p']
                to_remove = to_remove or (
                    (counts['p'] and counts['img'] > 1 + counts['p'] * 1.3) or
                    (counts['input'] > counts['p'] / 3) or
                    (content_length < min_len and counts['img'] == 0) or
                    (content_length < min_len and counts['img'] > 2) or
                    (weight < 25 and link_density > 0.2) or
                    (weight >= 25 and link_density > 0.5) or
                    ((counts["embed"] == 1 and content_length < 75) or counts["embed"] > 1))
                if not to_remove and not content_length:
                    to_remove = True
                if to_remove:
                    el = next(el.iterancestors('a'), el)
                    self._excludes.add(el.get('x', u''))
            elif tag == 'ul' or tag == 'ol':
                if len(el.findall('.//li')) == len(el.findall('.//a')):
                    el = next(el.iterancestors('a'), el)
                    self._excludes.add(el.get('x', u''))

        self._excludes.discard(u'')

    def _collect_drop_paths(self, drop_list, element):
        drop = True
        sub_list = []
        excludes = self._excludes
        for child in element:
            path = child.get('x', '')
            if not path:
                continue
            if path in excludes:
                drop = False
            else:
                drop = self._collect_drop_paths(sub_list, child) and drop
        path = element.get('x', '')
        if drop and path:
            drop_list.append(path)
        else:
            drop_list.extend(sub_list)
        return drop

    def _drop_text_elements(self, doc, drop_list):
        tree = doc.tree
        drop_elements = []
        for path in drop_list:
            el = tree.find(path)
            if el is not None:
                drop_elements.append(el)
        for el in drop_elements:
            el.drop_tree()
