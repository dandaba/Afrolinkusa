import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import requests

# ============================================================
# 1. CONFIGURATION & CLIENTS
# ============================================================
try:
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    # Google Places API key is OPTIONAL — the directory works without it,
    # just without the "suggested from Google" fallback when local results are thin.
    GOOGLE_PLACES_API_KEY = st.secrets.get("GOOGLE_PLACES_API_KEY", "")
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.stop()

st.set_page_config(page_title="African Business Directory", page_icon="🌍", layout="wide")

# ============================================================
# 2. CONSTANTS
# ============================================================
CATEGORIES = [
    "Restaurant", "Grocery & Market", "Beauty & Hair", "Fashion & Retail",
    "Professional Services", "Event & Catering", "Import / Export",
    "Health & Wellness", "Arts & Media", "Other",
]

# All 54 African countries — this directory is NOT limited to AGOA-eligible
# countries; it covers any business with African ownership or heritage.
AFRICAN_COUNTRIES = [
    "Algeria","Angola","Benin","Botswana","Burkina Faso","Burundi","Cabo Verde",
    "Cameroon","Central African Republic","Chad","Comoros","Congo (Republic)",
    "Congo (DRC)","Djibouti","Egypt","Equatorial Guinea","Eritrea","Eswatini",
    "Ethiopia","Gabon","Gambia","Ghana","Guinea","Guinea-Bissau","Ivory Coast",
    "Kenya","Lesotho","Liberia","Libya","Madagascar","Malawi","Mali",
    "Mauritania","Mauritius","Morocco","Mozambique","Namibia","Niger","Nigeria",
    "Rwanda","Sao Tome and Principe","Senegal","Seychelles","Sierra Leone",
    "Somalia","South Africa","South Sudan","Sudan","Tanzania","Togo","Tunisia",
    "Uganda","Zambia","Zimbabwe","Pan-African / Multiple",
]

US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
]

# ============================================================
# 3. GOOGLE PLACES FALLBACK SEARCH (optional enhancement)
# Used only when local directory results are thin, to suggest businesses
# that might qualify but haven't been added yet. Never auto-inserted —
# always requires human claim/submission before appearing in the directory.
# ============================================================
def search_google_places(query: str, max_results: int = 5) -> list:
    if not GOOGLE_PLACES_API_KEY:
        return []
    try:
        resp = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
                "X-Goog-FieldMask": (
                    "places.displayName,places.formattedAddress,"
                    "places.id,places.internationalPhoneNumber,"
                    "places.websiteUri"
                ),
            },
            json={"textQuery": query, "maxResultCount": max_results},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("places", [])
    except Exception:
        # Fail silently — Google fallback is a nice-to-have, not required
        return []


# ============================================================
# 4. DATABASE HELPERS
# ============================================================
def fetch_businesses(category: str = None, state: str = None, search: str = None) -> pd.DataFrame:
    """Fetch approved businesses matching filters."""
    query = supabase.table("afrousa_business").select("*").eq("status", "approved")

    if category and category != "All Categories":
        query = query.eq("category", category)
    if state and state != "All States":
        query = query.eq("state", state)

    try:
        result = query.execute()
        df = pd.DataFrame(result.data)
    except Exception as e:
        st.error(f"Could not load listings: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    if search:
        s = search.strip().lower()
        mask = (
            df["business_name"].str.lower().str.contains(s, na=False) |
            df["description"].fillna("").str.lower().str.contains(s, na=False) |
            df["city"].fillna("").str.lower().str.contains(s, na=False)
        )
        df = df[mask]

    return df


def submit_business(data: dict) -> bool:
    try:
        data["status"] = "pending"
        data["is_verified"] = False
        data["created_at"] = datetime.utcnow().isoformat()
        supabase.table("afrousa_business").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Submission failed: {e}")
        return False


def fetch_by_status(status: str) -> pd.DataFrame:
    """Fetch all businesses with a given status (pending / approved / rejected)."""
    try:
        result = (
            supabase.table("afrousa_business")
            .select("*")
            .eq("status", status)
            .order("created_at", desc=True)
            .execute()
        )
        return pd.DataFrame(result.data)
    except Exception as e:
        st.error(f"Could not load submissions: {e}")
        return pd.DataFrame()


def update_status(business_id, new_status: str) -> bool:
    """Approve or reject a business by updating its status."""
    try:
        supabase.table("afrousa_business").update(
            {"status": new_status}
        ).eq("id", business_id).execute()
        return True
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False


def toggle_verified(business_id, verified: bool) -> bool:
    """Mark a business as verified/unverified."""
    try:
        supabase.table("afrousa_business").update(
            {"is_verified": verified}
        ).eq("id", business_id).execute()
        return True
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False


# ============================================================
# 5. SESSION STATE
# ============================================================
if "prefill_name" not in st.session_state:
    st.session_state.prefill_name = ""
if "prefill_address" not in st.session_state:
    st.session_state.prefill_address = ""
if "active_tab" not in st.session_state:
    st.session_state.active_tab = 0
if "admin_authed" not in st.session_state:
    st.session_state.admin_authed = False

# ============================================================
# 6. UI
# ============================================================
st.title("🌍 African Business Directory")
st.caption("Discover African-owned restaurants, retail, and services across the United States")

tab_browse, tab_add, tab_admin = st.tabs(["🔍 Browse Directory", "➕ Add Your Business", "🔐 Admin"])

# ------------------------------------------------------------
# TAB 1 — BROWSE
# ------------------------------------------------------------
with tab_browse:
    st.subheader("Find a Business")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_term = st.text_input("Search by name, description, or city", placeholder="e.g. Ethiopian, braids, Houston")
    with col2:
        category_filter = st.selectbox("Category", ["All Categories"] + CATEGORIES)
    with col3:
        state_filter = st.selectbox("State", ["All States"] + US_STATES)

    results = fetch_businesses(
        category=category_filter, state=state_filter, search=search_term
    )

    if results.empty:
        st.info("No listings match your search yet.")

        # Fallback: suggest businesses via Google Places if a search term was entered
        if search_term and GOOGLE_PLACES_API_KEY:
            location_hint = f" in {state_filter}" if state_filter != "All States" else ""
            suggestions = search_google_places(f"{search_term}{location_hint}")

            if suggestions:
                st.markdown("#### 🔎 Found on Google — not yet in our directory")
                st.caption("These aren't confirmed as African-owned. If one of these is your business, claim it below.")
                for place in suggestions:
                    name = place.get("displayName", {}).get("text", "Unknown")
                    address = place.get("formattedAddress", "")
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"**{name}**")
                            st.caption(address)
                        with c2:
                            if st.button("Claim / Add", key=f"claim_{place.get('id')}"):
                                st.session_state.prefill_name = name
                                st.session_state.prefill_address = address
                                st.session_state.active_tab = 1
                                st.rerun()
        elif search_term and not GOOGLE_PLACES_API_KEY:
            st.caption(
                "💡 Tip: Google Places suggestions are disabled — add a "
                "`GOOGLE_PLACES_API_KEY` to secrets to enable fallback search."
            )
    else:
        st.success(f"Found **{len(results)}** business{'es' if len(results) != 1 else ''}")

        for _, biz in results.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1, 3])
                with c1:
                    if biz.get("photo_url"):
                        st.image(biz["photo_url"], use_container_width=True)
                    else:
                        st.markdown("### 🏪")
                with c2:
                    badge = "✅ Verified" if biz.get("is_verified") else ""
                    st.markdown(f"### {biz['business_name']} {badge}")
                    st.caption(f"{biz.get('category', '')} · {biz.get('country_connection', '')}")
                    if biz.get("description"):
                        st.write(biz["description"])
                    loc_parts = [p for p in [biz.get("address"), biz.get("city"), biz.get("state")] if p]
                    if loc_parts:
                        st.write(f"📍 {', '.join(loc_parts)}")
                    contact_cols = st.columns(3)
                    if biz.get("phone"):
                        contact_cols[0].write(f"📞 {biz['phone']}")
                    if biz.get("website"):
                        contact_cols[1].markdown(f"[🔗 Website]({biz['website']})")
                    if biz.get("email"):
                        contact_cols[2].write(f"✉️ {biz['email']}")

# ------------------------------------------------------------
# TAB 2 — ADD YOUR BUSINESS
# ------------------------------------------------------------
with tab_add:
    st.subheader("List Your Business")
    st.caption(
        "Submissions are reviewed within 24–48 hours before appearing in the directory. "
        "There is no fee to list a basic profile."
    )

    with st.form("add_business_form", clear_on_submit=False):
        business_name = st.text_input("Business Name*", value=st.session_state.prefill_name)
        category = st.selectbox("Category*", CATEGORIES)
        country_connection = st.selectbox("Country / Heritage Connection*", AFRICAN_COUNTRIES)
        description = st.text_area("Description", placeholder="What does your business offer?", max_chars=500)

        st.markdown("**Location**")
        address = st.text_input("Street Address", value=st.session_state.prefill_address)
        col_c, col_s, col_z = st.columns(3)
        city = col_c.text_input("City*")
        state = col_s.selectbox("State*", US_STATES)
        zip_code = col_z.text_input("ZIP Code")

        st.markdown("**Contact**")
        col_p, col_w = st.columns(2)
        phone = col_p.text_input("Phone")
        website = col_w.text_input("Website", placeholder="https://")
        email = st.text_input("Email*", placeholder="you@business.com")
        photo_url = st.text_input(
            "Photo URL (optional)",
            help="Paste a link to a photo of your storefront, logo, or product. "
                 "Direct image upload is not yet supported — use an image hosting link.",
        )

        submitted = st.form_submit_button("Submit for Review", type="primary")

        if submitted:
            errors = []
            if not business_name.strip():
                errors.append("Business name is required.")
            if not city.strip():
                errors.append("City is required.")
            if not email.strip() or "@" not in email:
                errors.append("A valid email is required.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                success = submit_business({
                    "business_name":       business_name.strip(),
                    "category":            category,
                    "country_connection":  country_connection,
                    "description":         description.strip(),
                    "address":             address.strip(),
                    "city":                city.strip(),
                    "state":               state,
                    "zip":                 zip_code.strip(),
                    "phone":               phone.strip(),
                    "website":             website.strip(),
                    "email":               email.strip(),
                    "photo_url":           photo_url.strip(),
                })
                if success:
                    st.success(
                        "✅ Thank you! Your business has been submitted for review. "
                        "You'll see it appear in the directory once approved."
                    )
                    st.session_state.prefill_name = ""
                    st.session_state.prefill_address = ""

# ------------------------------------------------------------
# TAB 3 — ADMIN
# Password-gated moderation panel. Approve/reject/verify submissions
# without needing to leave the app and go into Supabase manually.
# ------------------------------------------------------------
with tab_admin:
    ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", None)

    if not ADMIN_PASSWORD:
        st.error(
            "Admin panel is not configured. Add `ADMIN_PASSWORD` to your app secrets "
            "to enable this tab."
        )
    elif not st.session_state.admin_authed:
        st.subheader("Admin Login")
        pw_input = st.text_input("Password", type="password", key="admin_pw_input")
        if st.button("Log In"):
            if pw_input == ADMIN_PASSWORD:
                st.session_state.admin_authed = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        col_head, col_logout = st.columns([4, 1])
        with col_head:
            st.subheader("Moderation Queue")
        with col_logout:
            if st.button("Log Out"):
                st.session_state.admin_authed = False
                st.rerun()

        status_tab_pending, status_tab_approved, status_tab_rejected = st.tabs(
            ["🕓 Pending", "✅ Approved", "❌ Rejected"]
        )

        # --- Pending submissions: approve or reject ---
        with status_tab_pending:
            pending = fetch_by_status("pending")
            if pending.empty:
                st.info("No pending submissions. You're all caught up.")
            else:
                st.caption(f"{len(pending)} submission(s) awaiting review")
                for _, biz in pending.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"**{biz['business_name']}**")
                            st.caption(f"{biz.get('category', '')} · {biz.get('country_connection', '')}")
                            loc_parts = [p for p in [biz.get("address"), biz.get("city"), biz.get("state")] if p]
                            if loc_parts:
                                st.write(f"📍 {', '.join(loc_parts)}")
                            if biz.get("description"):
                                st.write(biz["description"])
                            contact_bits = [
                                f"📞 {biz['phone']}" if biz.get("phone") else None,
                                f"✉️ {biz['email']}" if biz.get("email") else None,
                                f"🔗 {biz['website']}" if biz.get("website") else None,
                            ]
                            st.caption(" · ".join(b for b in contact_bits if b))
                            if biz.get("photo_url"):
                                st.image(biz["photo_url"], width=200)
                        with c2:
                            if st.button("✅ Approve", key=f"approve_{biz['id']}", type="primary"):
                                if update_status(biz["id"], "approved"):
                                    st.success("Approved!")
                                    st.rerun()
                            if st.button("❌ Reject", key=f"reject_{biz['id']}"):
                                if update_status(biz["id"], "rejected"):
                                    st.warning("Rejected.")
                                    st.rerun()

        # --- Approved listings: toggle verified badge, or move back to pending/reject ---
        with status_tab_approved:
            approved = fetch_by_status("approved")
            if approved.empty:
                st.info("No approved listings yet.")
            else:
                st.caption(f"{len(approved)} live listing(s)")
                for _, biz in approved.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3, 1, 1])
                        with c1:
                            badge = "✅ Verified" if biz.get("is_verified") else "— Not verified"
                            st.markdown(f"**{biz['business_name']}** · {badge}")
                            st.caption(f"{biz.get('city', '')}, {biz.get('state', '')}")
                        with c2:
                            is_verified = bool(biz.get("is_verified"))
                            new_val = st.checkbox(
                                "Verified", value=is_verified, key=f"verify_{biz['id']}"
                            )
                            if new_val != is_verified:
                                if toggle_verified(biz["id"], new_val):
                                    st.rerun()
                        with c3:
                            if st.button("Remove", key=f"remove_{biz['id']}"):
                                if update_status(biz["id"], "rejected"):
                                    st.warning("Removed from directory.")
                                    st.rerun()

        # --- Rejected: allow re-approval if you change your mind ---
        with status_tab_rejected:
            rejected = fetch_by_status("rejected")
            if rejected.empty:
                st.info("No rejected submissions.")
            else:
                st.caption(f"{len(rejected)} rejected submission(s)")
                for _, biz in rejected.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"**{biz['business_name']}**")
                            st.caption(f"{biz.get('city', '')}, {biz.get('state', '')}")
                        with c2:
                            if st.button("↩️ Restore & Approve", key=f"restore_{biz['id']}"):
                                if update_status(biz["id"], "approved"):
                                    st.success("Restored!")
                                    st.rerun()
