import re
import pandas as pd, numpy as np
from pyq_analyzer import *
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
pd.set_option('display.width', 220); pd.set_option('display.max_colwidth', 80); pd.set_option('display.max_rows', 200)
df = load('papers/*.txt')
df['uid'] = df['year'] + ' ' + df['section'] + str('') + df['q_no'].astype(str) + df['part']
YEARS = sorted(df.year.unique())

# 1. share of each unit in every paper (marks offered)
sh = df.pivot_table(index='unit', columns='year', values='marks', aggfunc='sum')
print('Marks offered per unit\n', sh); print((sh / sh.sum() * 100).round(1))

# 2. topic frequency
t = df.explode('topic_list').dropna(subset=['topic_list']).rename(columns={'topic_list': 'topic'})
g = t.groupby('topic').agg(years=('year', 'nunique'), times=('uid', 'count'),
                           year_list=('year', lambda s: ', '.join(sorted(set(s)))))
g['unit'] = [TOPICS[k][1] for k in g.index]
g = g.reset_index().sort_values(['unit', 'years', 'times'], ascending=[True, False, False])
print(g.to_string(index=False))
g.to_csv('topic_summary.csv', index=False)

# 3. questions that came again in other years (TF-IDF cosine similarity)
v = TfidfVectorizer(stop_words='english', ngram_range=(1, 2)).fit_transform(df['text'])
S = cosine_similarity(v)
def sched(t): return [x.replace(' ', '').upper() for x in re.findall(r'[RrWw]\d\s*\(\s*\w\s*\)', t)]
sc = [sched(t) for t in df['text']]
def same(i, j):
    if df.year[i] == df.year[j]: return False
    if len(sc[i]) >= 5 and sc[i] == sc[j]: return True                    # exactly the same schedule
    shared = set(df.topic_list[i]) & set(df.topic_list[j])
    return (S[i, j] >= 0.55 and bool(shared)) or S[i, j] >= 0.8
pairs = [(i, j, S[i, j]) for i in range(len(df)) for j in range(i + 1, len(df)) if same(i, j)]
# group into clusters
parent = list(range(len(df)))
def f(x):
    while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
    return x
for i, j, s in pairs: parent[f(i)] = f(j)
df['cluster'] = [f(i) for i in range(len(df))]
rep = df.groupby('cluster').filter(lambda c: c.year.nunique() > 1)
rows = []
for c, grp in rep.groupby('cluster'):
    grp = grp.sort_values('year')
    rows.append(dict(times=grp.year.nunique(), years=', '.join(grp.year), unit=int(grp.unit.mode()[0]),
                     marks=int(grp.marks.max()), question=grp.text.iloc[-1][:150]))
R = pd.DataFrame(rows).sort_values(['times', 'unit'], ascending=[False, True])
print(R.to_string(index=False)); R.to_csv('repeated_questions.csv', index=False)
df.drop(columns=['topic_list', 'cluster']).to_csv('questions_all.csv', index=False)
