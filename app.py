import streamlit as st
from tempfile import NamedTemporaryFile
from cause_list_parser import parse_pdf, build_index, format_line

st.set_page_config(page_title="Cause List Selector", layout="centered")
st.title("Cause List Selector")

pdf_file = st.file_uploader("Upload cause-list PDF", type=["pdf"])
refs = st.text_area("Enter refs (one per line or comma separated)", height=200)

if st.button("Extract") and pdf_file and refs.strip():
    with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_file.read())
        tmp.flush()
        items = parse_pdf(tmp.name)
    idx = build_index(items)
    query_refs = [r.strip() for r in refs.replace(",", "\n").splitlines() if r.strip()]
    lines = []
    for ref in query_refs:
        it = idx.get(ref)
        lines.append(format_line(it) if it else f"{ref} - NOT FOUND")
    st.subheader("Results")
    st.code("\n".join(lines))
