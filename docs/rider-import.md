# Importing riders from a spreadsheet

Not every rider list comes from BikeReg. A venue might take walk-up entries on paper, keep a club list in a spreadsheet, or get a list from another registration site. This page describes the CSV file MadTracker can import, so a list from anywhere can come in the same way a BikeReg export does.

There's no separate import for this. The file is read by **Import from BikeReg...** in **File** -> **Edit Riders...**, which only looks for the column names BikeReg uses. A file with those columns imports like a BikeReg export, with the same preview and the same matching against riders already on file.

## The template

Start from this file: [rider-import-template.csv](rider-import-template.csv). It has every column the import reads and six invented riders showing the common cases. Delete the example rows, then fill in your own.

```csv
Last Name,First Name,Bib,USAC License,UCI Code,Age on 12/31/2026,Category
Halloran,Bridget,12,412233,,34,Cat 1/2/3 (Group A)
Okafor,Desmond,,587120,10088812345,27,Cat 1/2/3 (Group A)
Varga,Petra,31,,,45,Masters 40+
Lindqvist,Jonas,,INTL-SWE,10009876543,22,Cat 4/5 (Group B)
Moreau,Celine,,,,14,Juniors (14 and under)
Teague,Ronan,,,,,
```

The last row is the smallest a row can be: a name and nothing else.

## Columns

The first row must hold the column names, spelled exactly as below (capitals and spaces included). The columns can be in any order. Any other column is ignored, so a spreadsheet with extra columns (eg: phone, email, team) doesn't need to be trimmed first.

- Last Name: the column is required. A row may leave it blank if First Name is filled in.
- First Name: the column is required. A row with both names blank is skipped.
- Bib: optional. A whole number from 1 to 9999. Leave it blank if bibs aren't handed out yet; they can be typed in the import preview or on the roster later.
- USAC License: optional. Digits only; leading zeros are dropped, so 0412233 and 412233 are the same license. Anything that isn't a number (eg: "INTL-SWE" or "PENDING") is read as no license, and the preview says why.
- UCI Code: optional. The rider's 11-digit UCI ID. This is the usual id for a foreign rider without a USAC license.
- Age on 12/31/2026: optional. The rider's racing age, which is their age on December 31 of the season. Change the year in the column name to the season's year, as MadTracker works out the birth year from it (2026 minus 34 is 1992).
- Category: optional. This becomes the rider's group on the event's roster.

Only the two name columns are required. But a USAC License or UCI Code is what lets the next import find the same rider again with certainty, so include them when you have them. Without one, a returning rider is matched by name, and a name alone sometimes needs a decision in the preview.

## How Category becomes a group

The group is taken from the Category text like this:

- No parentheses: the whole text is the group. "Masters 40+" is group "Masters 40+".
- Text in the last parentheses: that text is the group. "Cat 1/2/3 (Group A)" is group "Group A".
- An age note in the last parentheses (it starts with a digit): the text before it is the group. "Juniors (14 and under)" is group "Juniors".

If you're writing the file by hand, the plainest choice is to put the group name alone in Category, eg: "Group A".

## Saving the file

Save it as CSV. In Excel that's **File** -> **Save As** with "CSV UTF-8 (Comma delimited)", which keeps accented names intact. A semicolon- or tab-separated file also works, as does a plain Windows "CSV (Comma delimited)" file. An Excel workbook (.xlsx) does not; save it as CSV first.

Watch the UCI Code column in Excel. Excel treats an 11-digit number as a number, so it can drop a leading zero or show it as 1.00888E+10. Format that column as Text before typing or pasting the ids in.

## Importing

1. **File** -> **Edit Riders...**, then **Import from BikeReg...**, and pick the file.
2. Set **Put on the roster of** to the event the riders go on, or **No Event** to add them to the rider list only.
3. Check the preview, then click **Import**.

The preview, its statuses, and how a row is matched to a rider on file are covered in the program's help, under Getting Started.
