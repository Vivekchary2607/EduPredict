# app.py
import streamlit as st
import pandas as pd
import joblib
import matplotlib.pyplot as plt
import shap
import json
from database import validate_user, add_user, save_prediction, get_all_predictions,validate_invite,mark_invite_used,create_invite,get_all_organizations,request_student_record,get_pending_requests,get_shared_student_record,update_request_status
from database import create_organization,get_users_by_org,get_predictions_by_org,validate_org_code,get_org_admin,clear_predictions_by_org,get_received_requests,get_sent_requests
from database import validate_global_student_id,is_request_already_sent,get_org_name,get_prediction_count_by_org
from database import raise_withdraw_request,get_withdraw_requests,approve_withdraw_request
from database import get_platform_stats,get_prediction_count_by_org,get_prediction_distribution,get_predictions_by_org_stats,get_user_role_distribution
from email_utils import send_invite_email,send_org_code_email
from database import init_db, seed_initial_data

init_db()
seed_initial_data()
# ---------- Session State Initialization ----------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = None

if "role" not in st.session_state:
    st.session_state.role = None

if "org_id" not in st.session_state:
    st.session_state.org_id = None   # 🔑 THIS FIXES YOUR ERROR

if "subject" not in st.session_state:
    st.session_state.subject = None

# ------------------- Utilities -------------------
def safe_encode_series(series, encoder):
    classes = list(encoder.classes_)
    mapping = {v: i for i, v in enumerate(classes)}
    default_idx = 0
    return series.map(mapping).fillna(default_idx).astype(int)

def get_class_group_from_level(class_level):
    if class_level <= 5:
        return "primary"
    elif class_level <= 8:
        return "middle"
    else:
        return "secondary"
def safe_get(col, df):
    return df[col].values[0] if col in df.columns else None


def generate_explanation(pred_prob, prediction, input_data):
    reasons_positive, reasons_negative = [], []

    if pred_prob > 0.85 or pred_prob < 0.15:
        certainty = "with high certainty"
    elif 0.65 <= pred_prob <= 0.85 or 0.15 <= pred_prob <= 0.35:
        certainty = "with moderate certainty"
    else:
        certainty = "with low certainty"

    if input_data['math_score'].values[0] < 40:
        reasons_negative.append(f"low math score ({int(input_data['math_score'].values[0])})")
    elif input_data['math_score'].values[0] > 70:
        reasons_positive.append(f"strong math score ({int(input_data['math_score'].values[0])})")

    if input_data['english_score'].values[0] < 40:
        reasons_negative.append(f"low English score ({int(input_data['english_score'].values[0])})")
    elif input_data['english_score'].values[0] > 70:
        reasons_positive.append(f"strong English score ({int(input_data['english_score'].values[0])})")

    hours = safe_get("weekly_self_study_hours", input_data)
    if hours is not None:
        if hours == 0:
            reasons_negative.append("no self-study hours")
        elif hours > 5:
            reasons_positive.append("consistent self-study")


    if input_data['extracurricular_activities'].values[0] == 0:
        reasons_negative.append("no extracurricular activities")
    else:
        reasons_positive.append("involvement in extracurriculars")

    if input_data['absence_days'].values[0] > 20:
        reasons_negative.append(f"{int(input_data['absence_days'].values[0])} absence days")
    elif input_data['absence_days'].values[0] < 5:
        reasons_positive.append("very few absences")

    if prediction == 1:
        msg = f"This student is predicted to **Pass** {certainty} (model output: {pred_prob:.2f}). "
        if reasons_positive:
            msg += "Supported by " + ", ".join(reasons_positive) + ". "
        if reasons_negative:
            msg += "Some risks: " + ", ".join(reasons_negative) + "."
    else:
        msg = f"This student is predicted to **Fail** {certainty} (model output: {pred_prob:.2f}). "
        if reasons_negative:
            msg += "Driven by " + ", ".join(reasons_negative) + ". "
        if reasons_positive:
            msg += "Positive signals: " + ", ".join(reasons_positive) + "."

    return msg
CLASS_CONFIG = {
    "primary": {
        "model_file": "model_primary.pkl",
        "columns_file": "columns_primary.pkl",
        "subjects": ["math_score", "english_score", "physics_score"]
    },
    "middle": {
        "model_file": "model_middle.pkl",
        "columns_file": "columns_middle.pkl",
        "subjects": ["math_score", "english_score", "physics_score"]
    },
    "secondary": {
        "model_file": "model_secondary.pkl",
        "columns_file": "columns_secondary.pkl",
        "subjects": [
            "math_score", "english_score", "physics_score",
            "biology_score", "chemistry_score",
            "history_score", "geography_score"
        ]
    }
}

# ------------------- Load Model -------------------
try:
        MODELS = {
        }
        MODEL_COLUMNS = {
        }
        for group, cfg in CLASS_CONFIG.items():
            MODELS[group] = joblib.load(cfg["model_file"])
            MODEL_COLUMNS[group] = joblib.load(cfg["columns_file"])
except Exception as e:
    st.error(f"❌ Could not load model or columns. Error: {e}")
    st.stop()

# Load encoders
encoder_names = {
    "gender": "gender_encoder.pkl",
    "part_time_job": "part_time_job_encoder.pkl",
    "extracurricular_activities": "extracurricular_activities_encoder.pkl",
    "career_aspiration": "career_aspiration_encoder.pkl"
}
encoders = {}
for k, fname in encoder_names.items():
    try:
        encoders[k] = joblib.load(fname)
    except:
        encoders[k] = None

# ------------------- Streamlit Config -------------------
st.set_page_config(page_title="Student Performance System", layout="wide")
st.sidebar.markdown("## 📘 Student Performance & Analytics System")
st.sidebar.info("An AI-powered early-warning system for teachers 🚀")

# ------------------- Session State -------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None

# ------------------- Auth -------------------
if not st.session_state.logged_in:
    st.title("🔐 Authentication Required")
    choice = st.radio("Select Option:", ["Login", "Register","Register Organization"])
    if choice == "Login":
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            user = validate_user(username, password)
            if user == "deactivated":
                st.error("❌ Your organization has been deactivated.")
            elif user:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = user["role"]
                st.session_state.subject = user["subject"]
                st.session_state.org_id = user["org_id"] 
                st.rerun()
                
            else:
                st.error("Invalid credentials")
    elif choice == "Register":
        st.subheader("📝 Register Using Invite Code")

        email = st.text_input("Email (must match invite)")
        invite_token = st.text_input("Invite Token")
        username = st.text_input("Choose Username")
        password = st.text_input("Choose Password", type="password")

        if st.button("Register"):
            #  Validate invite
            invite_data, error = validate_invite(
                invite_token.strip().upper(),
                email.strip()
            )

            if error:
                st.error(error)
                st.stop()

            # 3 Create user WITH org_id
            add_user(
                username=username,
                password=password,
                role=invite_data["role"],
                subject=invite_data.get("subject"),
                org_id=invite_data["org_id"]   # ✅ THIS IS THE KEY FIX
            )

            #  Mark invite as used
            mark_invite_used(invite_data["invite_id"])

            st.success("✅ Account created successfully! Please login.")
    elif choice == "Register Organization":

        st.subheader("🏫 Organization Registration")

        org_code = st.text_input("Organization Code", key="org_reg_code")
        admin_username = st.text_input("Admin Username", key="org_admin_user")
        admin_password = st.text_input("Admin Password", type="password", key="org_admin_pass")

        if st.button("Register Organization", key="org_register_btn"):

            # 1️⃣ Validate org code
            org = validate_org_code(org_code.strip())

            if not org:
                st.error("Invalid Organization Code")
                st.stop()

            # 2️⃣ Check if org already has admin
            existing_admin = get_org_admin(org["id"])

            if existing_admin:
                st.error("Organization admin already registered.")
                st.stop()

            # 3️⃣ Create admin user for that org
            add_user(
                username=admin_username,
                password=admin_password,
                role="admin",
                subject=None,
                org_id=org["id"]
            )

            st.success("✅ Organization registered successfully! Please login.")

    st.info("Login or Register to continue.")
    st.stop()


# ------------------- Navigation -------------------
#st.sidebar.write(f"👤 Logged in as: **{st.session_state.username}** ({st.session_state.role})")
# ------------------- ROLE-BASED NAVIGATION -------------------

if st.session_state.role == "super_admin":
    allowed_pages = [
        "Platform Admin",
        "Logout"
    ]

elif st.session_state.role == "admin":
    allowed_pages = [
        "Single Prediction",
        "Batch Prediction",
        "Record Requests",
        "Organization Admin Panel",
        "Logout"
    ]

else:  # teacher
    allowed_pages = [
        "Single Prediction",
        "Batch Prediction",
        "Logout"
    ]
org_name=get_org_name(st.session_state.org_id)

st.sidebar.markdown(
    f"""
    👤Logged in as: **{st.session_state.username}**  
    🏫 **{org_name}**  
    🔐 Role: **{st.session_state.role.upper()}**
    """
)
#page = st.sidebar.radio("Navigation", ["Single Prediction", "Batch Prediction", "Admin Panel", "Logout"])
# page = st.sidebar.radio(
#     "Navigation",
#     [
#         "Single Prediction",
#         "Batch Prediction",
#         "Record Requests",
#         "Admin Panel",
#         "Logout"
#     ]
# )
page = st.sidebar.radio("Navigation", allowed_pages)

if page == "Logout":
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.org_id = None
    st.session_state.username = None
    st.rerun()

# ------------------- Single Prediction -------------------
if page == "Single Prediction":
    st.header("🔎 Single Student Prediction")
    class_level = st.selectbox("📘 Select Class", list(range(1, 11)))
    class_group = get_class_group_from_level(class_level)

    model = MODELS[class_group]
    columns = MODEL_COLUMNS[class_group]

    st.info(f"Using **{class_group.upper()} model**")

    student_name = st.text_input("Student name (optional)")
    #Org_ID = st.text_input("Enter Organization ID ")
    org_id = st.session_state.org_id

    with st.expander("📋 Student Info"):
        col1, col2 = st.columns(2)

        with col1:
            gender = st.selectbox("Gender", ["male", "female"])
            extracurricular = st.selectbox("Extracurricular Activities", ["True", "False"])

            part_time_job = None
            career = None

            if class_group == "secondary":
                part_time_job = st.selectbox("Part-Time Job", ["True", "False"])
                career = st.selectbox(
                    "Career Aspiration",
                    list(encoders["career_aspiration"].classes_)
                )

        with col2:
            absence_days = st.number_input("Absence Days", 0, 365)
            weekly_study_hours = 0

            if class_group != "primary":
                weekly_study_hours = st.slider("Weekly Self Study Hours", 0, 40)

            math = st.slider("Math Score", 0, 100)
            english = st.slider("English Score", 0, 100)
            physics = st.slider("Physics Score", 0, 100)

            history = chemistry = biology = geography = 0
            if class_group == "secondary":
                history = st.slider("History Score", 0, 100)
                chemistry = st.slider("Chemistry Score", 0, 100)
                biology = st.slider("Biology Score", 0, 100)
                geography = st.slider("Geography Score", 0, 100)


        if st.button("Predict"):
            input_dict = {
                "gender": gender,
                "extracurricular_activities": extracurricular,
                "absence_days": absence_days,
                "math_score": math,
                "english_score": english,
                "physics_score": physics
            }

            if class_group != "primary":
                input_dict["weekly_self_study_hours"] = weekly_study_hours

            if class_group == "secondary":
                input_dict.update({
                    "history_score": history,
                    "chemistry_score": chemistry,
                    "biology_score": biology,
                    "geography_score": geography,
                    "career_aspiration": career,
                    "part_time_job": part_time_job
                })

            input_data = pd.DataFrame([input_dict])


            # encode categorical safely
            for col in encoders:
                if col in input_data.columns:
                    enc = encoders[col]
                    if enc:
                        input_data[col] = safe_encode_series(input_data[col], enc)


            for c in columns:
                if c not in input_data.columns:
                    input_data[c] = 0
            input_data = input_data[columns]

            prediction = model.predict(input_data)[0]
            pred_prob = model.predict_proba(input_data)[0][1]

            # Result Card
            if prediction == 1:
                st.success(f"🎯 Prediction: PASS ✅ (Probability: {pred_prob:.2f})")
            else:
                st.error(f"🎯 Prediction: FAIL ❌ (Probability: {pred_prob:.2f})")

            # Bar chart
            CLASS_FEATURES_UI = {
                "primary": ["math_score", "english_score", "physics_score"],
                "middle": ["math_score", "english_score", "physics_score"],
                "secondary": [
                    "math_score", "english_score", "physics_score",
                    "biology_score", "chemistry_score",
                    "history_score", "geography_score"
                ]
            }
            subjects = CLASS_FEATURES_UI[class_group]

            scores = {sub.replace("_score", "").title(): input_data[sub].values[0] for sub in subjects}

            fig, ax = plt.subplots(figsize=(3.5, 2.2))
            ax.bar(scores.keys(), scores.values(),
                color=["green" if v >= 40 else "red" for v in scores.values()])
            ax.axhline(y=40, linestyle="--", color="black")
            ax.set_ylabel("Marks", fontsize=8)
            ax.set_title("Subject-wise Scores", fontsize=10)
            ax.tick_params(axis='x', labelrotation=30, labelsize=8)  
            ax.tick_params(axis='y', labelsize=8)
            st.pyplot(fig, clear_figure=True,use_container_width=False)

            # SHAP Explanation
            explainer = shap.Explainer(model, input_data)
            shap_values = explainer(input_data)

            st.markdown("### 🔍 SHAP Decision Plot for Prediction")
            st.write("Shows how each feature moves the prediction score towards Pass or Fail.")

            plt.rcParams.update({'font.size': 0.3})  
            fig= plt.figure(figsize=(3.5, 2.5))  
            shap.decision_plot(
                base_value=explainer.expected_value[1],
                shap_values=shap_values.values[0, :, 1],
                features=input_data,
                feature_names=list(input_data.columns),
                show=False
            )
            st.pyplot(fig, clear_figure=True)


            # Text Explanation
            explanation = generate_explanation(pred_prob, prediction, input_data)
            st.markdown("### 📌 Prediction Explanation")
            st.markdown(explanation)

            # Save to DB
            student_display_name = student_name if student_name else "Unnamed Student"
            org_id = st.session_state.org_id
            save_prediction(st.session_state.username, student_display_name,class_level,class_group,
                            json.loads(input_data.to_json(orient="records"))[0],
                            "Pass" if prediction == 1 else "Fail",
                            float(pred_prob), explanation,org_id)
            st.success("Prediction saved to database.")

# ------------------- Batch Prediction -------------------
# ---------- Batch Prediction ----------
elif page == "Batch Prediction":

        class_level = st.selectbox("📘 Select Class for Batch", list(range(1, 11)))
        class_group = get_class_group_from_level(class_level)

        model = MODELS[class_group]
        columns = MODEL_COLUMNS[class_group]
        subjects = CLASS_CONFIG[class_group]["subjects"]

        st.info(f"Batch prediction using **{class_group.upper()} model**")

        uploaded_file = st.file_uploader("Upload CSV for batch prediction", type=["csv"])

        if uploaded_file:
            df = pd.read_csv(uploaded_file)

            # ---- Encode safely (only if present) ----
            for col in ["gender", "part_time_job", "extracurricular_activities", "career_aspiration"]:
                if col in df.columns and encoders.get(col):
                    df[col] = safe_encode_series(df[col], encoders[col])

            # ---- Build model input safely ----
            df_model = pd.DataFrame()

            for col in columns:
                if col in df.columns:
                    df_model[col] = df[col]
                else:
                    df_model[col] = 0   # missing feature → neutral default

            # ---- Predict ----
            preds = model.predict(df_model)
            probs = model.predict_proba(df_model)[:, 1]

            df["Prediction"] = ["Pass" if p == 1 else "Fail" for p in preds]
            df["Probability"] = probs.round(3)

            # ---- Explanations ----
            explanations = []
            for i in range(len(df_model)):
                explanations.append(
                    generate_explanation(probs[i], preds[i], df_model.iloc[[i]])
                )
            df["Explanation"] = explanations

            st.dataframe(df.head(200))

            # ---- Download ----
            st.download_button(
                "Download predictions CSV",
                df.to_csv(index=False).encode("utf-8"),
                "predictions.csv"
            )

            # Save predictions into DB
            for i, row in df.iterrows():
                student_name = row.get("student_name", f"Student_{i+1}")

                # org_id = (
                #     int(row["org_id"])
                #     if "org_id" in row and not pd.isna(row["org_id"])
                #     else st.session_state.org_id
                # )
                org_id=st.session_state.org_id

                save_prediction(
                    st.session_state.username,
                    student_name,class_level,class_group,
                    json.loads(df_model.iloc[i:i+1].to_json(orient="records"))[0],
                    row["Prediction"],
                    float(row["Probability"]),
                    row["Explanation"],
                    org_id
                )

            st.success("✅ All batch predictions saved to database.")


            # ---- NEW FEATURE: View Student Details ----
            st.markdown("### 🔎 View Individual Student Details")

            student_choice = st.selectbox(
                "Select student",
                df.index,
                format_func=lambda x: df.loc[x].get("student_name", f"Student {x+1}")
            )

            if st.button("Show Details"):
                row = df.iloc[student_choice]
                input_row = df_model.iloc[[student_choice]]

                st.subheader("📌 Detailed Report")
                st.write(f"**Prediction:** {row['Prediction']} ({row['Probability']})")
                st.write(row["Explanation"])

                # ---- Bar Plot (CLASS-AWARE) ----
                scores = {s.replace("_score","").title(): row[s] for s in subjects}

                fig, ax = plt.subplots(figsize=(4,2.5))
                ax.bar(scores.keys(), scores.values(),
                    color=["green" if v >= 40 else "red" for v in scores.values()])
                ax.axhline(40, linestyle="--", color="black")
                ax.set_ylabel("Marks", fontsize=8)
                ax.set_title("Subject-wise Scores", fontsize=10)
                ax.tick_params(axis='x', labelrotation=30, labelsize=8)  
                ax.tick_params(axis='y', labelsize=8)
                st.pyplot(fig, clear_figure=True,use_container_width=False)

                # ---- SHAP ----
                explainer = shap.Explainer(model, df_model)
                shap_values = explainer(input_row)

                st.markdown("### 🔍 SHAP Decision Plot for Prediction")
                st.write("Shows how each feature moves the prediction score towards Pass or Fail.")

                plt.rcParams.update({'font.size': 0.3})  
                fig= plt.figure(figsize=(3.5, 2.5)) 
                shap.decision_plot(
                    explainer.expected_value[1],
                    shap_values.values[0,:,1],
                    input_row,
                    show=False
                )
                st.pyplot(fig, clear_figure=True)


elif page == "Record Requests":

    st.header("📨 Student Performance Verification")

    global_id = st.text_input("Global Student ID")

    orgs = get_all_organizations()
    #org_map = {o["org_name"]: o["id"] for o in orgs}
    # Remove current organization
    filtered_orgs = [
        o for o in orgs if o["id"] != st.session_state.org_id
    ]

    org_map = {o["org_name"]: o["id"] for o in filtered_orgs}
    source_org = st.selectbox("Previous Organization", list(org_map.keys()))

    if st.button("Send Request"):

        if not global_id.strip():
            st.warning("Please enter Global Student ID.")
            st.stop()

        source_org_id = org_map[source_org]
        if source_org_id == st.session_state.org_id:
            st.error("You cannot request your own organization's student.")
            st.stop()

        # ✅ 1️⃣ Check if student exists in selected org
        exists = validate_global_student_id(global_id.strip(), source_org_id)

        if not exists:
            st.error("❌ Global Student ID not found in selected organization.")
            st.stop()

        # ✅ 2️⃣ Check duplicate request
        duplicate = is_request_already_sent(
            st.session_state.org_id,
            source_org_id,
            global_id.strip()
        )

        if duplicate:
            st.warning("⚠️ Request already sent and pending approval.")
            st.stop()

        # ✅ 3️⃣ Send request
        result=request_student_record(
            st.session_state.org_id,
            source_org_id,
            global_id.strip()
        )
        if result != "success":
            st.error(result)
        else:
            st.success("✅ Request sent successfully.")
        



# ------------------- PLATFORM ADMIN -------------------
elif page == "Platform Admin":

    if st.session_state.role != "super_admin":
        st.error("Unauthorized")
        st.stop()

    st.header("🌐 Super Admin – Platform Control")

    tab1,tab2,tab3,tab4,tab5=st.tabs(["➕ Create Organization","🏫 Registered Organizations","📊 Organization Statistics","📥 Organization Withdrawal Requests","📊 Platform Overview"])
    with tab1:
        st.subheader("➕ Create Organization")

        org_name = st.text_input("Organization Name", key="create_org_name")
        admin_email = st.text_input("Organization Admin Email", key="create_org_email")

        if st.button("Create Organization", key="create_org_button"):
            if org_name and admin_email:

                org_code = create_organization(org_name,admin_email)

                # Send secure email
                send_org_code_email(admin_email, org_name, org_code)

                st.success(f"✅ Organization created successfully!")
                st.info(f"Organization Code sent securely to {admin_email}")

            else:
                st.warning("Please fill all fields.")
    with tab2:
        st.subheader("🏫 Registered Organizations")

        orgs = get_all_organizations()

        if orgs:
            df_org = pd.DataFrame(orgs)
            st.dataframe(df_org, use_container_width=True)
            
        else:
            st.info("No organizations registered.")
    with tab3:
        st.subheader("📊 Organization Statistics")

        for org in orgs:
            #count = get_prediction_count_by_org(org["id"])
            print(org)
            print(type(org["id"]), org["id"])
            count = get_prediction_count_by_org(int(org["id"]))
            st.write(f"{org['org_name']} → {count} Predictions")
    with tab4:
        st.subheader("📥 Organization Withdrawal Requests")

        requests = get_withdraw_requests()

        if requests:
            for r in requests:
                st.write(f"🏫 {r['org_name']}")
                st.write(f"Organiztion id:{r["org_id"]}")
                st.write(f"Reason: {r['reason']}")
                st.write(f"Requested on: {r['timestamp']}")
                
                if st.button(f"Approve - {r['org_name']}", key=r["id"]):
                    approve_withdraw_request(r["id"], r["org_id"])
                    st.success(f"{r['org_name']} has been deactivated.")
                    st.experimental_rerun()
        else:
            st.info("No pending withdrawal requests.")
    with tab5:
        st.subheader("📊 Platform Overview")

        total_orgs, total_users, total_predictions = get_platform_stats()

        col1, col2, col3 = st.columns(3)

        col1.metric("Active Organizations", total_orgs)
        col2.metric("Total Users", total_users)
        col3.metric("Total Predictions", total_predictions)

        import plotly.express as px
        import pandas as pd

        st.subheader("🎯 Prediction Distribution")

        dist = get_prediction_distribution()

        if dist:
            df = pd.DataFrame(dist)
            df.rename(columns={"result": "Result", "count": "Count"}, inplace=True)

            fig = px.pie(df, names="Result", values="Count", title="Pass vs Fail")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No prediction data available")

        st.subheader("👥 User Role Distribution")

        roles = get_user_role_distribution()

        if roles:
            df_roles = pd.DataFrame(roles)
            df_roles.rename(columns={"role": "Role", "count": "Count"}, inplace=True)

            fig_roles = px.pie(df_roles, names="Role", values="Count", title="Users by Role")
            st.plotly_chart(fig_roles, use_container_width=True)
        else:
            st.warning("No user data available")


        st.subheader("🏫 Predictions Per Organization")

        org_stats = get_predictions_by_org_stats()

        if org_stats:
            df_org = pd.DataFrame([dict(row) for row in org_stats])

            fig_bar = px.bar(
                df_org,
                x="org_name",
                y="total_predictions",
                title="Predictions by Organization"
            )

            st.plotly_chart(fig_bar, use_container_width=True)



# ------------------- Admin Panel -------------------
elif page == "Organization Admin Panel":
    if st.session_state.role != "admin":
        st.error("Admin access only")
        st.stop()

    # ---------- Admin Panel ---------
    st.header("🏫 Organization Admin Panel")

    # Tabs for admin functions
    tab1, tab2, tab3 ,tab4, tab5,tab6,tab7 = st.tabs(["📊 Predictions","📄 My Students", "👤 Manage Users","📥 Student Record Requests Management","🔍 View Shared Student Record ","🚪 Withdraw Organization","⚠️ Database Tools"])

    with tab1:
        st.subheader("Organization Predictions")

        all_preds = get_predictions_by_org(st.session_state.org_id)

        if not all_preds:
            st.info("No predictions found.")
        else:
            df_all = pd.DataFrame(all_preds)

             #Filtering options
            teacher_filter = st.selectbox(
                "Filter by Teacher",
                ["All"] + df_all["username"].unique().tolist(),
                key="org_teacher_filter"
            )

            student_filter = st.text_input(
                "Filter by Student Name",
                key="org_student_filter"
            )
            class_filter = st.selectbox(
                                "Filter by Class",
                                ["All"] + sorted(df_all["class_level"].dropna().unique().tolist())
                            )

            df_filtered = df_all.copy()

            if teacher_filter != "All":
                df_filtered = df_filtered[df_filtered["username"] == teacher_filter]

            if student_filter:
                df_filtered = df_filtered[
                    df_filtered["student_name"].str.contains(
                        student_filter, case=False, na=False
                    )
                ]

            if class_filter != "All":
                df_filtered = df_filtered[df_filtered["class_level"] == class_filter]

            st.dataframe(df_filtered, use_container_width=True)
            # Option to download
            csv_all = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button("Download filtered predictions CSV", csv_all, "filtered_predictions.csv")
    
    with tab2:
        st.subheader("My Organization Students")

        students = get_predictions_by_org(st.session_state.org_id)

        if students:
            df = pd.DataFrame(students)

            df_unique = df.drop_duplicates(
                subset=["student_name", "class_level", "global_student_id"]
            )

            df = df_unique

            # -------- FILTER SECTION --------
            col1, col2 ,col3= st.columns(3)

            with col1:
                class_filter = st.selectbox(
                    "Filter by Class",
                    ["All"] + sorted(df["class_level"].dropna().unique().tolist()),key="CLASS_FILTER"
                )

            with col2:
                name_filter = st.text_input("Search by Student Name")
            
            with col3:
                result_filter = st.selectbox("Filter by Result", ["All", "Pass", "Fail"],key="RESULT")

            

            # -------- APPLY FILTER --------
            df_filtered = df.copy()

            if class_filter != "All":
                df_filtered = df_filtered[df_filtered["class_level"] == class_filter]

            if name_filter:
                df_filtered = df_filtered[
                    df_filtered["student_name"]
                    .str.contains(name_filter, case=False, na=False)
                ]
            if result_filter != "All":
                df_filtered = df_filtered[df_filtered["result"] == result_filter]

            # -------- DISPLAY --------
            st.dataframe(
                df_filtered[
                    ["student_name", "class_level", "global_student_id", "result", "timestamp"]
                ],
                use_container_width=True
            )

            st.write(f"Showing {len(df_filtered)} students")

        else:
            st.info("No students found.")




    with tab3:

        from database import get_all_users, delete_user, add_user

        st.subheader("Manage Organization Users")

        users = get_users_by_org(st.session_state.org_id)

        if users:
            df_users = pd.DataFrame(users)
            st.dataframe(df_users, use_container_width=True)

            del_user = st.selectbox("Select a user to delete", ["None"] + df_users["username"].tolist())
            if del_user != "None" and st.button("Delete User"):
                    delete_user(del_user)
                    st.success(f"✅ User '{del_user}' deleted.")
                    st.experimental_rerun()
        else:
            st.info("No users found in this organization.")

        with tab3:
             st.subheader("📨 Invite New User")

             email = st.text_input("Recipient Email")
             role = st.selectbox("Role", ["teacher", "admin"])
             expiry = st.slider("Invite Expiry (hours)", 1, 72, 24)
             subject = None
             if role == "teacher":
                 subject = st.selectbox("Subject", ["Math", "Science", "English", "General"])

             if st.button("Send Invite"):
                 token, expires_at = create_invite(
                    email=email,
                    role=role,
                    org_id=st.session_state.org_id,
                    subject=subject,
                    expires_in_hours=expiry
                )

                 send_invite_email(email, token, expires_at)
                 st.success(f"Invite sent to {email}")

    with tab4:
        sub_tab1, sub_tab2 = st.tabs([
        "📤 Sent Request History",
        "📜 Received Request History"
        ])
        st.subheader("Incoming Student Record Requests")

        requests = get_pending_requests(st.session_state.org_id)

        if not requests:
            st.info("No pending requests.")
        else:
            for r in requests:
                st.write(f"Student ID: {r['global_student_id']}")

                col1, col2 = st.columns(2)

                if col1.button("Approve", key=f"approve_{r['id']}"):
                    update_request_status(r["id"], "approved")
                    st.success("Approved")
                    st.experimental_rerun()

                if col2.button("Reject", key=f"reject_{r['id']}"):
                    update_request_status(r["id"], "rejected")
                    st.warning("Rejected")
                    st.experimental_rerun()
        with sub_tab1:
            sent = get_sent_requests(st.session_state.org_id)

            if not sent:
                st.info("No requests sent.")
            else:
                st.dataframe(pd.DataFrame(sent))  

        # ---------------- HISTORY ----------------
        with sub_tab2:
            history = get_received_requests(st.session_state.org_id)

            if not history:
                st.info("No request history.")
            else:
                st.dataframe(pd.DataFrame(history))
    with tab5:
        st.subheader("🔍 View Shared Student Record")

        lookup_id = st.text_input("Enter Global Student ID")

        if st.button("Fetch Record"):
            record = get_shared_student_record(lookup_id, st.session_state.org_id)

            if record:
                 st.dataframe(pd.DataFrame(record))
            else:
                 st.error("No approved record found")
            # ---------------- SENT ----------------
    with tab6:
        st.subheader("🚪 Withdraw Organization")

        reason = st.text_area("Reason for Deactivation")

        if st.button("Request Deactivation"):
            raise_withdraw_request(st.session_state.org_id, reason)
            st.success("Withdrawal request sent to Platform Admin.")
    with tab7:
        st.subheader("Organization Database Tools")

        if st.button("Clear My Organization Predictions", key="clear_org_preds"):
            clear_predictions_by_org(st.session_state.org_id)
            st.success("Predictions cleared.")
            st.rerun()

