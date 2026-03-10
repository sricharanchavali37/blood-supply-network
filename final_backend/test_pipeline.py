"""
test_pipeline.py — Smart Blood Network Integration Test
Runs the full operational pipeline against the backend and verifies each step.

Usage:
    python test_pipeline.py
    python test_pipeline.py http://127.0.0.1:8000
"""

import sys
import json
import uuid
import datetime
import requests

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"

RUN_ID = uuid.uuid4().hex[:8]

# ---------- USERS ----------

HOSPITAL_ADMIN = {
    "email": f"admin_{RUN_ID}@gmail.com",
    "password": "AdminPass123!",
    "full_name": f"Hospital Admin {RUN_ID}",
    "role_id": 2,
}

LAB_TECH = {
    "email": f"labtech_{RUN_ID}@gmail.com",
    "password": "LabPass123!",
    "full_name": f"Lab Technician {RUN_ID}",
    "role_id": 3,
}

DONOR_USER = {
    "email": f"donor_{RUN_ID}@gmail.com",
    "password": "DonorPass123!",
    "full_name": f"Donor User {RUN_ID}",
    "role_id": 4,
}

# ---------- HOSPITAL ----------

HOSPITAL_DATA = {
    "name": f"City Blood Bank {RUN_ID}",
    "latitude": 17.3850,
    "longitude": 78.4867,
    "contact_email": f"hospital_{RUN_ID}@gmail.com",
    "contact_phone": "9000000000",
}

BLOOD_GROUP = "O+"

DONOR_LATITUDE = 17.3850
DONOR_LONGITUDE = 78.4867

BLOOD_UNITS_TO_ADD = 3

COLLECTION_DATE = (
    datetime.date.today() - datetime.timedelta(days=1)
).isoformat()


def request(method, path, token=None, json_body=None, expected_status=200):
    url = f"{BASE_URL}{path}"

    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.request(
        method,
        url,
        headers=headers,
        json=json_body,
        timeout=30,
    )

    if response.status_code != expected_status:
        print("\nFAILED REQUEST")
        print(method, path)
        print("Expected:", expected_status)
        print("Actual:", response.status_code)

        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print(response.text)

        sys.exit(1)

    try:
        return response.json()
    except Exception:
        return {}


def main():
    print("\nSmart Blood Network Pipeline Test")
    print("Base URL:", BASE_URL)
    print("Run ID:", RUN_ID)

    # ---------- STEP 1 ----------
    print("\nSTEP 1 Register Hospital Admin")
    data = request("POST", "/auth/register", json_body=HOSPITAL_ADMIN, expected_status=201)
    admin_user_id = data["id"]  # noqa: F841

    # ---------- STEP 2 ----------
    print("STEP 2 Login Hospital Admin")
    data = request(
        "POST",
        "/auth/login",
        json_body={"email": HOSPITAL_ADMIN["email"], "password": HOSPITAL_ADMIN["password"]},
        expected_status=200,
    )
    admin_token = data["access_token"]

    # ---------- STEP 3 ----------
    print("STEP 3 Create Hospital")
    data = request("POST", "/hospitals", token=admin_token, json_body=HOSPITAL_DATA, expected_status=201)
    hospital_id = data["id"]

    # ---------- STEP 4 ----------
    print("STEP 4 Register Lab Technician")
    data = request("POST", "/auth/register", json_body=LAB_TECH, expected_status=201)
    lab_user_id = data["id"]  # noqa: F841

    # ---------- STEP 5 ----------
    print("STEP 5 Login Lab Technician")
    data = request(
        "POST",
        "/auth/login",
        json_body={"email": LAB_TECH["email"], "password": LAB_TECH["password"]},
        expected_status=200,
    )
    lab_token = data["access_token"]

    # ---------- STEP 6 ----------
    print("STEP 6 Add Blood Units")
    for _ in range(BLOOD_UNITS_TO_ADD):
        request(
            "POST",
            "/inventory/units",
            token=lab_token,
            json_body={
                "blood_group": BLOOD_GROUP,
                "quantity_ml": 450,
                "collection_date": COLLECTION_DATE,
                "hospital_id": hospital_id,
            },
            expected_status=201,
        )

    # ---------- STEP 7 ----------
    print("STEP 7 Shortage Prediction")
    request(
        "POST",
        "/shortage-prediction/forecast",
        token=admin_token,
        json_body={"hospital_id": hospital_id, "blood_group": BLOOD_GROUP, "forecast_hours": 24},
        expected_status=200,
    )

    # ---------- STEP 8 ----------
    print("STEP 8 Decision Engine")
    data = request(
        "POST",
        "/decision-engine/orchestrate",
        token=admin_token,
        json_body={
            "hospital_id": hospital_id,
            "blood_group": BLOOD_GROUP,
            "forecast_hours": 24,
            "search_radius_km": 100,
            "max_donors": 10,
        },
        expected_status=200,
    )

    decision = data.get("decision", {})
    alert_id = decision.get("alert_id", 0)

    # ---------- STEP 9 ----------
    print("STEP 9 Register Donor User")
    data = request("POST", "/auth/register", json_body=DONOR_USER, expected_status=201)
    donor_user_id = data["id"]

    # ---------- STEP 10 ----------
    print("STEP 10 Login Donor")
    data = request(
        "POST",
        "/auth/login",
        json_body={"email": DONOR_USER["email"], "password": DONOR_USER["password"]},
        expected_status=200,
    )
    donor_token = data["access_token"]

    # ---------- STEP 11 ----------
    print("STEP 11 Register Donor Profile")
    data = request(
        "POST",
        "/donors/register",
        token=donor_token,
        json_body={
            "user_id": donor_user_id,
            "blood_group": BLOOD_GROUP,
            "latitude": DONOR_LATITUDE,
            "longitude": DONOR_LONGITUDE,
        },
        expected_status=201,
    )
    donor_id = data["id"]

    # ---------- STEP 12 ----------
    print("STEP 12 Donor Response")
    if alert_id:
        request(
            "POST",
            "/donors/response",
            token=donor_token,
            json_body={
                "donor_id": donor_id,
                "alert_id": alert_id,
                "response_type": "accepted",
            },
            expected_status=201,
        )

    # ---------- STEP 13 ----------
    print("STEP 13 Record Donation")
    request(
        "POST",
        "/donors/donation",
        token=lab_token,
        json_body={
            "donor_id": donor_id,
            "donation_date": datetime.date.today().isoformat(),
        },
        expected_status=200,
    )

    # ---------- STEP 14 ----------
    print("STEP 14 Verify Donor")
    data = request("GET", f"/donors/{donor_id}", token=donor_token, expected_status=200)
    assert data["total_donations"] >= 1

    # ---------- STEP 15 ----------
    print("STEP 15 Analytics Check")
    analytics = [
        "/analytics/system-overview",
        "/analytics/alert-performance",
        "/analytics/blood-group-stability",
        "/analytics/donor-leaderboard",
        "/analytics/hospital-shortage-summary",
        "/analytics/donation-activity",
    ]
    for route in analytics:
        request("GET", route, token=admin_token, expected_status=200)

    print("\nPIPELINE COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
