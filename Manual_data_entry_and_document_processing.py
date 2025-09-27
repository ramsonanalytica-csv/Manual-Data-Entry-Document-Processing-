import streamlit as st
import pandas as pd
import pdfplumber
import docx
import pytesseract
from PIL import Image
import re
import io
import sqlite3
import json
from datetime import datetime
import matplotlib.pyplot as plt

st.set_page_config(page_title="Document Processor", page_icon="📊", layout="wide")

# ------------------ Database Setup ------------------ #
def init_db():
    conn = sqlite3.connect("documents.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            raw_data TEXT,
            cleaned_data TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_to_db(filename, raw_df, cleaned_df):
    conn = sqlite3.connect("documents.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO documents (filename, raw_data, cleaned_data, timestamp)
        VALUES (?, ?, ?, ?)
    """, (
        filename,
        raw_df.to_json(orient="records"),
        cleaned_df.to_json(orient="records"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()

def fetch_from_db():
    conn = sqlite3.connect("documents.db")
    df = pd.read_sql_query("SELECT * FROM documents ORDER BY id DESC", conn)
    conn.close()
    return df

# ------------------ Validation ------------------ #
def validate_data(df):
    df = df.copy()
    df.drop_duplicates(inplace=True)
    df.fillna("N/A", inplace=True)

    for col in df.columns:
        if "email" in col.lower():
            df[col] = df[col].apply(lambda x: x if re.match(r"[^@]+@[^@]+\.[^@]+", str(x)) else "INVALID_EMAIL")
        if "phone" in col.lower() or "contact" in col.lower():
            df[col] = df[col].apply(lambda x: x if re.match(r"^\+?\d{7,15}$", str(x)) else "INVALID_PHONE")

    return df

def download_excel(df, filename):
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False, engine="openpyxl")
    towrite.seek(0)
    st.download_button("📥 Download Cleaned Excel", data=towrite, file_name=filename)

# ------------------ App Layout ------------------ #
st.title("📊 Document Processing Automation Suite")
st.write("Upload → Extract → Validate → Store → Analyze")

init_db()

tab1, tab2, tab3 = st.tabs(["📂 Upload & Process", "📜 Document History", "📈 Analytics Dashboard"])

# ------------------ Upload & Process ------------------ #
with tab1:
    uploaded_file = st.file_uploader("Upload File", type=["xlsx", "xls", "pdf", "docx", "png", "jpg", "jpeg"])

    if uploaded_file:
        file_type = uploaded_file.name.split(".")[-1].lower()
        extracted_data = []

        if file_type in ["xlsx", "xls"]:
            df = pd.read_excel(uploaded_file)
        elif file_type == "pdf":
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        extracted_data.extend(text.split("\n"))
            df = pd.DataFrame(extracted_data, columns=["Extracted Data"])
        elif file_type == "docx":
            doc = docx.Document(uploaded_file)
            extracted_data = [p.text for p in doc.paragraphs if p.text.strip()]
            df = pd.DataFrame(extracted_data, columns=["Extracted Data"])
        elif file_type in ["png", "jpg", "jpeg"]:
            img = Image.open(uploaded_file)
            text = pytesseract.image_to_string(img)
            df = pd.DataFrame([text], columns=["Extracted Data"])
        else:
            st.error("❌ Unsupported file type")
            df = None

        if df is not None:
            st.subheader("🔎 Raw Extracted Data")
            st.dataframe(df)

            cleaned_df = validate_data(df)
            st.subheader("🧹 Cleaned & Validated Data")
            st.dataframe(cleaned_df)

            download_excel(cleaned_df, f"cleaned_{file_type}.xlsx")

            save_to_db(uploaded_file.name, df, cleaned_df)
            st.success("✅ Data saved to database!")

# ------------------ History ------------------ #
with tab2:
    st.subheader("📜 Processed Document History")
    history_df = fetch_from_db()

    if not history_df.empty:
        st.dataframe(history_df[["id", "filename", "timestamp"]])

        selected_id = st.selectbox("Select a document ID to view details:", history_df["id"])
        if selected_id:
            row = history_df[history_df["id"] == selected_id].iloc[0]
            st.write(f"**Filename:** {row['filename']}")
            st.write(f"**Uploaded At:** {row['timestamp']}")

            raw_df = pd.DataFrame(json.loads(row["raw_data"]))
            cleaned_df = pd.DataFrame(json.loads(row["cleaned_data"]))

            st.write("🔎 Raw Extracted Data")
            st.dataframe(raw_df)

            st.write("🧹 Cleaned & Validated Data")
            st.dataframe(cleaned_df)
    else:
        st.info("No documents processed yet.")

# ------------------ Analytics ------------------ #
with tab3:
    st.subheader("📈 Analytics Dashboard")
    history_df = fetch_from_db()

    if not history_df.empty:
        # Total processed
        total_docs = len(history_df)
        st.metric("📂 Total Documents Processed", total_docs)

        # Errors detected
        error_counts = {"Invalid Emails": 0, "Invalid Phones": 0}
        total_duplicates = 0

        for _, row in history_df.iterrows():
            cleaned_df = pd.DataFrame(json.loads(row["cleaned_data"]))
            total_duplicates += len(json.loads(row["raw_data"])) - len(cleaned_df)

            for col in cleaned_df.columns:
                error_counts["Invalid Emails"] += (cleaned_df[col] == "INVALID_EMAIL").sum()
                error_counts["Invalid Phones"] += (cleaned_df[col] == "INVALID_PHONE").sum()

        st.metric("🧹 Duplicates Removed", total_duplicates)
        st.metric("📧 Invalid Emails Found", error_counts["Invalid Emails"])
        st.metric("📞 Invalid Phones Found", error_counts["Invalid Phones"])

        # Chart: Docs processed over time
        history_df["timestamp"] = pd.to_datetime(history_df["timestamp"])
        docs_per_day = history_df.groupby(history_df["timestamp"].dt.date).size()

        fig, ax = plt.subplots()
        docs_per_day.plot(kind="bar", ax=ax, color="skyblue")
        ax.set_title("Documents Processed Per Day")
        ax.set_xlabel("Date")
        ax.set_ylabel("Documents")
        st.pyplot(fig)

    else:
        st.info("No data available for analytics yet.")