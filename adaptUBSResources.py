#!/usr/bin/env -S uv run
# -\*- coding: utf-8 -\*-
# SPDX-FileCopyrightText: © 2026 Robert Hunt <Freely.Given.org+OBD@gmail.com>
# SPDX-License-Identifier: CC0-1.0
#
# adaptUBSResources.py
#
# Script to adapt the UBS open-licensed resources to suit the OET-RV
#
# Copyright (C) 2026 Robert Hunt
# Author: Robert Hunt <Freely.Given.org+OBD@gmail.com>
# License: CC0-1.0 (the script itself)
#   The adapted UBS resources remain CC BY-SA 4.0 (see ADAPTATION_NOTICE.md)
#
"""
Adapt the English UBS open-licensed resources
    (from https://github.com/ubsicap/ubs-open-license, cloned into the parent folder)
    to imitate how the OET Readers' Version (OET-RV) handles names and some wording.

The names code block is shared (by copying) with
    OpenBibleData/datasets/Tyndale/OET_TyndaleOpenResources/adaptTyndaleResources.py, adapt_uW_en_tn.py, and adaptSILOpenTranslatorsNotes.py
    (so that this script is independent)
    (which loads OET-RV_names_table.tsv and checks how the OET-RV ESFM files explain each name),
    so both sets of adapted resources are treated identically.

Steps:
    1/ Delete and freshly re-copy the English (and language-neutral) resources from the parent folder.
        Non-English files aren't copied (our adaptations are only for English),
        nor are the image zip files (2.7GB of unchanged binaries — get them from the original repo).
    2/ Adapt the English text fields, e.g., 'Jesus' -> 'Yeshua (Jesus; Grk. Yesus)' on first use
        in each dictionary entry/article, then just 'Yeshua' (until EXPLAIN_WINDOW_FIELDS fields later).
        Only prose fields are changed (glosses, definitions, comments, descriptions, paragraphs, remarks…):
            never keys, codes, references, Hebrew/Greek, domain labels, or UBS {X:…} tokens.
        Text quoted from other Bible versions, e.g., '“helmets” (<a>RSV</a>)' isn't changed.
        In UBS link tokens like '{L:Abijah<SDBH:אֲבִיָּה>}' only the displayed name is changed,
            and any explanation goes after the token, e.g., '{L:Aviyah<SDBH:אֲבִיָּה>} (Abijah)'.
    3/ Write a table of OET-RV forms of the Bible route titles (the route filenames are left unchanged).
    4/ Write ADAPTATION_NOTICE.md (required by CC BY-SA) and adaptation_log.tsv.

CHANGELOG:
    2026-11-19 First version
    2026-11-19 Also adapt the HOTTP English suggestions
    2026-11-19 Copy the names code into this script (instead of importing adaptTyndaleResources.py) so that it's independent;
                don't change Bible book names in references like 'John 1:19'
    2026-11-20 Update the shared names code block; leave text quoted from other Bible versions unchanged
"""
from collections import Counter, defaultdict
from csv import DictReader
from functools import lru_cache
import json
from pathlib import Path
import re
import shutil
import sys


LAST_MODIFIED_DATE = '2026-11-20' # by RJH
PROGRAM_NAME = "Adapt UBS open-licensed resources for OET-RV"
PROGRAM_VERSION = '0.13'

THIS_FOLDER = Path(__file__).resolve().parent
UBS_FOLDER = THIS_FOLDER.parent # The original UBS repo
OET_RV_FOLDER = Path('/srv/FreelyGiven/OpenEnglishTranslation--OET/translatedTexts/ReadersVersion/')
NAMES_TABLE_FILEPATH = OET_RV_FOLDER / 'OET-RV_names_table.tsv'

EXPLAIN_WINDOW_FIELDS = EXPLAIN_WINDOW = 10 # Re-explain a name if it was last explained more than this many text fields earlier (in the same entry)
EXPLAIN_ONLY_FLAGGED_NAMES = False # True = only explain names with Explained=Y in the names table
MAX_TRADITIONAL_FRACTION = 0.2 # Don't change a name if the OET-RV text itself uses the traditional form more than this fraction of the time

# Traditional names that are also common English words or otherwise unsafe to change automatically
SKIP_NAMES = { 'Abed', 'Agar', 'Bath', 'Beer', 'Behemoth', 'Carpus', 'Cherub', 'Clement', 'Col', 'Crates',
    'Destiny', 'Epicurean', 'Epicureans', 'Ether', 'Fortune', 'Gob', 'Leviathan', 'Macron', 'Manes',
    'Media', 'Mica', 'Mortar', 'Narcissus', 'Onus', 'Phoenix', 'Shamed', 'Stoic', 'Straight', 'Tidal', 'Weeks',
    'Hebrew', 'Hebrews', 'Greek', 'Greeks', 'Aramaic', 'Latin', # Mostly refer to languages (or a book) in these resources
    'Corinthians', 'Ephesians', 'Philippians', 'Thessalonians', 'Colossians', 'Galatians', 'Romans', # Mostly refer to NT books
    'Josephus', # The historian
    'Nazarene', 'Judea', # Table maps these to Nazaret and Yehudah, which don't suit NT commentary
    }

# Terminology changes: (enabled, regex, replacement, description)
#   Replacements keep the case of the first letter of the matched text.
TERMINOLOGY_RULES = [
    (True, r'\b(?:[Tt]he )?LORD\b', 'Yahweh', "LORD → Yahweh"),
    (True, r'\bJohn the Baptist\b', 'John the immerser', "John the Baptist → John the immerser"),
    # Disabled: OET-RV wording, but it would hide the standard terms in lexicon glosses
    (False, r'\bSabbath\b', 'Rest Day', "Sabbath → Rest Day"),
    (False, r'\bsynagogue\b', 'meeting hall', "synagogue → meeting hall"),
    ]

# Folders (relative to the UBS repo) that we delete and re-copy each run, with the files to copy
#   None means copy all files (they're language-neutral)
ENGLISH_FILE_RE = re.compile(r'(?i)(?:[-_]en\.(?:json|xml|html)|^README\.md|^LICENSE\.md|^HOTTP\.XML)$')
COPIED_FOLDERS = {
    'dictionaries': ENGLISH_FILE_RE,
    'flora-fauna-realia': ENGLISH_FILE_RE,
    'HOTTP': ENGLISH_FILE_RE, # HOTTP.XML contains both English and French (only the English is adapted)
    'parallel passages': None, # References and word-match codes only
    'index': None, # MARBLE links from WLC words to other resources (codes only)
    'ubs-bible-routes': None, # GeoJSON and SVG (no text except for the filenames)
    'images': re.compile(r'^(?:README|LICENSE)\.md$'), # Not the zip files
    }
COPIED_TOP_LEVEL_FILES = {'README.md':'UBS_README.md', 'LICENSE.md':'UBS_LICENSE.md'}

# JSON keys that contain English prose that we adapt (as long as any LanguageCode is 'en')
JSON_TEXT_KEYS = {
    'Glosses', 'DefinitionShort', 'DefinitionLong', 'Comments', # In LEXSenses
    'Description', 'Comment', # In SemanticDomainLocalizations
    }
    # Not 'Notes'/'Content' (textual notes quoting other translations), 'Label' (domain names used as keys),
    #   'Meaning' (only grammatical comments like 'indeclinable' or empty name meanings)

# XML elements that contain English prose that we adapt, and elements inside them that we never change
XML_TEXT_ELEMENTS = {
    'Gloss', 'DefinitionShort', 'DefinitionLong', 'Comments', # Dictionary senses
    'Description', 'Comment', # Semantic domains
    'Title', 'Heading', 'SubHeading', 'Paragraph', 'Caption', # Flora, fauna, realia
    'Remark', 'Suggestion', 'Literal', # HOTTP (but not Remark-FR, SuggestionFR, LiteralFR, or quoted Versions)
    }
XML_SKIP_ELEMENTS = {'s', 'l', 'Reference', 'Lemma', 'Transliteration', 'FileName', 'Copyright', 'Label', 'LanguageCode'}
XML_ITEM_ELEMENTS = {'Lexicon_Entry', 'SemanticDomain', 'ThemLex_Entry', 'HOTTP_Entry'} # Explanations restart in each of these

UBS_TOKEN_RE = re.compile(r'\{([A-Z]):([^{}]*)\}') # e.g., {S:04600100000000} or {L:Abijah<SDBH:אֲבִיָּה>}
EXPLAINED_RE = re.compile(r'^(.*\S) (\([^()]+\))$') # e.g., 'Aviyah (Abijah)'


############################################################################################################
# BEGIN OET-RV names code
#   This block is copied (identically) into adaptTyndaleResources.py, adaptUBSResources.py, adapt_uW_en_tn.py,
#       and adaptSILOpenTranslatorsNotes.py so that each repo's script is independent. Please keep the copies in sync.
#   The including script must first define OET_RV_FOLDER, NAMES_TABLE_FILEPATH, EXPLAIN_WINDOW, EXPLAIN_ONLY_FLAGGED_NAMES,
#       MAX_TRADITIONAL_FRACTION, SKIP_NAMES, and TERMINOLOGY_RULES (a list of (enabled, regex, replacement, description)
#       which is used unless the NameAdapter is given its own compiled terminology rules).
############################################################################################################

POSSESSIVE_RE = re.compile(r"(?:[’']s\b|[’'](?= [a-z]))") # ’s or (after s) a bare ’ followed by a lower-case word
BOOK_REFERENCE_AFTER_RE = re.compile(r'\s\d{1,3}(?=[:.,;–\-)\]\s]|$)') # e.g., the ' 1' in 'John 1:19' (the name is a Bible book)
BOOK_NUMBER_BEFORE_RE = re.compile(r'(?:^|\W)[1-4]\s$') # e.g., the '1 ' in '1 John'
NUMBERED_BOOK_NAMES = {'Samuel', 'John', 'Peter', 'Esdras', 'Ezra'} # Names that are also numbered Bible books, e.g., '2 Samuel'

# Text quoted from (or attributed to) these Bible versions is never changed, e.g., '“For God so loved…” (NIV)'
#   (except for a resource's own base translation(s) — see NameAdapter ownVersions)
BIBLE_VERSIONS = ('KJV', 'AV', 'NKJV', 'NIV', 'NIV84', 'NIV93', 'NIV11', 'NIV2011', 'TNIV', 'NIrV', 'NIRV',
    'NLT', 'NLT96', 'NLT04', 'NLV', 'RSV', 'NRSV', 'NRSVue', 'ESV', 'NASB', 'NASB95', 'NASB20', 'NAB', 'NABRE',
    'JB', 'NJB', 'NEB', 'REB', 'GNT', 'GNB', 'TEV', 'CEV', 'NCV', 'NET', 'HCSB', 'CSB', 'CEB', 'BSB', 'BLB', 'MSB',
    'ASV', 'JPS', 'NJPS', 'NJPSV', 'TLB', 'LB', 'ULT', 'UST', 'ULB', 'UDB', 'GW', 'ERV', 'ICB', 'MSG', 'AMP',
    'LEB', 'WEB', 'YLT', 'DRA', 'LXX', 'JBP', 'Phps', 'Phillips', 'Mft', 'Moffatt', 'Knox', 'Weymouth', 'Goodspeed',
    'TRT', 'EASY', 'T4T', 'VOICE', 'Voice', 'TLV', 'CJB', 'AT', 'BE', 'TNT', 'TOB', 'NOB', 'NVSR', 'SSA',
    'GECL', 'ITCL', 'FRCL', 'SPCL', 'DUCL', 'BRCL', 'Vulgate', 'Syriac', 'Peshitta', 'Targum')
MAX_QUOTE_LENGTH = 800 # characters
INLINE_TAG_RE = re.compile(r'</?(?:a|b|i|u|s|l|em|strong|span|sup|sub|small|cite)\b[^>]*>') # Other tags separate blocks of text
_VERSION_PATTERN = '|'.join(re.escape(version) for version in sorted(BIBLE_VERSIONS, key=len, reverse=True)) \
                    + r'|[A-Z][\w-]+(?: [A-Z][\w-]+)* [Bb]ack [Tt]ranslation' # e.g., '(Kankanaey Back Translation)'
VERSION_RE = re.compile(rf'(?<![\w-])(?:{_VERSION_PATTERN})(?![\w-])')
# These patterns are used on 'masked' text, where inline tags are replaced by \x00 and other tags by \x01
_IG = r'[\s\x00]*' # Ignorable whitespace and inline tags
_VERSION_LIST = rf'(?<![\w-])(?:{_VERSION_PATTERN})(?![\w-])(?:{_IG}(?:,|/|;|&|and|or){_IG}(?<![\w-])(?:{_VERSION_PATTERN})(?![\w-]))*' \
                rf'(?:{_IG}(?:footnote|margin|text|note|\d{{2,4}}))?'
_ATTRIBUTION = rf'[(\[]{_IG}(?:[^()\[\]\x01]{{0,40}}?[\s\x00,;:])?{_VERSION_LIST}(?:{_IG}[,;][^()\[\]\x01]{{0,60}})?[\s\x00,;.]*[)\]]'
    # e.g., '(NIV)', '(John 3:16, NIV)', '(RSV; Greek skēnē)'
_REFERENCE = r'(?:[1-4] ?)?[A-Z][a-z]{1,14}\.? \d{1,3}(?:[:.]\d{1,3}(?:[–-]\d{1,3})?)?' # e.g., 'Jn 3:16'
_QUOTE = r'(?:“[^“”\x01]{1,800}”|‘[^‘\x01]{1,800}?’(?!\w)|"[^"\x01]{1,800}")'
QUOTE_THEN_VERSION_RES = ( # Each has a closing quote and an attribution
    re.compile(rf'(?P<close>[”’"]){_IG}[.,;:]?{_IG}(?:{_REFERENCE}{_IG})?(?P<attribution>{_ATTRIBUTION})'), # '“…” (NIV)'
    re.compile(rf'(?P<close>[”’"]){_IG}[;,]{_IG}(?P<attribution>{_VERSION_LIST})(?={_IG}[)\]])'), # '(“tent”; RSV)'
    re.compile(rf'(?P<close>[”’"]){_IG}[.,]?{_IG}(?:in|from|according to){_IG}(?:the{_IG})?(?P<attribution>{_VERSION_LIST})'), # '“boxwood” in NEB'
    )
_BETWEEN = r'[^“”‘"\x01.!?;]{0,80}?' # Not crossing a sentence end or another quote
VERSION_THEN_QUOTE_RE = re.compile(rf'(?P<attribution>{_VERSION_LIST}){_IG}(?:’s)?' # e.g., 'NIV: “…”', 'the RSV has “…”', 'NJB (similarly JB), “…”'
    rf'(?:{_BETWEEN}(?<![\w-])(?:has|have|had|reads?|translates?|translated|translation|renders?|rendered|rendering|says|said|gives|gave|uses|used|puts? it'
                    rf'|offers|prefers|provides|model|calls?|called|with|as)(?![\w-]){_BETWEEN}(?::|,)?|{_BETWEEN}[:,])?{_IG}'
    rf'(?P<quote>{_QUOTE})')
GENERIC_VERSIONS_THEN_QUOTE_RE = re.compile(rf'(?<![\w-])(?:translations|versions)(?![\w-]){_BETWEEN}(?<![\w-])(?:have|has|read|reads|say|says|translate|translates|render|renders)(?![\w-])'
                                            rf'{_BETWEEN}(?::|,)?{_IG}(?P<quote>{_QUOTE})') # e.g., 'many modern translations have: “…”'
VERSION_NAME_RE = re.compile(r"\b(?:King James|(?:New )?Jerusalem Bible|Matthew[’']s Bible)\b") # Names that contain a person or place name
BLOCKQUOTE_RE = re.compile(r'<blockquote\b[^>]*>(.*?)</blockquote>', re.DOTALL)
SIMPLE_LIST_ITEM_RE = re.compile(r'<li\b[^>]*>(<p\b[^>]*>(?:(?!</?(?:p|li|ul|ol|blockquote)\b).)*</p>)</li>', re.DOTALL)
TABLE_CELL_RE = re.compile(r'<td\b[^>]*>(.*?)</td>', re.DOTALL)
ATTRIBUTION_RE = re.compile(rf'(?P<attribution>{_ATTRIBUTION})')
VERSION_INTRODUCTION_RE = re.compile(rf'(?P<attribution>{_VERSION_LIST})[^.!?\x01]{{0,60}}:[\s\x00\x01]*$') # e.g., '…the RSV says:</p>' (before a blockquote)
ATTRIBUTED_BLOCK_END_RE = re.compile(rf'(?P<attribution>{_ATTRIBUTION}(?:{_IG}{_ATTRIBUTION})*)[\s\x00\x01]*$') # e.g., '…Jerusalem (GW)</p>'
OPENING_QUOTES = {'”':'“', '’':'‘', '"':'"'}
PROTECT_START, PROTECT_END = '\uE000', '\uE001' # Private-use characters for our placeholders
_protectionCount = 0 # Gives each protectSpans call its own placeholders (so that protected text can be protected again)


def maskTags(text:str) -> str:
    """
    Return the text with each tag replaced by the same number of \\x00 (inline tags) or \\x01 (other tags) characters,
        so that our quote patterns can see the text (but not cross block boundaries) and the character positions don't change.
    """
    return re.sub(r'<[^>]*>', lambda m: ('\x00' if INLINE_TAG_RE.fullmatch(m.group(0)) else '\x01') * len(m.group(0)), text)
# end of maskTags


def versionQuoteSpans(text:str, ownVersions=frozenset()) -> list[tuple[int,int]]:
    """
    Find text quoted from other Bible versions (which we mustn't change), e.g.,
        '“For God so loved…” (NIV)', '“…” (Jn 3:16 NIV)', '“sanctuary”; <a>RSV</a>)', '“boxwood” in NEB',
        'NIV: “…”', 'the RSV has “…”', '<a>CEV</a> renders <s>…</s> as “…”', 'many modern translations have: “…”',
        (SIL) blockquotes like '<blockquote><p>Simon was coming into Jerusalem (GW)</p></blockquote>'
            or introduced by '…the RSV says:</p>', list items like '<li><p>…to Jesus (NJB)</p></li>', table cells like '<td><p>Don’t Be Ashamed of Jesus (NCV)</p></td>',
        and the names of versions like 'King James Version' and 'New Jerusalem Bible'.

    The text can contain (XML/HTML) tags. Quotes attributed only to ownVersions (the resource's own base translations)
        aren't included.

    Returns a sorted list of non-overlapping (start, end) character spans (including the attributions).
    """
    spans = [(match.start(), match.end()) for match in VERSION_NAME_RE.finditer(text)]
    if not VERSION_RE.search(text) and not GENERIC_VERSIONS_THEN_QUOTE_RE.search(text): return spans
    masked = maskTags(text)
    def isOtherVersion(attribution:str) -> bool:
        return bool(set(VERSION_RE.findall(attribution)) - set(ownVersions))
    for quoteThenVersionRE in QUOTE_THEN_VERSION_RES:
        for match in quoteThenVersionRE.finditer(masked):
            if not isOtherVersion(match.group('attribution')): continue
            closeIndex = match.start('close')
            lowIndex = max(masked.rfind('\x01', 0, closeIndex) + 1, closeIndex - MAX_QUOTE_LENGTH)
            openIndex = masked.rfind(OPENING_QUOTES[match.group('close')], lowIndex, closeIndex)
            if openIndex >= 0: spans.append((openIndex, match.end()))
    for match in VERSION_THEN_QUOTE_RE.finditer(masked):
        if isOtherVersion(match.group('attribution')): spans.append((match.start(), match.end()))
    for match in GENERIC_VERSIONS_THEN_QUOTE_RE.finditer(masked):
        spans.append((match.start('quote'), match.end('quote')))
    introducedEnd = None # End of the last blockquote that was introduced by a version, e.g., 'the RSV says:'
    for match in BLOCKQUOTE_RE.finditer(text):
        attributionMatch = ATTRIBUTED_BLOCK_END_RE.search(masked, match.start(1), match.end(1))
        if attributionMatch and isOtherVersion(attributionMatch.group('attribution')):
            spans.append((match.start(1), match.end(1)))
            continue
        before = masked[max(0, match.start()-300):match.start()].rstrip('\x01\x00 \n')
        if introducedEnd is not None and not masked[introducedEnd:match.start()].strip('\x01\x00 \n'): # Follows on from an introduced blockquote
            spans.append((match.start(1), match.end(1))); introducedEnd = match.end(); continue
        introductionMatch = VERSION_INTRODUCTION_RE.search(before[before.rfind('\x01')+1:])
        if introductionMatch and isOtherVersion(introductionMatch.group('attribution')):
            spans.append((match.start(1), match.end(1))); introducedEnd = match.end()
        else: introducedEnd = None
    for match in SIMPLE_LIST_ITEM_RE.finditer(text): # e.g., '<li><p>Then they took the colt to Jesus (NJB)</p></li>'
        attributionMatch = ATTRIBUTED_BLOCK_END_RE.search(masked, match.start(1), match.end(1))
        if attributionMatch and isOtherVersion(attributionMatch.group('attribution')):
            spans.append((match.start(1), match.end(1)))
    for match in TABLE_CELL_RE.finditer(text): # e.g., section headings from various versions '<td><p>Don’t Be Ashamed of Jesus (NCV)</p></td>'
        attributionEnds = [attributionMatch.end() for attributionMatch in ATTRIBUTION_RE.finditer(masked, match.start(1), match.end(1))
                                if isOtherVersion(attributionMatch.group('attribution'))]
        if attributionEnds: spans.append((match.start(1), attributionEnds[-1]))
    mergedSpans = []
    for start, end in sorted(spans):
        if mergedSpans and start <= mergedSpans[-1][1]:
            mergedSpans[-1] = (mergedSpans[-1][0], max(end, mergedSpans[-1][1]))
        else: mergedSpans.append((start, end))
    return mergedSpans
# end of versionQuoteSpans


def protectSpans(text:str, spans:list[tuple[int,int]]) -> tuple[str,list[str]]:
    """
    Replace the text (but not any tags) inside each span with numbered placeholders,
        so that later processing (which still sees all the tags) can't change it.

    Returns the new text and the list of saved pieces (for restoreSpans).
    """
    global _protectionCount
    if not spans: return text, []
    _protectionCount += 1
    pieces, saved, lastEnd = [], [f'{_protectionCount}:'], 0 # saved[0] is our placeholder prefix
    for start, end in spans:
        pieces.append(text[lastEnd:start])
        for piece in re.split(r'(<[^>]*>)', text[start:end]):
            if piece.startswith('<') or not piece: pieces.append(piece)
            else:
                pieces.append(f'{PROTECT_START}{saved[0]}{len(saved)}{PROTECT_END}')
                saved.append(piece)
        lastEnd = end
    pieces.append(text[lastEnd:])
    return ''.join(pieces), saved
# end of protectSpans


def restoreSpans(text:str, saved:list[str]) -> str:
    if not saved: return text
    placeholderRE = re.compile(f'{PROTECT_START}{saved[0]}(\\d+){PROTECT_END}')
    text, numRestored = placeholderRE.subn(lambda m: saved[int(m.group(1))], text)
    assert numRestored == len(saved) - 1, f"Only restored {numRestored} of {len(saved)-1} protected pieces"
    return text
# end of restoreSpans


def harvestEsfmExplanations() -> tuple[dict[str,Counter],Counter]:
    """
    Scan the OET-RV ESFM files for name explanations like 'Yeshua \\add !(Jesus; Grk. Yesus)\\add*'
        so that we can imitate the way each name is most commonly explained.

    Also counts how often each capitalised word (or hyphenated word) is used in the OET-RV text
        (outside of explanations), so we can tell if the OET-RV actually keeps a traditional name.

    Returns a dict with RV names as keys, and counters of the explanation (inside the parentheses) as values,
        plus a counter of words used in the OET-RV text.
    """
    explanations, wordCounts = defaultdict(Counter), Counter()
    explanationRE = re.compile(r"([A-Z][\w’'-]*)(?:\\\+?add\*)? \\\+?add !\(([^)]+)\)")
    for filepath in sorted(OET_RV_FOLDER.glob('OET-RV_*.ESFM')):
        text = re.sub(r'¦\d+', '', filepath.read_text(encoding='utf-8'))
        for match in explanationRE.finditer(text):
            rvName, explanation = match.group(1), match.group(2)
            if rvName[-2:] in ("'s",'’s'): # Ignore possessives (they're handled by our code)
                continue
            explanations[rvName][explanation] += 1
        # Now count words in the Bible text only (not in introductions, headings, comments, or footnotes)
        text = '\n'.join(line for line in text.splitlines()
                            if not re.match(r'\\(rem|i[a-z]*|li\d?|mt\d?|toc\d|h|id|usfm|ide|s\d?|r|d|ms\d?|mr|sr|cl)\b', line))
        text = re.sub(r'\\f .+?\\f\*|\\x .+?\\x\*', ' ', text) # Remove footnotes and cross-references
        text = explanationRE.sub(r'\1', text) # Remove explanations
        text = re.sub(r'\([^()]*\)', ' ', text) # Remove other parenthesised text (e.g., unmarked explanations)
        text = re.sub(r"[\w’']+/ ?([\w’']+)", r'\1', text) # Remove slashed explanations like Yakov/Jacob
        text = re.sub(r'\\[a-z0-9+]+\*?|[@&*≈~]', ' ', text).replace("'", '’') # Remove markers and OET-RV special characters
        wordCounts.update(re.findall(r"(?<![\w’'-])[A-Z][\w’']*(?:[- ][A-Z][\w’']*)*", text))
    print(f"  Found explanations for {len(explanations):,} names in the OET-RV ESFM files")
    return explanations, wordCounts
# end of harvestEsfmExplanations


def loadNames(esfmExplanations:dict[str,Counter], esfmWordCounts:Counter) -> dict[str,dict]:
    """
    Load the OET-RV names table and decide how to explain each name.

    Returns a dict with traditional names as keys.
    """
    rowsByTraditionalName = defaultdict(list)
    with open(NAMES_TABLE_FILEPATH, 'rt', encoding='utf-8', newline='') as tsvFile:
        for row in DictReader(tsvFile, delimiter='\t'):
            rowsByTraditionalName[row['TraditionalName'].strip()].append(row)

    @lru_cache(maxsize=None)
    def esfmCount(name:str) -> int:
        """ How often the OET-RV uses this name (including possessive and multi-word uses) """
        return sum(count for word,count in esfmWordCounts.items()
                    if word == name or word == f"{name}’s" or word.startswith(f'{name} ') or word.endswith(f' {name}'))

    names, skippedAmbiguous, skippedKept = {}, [], []
    for traditionalName, rows in rowsByTraditionalName.items():
        if not traditionalName or traditionalName in SKIP_NAMES \
        or '' in traditionalName.split('-'): # e.g., 'Beth-' name components
            continue
        rows = [row for row in rows if row['RVName'].strip() and row['RVName'].strip() != traditionalName
                    and '(0)' not in row['Comment']] # '(0)' entries are name components and titles
        if not rows: continue
        if len({row['RVName'] for row in rows}) > 1: # Same traditional name maps to different RV names
            flaggedRows = [row for row in rows if row['Explained'].strip()=='Y']
            if len(flaggedRows) != 1:
                skippedAmbiguous.append(f"{traditionalName}={'/'.join(row['RVName'] for row in rows)}")
                continue
            rows = flaggedRows # Use the main (explained) one
        row = rows[0]
        rvName = row['RVName'].strip()
        traditionalCount = esfmCount(traditionalName)
        if traditionalCount > MAX_TRADITIONAL_FRACTION * (traditionalCount + esfmCount(rvName)):
            skippedKept.append(traditionalName) # The OET-RV text often still uses the traditional form
            continue
        isFlagged = row['Explained'].strip() == 'Y'
        if EXPLAIN_ONLY_FLAGGED_NAMES and not isFlagged:
            explanation = None
        else:
            explanation = traditionalName # Default
            # See if the OET-RV ESFM files usually add a Greek form
            grkExplanations = Counter()
            for esfmExplanation,count in esfmExplanations.get(rvName, {}).items():
                if esfmExplanation.startswith(f'{traditionalName}; Grk. '):
                    grkExplanations[esfmExplanation] += count
                elif esfmExplanation == traditionalName:
                    grkExplanations[None] += count
            if grkExplanations:
                mostCommon = grkExplanations.most_common(1)[0][0]
                if mostCommon: explanation = mostCommon
        names[traditionalName] = {'rvName':rvName, 'explanation':explanation, 'flagged':isFlagged}
    print(f"  Loaded {len(names):,} names to change from {NAMES_TABLE_FILEPATH.name}")
    if skippedKept:
        print(f"  Skipped {len(skippedKept)} names still often used in OET-RV text: {', '.join(skippedKept)}")
    if skippedAmbiguous:
        print(f"  Skipped {len(skippedAmbiguous)} ambiguous names: {', '.join(skippedAmbiguous)}")
    return names
# end of loadNames


def makeNamesRegex(names:dict[str,dict]) -> re.Pattern:
    """
    Make one big regex that matches any of the traditional names (longest first).

    Parts after a hyphen can be either case, e.g., 'Abel-meholah' also matches 'Abel-Meholah'.
    """
    def namePattern(name:str) -> str:
        parts = name.split('-')
        return '-'.join([re.escape(parts[0])] + [f'[{p[0].upper()}{p[0].lower()}]{re.escape(p[1:])}' for p in parts[1:]])
    alternatives = '|'.join(namePattern(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w’'-])({alternatives})(?![\w]|-\w)")
# end of makeNamesRegex


def possessive(name:str) -> str:
    """ Jesus -> Jesus’, John -> John’s, Grk. Yoannes -> Grk. Yoannes’ """
    return name + ('’' if name.endswith('s') else '’s')
# end of possessive


def matchCase(replacement:str, matchedText:str) -> str:
    if replacement.startswith('<') or not matchedText or not replacement: return replacement
    if matchedText[0].isupper(): return replacement[0].upper() + replacement[1:]
    return replacement
# end of matchCase


class NameAdapter:
    """
    Changes names (and some terminology) in text fields,
        explaining each name on its first use in an item (entry/note/article),
        and again if it hasn't been explained within the last EXPLAIN_WINDOW fields/lines.

    By default (for dictionaries and articles), names are changed to the OET-RV names,
        e.g., 'Samuel' -> 'Shmuel (Samuel)' then just 'Shmuel'.
    If theirNameFirst is set (for notes that refer to their own translation, e.g., the NLT, ULT, or BSB),
        their name is kept, with the OET-RV name after it on first use, e.g., 'Samuel (Shmuel)' then just 'Samuel',
        and likewise for their terms, e.g., 'the LORD (Yahweh)'.

    Text quoted from other Bible versions (not ownVersions) can be left unchanged using adaptProtected().
    """
    def __init__(self, names:dict[str,dict], namesRE:re.Pattern, counts:Counter, *,
                    theirNameFirst:bool=False, ownVersions=frozenset(), terminologyRules:list|None=None) -> None:
        self.names, self.namesRE, self.counts = names, namesRE, counts
        self.theirNameFirst, self.ownVersions = theirNameFirst, frozenset(ownVersions)
        self.lowerNames = {name.lower():name for name in names}
        self.terminologyRules = terminologyRules if terminologyRules is not None \
                                    else [(re.compile(regex), replacement, description)
                                            for enabled, regex, replacement, description in TERMINOLOGY_RULES if enabled]
        self.lastExplainedLine:dict[str,int] = {}
        self.lineNumber = 0

    def newItem(self) -> None:
        self.lastExplainedLine = {}

    def adaptProtected(self, text:str, adaptFunction) -> str:
        """
        Call adaptFunction(text) but with any text quoted from other Bible versions protected from changes.
        """
        spans = versionQuoteSpans(text, self.ownVersions)
        if not spans: return adaptFunction(text)
        self.counts['KEEP\tQuote from another Bible version (unchanged)'] += len(spans)
        protectedText, saved = protectSpans(text, spans)
        return restoreSpans(adaptFunction(protectedText), saved)

    def adaptText(self, text:str) -> str:
        """
        Adapt one plain-text field (counted as one 'line' for the explanation window).
        """
        self.lineNumber += 1
        return self.adaptProtected(text, lambda t: self.adaptNames(self.adaptTerminology(t, self.terminologyRules)))

    def adaptTerminology(self, text:str, rules:list) -> str:
        for regex, replacement, description in rules:
            if self.theirNameFirst: text = self.explainTerms(text, regex, replacement, description)
            else:
                text, numChanges = regex.subn(lambda m: matchCase(m.expand(replacement), m.group(0)), text)
                if numChanges: self.counts[f'TERM\t{description}'] += numChanges
        return text

    def explainTerms(self, text:str, regex:re.Pattern, replacement:str, description:str) -> str:
        """
        For notes that refer to their own translation: keep their term, but add ours after it on first use
            (and again after EXPLAIN_WINDOW lines), e.g., 'the LORD (Yahweh)', 'the LORD’s (Yahweh’s)'.
        """
        result, lastEnd = [], 0
        for match in regex.finditer(text):
            ourTerm = re.sub(r'<[^>]*>', '', matchCase(match.expand(replacement), match.group(0))).strip().rstrip('.,;:!?')
            key = f'TERM:{ourTerm}'
            if not ourTerm or self.lineNumber - self.lastExplainedLine.get(key, -9999) <= EXPLAIN_WINDOW: continue
            self.lastExplainedLine[key] = self.lineNumber
            self.counts[f'TERM\t{description} (added after their term)'] += 1
            theirTerm, endIndex, trailing = match.group(0), match.end(), ''
            if (punctuationMatch := re.search(r'([.,;:!?]+)(</\w+>)$', theirTerm)): # e.g., '<span class="divine-name">Lord,</span>'
                theirTerm, trailing = theirTerm[:punctuationMatch.start()] + punctuationMatch.group(2), punctuationMatch.group(1)
            elif (possessiveMatch := re.match(r"[’']s\b", text[endIndex:])): # e.g., 'the LORD’s (Yahweh’s)'
                theirTerm, endIndex, ourTerm = theirTerm + possessiveMatch.group(0), endIndex + len(possessiveMatch.group(0)), possessive(ourTerm)
            result.append(text[lastEnd:match.start()])
            result.append(f'{theirTerm} ({ourTerm}){trailing}')
            lastEnd = endIndex
        result.append(text[lastEnd:])
        return ''.join(result)

    def adaptNames(self, text:str) -> str:
        result, lastEnd = [], 0
        for match in self.namesRE.finditer(text):
            matchedName = match.group(1)
            traditionalName = matchedName if matchedName in self.names else self.lowerNames.get(matchedName.lower())
            if traditionalName is None or not matchedName[0].isupper(): continue
            if BOOK_REFERENCE_AFTER_RE.match(text, match.end()) \
            or (traditionalName in NUMBERED_BOOK_NAMES and BOOK_NUMBER_BEFORE_RE.search(text[:match.start()])):
                continue # It's a Bible book name in a reference, e.g., 'John 1:19' or '1 John'
            info = self.names[traditionalName]
            rvName = info['rvName']
            # Possessives: ’s, or a bare ’ after a name ending in 's' (but not a closing quote)
            possessiveMatch = POSSESSIVE_RE.match(text, match.end())
            if possessiveMatch and len(possessiveMatch.group(0)) == 1 \
            and (not matchedName.endswith('s') or text[max(0,match.start()-1):match.start()] in ('‘',"'")):
                possessiveMatch = None # Not a possessive, e.g., ‘Jesus’ is (a closing quote)
            endIndex = possessiveMatch.end() if possessiveMatch else match.end()
            # See if the source already follows the name with a parenthesised alternative that we'd change to the same RV name
            alreadyExplainedMatch, alternativeName = re.compile(r" \(([\w’' -]+)\)").match(text, endIndex), None
            if alreadyExplainedMatch:
                alternative = alreadyExplainedMatch.group(1)
                if alternative == rvName: # e.g., 'Syria (Aram)'
                    endIndex = alreadyExplainedMatch.end()
                elif alternative != traditionalName and self.names.get(alternative, {}).get('rvName') == rvName: # e.g., 'Ahasuerus (Xerxes)'
                    endIndex, alternativeName = alreadyExplainedMatch.end(), alternative
                else: alreadyExplainedMatch = None
            needsExplanation = info['explanation'] is not None \
                and (alreadyExplainedMatch or self.lineNumber - self.lastExplainedLine.get(rvName, -9999) > EXPLAIN_WINDOW)
            ourName = rvName + ('’s' if possessiveMatch else '') # OET-RV uses 'Paulos's' (not 'Paulos'')
            if self.theirNameFirst: # Keep their name, adding ours on first use, e.g., 'Samuel (Shmuel)'
                if not needsExplanation: continue # Leave their name unchanged
                self.lastExplainedLine[rvName] = self.lineNumber
                if alreadyExplainedMatch and not alternativeName: continue # They already give our name, e.g., 'Syria (Aram)'
                self.counts[f"NAME\t{traditionalName} → {traditionalName} ({rvName})"] += 1
                if alternativeName: # e.g., 'Ahasuerus (Xerxes)' -> 'Ahasuerus (Xerxes; Ahashverosh)'
                    rvText = f'{text[match.start():alreadyExplainedMatch.end()-1]}; {ourName})'
                else: rvText = f'{text[match.start():endIndex]} ({ourName})'
            else: # Change to our name, explaining it on first use, e.g., 'Shmuel (Samuel)'
                self.counts[f"NAME\t{traditionalName} → {rvName}"] += 1
                rvText = ourName
                if needsExplanation:
                    self.lastExplainedLine[rvName] = self.lineNumber
                    explanation = info['explanation']
                    if alternativeName: # e.g., 'Ahashverosh (Ahasuerus/Xerxes)' like the OET-RV
                        explanation = explanation.replace(traditionalName, f'{traditionalName}/{alternativeName}', 1)
                    if possessiveMatch: # e.g., 'Yeshua’s (Jesus’; Grk. Yesus’)'
                        explanation = '; '.join(possessive(part) for part in explanation.split('; '))
                    rvText = f'{rvText} ({explanation})'
            result.append(text[lastEnd:match.start()])
            result.append(rvText)
            lastEnd = endIndex
        result.append(text[lastEnd:])
        return ''.join(result)
    # end of NameAdapter.adaptNames
# end of NameAdapter class

############################################################################################################
# END OET-RV names code
############################################################################################################


def copyResources() -> None:
    """
    Delete any previous copies and re-copy the English and language-neutral resources.
    """
    for folderName, fileRE in COPIED_FOLDERS.items():
        sourcePath, destinationPath = UBS_FOLDER / folderName, THIS_FOLDER / folderName
        if not sourcePath.is_dir():
            sys.exit(f"ERROR: Can't find UBS folder '{sourcePath}'")
        if destinationPath.exists():
            assert destinationPath.resolve() != sourcePath.resolve()
            shutil.rmtree(destinationPath)
        numFiles = 0
        for sourceFilepath in sorted(sourcePath.rglob('*')):
            if sourceFilepath.is_file() and (fileRE is None or fileRE.search(sourceFilepath.name)):
                destinationFilepath = destinationPath / sourceFilepath.relative_to(sourcePath)
                destinationFilepath.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sourceFilepath, destinationFilepath)
                numFiles += 1
        print(f"  Copied {numFiles:,} files from '{sourcePath}'")
    for sourceName, destinationName in COPIED_TOP_LEVEL_FILES.items():
        shutil.copy2(UBS_FOLDER / sourceName, THIS_FOLDER / destinationName)
# end of copyResources


class UBSAdapter:
    """
    Wraps the NameAdapter to handle UBS {X:…} tokens.
    """
    def __init__(self, names, namesRE, counts:Counter) -> None:
        self.itemAdapter = NameAdapter(names, namesRE, counts)

    def newItem(self) -> None:
        self.itemAdapter.newItem()

    def adaptGloss(self, text:str) -> str:
        """
        Glosses are short headline labels (also used in indexes), so names in them are always explained,
            e.g., 'Yeshua (Jesus; Grk. Yesus)', independently of the explanations in the surrounding fields
            (which come before the glosses in the UBS data).
        """
        adapter = self.itemAdapter
        savedLastExplainedLine, adapter.lastExplainedLine = adapter.lastExplainedLine, {}
        try: return self.adaptField(text, countLine=False)
        finally: adapter.lastExplainedLine = savedLastExplainedLine

    def adaptField(self, text:str, countLine:bool=True) -> str:
        """
        Adapt one text field (counted as one 'line'), leaving UBS tokens unchanged
            except for the displayed name in {L:…<…>} lemma links.
        """
        adapter = self.itemAdapter
        if countLine: adapter.lineNumber += 1
        return adapter.adaptProtected(text, self.adaptUnprotectedField)

    def adaptUnprotectedField(self, text:str) -> str:
        pieces, lastEnd = [], 0
        for match in UBS_TOKEN_RE.finditer(text):
            pieces.append(self.adaptPlain(text[lastEnd:match.start()]))
            kind, payload = match.groups()
            linkMatch = re.fullmatch(r'([^<>]+)(<[^<>]+>)', payload) if kind == 'L' else None
            if linkMatch:
                displayText = self.adaptPlain(linkMatch.group(1))
                explainedMatch = EXPLAINED_RE.match(displayText)
                if explainedMatch: # Put the explanation after the link token
                    pieces.append(f'{{L:{explainedMatch.group(1)}{linkMatch.group(2)}}} {explainedMatch.group(2)}')
                else: pieces.append(f'{{L:{displayText}{linkMatch.group(2)}}}')
            else: pieces.append(match.group(0)) # Leave other tokens unchanged
            lastEnd = match.end()
        pieces.append(self.adaptPlain(text[lastEnd:]))
        return ''.join(pieces)

    def adaptPlain(self, text:str) -> str:
        adapter = self.itemAdapter
        return adapter.adaptNames(adapter.adaptTerminology(text, adapter.terminologyRules)) if text else text
# end of UBSAdapter class


def adaptJSONValue(value, adapter:UBSAdapter, adaptStrings:bool|str=False):
    """
    Recursively adapt the prose fields in a JSON value (modified in place where possible).
    """
    if isinstance(value, dict):
        if value.get('LanguageCode', 'en') != 'en': return value
        for key, subValue in value.items():
            value[key] = adaptJSONValue(subValue, adapter, adaptStrings=key if key in JSON_TEXT_KEYS else False)
        return value
    if isinstance(value, list):
        return [adaptJSONValue(item, adapter, adaptStrings) for item in value]
    if isinstance(value, str) and adaptStrings and value:
        return adapter.adaptGloss(value) if adaptStrings == 'Glosses' else adapter.adaptField(value)
    return value
# end of adaptJSONValue


def adaptJSONFile(filepath:Path, adapter:UBSAdapter) -> None:
    originalText = filepath.read_text(encoding='utf-8')
    data = json.loads(originalText)
    assert json.dumps(data, ensure_ascii=False, separators=(',',':')) == originalText, f"Unexpected JSON formatting in {filepath}"
    assert isinstance(data, list)
    for entry in data:
        adapter.newItem()
        adaptJSONValue(entry, adapter)
    filepath.write_text(json.dumps(data, ensure_ascii=False, separators=(',',':')), encoding='utf-8')
# end of adaptJSONFile


def adaptMarkupFile(filepath:Path, adapter:UBSAdapter, textElements:set[str]|None) -> None:
    """
    Adapt the text in an XML (or simple HTML) file, processing the whole file as a stream of tags and text
        (because some elements, e.g., REALIA paragraphs, continue over several lines).

    If textElements is None, all text is adapted (except in XML_SKIP_ELEMENTS, <style>, and <title>).
    """
    originalText = filepath.read_text(encoding='utf-8')
    newText = adapter.itemAdapter.adaptProtected(originalText, lambda text: adaptMarkupText(text, adapter, textElements))
    if newText != originalText:
        filepath.write_text(newText, encoding='utf-8')
# end of adaptMarkupFile


def adaptMarkupText(markupText:str, adapter:UBSAdapter, textElements:set[str]|None) -> str:
    pieces = re.split(r'(<[^>]*>)', markupText)
    stack:list[str] = []
    for ix, piece in enumerate(pieces):
        if piece.startswith('<'):
            tagMatch = re.match(r'<(/?)([\w:-]+)[^>]*?(/?)>$', piece)
            if not tagMatch: continue # e.g., <?xml…?> or <!--…-->
            isClosing, tagName, isEmpty = tagMatch.groups()
            if isEmpty or tagName.lower() in ('meta','br','img','hr','link'): continue
            if isClosing:
                if tagName in stack: # Pop back to the matching open tag
                    while stack.pop() != tagName: pass
            else:
                stack.append(tagName)
                if tagName in XML_ITEM_ELEMENTS: adapter.newItem()
        elif piece.strip() and not any(tag in XML_SKIP_ELEMENTS or tag.lower() in ('style','title','script') for tag in stack) \
        and (textElements is None or any(tag in textElements for tag in stack)):
            pieces[ix] = adapter.adaptGloss(piece) if stack[-1] == 'Gloss' else adapter.adaptField(piece)
    return ''.join(pieces)
# end of adaptMarkupText


def writeRouteTitles(adapter:UBSAdapter) -> int:
    """
    The route files have no text except their filenames (which we don't change because they're identifiers),
        so make a table with the OET-RV forms of their titles.
    """
    routesFolder = THIS_FOLDER / 'ubs-bible-routes'
    lines = ['Number\tOriginalTitle\tOETTitle\tGeoJSONFilename\tSVGFilename\n']
    for geojsonPath in sorted((routesFolder / 'GeoJsonRoutes').glob('*.geojson')):
        titleMatch = re.match(r'(\d+[a-z]?)(?:\.\s*(.*?)\.*)?$', geojsonPath.stem) # e.g., '107a. Rehoboam to Shechem', '112.Zerah…', '100'
        if not titleMatch:
            print(f"  WARNING: Unexpected route filename '{geojsonPath.name}'"); continue
        number, title = titleMatch.group(1), (titleMatch.group(2) or '').replace('_', '/')
        adapter.newItem()
        svgPath = routesFolder / 'SVG-Routes' / f'{geojsonPath.stem}.svg'
        lines.append(f"{number}\t{title}\t{adapter.adaptField(title)}\t{geojsonPath.name}\t{svgPath.name if svgPath.is_file() else ''}\n")
    (routesFolder / 'RouteTitles_OET-RV.tsv').write_text(''.join(lines), encoding='utf-8')
    return len(lines) - 1
# end of writeRouteTitles


def writeNotices(counts:Counter) -> None:
    enabledRules = [description for enabled, _regex, _replacement, description in TERMINOLOGY_RULES if enabled]
    notice = f"""# Adaptation notice

This repository contains works adapted from the [UBS open-licensed resources](https://github.com/ubsicap/ubs-open-license)
(© United Bible Societies; see `UBS_README.md` for the copyright details of each resource).
The original works are licensed under [CC BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/),
and these adaptations are released under the same licence.

Only the English resources are included here.
The image collections are not included (they're unchanged, so download them from the original repository).

## Changes made

These changes were made automatically by `adaptUBSResources.py` (version {PROGRAM_VERSION})
to match the [Open English Translation](https://github.com/Freely-Given-org/OpenEnglishTranslation--OET) Readers’ Version (OET-RV):

- Traditional forms of names were changed to the OET-RV forms from `OET-RV_names_table.tsv`
  in glosses, definitions, comments, domain descriptions, the flora/fauna/realia handbooks, and the HOTTP English remarks, suggestions, and literal translations.
  The traditional form is given in parentheses in glosses, and at the first use in each entry or article
  (and again after about {EXPLAIN_WINDOW_FIELDS} text fields), imitating the OET-RV,
  e.g., ‘Yeshua (Jesus; Grk. Yesus)’ then just ‘Yeshua’.
- Other wording changes:
""" + ''.join(f"  - {description}\n" for description in dict.fromkeys(enabledRules)) + """- `ubs-bible-routes/RouteTitles_OET-RV.tsv` was added, giving the OET-RV form of each route title
  (the route files themselves are unchanged).

Text quoted from other Bible versions (e.g., ‘“helmets” (RSV)’) was not changed, nor were
codes, references, Hebrew and Greek words, semantic domain labels, textual notes (which quote other translations),
the parallel passages database, and the MARBLE index were not changed.
See `adaptation_log.tsv` for the number of times each change was made.
"""
    (THIS_FOLDER / 'ADAPTATION_NOTICE.md').write_text(notice, encoding='utf-8')
    with open(THIS_FOLDER / 'adaptation_log.tsv', 'wt', encoding='utf-8') as logFile:
        logFile.write('Type\tChange\tCount\n')
        for key, count in sorted(counts.items(), key=lambda kc: (-kc[1], kc[0])):
            logFile.write(f'{key}\t{count}\n')
# end of writeNotices


def main() -> None:
    print(f"{PROGRAM_NAME} v{PROGRAM_VERSION} ({LAST_MODIFIED_DATE})")
    copyResources()
    names = loadNames(*harvestEsfmExplanations())
    namesRE = makeNamesRegex(names)
    counts = Counter()
    adapter = UBSAdapter(names, namesRE, counts)

    for filepath in sorted((THIS_FOLDER / 'dictionaries').rglob('*-en.JSON')):
        adaptJSONFile(filepath, adapter)
        print(f"  Adapted {filepath.relative_to(THIS_FOLDER)}")
    for filepath in sorted((THIS_FOLDER / 'dictionaries').rglob('*-en.XML')) \
                    + sorted((THIS_FOLDER / 'flora-fauna-realia').rglob('*_en.xml')) \
                    + [THIS_FOLDER / 'HOTTP' / 'HOTTP.XML']:
        adaptMarkupFile(filepath, adapter, XML_TEXT_ELEMENTS)
        print(f"  Adapted {filepath.relative_to(THIS_FOLDER)}")
    for filepath in sorted((THIS_FOLDER / 'HOTTP').glob('*-EN.HTML')):
        adaptMarkupFile(filepath, adapter, None)
        print(f"  Adapted {filepath.relative_to(THIS_FOLDER)}")
    print(f"  Wrote OET-RV titles for {writeRouteTitles(adapter)} routes")

    writeNotices(counts)
    numNameChanges = sum(count for key, count in counts.items() if key.startswith('NAME'))
    numTermChanges = sum(count for key, count in counts.items() if key.startswith('TERM'))
    print(f"  Made {numNameChanges:,} name changes and {numTermChanges:,} terminology changes (see adaptation_log.tsv)")
# end of main

if __name__ == '__main__':
    main()
# end of adaptUBSResources.py
