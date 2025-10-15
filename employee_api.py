"""
fake employee API
"""

# ---------------------------
# Fake Employee Data
# ---------------------------

employees = [
    {
        "employee_id": 1001,
        "employee_name": "Alice Rossi",
        "dept_name": "OCI Engineering",
        "location": "Milan, Italy",
        "employee_level": "IC4",
        "vacation_days_taken": 12,
    },
    {
        "employee_id": 1002,
        "employee_name": "Bruno Schneider",
        "dept_name": "Cloud Infrastructure",
        "location": "Zurich, Switzerland",
        "employee_level": "IC3",
        "vacation_days_taken": 7,
    },
    {
        "employee_id": 1003,
        "employee_name": "Carla Dupont",
        "dept_name": "AI Services",
        "location": "Paris, France",
        "employee_level": "IC5",
        "vacation_days_taken": 18,
    },
    {
        "employee_id": 1004,
        "employee_name": "David Novak",
        "dept_name": "Database Development",
        "location": "Prague, Czech Republic",
        "employee_level": "IC2",
        "vacation_days_taken": 4,
    },
    {
        "employee_id": 1005,
        "employee_name": "Elena Popescu",
        "dept_name": "Analytics & BI",
        "location": "Bucharest, Romania",
        "employee_level": "IC3",
        "vacation_days_taken": 10,
    },
    {
        "employee_id": 1006,
        "employee_name": "Francesco Greco",
        "dept_name": "Finance Systems",
        "location": "Rome, Italy",
        "employee_level": "IC6",
        "vacation_days_taken": 21,
    },
    {
        "employee_id": 1007,
        "employee_name": "Greta Müller",
        "dept_name": "Human Resources",
        "location": "Berlin, Germany",
        "employee_level": "IC2",
        "vacation_days_taken": 6,
    },
    {
        "employee_id": 1008,
        "employee_name": "Hugo Fernandez",
        "dept_name": "Customer Success",
        "location": "Madrid, Spain",
        "employee_level": "IC4",
        "vacation_days_taken": 14,
    },
    {
        "employee_id": 1009,
        "employee_name": "Isabelle Laurent",
        "dept_name": "Legal & Compliance",
        "location": "Brussels, Belgium",
        "employee_level": "IC5",
        "vacation_days_taken": 19,
    },
    {
        "employee_id": 1010,
        "employee_name": "Jakob Johansson",
        "dept_name": "Security Engineering",
        "location": "Stockholm, Sweden",
        "employee_level": "IC3",
        "vacation_days_taken": 9,
    },
]

# ---------------------------
# Lookup Function
# ---------------------------


def get_employee(identifier: str | int) -> dict | None:
    """
    Return employee information by employee_id (int) or employee_name (str).

    Args:
        identifier: int or str — the employee id or name (case-insensitive).

    Returns:
        dict | None: Employee dictionary if found, else None.
    """
    for emp in employees:
        if isinstance(identifier, int) and emp["employee_id"] == identifier:
            return emp
        if (
            isinstance(identifier, str)
            and emp["employee_name"].lower() == identifier.lower()
        ):
            return emp
    return None


def list_employees() -> list[dict]:
    """
    Return the list of all employees.

    Returns:
        list[dict]: List of employee dictionaries.
    """
    return employees
