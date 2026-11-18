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

This reuses the name-handling code from
    OpenBibleData/datasets/Tyndale/OET_TyndaleOpenResources/adaptTyndaleResources.py
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
        In UBS link tokens like '{L:Abijah<SDBH:אֲבִיָּה>}' only the displayed name is changed,
            and any explanation goes after the token, e.g., '{L:Aviyah<SDBH:אֲבִיָּה>} (Abijah)'.
    3/ Write a table of OET-RV forms of the Bible route titles (the route filenames are left unchanged).
    4/ Write ADAPTATION_NOTICE.md (required by CC BY-SA) and adaptation_log.tsv.

CHANGELOG:
    2026-11-19 First version
"""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys


LAST_MODIFIED_DATE = '2026-11-19' # by RJH
PROGRAM_NAME = "Adapt UBS open-licensed resources for OET-RV"
PROGRAM_VERSION = '0.10'

THIS_FOLDER = Path(__file__).resolve().parent
UBS_FOLDER = THIS_FOLDER.parent # The original UBS repo
TYNDALE_ADAPTER_FILEPATH = Path('/srv/FreelyGiven/OpenBibleData/datasets/Tyndale/OET_TyndaleOpenResources/adaptTyndaleResources.py')

EXPLAIN_WINDOW_FIELDS = 10 # Re-explain a name if it was last explained more than this many text fields earlier (in the same entry)

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
    'Remark', 'Literal', # HOTTP (but not Remark-FR or LiteralFR)
    }
XML_SKIP_ELEMENTS = {'s', 'l', 'Reference', 'Lemma', 'Transliteration', 'FileName', 'Copyright', 'Label', 'LanguageCode'}
XML_ITEM_ELEMENTS = {'Lexicon_Entry', 'SemanticDomain', 'ThemLex_Entry', 'HOTTP_Entry'} # Explanations restart in each of these

UBS_TOKEN_RE = re.compile(r'\{([A-Z]):([^{}]*)\}') # e.g., {S:04600100000000} or {L:Abijah<SDBH:אֲבִיָּה>}
EXPLAINED_RE = re.compile(r'^(.*\S) (\([^()]+\))$') # e.g., 'Aviyah (Abijah)'


def loadTyndaleAdapterModule():
    """
    Import the Tyndale adaptation script as a module (so we share its names handling).
    """
    spec = importlib.util.spec_from_file_location('adaptTyndaleResources', TYNDALE_ADAPTER_FILEPATH)
    if spec is None or not TYNDALE_ADAPTER_FILEPATH.is_file():
        sys.exit(f"ERROR: Can't find {TYNDALE_ADAPTER_FILEPATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
# end of loadTyndaleAdapterModule


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
    Wraps the Tyndale ItemAdapter to handle UBS {X:…} tokens.
    """
    def __init__(self, tyndaleModule, names, namesRE, counts:Counter) -> None:
        self.itemAdapter = tyndaleModule.ItemAdapter(names, namesRE, 'UBS', counts)

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
    pieces = re.split(r'(<[^>]*>)', originalText)
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
    newText = ''.join(pieces)
    if newText != originalText:
        filepath.write_text(newText, encoding='utf-8')
# end of adaptMarkupFile


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


def writeNotices(tyndaleModule, counts:Counter) -> None:
    enabledRules = [description for enabled, scopes, _regex, _replacement, description in tyndaleModule.TERMINOLOGY_RULES
                        if enabled and 'UBS' in scopes and not description.startswith('(')]
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
  in glosses, definitions, comments, domain descriptions, the flora/fauna/realia handbooks, and the HOTTP English remarks and literal translations.
  The traditional form is given in parentheses in glosses, and at the first use in each entry or article
  (and again after about {EXPLAIN_WINDOW_FIELDS} text fields), imitating the OET-RV,
  e.g., ‘Yeshua (Jesus; Grk. Yesus)’ then just ‘Yeshua’.
- Other wording changes:
""" + ''.join(f"  - {description}\n" for description in dict.fromkeys(enabledRules)) + """- `ubs-bible-routes/RouteTitles_OET-RV.tsv` was added, giving the OET-RV form of each route title
  (the route files themselves are unchanged).

Codes, references, Hebrew and Greek words, semantic domain labels, textual notes (which quote other translations),
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
    tyndaleModule = loadTyndaleAdapterModule()
    tyndaleModule.EXPLAIN_WINDOW_LINES = EXPLAIN_WINDOW_FIELDS
    copyResources()
    names = tyndaleModule.loadNames(*tyndaleModule.harvestEsfmExplanations())
    namesRE = tyndaleModule.makeNamesRegex(names)
    counts = Counter()
    adapter = UBSAdapter(tyndaleModule, names, namesRE, counts)

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

    writeNotices(tyndaleModule, counts)
    numNameChanges = sum(count for key, count in counts.items() if key.startswith('NAME'))
    numTermChanges = sum(count for key, count in counts.items() if key.startswith('TERM'))
    print(f"  Made {numNameChanges:,} name changes and {numTermChanges:,} terminology changes (see adaptation_log.tsv)")
# end of main

if __name__ == '__main__':
    main()
# end of adaptUBSResources.py
