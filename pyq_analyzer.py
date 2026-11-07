import re, glob
import pandas as pd

NOISE = re.compile(r'QP\d+|Printed Page|Subject Code|Roll No|^BTECH|^\(SEM|^DATA ?BASE MANAGEMENT|'
                   r'^TIME:|^Note:|^\d+ \| Page|^Q ?no\.|^Leve?l?$|^l$', re.I)
SEC = re.compile(r'SECTION\s+([ABC])')
QHDR = re.compile(r'(\d)\.\s+Attempt')
PART = re.compile(r'^(?:\(([a-j])\)|([a-j])\.)\s*(.*)$')

# the CO (course outcome = unit) sits at the end of a question; each paper format writes it differently
# format: (pattern that ends a question, how to read it, what to strip from the text)
MARK = {
 'co_k':     (re.compile(r'^(.*?)\s*\b([1-5])\s+K([1-6])\s*$'),   lambda m: (None, int(m.group(2)), 'K' + m.group(3)), re.compile(r'\s*\b[1-5]\s+K[1-6]\s*$')),
 'co_label': (re.compile(r'^(.*?)\s*\b(\d{1,2})\s+CO([1-5])\s*$'), lambda m: (int(m.group(2)), int(m.group(3)), ''),    re.compile(r'\s*\b\d{1,2}\s+CO[1-5]\s*$')),
 'marks_co': (re.compile(r'^(.*?)\s*\b(2|10)\s+([1-5])\s*$'),      lambda m: (int(m.group(2)), int(m.group(3)), ''),    re.compile(r'\s*\b(?:2|10)\s+[1-5]\s*$')),
}

def detect_format(t):
    if re.search(r'\bCO[1-5]\s*$', t, re.M): return 'co_label'
    if re.search(r'Marks\s+CO', t): return 'marks_co'
    if re.search(r'\b[1-5]\s+K[1-6]\s*$', t, re.M): return 'co_k'
    return 'none'

def pdf_to_text(path):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)

def parse_paper(text):
    fmt = detect_format(text)
    y = re.search(r'EXAMINATION\s+(\d{4}-\d{2})', text); year = y.group(1) if y else ''
    tm = re.search(r'(?:M\.MARKS|Total Marks):\s*(\d+)', text); total = int(tm.group(1)) if tm else None
    rows, section, qno, exp, hdr, cur = [], '', 0, 'a', None, None
    def flush():
        nonlocal cur
        if cur: rows.append(cur)
        cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or NOISE.search(line): continue
        if (m := SEC.match(line)): flush(); section = m.group(1); continue
        if (m := QHDR.match(line)):
            flush(); qno = int(m.group(1)); exp = 'a'
            h = re.search(r'(\d+)\s*[x×]\s*(\d+)\s*=\s*\d+', line)
            hdr = max(int(h.group(1)), int(h.group(2))) if h else None
            continue
        m = PART.match(line); letter = (m.group(1) or m.group(2)) if m else None
        if m and letter == exp:                       # the next expected part letter starts a new question part
            flush(); exp = chr(ord(exp) + 1); body = m.group(3)
            cur = dict(year=year, total_marks=total, section=section, q_no=qno, part=letter, text=body,
                       marks=2 if section == 'A' else (hdr or 10), co=None, level='', closed=False)
        elif cur is not None and not cur['closed']:  # otherwise the line continues the current question
            cur['text'] += ' ' + line; body = line
        else:
            continue
        if fmt != 'none' and (mm := MARK[fmt][0].match(body)):
            marks, co, lvl = MARK[fmt][1](mm)
            cur['text'] = MARK[fmt][2].sub('', cur['text']).strip()
            cur['co'], cur['level'], cur['closed'] = co, lvl, True
            if marks and section != 'A': cur['marks'] = marks
    flush()
    df = pd.DataFrame(rows).drop(columns='closed')
    df['co_source'] = df['co'].apply(lambda c: 'paper' if pd.notna(c) else '')
    if fmt != 'none':   # a missing CO (cut-off text) is copied from the other part of the same question
        df['co'] = df.groupby(['section', 'q_no'])['co'].transform(lambda s: s.fillna(s.dropna().iloc[0] if s.notna().any() else None))
        df.loc[(df.co_source == '') & df.co.notna(), 'co_source'] = 'sibling'
    return df

# topic -> (keyword pattern, unit)
TOPICS = {
 "File system vs DBMS": (r"file system", 1),
 "Data independence": (r"data independen", 1),
 "Schema architecture / data abstraction": (r"three[- ]level|three[- ]schema|data abstraction|levels? of abstraction|schemas architecture", 1),
 "Overall structure of DBMS": (r"architecture of dbms|database architecture|overall structure", 1),
 "Data models": (r"types of data models", 1),
 "DDL / DML (procedural DML)": (r"procedural dml|\bddl\b|currency with respect", 1),
 "DBA role and functions": (r"database administrator|functions of dba", 1),
 "ER diagram and components": (r"\ber diagram|e-r schema", 1),
 "Strong/weak entity, recursive relationship": (r"weak entity|recursive relationship", 1),
 "Generalization / specialization / aggregation": (r"generalization|specialization|aggregation", 1),
 "Keys": (r"candidate key|super key|concept of keys", 1),
 "ER to relational tables": (r"reducing an er|map the e-r|map the er", 1),
 "Integrity constraints": (r"integrity constraint|referential integrity|entity integrity", 2),
 "SQL queries (write in SQL)": (r"write the following queries|sql statements", 2),
 "Aggregate functions": (r"aggregate function", 2),
 "SQL commands / features / clause": (r"truncate|drop and delete|features of sql|clause in terms", 2),
 "Triggers": (r"trigger", 2),
 "PL/SQL procedures": (r"procedure in sql", 2),
 "Joins": (r"(?<![\w-])joins?\b|equi-join", 2),
 "Relational algebra": (r"relational algebra|\bra statement|union-?\s*compatible", 2),
 "Relational calculus": (r"relational calculus", 2),
 "Functional dependency / Armstrong / closure": (r"\bfds?\b|functional dependenc|armstrong|inference rule|closure of an attribute", 3),
 "Canonical / minimum cover": (r"canonical cover|minimum cover", 3),
 "Prime attributes and keys of a relation": (r"prime and non-prime|prime attributes|identify the key|key for r\b", 3),
 "Normal forms and normalization": (r"normal form|\b[1-5] ?nf\b|normaliz", 3),
 "Decomposition (lossless / lossy)": (r"decompos|loss[- ]?less|lossy", 3),
 "MVD / 4NF / 5NF": (r"\bmvd\b|multivalued dependency", 3),
 "Transitive dependency": (r"transitive dependenc", 3),
 "ACID / transaction properties": (r"acid properties|properties of transaction|property of a transaction|consistency and isolation", 4),
 "Transaction states / failures / rollback": (r"state diagram|states that a transaction|reasons for transaction failure|types of failures|rolled back", 4),
 "Serializability": (r"serializab|equivalent to serial", 4),
 "Recoverable / cascadeless / strict schedules": (r"recoverab|cascade ?less", 4),
 "Log and log-based recovery": (r"\blog\b|log file|deferred|immediate update|immediate database|recovery from", 4),
 "Deadlock": (r"deadlock", 4),
 "Distributed database / replication": (r"distributed|replication", 4),
 "Two-phase commit (2PC)": (r"2 phase commit|2pc|two[- ]phase commit", 5),
 "Locking (2PL, graph-based, granularity, locks)": (r"2pl|graph based locking|multiple\s+gran|levels of locking|exclusive lock|lock in transaction", 5),
 "Timestamp ordering": (r"time ?stamp", 5),
 "Validation / optimistic protocol": (r"validation|optimistic", 5),
 "Multiversion schemes": (r"multi ?version", 5),
 "Concurrency control (basics)": (r"concurrency control|concurrent transactions", 5),
}
SPECIFIC5 = ["Locking (2PL, graph-based, granularity, locks)", "Timestamp ordering", "Validation / optimistic protocol",
             "Multiversion schemes", "Two-phase commit (2PC)"]

def tag(text):
    t = [k for k, (rx, u) in TOPICS.items() if re.search(rx, text, re.I)]
    if "Concurrency control (basics)" in t and any(s in t for s in SPECIFIC5): t.remove("Concurrency control (basics)")
    return t

def positional_unit(r):       # last-resort guess from the question's position in the paper
    i = ord(r['part']) - 97
    return i // 2 + 1 if r['section'] == 'A' else (i + 1 if r['section'] == 'B' else r['q_no'] - 2)

def assign_unit(r):
    if pd.notna(r['co']): return int(r['co']), 'CO in paper'
    us = [TOPICS[t][1] for t in r['topic_list']]
    if us: return max(set(us), key=us.count), 'from topic'
    return positional_unit(r), 'by position'

def load(pattern):
    frames = []
    for f in sorted(glob.glob(pattern)):
        text = pdf_to_text(f) if f.lower().endswith('.pdf') else open(f, encoding='utf-8').read()
        frames.append(parse_paper(text))
    df = pd.concat(frames, ignore_index=True)
    df['topic_list'] = df['text'].apply(tag)
    df[['unit', 'unit_source']] = df.apply(lambda r: pd.Series(assign_unit(r)), axis=1)
    df['topics'] = df['topic_list'].apply('; '.join)
    return df
