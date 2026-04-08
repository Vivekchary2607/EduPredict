import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier

# ---------------- Load dataset ----------------
df = pd.read_csv("student_class_wise_dataset.csv")
df = df.drop(columns=["id", "first_name", "last_name", "email"])

# ---------------- Encode categorical ----------------
encoder_cols = [
    "gender",
    "part_time_job",
    "extracurricular_activities",
    "career_aspiration"
]

for col in encoder_cols:
    encoder = joblib.load(f"{col}_encoder.pkl")
    df[col] = encoder.transform(df[col].astype(str))

# ---------------- Feature sets ----------------
FEATURES = {
    "primary": [
        "math_score", "english_score", "physics_score",
        "absence_days", "extracurricular_activities"
    ],
    "middle": [
        "math_score", "english_score", "physics_score",
        "absence_days", "weekly_self_study_hours",
        "extracurricular_activities"
    ],
    "secondary": [
        "math_score", "english_score", "physics_score",
        "biology_score", "chemistry_score",
        "history_score", "geography_score",
        "absence_days", "weekly_self_study_hours",
        "extracurricular_activities",
        "career_aspiration", "part_time_job"
    ]
}

# ---------------- PASS/FAIL logic ----------------
def compute_target(row, group):
    if group in ["primary", "middle"]:
        scores = ["math_score", "english_score", "physics_score"]
        return int((row[scores] >= 40).sum() >= 2)
    else:
        scores = [
            "math_score", "english_score", "physics_score",
            "biology_score", "chemistry_score",
            "history_score", "geography_score"
        ]
        return int((row[scores] >= 40).sum() >= 5)

# ---------------- Train per group ----------------
for group in ["primary", "middle", "secondary"]:
    group_df = df[df["class_group"] == group].copy()
    group_df["pass_fail"] = group_df.apply(lambda r: compute_target(r, group), axis=1)

    X = group_df[FEATURES[group]]
    y = group_df["pass_fail"]

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced"
    )

    model.fit(X, y)

    joblib.dump(model, f"model_{group}.pkl")
    joblib.dump(FEATURES[group], f"columns_{group}.pkl")

    print(f"✅ Trained & saved {group.upper()} model")
