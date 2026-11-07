import pandas as pd
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="AKTU PYQ Analyzer", layout="wide")
HERE = Path(__file__).parent
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}


# ---------- 1. load the data (read the CSV files once) ----------
@st.cache_data
def load_data():
    q = pd.read_csv(HERE / "questions_all.csv")
    q["topics"] = q["topics"].fillna("")
    ts = pd.read_csv(HERE / "topic_summary.csv")                     # topic -> unit
    t = q.assign(topic=q["topics"].str.split("; ")).explode("topic")  # one row per (question, topic)
    t = t[t["topic"] != ""].copy()
    t["topic_unit"] = t["topic"].map(dict(zip(ts["topic"], ts["unit"])))
    rep = pd.read_csv(HERE / "repeated_questions.csv")
    return q, t, rep


q, t, rep = load_data()

# ---------- 2. sidebar filters ----------
st.sidebar.header("Filters")
all_years = sorted(q["year"].unique())
unit_choice = st.sidebar.selectbox("Unit", ["All units"] + [f"Unit {r}" for r in ROMAN.values()])
years = st.sidebar.multiselect("Exam years", all_years, default=all_years)

unit_no = None if unit_choice == "All units" else unit_choice.split()[1]
unit_no = None if unit_no is None else [k for k, v in ROMAN.items() if v == unit_no][0]

if not years:
    st.warning("Select at least one exam year in the sidebar.")
    st.stop()

qf = q[q["year"].isin(years)]                   # questions after the filters
tf = t[t["year"].isin(years)]                   # question-topic rows after the filters
if unit_no:
    qf = qf[qf["unit"] == unit_no]
    tf = tf[tf["topic_unit"] == unit_no]

# ---------- 3. header ----------
st.title("AKTU Previous Year Question Analyzer")
st.caption("Subject: Database Management System (BCS501 / KCS501), semester 5")
c1, c2, c3 = st.columns(3)
c1.metric("Papers selected", len(years))
c2.metric("Questions", len(qf))
c3.metric("Marks offered", int(qf["marks"].sum()))

tab1, tab2, tab3, tab4 = st.tabs(["Important topics", "All questions", "Repeated questions", "Unit weightage"])

# ---------- 4. important topics ----------
with tab1:
    if tf.empty:
        st.info("No data for these filters.")
    else:
        n = len(years)
        summary = (tf.groupby("topic")
                     .agg(years_asked=("year", "nunique"), questions=("year", "size"),
                          asked_in=("year", lambda s: ", ".join(sorted(set(s)))))
                     .reset_index()
                     .sort_values(["years_asked", "questions"], ascending=False))
        summary["priority"] = summary["years_asked"].apply(
            lambda y: "High" if y >= 0.8 * n else ("Medium" if y >= 0.5 * n else "Low"))
        st.subheader("How many years each topic was asked")
        st.bar_chart(summary.head(15).set_index("topic")["years_asked"])
        st.dataframe(summary, hide_index=True)
        st.caption("High = asked in at least 80% of the selected years, Medium = at least 50%.")

# ---------- 5. all questions (with search) ----------
with tab2:
    word = st.text_input("Search the questions (for example: deadlock, join, normal form)")
    view = qf
    if word:
        view = view[view["text"].str.contains(word, case=False, na=False, regex=False)]
    st.write(f"{len(view)} questions found")
    cols = ["year", "section", "marks", "unit", "topics", "text"]
    st.dataframe(view.sort_values(["year", "unit"], ascending=[False, True])[cols], hide_index=True)

# ---------- 6. repeated questions ----------
with tab3:
    r = rep if unit_no is None else rep[rep["unit"] == unit_no]
    st.write("Questions that came again in other years:")
    st.dataframe(r.sort_values("times", ascending=False), hide_index=True)

# ---------- 7. unit weightage ----------
with tab4:
    w = (q[q["year"].isin(years)]
         .pivot_table(index="unit", columns="year", values="marks", aggfunc="sum")
         .fillna(0))
    st.write("Marks offered per unit in each paper")
    st.bar_chart(w)
    st.dataframe(w.reset_index(), hide_index=True)
    st.caption("Section B and C give a choice, so the marks offered are more than the marks you answer.")
