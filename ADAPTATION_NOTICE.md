# Adaptation notice

This repository contains works adapted from the [UBS open-licensed resources](https://github.com/ubsicap/ubs-open-license)
(© United Bible Societies; see `UBS_README.md` for the copyright details of each resource).
The original works are licensed under [CC BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/),
and these adaptations are released under the same licence.

Only the English resources are included here.
The image collections are not included (they're unchanged, so download them from the original repository).

## Changes made

These changes were made automatically by `adaptUBSResources.py` (version 0.12)
to match the [Open English Translation](https://github.com/Freely-Given-org/OpenEnglishTranslation--OET) Readers’ Version (OET-RV):

- Traditional forms of names were changed to the OET-RV forms from `OET-RV_names_table.tsv`
  in glosses, definitions, comments, domain descriptions, the flora/fauna/realia handbooks, and the HOTTP English remarks, suggestions, and literal translations.
  The traditional form is given in parentheses in glosses, and at the first use in each entry or article
  (and again after about 10 text fields), imitating the OET-RV,
  e.g., ‘Yeshua (Jesus; Grk. Yesus)’ then just ‘Yeshua’.
- Other wording changes:
  - LORD → Yahweh
  - John the Baptist → John the immerser
- `ubs-bible-routes/RouteTitles_OET-RV.tsv` was added, giving the OET-RV form of each route title
  (the route files themselves are unchanged).

Codes, references, Hebrew and Greek words, semantic domain labels, textual notes (which quote other translations),
the parallel passages database, and the MARBLE index were not changed.
See `adaptation_log.tsv` for the number of times each change was made.
