#!/usr/bin/env python3
import sys
import re
from collections import Counter

def parse_query(query: str) -> dict:
    """
    Parse a user query in our DSL and return a dictionary describing:
      - command (FIND, COUNT, EXTRACT)
      - target (LINES, WORDS)
      - conditions (list of dicts: {type, value, quantifier, logic_connector, exclude, ...})
      - modifiers (ignore_case, multiline, dotall, whole_word)
      - extraction_pattern (only if command=EXTRACT)
    """

    # Convert to uppercase for keyword detection, but keep original for capturing phrases
    q_upper = query.upper()

    # Default structure
    result = {
        "command": None,            # FIND | COUNT | EXTRACT
        "target": "LINES",          # LINES | WORDS
        "conditions": [],           # each condition is a dict
        "modifiers": {
            "ignore_case": False,
            "multiline": False,
            "dotall": False,
            "whole_word": False
        },
        "extraction_pattern": None  # only used if command=EXTRACT
    }

    # 1. Detect command
    if "FIND" in q_upper:
        result["command"] = "FIND"
    if "COUNT" in q_upper:
        # If both FIND and COUNT appear, we can either prioritize the first found
        # or do something else. We'll just override if we see COUNT after FIND.
        result["command"] = "COUNT"
    if "EXTRACT" in q_upper:
        result["command"] = "EXTRACT"

    # If no command found, default to FIND
    if not result["command"]:
        result["command"] = "FIND"

    # 2. Detect target
    if "WORDS" in q_upper:
        result["target"] = "WORDS"
    # default is LINES

    # 3. Detect modifiers
    if "IGNORE CASE" in q_upper:
        result["modifiers"]["ignore_case"] = True
    if "MULTILINE" in q_upper:
        result["modifiers"]["multiline"] = True
    if "DOTALL" in q_upper:
        result["modifiers"]["dotall"] = True
    if "WHOLE WORD" in q_upper:
        result["modifiers"]["whole_word"] = True

    # 4. If command=EXTRACT, detect the pattern after "EXTRACT"
    #    e.g. "EXTRACT '(\d+)' FROM LINES THAT CONTAIN 'ID'"
    #    We'll do a naive approach: look for EXTRACT "some pattern" or EXTRACT REGEX "some pattern"
    if result["command"] == "EXTRACT":
        # find text after "EXTRACT"
        m = re.search(r'EXTRACT\s+"([^"]+)"', query, re.IGNORECASE)
        if m:
            result["extraction_pattern"] = m.group(1)
        else:
            # also check EXTRACT REGEX "..."
            m2 = re.search(r'EXTRACT\s+REGEX\s+"([^"]+)"', query, re.IGNORECASE)
            if m2:
                result["extraction_pattern"] = m2.group(1)

    # 5. Parse conditions
    #    We'll look for patterns like:
    #      - STARTS WITH "..."
    #      - ENDS WITH "..."
    #      - CONTAINS "..."
    #      - REGEX "..."
    #      - AT LEAST X TIMES "..."
    #      - EXACTLY X TIMES "..."
    #      - AT MOST X TIMES "..."
    #      - BETWEEN X AND Y TIMES "..."
    #    Also handle logic connectors (AND, OR) and excludes (BUT NOT, EXCEPT).

    # We'll define a small internal parser: we’ll split the query by recognized keywords,
    # then we’ll re-find them in context. In a real DSL, you'd do a more robust parse.
    # For demonstration, let's do a big search for each known pattern.

    # We gather conditions in a list. Each condition is a dict with:
    # {
    #   "type": "start"|"end"|"contains"|"regex"|"repeat",
    #   "text": "abc" or a pattern,
    #   "quantifier": "{2,}" or None,
    #   "logic": "AND"|"OR",
    #   "exclude": False|True
    # }

    # We'll do multiple passes or a single pass with multiple regex searches, whichever is simpler.

    # A. Find all quoted texts
    quoted_texts = re.findall(r'"([^"]+)"', query)

    # B. We'll scan for known phrases
    # We'll keep a simple pointer to the quoted_texts as we find patterns
    # We also track logic connectors (AND, OR) and excludes
    # This is a naive approach but workable for demonstration.

    # We'll break the query into segments by these keywords to find them in sequence.
    tokens = re.split(r'(\bAND\b|\bOR\b|\bBUT NOT\b|\bEXCEPT\b)', query, flags=re.IGNORECASE)
    # tokens might look like ["FIND LINES THAT START WITH ", "AND", " ENDS WITH ", ...]

    # We'll define some helper regex patterns to detect the condition type
    re_start = re.compile(r'\bSTARTS WITH\b', re.IGNORECASE)
    re_end = re.compile(r'\bENDS WITH\b', re.IGNORECASE)
    re_contains = re.compile(r'\bCONTAINS\b', re.IGNORECASE)
    re_regex = re.compile(r'\bREGEX\b', re.IGNORECASE)
    re_at_least = re.compile(r'\bAT\s+LEAST\s+(\d+)\s+TIMES?\b', re.IGNORECASE)
    re_at_most = re.compile(r'\bAT\s+MOST\s+(\d+)\s+TIMES?\b', re.IGNORECASE)
    re_exactly = re.compile(r'\bEXACTLY\s+(\d+)\s+TIMES?\b', re.IGNORECASE)
    re_between = re.compile(r'\bBETWEEN\s+(\d+)\s+AND\s+(\d+)\s+TIMES?\b', re.IGNORECASE)

    logic_for_next_condition = "AND"  # default

    # We'll parse each token, looking for a recognized condition phrase.
    # Then we try to assign the next quoted text to that condition.
    # We do a pointer to the quoted_texts we haven't used yet.
    quoted_idx = 0

    def next_quoted_text():
        nonlocal quoted_idx
        if quoted_idx < len(quoted_texts):
            txt = quoted_texts[quoted_idx]
            quoted_idx += 1
            return txt
        return None

    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Check for logic connectors
        if re.match(r'\bAND\b', token, re.IGNORECASE):
            logic_for_next_condition = "AND"
            i += 1
            continue
        if re.match(r'\bOR\b', token, re.IGNORECASE):
            logic_for_next_condition = "OR"
            i += 1
            continue
        if re.match(r'\bBUT NOT\b', token, re.IGNORECASE) or re.match(r'\bEXCEPT\b', token, re.IGNORECASE):
            logic_for_next_condition = "AND"
            # We'll treat this as an exclude flag for the next condition(s).
            # We'll parse the next tokens to see what the condition is.
            i += 1
            # The next condition we parse, we'll set exclude=True
            # But we still need to see what the user typed next. We'll do a small parse:
            # We'll look at the next token to see if it matches a known pattern or if we just
            # treat the next quoted text as an exclude "contains".
            # Let's do a quick peek:
            if i < len(tokens):
                sub = tokens[i]
                cond_type = None
                q_text = None
                quantifier = None

                # Detect if the next segment says "contains" or "regex" etc.
                if re_start.search(sub):
                    cond_type = "start"
                    q_text = next_quoted_text()
                elif re_end.search(sub):
                    cond_type = "end"
                    q_text = next_quoted_text()
                elif re_contains.search(sub):
                    cond_type = "contains"
                    q_text = next_quoted_text()
                elif re_regex.search(sub):
                    cond_type = "regex"
                    q_text = next_quoted_text()
                else:
                    # Possibly a quantifier pattern
                    match_at_least = re_at_least.search(sub)
                    match_at_most = re_at_most.search(sub)
                    match_exactly_ = re_exactly.search(sub)
                    match_between_ = re_between.search(sub)

                    if match_at_least:
                        cond_type = "repeat"
                        min_n = match_at_least.group(1)
                        quantifier = f"{{{min_n},}}"
                        q_text = next_quoted_text()
                    elif match_at_most:
                        cond_type = "repeat"
                        max_n = match_at_most.group(1)
                        quantifier = f"{{0,{max_n}}}"
                        q_text = next_quoted_text()
                    elif match_exactly_:
                        cond_type = "repeat"
                        exact_n = match_exactly_.group(1)
                        quantifier = f"{{{exact_n}}}"
                        q_text = next_quoted_text()
                    elif match_between_:
                        cond_type = "repeat"
                        low_n = match_between_.group(1)
                        high_n = match_between_.group(2)
                        quantifier = f"{{{low_n},{high_n}}}"
                        q_text = next_quoted_text()
                    else:
                        # If none of these recognized, we assume "contains"
                        cond_type = "contains"
                        q_text = next_quoted_text()

                if cond_type and q_text:
                    condition = {
                        "type": cond_type,
                        "text": q_text,
                        "quantifier": quantifier,
                        "logic": logic_for_next_condition,
                        "exclude": True
                    }
                    result["conditions"].append(condition)
                    i += 1
                else:
                    i += 1
            continue

        # If the token itself might have a condition
        cond_type = None
        q_text = None
        quantifier = None

        # Detect condition
        if re_start.search(token):
            cond_type = "start"
            q_text = next_quoted_text()
        elif re_end.search(token):
            cond_type = "end"
            q_text = next_quoted_text()
        elif re_contains.search(token):
            cond_type = "contains"
            q_text = next_quoted_text()
        elif re_regex.search(token):
            cond_type = "regex"
            q_text = next_quoted_text()
        else:
            # Possibly a quantifier pattern
            match_at_least = re_at_least.search(token)
            match_at_most = re_at_most.search(token)
            match_exactly_ = re_exactly.search(token)
            match_between_ = re_between.search(token)

            if match_at_least:
                cond_type = "repeat"
                min_n = match_at_least.group(1)
                quantifier = f"{{{min_n},}}"
                q_text = next_quoted_text()
            elif match_at_most:
                cond_type = "repeat"
                max_n = match_at_most.group(1)
                quantifier = f"{{0,{max_n}}}"
                q_text = next_quoted_text()
            elif match_exactly_:
                cond_type = "repeat"
                exact_n = match_exactly_.group(1)
                quantifier = f"{{{exact_n}}}"
                q_text = next_quoted_text()
            elif match_between_:
                cond_type = "repeat"
                low_n = match_between_.group(1)
                high_n = match_between_.group(2)
                quantifier = f"{{{low_n},{high_n}}}"
                q_text = next_quoted_text()

        if cond_type and q_text:
            condition = {
                "type": cond_type,
                "text": q_text,
                "quantifier": quantifier,
                "logic": logic_for_next_condition,
                "exclude": False
            }
            result["conditions"].append(condition)

        i += 1

    return result

def build_regex_from_condition(cond: dict, modifiers: dict) -> str:
    """
    Build a regex snippet from a single condition dictionary.
    We'll combine these later with AND/OR logic.
    Condition fields:
      - type: "start", "end", "contains", "regex", "repeat"
      - text: the string
      - quantifier: e.g. "{2,}" or None
      - exclude: bool
      - logic: "AND" or "OR"
    """

    text_esc = re.escape(cond["text"])

    # If WHOLE WORD is on, we might wrap the text in word boundaries \b
    # But let's do that in the final assembly, or do it here if simpler.
    # For "start" => ^text
    # For "end" => text$
    # For "contains" => text
    # For "regex" => user-provided pattern
    # For "repeat" => (?:text){quant}

    if cond["type"] == "start":
        return f"^{text_esc}"
    elif cond["type"] == "end":
        return f"{text_esc}$"
    elif cond["type"] == "contains":
        return text_esc
    elif cond["type"] == "regex":
        # We do not escape user text here, since it's already a raw pattern
        return cond["text"]
    elif cond["type"] == "repeat":
        # e.g. (?:text){2,}
        quant = cond["quantifier"] if cond["quantifier"] else "{1,}"
        return f"(?:{text_esc}){quant}"
    else:
        return text_esc  # fallback

def combine_conditions(conditions, modifiers):
    """
    Combine multiple conditions into a single regex pattern using lookaheads for AND,
    alternation for OR, etc. We also handle excludes separately in the final matching step.
    We'll build two patterns:
      1) 'include_pattern' - everything that must appear
      2) 'exclude_patterns' - each condition that must NOT appear
    Because mixing excludes with lookaheads can get complicated, we'll do a 2-phase approach:
      - Phase 1: check if line/word matches 'include_pattern'
      - Phase 2: check that none of the 'exclude_patterns' match
    """
    include_parts_and = []  # for AND logic
    include_parts_or = []   # for OR logic

    # We'll group conditions by logic connector. A naive approach:
    # If we see "OR", we group them separately from "AND."
    # A more robust approach would parse parentheses, but let's keep it simpler.
    # We'll do something like: all AND conditions => one big lookahead chain,
    # all OR conditions => one big alternation. But if user typed "AND" then "OR" then "AND" again,
    # it gets tricky. We'll approximate.

    exclude_patterns = []

    # We'll do a pass: if a condition has exclude=True, store in exclude_patterns.
    # If logic=OR => store in or list, else in and list
    # Then we'll combine them.

    for cond in conditions:
        if cond["exclude"]:
            # build the pattern for cond
            pat = build_regex_from_condition(cond, modifiers)
            exclude_patterns.append(pat)
        else:
            # build the pattern
            pat = build_regex_from_condition(cond, modifiers)
            if cond["logic"] == "OR":
                include_parts_or.append(pat)
            else:
                include_parts_and.append(pat)

    # Now build a single pattern for includes
    # For the AND part, we do a chain of lookaheads: (?=.*p1)(?=.*p2) ...
    # Then we optionally append the OR pattern as an alternative if we have both sets.
    # If we have only OR patterns, we just do alternation. If we have both AND and OR, we do:
    #   "((?=.*p1)(?=.*p2).* ) | (p3|p4)"
    # This is a bit naive but workable for a simple DSL.

    if include_parts_and and include_parts_or:
        # build the AND chain
        and_chain = "".join(f"(?=.*{p})" for p in include_parts_and) + ".*"
        # build the OR group
        or_group = "|".join(include_parts_or)
        include_pattern = f"(?:({and_chain})|({or_group}))"
    elif include_parts_and:
        # only AND
        and_chain = "".join(f"(?=.*{p})" for p in include_parts_and) + ".*"
        include_pattern = and_chain
    elif include_parts_or:
        # only OR
        or_group = "|".join(include_parts_or)
        include_pattern = f"(?:{or_group})"
    else:
        # no include conditions => match anything
        include_pattern = ".*"

    return include_pattern, exclude_patterns

def matches_item(item: str, include_pattern: str, exclude_patterns: list, modifiers: dict) -> bool:
    """
    Return True if `item` satisfies the include_pattern and does NOT match any exclude_pattern.
    """
    flags = 0
    if modifiers["ignore_case"]:
        flags |= re.IGNORECASE
    if modifiers["multiline"]:
        flags |= re.MULTILINE
    if modifiers["dotall"]:
        flags |= re.DOTALL

    # Check include
    if not re.search(include_pattern, item, flags=flags):
        return False

    # Check excludes
    for epat in exclude_patterns:
        if re.search(epat, item, flags=flags):
            return False

    return True

def process_lines(filename: str, query_data: dict):
    """
    The main logic for reading lines or words, matching conditions, printing or counting or extracting.
    """
    command = query_data["command"]
    target = query_data["target"]
    conditions = query_data["conditions"]
    modifiers = query_data["modifiers"]
    extraction_pattern = query_data["extraction_pattern"]

    # Build the big patterns from conditions
    include_pattern, exclude_patterns = combine_conditions(conditions, modifiers)

    # If WHOLE WORD is set, we might wrap the entire pattern in \b ... \b
    # or each sub-part. A simpler approach: we do a second pass at runtime:
    # We'll do a separate function if needed. For now, let's do the naive approach:
    if modifiers["whole_word"]:
        # We'll anchor the entire search in \b ... \b by rewriting the include pattern
        # and each exclude pattern. This is naive, but an example:
        include_pattern = rf"\b(?:{include_pattern})\b"
        exclude_patterns = [rf"\b(?:{p})\b" for p in exclude_patterns]

    # Decide how to open file
    if filename.strip():
        fh = open(filename, "r", encoding="utf-8", errors="ignore")
    else:
        fh = sys.stdin

    matched_count = 0
    matched_items = []  # lines or words that matched

    # For EXTRACT command, we store extracted results
    extracted_results = []

    for line in fh:
        line_stripped = line.rstrip("\n")

        if target == "WORDS":
            # Split line into words
            words = line_stripped.split()
            # For each word, check match
            for w in words:
                if matches_item(w, include_pattern, exclude_patterns, modifiers):
                    matched_count += 1
                    matched_items.append(w if command != "EXTRACT" else line)  # store entire line if extracting
                    if command == "EXTRACT" and extraction_pattern:
                        # do extraction
                        ex_list = re.findall(extraction_pattern, w, flags=(re.IGNORECASE if modifiers["ignore_case"] else 0))
                        extracted_results.extend(ex_list)
        else:
            # LINES
            if matches_item(line_stripped, include_pattern, exclude_patterns, modifiers):
                matched_count += 1
                matched_items.append(line)
                if command == "EXTRACT" and extraction_pattern:
                    ex_list = re.findall(extraction_pattern, line_stripped, flags=(re.IGNORECASE if modifiers["ignore_case"] else 0))
                    extracted_results.extend(ex_list)

    if filename.strip():
        fh.close()

    # Output results based on command
    if command == "COUNT":
        print(f"Matched {target.lower()}: {matched_count}")
    elif command == "FIND":
        for m in matched_items:
            # If target=WORDS, m is the word; if target=LINES, m is the entire line
            print(m, end="" if target == "LINES" else "\n")
    elif command == "EXTRACT":
        if extraction_pattern:
            for ex in extracted_results:
                if isinstance(ex, tuple):
                    # if user used groups in the pattern, we get a tuple
                    print(" ".join(ex))
                else:
                    print(ex)
        else:
            # if no extraction pattern, just print matched lines or words
            for m in matched_items:
                print(m, end="" if target == "LINES" else "\n")

def main():
    print("Enter your search query (in our DSL):")
    query = input("> ")
    print("Enter filename to search (or leave blank for stdin):")
    filename = input("> ")

    # 1) Parse the query into a structured form
    query_data = parse_query(query)

    # 2) Process lines (or words) from the file with the query data
    process_lines(filename, query_data)

if __name__ == "__main__":
    main()
