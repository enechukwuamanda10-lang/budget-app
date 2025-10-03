# budget_app.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import gspread
import uuid
from datetime import datetime
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
import json

# --- CONFIG: use Streamlit secrets ---
# Make sure your Streamlit secrets.toml has [SERVICE_ACCOUNT] and SHEET_ID
sa_info = st.secrets["SERVICE_ACCOUNT"]
if isinstance(sa_info, str):
    sa_info = json.loads(sa_info)

SHEET_ID = st.secrets["SHEET_ID"]

def connect_sheet():
    creds = Credentials.from_service_account_info(
        sa_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh

    except Exception as e:
        st.error(f"Could not connect to Google Sheets: {e}")
        st.stop()

def ensure_ws(sh, title, headers):
    """Return worksheet; create with headers if not exist."""
    try:
        ws = sh.worksheet(title)
    except WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows="100", cols="20")
        ws.append_row(headers)
        return ws
    # ensure header row exists & matches (if not, set it)
    row1 = ws.row_values(1)
    if row1 != headers:
        try:
            ws.delete_rows(1)
        except Exception:
            pass
        ws.insert_row(headers, index=1)
    return ws

def load_data_from_sheets(cat_ws, exp_ws):
    cats = {}
    try:
        cat_records = cat_ws.get_all_records()
    except Exception:
        cat_records = []
    for r in cat_records:
        name = r.get("category", "").strip()
        if not name:
            continue
        cid = r.get("id") or uuid.uuid4().hex
        budget = int(float(r.get("budget", 0) or 0))
        btype = r.get("type") or "Monthly"
        cats[name] = {"id": cid, "budget": budget, "type": btype, "expenses": []}

    try:
        exp_records = exp_ws.get_all_records()
    except Exception:
        exp_records = []
    for r in exp_records:
        cat = r.get("category", "").strip()
        if not cat:
            continue
        eid = r.get("id") or uuid.uuid4().hex
        try:
            amount = int(float(r.get("amount", 0) or 0))
        except:
            amount = 0
        note = r.get("note") or ""
        date = r.get("date") or ""
        if cat not in cats:
            cats[cat] = {"id": uuid.uuid4().hex, "budget": 0, "type": "Monthly", "expenses": []}
        cats[cat]["expenses"].append({"id": eid, "amount": amount, "note": note, "date": date})
    return cats

def append_category(cat_ws, name, budget, btype):
    cid = uuid.uuid4().hex
    cat_ws.append_row([cid, name, budget, btype])
    return cid

def append_expense(exp_ws, category, amount, note, date):
    eid = uuid.uuid4().hex
    exp_ws.append_row([eid, category, amount, note, date])
    return eid

def delete_category_and_its_expenses(cat_ws, exp_ws, category_name):
    # delete category rows
    vals = cat_ws.get_all_values()
    rows_to_delete = [i for i, row in enumerate(vals[1:], start=2) if len(row) >= 2 and row[1] == category_name]
    for r in reversed(rows_to_delete):
        cat_ws.delete_rows(r)
    # delete expenses rows matching category
    exp_vals = exp_ws.get_all_values()
    rows_to_delete = [i for i, row in enumerate(exp_vals[1:], start=2) if len(row) >= 2 and row[1] == category_name]
    for r in reversed(rows_to_delete):
        exp_ws.delete_rows(r)

def delete_expense_by_id(exp_ws, exp_id):
    vals = exp_ws.get_all_values()
    for i, row in enumerate(vals[1:], start=2):
        if len(row) >= 1 and row[0] == exp_id:
            exp_ws.delete_rows(i)
            return True
    return False

def update_expense_amount(exp_ws, exp_id, new_amount, new_note=None):
    vals = exp_ws.get_all_values()
    for i, row in enumerate(vals[1:], start=2):
        if len(row) >= 1 and row[0] == exp_id:
            exp_ws.update_cell(i, 3, new_amount)
            if new_note is not None:
                exp_ws.update_cell(i, 4, new_note)
            return True
    return False

# ------------------ App starts here ------------------
st.set_page_config(page_title="Budget & Expense Planner", layout="wide")
sh = connect_sheet()
cat_ws = ensure_ws(sh, "categories", ["id", "category", "budget", "type"])
exp_ws = ensure_ws(sh, "expenses", ["id", "category", "amount", "note", "date"])

if "categories" not in st.session_state:
    st.session_state.categories = load_data_from_sheets(cat_ws, exp_ws)

st.title("📊 Budget & Expense Planner (Google Sheets)")

# --- Add category ---
with st.expander("➕ Add Category", expanded=False):
    new_cat = st.text_input("Category name", key="new_cat")
    new_budget = st.number_input("Budget amount", min_value=0, step=100, key="new_budget")
    budget_type = st.selectbox("Type", ["Monthly", "Weekly", "Yearly", "One-time"], key="new_type")
    if st.button("Add Category", key="add_cat_btn"):
        if new_cat and new_cat not in st.session_state.categories:
            append_category(cat_ws, new_cat, int(new_budget), budget_type)
            st.session_state.categories = load_data_from_sheets(cat_ws, exp_ws)
            st.success(f"Category '{new_cat}' added.")
        else:
            st.warning("Invalid or duplicate category name.")

# --- Log expenses ---
with st.expander("💸 Log Expense", expanded=True):
    if st.session_state.categories:
        cat_list = list(st.session_state.categories.keys())
        cat_choice = st.selectbox("Category", cat_list, key="log_cat")
        amt = st.number_input("Amount", min_value=0, step=100, key="log_amount")
        note = st.text_input("Note (optional)", key="log_note")
        if st.button("Add Expense", key="add_exp_btn"):
            if amt > 0:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                append_expense(exp_ws, cat_choice, int(amt), note, now)
                st.session_state.categories = load_data_from_sheets(cat_ws, exp_ws)
                st.success(f"Added {amt} to {cat_choice}")
            else:
                st.warning("Enter an amount greater than 0.")
    else:
        st.info("Add a category first.")

# --- Manage categories ---
with st.expander("🗂️ Manage Categories", expanded=False):
    if st.session_state.categories:
        to_delete = st.selectbox("Select category to delete", list(st.session_state.categories.keys()), key="del_cat")
        if st.button("Delete Category", key="del_cat_btn"):
            delete_category_and_its_expenses(cat_ws, exp_ws, to_delete)
            st.session_state.categories = load_data_from_sheets(cat_ws, exp_ws)
            st.success(f"Deleted category '{to_delete}' and its expenses.")
    else:
        st.info("No categories yet.")

# --- Summary & History ---
st.header("📊 Summary")
summary = []
for cat, data in st.session_state.categories.items():
    budget = data.get("budget", 0)
    spent = sum(e.get("amount", 0) for e in data.get("expenses", []))
    summary.append([cat, data.get("type", "N/A"), budget, spent, budget - spent])

if summary:
    df = pd.DataFrame(summary, columns=["Category", "Type", "Budget", "Spent", "Remaining"])
    def highlight_over(val):
        return 'color: red; font-weight: bold;' if val < 0 else ''
    st.dataframe(df.style.applymap(highlight_over, subset=["Remaining"]))
    total_budget = df["Budget"].sum()
    total_spent = df["Spent"].sum()
    total_remaining = total_budget - total_spent
    st.markdown(f"**Total Budget:** {total_budget}   &nbsp;&nbsp; **Total Spent:** {total_spent}   &nbsp;&nbsp; **Remaining:** {total_remaining}")

    st.subheader("Category Progress")
    for _, row in df.iterrows():
        progress = row["Spent"] / row["Budget"] if row["Budget"] > 0 else 0
        st.write(f"**{row['Category']} ({row['Type']})**")
        st.progress(min(progress, 1.0))
else:
    st.info("No categories/expenses yet.")

# Expense history
st.header("📜 Expense History")
history = []
for cat, data in st.session_state.categories.items():
    for exp in data.get("expenses", []):
        history.append([cat, exp.get("amount", 0), exp.get("note", ""), exp.get("date", ""), exp.get("id")])
if history:
    hist_df = pd.DataFrame(history, columns=["Category", "Amount", "Note", "Date", "ID"])
    st.dataframe(hist_df.sort_values("Date", ascending=False).drop(columns=["ID"]))
else:
    st.info("No expenses logged yet.")

# Manage individual expenses
with st.expander("✏️ Edit / Delete an Expense", expanded=False):
    if history:
        manage_cat = st.selectbox("Choose category", list(st.session_state.categories.keys()), key="man_cat")
        exps = st.session
