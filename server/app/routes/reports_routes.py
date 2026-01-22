from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from ..db import get_db
from ..models import TimeEntry, Payment, Employee, Category, Company, EmployeeSalary
from ..models import Project
from ..deps import require_roles
from ..config import ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/allocation")
def allocation(year: int, month: int,
               employee_id: int | None = Query(None),
               company_id: str | None = Query(None),
               category_kind: str | None = Query(None),  # overhead, stage, project_name
               db: Session = Depends(get_db),
               _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))):
    """
    Allocation table per (employee, category) aggregated across ALL TimeEntry rows
    (fixes: hours not summing when same category used across multiple projects).

    - hours = SUM(TimeEntry.hours) for that employee/category/company (if company filter applied)
    - total_hours = total hours for that employee in the period (all categories)
    - percent/allocated: computed inside company bucket, then salary split by company share.
    """
    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1.12")

    # Convert company_id string to actual company ID
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            actual_company_id = int(company_id)
        except ValueError:
            company = db.query(Company).filter(Company.name == company_id).first()
            if company:
                actual_company_id = company.id

    # ---- categories list (used to include 0 rows) ----
    categories_q = db.query(Category)
    if category_kind:
        categories_q = categories_q.filter(Category.kind == category_kind)
    all_categories = categories_q.all()

    # ---- employees to include ----
    employees_q = db.query(Employee)
    if employee_id:
        employees_q = employees_q.filter(Employee.id == employee_id)

    if actual_company_id:
        # only employees who have entries in that company/month (keeps list tight)
        employees_q = (
            employees_q.join(TimeEntry, TimeEntry.employee_id == Employee.id)
            .filter(TimeEntry.year == year, TimeEntry.month == month, TimeEntry.company_id == actual_company_id)
            .distinct()
        )

    all_employees = employees_q.all()

    # ---- aggregated hours per (emp, company, category) ----
    agg_q = db.query(
        TimeEntry.employee_id.label("employee_id"),
        TimeEntry.company_id.label("company_id"),
        TimeEntry.category_id.label("category_id"),
        func.coalesce(func.sum(TimeEntry.hours), 0.0).label("hours"),
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
    )

    if employee_id:
        agg_q = agg_q.filter(TimeEntry.employee_id == employee_id)
    if actual_company_id:
        agg_q = agg_q.filter(TimeEntry.company_id == actual_company_id)
    if category_kind:
        agg_q = agg_q.join(Category, Category.id == TimeEntry.category_id).filter(Category.kind == category_kind)

    agg_q = agg_q.group_by(TimeEntry.employee_id, TimeEntry.company_id, TimeEntry.category_id)
    agg_rows = agg_q.all()

    hours_map = {(int(eid), int(cid_comp), int(cat_id)): float(h or 0.0)
                 for eid, cid_comp, cat_id, h in agg_rows}

    # ---- totals per employee (all companies) ----
    total_emp_q = db.query(
        TimeEntry.employee_id,
        func.coalesce(func.sum(TimeEntry.hours), 0.0).label("total_hours"),
    ).filter(TimeEntry.year == year, TimeEntry.month == month)

    if employee_id:
        total_emp_q = total_emp_q.filter(TimeEntry.employee_id == employee_id)

    totals_all = {int(eid): float(h or 0.0) for eid, h in total_emp_q.group_by(TimeEntry.employee_id).all()}

    # ---- totals per employee per company (for pct within company + salary split) ----
    total_emp_comp_q = db.query(
        TimeEntry.employee_id,
        TimeEntry.company_id,
        func.coalesce(func.sum(TimeEntry.hours), 0.0).label("total_hours"),
    ).filter(TimeEntry.year == year, TimeEntry.month == month)

    if employee_id:
        total_emp_comp_q = total_emp_comp_q.filter(TimeEntry.employee_id == employee_id)
    if actual_company_id:
        total_emp_comp_q = total_emp_comp_q.filter(TimeEntry.company_id == actual_company_id)

    totals_by_company = {(int(eid), int(cid_comp)): float(h or 0.0)
                         for eid, cid_comp, h in total_emp_comp_q.group_by(TimeEntry.employee_id, TimeEntry.company_id).all()}

    # ---- payments / salaries ----
    pays_q = db.query(Payment.employee_id, Payment.amount).filter(Payment.year == year, Payment.month == month)
    if employee_id:
        pays_q = pays_q.filter(Payment.employee_id == employee_id)
    pays = {int(eid): float(a or 0.0) for eid, a in pays_q.all()}

    salaries_q = db.query(EmployeeSalary.employee_id, EmployeeSalary.base_salary)
    if employee_id:
        salaries_q = salaries_q.filter(EmployeeSalary.employee_id == employee_id)
    salaries = {int(eid): float(a or 0.0) for eid, a in salaries_q.all()}

    # ---- companies lookup ----
    comp_by_id = {c.id: c.name for c in db.query(Company).all()}

    # ---- build output (include 0 entries) ----
    out = []
    for emp in all_employees:
        emp_id_int = int(emp.id)

        emp_total_payment = float(pays.get(emp_id_int, 0.0) or 0.0)
        if emp_total_payment <= 0.0:
            emp_total_payment = float(salaries.get(emp_id_int, 0.0) or 0.0)

        total_all_hours = float(totals_all.get(emp_id_int, 0.0) or 0.0)

        # determine which company buckets we output
        if actual_company_id:
            company_ids = [actual_company_id]
        else:
            # any company this employee worked in (month)
            company_ids = sorted({cid for (eid, cid) in totals_by_company.keys() if eid == emp_id_int})
            if not company_ids and getattr(emp, "company_id", None):
                company_ids = [int(emp.company_id)]

        for cid_comp in company_ids or [None]:
            comp_hours = float(totals_by_company.get((emp_id_int, int(cid_comp))) if cid_comp is not None else 0.0) if cid_comp is not None else 0.0

            # Salary portion for this company (split salary across companies by hours)
            company_salary_portion = 0.0
            if emp_total_payment > 0 and total_all_hours > 0 and cid_comp is not None and comp_hours > 0:
                company_salary_portion = (comp_hours / total_all_hours) * emp_total_payment

            for cat in all_categories:
                cat_id_int = int(cat.id)
                h = float(hours_map.get((emp_id_int, int(cid_comp) if cid_comp is not None else 0, cat_id_int), 0.0) or 0.0)

                pct = (h / comp_hours) if (comp_hours and h) else 0.0
                allocated = pct * company_salary_portion if (company_salary_portion and pct) else 0.0

                out.append({
                    "employee": emp.name,
                    "category": cat.name,
                    "kind": cat.kind,
                    "company": comp_by_id.get(int(cid_comp), None) if cid_comp is not None else (emp.company.name if getattr(emp, "company", None) else None),
                    "hours": h,
                    "total_hours": total_all_hours,
                    "percent": pct,
                    "allocated": allocated,
                    "employee_id": emp_id_int,
                    "category_id": cat_id_int,
                })

    return out


# -------------------------
# Stage leaf x Projects (for Table 2)
# Rows = Employees
# Columns = Projects (grouped by Stage leaf name, usually "Operation")
# -------------------------
@router.get("/stage-projects")
def report_stage_projects(
    year: int = Query(...),
    month: int = Query(...),
    company_id: str = Query(...),          # accepts id OR name (like matrix-leaf-project)
    employee_id: int = Query(None),
    db: Session = Depends(get_db),
):
    # resolve company (id or name)
    try:
        cid = int(company_id)
        c = db.query(Company).filter(Company.id == cid).first()
    except Exception:
        c = db.query(Company).filter(Company.name == company_id).first()

    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    # IMPORTANT:
    # Table2 needs ONLY stage entries that have project_id
    # (because columns are Projects)
    q = (
        db.query(
            Employee.name.label("employee"),
            TimeEntry.category_id.label("stage_category_id"),
            Category.name.label("stage_name"),
            TimeEntry.project_id.label("project_id"),
            Project.name.label("project_name"),
            func.sum(TimeEntry.hours).label("hours"),
        )
        .join(Employee, Employee.id == TimeEntry.employee_id)
        .join(Category, Category.id == TimeEntry.category_id)
        .join(Project, Project.id == TimeEntry.project_id)
        .filter(
            TimeEntry.company_id == c.id,
            TimeEntry.year == year,
            TimeEntry.month == month,
            Category.kind == "stage",
            TimeEntry.project_id.isnot(None),
            TimeEntry.hours != 0,
        )
        .group_by(
            Employee.name,
            TimeEntry.category_id,
            Category.name,
            TimeEntry.project_id,
            Project.name,
        )
        .order_by(Employee.name.asc(), Category.name.asc(), Project.name.asc())
    )

    if employee_id is not None:
        q = q.filter(TimeEntry.employee_id == employee_id)

    rows = q.all()

    out = []
    for r in rows:
        out.append(
            {
                "employee": r.employee,
                "stage_category_id": int(r.stage_category_id),
                "stage_name": r.stage_name,
                "project_id": int(r.project_id),
                "project_name": r.project_name,
                "hours": float(r.hours or 0.0),
            }
        )

    return out


@router.get("/matrix")
def report_matrix(
    year: int,
    month: int,
    employee_id: int | None = Query(None),
    company_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    """
    Excel-style matrix:
      rows = stage categories (Category.kind == 'stage')
      cols = overhead categories (Category.kind == 'overhead')
      cell = allocated $ (best-effort) from employee salary distribution.

    NOTE: This is an approximation because your TimeEntry stores only one category per entry.
    We build intersection by distributing each employee's salary across stage share × overhead share.
    """

    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # Convert company_id string to actual company ID
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            actual_company_id = int(company_id)
        except ValueError:
            company = db.query(Company).filter(Company.name == company_id).first()
            if company:
                actual_company_id = company.id

    # ---- salary sources (Payment first, then EmployeeSalary fallback) ----
    pays_q = db.query(Payment.employee_id, Payment.amount).filter(
        Payment.year == year, Payment.month == month
    )
    if employee_id:
        pays_q = pays_q.filter(Payment.employee_id == employee_id)
    pays = dict(pays_q.all())

    salaries_q = db.query(EmployeeSalary.employee_id, EmployeeSalary.base_salary)
    if employee_id:
        salaries_q = salaries_q.filter(EmployeeSalary.employee_id == employee_id)
    salaries = dict(salaries_q.all())

    # ---- employees who have entries in that period/company ----
    emp_q = db.query(Employee.id, Employee.name).join(
        TimeEntry, TimeEntry.employee_id == Employee.id
    ).filter(TimeEntry.year == year, TimeEntry.month == month)

    if actual_company_id:
        emp_q = emp_q.filter(TimeEntry.company_id == actual_company_id)
    if employee_id:
        emp_q = emp_q.filter(Employee.id == employee_id)

    emp_rows = emp_q.distinct().all()
    employees = [{"id": int(eid), "name": enm} for eid, enm in emp_rows]
    if not employees:
        return []

    # ---- stage cats used in that period/company ----
    stage_q = db.query(Category.id, Category.name).join(
        TimeEntry, TimeEntry.category_id == Category.id
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        Category.kind == "stage",
    )
    # ---- overhead cats used in that period/company ----
    over_q = db.query(Category.id, Category.name).join(
        TimeEntry, TimeEntry.category_id == Category.id
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        Category.kind == "overhead",
    )

    if actual_company_id:
        stage_q = stage_q.filter(TimeEntry.company_id == actual_company_id)
        over_q = over_q.filter(TimeEntry.company_id == actual_company_id)

    stage_cats = stage_q.distinct().order_by(Category.name.asc()).all()
    over_cats = over_q.distinct().order_by(Category.name.asc()).all()

    if not stage_cats or not over_cats:
        return []

    stage_ids = [int(cid) for cid, _ in stage_cats]
    over_ids = [int(cid) for cid, _ in over_cats]

    stage_name = {int(cid): nm for cid, nm in stage_cats}
    over_name = {int(cid): nm for cid, nm in over_cats}

    def total_hours_emp(eid: int) -> float:
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.year == year,
            TimeEntry.month == month,
        )
        if actual_company_id:
            q = q.filter(TimeEntry.company_id == actual_company_id)
        return float(q.scalar() or 0.0)

    def hours_by_categories(eid: int, ids: list[int]) -> dict[int, float]:
        q = db.query(TimeEntry.category_id, func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.category_id.in_(ids),
        )
        if actual_company_id:
            q = q.filter(TimeEntry.company_id == actual_company_id)
        return {int(cid): float(h or 0.0) for cid, h in q.group_by(TimeEntry.category_id).all()}

    # matrix (stage_id, overhead_id) -> amount
    matrix: dict[tuple[int, int], float] = {}

    for e in employees:
        eid = e["id"]

        sal = float(pays.get(eid, 0.0) or 0.0)
        if sal <= 0:
            sal = float(salaries.get(eid, 0.0) or 0.0)
        if sal <= 0:
            continue

        total_h = total_hours_emp(eid)
        if total_h <= 0:
            continue

        st_hours = hours_by_categories(eid, stage_ids)
        ov_hours = hours_by_categories(eid, over_ids)

        sum_st = sum(st_hours.values())
        sum_ov = sum(ov_hours.values())

        # need both to create intersection meaningfully
        if sum_st <= 0 or sum_ov <= 0:
            continue

        # shares within their own bucket
        st_share = {sid: (st_hours.get(sid, 0.0) / sum_st) for sid in stage_ids}
        ov_share = {oid: (ov_hours.get(oid, 0.0) / sum_ov) for oid in over_ids}

        # allocate salary using outer-product
        for sid in stage_ids:
            ss = st_share.get(sid, 0.0)
            if ss <= 0:
                continue
            for oid in over_ids:
                os = ov_share.get(oid, 0.0)
                if os <= 0:
                    continue
                amt = sal * ss * os
                key = (sid, oid)
                matrix[key] = matrix.get(key, 0.0) + amt

    out = []
    for (sid, oid), amt in matrix.items():
        out.append({
            "row_category_id": sid,
            "row_name": stage_name.get(sid, f"Stage {sid}"),
            "col_category_id": oid,
            "col_name": over_name.get(oid, f"Overhead {oid}"),
            "amount": float(amt),
        })

    out.sort(key=lambda x: ((x.get("row_name") or ""), (x.get("col_name") or "")))
    return out

@router.get("/matrix-tree")
def report_matrix_tree(
    year: int,
    month: int,
    employee_id: int | None = Query(None),
    company_id: str | None = Query(None),  # accept name or id like other routes
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    """
    Tree-aware Excel matrix (company specific):

    Columns:
      - overhead leaf categories (kind='overhead')
      - PLUS special roots:
          ProSteel  -> category_type in ('aluminum','steel')
          TempoGlass-> category_type in ('production')

    Rows:
      - fixed by name if exists: General, MFOC, Fabrication, Installation
      - PLUS leaf stage nodes under special roots (aluminum/steel/production)
      - PLUS ProSteel projects as rows (TimeEntry.project_id)
    Output format matches /matrix:
      [{row_name, col_name, amount, ...}]
    """

    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # ---- resolve company_id (string -> int) ----
    actual_company_id = None
    company_name = None
    if company_id and company_id != "All":
        try:
            actual_company_id = int(company_id)
            c = db.query(Company).filter(Company.id == actual_company_id).first()
            company_name = c.name if c else None
        except ValueError:
            c = db.query(Company).filter(Company.name == company_id).first()
            if c:
                actual_company_id = c.id
                company_name = c.name

    if not actual_company_id:
        raise HTTPException(400, "matrix-tree requires a specific company_id (not All)")

    if not company_name:
        c = db.query(Company).filter(Company.id == actual_company_id).first()
        company_name = c.name if c else ""

    # ---- load categories for that company (tree) ----
    cats = db.query(Category).filter(Category.company_id == actual_company_id).all()
    if not cats:
        return []

    by_id = {c.id: c for c in cats}
    children = {}
    parent_has_child = set()
    for c in cats:
        children.setdefault(c.parent_id, []).append(c.id)
        if c.parent_id is not None:
            parent_has_child.add(c.parent_id)

    def is_leaf(cat_id: int) -> bool:
        return cat_id not in parent_has_child

    def subtree_ids(root_id: int) -> set[int]:
        # include root + all descendants
        out = set()
        stack = [root_id]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            for ch in children.get(cur, []):
                stack.append(ch)
        return out

    # ---- special roots per company ----
    # You can adjust these names/types based on your real data.
    special_col_types = []
    special_root_types_for_rows = []

    nm_low = (company_name or "").strip().lower()
    if "prosteel" in nm_low:
        special_col_types = ["aluminum", "steel"]
        special_root_types_for_rows = ["aluminum", "steel"]
    elif "tempo" in nm_low:
        special_col_types = ["production"]
        special_root_types_for_rows = ["production"]

    # ---- find special root category IDs ----
    special_root_ids = []
    for c in cats:
        ct = (c.category_type or "").strip().lower()
        if ct in set([t.lower() for t in special_col_types]):
            special_root_ids.append(c.id)

    # ---- columns ----
    # 1) overhead leaf nodes
    overhead_leaf_ids = [
        c.id for c in cats
        if (c.kind or "").strip().lower() == "overhead" and is_leaf(c.id)
    ]
    overhead_leaf_ids.sort(key=lambda cid: (by_id[cid].name or ""))

    # 2) add special roots as columns (Alum/Steel/Production)
    col_defs = []
    for cid in overhead_leaf_ids:
        col_defs.append({
            "type": "cat_leaf_overhead",
            "id": cid,
            "name": (by_id[cid].name or "").strip(),
            "subtree": {cid},  # leaf only
        })

    # special roots column = whole subtree
    for rid in special_root_ids:
        col_defs.append({
            "type": "cat_root_special",
            "id": rid,
            "name": (by_id[rid].name or (by_id[rid].category_type or "")).strip(),
            "subtree": subtree_ids(rid),
        })

    # remove empty names / duplicates
    seen_col = set()
    cols = []
    for d in col_defs:
        n = (d["name"] or "").strip()
        if not n:
            continue
        key = (d["type"], d["id"])
        if key in seen_col:
            continue
        seen_col.add(key)
        cols.append(d)

    if not cols:
        return []

    # ---- rows ----
    rows = []

    # A) fixed rows by NAME if exists in this company
    fixed_names = ["General", "MFOC", "Fabrication", "Installation"]
    name_to_cat_ids = {}
    for c in cats:
        nm = (c.name or "").strip()
        if nm:
            name_to_cat_ids.setdefault(nm.lower(), []).append(c.id)

    for nm in fixed_names:
        ids = name_to_cat_ids.get(nm.lower(), [])
        if not ids:
            continue
        # if duplicates exist, take first (or you can choose best by level)
        rid = ids[0]
        rows.append({
            "type": "cat_fixed",
            "id": rid,
            "name": (by_id[rid].name or nm).strip(),
            "subtree": subtree_ids(rid),
        })

    # B) leaf STAGES under special roots (Alum/Steel/Production)
    for root_id in special_root_ids:
        root = by_id[root_id]
        root_sub = subtree_ids(root_id)

        # pick leaf stage nodes under this root
        stage_leafs = []
        for cid in root_sub:
            c = by_id.get(cid)
            if not c:
                continue
            if (c.kind or "").strip().lower() != "stage":
                continue
            if not is_leaf(cid):
                continue
            stage_leafs.append(cid)

        stage_leafs.sort(key=lambda cid: (by_id[cid].name or ""))

        for sid in stage_leafs:
            rows.append({
                "type": "cat_stage_leaf_under_root",
                "id": sid,
                "name": f"{(root.name or root.category_type or '').strip()} / {(by_id[sid].name or '').strip()}",
                "subtree": {sid},
            })

    # C) ProSteel projects rows (TimeEntry.project_id)
    add_projects = ("prosteel" in nm_low)
    project_ids = []
    project_name = {}
    if add_projects:
        pq = db.query(Project.id, Project.name).filter(Project.company_id == actual_company_id)
        for pid, pname in pq.all():
            project_ids.append(int(pid))
            project_name[int(pid)] = (pname or "").strip()

        project_ids.sort(key=lambda pid: project_name.get(pid, ""))

        for pid in project_ids:
            rows.append({
                "type": "project",
                "id": pid,
                "name": f"Project / {project_name.get(pid, str(pid))}",
                "subtree": None,  # handled by project_id, not category subtree
            })

    if not rows:
        return []

    # ---- salary sources (Payment first, then EmployeeSalary fallback) ----
    pays_q = db.query(Payment.employee_id, Payment.amount).filter(
        Payment.year == year, Payment.month == month
    )
    if employee_id:
        pays_q = pays_q.filter(Payment.employee_id == employee_id)
    pays = dict(pays_q.all())

    salaries_q = db.query(EmployeeSalary.employee_id, EmployeeSalary.base_salary)
    if employee_id:
        salaries_q = salaries_q.filter(EmployeeSalary.employee_id == employee_id)
    salaries = dict(salaries_q.all())

    # ---- employees who have entries in that company/month ----
    emp_q = db.query(Employee.id).join(TimeEntry, TimeEntry.employee_id == Employee.id).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        TimeEntry.company_id == actual_company_id,
    )
    if employee_id:
        emp_q = emp_q.filter(Employee.id == employee_id)
    emp_ids = [int(x[0]) for x in emp_q.distinct().all()]
    if not emp_ids:
        return []

    # ---- helper: hours per employee for a "bucket" ----
    def hours_emp_for_cat_ids(eid: int, cat_ids: set[int]) -> float:
        if not cat_ids:
            return 0.0
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.company_id == actual_company_id,
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.category_id.in_(list(cat_ids)),
        )
        return float(q.scalar() or 0.0)

    def hours_emp_for_project(eid: int, pid: int) -> float:
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.company_id == actual_company_id,
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.project_id == pid,
        )
        return float(q.scalar() or 0.0)

    # ---- Build matrix using outer-product shares per employee ----
    # matrix[(row_name, col_name)] = amount
    matrix = {}

    for eid in emp_ids:
        sal = float(pays.get(eid, 0.0) or 0.0)
        if sal <= 0:
            sal = float(salaries.get(eid, 0.0) or 0.0)
        if sal <= 0:
            continue

        # column hours for this employee
        col_hours = []
        for c in cols:
            h = hours_emp_for_cat_ids(eid, c["subtree"])
            col_hours.append(h)
        sum_col = sum(col_hours)
        if sum_col <= 0:
            continue

        # row hours for this employee
        row_hours = []
        for r in rows:
            if r["type"] == "project":
                h = hours_emp_for_project(eid, int(r["id"]))
            else:
                h = hours_emp_for_cat_ids(eid, r["subtree"])
            row_hours.append(h)
        sum_row = sum(row_hours)
        if sum_row <= 0:
            continue

        # shares
        col_share = [(h / sum_col) for h in col_hours]
        row_share = [(h / sum_row) for h in row_hours]

        # allocate salary
        for ri, r in enumerate(rows):
            rs = row_share[ri]
            if rs <= 0:
                continue
            rname = (r["name"] or "").strip()
            for ci, c in enumerate(cols):
                cs = col_share[ci]
                if cs <= 0:
                    continue
                cname = (c["name"] or "").strip()
                amt = sal * rs * cs
                key = (rname, cname)
                matrix[key] = matrix.get(key, 0.0) + amt

    out = []
    for (rname, cname), amt in matrix.items():
        out.append({
            "row_name": rname,
            "col_name": cname,
            "amount": float(amt),
        })

    out.sort(key=lambda x: ((x.get("row_name") or ""), (x.get("col_name") or "")))
    return out

@router.get("/matrix-tree2")
def report_matrix_tree2(
    year: int,
    month: int,
    employee_id: int | None = Query(None),
    company_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    """
    Excel matrix (Requested orientation):

    ROWS = Overhead leaf categories (kind='overhead')  (+ optional special roots like Production/Steel/Aluminum as ROWS)
    COLS = Stage rows (fixed if exist + leaf stage under special roots) + Projects rows (ProSteel)

    Cell = allocated $ using outer-product per employee (same concept as matrix-tree).
    Returns:
      [{row_name, col_name, amount}]
    """

    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # ---- resolve company_id (string -> int) ----
    actual_company_id = None
    company_name = None
    if company_id and company_id != "All":
        try:
            actual_company_id = int(company_id)
            c = db.query(Company).filter(Company.id == actual_company_id).first()
            company_name = c.name if c else None
        except ValueError:
            c = db.query(Company).filter(Company.name == company_id).first()
            if c:
                actual_company_id = c.id
                company_name = c.name

    if not actual_company_id:
        raise HTTPException(400, "matrix-tree2 requires a specific company_id (not All)")

    if not company_name:
        c = db.query(Company).filter(Company.id == actual_company_id).first()
        company_name = c.name if c else ""

    # ---- load categories for that company (tree) ----
    cats = db.query(Category).filter(Category.company_id == actual_company_id).all()
    if not cats:
        return []

    by_id = {c.id: c for c in cats}
    children = {}
    parent_has_child = set()
    for c in cats:
        children.setdefault(c.parent_id, []).append(c.id)
        if c.parent_id is not None:
            parent_has_child.add(c.parent_id)

    def is_leaf(cat_id: int) -> bool:
        return cat_id not in parent_has_child

    def subtree_ids(root_id: int) -> set[int]:
        out = set()
        stack = [root_id]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            for ch in children.get(cur, []):
                stack.append(ch)
        return out

    nm_low = (company_name or "").strip().lower()

    # ---- special roots per company (same logic as your matrix-tree) ----
    # ProSteel -> aluminum, steel
    # TempoGlass -> production
    special_types = []
    if "prosteel" in nm_low:
        special_types = ["aluminum", "steel"]
    elif "tempo" in nm_low:
        special_types = ["production"]

    # find special root IDs by category_type
    special_root_ids = []
    stset = set([t.lower() for t in special_types])
    for c in cats:
        ct = (c.category_type or "").strip().lower()
        if ct in stset and c.parent_id is None:
            special_root_ids.append(c.id)

    # =========================================================
    # ROWS = overhead leaf (+ optional special roots as one row)
    # =========================================================
    row_defs = []

    overhead_leaf_ids = [
        c.id for c in cats
        if (c.kind or "").strip().lower() == "overhead" and is_leaf(c.id)
    ]
    overhead_leaf_ids.sort(key=lambda cid: (by_id[cid].name or ""))

    for cid in overhead_leaf_ids:
        row_defs.append({
            "type": "overhead_leaf",
            "id": cid,
            "name": (by_id[cid].name or "").strip(),
            "subtree": {cid},
        })

    # OPTIONAL: add special roots also as ROWS (مثل Production ككل)
    # إذا ما بدك ياهم rows، علّق هالبلوك.
    for rid in special_root_ids:
        row_defs.append({
            "type": "special_root_row",
            "id": rid,
            "name": (by_id[rid].name or (by_id[rid].category_type or "")).strip(),
            "subtree": subtree_ids(rid),
        })

    # clean rows
    seen_r = set()
    rows = []
    for d in row_defs:
        n = (d["name"] or "").strip()
        if not n:
            continue
        key = (d["type"], d["id"])
        if key in seen_r:
            continue
        seen_r.add(key)
        rows.append(d)

    if not rows:
        return []

    # =========================================================
    # COLS = stages (fixed + leaf under special roots) + projects
    # =========================================================
    cols = []

    # A) fixed stage names (if exist)
    fixed_stage_names = ["General", "MFOC", "Fabrication", "Installation"]
    name_to_ids = {}
    for c in cats:
        nm = (c.name or "").strip()
        if nm:
            name_to_ids.setdefault(nm.lower(), []).append(c.id)

    for nm in fixed_stage_names:
        ids = name_to_ids.get(nm.lower(), [])
        if not ids:
            continue
        cid = ids[0]
        cols.append({
            "type": "fixed_stage",
            "id": cid,
            "name": (by_id[cid].name or nm).strip(),
            "subtree": subtree_ids(cid),
        })

    # B) leaf STAGE nodes under special roots (Aluminum/Steel/Production)
    for root_id in special_root_ids:
        root = by_id[root_id]
        root_sub = subtree_ids(root_id)

        stage_leafs = []
        for cid in root_sub:
            c = by_id.get(cid)
            if not c:
                continue
            if (c.kind or "").strip().lower() != "stage":
                continue
            if not is_leaf(cid):
                continue
            stage_leafs.append(cid)

        stage_leafs.sort(key=lambda cid: (by_id[cid].name or ""))

        for sid in stage_leafs:
            cols.append({
                "type": "stage_leaf",
                "id": sid,
                "name": f"{(root.name or root.category_type or '').strip()} / {(by_id[sid].name or '').strip()}",
                "subtree": {sid},
            })

    # C) ProSteel projects as columns
    add_projects = ("prosteel" in nm_low)
    if add_projects:
        pq = db.query(Project.id, Project.name).filter(Project.company_id == actual_company_id)
        proj = [(int(pid), (pname or "").strip()) for pid, pname in pq.all()]
        proj.sort(key=lambda x: x[1])

        for pid, pname in proj:
            cols.append({
                "type": "project",
                "id": pid,
                "name": f"Project / {pname or pid}",
                "subtree": None,  # handled via project_id
            })

    # clean cols
    seen_c = set()
    clean_cols = []
    for d in cols:
        n = (d["name"] or "").strip()
        if not n:
            continue
        key = (d["type"], d["id"])
        if key in seen_c:
            continue
        seen_c.add(key)
        clean_cols.append(d)
    cols = clean_cols

    if not cols:
        return []

    # ---- salary sources (Payment first, then EmployeeSalary fallback) ----
    pays_q = db.query(Payment.employee_id, Payment.amount).filter(
        Payment.year == year, Payment.month == month
    )
    if employee_id:
        pays_q = pays_q.filter(Payment.employee_id == employee_id)
    pays = dict(pays_q.all())

    salaries_q = db.query(EmployeeSalary.employee_id, EmployeeSalary.base_salary)
    if employee_id:
        salaries_q = salaries_q.filter(EmployeeSalary.employee_id == employee_id)
    salaries = dict(salaries_q.all())

    # ---- employees who have entries in that company/month ----
    emp_q = db.query(Employee.id).join(TimeEntry, TimeEntry.employee_id == Employee.id).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        TimeEntry.company_id == actual_company_id,
    )
    if employee_id:
        emp_q = emp_q.filter(Employee.id == employee_id)
    emp_ids = [int(x[0]) for x in emp_q.distinct().all()]
    if not emp_ids:
        return []

    # ---- helper: hours per employee for a bucket ----
    def hours_emp_for_cat_ids(eid: int, cat_ids: set[int]) -> float:
        if not cat_ids:
            return 0.0
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.company_id == actual_company_id,
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.category_id.in_(list(cat_ids)),
        )
        return float(q.scalar() or 0.0)

    def hours_emp_for_project(eid: int, pid: int) -> float:
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.company_id == actual_company_id,
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.project_id == pid,
        )
        return float(q.scalar() or 0.0)

    # ---- Build matrix using outer-product shares per employee ----
    matrix = {}

    for eid in emp_ids:
        sal = float(pays.get(eid, 0.0) or 0.0)
        if sal <= 0:
            sal = float(salaries.get(eid, 0.0) or 0.0)
        if sal <= 0:
            continue

        # row hours = overhead buckets
        row_hours = []
        for r in rows:
            h = hours_emp_for_cat_ids(eid, r["subtree"])
            row_hours.append(h)
        sum_row = sum(row_hours)
        if sum_row <= 0:
            continue

        # col hours = stage/project buckets
        col_hours = []
        for c in cols:
            if c["type"] == "project":
                h = hours_emp_for_project(eid, int(c["id"]))
            else:
                h = hours_emp_for_cat_ids(eid, c["subtree"])
            col_hours.append(h)
        sum_col = sum(col_hours)
        if sum_col <= 0:
            continue

        row_share = [(h / sum_row) for h in row_hours]
        col_share = [(h / sum_col) for h in col_hours]

        for ri, r in enumerate(rows):
            rs = row_share[ri]
            if rs <= 0:
                continue
            rname = (r["name"] or "").strip()
            for ci, c in enumerate(cols):
                cs = col_share[ci]
                if cs <= 0:
                    continue
                cname = (c["name"] or "").strip()
                amt = sal * rs * cs
                key = (rname, cname)
                matrix[key] = matrix.get(key, 0.0) + amt

    out = []
    for (rname, cname), amt in matrix.items():
        out.append({
            "row_name": rname,
            "col_name": cname,
            "amount": float(amt),
        })

    out.sort(key=lambda x: ((x.get("row_name") or ""), (x.get("col_name") or "")))
    return out


@router.get("/matrix-excel")
def report_matrix_excel(
    year: int,
    month: int,
    employee_id: int | None = Query(None),
    company_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    """
    Excel-like Matrix (AS YOUR SCREENSHOT):

    ROWS:
      - Fixed stages by name if exist: Installation, Fabrication, MFOC, General
      - + Projects (ProSteel) as rows

    COLS (2-level header):
      Top groups:
        - Departments  -> overhead leaf categories
        - Production   -> special roots (Steel, Aluminum) as columns (whole subtree)

    Returns rows with:
      {row_name, col_group, col_name, amount}
    """

    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # ---- resolve company_id (string -> int) ----
    actual_company_id = None
    company_name = None
    if company_id and company_id != "All":
        try:
            actual_company_id = int(company_id)
            c = db.query(Company).filter(Company.id == actual_company_id).first()
            company_name = c.name if c else None
        except ValueError:
            c = db.query(Company).filter(Company.name == company_id).first()
            if c:
                actual_company_id = c.id
                company_name = c.name

    if not actual_company_id:
        raise HTTPException(400, "matrix-excel requires a specific company_id (not All)")

    if not company_name:
        c = db.query(Company).filter(Company.id == actual_company_id).first()
        company_name = c.name if c else ""

    nm_low = (company_name or "").strip().lower()

    # ---- load categories for that company (tree) ----
    cats = db.query(Category).filter(Category.company_id == actual_company_id).all()
    if not cats:
        return []

    by_id = {c.id: c for c in cats}
    children = {}
    parent_has_child = set()
    for c in cats:
        children.setdefault(c.parent_id, []).append(c.id)
        if c.parent_id is not None:
            parent_has_child.add(c.parent_id)

    def is_leaf(cat_id: int) -> bool:
        return cat_id not in parent_has_child

    def subtree_ids(root_id: int) -> set[int]:
        out = set()
        stack = [root_id]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            for ch in children.get(cur, []):
                stack.append(ch)
        return out

    # =========================================================
    # COLS (Excel-style): Departments + Production( Steel/Aluminum )
    # =========================================================
    cols = []

    # Departments = overhead leaf
    overhead_leaf_ids = [
        c.id for c in cats
        if (c.kind or "").strip().lower() == "overhead" and is_leaf(c.id)
    ]
    overhead_leaf_ids.sort(key=lambda cid: (by_id[cid].name or ""))

    for cid in overhead_leaf_ids:
        cols.append({
            "group": "Departments",
            "id": cid,
            "name": (by_id[cid].name or "").strip(),
            "subtree": {cid},
            "type": "overhead_leaf",
        })

    # Production group columns:
    # ProSteel: steel + aluminum roots (category_type)
    # TempoGlass: (optional) production root only => but your screenshot is ProSteel
    special_types = []
    if "prosteel" in nm_low:
        special_types = ["steel", "aluminum"]
    elif "tempo" in nm_low:
        # if you ever want TempoGlass as Production only:
        special_types = ["production"]

    stset = set([t.lower() for t in special_types])
    special_root_ids = []
    for c in cats:
        ct = (c.category_type or "").strip().lower()
        if ct in stset and c.parent_id is None:
            special_root_ids.append(c.id)


    # enforce stable order Steel then Aluminum (like Excel)
    def _special_sort(cid: int):
        ct = (by_id[cid].category_type or "").strip().lower()
        order = {"steel": 0, "aluminum": 1, "production": 0}
        return (order.get(ct, 99), (by_id[cid].name or ct))

    special_root_ids.sort(key=_special_sort)

    for rid in special_root_ids:
        root = by_id[rid]
        nm = (root.name or root.category_type or "").strip()
        cols.append({
            "group": "Production",
            "id": rid,
            "name": nm,
            "subtree": subtree_ids(rid),  # whole subtree => hours under steel/aluminum
            "type": "special_root",
        })

    # if no cols -> empty
    cols = [c for c in cols if (c.get("name") or "").strip()]
    if not cols:
        return []

    # =========================================================
    # ROWS (Excel-style): Fixed stages + Projects
    # =========================================================
    rows = []

    fixed_stage_names = ["Installation", "Fabrication", "MFOC", "General"]
    name_to_ids = {}
    for c in cats:
        nm = (c.name or "").strip()
        if nm:
            name_to_ids.setdefault(nm.lower(), []).append(c.id)

    for nm in fixed_stage_names:
        ids = name_to_ids.get(nm.lower(), [])
        if not ids:
            continue
        cid = ids[0]
        rows.append({
            "type": "fixed_stage",
            "id": cid,
            "name": (by_id[cid].name or nm).strip(),
            "subtree": subtree_ids(cid),
        })

    # Projects rows for ProSteel
    add_projects = ("prosteel" in nm_low)
    if add_projects:
        # try to use code if exists, else name
        # (إذا Project model ما فيه code، خليه name)
        pq = db.query(Project.id, Project.name).filter(Project.company_id == actual_company_id).all()
        proj = [(int(pid), (pname or "").strip()) for pid, pname in pq]
        proj.sort(key=lambda x: x[1])

        for pid, pname in proj:
            # Excel screenshot shows P1/P2/P3... so keep short label if possible
            rows.append({
                "type": "project",
                "id": pid,
                "name": (pname or str(pid)).strip(),
                "subtree": None,
            })

    if not rows:
        return []

    # =========================================================
    # Salary sources
    # =========================================================
    pays_q = db.query(Payment.employee_id, Payment.amount).filter(Payment.year == year, Payment.month == month)
    if employee_id:
        pays_q = pays_q.filter(Payment.employee_id == employee_id)
    pays = dict(pays_q.all())

    salaries_q = db.query(EmployeeSalary.employee_id, EmployeeSalary.base_salary)
    if employee_id:
        salaries_q = salaries_q.filter(EmployeeSalary.employee_id == employee_id)
    salaries = dict(salaries_q.all())

    # employees who have entries for this company/month
    emp_q = db.query(Employee.id).join(TimeEntry, TimeEntry.employee_id == Employee.id).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        TimeEntry.company_id == actual_company_id,
    )
    if employee_id:
        emp_q = emp_q.filter(Employee.id == employee_id)
    emp_ids = [int(x[0]) for x in emp_q.distinct().all()]
    if not emp_ids:
        return []

    def hours_emp_for_cat_ids(eid: int, cat_ids: set[int]) -> float:
        if not cat_ids:
            return 0.0
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.company_id == actual_company_id,
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.category_id.in_(list(cat_ids)),
        )
        return float(q.scalar() or 0.0)

    def hours_emp_for_project(eid: int, pid: int) -> float:
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.company_id == actual_company_id,
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.project_id == pid,
        )
        return float(q.scalar() or 0.0)

    # matrix[(row_name, col_group, col_name)] = amount
    matrix = {}

    for eid in emp_ids:
        sal = float(pays.get(eid, 0.0) or 0.0)
        if sal <= 0:
            sal = float(salaries.get(eid, 0.0) or 0.0)
        if sal <= 0:
            continue

        # row hours
        row_hours = []
        for r in rows:
            if r["type"] == "project":
                h = hours_emp_for_project(eid, int(r["id"]))
            else:
                h = hours_emp_for_cat_ids(eid, r["subtree"])
            row_hours.append(h)
        sum_row = sum(row_hours)
        if sum_row <= 0:
            continue

        # col hours
        col_hours = []
        for c in cols:
            h = hours_emp_for_cat_ids(eid, c["subtree"])
            col_hours.append(h)
        sum_col = sum(col_hours)
        if sum_col <= 0:
            continue

        row_share = [(h / sum_row) for h in row_hours]
        col_share = [(h / sum_col) for h in col_hours]

        for ri, r in enumerate(rows):
            rs = row_share[ri]
            if rs <= 0:
                continue
            rname = (r["name"] or "").strip()
            for ci, c in enumerate(cols):
                cs = col_share[ci]
                if cs <= 0:
                    continue
                cgrp = (c["group"] or "").strip()
                cname = (c["name"] or "").strip()
                amt = sal * rs * cs
                key = (rname, cgrp, cname)
                matrix[key] = matrix.get(key, 0.0) + amt

    out = []
    for (rname, cgrp, cname), amt in matrix.items():
        out.append({
            "row_name": rname,
            "col_group": cgrp,   # "Departments" or "Production"
            "col_name": cname,   # Department name OR Steel/Aluminum
            "amount": float(amt),
        })

    out.sort(key=lambda x: ((x.get("row_name") or ""), (x.get("col_group") or ""), (x.get("col_name") or "")))
    return out


@router.get("/matrix-leaf-project")
def report_matrix_leaf_project(
    year: int,
    month: int,
    company_id: str | None = Query(None),
    employee_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    """
    Matrix: ROWS = Projects
            COLS = Leaf Categories (last node) for this company
            CELL = allocated $ based on REAL entries (not outer-product)
    Returns:
      [{row_name, col_group, col_name, amount}]
    """

    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # ---- resolve company_id -> int ----
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            actual_company_id = int(company_id)
        except ValueError:
            c = db.query(Company).filter(Company.name == company_id).first()
            if c:
                actual_company_id = c.id

    if not actual_company_id:
        raise HTTPException(400, "matrix-leaf-project requires a specific company_id (not All)")

    # ---- load company categories (to detect leaf nodes) ----
    cats = db.query(Category).filter(Category.company_id == actual_company_id).all()
    if not cats:
        return []

    by_id = {c.id: c for c in cats}
    parent_has_child = set()
    for c in cats:
        if c.parent_id is not None:
            parent_has_child.add(c.parent_id)

    def is_leaf(cid: int) -> bool:
        return cid not in parent_has_child

    # ---- leaf columns (last node) ----
    leaf_ids = [c.id for c in cats if is_leaf(c.id)]
    leaf_ids.sort(key=lambda cid: (by_id[cid].name or ""))

    # (optional) group name from kind/category_type if you want
    def col_group_for(cat: Category) -> str:
        # you can change this rule
        k = (cat.kind or "").strip().lower()
        if k == "overhead":
            return "Departments"
        if k == "stage":
            return "Stages"
        return (cat.category_type or "Other").strip() or "Other"

    # ---- salary sources ----
    pays_q = db.query(Payment.employee_id, Payment.amount).filter(Payment.year == year, Payment.month == month)
    if employee_id:
        pays_q = pays_q.filter(Payment.employee_id == employee_id)
    pays = dict(pays_q.all())

    salaries_q = db.query(EmployeeSalary.employee_id, EmployeeSalary.base_salary)
    if employee_id:
        salaries_q = salaries_q.filter(EmployeeSalary.employee_id == employee_id)
    salaries = dict(salaries_q.all())

    # ---- employees in this company/month ----
    emp_q = db.query(Employee.id).join(TimeEntry, TimeEntry.employee_id == Employee.id).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        TimeEntry.company_id == actual_company_id,
    )
    if employee_id:
        emp_q = emp_q.filter(Employee.id == employee_id)
    emp_ids = [int(x[0]) for x in emp_q.distinct().all()]
    if not emp_ids:
        return []

    # ---- projects list (rows) from entries OR from Project table ----
    # safest: projects that actually appear in TimeEntry for that period/company
    proj_q = db.query(Project.id, Project.name).join(TimeEntry, TimeEntry.project_id == Project.id).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        TimeEntry.company_id == actual_company_id,
    )
    proj_rows = proj_q.distinct().all()
    project_ids = [int(pid) for pid, _ in proj_rows]
    project_name = {int(pid): (nm or str(pid)).strip() for pid, nm in proj_rows}
    if not project_ids:
        return []

    project_ids.sort(key=lambda pid: project_name.get(pid, ""))

    # ---- helper: total hours per employee (company/month) ----
# ---- helper: total hours per employee (ALL companies / month) ----
    def total_hours_emp_all(eid: int) -> float:
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.year == year,
            TimeEntry.month == month,
        )
        return float(q.scalar() or 0.0)

    # ---- helper: total hours per employee (THIS company / month) ----
    def total_hours_emp_company(eid: int) -> float:
        q = db.query(func.coalesce(func.sum(TimeEntry.hours), 0.0)).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.company_id == actual_company_id,
            TimeEntry.year == year,
            TimeEntry.month == month,
        )
        return float(q.scalar() or 0.0)

    # ---- allocated by REAL entry: (hours/emp_total)*salary then sum by (project, leaf) ----
    matrix = {}

    for eid in emp_ids:
        sal = float(pays.get(eid, 0.0) or 0.0)
        if sal <= 0:
            sal = float(salaries.get(eid, 0.0) or 0.0)
        if sal <= 0:
            continue

        th = total_hours_emp_all(eid)   # ✅ FIX
        if th <= 0:
            continue

        q = db.query(
            TimeEntry.project_id,
            TimeEntry.category_id,
            func.coalesce(func.sum(TimeEntry.hours), 0.0),
        ).filter(
            TimeEntry.employee_id == eid,
            TimeEntry.company_id == actual_company_id,
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.project_id.isnot(None),
            TimeEntry.category_id.in_(leaf_ids),
        ).group_by(TimeEntry.project_id, TimeEntry.category_id)

        for pid, cid, h in q.all():
            pid = int(pid)
            cid = int(cid)
            h = float(h or 0.0)
            if h <= 0:
                continue

            allocated = (h / th) * sal
           


            row_name = project_name.get(pid, f"Project {pid}")
            cat = by_id.get(cid)
            col_name = (cat.name or str(cid)).strip() if cat else str(cid)
            col_group = col_group_for(cat) if cat else "Other"

            key = (row_name, col_group, col_name, cid)
            matrix[key] = matrix.get(key, 0.0) + allocated

    out = []
    for (rname, cgrp, cname, ccid), amt in matrix.items():
        out.append({"row_name": rname, "col_group": cgrp, "col_name": cname, "col_category_id": int(ccid), "amount": float(amt)})

    out.sort(key=lambda x: ((x["row_name"] or ""), (x["col_group"] or ""), (x["col_name"] or "")))
    return out

@router.get("/by-project")
def report_by_project(year: int, month: int,
                      company_id: str | None = Query(None),
                      employee_id: int | None = Query(None),
                      include_budget: bool = Query(True),
                      db: Session = Depends(get_db),
                      _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))):
    """Report hours broken down by project with budget tracking"""
    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # Convert company_id string to actual company ID
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            # If it's a numeric string, treat as ID
            actual_company_id = int(company_id)
        except ValueError:
            # If it's a name, find the corresponding ID
            company = db.query(Company).filter(Company.name == company_id).first()
            if company:
                actual_company_id = company.id
    
    # Query for project-related entries (categories with kind = 'project_name')
    query = db.query(
        Category.name.label('project_name'),
        Category.budget.label('budget'),
        Employee.name.label('employee_name'),
        func.coalesce(func.sum(TimeEntry.hours), 0.0).label('total_hours'),
        TimeEntry.employee_id,
        TimeEntry.category_id
    ).join(
        TimeEntry, TimeEntry.category_id == Category.id
    ).join(
        Employee, Employee.id == TimeEntry.employee_id
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        Category.kind == 'project_name'
    )

    # Apply filters
    if actual_company_id:
        query = query.filter(TimeEntry.company_id == actual_company_id)
    if employee_id:
        query = query.filter(TimeEntry.employee_id == employee_id)

    results = query.group_by(
        Category.name, Category.budget, Employee.name, TimeEntry.employee_id, TimeEntry.category_id
    ).order_by(Category.name, Employee.name).all()

    # Get all employees for the company (if company filter is applied)
    employees_query = db.query(Employee)
    if actual_company_id:
        employees_query = employees_query.filter(Employee.company_id == actual_company_id)
    if employee_id:
        employees_query = employees_query.filter(Employee.id == employee_id)
    all_employees = employees_query.all()

    # Get all project categories
    project_categories = db.query(Category).filter(Category.kind == 'project_name').all()

    # Create a mapping of existing results
    existing_results = {}
    for project_name, budget, employee_name, total_hours, emp_id, cat_id in results:
        key = (cat_id, emp_id)  # (project_id, employee_id)
        existing_results[key] = {
            "project_name": project_name,
            "budget": budget,
            "employee_name": employee_name,
            "total_hours": total_hours,
            "emp_id": emp_id,
            "cat_id": cat_id
        }

    out = []
    for proj_cat in project_categories:
        for emp in all_employees:
            key = (proj_cat.id, emp.id)
            if key in existing_results:
                # Use existing result with actual hours
                result = existing_results[key]
                budget_float = float(result["budget"]) if result["budget"] is not None else 0.0
                total_hours_float = float(result["total_hours"])
                budget_utilization = (total_hours_float / budget_float * 100) if budget_float > 0 else 0.0

                project_data = {
                    "project": result["project_name"],
                    "employee": result["employee_name"],
                    "employee_id": result["emp_id"],
                    "project_id": result["cat_id"],
                    "total_hours": total_hours_float,
                    "year": year,
                    "month": month
                }
            else:
                # Create entry with 0 hours for employee who didn't work on this project
                budget_float = float(proj_cat.budget) if proj_cat.budget is not None else 0.0
                total_hours_float = 0.0
                budget_utilization = 0.0

                project_data = {
                    "project": proj_cat.name,
                    "employee": emp.name,
                    "employee_id": emp.id,
                    "project_id": proj_cat.id,
                    "total_hours": total_hours_float,
                    "year": year,
                    "month": month
                }

            if include_budget:
                project_data.update({
                    "budget": budget_float,
                    "budget_utilization_percent": budget_utilization,
                    "remaining_budget_hours": budget_float - total_hours_float
                })

            out.append(project_data)
    return out


@router.get("/by-department")
def report_by_department(year: int, month: int,
                         company_id: str | None = Query(None),
                         employee_id: int | None = Query(None),
                         db: Session = Depends(get_db),
                         _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))):
    """Report hours broken down by department (overhead categories)"""
    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # Convert company_id string to actual company ID
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            # If it's a numeric string, treat as ID
            actual_company_id = int(company_id)
        except ValueError:
            # If it's a name, find the corresponding ID
            company = db.query(Company).filter(Company.name == company_id).first()
            if company:
                actual_company_id = company.id
    
    # Query for department-related entries (categories with kind = 'overhead')
    query = db.query(
        Category.name.label('department_name'),
        Employee.name.label('employee_name'),
        func.coalesce(func.sum(TimeEntry.hours), 0.0).label('total_hours'),
        TimeEntry.employee_id,
        TimeEntry.category_id
    ).join(
        TimeEntry, TimeEntry.category_id == Category.id
    ).join(
        Employee, Employee.id == TimeEntry.employee_id
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month,
        Category.kind == 'overhead'
    )

    # Apply filters
    if actual_company_id:
        query = query.filter(TimeEntry.company_id == actual_company_id)
    if employee_id:
        query = query.filter(TimeEntry.employee_id == employee_id)

    results = query.group_by(
        Category.name, Employee.name, TimeEntry.employee_id, TimeEntry.category_id
    ).order_by(Category.name, Employee.name).all()

    # Get all employees for the company (if company filter is applied)
    employees_query = db.query(Employee)
    if actual_company_id:
        employees_query = employees_query.filter(Employee.company_id == actual_company_id)
    if employee_id:
        employees_query = employees_query.filter(Employee.id == employee_id)
    all_employees = employees_query.all()

    # Get all department categories
    dept_categories = db.query(Category).filter(Category.kind == 'overhead').all()

    # Create a mapping of existing results
    existing_results = {}
    for dept_name, employee_name, total_hours, emp_id, cat_id in results:
        key = (cat_id, emp_id)  # (department_id, employee_id)
        existing_results[key] = {
            "dept_name": dept_name,
            "employee_name": employee_name,
            "total_hours": total_hours,
            "emp_id": emp_id,
            "cat_id": cat_id
        }

    out = []    
    for dept_cat in dept_categories:
        for emp in all_employees:
            key = (dept_cat.id, emp.id)
            if key in existing_results:
                # Use existing result with actual hours
                result = existing_results[key]
                out.append({
                    "department": result["dept_name"],
                    "employee": result["employee_name"],
                    "employee_id": result["emp_id"],
                    "department_id": result["cat_id"],
                    "total_hours": float(result["total_hours"]),
                    "year": year,
                    "month": month
                })
            else:
                # Create entry with 0 hours for employee who didn't work in this department
                out.append({
                    "department": dept_cat.name,
                    "employee": emp.name,
                    "employee_id": emp.id,
                    "department_id": dept_cat.id,
                    "total_hours": 0.0,
                    "year": year,
                    "month": month
                })
    return out


@router.get("/by-employee")
def report_by_employee(year: int, month: int,
                       company_id: str | None = Query(None),
                       category_id: int | None = Query(None),
                       db: Session = Depends(get_db),
                       _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))):
    """Report hours broken down by employee"""
    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # Convert company_id string to actual company ID
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            # If it's a numeric string, treat as ID
            actual_company_id = int(company_id)
        except ValueError:
            # If it's a name, find the corresponding ID
            company = db.query(Company).filter(Company.name == company_id).first()
            if company:
                actual_company_id = company.id
    
    query = db.query(
        Employee.name.label('employee_name'),
        Category.name.label('category_name'),
        Category.kind.label('category_kind'),
        func.coalesce(func.sum(TimeEntry.hours), 0.0).label('total_hours'),
        TimeEntry.employee_id,
        TimeEntry.category_id
    ).join(
        TimeEntry, TimeEntry.employee_id == Employee.id
    ).join(
        Category, Category.id == TimeEntry.category_id
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month
    )

    # Apply filters
    if actual_company_id:
        query = query.filter(TimeEntry.company_id == actual_company_id)
    if category_id:
        query = query.filter(TimeEntry.category_id == category_id)

    results = query.group_by(
        Employee.name, Category.name, Category.kind, TimeEntry.employee_id, TimeEntry.category_id
    ).order_by(Employee.name, Category.kind, Category.name).all()

    # Get all employees for the company (if company filter is applied)
    employees_query = db.query(Employee)
    if actual_company_id:
        employees_query = employees_query.filter(Employee.company_id == actual_company_id)
    all_employees = employees_query.all()

    # Get all categories (if category filter is applied)
    categories_query = db.query(Category)
    if category_id:
        categories_query = categories_query.filter(Category.id == category_id)
    all_categories = categories_query.all()

    # Create a mapping of existing results
    existing_results = {}
    for emp_name, cat_name, cat_kind, total_hours, emp_id, cat_id in results:
        key = (emp_id, cat_id)  # (employee_id, category_id)
        existing_results[key] = {
            "emp_name": emp_name,
            "cat_name": cat_name,
            "cat_kind": cat_kind,
            "total_hours": total_hours,
            "emp_id": emp_id,
            "cat_id": cat_id
        }

    out = []    
    for emp in all_employees:
        for cat in all_categories:
            key = (emp.id, cat.id)
            if key in existing_results:
                # Use existing result with actual hours
                result = existing_results[key]
                out.append({
                    "employee": result["emp_name"],
                    "employee_id": result["emp_id"],
                    "category": result["cat_name"],
                    "category_kind": result["cat_kind"],
                    "category_id": result["cat_id"],
                    "total_hours": float(result["total_hours"]),
                    "year": year,
                    "month": month
                })
            else:
                # Create entry with 0 hours for employee-category combination without entries
                out.append({
                    "employee": emp.name,
                    "employee_id": emp.id,
                    "category": cat.name,
                    "category_kind": cat.kind,
                    "category_id": cat.id,
                    "total_hours": 0.0,
                    "year": year,
                    "month": month
                })
    return out


@router.get("/summary")
def report_summary(year: int, month: int,
                   company_id: str | None = Query(None),
                   employee_id: int | None = Query(None),
                   category_kind: str | None = Query(None),
                   db: Session = Depends(get_db),
                   _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))):
    """Summary report with aggregated data"""
    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # Convert company_id string to actual company ID
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            # If it's a numeric string, treat as ID
            actual_company_id = int(company_id)
        except ValueError:
            # If it's a name, find the corresponding ID
            company = db.query(Company).filter(Company.name == company_id).first()
            if company:
                actual_company_id = company.id
    
    # Total hours by category kind
    query = db.query(
        Category.kind,
        func.sum(TimeEntry.hours).label('total_hours'),
        func.count(TimeEntry.id).label('entry_count')
    ).join(
        TimeEntry, TimeEntry.category_id == Category.id
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month
    )

    # Apply filters
    if actual_company_id:
        query = query.filter(TimeEntry.company_id == actual_company_id)
    if employee_id:
        query = query.filter(TimeEntry.employee_id == employee_id)
    if category_kind:
        query = query.filter(Category.kind == category_kind)

    kind_results = query.group_by(Category.kind).all()

    # Total hours by employee (with time entries)
    emp_query_with_entries = db.query(
        Employee.name,
        func.sum(TimeEntry.hours).label('total_hours'),
        func.count(TimeEntry.id).label('entry_count')
    ).join(
        TimeEntry, TimeEntry.employee_id == Employee.id
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month
    )

    # Apply filters
    if actual_company_id:
        emp_query_with_entries = emp_query_with_entries.filter(TimeEntry.company_id == actual_company_id)
    if employee_id:
        emp_query_with_entries = emp_query_with_entries.filter(TimeEntry.employee_id == employee_id)
    if category_kind:
        emp_query_with_entries = emp_query_with_entries.join(Category, TimeEntry.category_id == Category.id).filter(Category.kind == category_kind)

    emp_results_with_entries = emp_query_with_entries.group_by(Employee.name).all()

    # Get all employees for the company (if company filter is applied) to include those without entries
    employees_query = db.query(Employee)
    if actual_company_id:
        employees_query = employees_query.filter(Employee.company_id == actual_company_id)
    if employee_id:
        employees_query = employees_query.filter(Employee.id == employee_id)
    all_employees = employees_query.all()

    # Create a mapping of employees with time entries
    emp_hours_map = {emp_name: (float(hours) if hours else 0.0, count) for emp_name, hours, count in emp_results_with_entries}
    
    # Create complete employee list including those without time entries
    emp_results = []
    for emp in all_employees:
        if emp.name in emp_hours_map:
            total_hours, entry_count = emp_hours_map[emp.name]
            emp_results.append((emp.name, total_hours, entry_count))
        else:
            emp_results.append((emp.name, 0.0, 0))

    # Overall totals
    total_query = db.query(
        func.sum(TimeEntry.hours).label('grand_total'),
        func.count(TimeEntry.id).label('total_entries')
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month
    )

    if company_id:
        total_query = total_query.filter(TimeEntry.company_id == company_id)
    if employee_id:
        total_query = total_query.filter(TimeEntry.employee_id == employee_id)

    grand_total, total_entries = total_query.first()

    return {
        "summary": {
            "year": year,
            "month": month,
            "grand_total_hours": float(grand_total) if grand_total else 0.0,
            "total_entries": total_entries if total_entries else 0,
            "company_id": company_id,
            "employee_id": employee_id,
            "category_kind": category_kind
        },
        "by_category_kind": [
            {
                "kind": kind,
                "total_hours": float(hours) if hours else 0.0,
                "entry_count": count
            }
            for kind, hours, count in kind_results
        ],
        "by_employee": [
            {
                "employee": emp_name,
                "total_hours": float(hours),
                "entry_count": count
            }
            for emp_name, hours, count in emp_results
        ]
    }


@router.get("/project-budget")
def report_project_budget(year: int, month: int,
                          company_id: str | None = Query(None),
                          db: Session = Depends(get_db),
                          _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))):
    """Report showing project budgets vs actual hours"""
    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # Get project hours and budget information
    query = db.query(
        Category.name.label('project_name'),
        Category.budget.label('budget'),
        func.coalesce(func.sum(TimeEntry.hours), 0.0).label('actual_hours'),
        Category.id.label('project_id')
    ).outerjoin(
        TimeEntry, and_(
            TimeEntry.category_id == Category.id,
            TimeEntry.year == year,
            TimeEntry.month == month
        )
    ).filter(
        Category.kind == 'project_name'
    )

    # Convert company_id string to actual company ID
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            # If it's a numeric string, treat as ID
            actual_company_id = int(company_id)
        except ValueError:
            # If it's a name, find the corresponding ID
            company = db.query(Company).filter(Company.name == company_id).first()
            if company:
                actual_company_id = company.id
    
    # Apply company filter if specified
    if actual_company_id:
        # For company-specific budget report, we need to show projects with entries for that company
        # We'll use a subquery to get the projects that have time entries for the specified company
        subquery = db.query(
            Category.id.label('cat_id'),
            Category.name.label('project_name'),
            Category.budget.label('budget'),
            func.coalesce(func.sum(TimeEntry.hours), 0.0).label('actual_hours')
        ).join(
            TimeEntry, TimeEntry.category_id == Category.id
        ).filter(
            TimeEntry.year == year,
            TimeEntry.month == month,
            TimeEntry.company_id == actual_company_id,
            Category.kind == 'project_name'
        ).group_by(
            Category.id, Category.name, Category.budget
        ).subquery()
        
        # Now get the results from the subquery
        results = db.query(
            subquery.c.project_name,
            subquery.c.budget,
            subquery.c.actual_hours,
            subquery.c.cat_id
        ).order_by(subquery.c.project_name).all()
    else:
        results = query.group_by(
            Category.name, Category.budget, Category.id
        ).order_by(Category.name).all()

    out = []
    for project_name, budget, actual_hours, project_id in results:
        budget_float = float(budget) if budget is not None else 0.0
        actual_float = float(actual_hours) if actual_hours is not None else 0.0
        budget_utilization = (actual_float / budget_float * 100) if budget_float > 0 else 0.0

        out.append({
            "project": project_name,
            "project_id": project_id,
            "budget": budget_float,
            "actual_hours": actual_float,
            "budget_utilization_percent": budget_utilization,
            "remaining_budget": budget_float - actual_float,
            "year": year,
            "month": month
        })
    return out


@router.get("/company-summary")
def report_company_summary(year: int, month: int,
                           company_id: str | None = Query(None),
                           db: Session = Depends(get_db),
                           _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))):
    """Company-based summary report showing all data for a specific company or all companies"""
    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")

    # Build query for time entries
    entries_query = db.query(
        TimeEntry,
        Employee.name.label('employee_name'),
        Category.name.label('category_name'),
        Category.kind.label('category_kind')
    ).join(
        Employee, Employee.id == TimeEntry.employee_id
    ).join(
        Category, Category.id == TimeEntry.category_id
    ).filter(
        TimeEntry.year == year,
        TimeEntry.month == month
    )
    
    # Convert company_id string to actual company ID
    actual_company_id = None
    if company_id and company_id != "All":
        try:
            # If it's a numeric string, treat as ID
            actual_company_id = int(company_id)
        except ValueError:
            # If it's a name, find the corresponding ID
            company = db.query(Company).filter(Company.name == company_id).first()
            if company:
                actual_company_id = company.id
    
    # Filter by company if specified
    if actual_company_id:
        entries_query = entries_query.filter(TimeEntry.company_id == actual_company_id)
    
    entries_query = entries_query.order_by(Employee.name, Category.kind, Category.name)
    entries_result = entries_query.all()

    # Organize by employee
    company_data = {}
    total_company_hours = 0

    for entry, emp_name, cat_name, cat_kind in entries_result:
        if emp_name not in company_data:
            company_data[emp_name] = {
                "employee_id": entry.employee_id,
                "total_hours": 0,
                "categories": {}
            }

        # Add to employee's total
        company_data[emp_name]["total_hours"] += float(entry.hours)
        total_company_hours += float(entry.hours)

        # Add category data
        if cat_name not in company_data[emp_name]["categories"]:
            company_data[emp_name]["categories"][cat_name] = {
                "category_id": entry.category_id,
                "kind": cat_kind,
                "hours": 0
            }

        company_data[emp_name]["categories"][cat_name]["hours"] += float(entry.hours)

    # Get company info if company_id was specified
    company_info = None
    if company_id:
        company = db.query(Company).filter(Company.id == actual_company_id).first() if actual_company_id else None
        if company:
            company_info = {
                "id": actual_company_id,
                "name": company.name
            }
    
    return {
        "company": company_info,
        "period": {
            "year": year,
            "month": month
        },
        "summary": {
            "total_hours": total_company_hours,
            "total_employees": len(company_data),
            "total_categories": len(set(cat for emp_data in company_data.values() for cat in emp_data["categories"]))
        },
        "employees": company_data
    }