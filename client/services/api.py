# client/services/api.py
from __future__ import annotations

import requests
from typing import Any

from . import session

TIMEOUT = 15


class ApiError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


# -------------------------
# Low-level helpers
# -------------------------
def _headers() -> dict:
    h = {"Accept": "application/json"}
    if session.TOKEN:
        h["Authorization"] = f"Bearer {session.TOKEN}"
    return h


def _handle_json(r: requests.Response, url: str):
    try:
        data = r.json()
    except Exception:
        body = (r.text or "")[:500]
        raise ApiError(r.status_code, f"Invalid JSON from server ({url}): {body}")

    if not r.ok:
        if isinstance(data, dict):
            msg = data.get("detail") or data.get("message") or str(data)
        else:
            msg = str(data)
        raise ApiError(r.status_code, f"{url}: {msg}")

    return data
# -------------------------
# Auth/session helpers
# -------------------------

def _on_unauthorized():
    session.TOKEN = None
    session.ROLE = None
    session.USERNAME = None

    cb = getattr(session, "ON_UNAUTHORIZED", None)
    if callable(cb):
        cb()


def _request(method: str, url: str, params=None, json=None, data=None):
    full = f"{session.API_BASE}{url}"
    r = requests.request(
        method=method,
        url=full,
        params=params,
        json=json,
        data=data,
        headers=_headers(),
        timeout=TIMEOUT,
    )

    # ✅ interceptor مثل axios
    if r.status_code == 401:
        _on_unauthorized()

    return _handle_json(r, url)

def _get(url: str, params=None):
    return _request("GET", url, params=params)


def _post(url: str, json=None, data=None):
    return _request("POST", url, json=json, data=data)


# -------------------------
# Companies (needed for company_id)
# -------------------------
_COMPANY_CACHE: dict[str, int] = {}  # name_lower -> id


def companies_list() -> list[dict]:
    res = _get("/companies")
    return res if isinstance(res, list) else (res.get("items") or res.get("companies") or [])


def _refresh_company_cache():
    global _COMPANY_CACHE
    _COMPANY_CACHE = {}
    rows = companies_list() or []
    for c in rows:
        name = (c.get("name") or "").strip()
        cid = c.get("id")
        if name and cid is not None:
            _COMPANY_CACHE[name.lower()] = int(cid)


def _resolve_company_id(company: int | str | None) -> int | None:
    if company is None:
        return None

    if isinstance(company, int):
        return company

    s = (company or "").strip()
    if not s or s.lower() == "all":
        return None

    if not _COMPANY_CACHE:
        _refresh_company_cache()

    cid = _COMPANY_CACHE.get(s.lower())
    if cid is None:
        _refresh_company_cache()
        cid = _COMPANY_CACHE.get(s.lower())

    if cid is None:
        raise RuntimeError(
            f"Unknown company '{company}'.\n"
            "Make sure server has /companies endpoint returning correct names/ids."
        )
    return cid


# =========================================================
# LOGIN
# =========================================================
def login(username: str, password: str):
    try:
        data = _post("/auth/login", json={"username": username, "password": password})
    except Exception:
        data = None

    if data is None:
        try:
            data = _post("/login", json={"username": username, "password": password})
        except Exception:
            data = None

    if data is None:
        url = f"{session.API_BASE}/auth/token"
        r = requests.post(
            url,
            headers={"Accept": "application/json"},
            data={"username": username, "password": password},
            timeout=10,
        )
        data = _handle_json(r, "/auth/token")

    if not isinstance(data, dict):
        raise RuntimeError("Login response is not a JSON object.")

    token = data.get("token") or data.get("access_token")
    if token:
        session.TOKEN = token

    if data.get("role"):
        session.ROLE = data["role"]
    if data.get("username"):
        session.USERNAME = data["username"]

    return data


def change_password(username: str, old_password: str, new_password: str):
    return _post(
        "/auth/change-password",
        json={
            "username": username,
            "old_password": old_password,
            "new_password": new_password,
        },
    )


# =========================================================
# EMPLOYEES / CATEGORIES
# =========================================================
def employees_list():
    return _get("/employees")


def employees_add(staff_id: str, name: str, company: str = ""):
    return _post("/employees", json={"staff_id": staff_id, "name": name, "company": company})


def employees_update(id: int, staff_id: str, name: str, company: str = ""):
    return _request("PUT", f"/employees/{id}", json={"staff_id": staff_id, "name": name, "company": company})


def employees_delete(id: int):
    return _request("DELETE", f"/employees/{id}")


def categories_update(id: int, name: str, kind: str, budget: float | None = None):
    payload: dict[str, Any] = {"name": name, "kind": kind}
    if budget is not None:
        payload["budget"] = budget
    return _request("PUT", f"/categories/{id}", json=payload)


def categories_list():
    return _get("/categories")


def categories_add(name: str, kind: str, budget: float | None = None):
    payload: dict[str, Any] = {"name": name, "kind": kind}
    if budget is not None:
        payload["budget"] = budget
    return _post("/categories", json=payload)


def categories_delete(id: int):
    return _request("DELETE", f"/categories/{id}")


# =========================================================
# TREE-BASED CATEGORIES
# =========================================================
def categories_tree_list(company_id: int | None = None):
    params = {}
    if company_id is not None:
        params["company_id"] = company_id
    return _get("/categories-tree/", params=params)


def categories_tree_flat(company_id: int | None = None):
    params = {}
    if company_id is not None:
        params["company_id"] = company_id
    return _get("/categories-tree/flat", params=params)


def categories_tree_add(code: str, name: str, parent_id: int | None, company_id: int,
                       category_type: str, kind: str, budget: float = 0.0, sort_order: int = 0):
    payload = {
        "code": code,
        "name": name,
        "parent_id": parent_id,
        "company_id": company_id,
        "category_type": category_type,
        "kind": kind,
        "budget": budget,
        "sort_order": sort_order
    }
    return _post("/categories-tree/", json=payload)


def categories_tree_update(id: int, **kwargs):
    return _request("PUT", f"/categories-tree/{id}", json=kwargs)


def categories_tree_move(id: int, new_parent_id: int | None = None, new_sort_order: int | None = None):
    payload = {}
    if new_parent_id is not None:
        payload["new_parent_id"] = new_parent_id
    if new_sort_order is not None:
        payload["new_sort_order"] = new_sort_order
    return _post(f"/categories-tree/{id}/move", json=payload)


def categories_tree_delete(id: int, cascade: bool = False):
    endpoint = f"/categories-tree/{id}/cascade" if cascade else f"/categories-tree/{id}"
    return _request("DELETE", endpoint)


# =========================================================
# PROJECTS
# =========================================================
def projects_list(company_id: int | None = None, status: str | None = None):
    params = {}
    if company_id is not None:
        params["company_id"] = company_id
    if status is not None:
        params["status"] = status
    return _get("/projects/", params=params)


def projects_get(project_id: int):
    return _get(f"/projects/{project_id}")


def projects_add(code: str, name: str, company_id: int, description: str | None = None,
                status: str = "on_hold", start_date: str | None = None, end_date: str | None = None,
                budget: float = 0.0, linked_category_ids: str | None = None):
    payload = {
        "code": code,
        "name": name,
        "company_id": company_id,
        "description": description,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
        "budget": budget,
        "linked_category_ids": linked_category_ids
    }
    return _post("/projects/", json=payload)


def projects_update(project_id: int, **kwargs):
    return _request("PUT", f"/projects/{project_id}", json=kwargs)


def projects_update_status(project_id: int, status: str, actual_completion_date: str | None = None):
    payload = {"status": status}
    if actual_completion_date:
        payload["actual_completion_date"] = actual_completion_date
    return _request("PATCH", f"/projects/{project_id}/status", json=payload)


def projects_delete(project_id: int):
    return _request("DELETE", f"/projects/{project_id}")


def projects_get_status_options():
    return _get("/projects/status-options")


def projects_get_company_summary(company_id: int):
    return _get(f"/projects/company/{company_id}/summary")


# =========================================================
# TIMESHEET
# =========================================================
def timesheet_get_sheet(employee_id: int, year: int, month: int, company: int | str | None = None):
    company_id = _resolve_company_id(company)
    params = {"employee_id": employee_id, "year": year, "month": month}
    if company_id is not None:
        params["company_id"] = company_id
    return _get("/timesheet/sheet", params)


def timesheet_bulk_upsert(employee_id: int, year: int, month: int, company: int | str, entries: list[dict]):
    company_id = _resolve_company_id(company)
    if company_id is None:
        raise RuntimeError("Monthly save requires a specific company (not All).")

    payload = {
        "employee_id": employee_id,
        "year": year,
        "month": month,
        "company_id": company_id,
        "entries": entries,
    }
    return _post("/timesheet/bulk-upsert", json=payload)


def timesheet_get_daily_sheet(employee_id: int, date: str, company: int | str | None = None):
    company_id = _resolve_company_id(company)
    params = {"employee_id": employee_id, "date": date}
    if company_id is not None:
        params["company_id"] = company_id
    return _get("/timesheet/daily-sheet", params)


def timesheet_daily_bulk_upsert(employee_id: int, date: str, company: int | str, entries: list[dict]):
    company_id = _resolve_company_id(company)
    if company_id is None:
        raise RuntimeError("Daily save requires a specific company (not All).")

    payload = {"employee_id": employee_id, "date": date, "company_id": company_id, "entries": entries}
    return _post("/timesheet/daily-bulk-upsert", json=payload)


# =========================================================
# PAYMENTS
# =========================================================
def payment_get(employee_id: int, year: int, month: int):
    return _get("/payments", {"employee_id": employee_id, "year": year, "month": month})


def payment_upsert(employee_id: int, year: int, month: int, amount: float):
    return _post("/payments/upsert", json={"employee_id": employee_id, "year": year, "month": month, "amount": amount})


def salary_list():
    return _get("/payments/salaries")


def salary_upsert_bulk(payload: list[dict]):
    return _post("/payments/salaries/bulk-upsert", json=payload)


# =========================================================
# REPORTS
# =========================================================
def report_allocation(year: int, month: int, company: int | str | None = None, employee_id: int | None = None):
    company_id = _resolve_company_id(company)
    params = {"year": year, "month": month}
    if company_id is not None:
        params["company_id"] = company_id
    if employee_id is not None:
        params["employee_id"] = employee_id
    return _get("/reports/allocation", params)

def report_stage_projects(year: int, month: int, company: int | str, employee_id: int | None = None):
    company_id = _resolve_company_id(company)
    if company_id is None:
        raise RuntimeError("stage-projects requires a specific company (not All).")

    params = {"year": year, "month": month, "company_id": company_id}
    if employee_id is not None:
        params["employee_id"] = employee_id

    return _get("/reports/stage-projects", params)


def report_matrix(year: int, month: int, company: int | str | None = None, employee_id: int | None = None):
    company_id = _resolve_company_id(company)
    params = {"year": year, "month": month}
    if company_id is not None:
        params["company_id"] = company_id
    if employee_id is not None:
        params["employee_id"] = employee_id
    return _get("/reports/matrix", params)

def report_matrix_tree(year: int, month: int, company: int | str, employee_id: int | None = None):
    company_id = _resolve_company_id(company)
    if company_id is None:
        raise RuntimeError("matrix-tree requires a specific company (not All).")
    params = {"year": year, "month": month, "company_id": company_id}
    if employee_id is not None:
        params["employee_id"] = employee_id
    return _get("/reports/matrix-tree", params)
def report_matrix_tree2(year: int, month: int, company: int | str, employee_id: int | None = None):
    company_id = _resolve_company_id(company)
    if company_id is None:
        raise RuntimeError("matrix-tree2 requires a specific company (not All).")
    params = {"year": year, "month": month, "company_id": company_id}
    if employee_id is not None:
        params["employee_id"] = employee_id
    return _get("/reports/matrix-tree2", params)

def report_matrix_excel(year: int, month: int, company: int | str, employee_id: int | None = None):
    company_id = _resolve_company_id(company)
    if company_id is None:
        raise RuntimeError("matrix-excel requires a specific company (not All).")
    params = {"year": year, "month": month, "company_id": company_id}
    if employee_id is not None:
        params["employee_id"] = employee_id
    return _get("/reports/matrix-excel", params)

def report_matrix_leaf_project(year: int, month: int, company: int | str, employee_id: int | None = None):
    company_id = _resolve_company_id(company)
    if company_id is None:
        raise RuntimeError("matrix-leaf-project requires a specific company (not All).")
    params = {"year": year, "month": month, "company_id": company_id}
    if employee_id is not None:
        params["employee_id"] = employee_id
    return _get("/reports/matrix-leaf-project", params)
