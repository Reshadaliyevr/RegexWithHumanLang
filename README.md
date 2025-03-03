# HumanReadableRegex

A simple command-line tool to perform text searches using a human-readable DSL (Domain-Specific Language).

## How to Use

Run the script using Python:

```sh
python3 main.py -i
```

Or make it executable and run:

```sh
./main.py
```

For more information you can run:
```sh
python main.py --help
```

### Example Usage

```sh
Enter your search query (in our DSL):
> FIND LINES THAT START WITH "abc" AND ENDS WITH "xyz" IGNORE CASE
Enter filename to search (or leave blank for stdin):
> myfile.txt
```

This will print all lines in `myfile.txt` that start with `abc` and end with `xyz` (case-insensitive).

---

## Commands

- **FIND**: Print each matching line or word.
- **COUNT**: Report the number of matching lines/words.
- **EXTRACT**: Use a capture pattern to extract parts of the matched lines/words.

## Targets

- **LINES** (default): Treat each line as a separate unit.
- **WORDS**: Split each line into words and evaluate each word separately.

## Conditions (Chainable)

- `STARTS WITH "some text"`
- `ENDS WITH "some text"`
- `CONTAINS "some text"`
- `REGEX "some regex"`
- `AT LEAST X TIMES "some text"`
- `AT MOST X TIMES "some text"`
- `EXACTLY X TIMES "some text"`
- `BETWEEN X AND Y TIMES "some text"`

Combine conditions with:

- **AND / OR** – Logical operators.
- **BUT NOT / EXCEPT** – Exclude specific patterns.

## Modifiers

- **IGNORE CASE** – Case-insensitive search.
- **MULTILINE** – `^` and `$` match line boundaries within a text block.
- **DOTALL** – `.` matches newline characters.
- **WHOLE WORD** – Wraps patterns with `\b...\b` (basic word boundary matching).

## Examples

```sh
COUNT LINES THAT CONTAIN "error" OR CONTAIN "failed" IGNORE CASE
FIND WORDS THAT EXACTLY 2 TIMES "abc" BUT NOT "xyz"
EXTRACT REGEX "ID:(\d+)" FROM LINES THAT CONTAINS "ID:"
FIND LINES THAT STARTS WITH "abc" AND ENDS WITH "xyz" WHOLE WORD DOTALL
```

